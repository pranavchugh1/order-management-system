"""Bills: exact integer-paise accounting with owner-scoped, atomic ledgers.

A bill and every cash event live in one document. CAS updates keep balances and
history consistent on standalone MongoDB, without requiring replica transactions.
"""
import hashlib
import json
import re
import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from auth import require_page
from database import db, now_iso, today_iso

router = APIRouter(prefix='/api/bills', tags=['Bills'])
MAX_MONEY = 100_000_000_000

class BillFields(BaseModel):
    model_config = ConfigDict(extra='forbid')
    vendor: str = Field(min_length=1, max_length=120)
    reference: str = Field(default='', max_length=80)
    date: date
    amount_paise: int = Field(strict=True, gt=0, le=MAX_MONEY)
    notes: str = Field(default='', max_length=2000)

    @field_validator('vendor', 'reference', 'notes')
    @classmethod
    def trim(cls, value):
        return value.strip()

    @field_validator('vendor')
    @classmethod
    def required(cls, value):
        if not value: raise ValueError('Vendor is required')
        return value

    @field_validator('date')
    @classmethod
    def valid_date(cls, value):
        if value.isoformat() > today_iso(): raise ValueError('Date cannot be in the future')
        return value

class CreateBill(BillFields):
    request_id: uuid.UUID
    initial_issue_paise: int = Field(default=0, strict=True, ge=0, le=MAX_MONEY)

class EditBill(BillFields):
    version: int = Field(strict=True, ge=0)

class CashEntry(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: uuid.UUID
    kind: Literal['issue', 'return']
    amount_paise: int = Field(strict=True, gt=0, le=MAX_MONEY)
    date: date
    note: str = Field(default='', max_length=500)
    _date = field_validator('date')(BillFields.valid_date.__func__)


def scope(user):
    return {} if user['role'] == 'admin' else {'created_by': user['id']}


def digest(data):
    return hashlib.sha256(json.dumps(data.model_dump(mode='json'), sort_keys=True).encode()).hexdigest()


def balances(amount, issued, returned):
    net = issued - returned
    return {'net_issued_paise': net, 'payable_paise': max(0, amount - net),
            'returnable_paise': max(0, net - amount),
            'status': 'payable' if net < amount else 'excess' if net > amount else 'settled'}


def public(doc, detail=True):
    hidden = {'_id', 'create_digest', 'request_id', 'vendor_key', 'reference_key'}
    if not detail: hidden |= {'payments', 'edits'}
    return {k: v for k, v in doc.items() if k not in hidden}


async def initialize_bills():
    await db.bills.create_index('id', unique=True)
    await db.bills.create_index('bill_number', unique=True)
    await db.bills.create_index([('created_by', 1), ('request_id', 1)], unique=True)
    for fields in ([('created_by', 1), ('created_at', -1), ('id', -1)], [('created_at', -1), ('id', -1)],
                   [('created_by', 1), ('status', 1), ('created_at', -1)], [('created_by', 1), ('vendor_key', 1)]):
        await db.bills.create_index(fields)


@router.get('')
async def list_bills(q: str = Query('', max_length=120), status: Literal['all', 'payable', 'excess', 'settled'] = 'all',
                     page: int = Query(1, ge=1, le=100000), page_size: int = Query(20, ge=1, le=100), user=Depends(require_page('bills'))):
    match = scope(user)
    if q.strip():
        prefix = '^' + re.escape(q.strip().casefold())
        match['$or'] = [{'vendor_key': {'$regex': prefix}}, {'reference_key': {'$regex': prefix}}, {'bill_number': {'$regex': '^' + re.escape(q.strip()), '$options': 'i'}}]
    filtered = [] if status == 'all' else [{'$match': {'status': status}}]
    sums = {key: {'$sum': '$' + key} for key in ['amount_paise', 'issued_paise', 'returned_paise', 'payable_paise', 'returnable_paise']}
    pipeline = [{'$match': match}, {'$sort': {'created_at': -1, 'id': -1}}, {'$facet': {
        'items': [*filtered, {'$skip': (page-1)*page_size}, {'$limit': page_size}, {'$project': {'_id': 0, 'payments': 0, 'edits': 0, 'create_digest': 0, 'request_id': 0, 'vendor_key': 0, 'reference_key': 0}}],
        'count': [*filtered, {'$count': 'total'}],
        'summary': [{'$group': {'_id': None, 'count': {'$sum': 1}, **sums,
            **{s: {'$sum': {'$cond': [{'$eq': ['$status', s]}, 1, 0]}} for s in ['payable', 'excess', 'settled']}}}, {'$project': {'_id': 0}}]
    }}]
    result = (await db.bills.aggregate(pipeline, maxTimeMS=10000).to_list(1))[0]
    total = (result['count'] or [{'total': 0}])[0]['total']
    return {'items': result['items'], 'summary': (result['summary'] or [{}])[0], 'total': total,
            'page': page, 'page_size': page_size, 'pages': max(1, (total + page_size - 1)//page_size)}


@router.post('', status_code=201)
async def create_bill(data: CreateBill, user=Depends(require_page('bills'))):
    key = {'created_by': user['id'], 'request_id': str(data.request_id)}
    fingerprint = digest(data)
    old = await db.bills.find_one(key)
    if old:
        if old['create_digest'] != fingerprint: raise HTTPException(409, 'This save key was used for different bill details.')
        return public(old)
    counter = await db.counters.find_one_and_update({'name': 'bills'}, {'$inc': {'value': 1}}, upsert=True, return_document=ReturnDocument.AFTER)
    stamp = now_iso()
    doc = {**data.model_dump(mode='json', exclude={'initial_issue_paise'}), **key, 'id': str(uuid.uuid4()),
           'bill_number': f'BILL-{counter["value"]:04d}', 'created_by_name': user['name'],
           'created_at': stamp, 'updated_at': stamp, 'version': 0, 'create_digest': fingerprint,
           'vendor_key': data.vendor.casefold(), 'reference_key': data.reference.casefold(),
           'issued_paise': data.initial_issue_paise, 'returned_paise': 0, 'payments': [], 'edits': [],
           **balances(data.amount_paise, data.initial_issue_paise, 0)}
    if data.initial_issue_paise:
        doc['payments'].append({'id': str(data.request_id), 'kind': 'issue', 'amount_paise': data.initial_issue_paise,
                                'date': data.date.isoformat(), 'note': 'Initial cash issued', 'created_at': stamp,
                                'recorded_by': user['id'], 'recorded_by_name': user['name']})
    try:
        await db.bills.insert_one(dict(doc))
    except DuplicateKeyError:
        old = await db.bills.find_one(key)
        if not old or old['create_digest'] != fingerprint: raise HTTPException(409, 'Bill changed during save. Retry with a new save key.')
        return public(old)
    return public(doc)


@router.get('/{bill_id}')
async def get_bill(bill_id: str, user=Depends(require_page('bills'))):
    doc = await db.bills.find_one({'id': bill_id, **scope(user)})
    if not doc: raise HTTPException(404, 'Bill not found')
    return public(doc)


@router.put('/{bill_id}')
async def edit_bill(bill_id: str, data: EditBill, user=Depends(require_page('bills'))):
    query = {'id': bill_id, **scope(user)}
    old = await db.bills.find_one(query)
    if not old: raise HTTPException(404, 'Bill not found')
    if old['version'] != data.version: raise HTTPException(409, 'This bill changed. Close and reopen it before editing.')
    if len(old.get('edits', [])) >= 100: raise HTTPException(409, 'Bill edit history limit reached.')
    changes = data.model_dump(mode='json', exclude={'version'})
    changes.update(vendor_key=data.vendor.casefold(), reference_key=data.reference.casefold(), updated_at=now_iso(),
                   **balances(data.amount_paise, old['issued_paise'], old['returned_paise']))
    history = {k: old[k] for k in ['vendor', 'reference', 'date', 'amount_paise', 'notes']}
    history.update(changed_at=now_iso(), changed_by=user['id'], changed_by_name=user['name'])
    updated = await db.bills.find_one_and_update({**query, 'version': data.version},
        {'$set': changes, '$inc': {'version': 1}, '$push': {'edits': history}}, return_document=ReturnDocument.AFTER)
    if not updated: raise HTTPException(409, 'This bill changed. Close and reopen it before editing.')
    return public(updated)


@router.post('/{bill_id}/payments')
async def record_cash(bill_id: str, data: CashEntry, user=Depends(require_page('bills'))):
    query = {'id': bill_id, **scope(user)}
    old = await db.bills.find_one(query)
    if not old: raise HTTPException(404, 'Bill not found')
    ident = str(data.request_id)
    fingerprint = digest(data)
    previous = next((p for p in old['payments'] if p['id'] == ident), None)
    if previous:
        if previous.get('digest') != fingerprint: raise HTTPException(409, 'This cash-entry key was used for different details.')
        return public(old)
    if len(old['payments']) >= 2000: raise HTTPException(409, 'Maximum 2,000 cash entries per bill reached.')
    if data.kind == 'return' and data.amount_paise > old['returnable_paise']:
        raise HTTPException(400, 'Cash returned cannot exceed the excess cash on this bill.')
    issued = old['issued_paise'] + (data.amount_paise if data.kind == 'issue' else 0)
    returned = old['returned_paise'] + (data.amount_paise if data.kind == 'return' else 0)
    if issued > MAX_MONEY: raise HTTPException(400, 'Total cash issued exceeds the bill ledger limit.')
    entry = {**data.model_dump(mode='json', exclude={'request_id'}), 'id': ident, 'digest': fingerprint,
             'created_at': now_iso(), 'recorded_by': user['id'], 'recorded_by_name': user['name']}
    updated = await db.bills.find_one_and_update({**query, 'version': old['version'], 'payments.id': {'$ne': ident}},
        {'$set': {'issued_paise': issued, 'returned_paise': returned, 'updated_at': now_iso(),
                  **balances(old['amount_paise'], issued, returned)}, '$push': {'payments': entry}, '$inc': {'version': 1}},
        return_document=ReturnDocument.AFTER)
    if not updated:
        current = await db.bills.find_one(query)
        replay = next((p for p in (current or {}).get('payments', []) if p['id'] == ident), None)
        if replay and replay.get('digest') == fingerprint: return public(current)
        raise HTTPException(409, 'Another entry was saved at the same time. Retry this cash entry safely.')
    return public(updated)
