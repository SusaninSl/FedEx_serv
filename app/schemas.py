from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class AccountBase(BaseModel):
    name: str
    account_number: str
    meter_number: Optional[str] = None
    api_key: str
    api_secret: str
    is_freight: bool = False


class AccountCreate(AccountBase):
    pass


class AccountRead(AccountBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True


AllowedService = Literal[
    "FIP",  # FedEx International Priority
    "IPE",  # FedEx International Priority Express
    "FIE",  # FedEx International Economy
    "RE",  # FedEx Regional Economy
    "PO",  # FedEx Priority Overnight
    "FICP",  # FedEx International Connect Plus
    "IPF",  # FedEx International Priority Freight
    "IEF",  # FedEx International Economy Freight
    "REF",  # FedEx Regional Economy Freight
]


class ShipmentBase(BaseModel):
    order_reference: str
    account_id: int
    shipper_id: int
    service_type: AllowedService = Field(
        ...,
        description="FedEx service code (FIP, IPE, FIE, RE, PO, FICP, IPF, IEF, REF)",
    )
    recipient_name: str
    recipient_company: Optional[str] = None
    recipient_phone: str
    recipient_email: Optional[str] = None
    recipient_address: str
    recipient_city: str
    recipient_state_code: str
    recipient_postal_code: str
    recipient_country: str
    weight_kg: float


class ShipmentCreate(ShipmentBase):
    pass


class ShipmentRead(ShipmentBase):
    id: int
    price_quote: float
    tracking_number: str
    label_path: str
    status: str
    created_at: datetime
    shipper: "ShipperRead"
    account: AccountRead

    class Config:
        orm_mode = True


class RateRequest(BaseModel):
    account_id: int
    shipper_id: int
    service_type: AllowedService
    weight_kg: float
    destination_country: str


class RateResponse(BaseModel):
    account_id: int
    service_type: str
    currency: str
    amount: float


class PaginatedShipments(BaseModel):
    items: List[ShipmentRead]
    total: int


class ShipperBase(BaseModel):
    name: str
    company: Optional[str] = None
    person_name: str
    phone_number: str
    email: Optional[str] = None
    street_lines: str = Field(..., description="Street lines separated by commas if multiple")
    city: str
    state_code: str
    postal_code: str
    country_code: str


class ShipperCreate(ShipperBase):
    pass


class ShipperRead(ShipperBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True


ShipmentRead.update_forward_refs()
