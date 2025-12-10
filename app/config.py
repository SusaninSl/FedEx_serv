import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LABEL_DIR = BASE_DIR / "labels"
FEDEX_BASE_URL = os.getenv("FEDEX_BASE_URL", "https://apis-sandbox.fedex.com")
# FEDEX_BASE_URL = os.getenv("FEDEX_BASE_URL", "https://webhook.site/0aa78e88-b482-4051-a2a2-cb5580c31ead")

DATA_DIR.mkdir(parents=True, exist_ok=True)
LABEL_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'app.db'}")
SERVICE_TOKEN = os.getenv("SERVICE_TOKEN", "fedex-secret-123")


def get_service_token() -> str:
    return SERVICE_TOKEN
