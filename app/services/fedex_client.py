import base64
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx
from fastapi import HTTPException, status

from app.config import FEDEX_BASE_URL, LABEL_DIR
from app.models import ApiLog

ServiceType = Literal[
    "FIP",
    "IPE",
    "FIE",
    "RE",
    "PO",
    "FICP",
    "IPF",
    "IEF",
    "REF",
]

SERVICE_TYPE_MAP = {
    "FIP": "INTERNATIONAL_PRIORITY",
    "IPE": "INTERNATIONAL_PRIORITY_EXPRESS",
    "FIE": "INTERNATIONAL_ECONOMY",
    "RE": "INTERNATIONAL_ECONOMY",
    "PO": "PRIORITY_OVERNIGHT",
    "FICP": "INTERNATIONAL_CONNECT_PLUS",
    "IPF": "INTERNATIONAL_PRIORITY_FREIGHT",
    "IEF": "INTERNATIONAL_ECONOMY_FREIGHT",
    "REF": "INTERNATIONAL_ECONOMY_FREIGHT",
}


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
    currency: str = "EUR"


class FedExClient:
    def __init__(self, account: FedExAccount, db):
        self.account = account
        self.db = db
        self.base_url = FEDEX_BASE_URL.rstrip("/")
        self._access_token: str | None = None
        self._token_expiry: float = 0
        self._http = httpx.Client(base_url=self.base_url, timeout=30.0)

    def _log_interaction(
        self,
        endpoint: str,
        method: str,
        request_payload: dict | str | None,
        response_status: int | None,
        response_payload: str,
    ) -> None:
        log = ApiLog(
            account_id=self.account.id if self.account else None,
            endpoint=endpoint,
            method=method,
            request_payload=json.dumps(request_payload, ensure_ascii=False)
            if isinstance(request_payload, (dict, list))
            else (request_payload or ""),
            response_payload=response_payload,
            status_code=response_status,
        )
        self.db.add(log)
        self.db.commit()

    def _get_access_token(self) -> str:
        if self._access_token and time.time() < self._token_expiry - 30:
            return self._access_token

        data = {
            "grant_type": "client_credentials",
            "client_id": self.account.api_key,
            "client_secret": self.account.api_secret,
        }
        url = "/oauth/token"
        response = self._http.post(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        self._log_interaction(url, "POST", data, response.status_code, response.text)

        if response.status_code != status.HTTP_200_OK:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"FedEx auth failed: {response.text}",
            )
        payload = response.json()
        self._access_token = payload.get("access_token")
        expires_in = payload.get("expires_in", 3600)
        self._token_expiry = time.time() + expires_in

        if not self._access_token:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="FedEx auth token missing")
        return self._access_token

    def _auth_headers(self) -> dict[str, str]:
        token = self._get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def get_rate(self, weight_kg: float, destination_country: str, service_type: ServiceType) -> RateQuote:
        if service_type not in SERVICE_TYPE_MAP:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported service type")

        body = {
            "accountNumber": {"value": self.account.account_number},
            "requestedShipment": {
                "shipper": {
                    "address": {
                        "postalCode": "03042",
                        "countryCode": "DE",
                    }
                },
                "recipient": {
                    "address": {
                        "countryCode": destination_country,
                    }
                },
                "serviceType": SERVICE_TYPE_MAP[service_type],
                "pickupType": "USE_SCHEDULED_PICKUP",
                "requestedPackageLineItems": [
                    {
                        "weight": {
                            "units": "KG",
                            "value": weight_kg,
                        }
                    }
                ],
                "preferredCurrency": "EUR",
            },
        }
        url = "/rate/v1/rates/quotes"
        response = self._http.post(url, headers=self._auth_headers(), json=body)
        self._log_interaction(url, "POST", body, response.status_code, response.text)

        if response.status_code != status.HTTP_200_OK:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"FedEx rate error: {response.text}",
            )

        payload = response.json()
        amount = None
        currency = "USD"
        try:
            details = payload["output"]["rateReplyDetails"][0]
            rated = details.get("ratedShipmentDetails", [])[0].get("totalNetCharge", {})
            amount = float(rated.get("amount"))
            currency = rated.get("currency") or currency
        except Exception:
            pass

        if amount is None:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="FedEx rate missing in response")

        return RateQuote(amount=amount, currency=currency)

    def create_shipment(self, shipment_id: int, destination: str, service_type: ServiceType, recipient: dict) -> tuple[str, str]:
        if service_type not in SERVICE_TYPE_MAP:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported service type")

        body = {
            "labelResponseOptions": "LABEL",
            "requestedShipment": {
                "shipper": {
                    "contact": {"personName": self.account.name},
                    "address": {
                        "streetLines": ["Merzdorfer Weg 4"],
                        "city": "Cottbus",
                        "postalCode": "03042",
                        "countryCode": "DE",
                    },
                },
                "recipients": [
                    {
                        "contact": {"personName": recipient.get("name")},
                        "address": {
                            "streetLines": [recipient.get("address")],
                            "city": recipient.get("city"),
                            "countryCode": recipient.get("country"),
                        },
                    }
                ],
                "serviceType": SERVICE_TYPE_MAP[service_type],
                "packagingType": "YOUR_PACKAGING",
                "pickupType": "USE_SCHEDULED_PICKUP",
                "shippingChargesPayment": {
                    "paymentType": "SENDER",
                    "payor": {"responsibleParty": {"accountNumber": {"value": self.account.account_number}}},
                },
                "labelSpecification": {
                    "imageType": "PDF",
                    "labelStockType": "PAPER_4X6",
                },
                "requestedPackageLineItems": [
                    {
                        "weight": {"units": "KG", "value": float(recipient.get("weight", 1))},
                    }
                ],
            },
        }
        url = "/ship/v1/shipments"
        response = self._http.post(url, headers=self._auth_headers(), json=body)
        self._log_interaction(url, "POST", body, response.status_code, response.text)

        if response.status_code not in (status.HTTP_200_OK, status.HTTP_201_CREATED):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"FedEx shipment error: {response.text}",
            )

        payload = response.json()
        tracking_number = self._extract_tracking(payload)
        label_path = self._save_label(payload, shipment_id, destination, service_type)

        if not tracking_number:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="FedEx tracking missing in response")

        return tracking_number, label_path

    def _extract_tracking(self, payload: dict) -> str | None:
        try:
            shipments = payload.get("output", {}).get("transactionShipments", [])
            if shipments:
                master = shipments[0].get("masterTrackingNumber")
                if master:
                    return master
                piece_responses = shipments[0].get("pieceResponses", [])
                if piece_responses:
                    return piece_responses[0].get("trackingNumber")
        except Exception:
            return None
        return None

    def _save_label(self, payload: dict, shipment_id: int, destination: str, service_type: ServiceType) -> str:
        label_bytes: bytes | None = None
        try:
            shipments = payload.get("output", {}).get("transactionShipments", [])
            if shipments:
                docs = shipments[0].get("pieceResponses", [])[0].get("packageDocuments", [])
                if docs:
                    encoded = docs[0].get("encodedLabel")
                    if encoded:
                        label_bytes = base64.b64decode(encoded)
        except Exception:
            label_bytes = None

        LABEL_DIR.mkdir(parents=True, exist_ok=True)
        label_path = LABEL_DIR / f"label_{shipment_id}.pdf"

        if label_bytes:
            Path(label_path).write_bytes(label_bytes)
        else:
            fallback = (
                f"FedEx Shipment\nID: {shipment_id}\nDestination: {destination}\nService: {service_type}"
            ).encode()
            Path(label_path).write_bytes(fallback)

        return str(label_path)
