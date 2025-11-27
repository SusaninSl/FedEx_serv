import random
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fpdf import FPDF

from app.config import LABEL_DIR

ServiceType = Literal["fedex_standard", "fedex_freight"]


@dataclass
class FedExAccount:
    id: int
    name: str
    account_number: str
    meter_number: str | None
    api_key: str
    api_secret: str
    is_freight: bool


@dataclass
class RateQuote:
    amount: float
    currency: str = "USD"


class LabelRenderer:
    @staticmethod
    def render_pdf(shipment_id: int, tracking_number: str, destination: str, service_type: ServiceType) -> str:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=14)
        pdf.cell(200, 10, txt="FedEx Shipment Label", ln=True, align="C")
        pdf.ln(4)
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt=f"Shipment ID: {shipment_id}", ln=True)
        pdf.cell(200, 10, txt=f"Tracking: {tracking_number}", ln=True)
        pdf.cell(200, 10, txt=f"Destination: {destination}", ln=True)
        pdf.cell(200, 10, txt=f"Service: {service_type}", ln=True)

        LABEL_DIR.mkdir(parents=True, exist_ok=True)
        label_path = LABEL_DIR / f"label_{shipment_id}.pdf"
        pdf.output(str(label_path))
        return str(label_path)


class FedExClient:
    def __init__(self, account: FedExAccount):
        self.account = account

    def get_rate(self, weight_kg: float, destination_country: str, service_type: ServiceType) -> RateQuote:
        base_rate = 15.0 if service_type == "fedex_standard" else 35.0
        zone_multiplier = 1.0 if destination_country.lower() == "usa" else 1.25
        freight_multiplier = 1.4 if self.account.is_freight else 1.0
        weight_multiplier = max(1.0, weight_kg / 2)

        amount = round(base_rate * zone_multiplier * freight_multiplier * weight_multiplier, 2)
        return RateQuote(amount=amount)

    def create_shipment(self, shipment_id: int, destination: str, service_type: ServiceType) -> str:
        tracking_prefix = "FXF" if self.account.is_freight else "FDX"
        tracking_number = f"{tracking_prefix}-" + self._random_string(10)
        label_path = LabelRenderer.render_pdf(shipment_id, tracking_number, destination, service_type)
        return tracking_number, label_path

    @staticmethod
    def _random_string(length: int) -> str:
        return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))
