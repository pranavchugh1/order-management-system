import asyncio
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pymongo import UpdateOne
from pymongo.errors import DuplicateKeyError

from auth import admin_user, current_user, require_page
from database import db, normalized, now_iso
from stock_ledger import dispatch_stock, recover_stock, submit_operation

stock_router = APIRouter(prefix='/api/stock', dependencies=[Depends(require_page('stock'))])
production_router = APIRouter(prefix='/api/production', dependencies=[Depends(require_page('production'))])

PRODUCTION_STAGES = ('Unissued', 'Stitching', 'Folding', 'Packing')
STANDARD_STAGES = PRODUCTION_STAGES
READY_STAGE = 'Ready stock'
PHOTO_RE = re.compile(r'^data:image/(png|jpe?g|webp);base64,[A-Za-z0-9+/=\s]+$')


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


def validate_photo_data_url(value):
    if not value:
        return None
    if len(value) > 1_200_000 or not PHOTO_RE.match(value):
        raise ValueError('Upload a PNG, JPG, or WebP image under about 900 KB')
    return value


class StockBatchIn(StrictModel):
    catalogue_id: str = Field(min_length=1, max_length=80)
    volume_id: str = Field(min_length=1, max_length=80)
    design_no: str = Field(min_length=1, max_length=80)
    total_pieces: int = Field(strict=True, gt=0, le=10_000_000)
    photo_data_url: str | None = Field(default=None, max_length=1_200_000)
    photo_id: uuid.UUID | None = None
    note: str = Field(default='', max_length=300)

    @field_validator('design_no', 'note')
    @classmethod
    def clean_text(cls, value, info):
        result = normalized(value) if value else ''
        if info.field_name in ('design_no', 'from_stage', 'to_stage', 'stage', 'text') and not result:
            raise ValueError('This field cannot be blank')
        return result

    @field_validator('photo_data_url')
    @classmethod
    def valid_photo(cls, value):
        return validate_photo_data_url(value)

class IssueIn(StrictModel):
    from_stage: str = Field(min_length=1, max_length=40)
    to_stage: str = Field(min_length=1, max_length=40)
    pieces: int = Field(strict=True, gt=0, le=10_000_000)
    note: str = Field(default='', max_length=300)
    version: int = Field(ge=0)

    @field_validator('from_stage', 'to_stage', 'note')
    @classmethod
    def clean_text(cls, value, info):
        result = normalized(value) if value else ''
        if info.field_name in ('design_no', 'from_stage', 'to_stage', 'stage', 'text') and not result:
            raise ValueError('This field cannot be blank')
        return result


class StockAddIn(StrictModel):
    request_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    catalogue_id: str = Field(min_length=1, max_length=80)
    volume_id: str = Field(min_length=1, max_length=80)
    sets: int = Field(default=0, strict=True, ge=0, le=1_000_000)
    pieces: int = Field(default=0, strict=True, ge=0, le=10_000_000)
    note: str = Field(default='', max_length=300)

    @field_validator('note')
    @classmethod
    def clean_note(cls, value):
        return normalized(value) if value else ''

    @model_validator(mode='after')
    def has_quantity(self):
        if self.sets <= 0 and self.pieces <= 0:
            raise ValueError('Enter sets or pieces to add')
        return self


class StockBalanceSetIn(StrictModel):
    request_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    version: int | None = Field(default=None, strict=True, ge=0)
    sets: int = Field(default=0, strict=True, ge=-1_000_000, le=1_000_000)
    pieces: int = Field(default=0, strict=True, ge=-10_000_000, le=10_000_000)
    note: str = Field(default='', max_length=300)

    @field_validator('note')
    @classmethod
    def clean_note(cls, value):
        return normalized(value) if value else ''


class StageBalanceIn(StrictModel):
    stage: str = Field(min_length=1, max_length=40)
    pieces: int = Field(strict=True, ge=0, le=10_000_000)

    @field_validator('stage')
    @classmethod
    def clean_stage(cls, value):
        return normalized(value)


class ProductionPatchIn(StrictModel):
    design_no: str = Field(min_length=1, max_length=80)
    total_pieces: int = Field(strict=True, gt=0, le=10_000_000)
    stage_balances: list[StageBalanceIn] = Field(min_length=1, max_length=30)
    note: str = Field(default='', max_length=300)
    photo_data_url: str | None = Field(default=None, max_length=1_200_000)
    photo_id: uuid.UUID | None = None
    keep_photo: bool = True
    version: int = Field(ge=0)

    @field_validator('design_no', 'note')
    @classmethod
    def clean_text(cls, value, info):
        result = normalized(value) if value else ''
        if info.field_name in ('design_no', 'from_stage', 'to_stage', 'stage', 'text') and not result:
            raise ValueError('This field cannot be blank')
        return result

    @field_validator('photo_data_url')
    @classmethod
    def valid_photo(cls, value):
        return validate_photo_data_url(value)


class UrgentRequirementIn(StrictModel):
    text: str = Field(min_length=1, max_length=300)
    party_name: str = Field(default='', max_length=120)
    needed_by: str = Field(default='', max_length=40)
    priority: str = Field(default='Normal', max_length=20)

    @field_validator('text', 'party_name', 'needed_by', 'priority')
    @classmethod
    def clean_text(cls, value, info):
        result = normalized(value) if value else ''
        if info.field_name in ('design_no', 'from_stage', 'to_stage', 'stage', 'text') and not result:
            raise ValueError('This field cannot be blank')
        return result


def stage_label(value):
    cleaned = normalized(value)
    if not cleaned:
        raise HTTPException(400, 'Stage is required')
    if cleaned.startswith('$') or '.' in cleaned:
        raise HTTPException(400, 'Stage cannot contain "." or start with "$"')
    standard = {stage.casefold(): stage for stage in STANDARD_STAGES}
    return standard.get(cleaned.casefold(), cleaned)


def stage_list(stage_map):
    ordered = []
    for stage in STANDARD_STAGES:
        ordered.append({'stage': stage, 'pieces': int(stage_map.get(stage, 0))})
    for stage, pieces in sorted(stage_map.items(), key=lambda item: item[0].casefold()):
        if stage not in STANDARD_STAGES:
            ordered.append({'stage': stage, 'pieces': int(pieces)})
    return ordered


def stage_map_from(batch):
    return {row['stage']: int(row.get('pieces', 0)) for row in batch.get('stage_balances', [])}


async def catalogue_volume(catalogue_id, volume_id):
    catalogue = await db.catalogues.find_one({'id': catalogue_id}, {'_id': 0, 'id': 1, 'name': 1, 'volumes': 1})
    if not catalogue:
        raise HTTPException(400, 'Catalogue no longer exists')
    volume = next((v for v in catalogue.get('volumes', []) if v['id'] == volume_id), None)
    if not volume:
        raise HTTPException(400, 'Volume no longer exists')
    return catalogue, volume


async def adjust_balance(catalogue_id, volume_id, catalogue_name, volume_name, pieces_per_set, delta):
    if not delta:
        return
    await db.stock_balances.update_one(
        {'catalogue_id': catalogue_id, 'volume_id': volume_id},
        {'$inc': {'available_pieces': int(delta)},
         '$set': {'catalogue_name': catalogue_name, 'volume_name': volume_name, 'pieces_per_set': int(pieces_per_set), 'updated_at': now_iso()},
         '$setOnInsert': {'id': str(uuid.uuid4()), 'created_at': now_iso()}},
        upsert=True,
    )


async def record_movement(batch, from_stage, to_stage, pieces, note, ready_delta, user, source='issue'):
    movement = {
        'id': str(uuid.uuid4()), 'batch_id': batch['id'], 'source': source,
        'catalogue_id': batch['catalogue_id'], 'volume_id': batch['volume_id'],
        'catalogue_name': batch['catalogue_name'], 'volume_name': batch['volume_name'],
        'design_no': batch['design_no'], 'from_stage': from_stage, 'to_stage': to_stage,
        'pieces': int(pieces), 'ready_delta': int(ready_delta), 'note': note or '',
        'created_at': now_iso(), 'created_by': {'id': user['id'], 'name': user['name']},
    }
    await db.stock_movements.insert_one(dict(movement))
    if ready_delta:
        await adjust_balance(batch['catalogue_id'], batch['volume_id'], batch['catalogue_name'], batch['volume_name'], batch['pieces_per_set'], ready_delta)


async def deduct_dispatched_stock(order, parcel_index, user=None):
    await dispatch_stock(order, parcel_index, user)


async def stock_balance_map():
    await recover_stock()
    balances = await db.stock_balances.find({}, {'_id': 0, 'catalogue_id': 1, 'volume_id': 1, 'available_pieces': 1}).to_list(None)
    return {(row['catalogue_id'], row['volume_id']): int(row.get('available_pieces', 0)) for row in balances}


async def pending_requirement_map():
    pipeline = [
        {'$match': {'visible': True, 'state': 'pending'}},
        {'$unwind': '$parcels'},
        {'$match': {'parcels.status': 'Pending'}},
        {'$unwind': '$parcels.compositions'},
        {'$group': {
            '_id': {'catalogue_id': '$parcels.compositions.catalogue_id', 'volume_id': '$parcels.compositions.volume_id'},
            'sets': {'$sum': '$parcels.compositions.sets'},
            'pieces': {'$sum': {'$multiply': ['$parcels.compositions.pieces_per_set', '$parcels.compositions.sets']}},
        }},
    ]
    rows = await db.orders.aggregate(pipeline, maxTimeMS=15000).to_list(None)
    return {(row['_id']['catalogue_id'], row['_id']['volume_id']): {'sets': int(row['sets']), 'pieces': int(row['pieces'])} for row in rows}


def parcel_requirements(parcel):
    requirements = {}
    labels = {}
    for comp in parcel['compositions']:
        key = (comp['catalogue_id'], comp['volume_id'])
        pieces = int(comp['pieces_per_set']) * int(comp['sets'])
        requirements[key] = requirements.get(key, 0) + pieces
        labels[key] = {
            'catalogue_id': comp['catalogue_id'], 'volume_id': comp['volume_id'],
            'catalogue_name': comp['catalogue_name'], 'volume_name': comp['volume_name'],
            'pieces_per_set': int(comp['pieces_per_set']),
        }
    return requirements, labels


def can_allocate(requirements, available):
    return all(available.get(key, 0) >= pieces for key, pieces in requirements.items())


def allocate(requirements, available):
    for key, pieces in requirements.items():
        available[key] = available.get(key, 0) - pieces


def parcel_payload(order, parcel_index, parcel, requirements, labels, available):
    items = []
    for key, pieces in requirements.items():
        label = labels[key]
        stock = max(0, available.get(key, 0))
        items.append({**label, 'required_pieces': pieces, 'available_pieces': stock, 'missing_pieces': max(0, pieces - stock)})
    return {
        'order_id': order['id'], 'order_number': order['order_number'], 'party_name': order['party_name'],
        'date': order['date'], 'parcel_index': parcel_index, 'parcel_pieces': int(parcel['target']), 'items': items,
    }


async def pending_stock_suggestions(limit=80, scan_orders=1000):
    available = {key: max(0, pieces) for key, pieces in (await stock_balance_map()).items()}
    ready_orders, ready_parcels, partials = [], [], []
    projection = {'_id': 0, 'id': 1, 'order_number': 1, 'party_id': 1, 'party_name': 1, 'date': 1, 'created_at': 1, 'parcels': 1}
    cursor = db.orders.find({'visible': True, 'state': 'pending'}, projection).sort([('created_at', 1), ('id', 1)]).limit(scan_orders).batch_size(100)
    async for order in cursor:
        await asyncio.sleep(0)
        pending = [(i, p) for i, p in enumerate(order['parcels']) if p['status'] == 'Pending']
        if not pending:
            continue
        order_requirements, parcel_rows = {}, []
        for parcel_index, parcel in pending:
            requirements, labels = parcel_requirements(parcel)
            parcel_rows.append((parcel_index, parcel, requirements, labels))
            for key, pieces in requirements.items():
                order_requirements[key] = order_requirements.get(key, 0) + pieces
        if can_allocate(order_requirements, available):
            allocate(order_requirements, available)
            ready_orders.append({
                'order_id': order['id'], 'order_number': order['order_number'], 'party_name': order['party_name'], 'date': order['date'],
                'pending_parcels': len(pending), 'pieces': sum(int(parcel['target']) for _, parcel in pending),
            })
        else:
            parcel_suggestions = []
            for parcel_index, parcel, requirements, labels in parcel_rows:
                if can_allocate(requirements, available):
                    parcel_suggestions.append(parcel_payload(order, parcel_index, parcel, requirements, labels, available))
                    allocate(requirements, available)
            if parcel_suggestions:
                ready_parcels.append({
                    'order_id': order['id'], 'order_number': order['order_number'], 'party_name': order['party_name'],
                    'date': order['date'], 'parcels': parcel_suggestions,
                })
            elif len(partials) < 20:
                best = max(
                    (parcel_payload(order, parcel_index, parcel, requirements, labels, available) for parcel_index, parcel, requirements, labels in parcel_rows),
                    key=lambda row: sum(min(item['required_pieces'], item['available_pieces']) for item in row['items']),
                )
                if any(item['available_pieces'] > 0 for item in best['items']):
                    partials.append(best)
        if len(ready_orders) + len(ready_parcels) >= limit:
            break
    return {'ready_orders': ready_orders[:limit], 'ready_parcels': ready_parcels[:limit], 'partial_parcels': partials[:20], 'scan_limit': scan_orders, 'suggestion_limit': limit}


@stock_router.get('')
async def stock_home(q: str = Query('', max_length=120), page: int = Query(1, ge=1, le=100000), page_size: int = Query(25, ge=1, le=100), movement_page: int = Query(1, ge=1, le=100000)):
    from read_models import stock_list
    return await stock_list(q, page, page_size, movement_page)


@stock_router.post('/add', status_code=201)
async def add_stock(data: StockAddIn, user=Depends(current_user)):
    catalogue, volume = await catalogue_volume(data.catalogue_id, data.volume_id)
    total_pieces = data.sets * int(volume['pieces_per_set']) + data.pieces
    if total_pieces <= 0 or total_pieces > 10_000_000:
        raise HTTPException(400, 'Stock addition must be between 1 and 10,000,000 pieces')
    stamp = now_iso()
    movement = {
        'id': str(uuid.uuid4()), 'source': 'manual_add',
        'catalogue_id': catalogue['id'], 'volume_id': volume['id'],
        'catalogue_name': catalogue['name'], 'volume_name': volume['name'],
        'pieces_per_set': int(volume['pieces_per_set']), 'sets': data.sets,
        'pieces': total_pieces, 'loose_pieces': data.pieces, 'ready_delta': total_pieces,
        'from_stage': 'Manual entry', 'to_stage': READY_STAGE,
        'note': data.note, 'created_at': stamp, 'created_by': {'id': user['id'], 'name': user['name']},
    }
    movement.update(source_key=f'manual:{user["id"]}:{data.request_id}', requested_delta=total_pieces)
    result = await submit_operation(movement, data.model_dump(mode='json'))
    return {**result, 'available_sets': result['available_pieces'] // int(volume['pieces_per_set'])}


@stock_router.patch('/balances/{catalogue_id}/{volume_id}')
async def set_stock_balance(catalogue_id: str, volume_id: str, data: StockBalanceSetIn, user=Depends(admin_user)):
    catalogue, volume = await catalogue_volume(catalogue_id, volume_id)
    target_pieces = data.sets * int(volume['pieces_per_set']) + data.pieces
    if target_pieces < -10_000_000 or target_pieces > 10_000_000:
        raise HTTPException(400, 'Stock balance is outside the allowed range')
    stamp = now_iso()
    movement = {
        'id': str(uuid.uuid4()), 'source': 'admin_stock_edit',
        'catalogue_id': catalogue_id, 'volume_id': volume_id,
        'catalogue_name': catalogue['name'], 'volume_name': volume['name'],
        'pieces_per_set': int(volume['pieces_per_set']), 'sets': data.sets,
        'pieces': abs(target_pieces), 'ready_delta': 0, 'from_stage': 'Admin edit', 'to_stage': READY_STAGE,
        'note': data.note, 'operation': 'set', 'target_pieces': target_pieces,
        'source_key': f'balance:{user["id"]}:{data.request_id}', 'expected_version': data.version,
        'created_at': stamp, 'created_by': {'id': user['id'], 'name': user['name']},
    }
    result = await submit_operation(movement, {**data.model_dump(mode='json'), 'catalogue_id': catalogue_id, 'volume_id': volume_id})
    return {**result, 'available_sets': result['available_pieces'] // int(volume['pieces_per_set'])}


@production_router.get('')
async def production_home(q: str = Query('', max_length=120), page: int = Query(1, ge=1, le=100000), page_size: int = Query(20, ge=1, le=100), urgent_page: int = Query(1, ge=1, le=100000)):
    from read_models import production_list
    return await production_list(q, page, page_size, urgent_page)


@production_router.get('/batches/{batch_id}')
async def production_batch(batch_id: str):
    batch = await db.stock_batches.find_one({'id': batch_id}, {'_id': 0})
    if not batch:
        raise HTTPException(404, 'Stock entry not found')
    batch['stage_balances'] = stage_list(stage_map_from(batch))
    history = batch.pop('history', [])
    if batch.get('photo_id'):
        batch['photo_url'] = f'/api/photos/{batch["photo_id"]}'
    movements = await db.stock_movements.find({'batch_id': batch_id}, {'_id': 0}).sort('created_at', -1).limit(50).to_list(50)
    return {'batch': batch, 'movements': sorted(history + movements, key=lambda m: m['created_at'], reverse=True)[:50]}


@production_router.post('/batches', status_code=201)
async def add_stock_batch(data: StockBatchIn, user=Depends(current_user)):
    from photos import validate_photo_owner
    await validate_photo_owner(data.photo_id, user)
    catalogue, volume = await catalogue_volume(data.catalogue_id, data.volume_id)
    doc = {
        'id': str(uuid.uuid4()), 'catalogue_id': catalogue['id'], 'catalogue_name': catalogue['name'],
        'volume_id': volume['id'], 'volume_name': volume['name'], 'pieces_per_set': int(volume['pieces_per_set']),
        'design_no': data.design_no, 'design_no_key': data.design_no.casefold(), 'photo_data_url': data.photo_data_url,
        'photo_id': str(data.photo_id) if data.photo_id else None, 'has_photo': bool(data.photo_id or data.photo_data_url), 'history': [],
        'total_pieces': data.total_pieces, 'stage_balances': stage_list({'Unissued': data.total_pieces}),
        'note': data.note, 'created_at': now_iso(), 'updated_at': now_iso(), 'version': 0,
        'created_by': {'id': user['id'], 'name': user['name']},
    }
    try:
        await db.stock_batches.insert_one(dict(doc))
    except DuplicateKeyError:
        raise HTTPException(409, 'This design number already exists for the selected catalogue and volume')
    return {k: v for k, v in doc.items() if k != '_id'}


@production_router.put('/batches/{batch_id}')
async def edit_production_batch(batch_id: str, data: ProductionPatchIn, user=Depends(admin_user)):
    existing = await db.stock_batches.find_one({'id': batch_id}, {'_id': 0})
    if not existing:
        raise HTTPException(404, 'Production entry not found')
    if data.version != existing.get('version', 0):
        raise HTTPException(409, 'This production entry changed. Reload it before editing.')
    merged_stages = {}
    for row in data.stage_balances:
        stage = stage_label(row.stage)
        if stage.casefold() == READY_STAGE.casefold():
            raise HTTPException(400, 'Production entries cannot use Ready stock. Use Stock for sellable stock.')
        merged_stages[stage] = merged_stages.get(stage, 0) + row.pieces
    if sum(merged_stages.values()) != data.total_pieces:
        raise HTTPException(400, 'Stage pieces must total exactly the production total')
    duplicate = await db.stock_batches.find_one({'id': {'$ne': batch_id}, 'catalogue_id': existing['catalogue_id'], 'volume_id': existing['volume_id'], 'design_no_key': data.design_no.casefold()}, {'_id': 1})
    if duplicate:
        raise HTTPException(409, 'This design number already exists for the selected catalogue and volume')
    fields = {
        'design_no': data.design_no, 'design_no_key': data.design_no.casefold(),
        'total_pieces': data.total_pieces, 'stage_balances': stage_list(merged_stages),
        'note': data.note, 'updated_at': now_iso(),
    }
    if data.photo_id:
        from photos import validate_photo_owner
        await validate_photo_owner(data.photo_id, user)
        fields.update(photo_id=str(data.photo_id), photo_data_url=None, has_photo=True)
    elif data.photo_data_url is not None:
        fields.update(photo_data_url=data.photo_data_url, photo_id=None, has_photo=True)
    elif not data.keep_photo:
        fields.update(photo_data_url=None, photo_id=None, has_photo=False)
    if len(existing.get('history', [])) >= 2000:
        raise HTTPException(409, 'Production history limit reached. Create a new production entry.')
    movement = {
        'id': str(uuid.uuid4()), 'batch_id': batch_id, 'source': 'admin_production_edit',
        'catalogue_id': existing['catalogue_id'], 'volume_id': existing['volume_id'],
        'catalogue_name': existing['catalogue_name'], 'volume_name': existing['volume_name'],
        'design_no': data.design_no, 'from_stage': 'Admin edit', 'to_stage': 'Production entry',
        'pieces': data.total_pieces, 'ready_delta': 0, 'note': data.note,
        'created_at': now_iso(), 'created_by': {'id': user['id'], 'name': user['name']},
    }
    try:
        result = await db.stock_batches.update_one({'id': batch_id, 'version': data.version},
            {'$set': fields, '$inc': {'version': 1}, '$push': {'history': movement}})
    except DuplicateKeyError:
        raise HTTPException(409, 'This design number already exists for the selected catalogue and volume')
    if not result.matched_count:
        raise HTTPException(409, 'This production entry changed. Reload it before editing.')
    return {k: v for k, v in {**existing, **fields, 'version': data.version + 1}.items() if k != 'history'}


@production_router.post('/batches/{batch_id}/issue')
async def issue_stock(batch_id: str, data: IssueIn, user=Depends(current_user)):
    batch = await db.stock_batches.find_one({'id': batch_id}, {'_id': 0})
    if not batch:
        raise HTTPException(404, 'Stock entry not found')
    if data.version != batch.get('version', 0):
        raise HTTPException(409, 'This stock entry changed. Reload it before issuing pieces.')
    from_stage, to_stage = stage_label(data.from_stage), stage_label(data.to_stage)
    if from_stage == to_stage:
        raise HTTPException(400, 'Choose different source and destination stages')
    stages = stage_map_from(batch)
    if stages.get(from_stage, 0) < data.pieces:
        raise HTTPException(409, f'Only {stages.get(from_stage, 0)} pieces are available in {from_stage}')
    stages[from_stage] = stages.get(from_stage, 0) - data.pieces
    stages[to_stage] = stages.get(to_stage, 0) + data.pieces
    if to_stage.casefold() == READY_STAGE.casefold() or from_stage.casefold() == READY_STAGE.casefold():
        raise HTTPException(400, 'Production flow uses Stitching, Folding, Packing, or a custom issue space. Add sellable stock from the Stock page.')
    if len(batch.get('history', [])) >= 2000 or len(stages) > 30:
        raise HTTPException(409, 'Production history or stage limit reached. Create a new entry.')
    updated_at = now_iso()
    movement = {'id': str(uuid.uuid4()), 'from_stage': from_stage, 'to_stage': to_stage, 'pieces': data.pieces,
                'note': data.note, 'created_at': updated_at, 'created_by': {'id': user['id'], 'name': user['name']}}
    result = await db.stock_batches.update_one(
        {'id': batch_id, 'version': data.version},
        {'$set': {'stage_balances': stage_list(stages), 'updated_at': updated_at}, '$inc': {'version': 1}, '$push': {'history': movement}},
    )
    if not result.matched_count:
        raise HTTPException(409, 'This stock entry changed. Reload it before issuing pieces.')
    updated = {**batch, 'stage_balances': stage_list(stages), 'updated_at': updated_at, 'version': data.version + 1}
    return {k: v for k, v in updated.items() if k != 'history'}


@production_router.post('/urgent', status_code=201)
async def add_urgent_requirement(data: UrgentRequirementIn, user=Depends(current_user)):
    doc = {
        'id': str(uuid.uuid4()), 'text': data.text, 'party_name': data.party_name,
        'needed_by': data.needed_by, 'priority': data.priority or 'Normal',
        'created_at': now_iso(), 'created_by': {'id': user['id'], 'name': user['name']},
    }
    await db.production_urgent.insert_one(dict(doc))
    return doc


@production_router.delete('/urgent/{requirement_id}')
async def remove_urgent_requirement(requirement_id: str, user=Depends(current_user)):
    result = await db.production_urgent.delete_one({'id': requirement_id})
    if not result.deleted_count:
        raise HTTPException(404, 'Urgent requirement not found')
    return {'ok': True}
