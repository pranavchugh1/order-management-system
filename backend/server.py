import logging
import os
from contextlib import asynccontextmanager

from database import client, db
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pymongo.errors import DuplicateKeyError, PyMongoError
from starlette.middleware.cors import CORSMiddleware

from auth import ORIGINS, current_user, initialize_auth, router as auth_router
from bills import initialize_bills, router as bills_router
from stock_ledger import initialize_ledger, recover_stock
from photos import initialize_photos, router as photos_router
from bulk_orders import router as bulk_router
from exports import router as export_router
from masters import router as master_router
from order_routes import router as order_router
from order_service import computed_fields
from stock import production_router, stock_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    for collection in ('parties', 'catalogues', 'orders'):
        await db[collection].create_index('id', unique=True)
    for collection in ('parties', 'catalogues'):
        await db[collection].create_index('name_key', unique=True, partialFilterExpression={'name_key': {'$exists': True}})
        await db[collection].create_index('name')
    for field in ('party_id', 'parcels.compositions.catalogue_id', 'parcels.compositions.volume_id'):
        await db.orders.create_index(field)
    await db.orders.create_index([('visible', 1), ('state', 1), ('created_at', -1), ('id', -1)])
    await db.orders.create_index([('visible', 1), ('created_at', -1), ('id', -1)])
    await db.orders.create_index([('visible', 1), ('party_name_key', 1)])
    await db.orders.create_index([('visible', 1), ('order_number_key', 1)])
    await db.orders.create_index([('visible', 1), ('parcels.status', 1)])
    await db.orders.create_index([('visible', 1), ('state', 1), ('party_name_key', 1), ('created_at', 1), ('id', 1)])
    await db.orders.create_index('order_number', unique=True)
    await db.orders.create_index('batch_key')
    await db.bulk_batches.create_index('key', unique=True)
    await db.stock_balances.create_index([('catalogue_id', 1), ('volume_id', 1)], unique=True)
    await db.stock_balances.create_index([('catalogue_name', 1), ('volume_name', 1)])
    await db.stock_batches.create_index('id', unique=True)
    await db.stock_batches.create_index([('catalogue_id', 1), ('volume_id', 1), ('design_no_key', 1)], unique=True)
    await db.stock_batches.create_index([('created_at', -1), ('id', -1)])
    await db.stock_batches.create_index([('catalogue_id', 1), ('volume_id', 1), ('created_at', -1)])
    await db.stock_movements.create_index('id', unique=True)
    await db.stock_movements.create_index('source_key', unique=True, partialFilterExpression={'source_key': {'$exists': True}})
    await db.stock_movements.create_index([('catalogue_id', 1), ('volume_id', 1), ('created_at', -1)])
    await db.stock_movements.create_index([('batch_id', 1), ('created_at', -1)])
    await db.stock_movements.create_index([('order_id', 1), ('parcel_index', 1)])
    await db.stock_movements.create_index([('created_at', -1), ('id', -1)])
    await db.stock_movements.create_index([('source', 1), ('created_at', -1)])
    await db.stock_movements.create_index([('ready_delta', 1), ('created_at', -1)])
    await db.production_urgent.create_index('id', unique=True)
    await db.production_urgent.create_index([('created_at', -1), ('id', -1)])
    await db.counters.create_index('name', unique=True)
    for collection in ('stock_batches', 'stock_balances', 'stock_movements'):
        await db[collection].create_index('volume_id')
    for collection in ('catalogues', 'parties'):
        await db[collection].create_index([('name_key', 1), ('id', 1)])
    await db.users.create_index([('created_at', 1), ('id', 1)])
    await db.users.create_index([('active', 1), ('created_at', 1), ('id', 1)])
    await db.stock_batches.create_index('photo_id')
    await db.rate_limits.create_index('key', unique=True)
    await db.rate_limits.create_index('created_at', expireAfterSeconds=3600)
    # One-time, backwards-compatible migration; normal requests never perform this work.
    async for old in db.orders.find({'party_name_key': {'$exists': False}}, {'_id': 0}):
        fields = computed_fields(old)
        fields.update(version=old.get('version', 0), visible=old.get('visible', True))
        await db.orders.update_one({'id': old['id']}, {'$set': fields})
    await initialize_auth()
    await initialize_bills()
    await initialize_ledger()
    await initialize_photos()
    await recover_stock()
    yield
    client.close()


app = FastAPI(title='Aditya Prints Order Desk', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware('http')
async def security_middleware(request: Request, call_next):
    response = None
    if request.method in ('POST', 'PUT', 'PATCH'):
        length = request.headers.get('content-length')
        if length and (not length.isdigit() or int(length) > 2_000_000):
            response = JSONResponse(status_code=413, content={'detail': 'Request is too large (maximum 2 MB).'})
        if response is None:
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 2_000_000:
                    response = JSONResponse(status_code=413, content={'detail': 'Request is too large (maximum 2 MB).'}); break
            if response is None:
                request._body = bytes(body)
    if response is None:
        try:
            response = await call_next(request)
        except Exception:
            logger.exception('Unhandled request failure at %s', request.url.path)
            response = JSONResponse(status_code=500, content={'detail': 'Something went wrong. Please try again.'})
    for key, value in {'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY', 'Referrer-Policy': 'no-referrer', 'Permissions-Policy': 'camera=(), microphone=(), geolocation=()', 'Cache-Control': 'no-store', 'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'"}.items():
        response.headers[key] = value
    return response


@app.exception_handler(RequestValidationError)
async def invalid_data(request, exc):
    return JSONResponse(status_code=422, content={'detail': 'The submitted data is invalid. Check required fields and numeric limits.'})


@app.exception_handler(DuplicateKeyError)
async def duplicate_error(request, exc):
    return JSONResponse(status_code=409, content={'detail': 'A record with these details already exists.'})


@app.exception_handler(PyMongoError)
async def database_error(request, exc):
    logger.exception('Database request failed')
    return JSONResponse(status_code=503, content={'detail': 'The workspace is temporarily unavailable. Please try again.'})


@app.get('/api/')
async def root():
    return {'message': 'Aditya Prints API'}


for router in (auth_router, master_router, bulk_router, export_router, order_router, stock_router, production_router, bills_router, photos_router):
    app.include_router(router)
app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_credentials=True, allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'], allow_headers=['Content-Type', 'X-CSRF-Token'], expose_headers=['Content-Disposition', 'Retry-After'])
