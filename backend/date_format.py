import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def app_timezone():
    key = os.environ.get('APP_TIMEZONE', 'Asia/Calcutta')
    try:
        return ZoneInfo(key)
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=5, minutes=30))


def display_date(value, include_time=False):
    if not value:
        return ''
    try:
        date = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if include_time and date.tzinfo:
            date = date.astimezone(app_timezone())
        return date.strftime('%d-%m-%Y %H:%M:%S' if include_time else '%d-%m-%Y')
    except ValueError:
        return ''
