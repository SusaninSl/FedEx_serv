from datetime import datetime
import json
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, validator


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


class CommodityItem(BaseModel):
    description: str
    quantity: Optional[float] = Field(None, description="Quantity of the item")
    price: Optional[float] = Field(None, description="Unit price in sender currency")
    weight_kg: Optional[float] = Field(None, description="Item weight in KG")


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
    customs_required: bool = Field(
        True,
        description="1 to include customsClearanceDetail, 0 to skip customs data",
    )
    customs_items: Optional[List[CommodityItem]] = Field(
        None,
        description=(
            "Commodity lines for customs; description required, quantity/price/weight optional"
        ),
    )


class ShipmentCreate(ShipmentBase):
    pass


class ShipmentRead(ShipmentBase):
    id: int
    price_quote: Optional[float] = None
    tracking_number: str
    label_path: str
    status: str
    created_at: datetime
    customs_required: bool
    shipper: "ShipperRead"
    account: AccountRead

    class Config:
        orm_mode = True

    @validator("customs_items", pre=True)
    def _parse_customs_items(cls, value):
        if value is None:
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return None
        return value


class RateRequest(BaseModel):
    account_id: int
    shipper_id: int
    service_type: AllowedService
    weight_kg: float
    destination_postal_code: str
    destination_country: str


class RateResponse(BaseModel):
    account_id: int
    service_type: str
    currency: str
    amount: float


class ShipmentTestRequest(BaseModel):
    account_id: int
    shipper_id: int
    order_reference_prefix: str
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
    customs_required: bool = True
    customs_items: Optional[List[CommodityItem]] = None


class ShipmentTestResult(BaseModel):
    service_type: AllowedService
    status: str
    shipment: Optional[ShipmentRead] = None
    error: Optional[str] = None

    class Config:
        orm_mode = True


class ShipmentTestResponse(BaseModel):
    results: List[ShipmentTestResult]


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
