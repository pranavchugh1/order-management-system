import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from pymongo import UpdateOne
from pymongo.errors import DuplicateKeyError
from starlette.concurrency import run_in_threadpool

from auth import current_user, require_page
from database import db
from order_service import OrderIn, StrictModel, canonical_orders, number_documents
from parcel_parser import catalogue_index, parse_parcels

router = APIRouter(prefix='/api/bulk', dependencies=[Depends(require_page('bulk'))])


class Block(StrictModel):
    party_id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=10000)
    remarks: str = Field(default='', max_length=1000)


class PreviewIn(StrictModel):
    blocks: list[Block] = Field(min_length=1, max_length=50)


class CommitIn(StrictModel):
    request_id: uuid.UUID
    orders: list[OrderIn] = Field(min_length=1, max_length=50)


def parse_blocks(blocks, parties, catalogues):
    party_map = {p['id']: p for p in parties}
    item_index = catalogue_index(catalogues)
    orders, errors, parcel_total = [], [], 0
    for bi, block in enumerate(blocks):
        party = party_map.get(block.party_id)
        if not party:
            errors.append({'block': bi + 1, 'line': 0, 'text': '', 'message': f'Block {bi + 1}: party is unknown. Select an existing party.'}); continue
        parcels, block_errors = parse_parcels(block.text, item_index)
        for err in block_errors:
            errors.append({'block': bi + 1, **err, 'party_name': party['name']})
        if parcel_total + len(parcels) > 500:
            errors.append({'block': bi + 1, 'line': 0, 'text': party['name'], 'message': 'Batch limit exceeded: 500 parcels per batch.'}); continue
        if len(parcels) > 100:
            errors.append({'block': bi + 1, 'line': 0, 'text': party['name'], 'message': 'Limit 100 parcels per order.'}); continue
        if not parcels and not block_errors:
            errors.append({'block': bi + 1, 'line': 0, 'text': party['name'], 'message': 'Add at least one parcel line.'})
            continue
        if not parcels:
            continue
        orders.append({'party_id': party['id'], 'party_name': party['name'], 'remarks': block.remarks.strip(), 'parcels': parcels})
        parcel_total += len(parcels)
    if sum(len(p['compositions']) for o in orders for p in o['parcels']) > 2000:
        errors.append({'block': 0, 'line': 0, 'text': '', 'message': 'Batch limit: 2,000 composition rows.'})
    if not orders and not errors:
        errors.append({'block': 0, 'line': 0, 'text': '', 'message': 'Add at least one party with parcels.'})
    return {'orders': orders, 'errors': errors, 'summary': {'orders': len(orders), 'parcels': parcel_total, 'sets': sum(c['sets'] for o in orders for p in o['parcels'] for c in p['compositions'])}}


@router.post('/preview')
async def preview(data: PreviewIn):
    party_ids = list({b.party_id for b in data.blocks})
    parties, cats = await asyncio.gather(
        db.parties.find({'id': {'$in': party_ids}}, {'_id': 0, 'id': 1, 'name': 1}).to_list(None),
        db.catalogues.find({}, {'_id': 0, 'id': 1, 'name': 1, 'volumes': 1}).to_list(None))
    return await run_in_threadpool(parse_blocks, data.blocks, parties, cats)


@router.post('/commit')
async def commit(data: CommitIn, user=Depends(current_user)):
    if sum(len(o.parcels) for o in data.orders) > 500 or sum(len(p.compositions) for o in data.orders for p in o.parcels) > 2000:
        raise HTTPException(400, 'Batch limit: 500 parcels and 2,000 composition rows')
    digest = hashlib.sha256(json.dumps([o.model_dump(mode='json') for o in data.orders], sort_keys=True).encode()).hexdigest()
    batch_key = f'{user["id"]}:{data.request_id}'
    batch = await db.bulk_batches.find_one({'key': batch_key}, {'_id': 0})
    if not batch:
        docs = await number_documents(await canonical_orders(data.orders))
        docs = [{**doc, 'visible': False, 'batch_key': batch_key} for doc in docs]
        candidate = {'key': batch_key, 'digest': digest, 'documents': docs, 'state': 'ready', 'created_at': datetime.now(timezone.utc)}
        try:
            await db.bulk_batches.insert_one(dict(candidate)); batch = candidate
        except DuplicateKeyError:
            batch = await db.bulk_batches.find_one({'key': batch_key}, {'_id': 0})
    if batch['digest'] != digest:
        raise HTTPException(409, 'This batch key belongs to a different preview. Start a new batch.')
    result = {'orders': [{'id': d['id'], 'order_number': d['order_number'], 'party_name': d['party_name']} for d in batch['documents']], 'count': len(batch['documents'])}
    if batch['state'] == 'done':
        return {**result, 'replayed': True}
    now = datetime.now(timezone.utc)
    claimed = await db.bulk_batches.find_one_and_update({'key': batch_key, '$or': [{'state': 'ready'}, {'state': 'writing', 'lease_until': {'$lt': now}}]}, {'$set': {'state': 'writing', 'lease_until': now + timedelta(minutes=2)}}, projection={'_id': 0})
    if not claimed:
        raise HTTPException(409, 'This batch is being saved. Retry this same batch shortly.')
    try:
        await db.orders.bulk_write([UpdateOne({'id': doc['id']}, {'$setOnInsert': doc}, upsert=True) for doc in batch['documents']], ordered=False)
        await db.orders.update_many({'batch_key': batch_key, 'visible': False}, {'$set': {'visible': True}})
        await db.bulk_batches.update_one({'key': batch_key}, {'$set': {'state': 'done'}, '$unset': {'lease_until': ''}})
    except Exception:
        await db.bulk_batches.update_one({'key': batch_key}, {'$set': {'state': 'ready'}})
        raise HTTPException(503, 'The batch could not finish. Retry the same preview; duplicate orders will not be created.')
    return {**result, 'replayed': False}
