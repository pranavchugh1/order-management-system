import os
import uuid

import pytest
import requests
from dotenv import load_dotenv


load_dotenv("/app/frontend/.env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


@pytest.fixture(scope="module")
def api():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def setup_data(api):
    suffix = uuid.uuid4().hex[:8]
    party = api.post(f"{BASE_URL}/api/parties", json={"name": f"TEST Party {suffix}"})
    catalogue = api.post(f"{BASE_URL}/api/catalogues", json={"name": f"TEST Catalogue {suffix}"})
    assert party.status_code == 200 and catalogue.status_code == 200
    volume = api.post(
        f"{BASE_URL}/api/catalogues/{catalogue.json()['id']}/volumes",
        json={"name": "TEST Volume", "pieces_per_set": 6},
    )
    assert volume.status_code == 200
    return party.json(), catalogue.json(), volume.json()


def composition(data, sets):
    party, catalogue, volume = data
    return {
        "catalogue_id": catalogue["id"],
        "volume_id": volume["id"],
        "catalogue_name": catalogue["name"],
        "volume_name": volume["name"],
        "pieces_per_set": 6,
        "sets": sets,
    }


def test_master_data_persists(api, setup_data):
    party, catalogue, volume = setup_data
    assert any(x["id"] == party["id"] for x in api.get(f"{BASE_URL}/api/parties").json())
    fetched = next(x for x in api.get(f"{BASE_URL}/api/catalogues").json() if x["id"] == catalogue["id"])
    assert fetched["volumes"][0]["pieces_per_set"] == volume["pieces_per_set"]


def test_incomplete_parcel_is_rejected(api, setup_data):
    party, _, _ = setup_data
    response = api.post(
        f"{BASE_URL}/api/orders",
        json={"party_id": party["id"], "party_name": party["name"], "parcels": [{"target": 72, "compositions": []}]},
    )
    assert response.status_code == 400
    assert "exactly 72" in response.json()["detail"]


def test_order_crud_sent_and_pending_aggregation(api, setup_data):
    party, _, _ = setup_data
    payload = {
        "party_id": party["id"],
        "party_name": party["name"],
        "remarks": "TEST remark",
        "parcels": [
            {"target": 72, "compositions": [composition(setup_data, 12)]},
            {"target": 76, "compositions": [composition(setup_data, 10), {**composition(setup_data, 1), "pieces_per_set": 16}]},
        ],
    }
    created = api.post(f"{BASE_URL}/api/orders", json=payload)
    assert created.status_code == 200
    order = created.json()
    assert order["order_number"].startswith("ORD-") and order["total_pieces"] == 148
    fetched = api.get(f"{BASE_URL}/api/orders/{order['id']}")
    assert fetched.status_code == 200 and fetched.json()["remarks"] == "TEST remark"
    sent = api.patch(f"{BASE_URL}/api/orders/{order['id']}/parcels/0", json={})
    assert sent.status_code == 200 and sent.json()["status"] == "Partially Pending"
    pending = api.get(f"{BASE_URL}/api/pending-requirements")
    assert pending.status_code == 200
    rows = pending.json()["rows"]
    assert any(r["volume_name"] == "TEST Volume" and r["sets"] >= 11 for r in rows)
    final = api.patch(f"{BASE_URL}/api/orders/{order['id']}/parcels/1", json={})
    assert final.status_code == 200 and final.json()["status"] == "Parcel Sent"


def test_parcel_patch_rejects_negative_index_without_mutation(api, setup_data):
    party, _, _ = setup_data
    payload = {
        "party_id": party["id"],
        "party_name": party["name"],
        "parcels": [
            {"target": 72, "compositions": [composition(setup_data, 12)]},
            {"target": 6, "compositions": [composition(setup_data, 1)]},
        ],
    }
    created = api.post(f"{BASE_URL}/api/orders", json=payload)
    assert created.status_code == 200
    order_id = created.json()["id"]

    rejected = api.patch(f"{BASE_URL}/api/orders/{order_id}/parcels/-1", json={})
    assert rejected.status_code == 404
    fetched = api.get(f"{BASE_URL}/api/orders/{order_id}")
    assert fetched.status_code == 200
    assert all(parcel["status"] == "Pending" for parcel in fetched.json()["parcels"])


def test_parcel_patch_rejects_arbitrary_status_without_mutation(api, setup_data):
    party, _, _ = setup_data
    payload = {
        "party_id": party["id"],
        "party_name": party["name"],
        "parcels": [{"target": 6, "compositions": [composition(setup_data, 1)]}],
    }
    created = api.post(f"{BASE_URL}/api/orders", json=payload)
    assert created.status_code == 200
    order_id = created.json()["id"]

    rejected = api.patch(
        f"{BASE_URL}/api/orders/{order_id}/parcels/0",
        json={"status": "Delivered"},
    )
    assert rejected.status_code == 422
    fetched = api.get(f"{BASE_URL}/api/orders/{order_id}")
    assert fetched.status_code == 200
    assert fetched.json()["parcels"][0]["status"] == "Pending"


def test_parcel_sent_transition_still_works(api, setup_data):
    party, _, _ = setup_data
    payload = {
        "party_id": party["id"],
        "party_name": party["name"],
        "parcels": [{"target": 6, "compositions": [composition(setup_data, 1)]}],
    }
    created = api.post(f"{BASE_URL}/api/orders", json=payload)
    assert created.status_code == 200
    order_id = created.json()["id"]

    sent = api.patch(f"{BASE_URL}/api/orders/{order_id}/parcels/0", json={})
    assert sent.status_code == 200
    assert sent.json()["parcels"][0]["status"] == "Parcel Sent"
    assert sent.json()["status"] == "Parcel Sent"
