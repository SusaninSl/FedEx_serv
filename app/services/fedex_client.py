import base64
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx
from fastapi import HTTPException, status

from app.config import FEDEX_BASE_URL, LABEL_DIR, LOG_DIR
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
    "RETURNS",
    "FIRST",
    "FP"
]

SERVICE_TYPE_MAP = {
    "FIP": "INTERNATIONAL_PRIORITY",
    "IPE": "INTERNATIONAL_PRIORITY_EXPRESS",
    "FIE": "INTERNATIONAL_ECONOMY",
    "RE": "FEDEX_REGIONAL_ECONOMY",
    "PO": "PRIORITY_OVERNIGHT",
    "FICP": "FEDEX_INTERNATIONAL_CONNECT_PLUS",
    "IPF": "INTERNATIONAL_PRIORITY_FREIGHT",
    "IEF": "INTERNATIONAL_ECONOMY_FREIGHT",
    "REF": "INTERNATIONAL_ECONOMY_FREIGHT",
    "RETURNS": "INTERNATIONAL_PRIORITY",
    "FIRST": "FEDEX_FIRST",
    "FP": "FEDEX_PRIORITY",
}

SERVICE_TYPE_REVERSE_MAP = {
    "INTERNATIONAL_PRIORITY": "FIP",
    "INTERNATIONAL_PRIORITY_EXPRESS": "IPE",
    "INTERNATIONAL_ECONOMY": "FIE",
    "FEDEX_REGIONAL_ECONOMY": "RE",
    "PRIORITY_OVERNIGHT": "PO",
    "FEDEX_INTERNATIONAL_CONNECT_PLUS": "FICP",
    "INTERNATIONAL_PRIORITY_FREIGHT": "IPF",
    "INTERNATIONAL_ECONOMY_FREIGHT": "IEF",
    "FEDEX_FIRST": "FIRST",
    "FEDEX_PRIORITY": "FP",
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
    service_type: str
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
        timestamp_ms = int(time.time() * 1000)
        safe_endpoint = endpoint.strip("/").replace("/", "-") or "root"
        log_file = LOG_DIR / f"{timestamp_ms}_{method.upper()}_{safe_endpoint}.json"
        log_file.write_text(
            json.dumps(
                {
                    "timestamp": timestamp_ms,
                    "account_id": self.account.id if self.account else None,
                    "endpoint": endpoint,
                    "method": method,
                    "request": request_payload,
                    "response_status": response_status,
                    "response": response_payload,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

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

    def _shipper_address(self, shipper) -> dict:
        return {
            "contact": {
                "personName": shipper.person_name,
                "companyName": shipper.company,
                "phoneNumber": shipper.phone_number,
                "emailAddress": shipper.email,
            },
            "address": {
                "streetLines": [line.strip() for line in shipper.street_lines.split(",") if line.strip()],
                "city": shipper.city,
                "stateOrProvinceCode": shipper.state_code,
                "postalCode": shipper.postal_code,
                "countryCode": shipper.country_code,
            },
        }

    def _shipper_object(self, shipper) -> dict:
        return self._shipper_address(shipper)

    def get_rate(
        self,
        weight_kg: float,
        shipper,
        recipient: dict,
        service_type: ServiceType | None,
    ) -> list[RateQuote]:
        if service_type and service_type not in SERVICE_TYPE_MAP:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported service type")

        body = {
            "accountNumber": {"value": self.account.account_number},
            "requestedShipment": {
                "shipper": self._shipper_address(shipper),
                },
                "recipient": {
                    "address": {
                        "postalCode": recipient.get("postal_code"),
                        "countryCode": recipient.get("country"),
                    }
                },
                "pickupType": "USE_SCHEDULED_PICKUP",
                "rateRequestType": ["ACCOUNT", "LIST"],
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
        if service_type:
            body["requestedShipment"]["serviceType"] = SERVICE_TYPE_MAP[service_type]
        url = "/rate/v1/rates/quotes"
        response = self._http.post(url, headers=self._auth_headers(), json=body)
        self._log_interaction(url, "POST", body, response.status_code, response.text)

        if response.status_code != status.HTTP_200_OK:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"FedEx rate error: {response.text}",
            )
        payload = response.json()
        quotes: list[RateQuote] = []
        try:
            details_list = payload.get("output", {}).get("rateReplyDetails", [])
            for details in details_list:
                fedex_service = details.get("serviceType")
                service_code = service_type or SERVICE_TYPE_REVERSE_MAP.get(fedex_service, fedex_service or "")
                rated = details.get("ratedShipmentDetails", [])
                if not rated:
                    continue
                total_charge = rated[0].get("totalNetCharge", {})
                currency = rated[0].get("currency", {})
                amount = total_charge
                if amount is None:
                    continue
                quotes.append(
                    RateQuote(
                        service_type=service_code,
                        amount=float(amount),
                        currency=currency,
                    )
                )
        except Exception:
            quotes = []

        if service_type and not quotes:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="FedEx rate missing in response")

        if not quotes:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="FedEx rate missing in response")

        return quotes

    def create_shipment(
        self,
        shipment_id: int,
        destination: str,
        service_type: ServiceType,
        recipient: dict,
        shipper,
        include_customs: bool,
        commodities: list | None = None,
        broker=None,
        broker_option: bool = False,
        third_party_consignee: bool = False,
        ship_alert_emails: list[str] | None = None,
        etd_documents: list[dict] | None = None,
        is_return: bool = False,
        return_reference: str | None = None,
    ) -> tuple[str, str]:
        if service_type not in SERVICE_TYPE_MAP:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported service type")

        commodity_lines: list[dict] = []
        if include_customs:
            if commodities:
                for item in commodities:
                    try:
                        data = item.dict(exclude_none=True)
                    except AttributeError:
                        data = item
                    line: dict = {"description": data.get("description")}
                    quantity = data.get("quantity")
                    if quantity:
                        line["quantity"] = quantity
                        line["quantityUnits"] = "PCS"
                    if data.get("price") is not None:
                        line["unitPrice"] = {"currency": "EUR", "amount": data.get("price")}
                        if quantity:
                            line["customsValue"] = {
                                "currency": "EUR",
                                "amount": data.get("price") * quantity,
                            }
                    weight_value = data.get("weight_kg") or data.get("weight")
                    if weight_value:
                        line["weight"] = {"units": "KG", "value": float(weight_value)}
                    commodity_lines.append(line)

            if not commodity_lines:
                commodity_lines.append(
                    {
                        "description": "PVC Window",
                        "quantity": 1,
                        "quantityUnits": "PCS",
                        "weight": {"units": "KG", "value": float(recipient.get("weight", 10))},
                    }
                )

        body = {
            "accountNumber": {"value": self.account.account_number},
            "labelResponseOptions": "LABEL",
            "mergeLabelDocOption": "LABELS_ONLY",
            "requestedShipment": {
                "shipper": self._shipper_object(shipper),
                "recipients": [
                    {
                        "contact": {
                            "personName": recipient.get("name"),
                            "companyName": recipient.get("company"),
                            "phoneNumber": recipient.get("phone"),
                            "emailAddress": recipient.get("email"),
                        },
                        "address": {
                            "streetLines": [recipient.get("address")],
                            "city": recipient.get("city"),
                            "stateOrProvinceCode": recipient.get("state_code"),
                            "postalCode": recipient.get("postal_code"),
                            "countryCode": recipient.get("country"),
                        },
                    }
                ],
                "serviceType": actual_service,
                "packagingType": "YOUR_PACKAGING",
                "pickupType": "USE_SCHEDULED_PICKUP",
                "shippingChargesPayment": {
                    "paymentType": "SENDER",
                    "payor": {"responsibleParty": {"accountNumber": {"value": self.account.account_number}}},
                },
                "labelSpecification": {
                    "imageType": "PDF",
                    "labelFormatType": "COMMON2D",
                    "labelStockType": "PAPER_4X6",
                },
                "requestedPackageLineItems": [
                    {
                        "weight": {"units": "KG", "value": float(recipient.get("weight", 1))},
                    }
                ],
            },
        }

        if is_return:
            body["requestedShipment"]["serviceType"] = SERVICE_TYPE_MAP.get("RETURNS", actual_service)
            body["requestedShipment"]["returnShipmentDetail"] = {
                "returnType": "PRINT_RETURN_LABEL",
                "rma": {"reason": return_reference or "Customer return"},
            }

        if service_type in {"IPF", "IEF", "REF"}:
            body["requestedShipment"]["totalWeight"] = {
                "units": "KG",
                "value": float(recipient.get("weight", 1)),
            }

        special_service_types: list[str] = []
        special_service_detail: dict = {}

        if broker_option and broker:
            special_service_types.append("BROKER_SELECT_OPTION")
            special_service_detail["brokerDetail"] = {
                "type": "BROKER_OF_CHOICE",
                "broker": self._shipper_object(broker),
            }

        if third_party_consignee:
            special_service_types.append("THIRD_PARTY_CONSIGNEE")

        if ship_alert_emails:
            special_service_types.append("EMAIL_NOTIFICATION")
            special_service_detail["emailNotificationDetail"] = {
                "aggregationType": "PER_SHIPMENT",
                "emailRecipients": [
                    {
                        "emailAddress": email,
                        "role": "RECIPIENT",
                        "notificationFormatType": "HTML",
                        "notificationEventType": [
                            "ON_SHIPMENT", "ON_DELIVERY", "ON_EXCEPTION",
                        ],
                    }
                    for email in ship_alert_emails
                    if email
                ],
            }

        if etd_documents:
            special_service_types.append("ELECTRONIC_TRADE_DOCUMENTS")
            body["requestedShipment"]["shippingDocumentSpecification"] = {
                "shippingDocumentTypes": list({doc.get("doc_type", "COMMERCIAL_INVOICE") for doc in etd_documents}),
                "commercialInvoiceDetail": {
                    "customerImageUsages": [
                        {
                            "type": "SIGNATURE_IMAGE",
                            "id": "SIGNATURE",
                        }
                    ]
                },
            }
            body["requestedShipment"]["documentUploads"] = [
                {
                    "documentType": doc.get("doc_type", "COMMERCIAL_INVOICE"),
                    "fileName": doc.get("name"),
                    "documentContent": doc.get("content_base64"),
                }
                for doc in etd_documents
            ]

        if special_service_types:
            body["requestedShipment"]["shipmentSpecialServices"] = {
                "specialServiceTypes": special_service_types,
                **special_service_detail,
            }

        if include_customs:
            body["requestedShipment"]["customsClearanceDetail"] = {
                "commercialInvoice": {
                    "shipmentPurpose": "SOLD",
                    "customerReferences": [
                        {"customerReferenceType": "INVOICE_NUMBER", "value": f"INV-{shipment_id}"}
                    ],
                    "comments": ["Generate invoice via FedEx"],
                },
                "commodities": commodity_lines,
                "dutiesPayment": {
                    "paymentType": "SENDER",
                    "payor": {
                        "responsibleParty": {"accountNumber": {"value": self.account.account_number}}
                    },
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

    def track_shipment(self, tracking_number: str) -> dict:
        body = {
            "includeDetailedScans": True,
            "trackingInfo": [
                {
                    "trackingNumberInfo": {
                        "trackingNumber": tracking_number,
                    }
                }
            ],
        }
        url = "/track/v1/trackingnumbers"
        response = self._http.post(url, headers=self._auth_headers(), json=body)
        self._log_interaction(url, "POST", body, response.status_code, response.text)

        if response.status_code != status.HTTP_200_OK:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"FedEx tracking error: {response.text}",
            )
        return response.json()

    def request_spod(self, tracking_number: str, save_path: Path) -> str:
        body = {
            "trackingInfo": [
                {
                    "trackingNumberInfo": {
                        "trackingNumber": tracking_number,
                    }
                }
            ],
            "format": "PDF",
        }
        url = "/track/v1/proof-of-delivery"
        response = self._http.post(url, headers=self._auth_headers(), json=body)
        self._log_interaction(url, "POST", body, response.status_code, response.text)

        if response.status_code != status.HTTP_200_OK:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"FedEx SPOD error: {response.text}",
            )
        payload = response.json()
        encoded = None
        try:
            encoded = (
                payload.get("output", {})
                .get("proofOfDeliveryDocuments", [])[0]
                .get("documentContent")
            )
        except Exception:
            encoded = None

        save_path.parent.mkdir(parents=True, exist_ok=True)
        if encoded:
            save_path.write_bytes(base64.b64decode(encoded))
        else:
            save_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        return str(save_path)
