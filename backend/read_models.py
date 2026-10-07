"""Bounded list read models. Database-side grouping; no per-row queries."""
import asyncio
import re
from database import db
from stock_ledger import recover_stock


def page_meta(total, page, size):
    return {'total': total, 'page': page, 'page_size': size, 'pages': max(1, (total+size-1)//size)}


async def requirements_list(q, catalogue_id, page, page_size):
    from stock import pending_stock_suggestions
    base = [{'$match': {'visible': True, 'state': 'pending'}}, {'$unwind': '$parcels'}, {'$match': {'parcels.status': 'Pending'}}]
    group = [{'$unwind': '$parcels.compositions'}, {'$group': {
        '_id': {'catalogue_id': '$parcels.compositions.catalogue_id', 'volume_id': '$parcels.compositions.volume_id'},
        'catalogue_name': {'$first': '$parcels.compositions.catalogue_name'}, 'volume_name': {'$first': '$parcels.compositions.volume_name'},
        'pieces_per_set': {'$first': '$parcels.compositions.pieces_per_set'}, 'sets': {'$sum': '$parcels.compositions.sets'},
        'pieces': {'$sum': {'$multiply': ['$parcels.compositions.pieces_per_set', '$parcels.compositions.sets']}}}},
        {'$project': {'_id': 0, 'catalogue_id': '$_id.catalogue_id', 'volume_id': '$_id.volume_id', 'catalogue_name': 1, 'volume_name': 1, 'pieces_per_set': 1, 'sets': 1, 'pieces': 1}}]
    if catalogue_id: group.append({'$match': {'catalogue_id': catalogue_id}})
    if q.strip(): group.append({'$match': {'$or': [{'catalogue_name': {'$regex': re.escape(q.strip()), '$options': 'i'}}, {'volume_name': {'$regex': re.escape(q.strip()), '$options': 'i'}}]}})
    summary = [{'$group': {'_id': '$id', 'parcels': {'$sum': 1}, 'pieces': {'$sum': '$parcels.target'}, 'sets': {'$sum': {'$sum': '$parcels.compositions.sets'}}}}, {'$group': {'_id': None, 'orders': {'$sum': 1}, 'parcels': {'$sum': '$parcels'}, 'pieces': {'$sum': '$pieces'}, 'sets': {'$sum': '$sets'}}}, {'$project': {'_id': 0}}]
    result, suggestions = await asyncio.gather(db.orders.aggregate([*base, {'$facet': {
        'rows': [*group, {'$sort': {'catalogue_name': 1, 'volume_name': 1, 'volume_id': 1}}, {'$skip': (page-1)*page_size}, {'$limit': page_size}],
        'count': [*group, {'$count': 'total'}], 'summary': summary}}], maxTimeMS=15000).to_list(1), pending_stock_suggestions())
    result = result[0]
    total = (result['count'] or [{'total': 0}])[0]['total']
    return {'rows': result['rows'], 'summary': (result['summary'] or [{}])[0], 'suggestions': suggestions, **page_meta(total, page, page_size)}


async def production_list(q, page, page_size, urgent_page):
    match = {}
    if q.strip():
        prefix = {'$regex': '^' + re.escape(q.strip()), '$options': 'i'}
        match['$or'] = [{'design_no': prefix}, {'catalogue_name': prefix}, {'volume_name': prefix}]
    pipeline = [{'$match': match}, {'$sort': {'created_at': -1, 'id': -1}}, {'$facet': {
        'batches': [{'$skip': (page-1)*page_size}, {'$limit': page_size}, {'$project': {'_id': 0, 'photo_data_url': 0, 'history': 0, 'design_no_key': 0}}],
        'count': [{'$count': 'total'}],
        'summary': [{'$unwind': '$stage_balances'}, {'$group': {'_id': '$stage_balances.stage', 'pieces': {'$sum': '$stage_balances.pieces'}}}, {'$project': {'_id': 0, 'stage': '$_id', 'pieces': 1}}],
        'totals': [{'$group': {'_id': None, 'produced': {'$sum': '$total_pieces'}}}, {'$project': {'_id': 0}}]
    }}]
    results, urgent, urgent_count = await asyncio.gather(
        db.stock_batches.aggregate(pipeline, maxTimeMS=15000).to_list(1),
        db.production_urgent.find({}, {'_id': 0}).sort([('created_at', -1), ('id', -1)]).skip((urgent_page-1)*20).limit(20).to_list(20),
        db.production_urgent.count_documents({}, maxTimeMS=10000))
    result = results[0]
    total = (result['count'] or [{'total': 0}])[0]['total']
    stages = {row['stage']: row['pieces'] for row in result['summary']}
    produced = (result['totals'] or [{'produced': 0}])[0]['produced']
    return {'batches': result['batches'], 'summary': result['summary'], 'stages': ['Unissued', 'Stitching', 'Folding', 'Packing'],
            'totals': {'produced': produced, 'unissued': stages.get('Unissued', 0), 'packing': stages.get('Packing', 0), 'in_process': produced-stages.get('Unissued', 0)},
            'urgent': urgent, 'urgent_pagination': page_meta(urgent_count, urgent_page, 20), **page_meta(total, page, page_size)}


async def stock_list(q, page, page_size, movement_page):
    await recover_stock()
    # Each source contributes quantities once. Master labels are first and win.
    pipeline = [
        {'$unwind': '$volumes'}, {'$project': {'_id': 0, 'catalogue_id': '$id', 'volume_id': '$volumes.id', 'catalogue_name': '$name', 'volume_name': '$volumes.name', 'pieces_per_set': '$volumes.pieces_per_set', 'available': {'$literal': 0}, 'pending': {'$literal': 0}, 'pending_sets': {'$literal': 0}, 'version': {'$literal': 0}}},
        {'$unionWith': {'coll': 'stock_balances', 'pipeline': [{'$project': {'_id': 0, 'catalogue_id': 1, 'volume_id': 1, 'catalogue_name': 1, 'volume_name': 1, 'pieces_per_set': 1, 'available': '$available_pieces', 'pending': {'$literal': 0}, 'pending_sets': {'$literal': 0}, 'version': {'$ifNull': ['$balance_version', 0]}}}]}},
        {'$unionWith': {'coll': 'orders', 'pipeline': [{'$match': {'visible': True, 'state': 'pending'}}, {'$unwind': '$parcels'}, {'$match': {'parcels.status': 'Pending'}}, {'$unwind': '$parcels.compositions'}, {'$replaceWith': '$parcels.compositions'}, {'$project': {'_id': 0, 'catalogue_id': 1, 'volume_id': 1, 'catalogue_name': 1, 'volume_name': 1, 'pieces_per_set': 1, 'available': {'$literal': 0}, 'pending': {'$multiply': ['$sets', '$pieces_per_set']}, 'pending_sets': '$sets', 'version': {'$literal': 0}}}]}},
        {'$group': {'_id': {'catalogue_id': '$catalogue_id', 'volume_id': '$volume_id'}, 'catalogue_name': {'$first': '$catalogue_name'}, 'volume_name': {'$first': '$volume_name'}, 'pieces_per_set': {'$first': '$pieces_per_set'}, 'available_pieces': {'$sum': '$available'}, 'pending_pieces': {'$sum': '$pending'}, 'pending_sets': {'$sum': '$pending_sets'}, 'version': {'$max': '$version'}}},
        {'$set': {'catalogue_id': '$_id.catalogue_id', 'volume_id': '$_id.volume_id', 'available_sets': {'$floor': {'$divide': ['$available_pieces', '$pieces_per_set']}}, 'shortfall_pieces': {'$max': [0, {'$subtract': ['$pending_pieces', {'$max': [0, '$available_pieces']}]}]}}},
        {'$project': {'_id': 0}}
    ]
    if q.strip():
        prefix = {'$regex': re.escape(q.strip()), '$options': 'i'}
        pipeline.append({'$match': {'$or': [{'catalogue_name': prefix}, {'volume_name': prefix}]}})
    pipeline += [{'$facet': {
        'summary': [{'$sort': {'catalogue_name': 1, 'volume_name': 1, 'volume_id': 1}}, {'$skip': (page-1)*page_size}, {'$limit': page_size}],
        'count': [{'$count': 'total'}],
        'totals': [{'$group': {'_id': None, 'available_sets': {'$sum': '$available_sets'}, 'pending_sets': {'$sum': '$pending_sets'}}}, {'$project': {'_id': 0}}]
    }}]
    movement_match = {'ready_delta': {'$ne': 0}, 'state': {'$nin': ['pending', 'rejected']}}
    results, movements, movement_count = await asyncio.gather(
        db.catalogues.aggregate(pipeline, maxTimeMS=15000).to_list(1),
        db.stock_movements.find(movement_match, {'_id': 0, 'digest': 0, 'requested_delta': 0, 'target_pieces': 0, 'expected_version': 0}).sort([('created_at', -1), ('id', -1)]).skip((movement_page-1)*20).limit(20).to_list(20),
        db.stock_movements.count_documents(movement_match, maxTimeMS=10000))
    result = results[0]
    total = (result['count'] or [{'total': 0}])[0]['total']
    return {'summary': result['summary'], 'totals': (result['totals'] or [{}])[0], 'movements': movements,
            'movement_pagination': page_meta(movement_count, movement_page, 20), **page_meta(total, page, page_size)}
