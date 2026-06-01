import pytest
from fastapi.testclient import TestClient


def _create_carrier(client: TestClient, name: str = "Fast Transport Sp. z o.o.", email: str = None) -> dict:
    if email is None:
        import random, string
        email = "carrier_" + "".join(random.choices(string.ascii_lowercase, k=5)) + "@test.pl"
    payload = {
        "name": name,
        "email": email,
        "phone": "+48 600 100 200",
        "city": "Poznan",
        "country": "PL",
        "equipment_types": "Curtainsider, Box",
        "max_weight_kg": 24000,
        "rating": 4.5,
    }
    resp = client.post("/api/carriers/", json=payload)
    assert resp.status_code == 201
    return resp.json()


def test_list_carriers_empty(client: TestClient):
    resp = client.get("/api/carriers/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_create_carrier(client: TestClient):
    data = _create_carrier(client)
    assert data["id"] is not None
    assert data["max_weight_kg"] == 24000


def test_get_carrier(client: TestClient):
    data = _create_carrier(client)
    resp = client.get(f"/api/carriers/{data['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == data["id"]


def test_get_carrier_not_found(client: TestClient):
    resp = client.get("/api/carriers/999999")
    assert resp.status_code == 404


def test_update_carrier(client: TestClient):
    data = _create_carrier(client)
    resp = client.patch(f"/api/carriers/{data['id']}", json={"rating": 3.5, "is_active": False})
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["rating"] == 3.5
    assert updated["is_active"] is False


def test_delete_carrier(client: TestClient):
    data = _create_carrier(client)
    resp = client.delete(f"/api/carriers/{data['id']}")
    assert resp.status_code == 204
    assert client.get(f"/api/carriers/{data['id']}").status_code == 404
