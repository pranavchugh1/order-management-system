import asyncio
import copy
import uuid
from datetime import date as Date
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ReturnDocument

from database import db, now_iso, today_iso


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Composition(StrictModel):
    catalogue_id: str = Field(min_length=1, max_length=80)
    volume_id: str = Field(min_length=1, max_length=80)
    catalogue_name: str = Field(min_length=1, max_length=120)
    volume_name: str = Field(min_length=1, max_length=80)
    pieces_per_set: int = Field(strict=True, gt=0, le=10000)
    sets: int = Field(strict=True, gt=0, le=100000)


FIRMS = ('Dhan Guru Nanak Synthetics', 'Alveera Fashion Private Limited')


class Parcel(StrictModel):
    target: int = Field(strict=True, gt=0, le=1000000)
    compositions: list[Composition] = Field(min_length=1, max_length=100)
    status: Literal['Pending', 'Parcel Sent'] = 'Pending'
    challan_number: str | None = Field(default=None, max_length=60)
    firm: Literal['Dhan Guru Nanak Synthetics', 'Alveera Fashion Private Limited'] | None = None
    sent_at: str | None = Field(default=None, max_length=40)


class OrderIn(StrictModel):
    party_id: str = Field(min_length=1, max_length=80)
    party_name: str = Field(min_length=1, max_length=120)
    parcels: list[Parcel] = Field(min_length=1, max_length=100)
    remarks: str = Field(default='', max_length=1000)
    date: Date | None = None
    version: int | None = Field(default=None, ge=0)


class OrderOut(BaseModel):
    model_config = ConfigDict(extra='allow')
    id: str
    order_number: str
    party_id: str
    party_name: str
    date: str
    parcels: list[dict]
    status: str
    total_pieces: int
    version: int


def order_view(doc):
    result = copy.deepcopy({k: v for k, v in doc.items() if k not in ('_id', 'search_key', 'visible', 'batch_key')})
    for parcel in result['parcels']:
        parcel['total'] = sum(c['pieces_per_set'] * c['sets'] for c in parcel['compositions'])
    result['total_pieces'] = sum(p['total'] for p in result['parcels'])
    sent = sum(p['status'] == 'Parcel Sent' for p in result['parcels'])
    result['status'] = 'Completed' if sent == len(result['parcels']) else 'Partially Pending' if sent else 'Pending'
    result['version'] = result.get('version', 0)
    return result


def computed_fields(doc):
    parcels = doc['parcels']
    pending = [p for p in parcels if p['status'] != 'Parcel Sent']
    total = sum(c['pieces_per_set'] * c['sets'] for p in parcels for c in p['compositions'])
    return {'state': 'pending' if pending else 'completed', 'total_pieces': total,
            'parcel_count': len(parcels), 'pending_parcels': len(pending),
            'total_sets': sum(c['sets'] for p in parcels for c in p['compositions']),
            'search_key': f"{doc.get('order_number', '')} {doc['party_name']}".casefold(),
            'party_name_key': doc['party_name'].casefold(), 'order_number_key': doc.get('order_number', '').casefold()}


async def canonical_orders(inputs, existing=None):
    """Two indexed queries for the whole batch; never one query per row/order."""
    party_ids = list({o.party_id for o in inputs})
    cat_ids = list({c.catalogue_id for o in inputs for p in o.parcels for c in p.compositions})
    parties, cats = await asyncio.gather(
        db.parties.find({'id': {'$in': party_ids}}, {'_id': 0, 'id': 1, 'name': 1}).to_list(None),
        db.catalogues.find({'id': {'$in': cat_ids}}, {'_id': 0, 'id': 1, 'name': 1, 'volumes': 1}).to_list(None))
    party_map = {p['id']: p for p in parties}
    volumes = {(c['id'], v['id']): (c, v) for c in cats for v in c['volumes']}
    docs = []
    for oi, order in enumerate(inputs):
        if order.party_id not in party_map:
            raise HTTPException(400, f'Order {oi+1}: party no longer exists')
        doc = order.model_dump(exclude={'version'}, mode='json')
        doc['party_name'] = party_map[order.party_id]['name']
        doc['date'] = doc['date'] or today_iso()
        if doc['date'] > today_iso():
            raise HTTPException(400, f'Order {oi+1}: date cannot be in the future')
        for pi, parcel in enumerate(doc['parcels']):
            if parcel['status'] == 'Parcel Sent' and not existing:
                raise HTTPException(400, 'New orders must have pending parcels')
            old = existing['parcels'][pi] if existing and pi < len(existing['parcels']) else None
            if old and old['status'] == 'Parcel Sent':
                if {k: parcel.get(k) for k in ('target', 'compositions', 'status')} != {k: old.get(k) for k in ('target', 'compositions', 'status')}:
                    raise HTTPException(409, f'Parcel {pi+1} has already been sent and cannot be changed')
                doc['parcels'][pi] = {k: old[k] for k in ('target', 'compositions', 'status', 'challan_number', 'firm', 'sent_at', 'stock_state', 'dispatched_by') if k in old}
                continue
            if parcel['status'] == 'Parcel Sent':
                raise HTTPException(400, 'Use the parcel sent action to dispatch parcels')
            for comp in parcel['compositions']:
                found = volumes.get((comp['catalogue_id'], comp['volume_id']))
                if not found:
                    raise HTTPException(400, f'Order {oi+1}, parcel {pi+1}: catalogue or volume no longer exists')
                catalogue, volume = found
                if comp['pieces_per_set'] != volume['pieces_per_set']:
                    raise HTTPException(409, f"{catalogue['name']} {volume['name']}: pieces per set changed; reselect the volume")
                comp.update(catalogue_name=catalogue['name'], volume_name=volume['name'], pieces_per_set=volume['pieces_per_set'])
            total = sum(c['pieces_per_set'] * c['sets'] for c in parcel['compositions'])
            if total != parcel['target']:
                raise HTTPException(400, f"Order {oi+1}, parcel {pi+1}: must total exactly {parcel['target']} pieces (currently {total})")
        if existing and any(p['status'] == 'Parcel Sent' for p in existing['parcels'][len(doc['parcels']):]):
            raise HTTPException(409, 'Sent parcels cannot be removed')
        if existing and any(p['status'] == 'Parcel Sent' for p in existing['parcels']) and doc['party_id'] != existing['party_id']:
            raise HTTPException(409, 'The party cannot change after dispatch')
        docs.append(doc)
    return docs


async def number_documents(docs):
    counter = await db.counters.find_one_and_update({'name': 'orders'}, {'$inc': {'value': len(docs)}}, upsert=True, return_document=ReturnDocument.AFTER, projection={'_id': 0})
    start = counter['value'] - len(docs) + 1
    result = []
    for i, data in enumerate(docs):
        doc = {**data, 'id': str(uuid.uuid4()), 'order_number': f'ORD-{start+i:03d}', 'created_at': now_iso(), 'version': 0, 'visible': True}
        doc.update(computed_fields(doc))
        result.append(doc)
    return result
