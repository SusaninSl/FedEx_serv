from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    account_number = Column(String(50), nullable=False)
    meter_number = Column(String(50), nullable=True)
    api_key = Column(String(255), nullable=False)
    api_secret = Column(String(255), nullable=False)
    is_freight = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    shipments = relationship("Shipment", back_populates="account")


class Shipper(Base):
    __tablename__ = "shippers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    company = Column(String(255), nullable=True)
    person_name = Column(String(255), nullable=False)
    phone_number = Column(String(50), nullable=False)
    email = Column(String(255), nullable=True)
    street_lines = Column(Text, nullable=False)
    city = Column(String(100), nullable=False)
    state_code = Column(String(10), nullable=False)
    postal_code = Column(String(20), nullable=False)
    country_code = Column(String(10), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    shipments = relationship("Shipment", back_populates="shipper")


class Shipment(Base):
    __tablename__ = "shipments"

    id = Column(Integer, primary_key=True, index=True)
    order_reference = Column(String(100), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    shipper_id = Column(Integer, ForeignKey("shippers.id"), nullable=False)
    service_type = Column(String(50), nullable=False)
    recipient_name = Column(String(255), nullable=False)
    recipient_company = Column(String(255), nullable=True)
    recipient_phone = Column(String(50), nullable=False)
    recipient_email = Column(String(255), nullable=True)
    recipient_address = Column(Text, nullable=False)
    recipient_city = Column(String(100), nullable=False)
    recipient_state_code = Column(String(10), nullable=False)
    recipient_postal_code = Column(String(20), nullable=False)
    recipient_country = Column(String(100), nullable=False)
    weight_kg = Column(Float, nullable=False)
    customs_items = Column(Text, nullable=True)
    price_quote = Column(Numeric(10, 2), nullable=True)
    tracking_number = Column(String(100), nullable=False)
    label_path = Column(String(255), nullable=False)
    status = Column(String(50), default="created")
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("Account", back_populates="shipments")
    shipper = relationship("Shipper", back_populates="shipments")


class ApiLog(Base):
    __tablename__ = "api_logs"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    endpoint = Column(String(255), nullable=False)
    method = Column(String(10), nullable=False)
    request_payload = Column(Text, nullable=True)
    response_payload = Column(Text, nullable=True)
    status_code = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
