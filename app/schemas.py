from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, field_validator
from app.models import ShipmentStatus, QuoteStatus, CustomerType


# ── Customer ─────────────────────────────────────────────────────────────────

class CustomerBase(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    country: str = "PL"
    vat_number: Optional[str] = None
    customer_type: CustomerType = CustomerType.BOTH
    notes: Optional[str] = None
    is_active: bool = True


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    vat_number: Optional[str] = None
    customer_type: Optional[CustomerType] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class CustomerOut(CustomerBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Carrier ───────────────────────────────────────────────────────────────────

class CarrierBase(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    country: str = "PL"
    mc_number: Optional[str] = None
    nip: Optional[str] = None
    equipment_types: Optional[str] = None
    max_weight_kg: Optional[float] = None
    is_active: bool = True
    rating: float = 5.0


class CarrierCreate(CarrierBase):
    pass


class CarrierUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    mc_number: Optional[str] = None
    nip: Optional[str] = None
    equipment_types: Optional[str] = None
    max_weight_kg: Optional[float] = None
    is_active: Optional[bool] = None
    rating: Optional[float] = None


class CarrierOut(CarrierBase):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Quote ─────────────────────────────────────────────────────────────────────

class QuoteBase(BaseModel):
    carrier_id: int
    price: float
    currency: str = "PLN"
    valid_until: Optional[datetime] = None
    notes: Optional[str] = None


class QuoteCreate(QuoteBase):
    pass


class QuoteOut(QuoteBase):
    id: int
    shipment_id: int
    status: QuoteStatus
    created_at: datetime
    carrier: Optional[CarrierOut] = None

    model_config = {"from_attributes": True}


# ── Status History ────────────────────────────────────────────────────────────

class StatusHistoryOut(BaseModel):
    id: int
    status: ShipmentStatus
    location: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Shipment ──────────────────────────────────────────────────────────────────

class ShipmentBase(BaseModel):
    sender_id: int
    receiver_id: int
    origin_address: str
    origin_city: str
    origin_country: str = "PL"
    origin_postal_code: Optional[str] = None
    destination_address: str
    destination_city: str
    destination_country: str = "PL"
    destination_postal_code: Optional[str] = None
    pickup_date: Optional[datetime] = None
    delivery_date: Optional[datetime] = None
    commodity: Optional[str] = None
    weight_kg: Optional[float] = None
    volume_m3: Optional[float] = None
    loading_meters: Optional[float] = None
    pallet_count: Optional[int] = None
    is_hazardous: bool = False
    temperature_controlled: bool = False
    price: Optional[float] = None
    currency: str = "PLN"
    notes: Optional[str] = None


class ShipmentCreate(ShipmentBase):
    pass


class ShipmentUpdate(BaseModel):
    carrier_id: Optional[int] = None
    status: Optional[ShipmentStatus] = None
    origin_address: Optional[str] = None
    origin_city: Optional[str] = None
    origin_postal_code: Optional[str] = None
    destination_address: Optional[str] = None
    destination_city: Optional[str] = None
    destination_postal_code: Optional[str] = None
    pickup_date: Optional[datetime] = None
    delivery_date: Optional[datetime] = None
    actual_pickup_at: Optional[datetime] = None
    actual_delivery_at: Optional[datetime] = None
    commodity: Optional[str] = None
    weight_kg: Optional[float] = None
    volume_m3: Optional[float] = None
    loading_meters: Optional[float] = None
    pallet_count: Optional[int] = None
    is_hazardous: Optional[bool] = None
    temperature_controlled: Optional[bool] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    notes: Optional[str] = None


class ShipmentOut(ShipmentBase):
    id: int
    reference: str
    status: ShipmentStatus
    carrier_id: Optional[int] = None
    actual_pickup_at: Optional[datetime] = None
    actual_delivery_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    sender: Optional[CustomerOut] = None
    receiver: Optional[CustomerOut] = None
    carrier: Optional[CarrierOut] = None
    status_history: List[StatusHistoryOut] = []
    quotes: List[QuoteOut] = []

    model_config = {"from_attributes": True}


# ── Status Update ─────────────────────────────────────────────────────────────

class StatusUpdate(BaseModel):
    status: ShipmentStatus
    location: Optional[str] = None
    note: Optional[str] = None


# ── Pagination / Stats ────────────────────────────────────────────────────────

class PaginatedShipments(BaseModel):
    items: List[ShipmentOut]
    total: int
    skip: int
    limit: int


class DashboardStats(BaseModel):
    total_shipments: int
    pending: int
    in_transit: int
    delivered: int
    cancelled: int
    total_customers: int
    total_carriers: int
    revenue_this_month: float
