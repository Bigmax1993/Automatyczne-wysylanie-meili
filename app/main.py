from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional
import os

from app.database import get_db, init_db
from app import crud, schemas, models
from app.routers import customers, carriers, shipments


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Forwardo TMS",
    description="Transportation Management System for freight forwarding",
    version="1.0.0",
    lifespan=lifespan,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

app.include_router(customers.router)
app.include_router(carriers.router)
app.include_router(shipments.router)


@app.get("/api/stats", response_model=schemas.DashboardStats, tags=["stats"])
def dashboard_stats(db: Session = Depends(get_db)):
    return crud.get_dashboard_stats(db)


# ── HTML pages ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    stats = crud.get_dashboard_stats(db)
    recent_shipments, _ = crud.get_shipments(db, skip=0, limit=10)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"stats": stats, "recent_shipments": recent_shipments},
    )


@app.get("/shipments", response_class=HTMLResponse)
def shipments_page(
    request: Request,
    status: Optional[str] = None,
    search: str = "",
    page: int = 1,
    db: Session = Depends(get_db),
):
    limit = 20
    skip = (page - 1) * limit
    items, total = crud.get_shipments(db, skip=skip, limit=limit, status=status, search=search)
    pages = (total + limit - 1) // limit
    statuses = [s.value for s in models.ShipmentStatus]
    return templates.TemplateResponse(
        request,
        "shipments.html",
        {
            "shipments": items,
            "total": total,
            "page": page,
            "pages": pages,
            "status_filter": status,
            "search": search,
            "statuses": statuses,
        },
    )


@app.get("/shipments/{shipment_id}", response_class=HTMLResponse)
def shipment_detail_page(request: Request, shipment_id: int, db: Session = Depends(get_db)):
    obj = crud.get_shipment(db, shipment_id)
    if not obj:
        return HTMLResponse("<h1>404 - Shipment not found</h1>", status_code=404)
    carriers_list = crud.get_carriers(db, limit=200)
    return templates.TemplateResponse(
        request,
        "shipment_detail.html",
        {"shipment": obj, "carriers": carriers_list},
    )


@app.get("/customers", response_class=HTMLResponse)
def customers_page(request: Request, search: str = "", db: Session = Depends(get_db)):
    items = crud.get_customers(db, limit=200, search=search)
    return templates.TemplateResponse(
        request,
        "customers.html",
        {"customers": items, "search": search},
    )


@app.get("/carriers", response_class=HTMLResponse)
def carriers_page(request: Request, search: str = "", db: Session = Depends(get_db)):
    items = crud.get_carriers(db, limit=200, search=search)
    return templates.TemplateResponse(
        request,
        "carriers.html",
        {"carriers": items, "search": search},
    )
