import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal

from auth import ORDER_PAGES, current_user, has_page_access, require_page
from database import db, now_iso
from order_service import FIRMS, OrderIn, OrderOut, canonical_orders, computed_fields, number_documents, order_view
from stock import deduct_dispatched_stock, pending_stock_suggestions

router = APIRouter(prefix='/api', dependencies=[Depends(current_user)])


def order_page_for(status):
    return {'all': 'orders_all', 'pending': 'orders_pending', 'completed': 'orders_completed'}[status]


class OrderList(BaseModel):
    items: list[dict]
    total: int
    page: int
    page_size: int
    pages: int


class SentIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['Parcel Sent'] = 'Parcel Sent'
    version: int | None = None
    challan_number: str = Field(min_length=1, max_length=60)
    firm: str = Field(min_length=1, max_length=120)

    @field_validator('firm')
    @classmethod
    def firm_allowed(cls, value):
        if value not in FIRMS:
            raise ValueError('Firm must be one of the configured firms')
        return value

    @field_validator('challan_number')
    @classmethod
    def clean_challan(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('Challan number is required')
        return value


@router.get('/orders', response_model=OrderList)
async def list_orders(status: Literal['all', 'pending', 'completed'] = 'all', q: str = Query('', max_length=120), page: int = Query(1, ge=1, le=100000), page_size: int = Query(25, ge=1, le=100), user=Depends(current_user)):
    if not has_page_access(user, order_page_for(status)):
        raise HTTPException(403, 'You do not have access to this page')
    match = {'visible': True}
    if status != 'all':
        match['state'] = status
    if q.strip():
        prefix = {'$regex': '^' + re.escape(q.strip().casefold())}
        match['$or'] = [{'party_name_key': prefix}, {'order_number_key': prefix}]
    pipeline = [{'$match': match}, {'$sort': {'created_at': -1, 'id': -1}}, {'$facet': {
        'items': [{'$skip': (page-1)*page_size}, {'$limit': page_size}, {'$project': {'_id': 0, 'id': 1, 'order_number': 1, 'date': 1, 'party_name': 1, 'parcel_count': 1, 'pending_parcels': 1, 'total_pieces': 1, 'total_sets': 1, 'state': 1, 'remarks': 1}}],
        'count': [{'$count': 'total'}]}}]
    result = (await db.orders.aggregate(pipeline, maxTimeMS=15000).to_list(1))[0]
    total = result['count'][0]['total'] if result['count'] else 0
    return {'items': result['items'], 'total': total, 'page': page, 'page_size': page_size, 'pages': max(1, (total+page_size-1)//page_size)}


@router.get('/orders/{order_id}', response_model=OrderOut)
async def get_order(order_id: str, user=Depends(require_page(*ORDER_PAGES))):
    doc = await db.orders.find_one({'id': order_id, 'visible': True}, {'_id': 0})
    if not doc:
        raise HTTPException(404, 'Order not found')
    return order_view(doc)


@router.post('/orders', response_model=OrderOut, status_code=201)
async def add_order(data: OrderIn, user=Depends(require_page(*ORDER_PAGES))):
    doc = (await number_documents(await canonical_orders([data])))[0]
    await db.orders.insert_one(dict(doc))
    return order_view(doc)


@router.put('/orders/{order_id}', response_model=OrderOut)
async def update_order(order_id: str, data: OrderIn, user=Depends(require_page(*ORDER_PAGES))):
    existing = await db.orders.find_one({'id': order_id, 'visible': True}, {'_id': 0})
    if not existing:
        raise HTTPException(404, 'Order not found')
    if data.version is None or data.version != existing['version']:
        raise HTTPException(409, 'This order changed. Reload it before editing.')
    doc = (await canonical_orders([data], existing=existing))[0]
    merged = {**existing, **doc}
    doc.update(computed_fields(merged), updated_at=now_iso())
    result = await db.orders.update_one({'id': order_id, 'version': data.version}, {'$set': doc, '$inc': {'version': 1}})
    if not result.matched_count:
        raise HTTPException(409, 'This order changed. Reload it before editing.')
    return order_view({**existing, **doc, 'version': data.version+1})


@router.patch('/orders/{order_id}/parcels/{parcel_index}', response_model=OrderOut)
async def mark_sent(order_id: str, parcel_index: int, data: SentIn, user=Depends(require_page(*ORDER_PAGES))):
    doc = await db.orders.find_one({'id': order_id, 'visible': True}, {'_id': 0})
    if not doc or parcel_index < 0 or parcel_index >= len(doc['parcels']):
        raise HTTPException(404, 'Parcel not found')
    if doc['parcels'][parcel_index]['status'] == 'Parcel Sent':
        if doc['parcels'][parcel_index].get('challan_number') != data.challan_number or doc['parcels'][parcel_index].get('firm') != data.firm:
            raise HTTPException(409, 'This parcel was dispatched with different challan details.')
        await deduct_dispatched_stock(doc, parcel_index, user)
        return order_view(doc)
    if data.version is None or data.version != doc['version']:
        raise HTTPException(409, 'This order changed. Reload it before dispatching.')
    sent_at = now_iso()
    actor = {'id': user['id'], 'name': user['name']}
    doc['parcels'][parcel_index].update(status='Parcel Sent', challan_number=data.challan_number, firm=data.firm, sent_at=sent_at, stock_state='pending', dispatched_by=actor)
    fields = computed_fields(doc)
    fields.update({f'parcels.{parcel_index}.status': 'Parcel Sent', f'parcels.{parcel_index}.challan_number': data.challan_number, f'parcels.{parcel_index}.firm': data.firm, f'parcels.{parcel_index}.sent_at': sent_at, f'parcels.{parcel_index}.stock_state': 'pending', f'parcels.{parcel_index}.dispatched_by': actor, 'updated_at': sent_at})
    result = await db.orders.update_one({'id': order_id, 'version': doc['version']}, {'$set': fields, '$inc': {'version': 1}})
    if not result.matched_count:
        raise HTTPException(409, 'This order changed. Reload it before dispatching.')
    await deduct_dispatched_stock(doc, parcel_index, user)
    doc['version'] += 1
    return order_view(doc)


@router.get('/firms')
async def firms(user=Depends(require_page(*ORDER_PAGES, 'challans'))):
    return {'firms': list(FIRMS)}


class ChallanContent(BaseModel):
    catalogue_name: str
    volume_name: str


class ChallanRow(BaseModel):
    order_id: str
    order_number: str
    party_name: str
    order_date: str
    parcel_index: int
    challan_number: str
    firm: str | None = None
    sent_at: str | None = None
    compositions: list[ChallanContent]


class ChallanList(BaseModel):
    rows: list[ChallanRow]
    firms: list[str]
    total: int
    page: int
    page_size: int
    pages: int


@router.get('/challans', response_model=ChallanList)
async def challans(firm: str | None = None, q: str = Query('', max_length=120), page: int = Query(1, ge=1, le=100000), page_size: int = Query(25, ge=1, le=100), user=Depends(require_page('challans'))):
    match = {'visible': True, 'parcels.status': 'Parcel Sent'}
    pipeline = [{'$match': match}, {'$unwind': {'path': '$parcels', 'includeArrayIndex': 'parcel_index'}}, {'$match': {'parcels.status': 'Parcel Sent', 'parcels.challan_number': {'$type': 'string'}}}]
    if firm:
        if firm not in FIRMS:
            raise HTTPException(400, 'Unknown firm')
        pipeline.append({'$match': {'parcels.firm': firm}})
    if q.strip():
        prefix = q.strip().casefold()
        pipeline.append({'$match': {'$or': [{'parcels.challan_number': {'$regex': '^' + re.escape(prefix), '$options': 'i'}}, {'party_name_key': {'$regex': '^' + re.escape(prefix)}}, {'order_number_key': {'$regex': '^' + re.escape(prefix)}}]}})
    pipeline += [{'$facet': {
        'rows': [{'$sort': {'parcels.sent_at': -1, 'created_at': -1, 'id': -1, 'parcel_index': 1}}, {'$skip': (page - 1) * page_size}, {'$limit': page_size},
                 {'$project': {'_id': 0, 'order_id': '$id', 'order_number': 1, 'party_name': 1, 'order_date': '$date', 'parcel_index': 1,
                               'challan_number': '$parcels.challan_number', 'firm': {'$ifNull': ['$parcels.firm', None]}, 'sent_at': {'$ifNull': ['$parcels.sent_at', None]},
                               'compositions': {'$map': {'input': '$parcels.compositions', 'as': 'c', 'in': {'catalogue_name': '$$c.catalogue_name', 'volume_name': '$$c.volume_name'}}}}}],
        'count': [{'$count': 'total'}]}}]
    result = (await db.orders.aggregate(pipeline, maxTimeMS=15000).to_list(1))[0]
    total = result['count'][0]['total'] if result['count'] else 0
    return {'rows': result['rows'], 'firms': list(FIRMS), 'total': total, 'page': page, 'page_size': page_size, 'pages': max(1, (total + page_size - 1) // page_size)}


@router.get('/pending-requirements')
async def pending_requirements(q: str = Query('', max_length=120), catalogue_id: str = Query('', max_length=80), page: int = Query(1, ge=1, le=100000), page_size: int = Query(25, ge=1, le=100), user=Depends(require_page('pending_requirements'))):
    from read_models import requirements_list
    return await requirements_list(q, catalogue_id, page, page_size)
