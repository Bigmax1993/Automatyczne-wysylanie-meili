from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from app import crud, schemas
from app.database import get_db

router = APIRouter(prefix="/api/shipments", tags=["shipments"])


@router.get("/", response_model=schemas.PaginatedShipments)
def list_shipments(
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None,
    search: str = Query("", max_length=200),
    db: Session = Depends(get_db),
):
    items, total = crud.get_shipments(db, skip=skip, limit=limit, status=status, search=search)
    return schemas.PaginatedShipments(items=items, total=total, skip=skip, limit=limit)


@router.post("/", response_model=schemas.ShipmentOut, status_code=201)
def create_shipment(data: schemas.ShipmentCreate, db: Session = Depends(get_db)):
    return crud.create_shipment(db, data)


@router.get("/{shipment_id}", response_model=schemas.ShipmentOut)
def get_shipment(shipment_id: int, db: Session = Depends(get_db)):
    obj = crud.get_shipment(db, shipment_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return obj


@router.patch("/{shipment_id}", response_model=schemas.ShipmentOut)
def update_shipment(shipment_id: int, data: schemas.ShipmentUpdate, db: Session = Depends(get_db)):
    obj = crud.update_shipment(db, shipment_id, data)
    if not obj:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return obj


@router.delete("/{shipment_id}", status_code=204)
def delete_shipment(shipment_id: int, db: Session = Depends(get_db)):
    if not crud.delete_shipment(db, shipment_id):
        raise HTTPException(status_code=404, detail="Shipment not found")


@router.post("/{shipment_id}/status", response_model=schemas.ShipmentOut)
def update_status(shipment_id: int, data: schemas.StatusUpdate, db: Session = Depends(get_db)):
    obj = crud.update_shipment_status(db, shipment_id, data)
    if not obj:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return obj


@router.post("/{shipment_id}/quotes", response_model=schemas.QuoteOut, status_code=201)
def add_quote(shipment_id: int, data: schemas.QuoteCreate, db: Session = Depends(get_db)):
    if not crud.get_shipment(db, shipment_id):
        raise HTTPException(status_code=404, detail="Shipment not found")
    return crud.create_quote(db, shipment_id, data)


@router.post("/{shipment_id}/quotes/{quote_id}/accept", response_model=schemas.ShipmentOut)
def accept_quote(shipment_id: int, quote_id: int, db: Session = Depends(get_db)):
    obj = crud.accept_quote(db, shipment_id, quote_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Quote or shipment not found")
    return obj
