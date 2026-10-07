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
def records(api):
    suffix = uuid.uuid4().hex[:8]
    party = api.post(f"{BASE_URL}/api/parties", json={"name": f"TEST Hard Party {suffix}"}).json()
    catalogue = api.post(f"{BASE_URL}/api/catalogues", json={"name": f"TEST Hard Catalogue {suffix}"}).json()
    volume = api.post(
        f"{BASE_URL}/api/catalogues/{catalogue['id']}/volumes",
        json={"name": f"TEST Hard Volume {suffix}", "pieces_per_set": 6},
    ).json()
    return party, catalogue, volume


def order_payload(records):
    party, catalogue, volume = records
    return {
        "party_id": party["id"],
        "party_name": party["name"],
        "parcels": [{"target": 6, "compositions": [{
            "catalogue_id": catalogue["id"], "volume_id": volume["id"],
            "catalogue_name": catalogue["name"], "volume_name": volume["name"],
            "pieces_per_set": 6, "sets": 1,
        }]}],
    }


def test_security_headers_and_cors_policy(api):
    response = api.get(f"{BASE_URL}/api/")
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    cors = api.options(f"{BASE_URL}/api/", headers={"Origin": "https://example.test", "Access-Control-Request-Method": "GET"})
    assert cors.headers.get("access-control-allow-credentials") != "true"


def test_duplicate_names_are_rejected(api, records):
    party, catalogue, volume = records
    assert api.post(f"{BASE_URL}/api/parties", json={"name": party["name"].upper()}).status_code == 409
    assert api.post(f"{BASE_URL}/api/catalogues", json={"name": catalogue["name"]}).status_code == 409
    assert api.post(f"{BASE_URL}/api/catalogues/{catalogue['id']}/volumes", json={"name": volume["name"], "pieces_per_set": 6}).status_code == 409


def test_master_edit_persists(api, records):
    party, catalogue, volume = records
    new_party = f"{party['name']} edited"
    new_volume = f"{volume['name']} edited"
    assert api.put(f"{BASE_URL}/api/parties/{party['id']}", json={"name": new_party}).status_code == 200
    assert api.put(f"{BASE_URL}/api/catalogues/{catalogue['id']}/volumes/{volume['id']}", json={"name": new_volume, "pieces_per_set": 7}).status_code == 200
    party_list = api.get(f"{BASE_URL}/api/parties").json()
    cat = next(x for x in api.get(f"{BASE_URL}/api/catalogues").json() if x["id"] == catalogue["id"])
    assert next(x for x in party_list if x["id"] == party["id"])["name"] == new_party
    assert cat["volumes"][0]["pieces_per_set"] == 7


def test_unchanged_volume_edit_is_not_reported_missing(api, records):
    suffix = uuid.uuid4().hex[:8]
    catalogue = api.post(f"{BASE_URL}/api/catalogues", json={"name": f"TEST Same Catalogue {suffix}"}).json()
    volume = api.post(
        f"{BASE_URL}/api/catalogues/{catalogue['id']}/volumes",
        json={"name": f"TEST Same Volume {suffix}", "pieces_per_set": 9},
    ).json()
    response = api.put(
        f"{BASE_URL}/api/catalogues/{catalogue['id']}/volumes/{volume['id']}",
        json={"name": volume["name"], "pieces_per_set": volume["pieces_per_set"]},
    )
    assert response.status_code == 200
    assert response.json()["id"] == volume["id"]


def test_referenced_master_deletes_return_conflict_and_preserve_data(api, records):
    party, catalogue, volume = records
    created = api.post(f"{BASE_URL}/api/orders", json=order_payload(records))
    assert created.status_code == 200
    assert api.delete(f"{BASE_URL}/api/parties/{party['id']}").status_code == 409
    assert api.delete(f"{BASE_URL}/api/catalogues/{catalogue['id']}").status_code == 409
    assert api.delete(f"{BASE_URL}/api/catalogues/{catalogue['id']}/volumes/{volume['id']}").status_code == 409
    assert any(x["id"] == party["id"] for x in api.get(f"{BASE_URL}/api/parties").json())
    assert any(x["id"] == catalogue["id"] for x in api.get(f"{BASE_URL}/api/catalogues").json())


def test_invalid_order_is_safe_validation_error(api, records):
    payload = order_payload(records)
    payload["unexpected"] = "do not accept"
    response = api.post(f"{BASE_URL}/api/orders", json=payload)
    assert response.status_code == 422
    assert response.json() == {"detail": "The submitted data is invalid."}