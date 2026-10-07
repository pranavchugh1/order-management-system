"""Recoverable stock operations for standalone MongoDB.

The account CAS stores the new balance and a receipt in ONE atomic update.
The ledger is finalized before removing the receipt. Every receipt removal bumps
revision. Crucially, workers read the account BEFORE the operation state: a stale
worker can never reapply after receipt cleanup because its revision is obsolete.
This is recoverable consistency, not a cross-document transaction. Stock reads
repair incomplete operations before reporting balances; dispatch carries an
atomic recovery marker on the order. No process-local lock is required for safety.
"""
import asyncio
import hashlib
import json
import uuid

from fastapi import HTTPException
from pymongo import UpdateOne
from pymongo.errors import DuplicateKeyError
from database import db, now_iso, clean


async def initialize_ledger():
    await db.stock_movements.create_index([('state', 1), ('created_at', 1)])
    await db.orders.create_index([('visible', 1), ('parcels.stock_state', 1)])
    await db.stock_balances.create_index('receipts.key', sparse=True)
    await db.stock_balances.update_many({'revision': {'$exists': False}}, {'$set': {'revision': 0, 'balance_version': 0, 'receipts': []}})


async def ensure_account(op):
    query = {'catalogue_id': op['catalogue_id'], 'volume_id': op['volume_id']}
    try:
        await db.stock_balances.update_one(query, {'$setOnInsert': {
            **query, 'id': str(uuid.uuid4()), 'available_pieces': 0, 'revision': 0, 'balance_version': 0,
            'receipts': [], 'created_at': now_iso(), 'catalogue_name': op['catalogue_name'],
            'volume_name': op['volume_name'], 'pieces_per_set': op['pieces_per_set']}}, upsert=True)
    except DuplicateKeyError:
        pass
    return query


async def apply_operation(op):
    query = await ensure_account(op)
    for _ in range(30):
        # Do not reorder these reads: account-before-operation is part of safety.
        account = await db.stock_balances.find_one(query, {'_id': 0})
        current = await db.stock_movements.find_one({'source_key': op['source_key']}, {'_id': 0})
        if not current: raise HTTPException(503, 'Stock operation unavailable. Retry safely.')
        if current.get('state') == 'rejected': raise HTTPException(409, current['error'])
        if current.get('state') == 'applied':
            await db.stock_balances.update_one({**query, 'receipts.key': op['source_key']},
                {'$pull': {'receipts': {'key': op['source_key']}}, '$inc': {'revision': 1}})
            return current
        receipt = next((r for r in account.get('receipts', []) if r['key'] == op['source_key']), None)
        if receipt is None:
            expected = current.get('expected_version')
            if expected is not None and expected != account.get('balance_version', 0):
                message = 'Stock changed since this balance was opened. Reload before editing.'
                await db.stock_movements.update_one({'source_key': op['source_key'], 'state': 'pending'}, {'$set': {'state': 'rejected', 'error': message}})
                raise HTTPException(409, message)
            previous = int(account.get('available_pieces', 0))
            delta = int(current['target_pieces']) - previous if current.get('operation') == 'set' else int(current['requested_delta'])
            receipt = {'key': op['source_key'], 'delta': delta, 'previous': previous, 'available': previous + delta, 'version': account.get('balance_version', 0) + 1}
            if len(account.get('receipts', [])) >= 1000:
                raise HTTPException(503, 'Stock recovery is pending. Ask the administrator to run recovery before retrying.')
            result = await db.stock_balances.update_one({**query, 'revision': account['revision']},
                {'$inc': {'available_pieces': delta, 'revision': 1, 'balance_version': 1}, '$push': {'receipts': receipt},
                 '$set': {'updated_at': now_iso(), 'catalogue_name': current['catalogue_name'],
                          'volume_name': current['volume_name'], 'pieces_per_set': current['pieces_per_set']}})
            if not result.matched_count:
                await asyncio.sleep(0)
                continue
        await db.stock_movements.update_one({'source_key': op['source_key'], 'state': 'pending'},
            {'$set': {'state': 'applied', 'ready_delta': receipt['delta'], 'previous_pieces': receipt['previous'],
                      'available_pieces': receipt['available'], 'balance_version': receipt['version'], 'applied_at': now_iso()}})
        await db.stock_balances.update_one({**query, 'receipts.key': op['source_key']},
            {'$pull': {'receipts': {'key': op['source_key']}}, '$inc': {'revision': 1}})
        return await db.stock_movements.find_one({'source_key': op['source_key']}, {'_id': 0})
    raise HTTPException(409, 'Stock is being updated by another request. Retry the same operation safely.')


async def submit_operation(movement, payload):
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    movement = {**movement, 'state': 'pending', 'digest': fingerprint}
    try:
        await db.stock_movements.insert_one(dict(movement))
    except DuplicateKeyError:
        movement = await db.stock_movements.find_one({'source_key': movement['source_key']}, {'_id': 0})
        if not movement or movement.get('digest') != fingerprint:
            raise HTTPException(409, 'This operation key belongs to different stock details. Start a new entry.')
    result = await apply_operation(movement)
    return {k: v for k, v in result.items() if k not in ('digest', 'requested_delta', 'target_pieces', 'expected_version', 'operation')}


async def dispatch_stock(order, parcel_index, user=None):
    parcel = order['parcels'][parcel_index]
    if parcel.get('stock_state') != 'pending': return
    actor = parcel.get('dispatched_by') or ({'id': user['id'], 'name': user['name']} if user else None)
    operations = []
    for ci, comp in enumerate(parcel['compositions']):
        pieces = int(comp['pieces_per_set']) * int(comp['sets'])
        movement = {'id': str(uuid.uuid4()), 'source': 'dispatch', 'source_key': f"dispatch:{order['id']}:{parcel_index}:{ci}",
            'order_id': order['id'], 'order_number': order['order_number'], 'party_id': order['party_id'], 'party_name': order['party_name'],
            'parcel_index': parcel_index, **{k: comp[k] for k in ['catalogue_id', 'volume_id', 'catalogue_name', 'volume_name', 'pieces_per_set', 'sets']},
            'pieces': pieces, 'requested_delta': -pieces, 'ready_delta': -pieces, 'state': 'pending',
            'created_at': parcel.get('sent_at') or now_iso(), 'created_by': actor}
        operations.append(UpdateOne({'source_key': movement['source_key']}, {'$setOnInsert': movement}, upsert=True))
    if operations:
        await db.stock_movements.bulk_write(operations, ordered=False)
        movements = await db.stock_movements.find({'order_id': order['id'], 'parcel_index': parcel_index, 'source': 'dispatch'}, {'_id': 0}).to_list(100)
        # Sequential per parcel is bounded (100 compositions); no per-row read on list APIs.
        for movement in movements:
            await apply_operation(movement)
    await db.orders.update_one({'id': order['id'], f'parcels.{parcel_index}.stock_state': 'pending'},
        {'$set': {f'parcels.{parcel_index}.stock_state': 'applied'}})
    parcel['stock_state'] = 'applied'


async def recover_stock(limit=100):
    """Bounded, indexed, request/startup-driven repair; fail closed on a backlog."""
    orders = await db.orders.find({'visible': True, 'parcels.stock_state': 'pending'}, {'_id': 0}).limit(limit).to_list(limit)
    for order in orders:
        for i, parcel in enumerate(order['parcels']):
            if parcel.get('stock_state') == 'pending': await dispatch_stock(order, i)
    operations = await db.stock_movements.find({'state': 'pending'}, {'_id': 0}).sort('created_at', 1).limit(limit).to_list(limit)
    for operation in operations:
        try:
            await apply_operation(operation)
        except HTTPException as exc:
            if exc.status_code != 409: raise
    if await db.orders.find_one({'visible': True, 'parcels.stock_state': 'pending'}, {'_id': 1}) or await db.stock_movements.find_one({'state': 'pending'}, {'_id': 1}):
        raise HTTPException(503, 'Stock recovery is still running. Refresh to continue recovery; no duplicate deductions will be made.')
    # Recover a crash after ledger finalization but before receipt pruning.
    accounts = await db.stock_balances.find({'receipts.key': {'$exists': True}}, {'_id': 0, 'id': 1, 'receipts': 1}).limit(limit).to_list(limit)
    keys = [r['key'] for account in accounts for r in account['receipts']]
    if keys:
        done = await db.stock_movements.find({'source_key': {'$in': keys}, 'state': 'applied'}, {'_id': 0, 'source_key': 1}).to_list(len(keys))
        done_keys = [d['source_key'] for d in done]
        if done_keys:
            await db.stock_balances.update_many({'receipts.key': {'$in': done_keys}}, {'$pull': {'receipts': {'key': {'$in': done_keys}}}, '$inc': {'revision': 1}})
