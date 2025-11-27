from datetime import datetime
from typing import List, Optional

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


class ShipmentBase(BaseModel):
    order_reference: str
    account_id: int
    service_type: str = Field(..., description="fedex_standard or fedex_freight")
    recipient_name: str
    recipient_address: str
    recipient_city: str
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
    account: AccountRead

    class Config:
        orm_mode = True


class RateRequest(BaseModel):
    account_id: int
    service_type: str = Field(..., description="fedex_standard or fedex_freight")
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
