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
    "RETURNS",  # FedEx Global Returns
]


class CommodityItem(BaseModel):
    description: str
    quantity: Optional[float] = Field(None, description="Quantity of the item")
    price: Optional[float] = Field(None, description="Unit price in sender currency")
    weight_kg: Optional[float] = Field(None, description="Item weight in KG")


class ETDDocument(BaseModel):
    name: str = Field(..., description="Original filename or identifier")
    content_base64: str = Field(..., description="Base64-encoded file content")
    doc_type: str = Field("COMMERCIAL_INVOICE", description="FedEx document type")


class ShipmentBase(BaseModel):
    order_reference: str
    account_id: int
    shipper_id: int
    broker_id: Optional[int] = Field(None, description="Broker to use for BSO")
    service_type: AllowedService = Field(
        ...,
        description="FedEx service code (FIP, IPE, FIE, RE, PO, FICP, IPF, IEF, REF, RETURNS)",
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
    broker_select_option: bool = Field(
        False, description="Enable International Broker Select Option (requires broker_id)"
    )
    third_party_consignee: bool = Field(False, description="Enable FedEx Third Party Consignee")
    ship_alert_emails: Optional[List[str]] = Field(
        None,
        description="Email notifications for ShipAlert; set to [] or omit to disable",
    )
    etd_documents: Optional[List["ETDDocument"]] = Field(
        None, description="Electronic Trade Documents for customer upload"
    )
    is_return: bool = Field(False, description="Mark shipment as FedEx Global Return")
    return_reference: Optional[str] = Field(
        None, description="Optional reference to the original order for returns"
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
    broker: Optional["BrokerRead"] = None
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

    @validator("ship_alert_emails", pre=True)
    def _parse_emails(cls, value):
        if value is None:
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return None
        return value

    @validator("etd_documents", pre=True)
    def _parse_etd(cls, value):
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
    service_type: Optional[AllowedService] = Field(
        None,
        description=(
            "Optional service code (FIP, IPE, FIE, RE, PO, FICP, IPF, IEF, REF); "
            "omit to get all available services"
        ),
    )
    weight_kg: float
    destination_postal_code: str
    destination_country: str


class RateQuote(BaseModel):
    service_type: str
    currency: str
    amount: float


class RateResponse(BaseModel):
    account_id: int
    service_type: str
    currency: str
    amount: float


class RateListResponse(BaseModel):
    account_id: int
    quotes: List[RateQuote]


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
    ship_alert_emails: Optional[List[str]] = None
    etd_documents: Optional[List[ETDDocument]] = None


class ShipmentTestResult(BaseModel):
    service_type: AllowedService
    status: str
    shipment: Optional[ShipmentRead] = None
    error: Optional[str] = None

    class Config:
        orm_mode = True


class ShipmentTestResponse(BaseModel):
    results: List[ShipmentTestResult]


class ReturnShipmentCreate(BaseModel):
    order_reference: str
    account_id: int
    warehouse_shipper_id: int = Field(..., description="Warehouse (shipper) receiving the return")
    service_type: AllowedService = Field("RETURNS", description="Return service code")
    customer_name: str
    customer_company: Optional[str] = None
    customer_phone: str
    customer_email: Optional[str] = None
    customer_address: str
    customer_city: str
    customer_state_code: str
    customer_postal_code: str
    customer_country: str
    weight_kg: float
    customs_required: bool = True
    customs_items: Optional[List[CommodityItem]] = None
    ship_alert_emails: Optional[List[str]] = None
    etd_documents: Optional[List[ETDDocument]] = None
    return_reference: Optional[str] = None


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


class BrokerBase(BaseModel):
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


class BrokerCreate(BrokerBase):
    pass


class BrokerRead(BrokerBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True


class TrackingRequest(BaseModel):
    account_id: int
    tracking_number: str


class TrackingResponse(BaseModel):
    tracking_number: str
    raw_detail: dict


class SpodResponse(BaseModel):
    tracking_number: str
    proof_path: str


ShipmentRead.update_forward_refs(ShipperRead=ShipperRead, BrokerRead=BrokerRead, ETDDocument=ETDDocument)
