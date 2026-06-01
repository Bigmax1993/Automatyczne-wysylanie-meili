from datetime import datetime, timezone
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey,
    Enum, Text, Boolean
)
from sqlalchemy.orm import relationship
from app.database import Base


def _now():
    return datetime.now(timezone.utc)


class ShipmentStatus(str, PyEnum):
    PENDING = "PENDING"
    QUOTED = "QUOTED"
    BOOKED = "BOOKED"
    PICKUP_SCHEDULED = "PICKUP_SCHEDULED"
    PICKED_UP = "PICKED_UP"
    IN_TRANSIT = "IN_TRANSIT"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class QuoteStatus(str, PyEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class CustomerType(str, PyEnum):
    SHIPPER = "SHIPPER"
    CONSIGNEE = "CONSIGNEE"
    BOTH = "BOTH"


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    email = Column(String(200), unique=True, index=True)
    phone = Column(String(50))
    address = Column(String(300))
    city = Column(String(100))
    country = Column(String(100), default="PL")
    vat_number = Column(String(50))
    customer_type = Column(Enum(CustomerType), default=CustomerType.BOTH)
    notes = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    shipments_as_sender = relationship(
        "Shipment", foreign_keys="Shipment.sender_id", back_populates="sender"
    )
    shipments_as_receiver = relationship(
        "Shipment", foreign_keys="Shipment.receiver_id", back_populates="receiver"
    )


class Carrier(Base):
    __tablename__ = "carriers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    email = Column(String(200), unique=True, index=True)
    phone = Column(String(50))
    address = Column(String(300))
    city = Column(String(100))
    country = Column(String(100), default="PL")
    mc_number = Column(String(50))
    nip = Column(String(20))
    equipment_types = Column(String(300))
    max_weight_kg = Column(Float)
    is_active = Column(Boolean, default=True)
    rating = Column(Float, default=5.0)
    created_at = Column(DateTime(timezone=True), default=_now)

    quotes = relationship("Quote", back_populates="carrier")
    shipments = relationship("Shipment", back_populates="carrier")


class Shipment(Base):
    __tablename__ = "shipments"

    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String(50), unique=True, index=True, nullable=False)
    status = Column(Enum(ShipmentStatus), default=ShipmentStatus.PENDING)

    sender_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    receiver_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    carrier_id = Column(Integer, ForeignKey("carriers.id"), nullable=True)

    origin_address = Column(String(300), nullable=False)
    origin_city = Column(String(100), nullable=False)
    origin_country = Column(String(100), default="PL")
    origin_postal_code = Column(String(20))

    destination_address = Column(String(300), nullable=False)
    destination_city = Column(String(100), nullable=False)
    destination_country = Column(String(100), default="PL")
    destination_postal_code = Column(String(20))

    pickup_date = Column(DateTime(timezone=True))
    delivery_date = Column(DateTime(timezone=True))
    actual_pickup_at = Column(DateTime(timezone=True))
    actual_delivery_at = Column(DateTime(timezone=True))

    commodity = Column(String(300))
    weight_kg = Column(Float)
    volume_m3 = Column(Float)
    loading_meters = Column(Float)
    pallet_count = Column(Integer)
    is_hazardous = Column(Boolean, default=False)
    temperature_controlled = Column(Boolean, default=False)

    price = Column(Float)
    currency = Column(String(10), default="PLN")
    notes = Column(Text)

    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    sender = relationship("Customer", foreign_keys=[sender_id], back_populates="shipments_as_sender")
    receiver = relationship("Customer", foreign_keys=[receiver_id], back_populates="shipments_as_receiver")
    carrier = relationship("Carrier", back_populates="shipments")
    status_history = relationship("StatusHistory", back_populates="shipment", cascade="all, delete-orphan")
    quotes = relationship("Quote", back_populates="shipment", cascade="all, delete-orphan")


class StatusHistory(Base):
    __tablename__ = "status_history"

    id = Column(Integer, primary_key=True, index=True)
    shipment_id = Column(Integer, ForeignKey("shipments.id"), nullable=False)
    status = Column(Enum(ShipmentStatus), nullable=False)
    location = Column(String(200))
    note = Column(Text)
    created_at = Column(DateTime(timezone=True), default=_now)

    shipment = relationship("Shipment", back_populates="status_history")


class Quote(Base):
    __tablename__ = "quotes"

    id = Column(Integer, primary_key=True, index=True)
    shipment_id = Column(Integer, ForeignKey("shipments.id"), nullable=False)
    carrier_id = Column(Integer, ForeignKey("carriers.id"), nullable=False)
    price = Column(Float, nullable=False)
    currency = Column(String(10), default="PLN")
    valid_until = Column(DateTime(timezone=True))
    status = Column(Enum(QuoteStatus), default=QuoteStatus.PENDING)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), default=_now)

    shipment = relationship("Shipment", back_populates="quotes")
    carrier = relationship("Carrier", back_populates="quotes")
