import pytest
import random
import string
from fastapi.testclient import TestClient


def _rand_email(prefix="user"):
    return prefix + "_" + "".join(random.choices(string.ascii_lowercase, k=6)) + "@test.pl"


def _setup_parties(client: TestClient):
    sender = client.post("/api/customers/", json={
        "name": "Sender Corp",
        "email": _rand_email("sender"),
        "city": "Warsaw",
        "country": "PL",
        "customer_type": "SHIPPER",
    }).json()
    receiver = client.post("/api/customers/", json={
        "name": "Receiver GmbH",
        "email": _rand_email("receiver"),
        "city": "Berlin",
        "country": "DE",
        "customer_type": "CONSIGNEE",
    }).json()
    carrier = client.post("/api/carriers/", json={
        "name": "Speedy Trucks",
        "email": _rand_email("carrier"),
        "city": "Lodz",
        "country": "PL",
        "max_weight_kg": 22000,
    }).json()
    return sender["id"], receiver["id"], carrier["id"]


def _create_shipment(client: TestClient):
    sender_id, receiver_id, carrier_id = _setup_parties(client)
    payload = {
        "sender_id": sender_id,
        "receiver_id": receiver_id,
        "origin_address": "ul. Przemysłowa 1",
        "origin_city": "Warsaw",
        "origin_country": "PL",
        "origin_postal_code": "00-001",
        "destination_address": "Industriestraße 5",
        "destination_city": "Berlin",
        "destination_country": "DE",
        "destination_postal_code": "10115",
        "commodity": "Machinery parts",
        "weight_kg": 5000,
        "pallet_count": 10,
        "currency": "EUR",
    }
    resp = client.post("/api/shipments/", json=payload)
    assert resp.status_code == 201
    return resp.json(), carrier_id


def test_create_shipment(client: TestClient):
    data, _ = _create_shipment(client)
    assert data["id"] is not None
    assert data["reference"].startswith("FWD-")
    assert data["status"] == "PENDING"
    assert len(data["status_history"]) == 1


def test_list_shipments(client: TestClient):
    _create_shipment(client)
    resp = client.get("/api/shipments/")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert body["total"] >= 1


def test_get_shipment(client: TestClient):
    data, _ = _create_shipment(client)
    resp = client.get(f"/api/shipments/{data['id']}")
    assert resp.status_code == 200
    assert resp.json()["reference"] == data["reference"]


def test_get_shipment_not_found(client: TestClient):
    assert client.get("/api/shipments/999999").status_code == 404


def test_update_shipment(client: TestClient):
    data, _ = _create_shipment(client)
    resp = client.patch(f"/api/shipments/{data['id']}", json={"notes": "Handle with care", "pallet_count": 12})
    assert resp.status_code == 200
    assert resp.json()["notes"] == "Handle with care"
    assert resp.json()["pallet_count"] == 12


def test_status_update(client: TestClient):
    data, _ = _create_shipment(client)
    resp = client.post(f"/api/shipments/{data['id']}/status", json={
        "status": "IN_TRANSIT",
        "location": "Frankfurt, DE",
        "note": "Crossed the border",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "IN_TRANSIT"
    statuses = [h["status"] for h in body["status_history"]]
    assert "IN_TRANSIT" in statuses


def test_delivered_records_timestamp(client: TestClient):
    data, _ = _create_shipment(client)
    resp = client.post(f"/api/shipments/{data['id']}/status", json={"status": "DELIVERED"})
    assert resp.status_code == 200
    assert resp.json()["actual_delivery_at"] is not None


def test_quote_flow(client: TestClient):
    data, carrier_id = _create_shipment(client)
    shipment_id = data["id"]

    q_resp = client.post(f"/api/shipments/{shipment_id}/quotes", json={
        "carrier_id": carrier_id,
        "price": 1250.00,
        "currency": "EUR",
        "notes": "Best price available",
    })
    assert q_resp.status_code == 201
    quote_id = q_resp.json()["id"]

    get_resp = client.get(f"/api/shipments/{shipment_id}")
    assert get_resp.json()["status"] == "QUOTED"

    accept_resp = client.post(f"/api/shipments/{shipment_id}/quotes/{quote_id}/accept")
    assert accept_resp.status_code == 200
    accepted = accept_resp.json()
    assert accepted["status"] == "BOOKED"
    assert accepted["carrier_id"] == carrier_id
    assert accepted["price"] == 1250.00


def test_filter_by_status(client: TestClient):
    data, _ = _create_shipment(client)
    client.post(f"/api/shipments/{data['id']}/status", json={"status": "CANCELLED"})
    resp = client.get("/api/shipments/?status=CANCELLED")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all(i["status"] == "CANCELLED" for i in items)


def test_delete_shipment(client: TestClient):
    data, _ = _create_shipment(client)
    resp = client.delete(f"/api/shipments/{data['id']}")
    assert resp.status_code == 204
    assert client.get(f"/api/shipments/{data['id']}").status_code == 404


def test_dashboard_stats(client: TestClient):
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert "total_shipments" in body
    assert "revenue_this_month" in body


def test_html_pages(client: TestClient):
    for path in ["/", "/shipments", "/customers", "/carriers"]:
        resp = client.get(path)
        assert resp.status_code == 200, f"Failed for {path}"
        assert "Forwardo TMS" in resp.text
