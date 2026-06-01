from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
from app import crud, schemas
from app.database import get_db

router = APIRouter(prefix="/api/customers", tags=["customers"])


@router.get("/", response_model=List[schemas.CustomerOut])
def list_customers(
    skip: int = 0,
    limit: int = 100,
    search: str = Query("", max_length=100),
    db: Session = Depends(get_db),
):
    return crud.get_customers(db, skip=skip, limit=limit, search=search)


@router.post("/", response_model=schemas.CustomerOut, status_code=201)
def create_customer(data: schemas.CustomerCreate, db: Session = Depends(get_db)):
    return crud.create_customer(db, data)


@router.get("/{customer_id}", response_model=schemas.CustomerOut)
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    obj = crud.get_customer(db, customer_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Customer not found")
    return obj


@router.patch("/{customer_id}", response_model=schemas.CustomerOut)
def update_customer(customer_id: int, data: schemas.CustomerUpdate, db: Session = Depends(get_db)):
    obj = crud.update_customer(db, customer_id, data)
    if not obj:
        raise HTTPException(status_code=404, detail="Customer not found")
    return obj


@router.delete("/{customer_id}", status_code=204)
def delete_customer(customer_id: int, db: Session = Depends(get_db)):
    if not crud.delete_customer(db, customer_id):
        raise HTTPException(status_code=404, detail="Customer not found")
