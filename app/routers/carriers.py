from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
from app import crud, schemas
from app.database import get_db

router = APIRouter(prefix="/api/carriers", tags=["carriers"])


@router.get("/", response_model=List[schemas.CarrierOut])
def list_carriers(
    skip: int = 0,
    limit: int = 100,
    search: str = Query("", max_length=100),
    db: Session = Depends(get_db),
):
    return crud.get_carriers(db, skip=skip, limit=limit, search=search)


@router.post("/", response_model=schemas.CarrierOut, status_code=201)
def create_carrier(data: schemas.CarrierCreate, db: Session = Depends(get_db)):
    return crud.create_carrier(db, data)


@router.get("/{carrier_id}", response_model=schemas.CarrierOut)
def get_carrier(carrier_id: int, db: Session = Depends(get_db)):
    obj = crud.get_carrier(db, carrier_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Carrier not found")
    return obj


@router.patch("/{carrier_id}", response_model=schemas.CarrierOut)
def update_carrier(carrier_id: int, data: schemas.CarrierUpdate, db: Session = Depends(get_db)):
    obj = crud.update_carrier(db, carrier_id, data)
    if not obj:
        raise HTTPException(status_code=404, detail="Carrier not found")
    return obj


@router.delete("/{carrier_id}", status_code=204)
def delete_carrier(carrier_id: int, db: Session = Depends(get_db)):
    if not crud.delete_carrier(db, carrier_id):
        raise HTTPException(status_code=404, detail="Carrier not found")
