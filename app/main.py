from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import schemas
from app.config import get_service_token
from app.database import engine, get_db
from app.models import Account, Base, Shipment, Shipper
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


@app.post("/shippers", response_model=schemas.ShipperRead, dependencies=[Depends(require_token)])
def create_shipper(shipper: schemas.ShipperCreate, db: Session = Depends(get_db)):
    db_shipper = Shipper(**shipper.dict())
    db.add(db_shipper)
    db.commit()
    db.refresh(db_shipper)
    return db_shipper


@app.get("/shippers", response_model=list[schemas.ShipperRead], dependencies=[Depends(require_token)])
def list_shippers(db: Session = Depends(get_db)):
    return db.query(Shipper).order_by(Shipper.created_at.desc()).all()


def _get_shipper(db: Session, shipper_id: int) -> Shipper:
    shipper = db.query(Shipper).filter(Shipper.id == shipper_id).first()
    if not shipper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipper not found")
    return shipper


def _fedex_client(account: Account, db: Session) -> FedExClient:
    return FedExClient(
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


def _create_and_send_shipment(
    db: Session,
    client: FedExClient,
    *,
    account: Account,
    shipper: Shipper,
    service_type: schemas.AllowedService,
    order_reference: str,
    recipient_payload: dict,
    weight_kg: float,
) -> Shipment:
    shipment = Shipment(
        order_reference=order_reference,
        account_id=account.id,
        shipper_id=shipper.id,
        service_type=service_type,
        recipient_name=recipient_payload.get("name"),
        recipient_company=recipient_payload.get("company"),
        recipient_phone=recipient_payload.get("phone"),
        recipient_email=recipient_payload.get("email"),
        recipient_address=recipient_payload.get("address"),
        recipient_city=recipient_payload.get("city"),
        recipient_state_code=recipient_payload.get("state_code"),
        recipient_postal_code=recipient_payload.get("postal_code"),
        recipient_country=recipient_payload.get("country"),
        weight_kg=weight_kg,
        price_quote=None,
        tracking_number="",
        label_path="",
    )
    db.add(shipment)
    db.commit()
    db.refresh(shipment)

    try:
        tracking_number, label_path = client.create_shipment(
            shipment_id=shipment.id,
            destination=f"{shipment.recipient_city}, {shipment.recipient_country}",
            service_type=service_type,
            recipient={
                "name": shipment.recipient_name,
                "company": shipment.recipient_company,
                "phone": shipment.recipient_phone,
                "email": shipment.recipient_email,
                "address": shipment.recipient_address,
                "city": shipment.recipient_city,
                "state_code": shipment.recipient_state_code,
                "postal_code": shipment.recipient_postal_code,
                "country": shipment.recipient_country,
                "weight": shipment.weight_kg,
            },
            shipper=shipper,
        )
    except HTTPException:
        shipment.status = "error"
        db.add(shipment)
        db.commit()
        raise

    shipment.tracking_number = tracking_number
    shipment.label_path = label_path
    db.add(shipment)
    db.commit()
    db.refresh(shipment)
    return shipment


@app.post("/rates", response_model=schemas.RateResponse, dependencies=[Depends(require_token)])
def get_rate(rate_request: schemas.RateRequest, db: Session = Depends(get_db)):
    account = _get_account(db, rate_request.account_id)
    shipper = _get_shipper(db, rate_request.shipper_id)
    client = _fedex_client(account, db)
    quote = client.get_rate(
        weight_kg=rate_request.weight_kg,
        shipper=shipper,
        recipient={
            "address": rate_request.destination_address,
            "city": rate_request.destination_city,
            "state_code": rate_request.destination_state_code,
            "postal_code": rate_request.destination_postal_code,
            "country": rate_request.destination_country,
        },
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
    shipper = _get_shipper(db, order.shipper_id)
    client = _fedex_client(account, db)

    recipient_payload = {
        "name": order.recipient_name,
        "company": order.recipient_company,
        "phone": order.recipient_phone,
        "email": order.recipient_email,
        "address": order.recipient_address,
        "city": order.recipient_city,
        "state_code": order.recipient_state_code,
        "postal_code": order.recipient_postal_code,
        "country": order.recipient_country,
    }

    shipment = _create_and_send_shipment(
        db,
        client,
        account=account,
        shipper=shipper,
        service_type=order.service_type,
        order_reference=order.order_reference,
        recipient_payload=recipient_payload,
        weight_kg=order.weight_kg,
    )

    return shipment


TEST_SERVICE_TYPES: list[schemas.AllowedService] = ["FIP", "IPE", "FIE", "RE", "PO", "FICP"]


@app.post(
    "/test/shipments",
    response_model=schemas.ShipmentTestResponse,
    dependencies=[Depends(require_token)],
    summary="Create test shipments for multiple services from the same shipper/recipient",
)
def run_test_shipments(payload: schemas.ShipmentTestRequest, db: Session = Depends(get_db)):
    account = _get_account(db, payload.account_id)
    shipper = _get_shipper(db, payload.shipper_id)
    client = _fedex_client(account, db)

    recipient_payload = {
        "name": payload.recipient_name,
        "company": payload.recipient_company,
        "phone": payload.recipient_phone,
        "email": payload.recipient_email,
        "address": payload.recipient_address,
        "city": payload.recipient_city,
        "state_code": payload.recipient_state_code,
        "postal_code": payload.recipient_postal_code,
        "country": payload.recipient_country,
    }

    results: list[schemas.ShipmentTestResult] = []
    for service_type in TEST_SERVICE_TYPES:
        order_reference = f"{payload.order_reference_prefix}-{service_type}"
        try:
            shipment = _create_and_send_shipment(
                db,
                client,
                account=account,
                shipper=shipper,
                service_type=service_type,
                order_reference=order_reference,
                recipient_payload=recipient_payload,
                weight_kg=payload.weight_kg,
            )
            results.append(
                schemas.ShipmentTestResult(
                    service_type=service_type, status=shipment.status, shipment=shipment
                )
            )
        except HTTPException as exc:
            db.rollback()
            results.append(
                schemas.ShipmentTestResult(
                    service_type=service_type,
                    status="error",
                    error=str(exc.detail),
                )
            )
        except Exception as exc:  # pragma: no cover - unexpected failures surfaced to client
            db.rollback()
            results.append(
                schemas.ShipmentTestResult(
                    service_type=service_type,
                    status="error",
                    error=str(exc),
                )
            )

    return schemas.ShipmentTestResponse(results=results)


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
