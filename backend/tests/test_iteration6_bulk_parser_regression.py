"""Iteration 6 regression: parser/allocation + authenticated bulk/order/challan flows."""
import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from statistics import median

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = os.environ["ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]
MONGO_URL = os.environ["MONGO_URL"].strip('"\'')
DB_NAME = os.environ["DB_NAME"].strip('"\'')

sys.path.insert(0, "/app/backend")
from bulk_orders import Block, parse_blocks  # noqa: E402
from parcel_allocation import allocate_sets  # noqa: E402
from parcel_parser import catalogue_index, parse_line, parse_parcels, resolve  # noqa: E402


@pytest.fixture(scope="module")
def api_state():
    """Authenticated session + created test fixtures tracker."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json", "Origin": BASE_URL, "Referer": BASE_URL + "/"})
    login = session.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert login.status_code == 200, f"login failed: {login.status_code} {login.text}"
    csrf = session.cookies.get("csrf_token")
    assert csrf, "csrf_token cookie missing"
    session.headers.update({"X-CSRF-Token": csrf})
    me = session.get(f"{BASE_URL}/api/auth/me")
    assert me.status_code == 200
    user_id = me.json()["id"]

    state = {
        "session": session,
        "user_id": user_id,
        "party_ids": [],
        "catalogue_ids": [],
        "order_ids": [],
        "batch_keys": [],
    }
    yield state

    mongo = MongoClient(MONGO_URL)
    db = mongo[DB_NAME]
    if state["order_ids"]:
        db.orders.delete_many({"id": {"$in": list(set(state["order_ids"]))}})
    if state["batch_keys"]:
        db.bulk_batches.delete_many({"key": {"$in": list(set(state["batch_keys"]))}})
    if state["party_ids"]:
        db.parties.delete_many({"id": {"$in": list(set(state["party_ids"]))}})
    if state["catalogue_ids"]:
        db.catalogues.delete_many({"id": {"$in": list(set(state["catalogue_ids"]))}})
    mongo.close()


@pytest.fixture(scope="module")
def parser_catalogues():
    """Isolated parser fixtures with aliases and separator-containing names."""
    return [
        {"id": "cat-saya", "name": "Saya", "volumes": [{"id": "vol-saya-1", "name": "1", "pieces_per_set": 6}, {"id": "vol-saya-2", "name": "vol 2", "pieces_per_set": 10}]},
        {"id": "cat-siya", "name": "Siya", "volumes": [{"id": "vol-siya-2", "name": "2", "pieces_per_set": 6}, {"id": "vol-siya-1", "name": "1", "pieces_per_set": 10}]},
        {"id": "cat-quoted", "name": "A and B", "volumes": [{"id": "vol-quoted", "name": "V+1", "pieces_per_set": 6}]},
    ]


def _create_party(api_state, name):
    session = api_state["session"]
    r = session.post(f"{BASE_URL}/api/parties", json={"name": name})
    assert r.status_code == 200, r.text
    party = r.json()
    api_state["party_ids"].append(party["id"])
    return party


def _create_catalogue_with_volumes(api_state, name, volumes):
    session = api_state["session"]
    c = session.post(f"{BASE_URL}/api/catalogues", json={"name": name})
    assert c.status_code == 200, c.text
    cat = c.json()
    api_state["catalogue_ids"].append(cat["id"])
    created_volumes = []
    for vol_name, pps in volumes:
        v = session.post(f"{BASE_URL}/api/catalogues/{cat['id']}/volumes", json={"name": vol_name, "pieces_per_set": pps})
        assert v.status_code == 200, v.text
        created_volumes.append(v.json())
    cat["volumes"] = created_volumes
    return cat


def _commit_and_track(api_state, request_id, orders):
    payload = {"request_id": str(request_id), "orders": orders}
    session = api_state["session"]
    r = session.post(f"{BASE_URL}/api/bulk/commit", json=payload)
    assert r.status_code == 200, r.text
    batch_key = f"{api_state['user_id']}:{request_id}"
    api_state["batch_keys"].append(batch_key)
    api_state["order_ids"].extend([x["id"] for x in r.json()["orders"]])
    return r.json()


def test_auth_cookies_and_csrf_contract(api_state):
    """Auth contract: HttpOnly token cookies + readable csrf + explicit origin checks."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json", "Origin": BASE_URL, "Referer": BASE_URL + "/"})
    r = session.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200
    set_cookie = ",".join(r.raw.headers.get_all("Set-Cookie"))
    assert "access_token=" in set_cookie and "HttpOnly" in set_cookie
    assert "refresh_token=" in set_cookie and "HttpOnly" in set_cookie
    assert "csrf_token=" in set_cookie
    assert session.cookies.get("csrf_token")

    bad_origin = requests.Session()
    bad_origin.headers.update({"Content-Type": "application/json", "Origin": "https://not-allowed.example"})
    blocked = bad_origin.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert blocked.status_code == 403


def test_seed_admin_hash_uses_bcrypt_prefix():
    """Auth storage check: admin password hash uses bcrypt $2b$ format."""
    mongo = MongoClient(MONGO_URL)
    db = mongo[DB_NAME]
    admin = db.users.find_one({"email": ADMIN_EMAIL.strip().casefold()}, {"_id": 0, "password_hash": 1})
    mongo.close()
    assert admin and admin["password_hash"].startswith("$2b$")


def test_parser_three_separators_and_default_count(parser_catalogues):
    """Parser accepts &, +, and separators and default parcel count=1."""
    index = catalogue_index(parser_catalogues)
    for expression in ("Saya 1 & Siya 2", "Saya 1+ Siya 2", "Saya 1 and Siya 2 1 parcel"):
        parcel, count = parse_line(expression, index)
        assert count == 1
        assert parcel["target"] == 72
        assert [c["sets"] for c in parcel["compositions"]] == [6, 6]


def test_parser_mixed_sizes_targets_and_reversed_order(parser_catalogues):
    """Parser computes 2x6=>6 sets each, 3x6=>4 each, 10+6@76 and reverse."""
    index = catalogue_index(parser_catalogues)

    two, _ = parse_line("Saya 1 + Siya 2", index)
    assert [c["sets"] for c in two["compositions"]] == [6, 6]

    parser_catalogues_three = parser_catalogues + [{"id": "cat-third", "name": "Miya", "volumes": [{"id": "vol-third", "name": "3", "pieces_per_set": 6}]}]
    three_index = catalogue_index(parser_catalogues_three)
    three, _ = parse_line("Saya 1 + Siya 2 + Miya 3", three_index)
    assert [c["sets"] for c in three["compositions"]] == [4, 4, 4]

    mix, _ = parse_line("Saya vol 2 + Siya 2 @ 76 pcs", index)
    assert [c["sets"] for c in mix["compositions"]] == [4, 6]

    mix_rev, _ = parse_line("Siya 2 + Saya vol 2 @ 76 pcs", index)
    assert [c["sets"] for c in mix_rev["compositions"]] == [6, 4]

    all_ten, _ = parse_line("Saya vol 2 + Siya 1", index)
    assert all_ten["target"] == 80


def test_parser_aliases_and_quoted_names(parser_catalogues):
    """Aliases vol1/volume1 and quoted dropdown syntax resolve correctly."""
    index = catalogue_index(parser_catalogues)
    assert resolve("Saya 1", index)[1]["id"] == "vol-saya-1"
    assert resolve("Saya vol1", index)[1]["id"] == "vol-saya-1"
    assert resolve("Saya volume1", index)[1]["id"] == "vol-saya-1"
    assert resolve("Saya vol 2", index)[1]["id"] == "vol-saya-2"

    parcel, count = parse_line('"A and B | V+1" 1 parcel', index)
    assert count == 1
    assert len(parcel["compositions"]) == 1
    assert parcel["compositions"][0]["catalogue_name"] == "A and B"


def test_parser_validation_and_limits(parser_catalogues):
    """Parser rejects unknown/duplicate/malformed/oversized inputs and >100 parcels."""
    index = catalogue_index(parser_catalogues)

    with pytest.raises(ValueError):
        parse_line("Unknown 1", index)
    with pytest.raises(ValueError):
        parse_line("Saya 1 + Saya 1", index)
    with pytest.raises(ValueError):
        parse_line("Saya 1 0 parcels", index)
    with pytest.raises(ValueError):
        parse_line("Saya 1 @ 1000001 pcs", index)
    with pytest.raises(ValueError):
        parse_line("Saya 1 + Siya 2 @ 70 pcs", index)

    _, errors = parse_parcels("Saya 1 101 parcels", index)
    assert errors and "between 1 and 100" in errors[0]["message"]


def test_allocation_integer_exact_and_large_target_performance():
    """Allocation outputs positive integer sets, exact totals, and bounded runtime."""
    result = allocate_sets((6, 8, 10), 96)
    assert all(isinstance(x, int) and x > 0 for x in result)
    assert sum(s * p for s, p in zip(result, (6, 8, 10))) == 96

    started = time.perf_counter()
    large = allocate_sets((6, 10), 500000)
    elapsed = time.perf_counter() - started
    assert sum(s * p for s, p in zip(large, (6, 10))) == 500000
    assert elapsed < 1.5


def test_parse_blocks_batch_and_composition_caps(parser_catalogues):
    """Bulk parse enforces batch 500 parcels and 2000 composition row limits."""
    parties = [{"id": "p1", "name": "P1"}]
    cat5 = [
        {"id": "cat1", "name": "C1", "volumes": [{"id": "v1", "name": "1", "pieces_per_set": 6}]},
        {"id": "cat2", "name": "C2", "volumes": [{"id": "v2", "name": "1", "pieces_per_set": 6}]},
        {"id": "cat3", "name": "C3", "volumes": [{"id": "v3", "name": "1", "pieces_per_set": 6}]},
        {"id": "cat4", "name": "C4", "volumes": [{"id": "v4", "name": "1", "pieces_per_set": 6}]},
        {"id": "cat5", "name": "C5", "volumes": [{"id": "v5", "name": "1", "pieces_per_set": 6}]},
    ]

    over_500 = [Block(party_id="p1", text="C1 1 100 parcels", remarks="") for _ in range(6)]
    res500 = parse_blocks(over_500, parties, cat5)
    assert any("500 parcels" in e["message"] for e in res500["errors"])

    row_heavy_text = "C1 1 + C2 1 + C3 1 + C4 1 + C5 1 50 parcels @ 150 pcs"
    over_rows = [Block(party_id="p1", text=row_heavy_text, remarks="") for _ in range(10)]
    res2000 = parse_blocks(over_rows, parties, cat5)
    assert any("2,000 composition" in e["message"] for e in res2000["errors"])


def test_bulk_preview_no_db_write_and_commit_idempotent(api_state):
    """Preview does not write orders; commit persists once and replay is idempotent."""
    session = api_state["session"]
    suffix = uuid.uuid4().hex[:8]
    party = _create_party(api_state, f"TEST Party {suffix}")
    cat_a = _create_catalogue_with_volumes(api_state, f"TEST Cat A {suffix}", [("1", 10)])
    cat_b = _create_catalogue_with_volumes(api_state, f"TEST Cat B {suffix}", [("2", 6)])

    mongo = MongoClient(MONGO_URL)
    db = mongo[DB_NAME]
    before = db.orders.count_documents({"party_id": party["id"]})

    preview_payload = {
        "blocks": [
            {
                "party_id": party["id"],
                "text": f'"{cat_a["name"]} | {cat_a["volumes"][0]["name"]}" + "{cat_b["name"]} | {cat_b["volumes"][0]["name"]}" @ 76 pcs\n"{cat_a["name"]} | {cat_a["volumes"][0]["name"]}" + "{cat_b["name"]} | {cat_b["volumes"][0]["name"]}" 1 parcel',
                "remarks": "iteration6",
            }
        ]
    }
    preview = session.post(f"{BASE_URL}/api/bulk/preview", json=preview_payload)
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["errors"] == []
    assert len(body["orders"]) == 1
    assert len(body["orders"][0]["parcels"]) == 2

    after_preview = db.orders.count_documents({"party_id": party["id"]})
    assert after_preview == before

    request_id = uuid.uuid4()
    for order in body["orders"]:
        order["date"] = order.get("date") or "2026-02-20"
    first = _commit_and_track(api_state, request_id, body["orders"])
    second = _commit_and_track(api_state, request_id, body["orders"])
    assert first["replayed"] is False
    assert second["replayed"] is True
    assert [o["id"] for o in first["orders"]] == [o["id"] for o in second["orders"]]

    saved = session.get(f"{BASE_URL}/api/orders/{first['orders'][0]['id']}")
    assert saved.status_code == 200
    order = saved.json()
    assert len(order["parcels"]) == 2
    totals = [sum(c["pieces_per_set"] * c["sets"] for c in p["compositions"]) for p in order["parcels"]]
    assert totals == [76, 72]

    pending = session.get(f"{BASE_URL}/api/pending-requirements")
    assert pending.status_code == 200
    p_rows = pending.json()["rows"]
    names = {(r["catalogue_name"], r["volume_name"]) for r in p_rows}
    assert (cat_a["name"], cat_a["volumes"][0]["name"]) in names
    assert (cat_b["name"], cat_b["volumes"][0]["name"]) in names
    mongo.close()


def test_bulk_preview_concurrency_and_500_parcels_performance(api_state):
    """Bulk preview handles concurrent queries and 500-parcel payload in bounded time."""
    session = api_state["session"]
    suffix = uuid.uuid4().hex[:8]
    party = _create_party(api_state, f"TEST Party Perf {suffix}")
    cat = _create_catalogue_with_volumes(api_state, f"TEST Cat Perf {suffix}", [("1", 6)])

    block_text = f'"{cat["name"]} | {cat["volumes"][0]["name"]}" 100 parcels'
    payload = {"blocks": [{"party_id": party["id"], "text": block_text, "remarks": ""} for _ in range(5)]}

    started = time.perf_counter()
    single = session.post(f"{BASE_URL}/api/bulk/preview", json=payload)
    single_elapsed = time.perf_counter() - started
    assert single.status_code == 200, single.text
    assert single.json()["summary"]["parcels"] == 500

    def worker():
        return session.post(f"{BASE_URL}/api/bulk/preview", json=payload).status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(lambda _: worker(), range(4)))
    assert statuses == [200, 200, 200, 200]
    assert single_elapsed < 8.0


def test_orders_challans_median_response_and_challan_page_size(api_state):
    """Orders/challans median latency sampled; challans page_size=1 paging stays correct."""
    session = api_state["session"]
    suffix = uuid.uuid4().hex[:8]
    party = _create_party(api_state, f"TEST Party Med {suffix}")
    cat = _create_catalogue_with_volumes(api_state, f"TEST Cat Med {suffix}", [("1", 6)])

    preview_payload = {"blocks": [{"party_id": party["id"], "text": f'"{cat["name"]} | {cat["volumes"][0]["name"]}" 2 parcels', "remarks": "med"}]}
    preview = session.post(f"{BASE_URL}/api/bulk/preview", json=preview_payload)
    assert preview.status_code == 200
    orders = preview.json()["orders"]
    for o in orders:
        o["date"] = "2026-02-21"
    committed = _commit_and_track(api_state, uuid.uuid4(), orders)
    order_id = committed["orders"][0]["id"]

    order_doc = session.get(f"{BASE_URL}/api/orders/{order_id}").json()
    send = session.patch(
        f"{BASE_URL}/api/orders/{order_id}/parcels/0",
        json={"version": order_doc["version"], "challan_number": f"TEST-CH-{suffix}", "firm": "Alveera Fashion Private Limited"},
    )
    assert send.status_code == 200, send.text

    orders_times = []
    challans_times = []
    for _ in range(5):
        t0 = time.perf_counter()
        ro = session.get(f"{BASE_URL}/api/orders", params={"status": "all", "page": 1})
        orders_times.append(time.perf_counter() - t0)
        assert ro.status_code == 200

        t1 = time.perf_counter()
        rc = session.get(f"{BASE_URL}/api/challans", params={"page": 1, "page_size": 1, "q": f"TEST-CH-{suffix}"})
        challans_times.append(time.perf_counter() - t1)
        assert rc.status_code == 200
        body = rc.json()
        assert body["page_size"] == 1
        assert body["rows"]
        row = body["rows"][0]
        assert row["challan_number"].startswith("TEST-CH-")
        assert "target" not in row

    assert median(orders_times) < 2.0
    assert median(challans_times) < 2.0
