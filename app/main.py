from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import schemas
from app.config import get_service_token
from app.database import engine, get_db
from app.models import Account, Base, Shipment
from app.services.fedex_client import FedExAccount, FedExClient

Base.metadata.create_all(bind=engine)

app = FastAPI(title="FedEx Shipment Gateway", version="1.0.0")


def require_token(token: str = Query(..., description="Service token for authentication")):
    expected_token = get_service_token()
    if not expected_token or token != expected_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


@app.post("/accounts", response_model=schemas.AccountRead, dependencies=[Depends(require_token)])
def create_account(account: schemas.AccountCreate, db: Session = Depends(get_db)):
    db_account = Account(**account.dict())
    db.add(db_account)
    db.commit()
    db.refresh(db_account)
    return db_account


@app.get("/accounts", response_model=list[schemas.AccountRead], dependencies=[Depends(require_token)])
def list_accounts(db: Session = Depends(get_db)):
    return db.query(Account).order_by(Account.created_at.desc()).all()


def _get_account(db: Session, account_id: int) -> Account:
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account


@app.post("/rates", response_model=schemas.RateResponse, dependencies=[Depends(require_token)])
def get_rate(rate_request: schemas.RateRequest, db: Session = Depends(get_db)):
    account = _get_account(db, rate_request.account_id)
    client = FedExClient(
        FedExAccount(
            id=account.id,
            name=account.name,
            account_number=account.account_number,
            meter_number=account.meter_number,
            api_key=account.api_key,
            api_secret=account.api_secret,
            is_freight=account.is_freight,
        ),
        db,
    )
    quote = client.get_rate(
        weight_kg=rate_request.weight_kg,
        destination_country=rate_request.destination_country,
        service_type=rate_request.service_type,
    )
    return schemas.RateResponse(
        account_id=account.id,
        service_type=rate_request.service_type,
        currency=quote.currency,
        amount=quote.amount,
    )


@app.post("/orders", response_model=schemas.ShipmentRead, dependencies=[Depends(require_token)])
def create_shipment(order: schemas.ShipmentCreate, db: Session = Depends(get_db)):
    account = _get_account(db, order.account_id)
    client = FedExClient(
        FedExAccount(
            id=account.id,
            name=account.name,
            account_number=account.account_number,
            meter_number=account.meter_number,
            api_key=account.api_key,
            api_secret=account.api_secret,
            is_freight=account.is_freight,
        ),
        db,
    )

    rate = client.get_rate(
        weight_kg=order.weight_kg,
        destination_country=order.recipient_country,
        service_type=order.service_type,
    )

    shipment = Shipment(
        order_reference=order.order_reference,
        account_id=account.id,
        service_type=order.service_type,
        recipient_name=order.recipient_name,
        recipient_address=order.recipient_address,
        recipient_city=order.recipient_city,
        recipient_country=order.recipient_country,
        weight_kg=order.weight_kg,
        price_quote=rate.amount,
        tracking_number="",
        label_path="",
    )
    db.add(shipment)
    db.commit()
    db.refresh(shipment)

    tracking_number, label_path = client.create_shipment(
        shipment_id=shipment.id,
        destination=f"{shipment.recipient_city}, {shipment.recipient_country}",
        service_type=order.service_type,
        recipient={
            "name": shipment.recipient_name,
            "address": shipment.recipient_address,
            "city": shipment.recipient_city,
            "country": shipment.recipient_country,
            "weight": shipment.weight_kg,
        },
    )

    shipment.tracking_number = tracking_number
    shipment.label_path = label_path
    db.add(shipment)
    db.commit()
    db.refresh(shipment)

    return shipment


@app.get("/shipments", response_model=schemas.PaginatedShipments, dependencies=[Depends(require_token)])
def list_shipments(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    query = db.query(Shipment).order_by(Shipment.created_at.desc())
    total = query.count()
    items = query.offset(skip).limit(limit).all()
    return schemas.PaginatedShipments(items=items, total=total)


@app.get("/shipments/{shipment_id}", response_model=schemas.ShipmentRead, dependencies=[Depends(require_token)])
def get_shipment(shipment_id: int, db: Session = Depends(get_db)):
    shipment = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not shipment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")
    return shipment


@app.get("/shipments/{shipment_id}/label", response_class=FileResponse, dependencies=[Depends(require_token)])
def download_label(shipment_id: int, db: Session = Depends(get_db)):
    shipment = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not shipment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")
    if not shipment.label_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label missing")
    return FileResponse(shipment.label_path, filename=f"label_{shipment_id}.pdf")


@app.get("/health")
def healthcheck():
    return {"status": "ok"}
