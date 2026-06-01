import random
import string
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, or_
from app import models, schemas


def _gen_reference() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    year = datetime.now().strftime("%y")
    return f"FWD-{year}-{suffix}"


# ── Customers ─────────────────────────────────────────────────────────────────

def get_customers(db: Session, skip: int = 0, limit: int = 100, search: str = "") -> List[models.Customer]:
    q = db.query(models.Customer)
    if search:
        q = q.filter(
            or_(
                models.Customer.name.ilike(f"%{search}%"),
                models.Customer.email.ilike(f"%{search}%"),
                models.Customer.city.ilike(f"%{search}%"),
            )
        )
    return q.order_by(models.Customer.name).offset(skip).limit(limit).all()


def get_customer(db: Session, customer_id: int) -> Optional[models.Customer]:
    return db.query(models.Customer).filter(models.Customer.id == customer_id).first()


def create_customer(db: Session, data: schemas.CustomerCreate) -> models.Customer:
    obj = models.Customer(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update_customer(db: Session, customer_id: int, data: schemas.CustomerUpdate) -> Optional[models.Customer]:
    obj = get_customer(db, customer_id)
    if not obj:
        return None
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(obj, k, v)
    obj.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(obj)
    return obj


def delete_customer(db: Session, customer_id: int) -> bool:
    obj = get_customer(db, customer_id)
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True


# ── Carriers ──────────────────────────────────────────────────────────────────

def get_carriers(db: Session, skip: int = 0, limit: int = 100, search: str = "") -> List[models.Carrier]:
    q = db.query(models.Carrier)
    if search:
        q = q.filter(
            or_(
                models.Carrier.name.ilike(f"%{search}%"),
                models.Carrier.email.ilike(f"%{search}%"),
            )
        )
    return q.order_by(models.Carrier.name).offset(skip).limit(limit).all()


def get_carrier(db: Session, carrier_id: int) -> Optional[models.Carrier]:
    return db.query(models.Carrier).filter(models.Carrier.id == carrier_id).first()


def create_carrier(db: Session, data: schemas.CarrierCreate) -> models.Carrier:
    obj = models.Carrier(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update_carrier(db: Session, carrier_id: int, data: schemas.CarrierUpdate) -> Optional[models.Carrier]:
    obj = get_carrier(db, carrier_id)
    if not obj:
        return None
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


def delete_carrier(db: Session, carrier_id: int) -> bool:
    obj = get_carrier(db, carrier_id)
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True


# ── Shipments ─────────────────────────────────────────────────────────────────

def get_shipments(
    db: Session,
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None,
    search: str = "",
) -> tuple[List[models.Shipment], int]:
    q = db.query(models.Shipment)
    if status:
        q = q.filter(models.Shipment.status == status)
    if search:
        q = q.join(models.Customer, models.Shipment.sender_id == models.Customer.id, isouter=True).filter(
            or_(
                models.Shipment.reference.ilike(f"%{search}%"),
                models.Shipment.origin_city.ilike(f"%{search}%"),
                models.Shipment.destination_city.ilike(f"%{search}%"),
                models.Customer.name.ilike(f"%{search}%"),
            )
        )
    total = q.count()
    items = q.order_by(models.Shipment.created_at.desc()).offset(skip).limit(limit).all()
    return items, total


def get_shipment(db: Session, shipment_id: int) -> Optional[models.Shipment]:
    return db.query(models.Shipment).filter(models.Shipment.id == shipment_id).first()


def get_shipment_by_reference(db: Session, reference: str) -> Optional[models.Shipment]:
    return db.query(models.Shipment).filter(models.Shipment.reference == reference).first()


def create_shipment(db: Session, data: schemas.ShipmentCreate) -> models.Shipment:
    ref = _gen_reference()
    while get_shipment_by_reference(db, ref):
        ref = _gen_reference()
    obj = models.Shipment(reference=ref, **data.model_dump())
    db.add(obj)
    db.flush()
    history = models.StatusHistory(
        shipment_id=obj.id,
        status=models.ShipmentStatus.PENDING,
        note="Shipment created",
    )
    db.add(history)
    db.commit()
    db.refresh(obj)
    return obj


def update_shipment(db: Session, shipment_id: int, data: schemas.ShipmentUpdate) -> Optional[models.Shipment]:
    obj = get_shipment(db, shipment_id)
    if not obj:
        return None
    updates = data.model_dump(exclude_none=True)
    for k, v in updates.items():
        setattr(obj, k, v)
    obj.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(obj)
    return obj


def update_shipment_status(
    db: Session, shipment_id: int, data: schemas.StatusUpdate
) -> Optional[models.Shipment]:
    obj = get_shipment(db, shipment_id)
    if not obj:
        return None
    obj.status = data.status
    obj.updated_at = datetime.now(timezone.utc)
    if data.status == models.ShipmentStatus.PICKED_UP and not obj.actual_pickup_at:
        obj.actual_pickup_at = datetime.now(timezone.utc)
    if data.status == models.ShipmentStatus.DELIVERED and not obj.actual_delivery_at:
        obj.actual_delivery_at = datetime.now(timezone.utc)
    history = models.StatusHistory(
        shipment_id=shipment_id,
        status=data.status,
        location=data.location,
        note=data.note,
    )
    db.add(history)
    db.commit()
    db.refresh(obj)
    return obj


def delete_shipment(db: Session, shipment_id: int) -> bool:
    obj = get_shipment(db, shipment_id)
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True


# ── Quotes ────────────────────────────────────────────────────────────────────

def create_quote(db: Session, shipment_id: int, data: schemas.QuoteCreate) -> models.Quote:
    obj = models.Quote(shipment_id=shipment_id, **data.model_dump())
    db.add(obj)
    if get_shipment(db, shipment_id) and get_shipment(db, shipment_id).status == models.ShipmentStatus.PENDING:
        get_shipment(db, shipment_id).status = models.ShipmentStatus.QUOTED
    db.commit()
    db.refresh(obj)
    return obj


def accept_quote(db: Session, shipment_id: int, quote_id: int) -> Optional[models.Shipment]:
    quote = db.query(models.Quote).filter(
        models.Quote.id == quote_id,
        models.Quote.shipment_id == shipment_id,
    ).first()
    if not quote:
        return None
    quote.status = models.QuoteStatus.ACCEPTED
    db.query(models.Quote).filter(
        models.Quote.shipment_id == shipment_id,
        models.Quote.id != quote_id,
    ).update({"status": models.QuoteStatus.REJECTED})
    shipment = get_shipment(db, shipment_id)
    shipment.carrier_id = quote.carrier_id
    shipment.price = quote.price
    shipment.currency = quote.currency
    shipment.status = models.ShipmentStatus.BOOKED
    history = models.StatusHistory(
        shipment_id=shipment_id,
        status=models.ShipmentStatus.BOOKED,
        note=f"Quote #{quote_id} accepted. Carrier: {quote.carrier.name if quote.carrier else quote.carrier_id}",
    )
    db.add(history)
    db.commit()
    db.refresh(shipment)
    return shipment


# ── Dashboard Stats ───────────────────────────────────────────────────────────

def get_dashboard_stats(db: Session) -> schemas.DashboardStats:
    now = datetime.now(timezone.utc)
    total = db.query(func.count(models.Shipment.id)).scalar() or 0
    pending = db.query(func.count(models.Shipment.id)).filter(
        models.Shipment.status == models.ShipmentStatus.PENDING
    ).scalar() or 0
    in_transit = db.query(func.count(models.Shipment.id)).filter(
        models.Shipment.status.in_([
            models.ShipmentStatus.PICKED_UP,
            models.ShipmentStatus.IN_TRANSIT,
            models.ShipmentStatus.OUT_FOR_DELIVERY,
        ])
    ).scalar() or 0
    delivered = db.query(func.count(models.Shipment.id)).filter(
        models.Shipment.status == models.ShipmentStatus.DELIVERED
    ).scalar() or 0
    cancelled = db.query(func.count(models.Shipment.id)).filter(
        models.Shipment.status == models.ShipmentStatus.CANCELLED
    ).scalar() or 0
    customers = db.query(func.count(models.Customer.id)).scalar() or 0
    carriers = db.query(func.count(models.Carrier.id)).scalar() or 0
    revenue = db.query(func.sum(models.Shipment.price)).filter(
        models.Shipment.status == models.ShipmentStatus.DELIVERED,
        extract("month", models.Shipment.actual_delivery_at) == now.month,
        extract("year", models.Shipment.actual_delivery_at) == now.year,
    ).scalar() or 0.0
    return schemas.DashboardStats(
        total_shipments=total,
        pending=pending,
        in_transit=in_transit,
        delivered=delivered,
        cancelled=cancelled,
        total_customers=customers,
        total_carriers=carriers,
        revenue_this_month=float(revenue),
    )
