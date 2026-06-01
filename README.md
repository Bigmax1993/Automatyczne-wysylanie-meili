# Forwardo TMS

**Transportation Management System** for freight forwarding companies.

Built with **FastAPI**, **SQLAlchemy**, and **SQLite** (easily switched to PostgreSQL). Includes a web dashboard with full REST API.

## Features

- **Shipment management** — full lifecycle from quote to delivery, with status tracking
- **Customer management** — shippers and consignees
- **Carrier management** — transport partners with equipment types and ratings
- **Quote workflow** — request, compare, and accept carrier quotes per shipment
- **Timeline tracking** — every status change is recorded with location and notes
- **REST API** — full OpenAPI docs at `/docs`
- **Web dashboard** — HTML UI for browsing shipments, customers, carriers

## Shipment statuses

```
PENDING → QUOTED → BOOKED → PICKUP_SCHEDULED → PICKED_UP → IN_TRANSIT → OUT_FOR_DELIVERY → DELIVERED
                                                                                           └→ CANCELLED
```

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/Bigmax1993/forwardo-tms.git
cd forwardo-tms
python -m pip install -r requirements.txt

# 2. Configure environment (optional)
cp .env.example .env
# Edit .env as needed

# 3. Run the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open: http://localhost:8000

API docs: http://localhost:8000/docs

## API Examples

```bash
# Create a customer
curl -X POST http://localhost:8000/api/customers/ \
  -H "Content-Type: application/json" \
  -d '{"name":"ABC Logistics","email":"info@abc.pl","city":"Warsaw","country":"PL","customer_type":"SHIPPER"}'

# Create a carrier
curl -X POST http://localhost:8000/api/carriers/ \
  -H "Content-Type: application/json" \
  -d '{"name":"Fast Transport","email":"ops@fasttransport.pl","city":"Poznan","max_weight_kg":24000}'

# Create a shipment
curl -X POST http://localhost:8000/api/shipments/ \
  -H "Content-Type: application/json" \
  -d '{
    "sender_id": 1,
    "receiver_id": 2,
    "origin_address": "ul. Przemysłowa 1",
    "origin_city": "Warsaw",
    "origin_country": "PL",
    "destination_address": "Industriestraße 5",
    "destination_city": "Berlin",
    "destination_country": "DE",
    "commodity": "Machine parts",
    "weight_kg": 5000,
    "pallet_count": 10
  }'

# Update shipment status
curl -X POST http://localhost:8000/api/shipments/1/status \
  -H "Content-Type: application/json" \
  -d '{"status":"IN_TRANSIT","location":"Frankfurt, DE","note":"Crossing the border"}'

# Add a quote from a carrier
curl -X POST http://localhost:8000/api/shipments/1/quotes \
  -H "Content-Type: application/json" \
  -d '{"carrier_id":1,"price":1200.00,"currency":"EUR"}'

# Accept the quote
curl -X POST http://localhost:8000/api/shipments/1/quotes/1/accept

# Dashboard stats
curl http://localhost:8000/api/stats
```

## Project Structure

```
forwardo-tms/
├── app/
│   ├── main.py          # FastAPI app + HTML routes
│   ├── database.py      # SQLAlchemy engine & session
│   ├── models.py        # ORM models
│   ├── schemas.py       # Pydantic schemas
│   ├── crud.py          # Database operations
│   └── routers/         # API route handlers
│       ├── customers.py
│       ├── carriers.py
│       └── shipments.py
├── templates/           # Jinja2 HTML templates
├── static/              # CSS
├── tests/               # pytest test suite
├── .github/workflows/   # GitHub Actions CI
├── requirements.txt
└── .env.example
```

## Tests

```bash
python -m pytest tests/ -v
```

## Database

Default: **SQLite** (`forwardo.db` in project root — created automatically on first run).

To switch to PostgreSQL, set `DATABASE_URL` in `.env`:

```
DATABASE_URL=postgresql://user:password@localhost:5432/forwardo
```

Then install the async driver: `pip install psycopg2-binary` (or `asyncpg` for async).

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./forwardo.db` | Database connection string |
| `APP_HOST` | `0.0.0.0` | Server bind host |
| `APP_PORT` | `8000` | Server port |
