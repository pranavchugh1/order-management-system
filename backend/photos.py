"""Authenticated, resumable image uploads persisted in MongoDB, not local temp files."""
import hashlib
import io
import math
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from pymongo.errors import DuplicateKeyError
from starlette.concurrency import run_in_threadpool
from PIL import Image, UnidentifiedImageError

from auth import current_user, require_page, rate_limit
from database import db

router = APIRouter(prefix='/api/photos', dependencies=[Depends(require_page('production'))])
CHUNK_SIZE = 128 * 1024
MAX_SIZE = 5 * 1024 * 1024
TYPES = {'image/png': 'PNG', 'image/jpeg': 'JPEG', 'image/webp': 'WEBP'}
Image.MAX_IMAGE_PIXELS = 20_000_000

class StartUpload(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=200)
    size: int = Field(strict=True, gt=0, le=MAX_SIZE)
    content_type: str

async def initialize_photos():
    await db.photo_uploads.create_index('id', unique=True)
    await db.photo_uploads.create_index('expires_at', expireAfterSeconds=0)
    await db.photo_chunks.create_index([('upload_id', 1), ('index', 1)], unique=True)
    await db.photo_chunks.create_index('expires_at', expireAfterSeconds=0)
    await db.photos.create_index('id', unique=True)
    await db.photos.create_index('created_by')

@router.post('/uploads', status_code=201)
async def start_upload(data: StartUpload, user=Depends(current_user)):
    if data.content_type not in TYPES: raise HTTPException(400, 'Choose a PNG, JPG or WebP image.')
    await rate_limit(f'photo-upload:{user["id"]}', 100, 3600)
    ident = str(uuid.uuid4())
    doc = {'_id': ident, 'id': ident, **data.model_dump(), 'created_by': user['id'], 'chunks': math.ceil(data.size / CHUNK_SIZE), 'expires_at': datetime.now(timezone.utc) + timedelta(days=1)}
    await db.photo_uploads.insert_one(doc)
    return {'id': ident, 'chunk_size': CHUNK_SIZE, 'chunks': doc['chunks']}

@router.put('/uploads/{upload_id}/{index}')
async def put_chunk(upload_id: str, index: int, request: Request, user=Depends(current_user)):
    doc = await db.photo_uploads.find_one({'id': upload_id, 'created_by': user['id']})
    if not doc: raise HTTPException(404, 'Upload not found or expired. Select the file again.')
    if index < 0 or index >= doc['chunks']: raise HTTPException(400, 'Invalid chunk number')
    content = bytearray()
    async for part in request.stream():
        content.extend(part)
        if len(content) > CHUNK_SIZE: raise HTTPException(413, 'Chunk exceeds 128 KiB')
    expected = CHUNK_SIZE if index < doc['chunks']-1 else doc['size']-index*CHUNK_SIZE
    if len(content) != expected: raise HTTPException(400, 'Incomplete chunk; retry this part')
    digest = hashlib.sha256(content).hexdigest()
    key = {'upload_id': upload_id, 'index': index}
    try:
        await db.photo_chunks.insert_one({'_id': str(uuid.uuid4()), **key, 'data': bytes(content), 'digest': digest, 'expires_at': doc['expires_at']})
    except DuplicateKeyError:
        existing = await db.photo_chunks.find_one(key, {'digest': 1})
        if not existing or existing['digest'] != digest: raise HTTPException(409, 'This chunk was already uploaded with different content.')
    return {'index': index, 'received': len(content)}


def verify_image(content, expected):
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format != expected or image.width * image.height > Image.MAX_IMAGE_PIXELS:
                raise ValueError('Image format or dimensions are not supported')
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(400, 'This file is not a valid image, or exceeds 20 megapixels.')

@router.post('/uploads/{upload_id}/complete')
async def complete_upload(upload_id: str, user=Depends(current_user)):
    existing = await db.photos.find_one({'id': upload_id, 'created_by': user['id']}, {'_id': 0, 'id': 1})
    if existing: return existing
    doc = await db.photo_uploads.find_one({'id': upload_id, 'created_by': user['id']})
    if not doc: raise HTTPException(404, 'Upload not found or expired')
    chunks = await db.photo_chunks.find({'upload_id': upload_id}).sort('index', 1).to_list(40)
    if len(chunks) != doc['chunks']: raise HTTPException(409, 'Some parts are missing. Retry the upload.')
    content = b''.join(chunk['data'] for chunk in chunks)
    if len(content) != doc['size']: raise HTTPException(409, 'Upload is incomplete')
    await run_in_threadpool(verify_image, content, TYPES[doc['content_type']])
    try:
        await db.photos.insert_one({'_id': upload_id, 'id': upload_id, 'created_by': user['id'], 'content_type': doc['content_type'], 'data': content,
                                    'sha256': hashlib.sha256(content).hexdigest(), 'size': len(content), 'created_at': datetime.now(timezone.utc)})
    except DuplicateKeyError:
        pass
    await db.photo_chunks.delete_many({'upload_id': upload_id})
    await db.photo_uploads.delete_one({'id': upload_id})
    return {'id': upload_id}

async def validate_photo_owner(photo_id, user):
    if not photo_id: return
    doc = await db.photos.find_one({'id': str(photo_id)}, {'created_by': 1})
    if not doc or doc['created_by'] != user['id']:
        raise HTTPException(400, 'Select and upload this photo again with your account.')

@router.get('/{photo_id}')
async def get_photo(photo_id: str, user=Depends(current_user)):
    # Any authorized production user may view a photo attached to production.
    doc = await db.photos.find_one({'id': photo_id})
    if not doc: raise HTTPException(404, 'Photo not found')
    if doc['created_by'] != user['id'] and not await db.stock_batches.find_one({'photo_id': photo_id}, {'_id': 1}):
        raise HTTPException(404, 'Photo not found')
    return Response(bytes(doc['data']), media_type=doc['content_type'], headers={'Cache-Control': 'private, max-age=300', 'X-Content-Type-Options': 'nosniff', 'Content-Disposition': 'inline'})
