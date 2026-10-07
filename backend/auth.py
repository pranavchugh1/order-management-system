import hashlib
import logging
import hmac
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from starlette.concurrency import run_in_threadpool

from database import db, now_iso

router = APIRouter(prefix='/api/auth', tags=['Authentication'])
SECRET = os.environ['JWT_SECRET']
ORIGINS = list({x.strip().rstrip('/') for x in os.environ.get('CORS_ORIGINS', '').split(',') if x.strip() and x.strip() != '*'} | {os.environ['NEXT_PUBLIC_BASE_URL'].rstrip('/')})
if len(SECRET) < 64 or not ORIGINS:
    raise RuntimeError('Secure authentication configuration is required')
DUMMY_HASH = bcrypt.hashpw(secrets.token_bytes(32), bcrypt.gensalt()).decode()
PAGE_ACCESS = (
    'orders_all',
    'orders_pending',
    'orders_completed',
    'bulk',
    'pending_requirements',
    'challans',
    'catalogues',
    'parties',
    'stock',
    'production',
    'bills',
)
ORDER_PAGES = ('orders_all', 'orders_pending', 'orders_completed')
MASTER_READ_PAGES = (*ORDER_PAGES, 'bulk', 'pending_requirements', 'challans', 'catalogues', 'parties', 'stock', 'production')


def clean_page_access(values):
    seen = []
    for value in values or []:
        if value not in PAGE_ACCESS:
            raise ValueError('Unknown page access')
        if value not in seen:
            seen.append(value)
    return seen


class LoginIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=72)

    @field_validator('email')
    @classmethod
    def email_valid(cls, value):
        value = value.strip().casefold()
        if value.count('@') != 1 or any(x.isspace() for x in value) or not all(value.split('@')):
            raise ValueError('Enter a valid email')
        return value

    @field_validator('password')
    @classmethod
    def password_bytes(cls, value):
        if len(value.encode()) > 72:
            raise ValueError('Password cannot exceed 72 UTF-8 bytes')
        return value


class UserIn(LoginIn):
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=72)
    page_access: list[str] = Field(min_length=1, max_length=len(PAGE_ACCESS))

    @field_validator('name')
    @classmethod
    def name_valid(cls, value):
        if not value.strip():
            raise ValueError('Name is required')
        return value.strip()

    @field_validator('page_access')
    @classmethod
    def page_access_valid(cls, value):
        return clean_page_access(value)


class UserOut(BaseModel):
    id: str
    name: str
    email: str
    role: str
    active: bool
    page_access: list[str] = Field(default_factory=list)


class UserPatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = Field(default=None, min_length=3, max_length=254)
    active: bool | None = None
    page_access: list[str] | None = None

    @field_validator('name')
    @classmethod
    def name_valid(cls, value):
        return UserIn.name_valid(value) if value is not None else None

    @field_validator('email')
    @classmethod
    def email_valid(cls, value):
        return LoginIn.email_valid(value) if value is not None else None

    @field_validator('page_access')
    @classmethod
    def page_access_valid(cls, value):
        return clean_page_access(value) if value is not None else None


class PasswordIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    password: str = Field(min_length=12, max_length=72)
    _check = field_validator('password')(LoginIn.password_bytes.__func__)


async def rate_limit(key, limit, seconds=60):
    now = datetime.now(timezone.utc)
    bucket = f'{key}:{int(now.timestamp()) // seconds}'
    try:
        doc = await db.rate_limits.find_one_and_update(
            {'key': bucket}, {'$inc': {'count': 1}, '$setOnInsert': {'created_at': now}},
            upsert=True, return_document=ReturnDocument.AFTER, projection={'_id': 0, 'count': 1})
    except DuplicateKeyError:
        doc = await db.rate_limits.find_one_and_update({'key': bucket}, {'$inc': {'count': 1}}, return_document=ReturnDocument.AFTER, projection={'_id': 0, 'count': 1})
    if doc['count'] > limit:
        retry = seconds - int(now.timestamp()) % seconds
        raise HTTPException(429, 'Too many attempts. Please try again shortly.', headers={'Retry-After': str(retry)})


def check_origin(request):
    if request.headers.get('origin', '').rstrip('/') not in ORIGINS:
        logging.getLogger(__name__).warning('Rejected request origin: %s', request.headers.get('origin', '(missing)'))
        raise HTTPException(403, 'Request origin is not allowed')


async def token_session(request, token_type='access'):
    try:
        claims = jwt.decode(request.cookies.get(f'{token_type}_token', ''), SECRET, algorithms=['HS256'], options={'require': ['exp', 'sub', 'sid', 'type']})
        if claims['type'] != token_type:
            raise jwt.InvalidTokenError()
    except jwt.InvalidTokenError:
        raise HTTPException(401, 'Please sign in to continue')
    session = await db.sessions.find_one({'id': claims['sid'], 'user_id': claims['sub'], 'expires_at': {'$gt': datetime.now(timezone.utc)}}, {'_id': 0})
    if not session or (token_type == 'refresh' and claims.get('version') != session['version']):
        raise HTTPException(401, 'Your session has ended. Please sign in again.')
    return claims, session


def check_csrf(request, session):
    check_origin(request)
    supplied = request.headers.get('x-csrf-token', '')
    if not supplied or not hmac.compare_digest(hashlib.sha256(supplied.encode()).hexdigest(), session['csrf_hash']):
        raise HTTPException(403, 'Session verification failed. Please sign in again.')


async def current_user(request: Request):
    claims, session = await token_session(request)
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        check_csrf(request, session)
    user = await db.users.find_one({'id': claims['sub'], 'active': True}, {'_id': 0, 'password_hash': 0})
    if not user or session.get('auth_version', 0) != user.get('auth_version', 0):
        raise HTTPException(401, 'Your account or session is unavailable')
    request.state.user = user
    request.state.session = session
    route = request.scope.get('route')
    bucket = route.path if route else request.url.path
    limit = 5 if '/exports/' in bucket else 20 if '/bulk/' in bucket else 180 if request.method == 'GET' else 60
    await rate_limit(f'user:{user["id"]}:{request.method}:{bucket}', limit)
    return user


async def admin_user(user=Depends(current_user)):
    if user['role'] != 'admin':
        raise HTTPException(403, 'Administrator access required')
    return user


def has_page_access(user, *pages):
    return user.get('role') == 'admin' or any(page in user.get('page_access', []) for page in pages)


def require_page(*pages):
    async def dependency(user=Depends(current_user)):
        if not has_page_access(user, *pages):
            raise HTTPException(403, 'You do not have access to this page')
        return user
    return dependency


def user_out(user):
    data = {k: v for k, v in user.items() if k != 'password_hash'}
    if data.get('role') == 'admin':
        data['page_access'] = list(PAGE_ACCESS)
    else:
        data['page_access'] = clean_page_access(data.get('page_access', []))
    return UserOut(**data)


def set_tokens(response, user_id, session, csrf=None):
    now = datetime.now(timezone.utc)
    base = {'sub': user_id, 'sid': session['id'], 'iat': now}
    for kind, seconds in [('access', 900), ('refresh', 604800)]:
        expiry = min(now + timedelta(seconds=seconds), session['expires_at'].replace(tzinfo=timezone.utc))
        token = jwt.encode({**base, 'type': kind, 'exp': expiry, 'version': session['version']}, SECRET, algorithm='HS256')
        response.set_cookie(f'{kind}_token', token, max_age=max(0, int((expiry-now).total_seconds())), httponly=True, secure=True, samesite='none', path='/api')
    if csrf:
        response.set_cookie('csrf_token', csrf, max_age=604800, httponly=False, secure=True, samesite='none', path='/')


@router.post('/login', response_model=UserOut)
async def login(data: LoginIn, request: Request, response: Response):
    check_origin(request)
    # Private Unix-socket clients have no remote IP. Keep a shared ingress cap
    # rather than trusting a spoofable forwarded IP, plus the per-email cap.
    await rate_limit(f'login-ip:{request.client.host if request.client else "private-ingress"}', 60, 900)
    await rate_limit(f'login-email:{hashlib.sha256(data.email.encode()).hexdigest()}', 10, 900)
    user = await db.users.find_one({'email': data.email}, {'_id': 0})
    valid = await run_in_threadpool(bcrypt.checkpw, data.password.encode(), (user['password_hash'] if user else DUMMY_HASH).encode())
    if not valid or not user or not user['active']:
        raise HTTPException(401, 'Email or password is incorrect')
    csrf = secrets.token_urlsafe(32)
    session = {'id': str(uuid.uuid4()), 'auth_version': user.get('auth_version', 0), 'user_id': user['id'], 'csrf_hash': hashlib.sha256(csrf.encode()).hexdigest(), 'version': 1, 'expires_at': datetime.now(timezone.utc) + timedelta(days=7)}
    await db.sessions.insert_one(dict(session))
    set_tokens(response, user['id'], session, csrf)
    return user_out(user)


@router.get('/me', response_model=UserOut)
async def me(user=Depends(current_user)):
    return user_out(user)


@router.post('/refresh', response_model=UserOut)
async def refresh(request: Request, response: Response):
    _, session = await token_session(request, 'refresh')
    check_csrf(request, session)
    user = await db.users.find_one({'id': session['user_id'], 'active': True}, {'_id': 0, 'password_hash': 0})
    if not user or session.get('auth_version', 0) != user.get('auth_version', 0):
        raise HTTPException(401, 'Your account or session is unavailable')
    await rate_limit(f'refresh:{user["id"]}', 30)
    updated = await db.sessions.find_one_and_update({'id': session['id'], 'version': session['version']}, {'$inc': {'version': 1}}, return_document=ReturnDocument.AFTER, projection={'_id': 0})
    if not updated:
        raise HTTPException(401, 'Session already renewed. Please sign in again.')
    set_tokens(response, user['id'], updated)
    return user_out(user)


@router.post('/logout')
async def logout(request: Request, response: Response, user=Depends(current_user)):
    await db.sessions.delete_one({'id': request.state.session['id']})
    for key in ('access_token', 'refresh_token', 'csrf_token'):
        response.delete_cookie(key, path='/' if key == 'csrf_token' else '/api', secure=True, httponly=key != 'csrf_token', samesite='none')
    return {'ok': True}


@router.get('/users')
async def users(page: int = Query(1, ge=1, le=100000), page_size: int = Query(25, ge=1, le=100), status: str = Query('all', pattern='^(all|active|disabled)$'), user=Depends(admin_user)):
    filtered = [] if status == 'all' else [{'$match': {'active': status == 'active'}}]
    result = (await db.users.aggregate([{'$sort': {'created_at': 1, 'id': 1}}, {'$facet': {
        'items': [*filtered, {'$skip': (page-1)*page_size}, {'$limit': page_size}, {'$project': {'_id': 0, 'password_hash': 0}}],
        'count': [*filtered, {'$count': 'total'}],
        'summary': [{'$group': {'_id': None, 'total': {'$sum': 1}, 'active': {'$sum': {'$cond': ['$active', 1, 0]}}, 'disabled': {'$sum': {'$cond': ['$active', 0, 1]}}}}, {'$project': {'_id': 0}}]
    }}], maxTimeMS=10000).to_list(1))[0]
    total = (result['count'] or [{'total': 0}])[0]['total']
    return {'items': [user_out(doc) for doc in result['items']], 'summary': (result['summary'] or [{}])[0], 'total': total,
            'page': page, 'page_size': page_size, 'pages': max(1, (total+page_size-1)//page_size)}


@router.post('/users', response_model=UserOut, status_code=201)
async def add_user(data: UserIn, user=Depends(admin_user)):
    hashed = await run_in_threadpool(bcrypt.hashpw, data.password.encode(), bcrypt.gensalt())
    doc = {'id': str(uuid.uuid4()), 'name': data.name, 'email': data.email, 'password_hash': hashed.decode(), 'role': 'operator', 'active': True, 'page_access': data.page_access, 'created_at': now_iso()}
    try:
        await db.users.insert_one(dict(doc))
    except DuplicateKeyError:
        raise HTTPException(409, 'An account with this email already exists')
    return user_out(doc)


@router.patch('/users/{user_id}', response_model=UserOut)
async def update_user(user_id: str, data: UserPatch, user=Depends(admin_user)):
    target = await db.users.find_one({'id': user_id}, {'_id': 0, 'password_hash': 0})
    if not target:
        raise HTTPException(404, 'User not found')
    changes = {}
    if data.name is not None:
        changes['name'] = data.name
    if data.email is not None:
        changes['email'] = data.email
    if data.active is not None:
        if target['role'] == 'admin':
            raise HTTPException(409, 'The administrator account cannot be disabled')
        changes['active'] = data.active
    if data.page_access is not None:
        if target['role'] == 'admin':
            raise HTTPException(409, 'Administrator page access cannot be restricted')
        changes['page_access'] = data.page_access
    if not changes:
        raise HTTPException(400, 'No changes were submitted')
    try:
        update = {'$set': changes}
        if data.active is False:
            update['$inc'] = {'auth_version': 1}
        await db.users.update_one({'id': user_id}, update)
    except DuplicateKeyError:
        raise HTTPException(409, 'An account with this email already exists')
    if data.active is False:
        await db.sessions.delete_many({'user_id': user_id})
    return user_out({**target, **changes})


@router.put('/users/{user_id}/password')
async def set_password(user_id: str, data: PasswordIn, user=Depends(admin_user)):
    hashed = await run_in_threadpool(bcrypt.hashpw, data.password.encode(), bcrypt.gensalt())
    result = await db.users.update_one({'id': user_id}, {'$set': {'password_hash': hashed.decode()}, '$inc': {'auth_version': 1}})
    if not result.matched_count:
        raise HTTPException(404, 'User not found')
    await db.sessions.delete_many({'user_id': user_id})
    return {'ok': True}


async def initialize_auth():
    await db.users.create_index('id', unique=True)
    await db.users.create_index('email', unique=True)
    await db.sessions.create_index('id', unique=True)
    await db.sessions.create_index('user_id')
    await db.sessions.create_index('expires_at', expireAfterSeconds=0)
    email = os.environ['ADMIN_EMAIL'].strip().casefold()
    if not await db.users.find_one({'email': email}, {'_id': 1}):
        credentials = UserIn(name='Administrator', email=email, password=os.environ['ADMIN_PASSWORD'], page_access=list(PAGE_ACCESS))
        hashed = await run_in_threadpool(bcrypt.hashpw, credentials.password.encode(), bcrypt.gensalt())
        await db.users.update_one({'email': email}, {'$setOnInsert': {'id': str(uuid.uuid4()), 'email': email, 'name': 'Administrator', 'role': 'admin', 'active': True, 'page_access': list(PAGE_ACCESS), 'password_hash': hashed.decode(), 'created_at': now_iso()}}, upsert=True)
