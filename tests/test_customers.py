import random
import string
from fastapi.testclient import TestClient


def _rand_email(prefix="customer"):
    return prefix + "_" + "".join(random.choices(string.ascii_lowercase, k=6)) + "@test.pl"


def _create_customer(client: TestClient, name: str = None, email: str = None) -> dict:
    if name is None:
        name = "Test Shipper Sp. z o.o. " + "".join(random.choices(string.ascii_uppercase, k=3))
    payload = {
        "name": name,
        "email": email or _rand_email(),
        "phone": "+48 123 456 789",
        "city": "Warsaw",
        "country": "PL",
        "customer_type": "SHIPPER",
    }
    resp = client.post("/api/customers/", json=payload)
    assert resp.status_code == 201
    return resp.json()


def test_list_customers_empty(client: TestClient):
    resp = client.get("/api/customers/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_create_customer(client: TestClient):
    data = _create_customer(client)
    assert data["name"] is not None
    assert data["id"] is not None
    assert data["customer_type"] == "SHIPPER"


def test_get_customer(client: TestClient):
    data = _create_customer(client)
    resp = client.get(f"/api/customers/{data['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == data["id"]


def test_get_customer_not_found(client: TestClient):
    resp = client.get("/api/customers/999999")
    assert resp.status_code == 404


def test_update_customer(client: TestClient):
    data = _create_customer(client)
    resp = client.patch(f"/api/customers/{data['id']}", json={"city": "Krakow", "phone": "+48 999 888 777"})
    assert resp.status_code == 200
    assert resp.json()["city"] == "Krakow"


def test_search_customers(client: TestClient):
    unique = "UniqueSearchName" + "".join(random.choices(string.ascii_uppercase, k=4))
    _create_customer(client, name=unique)
    resp = client.get(f"/api/customers/?search={unique}")
    assert resp.status_code == 200
    results = resp.json()
    assert any(unique in c["name"] for c in results)


def test_delete_customer(client: TestClient):
    data = _create_customer(client)
    resp = client.delete(f"/api/customers/{data['id']}")
    assert resp.status_code == 204
    resp2 = client.get(f"/api/customers/{data['id']}")
    assert resp2.status_code == 404
