import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
import asyncio
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator

from auth import MASTER_READ_PAGES, ORDER_PAGES, current_user, require_page
from database import db, normalized, now_iso

router = APIRouter(prefix='/api', dependencies=[Depends(current_user)])


class NameIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=120)

    @field_validator('name')
    @classmethod
    def valid_name(cls, value):
        value = normalized(value)
        if not value:
            raise ValueError('Name cannot be empty')
        return value


class PartyIn(NameIn):
    agent: str = Field(default='', max_length=120)
    transport: str = Field(default='', max_length=120)

    @field_validator('agent', 'transport')
    @classmethod
    def valid_optional_name(cls, value):
        return normalized(value) if value else ''


class VolumeIn(NameIn):
    name: str = Field(min_length=1, max_length=80)
    pieces_per_set: int = Field(strict=True, gt=0, le=10000)


class MasterOut(BaseModel):
    model_config = ConfigDict(extra='allow')
    id: str
    name: str


async def add_master(collection, data, extra=None):
    doc = {'id': str(uuid.uuid4()), 'name': data.name, 'name_key': data.name.casefold(), 'created_at': now_iso(), **(extra or {})}
    await db[collection].insert_one(dict(doc))
    return MasterOut(**doc)


async def edit_master(collection, ident, data, extra=None):
    fields = {'name': data.name, 'name_key': data.name.casefold(), **(extra or {})}
    result = await db[collection].update_one({'id': ident}, {'$set': fields})
    if not result.matched_count:
        raise HTTPException(404, 'Record not found')
    return await db[collection].find_one({'id': ident}, {'_id': 0, 'name_key': 0})


async def stock_reference(query):
    results = await asyncio.gather(*(db[name].find_one(query, {'_id': 1}) for name in ('stock_batches', 'stock_balances', 'stock_movements')))
    return any(results)


async def delete_master(collection, ident, reference):
    if await db.orders.find_one({reference: ident}, {'_id': 1}):
        raise HTTPException(409, 'Cannot delete a record used by an order')
    if collection == 'catalogues' and await stock_reference({'catalogue_id': ident}):
        raise HTTPException(409, 'Cannot delete a catalogue referenced by stock or production history')
    result = await db[collection].delete_one({'id': ident})
    if not result.deleted_count:
        raise HTTPException(404, 'Record not found')
    return {'ok': True}


async def list_master_page(collection, q, page, page_size):
    match = {'name_key': {'$regex': '^' + re.escape(q.strip().casefold())}} if q.strip() else {}
    projection = {'_id': 0, 'id': 1, 'name': 1, 'agent': 1, 'transport': 1} if collection == 'parties' else {'_id': 0, 'id': 1, 'name': 1, 'volumes.id': 1, 'volumes.name': 1, 'volumes.pieces_per_set': 1}
    items, total = await asyncio.gather(db[collection].find(match, projection).sort([('name_key', 1), ('id', 1)]).skip((page-1)*page_size).limit(page_size).to_list(page_size), db[collection].count_documents(match, maxTimeMS=10000))
    return {'items': items, 'total': total, 'page': page, 'page_size': page_size, 'pages': max(1, (total+page_size-1)//page_size)}


@router.get('/parties')
async def parties(q: str = Query('', max_length=120), page: int = Query(1, ge=1, le=100000), page_size: int = Query(100, ge=1, le=200), user=Depends(require_page(*MASTER_READ_PAGES))):
    return await list_master_page('parties', q, page, page_size)


@router.post('/parties', response_model=MasterOut)
async def add_party(data: PartyIn, user=Depends(require_page(*ORDER_PAGES, 'parties'))):
    return await add_master('parties', data, {'agent': data.agent, 'transport': data.transport})


@router.put('/parties/{party_id}', response_model=MasterOut)
async def edit_party(party_id: str, data: PartyIn, user=Depends(require_page('parties'))):
    return await edit_master('parties', party_id, data, {'agent': data.agent, 'transport': data.transport})


@router.delete('/parties/{party_id}')
async def delete_party(party_id: str, user=Depends(require_page('parties'))): return await delete_master('parties', party_id, 'party_id')


@router.get('/catalogues')
async def catalogues(q: str = Query('', max_length=120), page: int = Query(1, ge=1, le=100000), page_size: int = Query(100, ge=1, le=200), user=Depends(require_page(*MASTER_READ_PAGES))):
    return await list_master_page('catalogues', q, page, page_size)


@router.post('/catalogues', response_model=MasterOut)
async def add_catalogue(data: NameIn, user=Depends(require_page('catalogues'))): return await add_master('catalogues', data, {'volumes': []})


@router.put('/catalogues/{catalogue_id}', response_model=MasterOut)
async def edit_catalogue(catalogue_id: str, data: NameIn, user=Depends(require_page('catalogues'))): return await edit_master('catalogues', catalogue_id, data)


@router.delete('/catalogues/{catalogue_id}')
async def delete_catalogue(catalogue_id: str, user=Depends(require_page('catalogues'))): return await delete_master('catalogues', catalogue_id, 'parcels.compositions.catalogue_id')


@router.post('/catalogues/{catalogue_id}/volumes', response_model=MasterOut)
async def add_volume(catalogue_id: str, data: VolumeIn, user=Depends(require_page('catalogues'))):
    volume = {'id': str(uuid.uuid4()), 'name': data.name, 'pieces_per_set': data.pieces_per_set, 'name_key': data.name.casefold()}
    catalogue = await db.catalogues.find_one({'id': catalogue_id}, {'_id': 0, 'volumes': 1})
    if not catalogue: raise HTTPException(404, 'Catalogue not found')
    if len(catalogue['volumes']) >= 1000: raise HTTPException(400, 'Maximum 1,000 volumes per catalogue. Create a new catalogue.')
    if any(v['name'].casefold() == data.name.casefold() for v in catalogue['volumes']): raise HTTPException(409, 'A volume with this name already exists')
    result = await db.catalogues.update_one({'id': catalogue_id, 'volumes.999': {'$exists': False}, 'volumes.name_key': {'$ne': data.name.casefold()}}, {'$push': {'volumes': volume}})
    if not result.matched_count: raise HTTPException(409, 'A volume with this name already exists')
    return volume


@router.put('/catalogues/{catalogue_id}/volumes/{volume_id}', response_model=MasterOut)
async def edit_volume(catalogue_id: str, volume_id: str, data: VolumeIn, user=Depends(require_page('catalogues'))):
    cat = await db.catalogues.find_one({'id': catalogue_id}, {'_id': 0, 'volumes': 1})
    old = next((v for v in (cat or {}).get('volumes', []) if v['id'] == volume_id), None)
    if not old: raise HTTPException(404, 'Volume not found')
    if any(v['id'] != volume_id and v['name'].casefold() == data.name.casefold() for v in cat['volumes']): raise HTTPException(409, 'A volume with this name already exists')
    if old['pieces_per_set'] != data.pieces_per_set:
        if await db.orders.find_one({'parcels.compositions.volume_id': volume_id}, {'_id': 1}) or await stock_reference({'volume_id': volume_id}):
            raise HTTPException(409, 'Pieces per set cannot change for a volume used by orders, stock or production. Add a new volume instead.')
    result = await db.catalogues.update_one({'id': catalogue_id, 'volumes.id': volume_id, 'volumes': {'$not': {'$elemMatch': {'id': {'$ne': volume_id}, 'name_key': data.name.casefold()}}}}, {'$set': {'volumes.$.name': data.name, 'volumes.$.name_key': data.name.casefold(), 'volumes.$.pieces_per_set': data.pieces_per_set}})
    if not result.matched_count: raise HTTPException(409, 'Volume changed. Please reload.')
    return {'id': volume_id, **data.model_dump()}


@router.delete('/catalogues/{catalogue_id}/volumes/{volume_id}')
async def delete_volume(catalogue_id: str, volume_id: str, user=Depends(require_page('catalogues'))):
    if await db.orders.find_one({'parcels.compositions.volume_id': volume_id}, {'_id': 1}) or await stock_reference({'volume_id': volume_id}):
        raise HTTPException(409, 'Cannot delete a volume used by orders, stock or production history')
    result = await db.catalogues.update_one({'id': catalogue_id, 'volumes.id': volume_id}, {'$pull': {'volumes': {'id': volume_id}}})
    if not result.modified_count: raise HTTPException(404, 'Volume not found')
    return {'ok': True}
