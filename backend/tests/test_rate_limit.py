import os

import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


def test_rate_limit_returns_429_after_threshold():
    session = requests.Session()
    responses = [session.get(f"{BASE_URL}/api/") for _ in range(181)]
    assert responses[-1].status_code == 429
    assert "Too many requests" in responses[-1].json()["detail"]