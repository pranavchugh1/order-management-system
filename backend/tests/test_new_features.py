"""Tests for iteration 5 features: exports, bulk blocks, mark-sent challan, /api/firms, /api/challans."""
import os
import uuid
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = "admin@adityaprints.local"
ADMIN_PASSWORD = "x1GFPpPGQSzeBo0NChZax6RJ"
FIRMS = ("Dhan Guru Nanak Synthetics", "Alveera Fashion Private Limited")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Origin": BASE_URL, "Referer": BASE_URL + "/"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    csrf = s.cookies.get("csrf_token")
    assert csrf, "no csrf cookie"
    s.headers.update({"X-CSRF-Token": csrf})
    return s


@pytest.fixture(scope="module")
def setup(api):
    suffix = uuid.uuid4().hex[:8]
    p = api.post(f"{BASE_URL}/api/parties", json={"name": f"TEST Party {suffix}"}).json()
    c = api.post(f"{BASE_URL}/api/catalogues", json={"name": f"TEST Cat {suffix}"}).json()
    v = api.post(f"{BASE_URL}/api/catalogues/{c['id']}/volumes",
                 json={"name": "vol1", "pieces_per_set": 6}).json()
    return p, c, v


def make_order(api, setup, sets=1):
    p, c, v = setup
    payload = {
        "party_id": p["id"], "party_name": p["name"],
        "parcels": [{"target": v["pieces_per_set"] * sets, "compositions": [{
            "catalogue_id": c["id"], "volume_id": v["id"],
            "catalogue_name": c["name"], "volume_name": v["name"],
            "pieces_per_set": v["pieces_per_set"], "sets": sets}]}]
    }
    r = api.post(f"{BASE_URL}/api/orders", json=payload)
    assert r.status_code in (200, 201), r.text
    return r.json()


# --- /api/firms ---
def test_firms_endpoint(api):
    r = api.get(f"{BASE_URL}/api/firms")
    assert r.status_code == 200
    data = r.json()
    assert data["firms"] == list(FIRMS)


# --- Mark sent requires challan+firm ---
def test_mark_sent_missing_fields_rejected(api, setup):
    o = make_order(api, setup)
    r = api.patch(f"{BASE_URL}/api/orders/{o['id']}/parcels/0", json={"version": o["version"]})
    assert r.status_code == 422

    r = api.patch(f"{BASE_URL}/api/orders/{o['id']}/parcels/0",
                  json={"version": o["version"], "challan_number": "CH-1"})
    assert r.status_code == 422

    r = api.patch(f"{BASE_URL}/api/orders/{o['id']}/parcels/0",
                  json={"version": o["version"], "challan_number": "CH-1", "firm": "Unknown Firm Ltd"})
    assert r.status_code == 422


def test_mark_sent_success_and_persistence(api, setup):
    o = make_order(api, setup, sets=2)
    r = api.patch(f"{BASE_URL}/api/orders/{o['id']}/parcels/0",
                  json={"version": o["version"], "challan_number": "TEST-CH-100", "firm": FIRMS[0]})
    assert r.status_code == 200, r.text
    parcel = r.json()["parcels"][0]
    assert parcel["status"] == "Parcel Sent"
    assert parcel["challan_number"] == "TEST-CH-100"
    assert parcel["firm"] == FIRMS[0]
    assert parcel["sent_at"]

    # verify via GET
    g = api.get(f"{BASE_URL}/api/orders/{o['id']}").json()
    assert g["parcels"][0]["challan_number"] == "TEST-CH-100"
    assert g["parcels"][0]["firm"] == FIRMS[0]


# --- /api/challans ---
def test_challans_listing_and_filters(api, setup):
    o = make_order(api, setup, sets=3)
    api.patch(f"{BASE_URL}/api/orders/{o['id']}/parcels/0",
              json={"version": o["version"], "challan_number": "TEST-CH-FILTER", "firm": FIRMS[1]})

    # unfiltered
    r = api.get(f"{BASE_URL}/api/challans")
    assert r.status_code == 200
    body = r.json()
    assert "rows" in body and "firms" in body
    assert body["firms"] == list(FIRMS)
    match = [x for x in body["rows"] if x.get("challan_number") == "TEST-CH-FILTER"]
    assert match and match[0]["firm"] == FIRMS[1]
    row = match[0]
    for k in ("order_number", "party_name", "sent_at", "target", "compositions"):
        assert k in row

    # firm filter
    r2 = api.get(f"{BASE_URL}/api/challans", params={"firm": FIRMS[1]})
    assert r2.status_code == 200
    assert all(x["firm"] == FIRMS[1] for x in r2.json()["rows"])

    # bad firm
    r3 = api.get(f"{BASE_URL}/api/challans", params={"firm": "Bogus"})
    assert r3.status_code == 400

    # search
    r4 = api.get(f"{BASE_URL}/api/challans", params={"q": "TEST-CH-FIL"})
    assert r4.status_code == 200
    assert any(x.get("challan_number") == "TEST-CH-FILTER" for x in r4.json()["rows"])


# --- Exports ---
@pytest.mark.parametrize("endpoint", [
    "/api/exports/pending-requirements.xlsx",
    "/api/exports/pending-orders.xlsx",
    "/api/exports/completed-orders.xlsx",
])
def test_export_endpoints(api, setup, endpoint):
    # ensure at least one pending & one completed exists
    make_order(api, setup)
    r = api.get(f"{BASE_URL}{endpoint}")
    assert r.status_code == 200, r.text
    ct = r.headers.get("content-type", "")
    assert "spreadsheetml" in ct or "xlsx" in ct, ct
    assert r.content[:2] == b"PK"  # xlsx = zip


def test_pending_alias(api):
    r = api.get(f"{BASE_URL}/api/exports/pending.xlsx")
    assert r.status_code == 200
    assert r.content[:2] == b"PK"


# --- Bulk preview block UI ---
def test_bulk_preview_blocks(api, setup):
    p, c, v = setup
    payload = {"blocks": [
        {"party_id": p["id"], "text": f"{c['name']} {v['name']} 1 parcel", "remarks": "TEST remarks"},
        {"party_id": p["id"], "text": "BogusCat BogusVol 1 parcel", "remarks": ""},
    ]}
    r = api.post(f"{BASE_URL}/api/bulk/preview", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["orders"]) == 1  # only the valid block
    assert body["orders"][0]["party_id"] == p["id"]
    assert len(body["errors"]) >= 1  # malformed line surfaced
    assert any(e.get("block") == 2 for e in body["errors"])


def test_bulk_commit_creates_orders(api, setup):
    p, c, v = setup
    prev = api.post(f"{BASE_URL}/api/bulk/preview", json={
        "blocks": [{"party_id": p["id"], "text": f"{c['name']} {v['name']} 2 parcels", "remarks": ""}]}).json()
    assert prev["orders"], prev
    orders = prev["orders"]
    for o in orders:
        o["date"] = None
    commit = api.post(f"{BASE_URL}/api/bulk/commit",
                      json={"request_id": str(uuid.uuid4()), "orders": orders})
    assert commit.status_code == 200, commit.text
    ids = [x["id"] for x in commit.json()["orders"]]
    for oid in ids:
        g = api.get(f"{BASE_URL}/api/orders/{oid}")
        assert g.status_code == 200
