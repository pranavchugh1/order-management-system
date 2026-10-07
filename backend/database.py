import os
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from date_format import app_timezone

load_dotenv(Path(__file__).resolve().parent.parent / '.env')
client = AsyncIOMotorClient(os.environ['MONGO_URL'], maxPoolSize=50, minPoolSize=5, serverSelectionTimeoutMS=5000)
db = client[os.environ['DB_NAME']]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def business_timezone():
    return app_timezone()


def today_iso():
    return datetime.now(business_timezone()).date().isoformat()


def clean(doc):
    return {k: v for k, v in doc.items() if k != '_id'} if doc else None


def normalized(value):
    return ' '.join(value.strip().split())
