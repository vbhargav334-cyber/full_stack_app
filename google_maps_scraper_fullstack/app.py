import io
import json
import logging
import math
import os
import re
import sqlite3
import smtplib
import sys
import threading
import time
import traceback
import uuid
import csv
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

# Load .env file from the project directory
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)

import pandas as pd
from flask import Flask, jsonify, request, send_file
from werkzeug.utils import secure_filename

from scraper import scrape_google_maps, scrape_place_links

# Configure logging
if sys.platform.startswith("win"):
    # Force UTF-8 for Windows console
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants (configurable via .env)
MAX_BULK_FILE_SIZE = int(os.environ.get("MAX_BULK_FILE_SIZE", "10")) * 1024 * 1024
MAX_CHECKPOINT_FILE_SIZE = int(os.environ.get("MAX_CHECKPOINT_FILE_SIZE", "50")) * 1024 * 1024

# Scraper defaults (configurable via .env)
DEFAULT_HEADLESS = os.environ.get("DEFAULT_HEADLESS", "True").lower() == "true"
DEFAULT_MAX_RETRIES = int(os.environ.get("DEFAULT_MAX_RETRIES", "3"))
DEFAULT_MIN_DELAY = float(os.environ.get("DEFAULT_MIN_DELAY", "0.9"))
DEFAULT_MAX_DELAY = float(os.environ.get("DEFAULT_MAX_DELAY", "1.8"))
ALLOWED_EXTENSIONS = {'.csv', '.xlsx', '.xls'}
MAX_CONCURRENT_JOBS = 5
ZIP_SWEEP_SEED_SUFFIXES = [
    "near me",
    "open now",
    "services",
    "company",
    "shop",
    "store",
    "local",
    "best",
    "top rated",
]
ZIP_SWEEP_FALLBACK_KEYWORDS = [
    "restaurant",
    "cafe",
    "bakery",
    "bar",
    "pizza",
    "dentist",
    "salon",
    "gym",
    "auto repair",
    "plumber",
    "electrician",
    "lawyer",
    "real estate agency",
    "insurance agency",
    "medical clinic",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resource_path(relative: str) -> str:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(getattr(sys, "_MEIPASS"))
    else:
        base = Path(__file__).resolve().parent
    return str((base / relative).resolve())


def _runtime_root_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


CHECKPOINT_DIR = _runtime_root_dir() / "checkpoints"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_DIR = _runtime_root_dir() / "history"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_MASTER_FILE = HISTORY_DIR / "latest_master.csv"
FRONTEND_DIR = _resource_path("frontend")
CRM_DB_FILE = _runtime_root_dir() / "crm.sqlite3"
LEGACY_CRM_JSON_FILE = _runtime_root_dir() / "mini_crm_leads.json"
CRM_JOB_FILES_DIR = _runtime_root_dir() / "crm_job_files"
CRM_JOB_FILES_DIR.mkdir(parents=True, exist_ok=True)
CRM_ALLOWED_STATUSES = ["new", "contacted", "qualified", "proposal", "won", "lost"]
LOCATION_DATA_DIR = _runtime_root_dir() / "data"
LOCATION_DATA_DIR.mkdir(parents=True, exist_ok=True)
LOCATION_ZIP_SOURCE_URLS = {
    "US": "https://download.geonames.org/export/zip/US.zip",
    "IN": "https://download.geonames.org/export/zip/IN.zip",
}
SUPPORTED_LOCATION_COUNTRIES = [
    {"code": "US", "name": "United States"},
    {"code": "IN", "name": "India"},
]
SUPPORTED_LOCATION_COUNTRY_CODES = {item["code"] for item in SUPPORTED_LOCATION_COUNTRIES}
PRESETS_DATA_FILE = _runtime_root_dir() / "saved_presets.json"
ZIP_PACKS_DATA_FILE = _runtime_root_dir() / "zip_packs.json"
NOTIFICATIONS_DATA_FILE = _runtime_root_dir() / "notifications_config.json"


def _write_json_atomic(
    target_path: Path,
    payload: Any,
    *,
    retries: int = 6,
    retry_delay_sec: float = 0.12,
) -> None:
    """Persist JSON with a Windows-friendly atomic write fallback."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    max_attempts = max(1, int(retries))

    for attempt in range(1, max_attempts + 1):
        tmp_path = target_path.with_name(f"{target_path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, target_path)
            return
        except PermissionError as exc:
            last_error = exc
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            if attempt < max_attempts:
                time.sleep(min(1.0, retry_delay_sec * attempt))
                continue
        except Exception:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise

    logger.warning(
        f"Atomic replace failed for {target_path.name}; falling back to direct write after retries. "
        f"Last error: {last_error}"
    )
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())


def validate_file_upload(file_storage, max_size: int, purpose: str) -> tuple[bool, str]:
    """Validate uploaded file for security and size."""
    if not file_storage or not file_storage.filename:
        return False, "No file provided"
    
    filename = secure_filename(file_storage.filename)
    ext = os.path.splitext(filename)[1].lower()
    
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
    
    # Check file size
    file_storage.seek(0, 2)
    file_size = file_storage.tell()
    file_storage.seek(0)
    
    if file_size > max_size:
        max_mb = max_size / (1024 * 1024)
        return False, f"File too large. Maximum {max_mb:.0f}MB allowed for {purpose}"
    
    if file_size == 0:
        return False, "File is empty"
    
    return True, filename


def _crm_clean_text(value: Any, max_len: int = 5000) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text[:max_len]


def _crm_clean_notes(value: Any, max_len: int = 8000) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text[:max_len]


def _crm_normalize_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    return status if status in CRM_ALLOWED_STATUSES else "new"


def _crm_normalize_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    # Keep only YYYY-MM-DD for follow-up date field.
    match = re.match(r"^\d{4}-\d{2}-\d{2}$", text)
    if match:
        return text
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.date().isoformat()
    except Exception:
        return ""


def _crm_clean_scraped_data(value: Any, max_keys: int = 800, max_value_len: int = 12000) -> Dict[str, str]:
    if not isinstance(value, dict):
        return {}
    cleaned: Dict[str, str] = {}
    for idx, (key, raw_val) in enumerate(value.items()):
        if idx >= max_keys:
            break
        clean_key = _crm_clean_text(key, max_len=160)
        if not clean_key:
            continue
        if raw_val is None:
            clean_val = ""
        elif isinstance(raw_val, (str, int, float, bool)):
            clean_val = _crm_clean_text(raw_val, max_len=max_value_len)
        else:
            try:
                clean_val = _crm_clean_text(
                    json.dumps(raw_val, ensure_ascii=False, default=str),
                    max_len=max_value_len,
                )
            except Exception:
                clean_val = _crm_clean_text(str(raw_val), max_len=max_value_len)
        cleaned[clean_key] = clean_val
    return cleaned


def _crm_segment_key(value: Any, max_len: int = 160) -> str:
    text = _crm_clean_text(value, max_len=max_len).lower()
    if not text:
        return "unknown"
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or "unknown"


def _crm_segment_zip_key(value: Any, max_len: int = 40) -> str:
    text = _crm_clean_text(value, max_len=max_len).lower()
    if not text:
        return "unknown"
    text = re.sub(r"[^0-9a-z-]+", "", text)
    return text or "unknown"


def _crm_identity_key(payload: Dict[str, Any]) -> str:
    place_id = _crm_clean_text(payload.get("place_id"), max_len=180).lower()
    maps_url = _crm_clean_text(payload.get("google_maps_url"), max_len=600)
    name = _crm_clean_text(payload.get("name"), max_len=200).lower()
    address = _crm_clean_text(payload.get("address"), max_len=300).lower()
    phone = re.sub(r"\D+", "", _crm_clean_text(payload.get("phone"), max_len=80))
    if place_id:
        return f"place:{place_id}"
    if maps_url:
        return f"url:{maps_url}"
    if phone and name:
        return f"phone_name:{phone}|{name}"
    if name and address:
        return f"name_addr:{name}|{address}"
    return ""


def _is_successful_result_row(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    if str(row.get("error", "")).strip():
        return False
    return True


def _successful_result_rows(rows: Any) -> List[Dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if _is_successful_result_row(row)]


def _failed_result_rows(rows: Any) -> List[Dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict) and str(row.get("error", "")).strip()]


class MiniCRMStore:
    def __init__(self, data_file: Path) -> None:
        self._data_file = data_file
        self._lock = threading.Lock()
        self._leads: Dict[str, Dict[str, Any]] = {}
        self._load()
        logger.info(f"MiniCRM initialized | leads={len(self._leads)}")

    def _load(self) -> None:
        if not self._data_file.exists():
            return
        try:
            with open(self._data_file, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as exc:
            logger.error(f"Failed to load mini CRM data: {exc}")
            return

        raw_items: List[Dict[str, Any]] = []
        if isinstance(payload, dict):
            if isinstance(payload.get("leads"), list):
                raw_items = [x for x in payload["leads"] if isinstance(x, dict)]
            else:
                raw_items = [x for x in payload.values() if isinstance(x, dict)]
        elif isinstance(payload, list):
            raw_items = [x for x in payload if isinstance(x, dict)]

        for item in raw_items:
            lead = self._build_lead(item, lead_id=str(item.get("lead_id", "")).strip() or str(uuid.uuid4()))
            self._leads[lead["lead_id"]] = lead

    def _save_locked(self) -> None:
        payload = {
            "version": 1,
            "updated_at": utc_now_iso(),
            "leads": list(self._leads.values()),
        }
        _write_json_atomic(self._data_file, payload)

    def _hydrate_segment_fields(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        category = _crm_clean_text(lead.get("category"), max_len=160)
        state = _crm_clean_text(lead.get("state"), max_len=120)
        city = _crm_clean_text(lead.get("city"), max_len=120)
        zip_code = _crm_clean_text(lead.get("zip_code"), max_len=40)

        lead["category"] = category
        lead["state"] = state
        lead["city"] = city
        lead["zip_code"] = zip_code

        lead["category_key"] = _crm_segment_key(lead.get("category_key") or category, max_len=160)
        lead["state_key"] = _crm_segment_key(lead.get("state_key") or state, max_len=120)
        lead["city_key"] = _crm_segment_key(lead.get("city_key") or city, max_len=120)
        lead["zip_key"] = _crm_segment_zip_key(lead.get("zip_key") or zip_code, max_len=40)
        return lead

    @staticmethod
    def _segment_bucket_item(lead: Dict[str, Any], segment: str) -> tuple[str, str]:
        if segment == "category":
            key = _crm_segment_key(lead.get("category_key") or lead.get("category"), max_len=160)
            label = _crm_clean_text(lead.get("category"), max_len=160) or "Unknown"
            return key, label
        if segment == "state":
            key = _crm_segment_key(lead.get("state_key") or lead.get("state"), max_len=120)
            label = _crm_clean_text(lead.get("state"), max_len=120) or "Unknown"
            return key, label
        if segment == "city":
            key = _crm_segment_key(lead.get("city_key") or lead.get("city"), max_len=120)
            label = _crm_clean_text(lead.get("city"), max_len=120) or "Unknown"
            return key, label
        if segment == "zip":
            key = _crm_segment_zip_key(lead.get("zip_key") or lead.get("zip_code"), max_len=40)
            label = _crm_clean_text(lead.get("zip_code"), max_len=40) or "Unknown"
            return key, label
        raise ValueError("invalid segment")

    def _collect_segment_options_from_rows(
        self,
        leads: List[Dict[str, Any]],
        segment: str,
        limit: int = 5000,
    ) -> List[Dict[str, Any]]:
        if segment not in {"category", "state", "city", "zip"}:
            raise ValueError("invalid segment")

        cap = max(1, min(int(limit), 10000))
        buckets: Dict[str, Dict[str, Any]] = {}
        for lead in leads:
            key, label = self._segment_bucket_item(lead, segment=segment)
            item = buckets.get(key)
            if not item:
                buckets[key] = {"value": key, "label": label, "count": 1}
                continue
            item["count"] = int(item.get("count", 0)) + 1
            if item.get("label") == "Unknown" and label != "Unknown":
                item["label"] = label

        items = list(buckets.values())
        items.sort(key=lambda x: (-int(x.get("count", 0)), str(x.get("label", "")).lower()))
        return items[:cap]

    def _compute_stats_for_rows(self, leads: List[Dict[str, Any]]) -> Dict[str, Any]:
        by_status = {status: 0 for status in CRM_ALLOWED_STATUSES}
        with_follow_up = 0
        for lead in leads:
            status = _crm_normalize_status(lead.get("status"))
            by_status[status] += 1
            if str(lead.get("next_follow_up", "")).strip():
                with_follow_up += 1
        return {
            "total": len(leads),
            "with_follow_up": with_follow_up,
            "by_status": by_status,
            "top_categories": self._collect_segment_options_from_rows(leads, segment="category", limit=25),
            "top_states": self._collect_segment_options_from_rows(leads, segment="state", limit=25),
        }

    def _build_lead(self, payload: Dict[str, Any], lead_id: str = "") -> Dict[str, Any]:
        now = utc_now_iso()
        created_at = _crm_clean_text(payload.get("created_at"), max_len=64) or now
        updated_at = _crm_clean_text(payload.get("updated_at"), max_len=64) or now
        lead = {
            "lead_id": lead_id or str(uuid.uuid4()),
            "created_at": created_at,
            "updated_at": updated_at,
            "source_job_id": _crm_clean_text(payload.get("source_job_id"), max_len=64),
            "source_job_created_at": _crm_clean_text(payload.get("source_job_created_at"), max_len=64),
            "source_record_id": _crm_clean_text(payload.get("source_record_id"), max_len=260),
            "name": _crm_clean_text(payload.get("name"), max_len=200),
            "category": _crm_clean_text(payload.get("category"), max_len=160),
            "category_key": _crm_clean_text(payload.get("category_key"), max_len=160),
            "phone": _crm_clean_text(payload.get("phone"), max_len=80),
            "email": _crm_clean_text(payload.get("email"), max_len=220),
            "website": _crm_clean_text(payload.get("website"), max_len=320),
            "address": _crm_clean_text(payload.get("address"), max_len=300),
            "city": _crm_clean_text(payload.get("city"), max_len=120),
            "city_key": _crm_clean_text(payload.get("city_key"), max_len=120),
            "state": _crm_clean_text(payload.get("state"), max_len=120),
            "state_key": _crm_clean_text(payload.get("state_key"), max_len=120),
            "zip_code": _crm_clean_text(payload.get("zip_code"), max_len=40),
            "zip_key": _crm_clean_text(payload.get("zip_key"), max_len=40),
            "status": _crm_normalize_status(payload.get("status")),
            "owner": _crm_clean_text(payload.get("owner"), max_len=120),
            "notes": _crm_clean_notes(payload.get("notes"), max_len=8000),
            "tags": _crm_clean_text(payload.get("tags"), max_len=400),
            "next_follow_up": _crm_normalize_date(payload.get("next_follow_up")),
            "last_contacted_at": _crm_clean_text(payload.get("last_contacted_at"), max_len=64),
            "lead_score": _crm_clean_text(payload.get("lead_score"), max_len=16),
            "lead_priority": _crm_clean_text(payload.get("lead_priority"), max_len=24),
            "place_id": _crm_clean_text(payload.get("place_id"), max_len=180),
            "feature_id": _crm_clean_text(payload.get("feature_id"), max_len=180),
            "google_maps_url": _crm_clean_text(payload.get("google_maps_url"), max_len=600),
            "final_email_source": _crm_clean_text(payload.get("final_email_source"), max_len=64),
            "scraped_data": _crm_clean_scraped_data(payload.get("scraped_data")),
        }
        return self._hydrate_segment_fields(lead)

    def _identity_index_locked(self) -> Dict[str, str]:
        index: Dict[str, str] = {}
        for lead_id, lead in self._leads.items():
            key = _crm_identity_key(lead)
            if key and key not in index:
                index[key] = lead_id
        return index

    def _source_record_index_locked(self) -> Dict[str, str]:
        index: Dict[str, str] = {}
        for lead_id, lead in self._leads.items():
            source_record_id = _crm_clean_text(lead.get("source_record_id"), max_len=260)
            if source_record_id and source_record_id not in index:
                index[source_record_id] = lead_id
        return index

    def _merge_import_locked(self, existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(existing)
        update_fields = [
            "source_job_id",
            "source_job_created_at",
            "source_record_id",
            "name",
            "category",
            "category_key",
            "phone",
            "email",
            "website",
            "address",
            "city",
            "city_key",
            "state",
            "state_key",
            "zip_code",
            "zip_key",
            "lead_score",
            "lead_priority",
            "place_id",
            "feature_id",
            "google_maps_url",
            "final_email_source",
        ]
        for field in update_fields:
            value = _crm_clean_text(incoming.get(field))
            if value:
                merged[field] = value
        incoming_scraped_data = _crm_clean_scraped_data(incoming.get("scraped_data"))
        if incoming_scraped_data:
            existing_scraped_data = _crm_clean_scraped_data(merged.get("scraped_data"))
            existing_scraped_data.update(incoming_scraped_data)
            merged["scraped_data"] = existing_scraped_data
        merged["updated_at"] = utc_now_iso()
        return self._hydrate_segment_fields(merged)

    def _row_to_import_payload(
        self,
        row: Dict[str, Any],
        source_job_id: str,
        source_job_created_at: str,
    ) -> Dict[str, Any]:
        email = _crm_clean_text(row.get("final_email"), max_len=220)
        if not email:
            email = _crm_clean_text(row.get("emails"), max_len=220)
        category = _crm_clean_text(row.get("category"), max_len=160) or _crm_clean_text(
            row.get("search_keyword"), max_len=160
        )
        city = _crm_clean_text(row.get("city"), max_len=120)
        state = _crm_clean_text(row.get("state"), max_len=120)
        zip_code = _crm_clean_text(row.get("zip_code"), max_len=40)
        return {
            "source_job_id": source_job_id,
            "source_job_created_at": source_job_created_at,
            "name": row.get("name"),
            "category": category,
            "category_key": _crm_segment_key(category, max_len=160),
            "phone": row.get("phone"),
            "email": email,
            "website": row.get("website"),
            "address": row.get("address"),
            "city": city,
            "city_key": _crm_segment_key(city, max_len=120),
            "state": state,
            "state_key": _crm_segment_key(state, max_len=120),
            "zip_code": zip_code,
            "zip_key": _crm_segment_zip_key(zip_code, max_len=40),
            "status": "new",
            "lead_score": row.get("lead_score"),
            "lead_priority": row.get("lead_priority"),
            "place_id": row.get("place_id"),
            "feature_id": row.get("feature_id"),
            "google_maps_url": row.get("google_maps_url"),
            "final_email_source": row.get("final_email_source"),
            "scraped_data": _crm_clean_scraped_data(row),
        }

    def list_leads(
        self,
        status: str = "",
        query: str = "",
        owner: str = "",
        category: str = "",
        state: str = "",
        city: str = "",
        zip_code: str = "",
        source_job_id: str = "",
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            leads = [self._hydrate_segment_fields(dict(v)) for v in self._leads.values()]

        status_filter = str(status or "").strip().lower()
        owner_filter = str(owner or "").strip().lower()
        category_filter_raw = str(category or "").strip().lower()
        state_filter_raw = str(state or "").strip().lower()
        city_filter_raw = str(city or "").strip().lower()
        zip_filter_raw = str(zip_code or "").strip().lower()
        job_filter = _crm_clean_text(source_job_id, max_len=64)
        q = str(query or "").strip().lower()

        category_filter = (
            _crm_segment_key(category_filter_raw, max_len=160)
            if category_filter_raw and category_filter_raw != "all"
            else ""
        )
        state_filter = (
            _crm_segment_key(state_filter_raw, max_len=120)
            if state_filter_raw and state_filter_raw != "all"
            else ""
        )
        city_filter = (
            _crm_segment_key(city_filter_raw, max_len=120)
            if city_filter_raw and city_filter_raw != "all"
            else ""
        )
        zip_filter = (
            _crm_segment_zip_key(zip_filter_raw, max_len=40)
            if zip_filter_raw and zip_filter_raw != "all"
            else ""
        )

        out: List[Dict[str, Any]] = []
        for lead in leads:
            if status_filter and status_filter != "all":
                if str(lead.get("status", "")).strip().lower() != status_filter:
                    continue
            if owner_filter:
                if owner_filter not in str(lead.get("owner", "")).strip().lower():
                    continue
            if category_filter:
                lead_category_key = _crm_segment_key(lead.get("category_key") or lead.get("category"), max_len=160)
                if lead_category_key != category_filter:
                    continue
            if state_filter:
                lead_state_key = _crm_segment_key(lead.get("state_key") or lead.get("state"), max_len=120)
                if lead_state_key != state_filter:
                    continue
            if city_filter:
                lead_city_key = _crm_segment_key(lead.get("city_key") or lead.get("city"), max_len=120)
                if lead_city_key != city_filter:
                    continue
            if zip_filter:
                lead_zip_key = _crm_segment_zip_key(lead.get("zip_key") or lead.get("zip_code"), max_len=40)
                if lead_zip_key != zip_filter:
                    continue
            if job_filter:
                if _crm_clean_text(lead.get("source_job_id"), max_len=64) != job_filter:
                    continue
            if q:
                hay = " | ".join(
                    [
                        str(lead.get("name", "")),
                        str(lead.get("category", "")),
                        str(lead.get("state", "")),
                        str(lead.get("city", "")),
                        str(lead.get("zip_code", "")),
                        str(lead.get("phone", "")),
                        str(lead.get("email", "")),
                        str(lead.get("address", "")),
                        str(lead.get("source_job_id", "")),
                        str(lead.get("owner", "")),
                        str(lead.get("notes", "")),
                        str(json.dumps(lead.get("scraped_data", {}), ensure_ascii=False)),
                    ]
                ).lower()
                if q not in hay:
                    continue
            out.append(lead)

        out.sort(key=lambda x: str(x.get("updated_at", "")), reverse=True)
        return out[: max(1, min(int(limit), 5000))]

    def get_filter_options(self, limit: int = 5000) -> Dict[str, Any]:
        with self._lock:
            leads = [self._hydrate_segment_fields(dict(v)) for v in self._leads.values()]
        return {
            "categories": self._collect_segment_options_from_rows(leads, segment="category", limit=limit),
            "states": self._collect_segment_options_from_rows(leads, segment="state", limit=limit),
            "cities": self._collect_segment_options_from_rows(leads, segment="city", limit=limit),
            "zips": self._collect_segment_options_from_rows(leads, segment="zip", limit=limit),
        }

    def segment_counts(self, group_by: str = "category", limit: int = 200) -> List[Dict[str, Any]]:
        segment = str(group_by or "").strip().lower()
        if segment not in {"category", "state", "city", "zip"}:
            raise ValueError("group_by must be one of: category, state, city, zip")
        with self._lock:
            leads = [self._hydrate_segment_fields(dict(v)) for v in self._leads.values()]
        return self._collect_segment_options_from_rows(leads, segment=segment, limit=limit)

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            leads = [self._hydrate_segment_fields(dict(v)) for v in self._leads.values()]
        return self._compute_stats_for_rows(leads)

    def get_stats_for_rows(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        normalized_rows = [self._hydrate_segment_fields(dict(row)) for row in (rows or []) if isinstance(row, dict)]
        return self._compute_stats_for_rows(normalized_rows)

    def create_or_merge(self, payload: Dict[str, Any]) -> tuple[Dict[str, Any], bool]:
        if not isinstance(payload, dict):
            raise ValueError("Invalid payload")
        lead = self._build_lead(payload)
        if not (lead["name"] or lead["phone"] or lead["email"]):
            raise ValueError("At least one of name, phone, or email is required")

        with self._lock:
            key = _crm_identity_key(lead)
            if key:
                identity_index = self._identity_index_locked()
                existing_id = identity_index.get(key)
                if existing_id and existing_id in self._leads:
                    merged = self._merge_import_locked(self._leads[existing_id], lead)
                    # Manual create should still be able to set status/owner/notes.
                    merged["status"] = _crm_normalize_status(payload.get("status", merged.get("status")))
                    merged["owner"] = _crm_clean_text(payload.get("owner"), max_len=120) or merged.get("owner", "")
                    merged["notes"] = _crm_clean_notes(payload.get("notes"), max_len=8000) or merged.get("notes", "")
                    merged["tags"] = _crm_clean_text(payload.get("tags"), max_len=400) or merged.get("tags", "")
                    follow_up = _crm_normalize_date(payload.get("next_follow_up"))
                    if follow_up:
                        merged["next_follow_up"] = follow_up
                    self._leads[existing_id] = merged
                    self._save_locked()
                    return dict(merged), False

            lead["created_at"] = utc_now_iso()
            lead["updated_at"] = lead["created_at"]
            self._leads[lead["lead_id"]] = lead
            self._save_locked()
            return dict(lead), True

    def update_lead(self, lead_id: str, patch: Dict[str, Any]) -> Dict[str, Any] | None:
        if not isinstance(patch, dict):
            return None
        with self._lock:
            existing = self._leads.get(lead_id)
            if not existing:
                return None
            updated = dict(existing)
            field_rules = {
                "name": lambda v: _crm_clean_text(v, max_len=200),
                "category": lambda v: _crm_clean_text(v, max_len=160),
                "phone": lambda v: _crm_clean_text(v, max_len=80),
                "email": lambda v: _crm_clean_text(v, max_len=220),
                "website": lambda v: _crm_clean_text(v, max_len=320),
                "address": lambda v: _crm_clean_text(v, max_len=300),
                "city": lambda v: _crm_clean_text(v, max_len=120),
                "state": lambda v: _crm_clean_text(v, max_len=120),
                "zip_code": lambda v: _crm_clean_text(v, max_len=40),
                "status": _crm_normalize_status,
                "owner": lambda v: _crm_clean_text(v, max_len=120),
                "notes": lambda v: _crm_clean_notes(v, max_len=8000),
                "tags": lambda v: _crm_clean_text(v, max_len=400),
                "next_follow_up": _crm_normalize_date,
                "last_contacted_at": lambda v: _crm_clean_text(v, max_len=64),
            }
            for field, cleaner in field_rules.items():
                if field in patch:
                    updated[field] = cleaner(patch.get(field))
            updated = self._hydrate_segment_fields(updated)
            updated["updated_at"] = utc_now_iso()
            self._leads[lead_id] = updated
            self._save_locked()
            return dict(updated)

    def delete_lead(self, lead_id: str) -> bool:
        with self._lock:
            if lead_id not in self._leads:
                return False
            self._leads.pop(lead_id, None)
            self._save_locked()
            return True

    def delete_by_job_id(self, source_job_id: str) -> Dict[str, Any]:
        job_id = _crm_clean_text(source_job_id, max_len=64)
        if not job_id:
            return {"job_id": "", "deleted": 0, "crm_total": len(self._leads)}

        with self._lock:
            target_ids = [
                lead_id
                for lead_id, lead in self._leads.items()
                if _crm_clean_text(lead.get("source_job_id"), max_len=64) == job_id
            ]
            for lead_id in target_ids:
                self._leads.pop(lead_id, None)
            if target_ids:
                self._save_locked()
            return {
                "job_id": job_id,
                "deleted": len(target_ids),
                "crm_total": len(self._leads),
            }

    def import_rows(
        self,
        rows: List[Dict[str, Any]],
        source_job_id: str,
        source_job_created_at: str = "",
        merge_existing: bool = False,
    ) -> Dict[str, Any]:
        imported = 0
        updated = 0
        skipped = 0
        total_rows = len(rows or [])

        with self._lock:
            identity_index = self._identity_index_locked()
            source_record_index = self._source_record_index_locked()
            for idx, row in enumerate(rows or []):
                if not isinstance(row, dict):
                    skipped += 1
                    continue
                if str(row.get("error", "")).strip():
                    skipped += 1
                    continue

                payload = self._row_to_import_payload(
                    row,
                    source_job_id=source_job_id,
                    source_job_created_at=source_job_created_at,
                )
                if not (
                    _crm_clean_text(payload.get("name"))
                    or _crm_clean_text(payload.get("phone"))
                    or _crm_clean_text(payload.get("email"))
                ):
                    skipped += 1
                    continue

                key = _crm_identity_key(payload)
                source_record_id = f"{source_job_id}|{key or f'row:{idx}'}"
                payload["source_record_id"] = source_record_id

                existing_id = source_record_index.get(source_record_id)
                if existing_id and existing_id in self._leads:
                    existing = self._leads.get(existing_id)
                    if not existing:
                        skipped += 1
                        continue
                    self._leads[existing_id] = self._merge_import_locked(existing, payload)
                    updated += 1
                    if key and key not in identity_index:
                        identity_index[key] = existing_id
                    continue

                if merge_existing and key and key in identity_index:
                    existing_id = identity_index[key]
                    existing = self._leads.get(existing_id)
                    if not existing:
                        skipped += 1
                        continue
                    self._leads[existing_id] = self._merge_import_locked(existing, payload)
                    updated += 1
                    continue

                new_lead = self._build_lead(payload, lead_id=str(uuid.uuid4()))
                new_lead["created_at"] = utc_now_iso()
                new_lead["updated_at"] = new_lead["created_at"]
                self._leads[new_lead["lead_id"]] = new_lead
                source_record_index[source_record_id] = new_lead["lead_id"]
                if key:
                    identity_index[key] = new_lead["lead_id"]
                imported += 1

            if imported or updated:
                self._save_locked()

        return {
            "job_id": source_job_id,
            "total_rows": total_rows,
            "imported": imported,
            "updated": updated,
            "skipped": skipped,
            "crm_total": len(self._leads),
            "merge_existing": bool(merge_existing),
        }


class DatabaseCRMStore(MiniCRMStore):
    def __init__(self, db_file: Path) -> None:
        self._db_file = db_file
        self._lock = threading.RLock()
        self._db_file.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_file, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._setup_db()
        logger.info(
            "CRM database initialized | "
            f"leads={self._count_locked()} db={self._db_file.name}"
        )

    def _setup_db(self) -> None:
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS leads (
                    lead_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    source_job_id TEXT NOT NULL DEFAULT '',
                    source_job_created_at TEXT NOT NULL DEFAULT '',
                    source_record_id TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT '',
                    category_key TEXT NOT NULL DEFAULT '',
                    phone TEXT NOT NULL DEFAULT '',
                    email TEXT NOT NULL DEFAULT '',
                    website TEXT NOT NULL DEFAULT '',
                    address TEXT NOT NULL DEFAULT '',
                    city TEXT NOT NULL DEFAULT '',
                    city_key TEXT NOT NULL DEFAULT '',
                    state TEXT NOT NULL DEFAULT '',
                    state_key TEXT NOT NULL DEFAULT '',
                    zip_code TEXT NOT NULL DEFAULT '',
                    zip_key TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'new',
                    owner TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '',
                    next_follow_up TEXT NOT NULL DEFAULT '',
                    last_contacted_at TEXT NOT NULL DEFAULT '',
                    lead_score TEXT NOT NULL DEFAULT '',
                    lead_priority TEXT NOT NULL DEFAULT '',
                    place_id TEXT NOT NULL DEFAULT '',
                    feature_id TEXT NOT NULL DEFAULT '',
                    google_maps_url TEXT NOT NULL DEFAULT '',
                    final_email_source TEXT NOT NULL DEFAULT '',
                    scraped_data_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            for statement in (
                "CREATE INDEX IF NOT EXISTS idx_crm_updated_at ON leads(updated_at DESC)",
                "CREATE INDEX IF NOT EXISTS idx_crm_status ON leads(status)",
                "CREATE INDEX IF NOT EXISTS idx_crm_source_job_id ON leads(source_job_id)",
                "CREATE INDEX IF NOT EXISTS idx_crm_category_key ON leads(category_key)",
                "CREATE INDEX IF NOT EXISTS idx_crm_state_key ON leads(state_key)",
                "CREATE INDEX IF NOT EXISTS idx_crm_city_key ON leads(city_key)",
                "CREATE INDEX IF NOT EXISTS idx_crm_zip_key ON leads(zip_key)",
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_crm_source_record_id "
                "ON leads(source_record_id) WHERE source_record_id <> ''",
            ):
                self._conn.execute(statement)
            self._conn.commit()

    def _serialize_scraped_data(self, value: Any) -> str:
        return json.dumps(
            _crm_clean_scraped_data(value),
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def _deserialize_scraped_data(self, raw_value: Any) -> Dict[str, str]:
        if not raw_value:
            return {}
        try:
            payload = json.loads(str(raw_value))
        except Exception:
            return {}
        return _crm_clean_scraped_data(payload)

    def _row_to_lead(self, row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
        item = dict(row)
        lead = {
            "lead_id": str(item.get("lead_id", "") or ""),
            "created_at": _crm_clean_text(item.get("created_at"), max_len=64),
            "updated_at": _crm_clean_text(item.get("updated_at"), max_len=64),
            "source_job_id": _crm_clean_text(item.get("source_job_id"), max_len=64),
            "source_job_created_at": _crm_clean_text(item.get("source_job_created_at"), max_len=64),
            "source_record_id": _crm_clean_text(item.get("source_record_id"), max_len=260),
            "name": _crm_clean_text(item.get("name"), max_len=200),
            "category": _crm_clean_text(item.get("category"), max_len=160),
            "category_key": _crm_clean_text(item.get("category_key"), max_len=160),
            "phone": _crm_clean_text(item.get("phone"), max_len=80),
            "email": _crm_clean_text(item.get("email"), max_len=220),
            "website": _crm_clean_text(item.get("website"), max_len=320),
            "address": _crm_clean_text(item.get("address"), max_len=300),
            "city": _crm_clean_text(item.get("city"), max_len=120),
            "city_key": _crm_clean_text(item.get("city_key"), max_len=120),
            "state": _crm_clean_text(item.get("state"), max_len=120),
            "state_key": _crm_clean_text(item.get("state_key"), max_len=120),
            "zip_code": _crm_clean_text(item.get("zip_code"), max_len=40),
            "zip_key": _crm_clean_text(item.get("zip_key"), max_len=40),
            "status": _crm_normalize_status(item.get("status")),
            "owner": _crm_clean_text(item.get("owner"), max_len=120),
            "notes": _crm_clean_notes(item.get("notes"), max_len=8000),
            "tags": _crm_clean_text(item.get("tags"), max_len=400),
            "next_follow_up": _crm_normalize_date(item.get("next_follow_up")),
            "last_contacted_at": _crm_clean_text(item.get("last_contacted_at"), max_len=64),
            "lead_score": _crm_clean_text(item.get("lead_score"), max_len=16),
            "lead_priority": _crm_clean_text(item.get("lead_priority"), max_len=24),
            "place_id": _crm_clean_text(item.get("place_id"), max_len=180),
            "feature_id": _crm_clean_text(item.get("feature_id"), max_len=180),
            "google_maps_url": _crm_clean_text(item.get("google_maps_url"), max_len=600),
            "final_email_source": _crm_clean_text(item.get("final_email_source"), max_len=64),
            "scraped_data": self._deserialize_scraped_data(item.get("scraped_data_json")),
        }
        return self._hydrate_segment_fields(lead)

    def _count_locked(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS count FROM leads").fetchone()
        return int((row["count"] if row else 0) or 0)

    def _fetch_all_locked(self) -> List[Dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM leads").fetchall()
        return [self._row_to_lead(row) for row in rows]

    def _fetch_lead_locked(self, lead_id: str) -> Dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM leads WHERE lead_id = ?",
            (str(lead_id or "").strip(),),
        ).fetchone()
        return self._row_to_lead(row) if row else None

    def _persist_lead_locked(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        clean = self._hydrate_segment_fields(dict(lead))
        payload = {
            "lead_id": clean.get("lead_id", ""),
            "created_at": _crm_clean_text(clean.get("created_at"), max_len=64) or utc_now_iso(),
            "updated_at": _crm_clean_text(clean.get("updated_at"), max_len=64) or utc_now_iso(),
            "source_job_id": _crm_clean_text(clean.get("source_job_id"), max_len=64),
            "source_job_created_at": _crm_clean_text(clean.get("source_job_created_at"), max_len=64),
            "source_record_id": _crm_clean_text(clean.get("source_record_id"), max_len=260),
            "name": _crm_clean_text(clean.get("name"), max_len=200),
            "category": _crm_clean_text(clean.get("category"), max_len=160),
            "category_key": _crm_clean_text(clean.get("category_key"), max_len=160),
            "phone": _crm_clean_text(clean.get("phone"), max_len=80),
            "email": _crm_clean_text(clean.get("email"), max_len=220),
            "website": _crm_clean_text(clean.get("website"), max_len=320),
            "address": _crm_clean_text(clean.get("address"), max_len=300),
            "city": _crm_clean_text(clean.get("city"), max_len=120),
            "city_key": _crm_clean_text(clean.get("city_key"), max_len=120),
            "state": _crm_clean_text(clean.get("state"), max_len=120),
            "state_key": _crm_clean_text(clean.get("state_key"), max_len=120),
            "zip_code": _crm_clean_text(clean.get("zip_code"), max_len=40),
            "zip_key": _crm_clean_text(clean.get("zip_key"), max_len=40),
            "status": _crm_normalize_status(clean.get("status")),
            "owner": _crm_clean_text(clean.get("owner"), max_len=120),
            "notes": _crm_clean_notes(clean.get("notes"), max_len=8000),
            "tags": _crm_clean_text(clean.get("tags"), max_len=400),
            "next_follow_up": _crm_normalize_date(clean.get("next_follow_up")),
            "last_contacted_at": _crm_clean_text(clean.get("last_contacted_at"), max_len=64),
            "lead_score": _crm_clean_text(clean.get("lead_score"), max_len=16),
            "lead_priority": _crm_clean_text(clean.get("lead_priority"), max_len=24),
            "place_id": _crm_clean_text(clean.get("place_id"), max_len=180),
            "feature_id": _crm_clean_text(clean.get("feature_id"), max_len=180),
            "google_maps_url": _crm_clean_text(clean.get("google_maps_url"), max_len=600),
            "final_email_source": _crm_clean_text(clean.get("final_email_source"), max_len=64),
            "scraped_data_json": self._serialize_scraped_data(clean.get("scraped_data")),
        }
        columns = list(payload.keys())
        placeholders = ", ".join("?" for _ in columns)
        assignments = ", ".join(f"{column} = excluded.{column}" for column in columns if column != "lead_id")
        self._conn.execute(
            f"""
            INSERT INTO leads ({", ".join(columns)})
            VALUES ({placeholders})
            ON CONFLICT(lead_id) DO UPDATE SET {assignments}
            """,
            [payload[column] for column in columns],
        )
        self._conn.commit()
        return self._row_to_lead(payload)

    def _identity_index_from_leads(self, leads: List[Dict[str, Any]]) -> Dict[str, str]:
        index: Dict[str, str] = {}
        for lead in leads:
            key = _crm_identity_key(lead)
            if key and key not in index:
                index[key] = str(lead.get("lead_id", "")).strip()
        return index

    def _source_record_index_from_leads(self, leads: List[Dict[str, Any]]) -> Dict[str, str]:
        index: Dict[str, str] = {}
        for lead in leads:
            source_record_id = _crm_clean_text(lead.get("source_record_id"), max_len=260)
            if source_record_id and source_record_id not in index:
                index[source_record_id] = str(lead.get("lead_id", "")).strip()
        return index

    def list_leads(
        self,
        status: str = "",
        query: str = "",
        owner: str = "",
        category: str = "",
        state: str = "",
        city: str = "",
        zip_code: str = "",
        source_job_id: str = "",
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        cap = max(1, min(int(limit), 5000))
        status_filter = str(status or "").strip().lower()
        owner_filter = str(owner or "").strip().lower()
        category_filter_raw = str(category or "").strip().lower()
        state_filter_raw = str(state or "").strip().lower()
        city_filter_raw = str(city or "").strip().lower()
        zip_filter_raw = str(zip_code or "").strip().lower()
        job_filter = _crm_clean_text(source_job_id, max_len=64)
        q = str(query or "").strip().lower()

        category_filter = (
            _crm_segment_key(category_filter_raw, max_len=160)
            if category_filter_raw and category_filter_raw != "all"
            else ""
        )
        state_filter = (
            _crm_segment_key(state_filter_raw, max_len=120)
            if state_filter_raw and state_filter_raw != "all"
            else ""
        )
        city_filter = (
            _crm_segment_key(city_filter_raw, max_len=120)
            if city_filter_raw and city_filter_raw != "all"
            else ""
        )
        zip_filter = (
            _crm_segment_zip_key(zip_filter_raw, max_len=40)
            if zip_filter_raw and zip_filter_raw != "all"
            else ""
        )

        clauses = []
        params: List[Any] = []
        if status_filter and status_filter != "all":
            clauses.append("status = ?")
            params.append(status_filter)
        if owner_filter:
            clauses.append("LOWER(owner) LIKE ?")
            params.append(f"%{owner_filter}%")
        if category_filter:
            clauses.append("category_key = ?")
            params.append(category_filter)
        if state_filter:
            clauses.append("state_key = ?")
            params.append(state_filter)
        if city_filter:
            clauses.append("city_key = ?")
            params.append(city_filter)
        if zip_filter:
            clauses.append("zip_key = ?")
            params.append(zip_filter)
        if job_filter:
            clauses.append("source_job_id = ?")
            params.append(job_filter)

        sql = "SELECT * FROM leads"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY updated_at DESC"

        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()

        leads = [self._row_to_lead(row) for row in rows]
        if not q:
            return leads[:cap]

        out: List[Dict[str, Any]] = []
        for lead in leads:
            hay = " | ".join(
                [
                    str(lead.get("name", "")),
                    str(lead.get("category", "")),
                    str(lead.get("state", "")),
                    str(lead.get("city", "")),
                    str(lead.get("zip_code", "")),
                    str(lead.get("phone", "")),
                    str(lead.get("email", "")),
                    str(lead.get("address", "")),
                    str(lead.get("source_job_id", "")),
                    str(lead.get("owner", "")),
                    str(lead.get("notes", "")),
                    str(json.dumps(lead.get("scraped_data", {}), ensure_ascii=False)),
                ]
            ).lower()
            if q in hay:
                out.append(lead)
            if len(out) >= cap:
                break
        return out

    def get_filter_options(self, limit: int = 5000) -> Dict[str, Any]:
        leads = self.list_leads(limit=max(5000, min(int(limit), 50000)))
        return {
            "categories": self._collect_segment_options_from_rows(leads, segment="category", limit=limit),
            "states": self._collect_segment_options_from_rows(leads, segment="state", limit=limit),
            "cities": self._collect_segment_options_from_rows(leads, segment="city", limit=limit),
            "zips": self._collect_segment_options_from_rows(leads, segment="zip", limit=limit),
        }

    def segment_counts(self, group_by: str = "category", limit: int = 200) -> List[Dict[str, Any]]:
        segment = str(group_by or "").strip().lower()
        if segment not in {"category", "state", "city", "zip"}:
            raise ValueError("group_by must be one of: category, state, city, zip")
        leads = self.list_leads(limit=50000)
        return self._collect_segment_options_from_rows(leads, segment=segment, limit=limit)

    def get_stats(self) -> Dict[str, Any]:
        leads = self.list_leads(limit=50000)
        return self._compute_stats_for_rows(leads)

    def get_stats_for_rows(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        normalized_rows = [self._hydrate_segment_fields(dict(row)) for row in (rows or []) if isinstance(row, dict)]
        return self._compute_stats_for_rows(normalized_rows)

    def create_or_merge(self, payload: Dict[str, Any]) -> tuple[Dict[str, Any], bool]:
        if not isinstance(payload, dict):
            raise ValueError("Invalid payload")
        lead = self._build_lead(payload)
        if not (lead["name"] or lead["phone"] or lead["email"]):
            raise ValueError("At least one of name, phone, or email is required")

        with self._lock:
            leads = self._fetch_all_locked()
            identity_index = self._identity_index_from_leads(leads)
            key = _crm_identity_key(lead)
            if key:
                existing_id = identity_index.get(key)
                if existing_id:
                    existing = self._fetch_lead_locked(existing_id)
                    if existing:
                        merged = self._merge_import_locked(existing, lead)
                        merged["status"] = _crm_normalize_status(payload.get("status", merged.get("status")))
                        merged["owner"] = _crm_clean_text(payload.get("owner"), max_len=120) or merged.get("owner", "")
                        merged["notes"] = _crm_clean_notes(payload.get("notes"), max_len=8000) or merged.get("notes", "")
                        merged["tags"] = _crm_clean_text(payload.get("tags"), max_len=400) or merged.get("tags", "")
                        follow_up = _crm_normalize_date(payload.get("next_follow_up"))
                        if follow_up:
                            merged["next_follow_up"] = follow_up
                        merged["updated_at"] = utc_now_iso()
                        return self._persist_lead_locked(merged), False

            lead["created_at"] = utc_now_iso()
            lead["updated_at"] = lead["created_at"]
            return self._persist_lead_locked(lead), True

    def update_lead(self, lead_id: str, patch: Dict[str, Any]) -> Dict[str, Any] | None:
        if not isinstance(patch, dict):
            return None
        with self._lock:
            existing = self._fetch_lead_locked(lead_id)
            if not existing:
                return None
            updated = dict(existing)
            field_rules = {
                "name": lambda v: _crm_clean_text(v, max_len=200),
                "category": lambda v: _crm_clean_text(v, max_len=160),
                "phone": lambda v: _crm_clean_text(v, max_len=80),
                "email": lambda v: _crm_clean_text(v, max_len=220),
                "website": lambda v: _crm_clean_text(v, max_len=320),
                "address": lambda v: _crm_clean_text(v, max_len=300),
                "city": lambda v: _crm_clean_text(v, max_len=120),
                "state": lambda v: _crm_clean_text(v, max_len=120),
                "zip_code": lambda v: _crm_clean_text(v, max_len=40),
                "status": _crm_normalize_status,
                "owner": lambda v: _crm_clean_text(v, max_len=120),
                "notes": lambda v: _crm_clean_notes(v, max_len=8000),
                "tags": lambda v: _crm_clean_text(v, max_len=400),
                "next_follow_up": _crm_normalize_date,
                "last_contacted_at": lambda v: _crm_clean_text(v, max_len=64),
            }
            for field, cleaner in field_rules.items():
                if field in patch:
                    updated[field] = cleaner(patch.get(field))
            updated = self._hydrate_segment_fields(updated)
            updated["updated_at"] = utc_now_iso()
            return self._persist_lead_locked(updated)

    def delete_lead(self, lead_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM leads WHERE lead_id = ?", (str(lead_id or "").strip(),))
            self._conn.commit()
            return cur.rowcount > 0

    def delete_by_job_id(self, source_job_id: str) -> Dict[str, Any]:
        job_id = _crm_clean_text(source_job_id, max_len=64)
        with self._lock:
            if not job_id:
                return {"job_id": "", "deleted": 0, "crm_total": self._count_locked()}
            cur = self._conn.execute("DELETE FROM leads WHERE source_job_id = ?", (job_id,))
            self._conn.commit()
            return {
                "job_id": job_id,
                "deleted": int(cur.rowcount or 0),
                "crm_total": self._count_locked(),
            }

    def import_rows(
        self,
        rows: List[Dict[str, Any]],
        source_job_id: str,
        source_job_created_at: str = "",
        merge_existing: bool = False,
    ) -> Dict[str, Any]:
        imported = 0
        updated = 0
        skipped = 0
        total_rows = len(rows or [])

        with self._lock:
            leads = self._fetch_all_locked()
            leads_by_id = {str(lead.get("lead_id", "")).strip(): lead for lead in leads}
            identity_index = self._identity_index_from_leads(leads)
            source_record_index = self._source_record_index_from_leads(leads)
            for idx, row in enumerate(rows or []):
                if not isinstance(row, dict):
                    skipped += 1
                    continue
                if str(row.get("error", "")).strip():
                    skipped += 1
                    continue

                payload = self._row_to_import_payload(
                    row,
                    source_job_id=source_job_id,
                    source_job_created_at=source_job_created_at,
                )
                if not (
                    _crm_clean_text(payload.get("name"))
                    or _crm_clean_text(payload.get("phone"))
                    or _crm_clean_text(payload.get("email"))
                ):
                    skipped += 1
                    continue

                key = _crm_identity_key(payload)
                source_record_id = f"{source_job_id}|{key or f'row:{idx}'}"
                payload["source_record_id"] = source_record_id

                existing_id = source_record_index.get(source_record_id)
                if existing_id and existing_id in leads_by_id:
                    merged = self._merge_import_locked(leads_by_id[existing_id], payload)
                    persisted = self._persist_lead_locked(merged)
                    leads_by_id[existing_id] = persisted
                    updated += 1
                    if key and key not in identity_index:
                        identity_index[key] = existing_id
                    continue

                if merge_existing and key and key in identity_index:
                    existing_id = identity_index[key]
                    existing = leads_by_id.get(existing_id)
                    if not existing:
                        skipped += 1
                        continue
                    merged = self._merge_import_locked(existing, payload)
                    persisted = self._persist_lead_locked(merged)
                    leads_by_id[existing_id] = persisted
                    updated += 1
                    source_record_index[source_record_id] = existing_id
                    continue

                new_lead = self._build_lead(payload, lead_id=str(uuid.uuid4()))
                new_lead["created_at"] = utc_now_iso()
                new_lead["updated_at"] = new_lead["created_at"]
                persisted = self._persist_lead_locked(new_lead)
                leads_by_id[persisted["lead_id"]] = persisted
                source_record_index[source_record_id] = persisted["lead_id"]
                if key:
                    identity_index[key] = persisted["lead_id"]
                imported += 1

            crm_total = self._count_locked()

        return {
            "job_id": source_job_id,
            "total_rows": total_rows,
            "imported": imported,
            "updated": updated,
            "skipped": skipped,
            "crm_total": crm_total,
            "merge_existing": bool(merge_existing),
        }


def _store_clean_name(value: Any, max_len: int = 96) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:max_len]


def _store_int(value: Any, default: int = 0, low: int = 0, high: int = 1_000_000) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(low, min(high, parsed))


class PresetStore:
    def __init__(self, data_file: Path) -> None:
        self._data_file = data_file
        self._lock = threading.Lock()
        self._items: Dict[str, Dict[str, Any]] = {}
        self._load()
        logger.info(f"PresetStore initialized | presets={len(self._items)}")

    def _load(self) -> None:
        if not self._data_file.exists():
            return
        try:
            with open(self._data_file, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as exc:
            logger.error(f"Failed to load presets data: {exc}")
            return

        raw_items: List[Dict[str, Any]] = []
        if isinstance(payload, dict) and isinstance(payload.get("presets"), list):
            raw_items = [x for x in payload["presets"] if isinstance(x, dict)]
        elif isinstance(payload, list):
            raw_items = [x for x in payload if isinstance(x, dict)]

        for item in raw_items:
            preset_id = str(item.get("preset_id", "")).strip() or str(uuid.uuid4())
            self._items[preset_id] = {
                "preset_id": preset_id,
                "name": _store_clean_name(item.get("name"), max_len=96) or "Untitled Preset",
                "description": _store_clean_name(item.get("description"), max_len=240),
                "config": item.get("config") if isinstance(item.get("config"), dict) else {},
                "created_at": str(item.get("created_at", "")).strip() or utc_now_iso(),
                "updated_at": str(item.get("updated_at", "")).strip() or utc_now_iso(),
                "last_used_at": str(item.get("last_used_at", "")).strip(),
                "use_count": _store_int(item.get("use_count", 0), default=0, low=0, high=1_000_000),
            }

    def _save_locked(self) -> None:
        payload = {
            "version": 1,
            "updated_at": utc_now_iso(),
            "presets": list(self._items.values()),
        }
        _write_json_atomic(self._data_file, payload)

    def list(self, limit: int = 200) -> List[Dict[str, Any]]:
        cap = max(1, min(int(limit), 2000))
        with self._lock:
            rows = [dict(v) for v in self._items.values()]
        rows.sort(key=lambda x: str(x.get("updated_at", "")), reverse=True)
        out: List[Dict[str, Any]] = []
        for row in rows[:cap]:
            out.append(
                {
                    "preset_id": row.get("preset_id", ""),
                    "name": row.get("name", ""),
                    "description": row.get("description", ""),
                    "updated_at": row.get("updated_at", ""),
                    "created_at": row.get("created_at", ""),
                    "last_used_at": row.get("last_used_at", ""),
                    "use_count": row.get("use_count", 0),
                }
            )
        return out

    def get(self, preset_id: str) -> Dict[str, Any] | None:
        target = str(preset_id or "").strip()
        if not target:
            return None
        with self._lock:
            item = self._items.get(target)
            if not item:
                return None
            return dict(item)

    def save(self, *, name: str, config: Dict[str, Any], description: str = "", preset_id: str = "") -> Dict[str, Any]:
        clean_name = _store_clean_name(name, max_len=96)
        if not clean_name:
            raise ValueError("preset name is required")
        if not isinstance(config, dict):
            raise ValueError("config must be an object")

        now = utc_now_iso()
        target_id = str(preset_id or "").strip()
        with self._lock:
            existing = self._items.get(target_id) if target_id else None
            if existing:
                created_at = str(existing.get("created_at", "")).strip() or now
                use_count = _store_int(existing.get("use_count", 0), default=0, low=0, high=1_000_000)
                last_used_at = str(existing.get("last_used_at", "")).strip()
                item_id = target_id
            else:
                created_at = now
                use_count = 0
                last_used_at = ""
                item_id = str(uuid.uuid4())

            item = {
                "preset_id": item_id,
                "name": clean_name,
                "description": _store_clean_name(description, max_len=240),
                "config": dict(config),
                "created_at": created_at,
                "updated_at": now,
                "last_used_at": last_used_at,
                "use_count": use_count,
            }
            self._items[item_id] = item
            self._save_locked()
            return dict(item)

    def mark_used(self, preset_id: str) -> Dict[str, Any] | None:
        target = str(preset_id or "").strip()
        if not target:
            return None
        now = utc_now_iso()
        with self._lock:
            item = self._items.get(target)
            if not item:
                return None
            item["last_used_at"] = now
            item["use_count"] = _store_int(item.get("use_count", 0), default=0, low=0, high=1_000_000) + 1
            item["updated_at"] = now
            self._save_locked()
            return dict(item)

    def delete(self, preset_id: str) -> bool:
        target = str(preset_id or "").strip()
        if not target:
            return False
        with self._lock:
            if target not in self._items:
                return False
            self._items.pop(target, None)
            self._save_locked()
            return True


class ZipPackStore:
    def __init__(self, data_file: Path) -> None:
        self._data_file = data_file
        self._lock = threading.Lock()
        self._packs: Dict[str, Dict[str, Any]] = {}
        self._load()
        logger.info(f"ZipPackStore initialized | packs={len(self._packs)}")

    def _load(self) -> None:
        if not self._data_file.exists():
            return
        try:
            with open(self._data_file, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as exc:
            logger.error(f"Failed to load zip pack data: {exc}")
            return

        raw_items: List[Dict[str, Any]] = []
        if isinstance(payload, dict) and isinstance(payload.get("packs"), list):
            raw_items = [x for x in payload["packs"] if isinstance(x, dict)]
        elif isinstance(payload, list):
            raw_items = [x for x in payload if isinstance(x, dict)]

        for item in raw_items:
            pack_id = str(item.get("pack_id", "")).strip() or str(uuid.uuid4())
            raw_locations = item.get("zip_locations")
            if not isinstance(raw_locations, list):
                raw_locations = []
            zip_locations = []
            for loc in raw_locations:
                if not isinstance(loc, dict):
                    continue
                zip_code = str(loc.get("zip", "")).strip()
                location = str(loc.get("location", "")).strip()
                if not zip_code:
                    continue
                if not location:
                    location = zip_code
                zip_locations.append({"zip": zip_code, "location": location})
            self._packs[pack_id] = {
                "pack_id": pack_id,
                "name": _store_clean_name(item.get("name"), max_len=96) or "Untitled ZIP Pack",
                "description": _store_clean_name(item.get("description"), max_len=240),
                "zip_locations": zip_locations,
                "zip_count": len(zip_locations),
                "created_at": str(item.get("created_at", "")).strip() or utc_now_iso(),
                "updated_at": str(item.get("updated_at", "")).strip() or utc_now_iso(),
            }

    def _save_locked(self) -> None:
        payload = {
            "version": 1,
            "updated_at": utc_now_iso(),
            "packs": list(self._packs.values()),
        }
        _write_json_atomic(self._data_file, payload)

    def list(self, limit: int = 200) -> List[Dict[str, Any]]:
        cap = max(1, min(int(limit), 2000))
        with self._lock:
            rows = [dict(v) for v in self._packs.values()]
        rows.sort(key=lambda x: str(x.get("updated_at", "")), reverse=True)
        out: List[Dict[str, Any]] = []
        for row in rows[:cap]:
            out.append(
                {
                    "pack_id": row.get("pack_id", ""),
                    "name": row.get("name", ""),
                    "description": row.get("description", ""),
                    "zip_count": _store_int(row.get("zip_count", 0), default=0, low=0, high=200000),
                    "updated_at": row.get("updated_at", ""),
                    "created_at": row.get("created_at", ""),
                }
            )
        return out

    def get(self, pack_id: str) -> Dict[str, Any] | None:
        target = str(pack_id or "").strip()
        if not target:
            return None
        with self._lock:
            item = self._packs.get(target)
            if not item:
                return None
            return dict(item)

    def save(
        self,
        *,
        name: str,
        zip_locations: List[Dict[str, str]],
        description: str = "",
        pack_id: str = "",
    ) -> Dict[str, Any]:
        clean_name = _store_clean_name(name, max_len=96)
        if not clean_name:
            raise ValueError("zip pack name is required")
        if not isinstance(zip_locations, list):
            raise ValueError("zip_locations must be a list")
        if len(zip_locations) == 0:
            raise ValueError("zip pack must contain at least one ZIP")

        normalized_locations: List[Dict[str, str]] = []
        for item in zip_locations:
            if not isinstance(item, dict):
                continue
            zip_code = str(item.get("zip", "")).strip()
            location = str(item.get("location", "")).strip() or zip_code
            if not zip_code:
                continue
            normalized_locations.append({"zip": zip_code, "location": location})
        if len(normalized_locations) == 0:
            raise ValueError("zip pack has no valid ZIP entries")

        now = utc_now_iso()
        target_id = str(pack_id or "").strip()
        with self._lock:
            existing = self._packs.get(target_id) if target_id else None
            if existing:
                created_at = str(existing.get("created_at", "")).strip() or now
                item_id = target_id
            else:
                created_at = now
                item_id = str(uuid.uuid4())
            item = {
                "pack_id": item_id,
                "name": clean_name,
                "description": _store_clean_name(description, max_len=240),
                "zip_locations": normalized_locations,
                "zip_count": len(normalized_locations),
                "created_at": created_at,
                "updated_at": now,
            }
            self._packs[item_id] = item
            self._save_locked()
            return dict(item)

    def delete(self, pack_id: str) -> bool:
        target = str(pack_id or "").strip()
        if not target:
            return False
        with self._lock:
            if target not in self._packs:
                return False
            self._packs.pop(target, None)
            self._save_locked()
            return True


class NotificationManager:
    def __init__(self, data_file: Path) -> None:
        self._data_file = data_file
        self._lock = threading.Lock()
        self._config: Dict[str, Any] = self._default_config()
        self._load()
        logger.info("NotificationManager initialized")

    @staticmethod
    def _parse_bool(value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        text = str(value).strip().lower()
        return text in {"1", "true", "yes", "y", "on"}

    @staticmethod
    def _parse_int(value: Any, default: int, low: int, high: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(low, min(high, parsed))

    @staticmethod
    def _parse_text(value: Any, max_len: int = 800) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        return text[:max_len]

    def _default_config(self) -> Dict[str, Any]:
        return {
            "enabled": self._parse_bool(os.getenv("SCRAPER_NOTIFICATIONS_ENABLED", "false"), default=False),
            "notify_on_success": True,
            "notify_on_failure": True,
            "webhook_url": self._parse_text(os.getenv("SCRAPER_WEBHOOK_URL", ""), max_len=1200),
            "telegram_enabled": self._parse_bool(os.getenv("SCRAPER_TELEGRAM_ENABLED", "false"), default=False),
            "telegram_bot_token": self._parse_text(os.getenv("SCRAPER_TELEGRAM_BOT_TOKEN", ""), max_len=400),
            "telegram_chat_id": self._parse_text(os.getenv("SCRAPER_TELEGRAM_CHAT_ID", ""), max_len=120),
            "email_enabled": self._parse_bool(os.getenv("SCRAPER_EMAIL_ENABLED", "false"), default=False),
            "smtp_host": self._parse_text(os.getenv("SCRAPER_SMTP_HOST", ""), max_len=300),
            "smtp_port": self._parse_int(os.getenv("SCRAPER_SMTP_PORT", 587), default=587, low=1, high=65535),
            "smtp_username": self._parse_text(os.getenv("SCRAPER_SMTP_USERNAME", ""), max_len=300),
            "smtp_password": self._parse_text(os.getenv("SCRAPER_SMTP_PASSWORD", ""), max_len=600),
            "smtp_use_tls": self._parse_bool(os.getenv("SCRAPER_SMTP_USE_TLS", "true"), default=True),
            "email_from": self._parse_text(os.getenv("SCRAPER_EMAIL_FROM", ""), max_len=300),
            "email_to": self._parse_text(os.getenv("SCRAPER_EMAIL_TO", ""), max_len=1000),
            "request_timeout_sec": self._parse_int(os.getenv("SCRAPER_NOTIFY_TIMEOUT_SEC", 12), default=12, low=3, high=60),
            "updated_at": utc_now_iso(),
        }

    def _load(self) -> None:
        if not self._data_file.exists():
            return
        try:
            with open(self._data_file, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as exc:
            logger.error(f"Failed to load notification config: {exc}")
            return
        if not isinstance(payload, dict):
            return
        with self._lock:
            merged = dict(self._config)
            merged.update(payload)
            merged["enabled"] = self._parse_bool(merged.get("enabled"), default=False)
            merged["notify_on_success"] = self._parse_bool(merged.get("notify_on_success"), default=True)
            merged["notify_on_failure"] = self._parse_bool(merged.get("notify_on_failure"), default=True)
            merged["telegram_enabled"] = self._parse_bool(merged.get("telegram_enabled"), default=False)
            merged["email_enabled"] = self._parse_bool(merged.get("email_enabled"), default=False)
            merged["smtp_use_tls"] = self._parse_bool(merged.get("smtp_use_tls"), default=True)
            merged["smtp_port"] = self._parse_int(merged.get("smtp_port"), default=587, low=1, high=65535)
            merged["request_timeout_sec"] = self._parse_int(merged.get("request_timeout_sec"), default=12, low=3, high=60)
            merged["updated_at"] = self._parse_text(merged.get("updated_at"), max_len=64) or utc_now_iso()
            self._config = merged

    def _save_locked(self) -> None:
        payload = dict(self._config)
        payload["updated_at"] = utc_now_iso()
        _write_json_atomic(self._data_file, payload)

    def get_config(self, include_secrets: bool = False) -> Dict[str, Any]:
        with self._lock:
            config = dict(self._config)
        if include_secrets:
            return config
        safe = dict(config)
        safe["telegram_bot_token_set"] = bool(safe.get("telegram_bot_token"))
        safe["smtp_password_set"] = bool(safe.get("smtp_password"))
        safe["webhook_enabled"] = bool(str(safe.get("webhook_url", "")).strip())
        safe.pop("telegram_bot_token", None)
        safe.pop("smtp_password", None)
        return safe

    def update_config(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(patch, dict):
            raise ValueError("config payload must be an object")
        text_fields = {
            "webhook_url": 1200,
            "telegram_bot_token": 400,
            "telegram_chat_id": 120,
            "smtp_host": 300,
            "smtp_username": 300,
            "smtp_password": 600,
            "email_from": 300,
            "email_to": 1000,
        }
        bool_fields = {
            "enabled",
            "notify_on_success",
            "notify_on_failure",
            "telegram_enabled",
            "email_enabled",
            "smtp_use_tls",
        }
        int_fields = {
            "smtp_port": (587, 1, 65535),
            "request_timeout_sec": (12, 3, 60),
        }

        with self._lock:
            cfg = dict(self._config)
            for key, val in patch.items():
                if key in text_fields:
                    cfg[key] = self._parse_text(val, max_len=text_fields[key])
                elif key in bool_fields:
                    cfg[key] = self._parse_bool(val, default=bool(cfg.get(key)))
                elif key in int_fields:
                    default, low, high = int_fields[key]
                    cfg[key] = self._parse_int(val, default=default, low=low, high=high)
            cfg["updated_at"] = utc_now_iso()
            self._config = cfg
            self._save_locked()
        return self.get_config(include_secrets=False)

    @staticmethod
    def _parse_iso(value: Any) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None

    def _build_job_payload(self, job: Dict[str, Any], event: str) -> Dict[str, Any]:
        params = job.get("params") if isinstance(job.get("params"), dict) else {}
        results = job.get("results") if isinstance(job.get("results"), list) else []
        success_rows = _successful_result_rows(results)
        failed_rows = _failed_result_rows(results)
        started_at = self._parse_iso(job.get("started_at"))
        finished_at = self._parse_iso(job.get("finished_at"))
        duration_sec = ""
        if started_at and finished_at:
            try:
                duration_sec = round((finished_at - started_at).total_seconds(), 2)
            except Exception:
                duration_sec = ""
        return {
            "app": "Google Maps Scraper",
            "event": str(event or "").strip().lower(),
            "timestamp_utc": utc_now_iso(),
            "job_id": str(job.get("job_id", "")),
            "status": str(job.get("status", "")),
            "mode": str(params.get("mode", "single")),
            "keyword": str(params.get("keyword", "")),
            "location": str(params.get("location", "")),
            "progress": job.get("progress", 0),
            "total": job.get("total", 0),
            "result_count": len(success_rows),
            "error_count": len(failed_rows),
            "checkpoint_rows": job.get("checkpoint_rows", 0),
            "dedup_removed_count": job.get("dedup_removed_count", 0),
            "message": str(job.get("message", "")),
            "error": str(job.get("error", "")),
            "created_at": str(job.get("created_at", "")),
            "started_at": str(job.get("started_at", "")),
            "finished_at": str(job.get("finished_at", "")),
            "duration_sec": duration_sec,
        }

    @staticmethod
    def _payload_to_message(payload: Dict[str, Any]) -> str:
        error_line = str(payload.get("error", "")).splitlines()[0] if payload.get("error") else ""
        parts = [
            f"[{payload.get('event', '').upper()}] Job {payload.get('job_id', '')}",
            f"Status: {payload.get('status', '')}",
            f"Mode: {payload.get('mode', '')}",
            f"Keyword: {payload.get('keyword', '')}",
            f"Location: {payload.get('location', '')}",
            f"Progress: {payload.get('progress', 0)}/{payload.get('total', 0)}",
            f"Results: {payload.get('result_count', 0)}",
            f"Duration(s): {payload.get('duration_sec', '')}",
            f"Message: {payload.get('message', '')}",
        ]
        if error_line:
            parts.append(f"Error: {error_line}")
        return "\n".join(parts)

    @staticmethod
    def _split_emails(raw_value: Any) -> List[str]:
        tokens = re.split(r"[,\n;]+", str(raw_value or ""))
        out: List[str] = []
        for token in tokens:
            email = token.strip()
            if email and email not in out:
                out.append(email)
        return out

    def _send_webhook(self, url: str, payload: Dict[str, Any], timeout_sec: int) -> None:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            code = int(getattr(resp, "status", 200))
            if code >= 400:
                raise RuntimeError(f"Webhook responded with status {code}")

    def _send_telegram(self, bot_token: str, chat_id: str, message: str, timeout_sec: int) -> None:
        api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        encoded = urllib.parse.urlencode(
            {
                "chat_id": chat_id,
                "text": message,
                "disable_web_page_preview": "true",
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            api_url,
            data=encoded,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            code = int(getattr(resp, "status", 200))
            if code >= 400:
                raise RuntimeError(f"Telegram API responded with status {code}")

    def _send_email(self, cfg: Dict[str, Any], subject: str, message: str) -> None:
        host = str(cfg.get("smtp_host", "")).strip()
        recipients = self._split_emails(cfg.get("email_to", ""))
        if not host or not recipients:
            raise RuntimeError("SMTP host/email_to is missing")
        port = self._parse_int(cfg.get("smtp_port"), default=587, low=1, high=65535)
        timeout_sec = self._parse_int(cfg.get("request_timeout_sec"), default=12, low=3, high=60)
        username = str(cfg.get("smtp_username", "")).strip()
        password = str(cfg.get("smtp_password", "")).strip()
        from_email = str(cfg.get("email_from", "")).strip() or username or "noreply@localhost"
        use_tls = self._parse_bool(cfg.get("smtp_use_tls"), default=True)

        msg = EmailMessage()
        msg["Subject"] = subject[:220]
        msg["From"] = from_email
        msg["To"] = ", ".join(recipients)
        msg.set_content(message)

        with smtplib.SMTP(host=host, port=port, timeout=timeout_sec) as server:
            if use_tls:
                server.starttls()
            if username:
                server.login(username, password)
            server.send_message(msg)

    def _should_notify(self, cfg: Dict[str, Any], event: str) -> bool:
        if not self._parse_bool(cfg.get("enabled"), default=False):
            return False
        if event == "completed":
            return self._parse_bool(cfg.get("notify_on_success"), default=True)
        if event == "failed":
            return self._parse_bool(cfg.get("notify_on_failure"), default=True)
        return True

    def send_job_notification(self, job: Dict[str, Any], event: str) -> Dict[str, Any]:
        with self._lock:
            cfg = dict(self._config)
        event_name = str(event or "").strip().lower()
        if not self._should_notify(cfg, event_name):
            return {"sent": [], "errors": [], "skipped": True}

        payload = self._build_job_payload(job, event=event_name)
        message = self._payload_to_message(payload)
        timeout_sec = self._parse_int(cfg.get("request_timeout_sec"), default=12, low=3, high=60)
        sent: List[str] = []
        errors: List[str] = []

        webhook_url = str(cfg.get("webhook_url", "")).strip()
        if webhook_url:
            try:
                self._send_webhook(webhook_url, payload, timeout_sec=timeout_sec)
                sent.append("webhook")
            except Exception as exc:
                errors.append(f"webhook: {exc}")

        if self._parse_bool(cfg.get("telegram_enabled"), default=False):
            token = str(cfg.get("telegram_bot_token", "")).strip()
            chat_id = str(cfg.get("telegram_chat_id", "")).strip()
            if token and chat_id:
                try:
                    self._send_telegram(token, chat_id, message=message, timeout_sec=timeout_sec)
                    sent.append("telegram")
                except Exception as exc:
                    errors.append(f"telegram: {exc}")
            else:
                errors.append("telegram: missing bot token or chat id")

        if self._parse_bool(cfg.get("email_enabled"), default=False):
            try:
                subject = f"[{event_name.upper()}] Google Maps Scraper Job {payload.get('job_id', '')}"
                self._send_email(cfg, subject=subject, message=message)
                sent.append("email")
            except Exception as exc:
                errors.append(f"email: {exc}")

        if errors:
            logger.warning(f"Notification dispatch errors for job {payload.get('job_id', '')}: {' | '.join(errors)}")
        elif sent:
            logger.info(f"Notifications sent for job {payload.get('job_id', '')}: {', '.join(sent)}")
        return {"sent": sent, "errors": errors, "payload": payload}

    def send_job_notification_async(self, job: Dict[str, Any], event: str) -> None:
        if not isinstance(job, dict):
            return

        def _runner() -> None:
            try:
                self.send_job_notification(job, event=event)
            except Exception as exc:
                logger.error(f"Async notification failed: {exc}")

        threading.Thread(target=_runner, daemon=True).start()

    def send_test_notification(self, channel: str = "all", message: str = "") -> Dict[str, Any]:
        with self._lock:
            cfg = dict(self._config)
        if not self._parse_bool(cfg.get("enabled"), default=False):
            raise ValueError("Notifications are disabled")
        channel_key = str(channel or "all").strip().lower()
        if channel_key not in {"all", "webhook", "telegram", "email"}:
            raise ValueError("channel must be one of: all, webhook, telegram, email")

        payload = {
            "app": "Google Maps Scraper",
            "event": "test",
            "timestamp_utc": utc_now_iso(),
            "message": self._parse_text(message, max_len=4000) or "Test notification from Google Maps Scraper app",
        }
        text_message = str(payload["message"])
        timeout_sec = self._parse_int(cfg.get("request_timeout_sec"), default=12, low=3, high=60)
        sent: List[str] = []
        errors: List[str] = []

        if channel_key in {"all", "webhook"}:
            webhook_url = str(cfg.get("webhook_url", "")).strip()
            if webhook_url:
                try:
                    self._send_webhook(webhook_url, payload, timeout_sec=timeout_sec)
                    sent.append("webhook")
                except Exception as exc:
                    errors.append(f"webhook: {exc}")
            elif channel_key == "webhook":
                errors.append("webhook: webhook_url is missing")

        if channel_key in {"all", "telegram"}:
            token = str(cfg.get("telegram_bot_token", "")).strip()
            chat_id = str(cfg.get("telegram_chat_id", "")).strip()
            if self._parse_bool(cfg.get("telegram_enabled"), default=False) and token and chat_id:
                try:
                    self._send_telegram(token, chat_id, message=text_message, timeout_sec=timeout_sec)
                    sent.append("telegram")
                except Exception as exc:
                    errors.append(f"telegram: {exc}")
            elif channel_key == "telegram":
                errors.append("telegram: channel disabled or token/chat_id missing")

        if channel_key in {"all", "email"}:
            if self._parse_bool(cfg.get("email_enabled"), default=False):
                try:
                    self._send_email(cfg, subject="[TEST] Google Maps Scraper Notification", message=text_message)
                    sent.append("email")
                except Exception as exc:
                    errors.append(f"email: {exc}")
            elif channel_key == "email":
                errors.append("email: channel disabled")

        return {"sent": sent, "errors": errors, "payload": payload}


class USLocationDirectory:
    def __init__(
        self,
        txt_file: Path | None = None,
        archive_file: Path | None = None,
        source_url: str = "",
        *,
        data_dir: Path | None = None,
        source_urls: Dict[str, str] | None = None,
    ) -> None:
        self._lock = threading.Lock()

        normalized_urls: Dict[str, str] = {}
        if source_urls:
            for code, url in source_urls.items():
                country = str(code or "").strip().upper()
                link = str(url or "").strip()
                if country and link:
                    normalized_urls[country] = link
        elif source_url:
            normalized_urls["US"] = str(source_url).strip()
        else:
            normalized_urls = dict(LOCATION_ZIP_SOURCE_URLS)
        self._source_urls = normalized_urls

        base_dir = data_dir or (txt_file.parent if txt_file else LOCATION_DATA_DIR)
        base_dir.mkdir(parents=True, exist_ok=True)
        self._txt_files: Dict[str, Path] = {}
        self._archive_files: Dict[str, Path] = {}
        for country in self._source_urls:
            if country == "US" and txt_file:
                self._txt_files[country] = txt_file
            else:
                self._txt_files[country] = base_dir / f"{country}.txt"
            if country == "US" and archive_file:
                self._archive_files[country] = archive_file
            else:
                self._archive_files[country] = base_dir / f"{country}.zip"

        self._loaded_countries: set[str] = set()
        self._states_by_country: Dict[str, List[Dict[str, str]]] = {}
        self._state_name_by_country_code: Dict[str, Dict[str, str]] = {}
        self._cities_by_country_state: Dict[str, Dict[str, List[str]]] = {}
        self._zips_by_country_state: Dict[str, Dict[str, List[str]]] = {}
        self._zips_by_country_state_city: Dict[str, Dict[str, List[str]]] = {}

    def _normalize_state_code(self, state_name: str, state_code: str) -> str:
        code = str(state_code or "").strip().upper()
        if code:
            return code
        fallback = re.sub(r"[^A-Z0-9]+", "", str(state_name or "").upper())
        if not fallback:
            return "NA"
        return fallback[:12]

    def _normalize_zip_for_country(self, country: str, zip_code: str) -> str:
        value = str(zip_code or "").strip()
        if not value:
            return ""
        if value.isdigit():
            if country == "US" and len(value) < 5:
                value = value.zfill(5)
            elif country == "IN" and len(value) < 6:
                value = value.zfill(6)
        if len(value) > 10:
            value = value[:10]
        return value

    def _ensure_data_file_locked(self, country: str) -> None:
        code = str(country or "").strip().upper()
        txt_path = self._txt_files.get(code)
        archive_path = self._archive_files.get(code)
        source_url = self._source_urls.get(code)
        if not txt_path or not archive_path or not source_url:
            raise RuntimeError(f"No location dataset source configured for country {code}")

        if txt_path.exists() and txt_path.stat().st_size > 1024:
            return

        txt_path.parent.mkdir(parents=True, exist_ok=True)
        archive_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            logger.info(f"Downloading {code} ZIP dataset...")
            with urllib.request.urlopen(source_url, timeout=120) as resp:
                payload = resp.read()
            with open(archive_path, "wb") as f:
                f.write(payload)
        except Exception as exc:
            raise RuntimeError(f"Failed to download {code} ZIP dataset: {exc}") from exc

        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                member = f"{code}.txt"
                if member not in zf.namelist():
                    candidates = [
                        name
                        for name in zf.namelist()
                        if name.lower().endswith(f"/{code.lower()}.txt") or name.lower().endswith(f"{code.lower()}.txt")
                    ]
                    if not candidates:
                        raise RuntimeError(f"{code}.txt not found in ZIP archive")
                    member = candidates[0]
                zf.extract(member, path=txt_path.parent)
                extracted = txt_path.parent / member
                extracted.parent.mkdir(parents=True, exist_ok=True)
                if extracted.resolve() != txt_path.resolve():
                    if txt_path.exists():
                        txt_path.unlink()
                    extracted.replace(txt_path)
        except Exception as exc:
            raise RuntimeError(f"Failed to extract {code} ZIP dataset: {exc}") from exc

    def _load_country_locked(self, country: str) -> None:
        code = str(country or "").strip().upper()
        if code in self._loaded_countries:
            return
        if code not in self._source_urls:
            raise RuntimeError(f"Unsupported country dataset: {code}")

        self._ensure_data_file_locked(code)
        txt_path = self._txt_files[code]

        state_names: Dict[str, str] = {}
        cities_by_state: Dict[str, set[str]] = {}
        zips_by_state: Dict[str, set[str]] = {}
        zips_by_state_city: Dict[str, set[str]] = {}

        try:
            with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.reader(f, delimiter="\t")
                for row in reader:
                    if len(row) < 5:
                        continue
                    row_country = str(row[0] or "").strip().upper()
                    if row_country and row_country != code:
                        continue

                    zip_code = self._normalize_zip_for_country(code, str(row[1] or "").strip())
                    city = str(row[2] or "").strip()
                    state_name = str(row[3] or "").strip()
                    state_code = self._normalize_state_code(state_name=state_name, state_code=str(row[4] or "").strip())

                    if not zip_code or not city or not state_code:
                        continue
                    if not state_name:
                        state_name = state_code

                    if state_code not in state_names:
                        state_names[state_code] = state_name
                    cities_by_state.setdefault(state_code, set()).add(city)
                    zips_by_state.setdefault(state_code, set()).add(zip_code)
                    city_key = f"{state_code}|{city.lower()}"
                    zips_by_state_city.setdefault(city_key, set()).add(zip_code)
        except Exception as exc:
            raise RuntimeError(f"Failed to parse {code} ZIP dataset: {exc}") from exc

        self._state_name_by_country_code[code] = state_names
        self._states_by_country[code] = sorted(
            [{"code": state_code, "name": state_name} for state_code, state_name in state_names.items()],
            key=lambda x: (x["name"], x["code"]),
        )
        self._cities_by_country_state[code] = {
            state_code: sorted(values, key=lambda x: x.lower())
            for state_code, values in cities_by_state.items()
        }
        self._zips_by_country_state[code] = {
            state_code: sorted(values)
            for state_code, values in zips_by_state.items()
        }
        self._zips_by_country_state_city[code] = {
            city_key: sorted(values)
            for city_key, values in zips_by_state_city.items()
        }
        self._loaded_countries.add(code)
        logger.info(
            f"{code} location directory loaded | "
            f"states={len(self._states_by_country.get(code, []))} "
            f"cities={sum(len(v) for v in self._cities_by_country_state.get(code, {}).values())} "
            f"zips={sum(len(v) for v in self._zips_by_country_state.get(code, {}).values())}"
        )

    def _ensure_loaded(self, country_code: str) -> str:
        code = str(country_code or "US").strip().upper() or "US"
        if code not in self._source_urls:
            raise RuntimeError(f"Unsupported country dataset: {code}")
        with self._lock:
            self._load_country_locked(code)
        return code

    def list_states(self, country_code: str = "US") -> List[Dict[str, str]]:
        code = self._ensure_loaded(country_code)
        return [dict(item) for item in self._states_by_country.get(code, [])]

    def list_cities(self, country_code: str, state_code: str, query: str = "", limit: int = 5000) -> List[str]:
        code = self._ensure_loaded(country_code)
        state = str(state_code or "").strip().upper()
        if not state:
            return []
        by_state = self._cities_by_country_state.get(code, {})
        cities = list(by_state.get(state, []))
        q = str(query or "").strip().lower()
        if q:
            cities = [city for city in cities if q in city.lower()]
        max_items = max(1, min(int(limit), 50000))
        return cities[:max_items]

    def list_zips(
        self,
        country_code: str,
        state_code: str,
        city: str = "",
        query: str = "",
        limit: int = 5000,
    ) -> List[str]:
        code = self._ensure_loaded(country_code)
        state = str(state_code or "").strip().upper()
        if not state:
            return []

        city_clean = str(city or "").strip()
        if city_clean:
            key = f"{state}|{city_clean.lower()}"
            by_city = self._zips_by_country_state_city.get(code, {})
            zips = list(by_city.get(key, []))
        else:
            by_state = self._zips_by_country_state.get(code, {})
            zips = list(by_state.get(state, []))

        q = str(query or "").strip()
        if q:
            zips = [zip_code for zip_code in zips if q in zip_code]
        max_items = max(1, min(int(limit), 50000))
        return zips[:max_items]

    def list_area_zips(
        self,
        country_code: str,
        state_code: str,
        area_query: str,
        limit: int = 5000,
    ) -> tuple[List[str], List[str]]:
        code = self._ensure_loaded(country_code)
        state = str(state_code or "").strip().upper()
        area = str(area_query or "").strip().lower()
        if not state or not area:
            return [], []

        by_state = self._cities_by_country_state.get(code, {})
        cities = list(by_state.get(state, []))
        matched_cities = [city for city in cities if area in city.lower()]
        if not matched_cities:
            return [], []

        by_city = self._zips_by_country_state_city.get(code, {})
        zip_pool: set[str] = set()
        for city in matched_cities:
            city_key = f"{state}|{city.lower()}"
            for zip_code in by_city.get(city_key, []):
                zip_pool.add(zip_code)

        max_items = max(1, min(int(limit), 50000))
        zips = sorted(zip_pool)[:max_items]
        return zips, matched_cities

    def state_name(self, country_code: str, state_code: str) -> str:
        code = self._ensure_loaded(country_code)
        state = str(state_code or "").strip().upper()
        by_code = self._state_name_by_country_code.get(code, {})
        return by_code.get(state, "")


class JobManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._active_jobs = 0
        self._history_file = _runtime_root_dir() / "jobs_history.json"
        self._load_history()
        logger.info("JobManager initialized with persistence")

    def _load_history(self) -> None:
        if not self._history_file.exists():
            return
        try:
            import json
            with open(self._history_file, 'r', encoding='utf-8') as f:
                saved_jobs = json.load(f)
                for jid, job in saved_jobs.items():
                    # Only load metadata, not full results in memory to save RAM if large
                    # But for simplicity in this app, we load everything or handle results specifically
                    # Let's verify checkpont file existence
                    self._jobs[jid] = job
        except Exception as e:
            logger.error(f"Failed to load job history: {e}")

    def _save_history(self) -> None:
        try:
            import json
            # Create a serializable copy
            serializable_jobs = {}
            with self._lock:
                for jid, job in self._jobs.items():
                    # Check if results are too large? For now save all.
                    # Or better, don't save 'results' array in JSON if it's large, rely on checkpoint file?
                    # For this implementation, we will keep it simple and save all.
                    serializable_jobs[jid] = job
            
            with open(self._history_file, 'w', encoding='utf-8') as f:
                json.dump(serializable_jobs, f, default=str)
        except Exception as e:
            logger.error(f"Failed to save job history: {e}")

    def create_job(self, params: Dict[str, Any]) -> str:
        with self._lock:
            if self._active_jobs >= MAX_CONCURRENT_JOBS:
                raise RuntimeError(f"Maximum concurrent jobs ({MAX_CONCURRENT_JOBS}) reached. Please wait.")
        
        job_id = str(uuid.uuid4())
        now = utc_now_iso()
        job = {
            "job_id": job_id,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "finished_at": None,
            "params": params,
            "progress": 0,
            "total": 0,
            "message": "Queued",
            "error": None,
            "results": [],
            "checkpoint_file": "",
            "checkpoint_rows": 0,
            "history_snapshot_file": "",
            "crm_file_csv": "",
            "crm_file_json": "",
            "crm_file_xlsx": "",
            "crm_file_saved_at": "",
            "crm_file_rows": 0,
            "dedup_removed_count": 0,
            "schedule_id": "",
        }
        with self._lock:
            self._jobs[job_id] = job
        self._save_history() # Save on create
        logger.info(f"Job created: {job_id} | Mode: {params.get('mode', 'single')}")
        return job_id

    def get(self, job_id: str) -> Dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            return dict(job)

    def delete(self, job_id: str) -> bool:
        deleted = False
        with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                deleted = True
        if deleted:
            self._save_history()
            return True
        return False

    def update(self, job_id: str, **updates: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            
            old_status = job.get("status")
            new_status = updates.get("status")
            
            if old_status != "running" and new_status == "running":
                self._active_jobs += 1
            elif old_status == "running" and new_status in ("completed", "failed"):
                self._active_jobs = max(0, self._active_jobs - 1)
            
            job.update(updates)
            job["updated_at"] = utc_now_iso()

        should_persist = new_status in ("completed", "failed") or any(
            str(key).startswith("crm_file_") for key in updates.keys()
        )
        if should_persist:
            self._save_history()
            if new_status in ("completed", "failed"):
                logger.info(f"Job {new_status}: {job_id}")

    def results(self, job_id: str) -> List[Dict[str, Any]] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            return list(job.get("results", []))

    def list_all(self) -> List[Dict[str, Any]]:
        with self._lock:
            # Return summary list
            return [
                {
                    "job_id": j["job_id"],
                    "status": j["status"],
                    "created_at": j["created_at"],
                    "keyword": j["params"].get("keyword", "Bulk/Resume"),
                    "location": j["params"].get("location", ""),
                    "total_leads": len(_successful_result_rows(j.get("results", []))),
                    "mode": j["params"].get("mode", "single"),
                    "crm_file_csv": str(j.get("crm_file_csv", "")),
                    "crm_file_json": str(j.get("crm_file_json", "")),
                    "crm_file_xlsx": str(j.get("crm_file_xlsx", "")),
                    "crm_file_saved_at": str(j.get("crm_file_saved_at", "")),
                    "crm_file_rows": _to_int(j.get("crm_file_rows", 0), default=0, low=0, high=10_000_000),
                }
                for j in self._jobs.values()
            ]

    def to_api_payload(self, job: Dict[str, Any], include_results: bool = False) -> Dict[str, Any]:
        payload = dict(job)
        if not include_results:
            payload.pop("results", None)
        payload["result_count"] = len(_successful_result_rows(job.get("results", [])))
        payload["error_count"] = len(_failed_result_rows(job.get("results", [])))
        return payload







app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="/static")
# Avoid stale JS/CSS during local runs (Waitress + browser cache can otherwise keep old frontend code).
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
jobs = JobManager()
crm = DatabaseCRMStore(CRM_DB_FILE)
presets = PresetStore(PRESETS_DATA_FILE)
zip_packs = ZipPackStore(ZIP_PACKS_DATA_FILE)
notifications = NotificationManager(NOTIFICATIONS_DATA_FILE)
locations = USLocationDirectory(
    data_dir=LOCATION_DATA_DIR,
    source_urls=LOCATION_ZIP_SOURCE_URLS,
)








def _write_checkpoint(job_id: str, rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return ""
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_path = CHECKPOINT_DIR / f"{job_id}_checkpoint.csv"
    pd.DataFrame(rows).to_csv(checkpoint_path, index=False, encoding="utf-8-sig")
    return str(checkpoint_path)


def _read_rows_from_upload(file_storage, purpose: str) -> List[Dict[str, Any]]:
    filename = file_storage.filename or "upload"
    ext = os.path.splitext(filename)[1].lower()
    stream = io.BytesIO(file_storage.read())
    stream.seek(0)

    if ext == ".csv":
        df = pd.read_csv(stream)
    elif ext in {".xlsx", ".xls"}:
        df = pd.read_excel(stream)
    else:
        raise ValueError(f"{purpose}: only .csv, .xlsx, or .xls files are supported")

    if df.empty:
        return []

    rows: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        payload: Dict[str, Any] = {}
        for col in df.columns:
            value = row.get(col, "")
            payload[str(col)] = "" if pd.isna(value) else value
        rows.append(payload)
    return rows


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(0))
    except (TypeError, ValueError):
        return None


def _parse_int(value: Any) -> int:
    if value is None:
        return 0
    text = str(value).strip()
    if not text:
        return 0
    match = re.search(r"\d[\d,]*", text)
    if not match:
        return 0
    try:
        return int(match.group(0).replace(",", ""))
    except (TypeError, ValueError):
        return 0


def _normalize_category(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _business_identity_key(row: Dict[str, Any]) -> str:
    place_id = str(row.get("place_id", "")).strip()
    feature_id = str(row.get("feature_id", "")).strip()
    maps_url = str(row.get("google_maps_url", "")).strip()
    phone = str(row.get("phone", "")).strip()
    name = re.sub(r"\s+", " ", str(row.get("name", "")).strip().lower())
    address = re.sub(r"\s+", " ", str(row.get("address", "")).strip().lower())
    if place_id:
        return f"place:{place_id}"
    if feature_id:
        return f"feature:{feature_id}"
    if maps_url:
        return f"url:{maps_url}"
    if phone and name:
        return f"phone_name:{phone}|{name}"
    return f"name_addr:{name}|{address}"


def _load_history_master() -> Dict[str, Dict[str, Any]]:
    if not HISTORY_MASTER_FILE.exists():
        return {}
    try:
        df = pd.read_csv(HISTORY_MASTER_FILE)
    except Exception:
        return {}

    cache: Dict[str, Dict[str, Any]] = {}
    for _, row in df.iterrows():
        key = str(row.get("identity_key", "")).strip()
        if not key:
            continue
        cache[key] = {
            "rating": "" if pd.isna(row.get("rating")) else str(row.get("rating")),
            "review_count": "" if pd.isna(row.get("review_count")) else str(row.get("review_count")),
            "business_status": "" if pd.isna(row.get("business_status")) else str(row.get("business_status")),
            "last_seen_at": "" if pd.isna(row.get("last_seen_at")) else str(row.get("last_seen_at")),
            "name": "" if pd.isna(row.get("name")) else str(row.get("name")),
        }
    return cache


def _apply_change_tracking(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    previous = _load_history_master()
    tracked = [dict(row) for row in rows]

    for row in tracked:
        key = _business_identity_key(row)
        prev = previous.get(key)

        row["change_flag"] = "No"
        row["previous_rating"] = ""
        row["rating_change"] = ""
        row["previous_review_count"] = ""
        row["review_count_change"] = ""
        row["previous_business_status"] = ""
        row["status_changed"] = "No"
        row["previous_seen_at"] = ""

        if not prev:
            row["change_flag"] = "New"
            continue

        cur_rating = _parse_float(row.get("rating"))
        prev_rating = _parse_float(prev.get("rating"))
        cur_reviews = _parse_int(row.get("review_count"))
        prev_reviews = _parse_int(prev.get("review_count"))
        cur_status = str(row.get("business_status", "")).strip().lower()
        prev_status = str(prev.get("business_status", "")).strip().lower()

        changed = False
        if prev_rating is not None:
            row["previous_rating"] = f"{prev_rating:.1f}"
        if cur_rating is not None and prev_rating is not None:
            delta = cur_rating - prev_rating
            row["rating_change"] = f"{delta:+.1f}" if abs(delta) >= 0.05 else "+0.0"
            if abs(delta) >= 0.05:
                changed = True

        row["previous_review_count"] = str(prev_reviews) if prev_reviews else ""
        review_delta = cur_reviews - prev_reviews
        row["review_count_change"] = f"{review_delta:+d}" if review_delta else "+0"
        if review_delta != 0:
            changed = True

        row["previous_business_status"] = str(prev.get("business_status", ""))
        if cur_status != prev_status:
            row["status_changed"] = "Yes"
            changed = True

        row["previous_seen_at"] = str(prev.get("last_seen_at", ""))
        row["change_flag"] = "Yes" if changed else "No"

    return tracked


def _persist_history(rows: List[Dict[str, Any]], job_id: str) -> str:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    snapshot_path = HISTORY_DIR / f"{job_id}_snapshot.csv"
    if rows:
        pd.DataFrame(rows).to_csv(snapshot_path, index=False, encoding="utf-8-sig")

    previous = _load_history_master()
    now = utc_now_iso()
    for row in rows:
        key = _business_identity_key(row)
        if not key:
            continue
        previous[key] = {
            "identity_key": key,
            "name": str(row.get("name", "")),
            "place_id": str(row.get("place_id", "")),
            "feature_id": str(row.get("feature_id", "")),
            "address": str(row.get("address", "")),
            "phone": str(row.get("phone", "")),
            "rating": str(row.get("rating", "")),
            "review_count": str(row.get("review_count", "")),
            "business_status": str(row.get("business_status", "")),
            "google_maps_url": str(row.get("google_maps_url", "")),
            "last_seen_at": now,
        }

    if previous:
        pd.DataFrame(list(previous.values())).to_csv(HISTORY_MASTER_FILE, index=False, encoding="utf-8-sig")

    return str(snapshot_path)


def _crm_job_file_key(job_id: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(job_id or "").strip())
    return clean[:120] or "job"


def _crm_job_file_paths(job_id: str) -> tuple[Path, Path]:
    key = _crm_job_file_key(job_id)
    csv_path = CRM_JOB_FILES_DIR / f"{key}.csv"
    json_path = CRM_JOB_FILES_DIR / f"{key}.json"
    return csv_path, json_path


def _crm_job_file_xlsx_path(job_id: str) -> Path:
    key = _crm_job_file_key(job_id)
    return CRM_JOB_FILES_DIR / f"{key}.xlsx"


def _crm_job_file_paths_all(job_id: str) -> tuple[Path, Path, Path]:
    csv_path, json_path = _crm_job_file_paths(job_id)
    xlsx_path = _crm_job_file_xlsx_path(job_id)
    return csv_path, json_path, xlsx_path


def _write_crm_job_file(rows: List[Dict[str, Any]], job_id: str, source_job_created_at: str = "") -> Dict[str, Any]:
    CRM_JOB_FILES_DIR.mkdir(parents=True, exist_ok=True)
    csv_path, json_path = _crm_job_file_paths(job_id)
    xlsx_path = _crm_job_file_xlsx_path(job_id)
    saved_at = utc_now_iso()
    safe_rows = [dict(row) for row in (rows or []) if isinstance(row, dict)]

    # CSV snapshot for easy sharing/import.
    pd.DataFrame(safe_rows).to_csv(csv_path, index=False, encoding="utf-8-sig")

    # JSON snapshot preserves full fidelity for CRM automation use-cases.
    payload = {
        "job_id": str(job_id),
        "source_job_created_at": str(source_job_created_at or ""),
        "saved_at": saved_at,
        "row_count": len(safe_rows),
        "rows": safe_rows,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

    xlsx_file = ""
    try:
        with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
            pd.DataFrame(safe_rows).to_excel(writer, index=False, sheet_name="leads")
        xlsx_file = str(xlsx_path)
    except Exception as exc:
        logger.error(f"Failed to write CRM XLSX file for {job_id}: {exc}")

    return {
        "job_id": str(job_id),
        "saved_at": saved_at,
        "row_count": len(safe_rows),
        "csv_file": str(csv_path),
        "json_file": str(json_path),
        "xlsx_file": xlsx_file,
    }


def _read_crm_job_file_meta(job_id: str) -> Dict[str, Any] | None:
    csv_path, json_path = _crm_job_file_paths(job_id)
    xlsx_path = _crm_job_file_xlsx_path(job_id)
    if not csv_path.exists() and not json_path.exists():
        return None

    row_count = 0
    saved_at = ""
    source_job_created_at = ""
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload, dict):
                row_count = _to_int(payload.get("row_count", 0), default=0, low=0, high=10_000_000)
                saved_at = str(payload.get("saved_at", "")).strip()
                source_job_created_at = str(payload.get("source_job_created_at", "")).strip()
        except Exception:
            row_count = 0

    if not saved_at:
        try:
            target = json_path if json_path.exists() else csv_path
            saved_at = datetime.fromtimestamp(target.stat().st_mtime, timezone.utc).isoformat()
        except Exception:
            saved_at = ""

    return {
        "job_id": str(job_id),
        "row_count": row_count,
        "saved_at": saved_at,
        "source_job_created_at": source_job_created_at,
        "csv_file": str(csv_path) if csv_path.exists() else "",
        "json_file": str(json_path) if json_path.exists() else "",
        "xlsx_file": str(xlsx_path) if xlsx_path.exists() else "",
    }


def _load_crm_job_dataframe(job_id: str) -> pd.DataFrame | None:
    csv_path, json_path = _crm_job_file_paths(job_id)
    if csv_path.exists():
        try:
            return pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        except Exception as exc:
            logger.error(f"Failed to read CRM job CSV for {job_id}: {exc}")
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            rows = payload.get("rows", []) if isinstance(payload, dict) else []
            if not isinstance(rows, list):
                rows = []
            return pd.DataFrame(rows)
        except Exception as exc:
            logger.error(f"Failed to read CRM job JSON for {job_id}: {exc}")
    return None


def _safe_sheet_name(name: str, used: set[str]) -> str:
    base = re.sub(r"[\[\]\*\?/\\:]", "_", str(name or "").strip())
    base = re.sub(r"\s+", " ", base).strip() or "Sheet"
    base = base[:31]
    if base not in used:
        used.add(base)
        return base
    counter = 2
    while True:
        suffix = f"_{counter}"
        trimmed = base[: max(1, 31 - len(suffix))]
        candidate = f"{trimmed}{suffix}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        counter += 1


def _crm_job_sheet_title(job_id: str) -> str:
    job = jobs.get(job_id)
    if job:
        keyword = str(job.get("params", {}).get("keyword", "")).strip()
        location = str(job.get("params", {}).get("location", "")).strip()
        if keyword and location:
            return f"{keyword} | {location}"
        if keyword:
            return keyword
        if location:
            return location
    return str(job_id)[:12]


def _list_crm_job_files(limit: int = 500) -> List[Dict[str, Any]]:
    cap = max(1, min(int(limit), 5000))
    CRM_JOB_FILES_DIR.mkdir(parents=True, exist_ok=True)
    metas: List[Dict[str, Any]] = []
    for json_path in CRM_JOB_FILES_DIR.glob("*.json"):
        job_id = json_path.stem
        meta = _read_crm_job_file_meta(job_id)
        if meta:
            metas.append(meta)
    metas.sort(key=lambda x: str(x.get("saved_at", "")), reverse=True)
    return metas[:cap]


def _apply_dedup(rows: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], int]:
    unique_rows: List[Dict[str, Any]] = []
    seen: Dict[str, int] = {}
    removed = 0

    for row in rows:
        item = dict(row)
        key = _business_identity_key(item)
        item["identity_key"] = key
        if key in seen:
            removed += 1
            first_idx = seen[key]
            first = unique_rows[first_idx]
            first_error = str(first.get("error", "")).strip()
            current_error = str(item.get("error", "")).strip()
            # Prefer non-error row if duplicate pair has one good row and one failed row.
            if first_error and not current_error:
                unique_rows[first_idx] = item
            continue
        seen[key] = len(unique_rows)
        unique_rows.append(item)

    return unique_rows, removed


def _enrich_quality_flags(rows: List[Dict[str, Any]]) -> None:
    for row in rows:
        score = 100
        flags: List[str] = []

        if str(row.get("error", "")).strip():
            score -= 70
            flags.append("scrape_error")

        if not str(row.get("name", "")).strip():
            score -= 20
            flags.append("missing_name")
        if not str(row.get("address", "")).strip():
            score -= 15
            flags.append("missing_address")
        if not str(row.get("phone", "")).strip():
            score -= 10
            flags.append("missing_phone")
        if not str(row.get("website", "")).strip():
            score -= 5
            flags.append("missing_website")

        lat = _parse_float(row.get("latitude"))
        lng = _parse_float(row.get("longitude"))
        if lat is None or lng is None:
            score -= 15
            flags.append("missing_coordinates")

        rating = _parse_float(row.get("rating"))
        if rating is None:
            score -= 8
            flags.append("missing_rating")

        reviews = _parse_int(row.get("review_count"))
        if reviews == 0:
            score -= 5
            flags.append("no_reviews")

        status = str(row.get("business_status", "")).lower()
        if "closed" in status:
            flags.append("closed_business")
            score -= 8

        score = max(0, min(100, score))
        if score >= 85:
            band = "High"
        elif score >= 60:
            band = "Medium"
        else:
            band = "Low"

        row["data_quality_score"] = score
        row["data_quality_band"] = band
        row["data_quality_flags"] = ";".join(flags)


def _enrich_area_clusters(rows: List[Dict[str, Any]], precision: int = 2) -> None:
    groups: Dict[str, List[int]] = {}
    for idx, row in enumerate(rows):
        lat = _parse_float(row.get("latitude"))
        lng = _parse_float(row.get("longitude"))
        if lat is None or lng is None:
            row["area_cluster_id"] = ""
            row["area_cluster_size"] = "0"
            row["area_cluster_rank"] = ""
            row["area_hotspot"] = "No"
            continue
        cluster_id = f"{round(lat, precision):.{precision}f}_{round(lng, precision):.{precision}f}"
        row["area_cluster_id"] = cluster_id
        groups.setdefault(cluster_id, []).append(idx)

    cluster_sizes = sorted(((cid, len(idxs)) for cid, idxs in groups.items()), key=lambda x: x[1], reverse=True)
    rank_map = {cid: rank + 1 for rank, (cid, _) in enumerate(cluster_sizes)}

    for cid, idxs in groups.items():
        size = len(idxs)
        rank = rank_map.get(cid, "")
        hotspot = "Yes" if size >= 3 else "No"
        for idx in idxs:
            rows[idx]["area_cluster_size"] = str(size)
            rows[idx]["area_cluster_rank"] = str(rank)
            rows[idx]["area_hotspot"] = hotspot


def _enrich_competitor_gap(rows: List[Dict[str, Any]]) -> None:
    for row in rows:
        rating = _parse_float(row.get("rating"))
        competitor_avg = _parse_float(row.get("competitor_avg_rating"))
        review_count = _parse_int(row.get("review_count"))
        top_reviews = _parse_int(row.get("top_competitor_reviews"))
        lead_score = _to_int(row.get("lead_score", 0), default=0, low=0, high=100)

        rating_gap = ""
        review_gap = ""
        opportunity = lead_score

        if rating is not None and competitor_avg is not None:
            rg = rating - competitor_avg
            rating_gap = f"{rg:+.2f}"
            if rg < -0.3:
                opportunity += 8
            elif rg > 0.3:
                opportunity -= 6

        if top_reviews > 0:
            diff = review_count - top_reviews
            review_gap = f"{diff:+d}"
            if diff < -100:
                opportunity += 6

        opportunity = max(0, min(100, opportunity))
        if opportunity >= 75:
            band = "High"
        elif opportunity >= 45:
            band = "Medium"
        else:
            band = "Low"

        row["competitor_rating_gap"] = rating_gap
        row["competitor_review_gap"] = review_gap
        row["opportunity_score"] = opportunity
        row["opportunity_band"] = band


def _build_cluster_summary(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    bucket: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        cid = str(row.get("area_cluster_id", "")).strip()
        if not cid:
            continue
        if cid not in bucket:
            bucket[cid] = {
                "area_cluster_id": cid,
                "business_count": 0,
                "avg_rating": 0.0,
                "avg_lead_score": 0.0,
                "high_priority_count": 0,
                "_rating_sum": 0.0,
                "_rating_count": 0,
                "_lead_sum": 0,
            }
        cur = bucket[cid]
        cur["business_count"] += 1
        rating = _parse_float(row.get("rating"))
        if rating is not None:
            cur["_rating_sum"] += rating
            cur["_rating_count"] += 1
        lead = _to_int(row.get("lead_score", 0), default=0, low=0, high=100)
        cur["_lead_sum"] += lead
        if str(row.get("lead_priority", "")).lower() == "high":
            cur["high_priority_count"] += 1

    output: List[Dict[str, Any]] = []
    for cid, cur in bucket.items():
        rc = cur.pop("_rating_count")
        rs = cur.pop("_rating_sum")
        ls = cur.pop("_lead_sum")
        bc = cur["business_count"] or 1
        cur["avg_rating"] = f"{(rs / rc):.2f}" if rc else ""
        cur["avg_lead_score"] = round(ls / bc, 2)
        output.append(cur)

    output.sort(key=lambda x: (x["high_priority_count"], x["business_count"]), reverse=True)
    return output


def _build_outreach_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    leads = []
    for row in rows:
        priority = str(row.get("lead_priority", "")).lower()
        if priority not in {"high", "medium"}:
            continue
        if str(row.get("business_status", "")).lower().find("closed") >= 0:
            continue
        pitch = (
            f"Hi {str(row.get('name', 'there')).strip()}, "
            f"we noticed strong local demand in your area and can help improve lead flow."
        )
        leads.append(
            {
                "business_name": row.get("name", ""),
                "phone": row.get("phone", ""),
                "email_or_website": row.get("website", ""),
                "address": row.get("address", ""),
                "lead_priority": row.get("lead_priority", ""),
                "lead_score": row.get("lead_score", ""),
                "lead_reason": row.get("lead_reason", ""),
                "opportunity_score": row.get("opportunity_score", ""),
                "pitch_template": pitch,
            }
        )

    leads.sort(key=lambda x: int(x.get("lead_score") or 0), reverse=True)
    return leads


def _build_crm_rows(rows: List[Dict[str, Any]], provider: str) -> List[Dict[str, Any]]:
    provider_key = provider.strip().lower()
    base = []
    for row in rows:
        if str(row.get("error", "")).strip():
            continue
        base.append(
            {
                "company": row.get("name", ""),
                "phone": row.get("phone", ""),
                "website": row.get("website", ""),
                "address": row.get("address", ""),
                "city": row.get("search_location", ""),
                "industry": row.get("category", ""),
                "lead_score": row.get("lead_score", ""),
                "lead_priority": row.get("lead_priority", ""),
                "source": "Google Maps Scraper",
                "maps_url": row.get("google_maps_url", ""),
                "place_id": row.get("place_id", ""),
            }
        )

    mapped: List[Dict[str, Any]] = []
    for row in base:
        if provider_key == "hubspot":
            mapped.append(
                {
                    "Company name": row["company"],
                    "Phone Number": row["phone"],
                    "Website URL": row["website"],
                    "Street Address": row["address"],
                    "City": row["city"],
                    "Industry": row["industry"],
                    "Lead Score": row["lead_score"],
                    "Lead Status": row["lead_priority"],
                    "Original Source": row["source"],
                    "Google Maps URL": row["maps_url"],
                    "Place ID": row["place_id"],
                }
            )
        elif provider_key == "zoho":
            mapped.append(
                {
                    "Company": row["company"],
                    "Phone": row["phone"],
                    "Website": row["website"],
                    "Street": row["address"],
                    "City": row["city"],
                    "Industry": row["industry"],
                    "Lead Score": row["lead_score"],
                    "Lead Status": row["lead_priority"],
                    "Lead Source": row["source"],
                    "Google Maps URL": row["maps_url"],
                    "Place ID": row["place_id"],
                }
            )
        else:  # salesforce default
            mapped.append(
                {
                    "Company": row["company"],
                    "Phone": row["phone"],
                    "Website": row["website"],
                    "Street": row["address"],
                    "City": row["city"],
                    "Industry": row["industry"],
                    "Rating": row["lead_priority"],
                    "Lead_Score__c": row["lead_score"],
                    "LeadSource": row["source"],
                    "Google_Maps_URL__c": row["maps_url"],
                    "Place_ID__c": row["place_id"],
                }
            )
    return mapped


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def _enrich_competitor_insights(rows: List[Dict[str, Any]], competitor_radius_km: float) -> None:
    if competitor_radius_km <= 0:
        return

    groups: Dict[tuple[str, str], List[tuple[int, float, float]]] = {}
    for idx, row in enumerate(rows):
        lat = _parse_float(row.get("latitude"))
        lng = _parse_float(row.get("longitude"))
        if lat is None or lng is None:
            continue
        category = _normalize_category(row.get("category", ""))
        if not category:
            continue
        query_scope = str(row.get("query_index") or "single")
        key = (query_scope, category)
        groups.setdefault(key, []).append((idx, lat, lng))

    lat_delta = competitor_radius_km / 111.0
    for _, items in groups.items():
        if len(items) < 2:
            continue

        sorted_items = sorted(items, key=lambda x: x[1])
        left = 0
        n = len(sorted_items)

        for pos, (idx_i, lat_i, lng_i) in enumerate(sorted_items):
            while left < n and sorted_items[left][1] < lat_i - lat_delta:
                left += 1

            right = pos + 1
            while right < n and sorted_items[right][1] <= lat_i + lat_delta:
                right += 1

            competitor_count = 0
            nearest: float | None = None
            top_idx: int | None = None
            top_key = (-1.0, -1)
            rating_sum = 0.0
            rated_count = 0

            for scan in range(left, right):
                idx_j, lat_j, lng_j = sorted_items[scan]
                if idx_j == idx_i:
                    continue
                distance = _haversine_km(lat_i, lng_i, lat_j, lng_j)
                if distance > competitor_radius_km:
                    continue

                competitor_count += 1
                if nearest is None or distance < nearest:
                    nearest = distance

                rating = _parse_float(rows[idx_j].get("rating"))
                reviews = _parse_int(rows[idx_j].get("review_count"))
                if rating is not None:
                    rating_sum += rating
                    rated_count += 1
                score_key = (rating if rating is not None else -1.0, reviews)
                if score_key > top_key:
                    top_key = score_key
                    top_idx = idx_j

            row = rows[idx_i]
            row["competitor_count_within_radius"] = str(competitor_count)
            row["nearest_competitor_distance_km"] = f"{nearest:.2f}" if nearest is not None else ""
            row["competitor_avg_rating"] = f"{(rating_sum / rated_count):.2f}" if rated_count else ""

            if top_idx is not None:
                top = rows[top_idx]
                row["top_competitor_name"] = str(top.get("name", ""))
                row["top_competitor_rating"] = str(top.get("rating", ""))
                row["top_competitor_reviews"] = str(top.get("review_count", ""))
                row["top_competitor_place_id"] = str(top.get("place_id", ""))


def _compute_lead_score(row: Dict[str, Any]) -> tuple[int, str, str]:
    if str(row.get("error", "")).strip():
        return 0, "Low", "Scrape error"

    status = str(row.get("business_status", "")).lower()
    if "permanently closed" in status or "temporarily closed" in status:
        return 0, "Low", "Business closed"

    score = 0
    reasons: List[str] = []

    rating = _parse_float(row.get("rating"))
    reviews = _parse_int(row.get("review_count"))
    photos = _parse_int(row.get("photos_count"))
    competitor_count = _parse_int(row.get("competitor_count_within_radius"))

    if rating is not None:
        if rating >= 4.5:
            score += 24
            reasons.append("Excellent rating")
        elif rating >= 4.2:
            score += 18
            reasons.append("Strong rating")
        elif rating >= 3.8:
            score += 10
            reasons.append("Average-good rating")

    if reviews <= 80 and reviews > 0 and (rating or 0) >= 4.0:
        score += 20
        reasons.append("High rating with low reviews")
    elif reviews <= 200 and reviews > 0:
        score += 10
        reasons.append("Moderate reviews")

    if not str(row.get("website", "")).strip():
        score += 14
        reasons.append("No website")
    if not str(row.get("phone", "")).strip():
        score += 4

    open_now = str(row.get("open_now", "")).lower()
    if "open" in open_now and "closed" not in open_now:
        score += 8
        reasons.append("Open now")

    if str(row.get("has_owner_responses", "")).strip().lower() == "no":
        score += 8
        reasons.append("No owner responses")

    if photos > 0 and photos <= 20:
        score += 6
        reasons.append("Low photos")

    if competitor_count <= 3:
        score += 10
        reasons.append("Low nearby competition")
    elif competitor_count >= 12:
        score -= 8

    score = max(0, min(100, score))
    if score >= 70:
        priority = "High"
    elif score >= 45:
        priority = "Medium"
    else:
        priority = "Low"

    return score, priority, "; ".join(reasons[:4])


def _apply_market_enrichment(rows: List[Dict[str, Any]], competitor_radius_km: float) -> List[Dict[str, Any]]:
    enriched = [dict(row) for row in rows]
    for row in enriched:
        row.setdefault("competitor_count_within_radius", "0")
        row.setdefault("nearest_competitor_distance_km", "")
        row.setdefault("competitor_avg_rating", "")
        row.setdefault("top_competitor_name", "")
        row.setdefault("top_competitor_rating", "")
        row.setdefault("top_competitor_reviews", "")
        row.setdefault("top_competitor_place_id", "")
        row.setdefault("lead_score", 0)
        row.setdefault("lead_priority", "Low")
        row.setdefault("lead_reason", "")

    _enrich_competitor_insights(enriched, competitor_radius_km=competitor_radius_km)

    for row in enriched:
        score, priority, reason = _compute_lead_score(row)
        row["lead_score"] = score
        row["lead_priority"] = priority
        row["lead_reason"] = reason

    return enriched


def _finalize_rows(rows: List[Dict[str, Any]], competitor_radius_km: float, dedupe_enabled: bool = True) -> tuple[List[Dict[str, Any]], int]:
    work_rows = [dict(r) for r in rows]
    dedup_removed = 0
    if dedupe_enabled:
        work_rows, dedup_removed = _apply_dedup(work_rows)

    enriched = _apply_market_enrichment(work_rows, competitor_radius_km=competitor_radius_km)
    _enrich_competitor_gap(enriched)
    _enrich_area_clusters(enriched)
    _enrich_quality_flags(enriched)

    tracked_rows = _apply_change_tracking(enriched)
    return tracked_rows, dedup_removed


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "on"}


def _to_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, parsed))


def _to_float(value: Any, default: float, low: float, high: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, parsed))


def _pick_column(df: pd.DataFrame, candidates: List[str]) -> str:
    lowered = {str(col).strip().lower(): str(col) for col in df.columns}
    for candidate in candidates:
        col = lowered.get(candidate.strip().lower())
        if col:
            return col
    return ""


def _parse_keyword_list(raw_text: str, max_items: int = 24) -> List[str]:
    tokens = re.split(r"[,\n;|]+", str(raw_text or ""))
    out: List[str] = []
    seen: set[str] = set()
    for token in tokens:
        cleaned = re.sub(r"\s+", " ", token).strip()
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        out.append(cleaned[:80])
        if len(out) >= max_items:
            break
    return out


def _clean_location_phrase(value: Any, max_len: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:max_len]


def _normalize_zip_token(value: Any) -> str:
    cleaned = re.sub(r"\s+", "", str(value or ""))
    cleaned = re.sub(r"[^0-9-]", "", cleaned)
    if not cleaned:
        return ""
    digits = cleaned.replace("-", "")
    if len(digits) < 5:
        return ""
    if len(digits) >= 9:
        return f"{digits[:5]}-{digits[5:9]}"
    if len(digits) == 6:
        return digits
    return digits[:5]


def _normalize_zip_locations(raw_value: Any, max_items: int = 500) -> List[Dict[str, str]]:
    tokens: List[Any] = []
    if isinstance(raw_value, list):
        tokens = list(raw_value)
    elif isinstance(raw_value, str):
        tokens = re.split(r"[,\n;|]+", raw_value)
    elif raw_value is not None:
        tokens = [raw_value]

    out: List[Dict[str, str]] = []
    seen: Dict[str, int] = {}
    for token in tokens:
        zip_candidate = ""
        location_candidate = ""
        if isinstance(token, dict):
            zip_candidate = (
                token.get("zip")
                or token.get("zipcode")
                or token.get("postal_code")
                or token.get("code")
                or token.get("value")
                or token.get("location")
                or ""
            )
            location_candidate = token.get("location") or token.get("label") or ""
        else:
            zip_candidate = token

        normalized_zip = _normalize_zip_token(zip_candidate)
        if not normalized_zip:
            continue

        location_text = _clean_location_phrase(location_candidate)
        if not location_text:
            location_text = normalized_zip
        entry = {"zip": normalized_zip, "location": location_text}
        key = normalized_zip.lower()
        existing_index = seen.get(key)
        if existing_index is not None:
            existing = out[existing_index]
            existing_location = str(existing.get("location", "")).strip()
            if (
                existing_location == str(existing.get("zip", "")).strip()
                or len(location_text) > len(existing_location)
            ):
                out[existing_index] = entry
            continue

        seen[key] = len(out)
        out.append(entry)
        if len(out) >= max_items:
            break
    return out


def _build_zip_sweep_queries(
    *,
    seed_keyword: str,
    location: str,
    max_results: int,
    custom_keywords_text: str,
    max_keywords: int,
) -> tuple[List[Dict[str, Any]], List[str]]:
    resolved_keywords: List[str] = []
    seen: set[str] = set()

    def _add_keyword(value: str) -> None:
        cleaned = re.sub(r"\s+", " ", str(value or "")).strip()
        if not cleaned:
            return
        lowered = cleaned.lower()
        if lowered in seen:
            return
        seen.add(lowered)
        resolved_keywords.append(cleaned[:80])

    seed = re.sub(r"\s+", " ", str(seed_keyword or "")).strip()
    custom_keywords = _parse_keyword_list(custom_keywords_text, max_items=max_keywords)

    if custom_keywords:
        _add_keyword(seed)
        for kw in custom_keywords:
            _add_keyword(kw)
    elif seed:
        _add_keyword(seed)
        for suffix in ZIP_SWEEP_SEED_SUFFIXES:
            _add_keyword(f"{seed} {suffix}")
    else:
        for kw in ZIP_SWEEP_FALLBACK_KEYWORDS:
            _add_keyword(kw)

    resolved_keywords = resolved_keywords[:max_keywords]
    queries = [
        {
            "keyword": kw,
            "location": location,
            "max_results": int(max_results),
        }
        for kw in resolved_keywords
    ]
    return queries, resolved_keywords


def _build_query_preview_from_payload(data: Dict[str, Any], max_preview: int = 250) -> Dict[str, Any]:
    keyword = str(data.get("keyword", "")).strip()
    manual_query = str(data.get("manual_query", "")).strip()
    manual_query_mode = _to_bool(data.get("manual_query_mode", False), default=False)
    if manual_query and (manual_query_mode or not keyword):
        keyword = manual_query
    location = str(data.get("location", "")).strip()
    max_results = _to_int(data.get("max_results", 20), default=20, low=1, high=200)
    zip_sweep_enabled = _to_bool(data.get("zip_sweep_enabled", False), default=False)
    bulk_keyword_mode = _to_bool(data.get("bulk_keyword_mode", False), default=False)
    zip_sweep_enabled = zip_sweep_enabled or bulk_keyword_mode
    zip_sweep_keywords = str(data.get("zip_sweep_keywords", "")).strip()
    bulk_keywords = str(data.get("bulk_keywords", "")).strip()
    if bulk_keywords and not zip_sweep_keywords:
        zip_sweep_keywords = bulk_keywords
    zip_sweep_max_keywords = _to_int(
        data.get("zip_sweep_max_keywords", 24),
        default=24,
        low=1,
        high=80,
    )
    zip_locations = _normalize_zip_locations(data.get("zip_locations"), max_items=500)

    mode = "single"
    queries: List[Dict[str, Any]] = []
    keyword_count = 0

    if zip_sweep_enabled:
        if (not keyword) and (not zip_sweep_keywords):
            raise ValueError("keyword or zip_sweep_keywords is required for ZIP sweep mode")
        if zip_locations:
            mode = "zip_sweep_multi_zip"
            merged_keywords: List[str] = []
            seen_keywords: set[str] = set()
            for zip_item in zip_locations:
                zip_location = _clean_location_phrase(zip_item.get("location") or zip_item.get("zip") or "")
                if not zip_location:
                    continue
                sub_queries, resolved_keywords = _build_zip_sweep_queries(
                    seed_keyword=keyword,
                    location=zip_location,
                    max_results=max_results,
                    custom_keywords_text=zip_sweep_keywords,
                    max_keywords=zip_sweep_max_keywords,
                )
                queries.extend(sub_queries)
                for kw in resolved_keywords:
                    lowered = kw.lower()
                    if lowered in seen_keywords:
                        continue
                    seen_keywords.add(lowered)
                    merged_keywords.append(kw)
            keyword_count = len(merged_keywords)
            if not queries:
                raise ValueError("ZIP sweep produced no valid keyword queries")
        else:
            if not location:
                raise ValueError("location/zip is required for ZIP sweep mode")
            mode = "zip_sweep"
            queries, resolved_keywords = _build_zip_sweep_queries(
                seed_keyword=keyword,
                location=location,
                max_results=max_results,
                custom_keywords_text=zip_sweep_keywords,
                max_keywords=zip_sweep_max_keywords,
            )
            keyword_count = len(resolved_keywords)
            if not queries:
                raise ValueError("ZIP sweep produced no valid keyword queries")
    elif zip_locations:
        if not keyword:
            raise ValueError("keyword is required when using ZIP list")
        mode = "multi_zip"
        for zip_item in zip_locations:
            zip_location = _clean_location_phrase(zip_item.get("location") or zip_item.get("zip") or "")
            if not zip_location:
                continue
            queries.append(
                {
                    "keyword": keyword,
                    "location": zip_location,
                    "max_results": max_results,
                }
            )
        if not queries:
            raise ValueError("ZIP list has no valid locations")
        keyword_count = 1
    else:
        if not keyword:
            raise ValueError("keyword is required")
        mode = "single"
        queries = [
            {
                "keyword": keyword,
                "location": location,
                "max_results": max_results,
            }
        ]
        keyword_count = 1

    cap = max(10, min(int(max_preview), 1000))
    preview_queries = []
    for query in queries[:cap]:
        q_keyword = str(query.get("keyword", "")).strip()
        q_location = str(query.get("location", "")).strip()
        q_max = _to_int(query.get("max_results", max_results), default=max_results, low=1, high=200)
        text = q_keyword
        if q_location:
            text = f"{q_keyword} in {q_location}" if q_keyword else q_location
        preview_queries.append(
            {
                "keyword": q_keyword,
                "location": q_location,
                "max_results": q_max,
                "query_text": text.strip(),
            }
        )

    return {
        "mode": mode,
        "query_count": len(queries),
        "zip_count": len(zip_locations),
        "keyword_count": keyword_count,
        "preview_limit": cap,
        "preview_truncated": len(queries) > cap,
        "queries": preview_queries,
    }


def _read_bulk_queries_from_upload(file_storage, default_location: str, default_max_results: int) -> List[Dict[str, Any]]:
    filename = file_storage.filename or "upload"
    ext = os.path.splitext(filename)[1].lower()
    stream = io.BytesIO(file_storage.read())
    stream.seek(0)

    if ext == ".csv":
        df = pd.read_csv(stream)
    elif ext in {".xlsx", ".xls"}:
        df = pd.read_excel(stream)
    else:
        raise ValueError("Only .csv, .xlsx, or .xls files are supported")

    if df.empty:
        return []

    keyword_col = _pick_column(
        df,
        [
            "keyword",
            "query",
            "search",
            "search_term",
            "business",
            "category",
            "term",
            "name",
        ],
    )
    location_col = _pick_column(df, ["location", "city", "area", "address", "state", "country"])
    max_results_col = _pick_column(df, ["max_results", "max result", "limit", "count", "results"])

    if not keyword_col:
        keyword_col = str(df.columns[0])

    queries: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        keyword_raw = row.get(keyword_col, "")
        keyword = "" if pd.isna(keyword_raw) else str(keyword_raw).strip()
        if not keyword:
            continue

        location = default_location
        if location_col:
            location_raw = row.get(location_col, "")
            if not pd.isna(location_raw):
                location = str(location_raw).strip() or default_location

        row_max = default_max_results
        if max_results_col:
            row_max = _to_int(row.get(max_results_col), default=default_max_results, low=1, high=200)

        queries.append(
            {
                "keyword": keyword,
                "location": location,
                "max_results": row_max,
            }
        )

    return queries


SCHEDULES_LOCK = threading.Lock()
SCHEDULES: Dict[str, Dict[str, Any]] = {}


def _launch_job(params: Dict[str, Any], schedule_id: str = "") -> str:
    if schedule_id:
        params = dict(params)
        params["schedule_id"] = schedule_id
    job_id = jobs.create_job(params)
    thread = threading.Thread(target=run_job, args=(job_id,), daemon=True)
    thread.start()
    return job_id


def _run_schedule_loop(schedule_id: str) -> None:
    while True:
        with SCHEDULES_LOCK:
            sched = SCHEDULES.get(schedule_id)
            if not sched:
                return
            if sched["status"] != "active":
                return
            stop_event: threading.Event = sched["stop_event"]
            interval_sec = max(60, int(sched["interval_minutes"] * 60))
            params = dict(sched["job_params"])

        if stop_event.wait(interval_sec):
            return

        try:
            job_id = _launch_job(params, schedule_id=schedule_id)
            with SCHEDULES_LOCK:
                cur = SCHEDULES.get(schedule_id)
                if cur:
                    cur["last_job_id"] = job_id
                    cur["last_run_at"] = utc_now_iso()
                    cur["run_count"] = int(cur.get("run_count", 0)) + 1
        except Exception as exc:
            with SCHEDULES_LOCK:
                cur = SCHEDULES.get(schedule_id)
                if cur:
                    cur["last_error"] = str(exc)


def run_job(job_id: str) -> None:
    job = jobs.get(job_id)
    if not job:
        return

    params = job["params"]
    mode = params.get("mode", "single")
    checkpoint_every = max(1, int(params.get("checkpoint_every", 10)))
    competitor_radius_km = float(params.get("competitor_radius_km", 5.0))
    dedupe_enabled = _to_bool(params.get("dedupe_enabled", True), default=True)
    schedule_id = str(params.get("schedule_id", "")).strip()
    enrich_socials = _to_bool(params.get("enrich_socials", True), default=True)
    enrich_facebook_emails = _to_bool(params.get("enrich_facebook_emails", True), default=True)
    website_max_pages = _to_int(params.get("website_max_pages", 4), default=4, low=1, high=20)
    fast_mode = _to_bool(params.get("fast_mode", True), default=True)
    max_workers = _to_int(params.get("max_workers", 1), default=1, low=1, high=8)
    collect_all_emails = _to_bool(params.get("collect_all_emails", False), default=False)
    adaptive_anti_block = _to_bool(params.get("adaptive_anti_block", True), default=True)
    # Backwards-compatible: older frontends don't send speed_profile; infer a sensible default.
    speed_profile = str(params.get("speed_profile", "") or "").strip().lower()
    if not speed_profile:
        if fast_mode:
            wants_enrichment = bool(enrich_socials or enrich_facebook_emails or website_max_pages > 1)
            speed_profile = "email_fast" if wants_enrichment else "max_speed"
        else:
            speed_profile = "balanced"
    if speed_profile not in {"balanced", "max_speed", "email_fast"}:
        speed_profile = "balanced"

    effective_max_retries = _to_int(params.get("max_retries", 2), default=2, low=1, high=8)
    effective_min_delay = _to_float(params.get("min_delay", 0.35), default=0.35, low=0.2, high=8.0)
    effective_max_delay = _to_float(params.get("max_delay", 0.85), default=0.85, low=0.3, high=12.0)
    if effective_min_delay > effective_max_delay:
        effective_min_delay, effective_max_delay = effective_max_delay, effective_min_delay

    if speed_profile == "max_speed":
        fast_mode = True
        enrich_socials = False
        enrich_facebook_emails = False
        collect_all_emails = False
        website_max_pages = 1
        effective_max_retries = 1
        effective_min_delay = 0.2
        effective_max_delay = 0.45
    elif speed_profile == "email_fast":
        fast_mode = True
        website_max_pages = min(max(1, website_max_pages), 5 if collect_all_emails else 2)
        effective_max_retries = 1
        effective_min_delay = min(effective_min_delay, 0.22)
        effective_max_delay = min(effective_max_delay, 0.5)

    logger.info(
        "Job effective settings | "
        f"id={job_id} mode={mode} speed_profile={speed_profile} fast_mode={fast_mode} "
        f"retries={effective_max_retries} delay={effective_min_delay:.2f}-{effective_max_delay:.2f}s "
        f"max_workers={max_workers} collect_all_emails={collect_all_emails} "
        f"website_max_pages={website_max_pages} enrich_socials={enrich_socials} "
        f"enrich_facebook_emails={enrich_facebook_emails} adaptive_anti_block={adaptive_anti_block}"
    )

    checkpoint_rows: List[Dict[str, Any]] = []
    checkpoint_index: Dict[str, int] = {}
    last_checkpoint_mark = 0
    last_crm_snapshot_mark = 0

    def row_key(row: Dict[str, Any], scope: str = "") -> str:
        place_id = str(row.get("place_id", "")).strip()
        maps_url = str(row.get("google_maps_url", "")).strip()
        feature_id = str(row.get("feature_id", "")).strip()
        name = str(row.get("name", "")).strip().lower()
        address = str(row.get("address", "")).strip().lower()
        core = place_id or maps_url or feature_id or f"{name}|{address}"
        return f"{scope}|{core}"

    def upsert_checkpoint_row(row: Dict[str, Any], scope: str = "") -> None:
        key = row_key(row, scope=scope)
        if key in checkpoint_index:
            checkpoint_rows[checkpoint_index[key]] = dict(row)
        else:
            checkpoint_index[key] = len(checkpoint_rows)
            checkpoint_rows.append(dict(row))

    def save_checkpoint_if_needed(force: bool = False, note: str = "") -> None:
        nonlocal last_checkpoint_mark, last_crm_snapshot_mark
        if not checkpoint_rows:
            return
        if not force and (len(checkpoint_rows) - last_checkpoint_mark) < checkpoint_every:
            return
        checkpoint_file = _write_checkpoint(job_id, checkpoint_rows)
        crm_snapshot_every = max(10, checkpoint_every)
        if force or (len(checkpoint_rows) - last_crm_snapshot_mark) >= crm_snapshot_every:
            maybe_auto_save_crm_job_file(checkpoint_rows)
            last_crm_snapshot_mark = len(checkpoint_rows)
        last_checkpoint_mark = len(checkpoint_rows)
        jobs.update(
            job_id,
            checkpoint_file=checkpoint_file,
            checkpoint_rows=last_checkpoint_mark,
            message=note or f"Checkpoint saved ({last_checkpoint_mark} rows)",
        )

    def dispatch_job_notification(event: str) -> None:
        job_payload = jobs.get(job_id)
        if not job_payload:
            return
        notifications.send_job_notification_async(job_payload, event=event)

    def maybe_auto_import_to_crm(rows: List[Dict[str, Any]]) -> Dict[str, Any] | None:
        if not _to_bool(params.get("auto_crm_import", False), default=False):
            return None
        valid_rows = _successful_result_rows(rows)
        if not valid_rows:
            return None
        try:
            summary = crm.import_rows(
                rows=valid_rows,
                source_job_id=job_id,
                source_job_created_at=str(job.get("created_at", "")),
                merge_existing=False,
            )
            logger.info(
                "Auto CRM import completed | "
                f"job={job_id} imported={summary.get('imported', 0)} "
                f"updated={summary.get('updated', 0)} skipped={summary.get('skipped', 0)}"
            )
            return summary
        except Exception as exc:
            logger.error(f"Auto CRM import failed for job {job_id}: {exc}", exc_info=True)
            return None

    def maybe_auto_save_crm_job_file(rows: List[Dict[str, Any]]) -> Dict[str, Any] | None:
        if not _to_bool(params.get("auto_crm_file_save", True), default=True):
            return None
        valid_rows = _successful_result_rows(rows)
        if not valid_rows:
            return None
        try:
            summary = _write_crm_job_file(
                rows=valid_rows,
                job_id=job_id,
                source_job_created_at=str(job.get("created_at", "")),
            )
            jobs.update(
                job_id,
                crm_file_csv=str(summary.get("csv_file", "")),
                crm_file_json=str(summary.get("json_file", "")),
                crm_file_xlsx=str(summary.get("xlsx_file", "")),
                crm_file_saved_at=str(summary.get("saved_at", "")),
                crm_file_rows=_to_int(summary.get("row_count", 0), default=0, low=0, high=10_000_000),
            )
            logger.info(
                "Auto CRM job file saved | "
                f"job={job_id} rows={summary.get('row_count', 0)} csv={summary.get('csv_file', '')}"
            )
            return summary
        except Exception as exc:
            logger.error(f"Auto CRM job file save failed for job {job_id}: {exc}", exc_info=True)
            return None

    jobs.update(
        job_id,
        status="running",
        started_at=utc_now_iso(),
        progress=0,
        error=None,
        schedule_id=schedule_id,
    )

    try:
        if mode == "resume":
            resume_rows = [dict(r) for r in params.get("resume_rows", [])]
            if not resume_rows:
                raise RuntimeError("Resume file has no rows")

            jobs.update(
                job_id,
                total=len(resume_rows),
                message=f"Resume mode: loaded {len(resume_rows)} rows from checkpoint",
            )

            retry_targets: List[Dict[str, Any]] = []
            target_index: Dict[str, List[int]] = {}

            for idx, row in enumerate(resume_rows):
                resume_key = str(idx)
                row["resume_key"] = resume_key
                maps_url = str(row.get("google_maps_url", "")).strip()
                has_error = str(row.get("error", "")).strip() != ""
                if maps_url and has_error:
                    target = {
                        "google_maps_url": maps_url,
                        "search_keyword": str(row.get("search_keyword", "")),
                        "search_location": str(row.get("search_location", "")),
                        "resume_key": resume_key,
                    }
                    retry_targets.append(target)
                    target_index.setdefault(resume_key, []).append(idx)
                upsert_checkpoint_row(row, scope="resume")

            if retry_targets:
                jobs.update(
                    job_id,
                    progress=0,
                    total=len(retry_targets),
                    message=f"Resume mode: retrying {len(retry_targets)} failed rows",
                )

                def progress_callback(progress: int, total: int, message: str) -> None:
                    jobs.update(job_id, progress=progress, total=total, message=f"Resume: {message}")

                def row_callback(row: Dict[str, str], progress: int, total: int) -> None:
                    key = str(row.get("resume_key", "")).strip()
                    if key and key in target_index and target_index[key]:
                        idx = target_index[key].pop(0)
                        existing = resume_rows[idx]
                        merged = dict(existing)
                        merged.update(row)
                        merged["error"] = str(row.get("error", ""))
                        resume_rows[idx] = merged
                        upsert_checkpoint_row(merged, scope="resume")
                        save_checkpoint_if_needed(note=f"Resume progress {progress}/{total}")

                scrape_place_links(
                    targets=retry_targets,
                    headless=bool(params["headless"]),
                    max_retries=effective_max_retries,
                    min_delay=effective_min_delay,
                    max_delay=effective_max_delay,
                    enrich_socials=enrich_socials,
                    enrich_facebook_emails=enrich_facebook_emails,
                    website_max_pages=website_max_pages,
                    fast_mode=fast_mode,
                    speed_profile=speed_profile,
                    collect_all_emails=collect_all_emails,
                    max_workers=max_workers,
                    adaptive_anti_block=adaptive_anti_block,
                    progress_callback=progress_callback,
                    row_callback=row_callback,
                )

            tracked_rows, dedup_removed = _finalize_rows(
                resume_rows,
                competitor_radius_km=competitor_radius_km,
                dedupe_enabled=dedupe_enabled,
            )
            checkpoint_file = _write_checkpoint(job_id, tracked_rows)
            snapshot_file = _persist_history(tracked_rows, job_id=job_id)

            jobs.update(
                job_id,
                status="completed",
                finished_at=utc_now_iso(),
                message="Resume completed",
                results=tracked_rows,
                progress=len(tracked_rows),
                total=max(len(tracked_rows), len(retry_targets)),
                checkpoint_file=checkpoint_file,
                checkpoint_rows=len(tracked_rows),
                history_snapshot_file=snapshot_file,
                dedup_removed_count=dedup_removed,
            )
            maybe_auto_import_to_crm(tracked_rows)
            maybe_auto_save_crm_job_file(tracked_rows)
            dispatch_job_notification("completed")
            return

        if mode == "bulk":
            queries = list(params.get("queries", []))
            total_queries = len(queries)
            if total_queries == 0:
                raise RuntimeError("Bulk file has no valid rows")

            jobs.update(job_id, total=total_queries, message=f"Starting bulk run: {total_queries} queries")
            discovery_error_rows: List[Dict[str, Any]] = []
            discovered_targets: List[Dict[str, Any]] = []
            discovered_seen_keys: set[str] = set()
            failed_queries = 0
            duplicate_target_count = 0

            for q_idx, query in enumerate(queries, start=1):
                keyword = str(query["keyword"]).strip()
                location = str(query.get("location", "")).strip()
                max_results = int(query.get("max_results", params["default_max_results"]))

                try:
                    jobs.update(
                        job_id,
                        progress=q_idx - 1,
                        total=total_queries,
                        message=f"Discovering unique Maps links for query {q_idx}/{total_queries}: {keyword}",
                    )
                    discovered_rows = scrape_google_maps(
                        keyword=keyword,
                        location=location,
                        max_results=max_results,
                        headless=bool(params["headless"]),
                        max_retries=effective_max_retries,
                        min_delay=effective_min_delay,
                        max_delay=effective_max_delay,
                        enrich_socials=enrich_socials,
                        enrich_facebook_emails=enrich_facebook_emails,
                        website_max_pages=website_max_pages,
                        fast_mode=fast_mode,
                        speed_profile=speed_profile,
                        collect_all_emails=collect_all_emails,
                        max_workers=max_workers,
                        adaptive_anti_block=adaptive_anti_block,
                        links_only=True,
                    )
                    discovered_for_query = 0
                    for target in discovered_rows:
                        target_row = dict(target)
                        target_row["query_index"] = q_idx
                        target_row["query_total"] = total_queries
                        identity_key = _row_identity_key(target_row)
                        if identity_key in discovered_seen_keys:
                            duplicate_target_count += 1
                            continue
                        discovered_seen_keys.add(identity_key)
                        discovered_targets.append(target_row)
                        discovered_for_query += 1
                    jobs.update(
                        job_id,
                        progress=q_idx,
                        total=total_queries,
                        message=(
                            f"Discovered {discovered_for_query} unique Maps links for query {q_idx}/{total_queries} "
                            f"({len(discovered_targets)} unique total)"
                        ),
                    )
                except Exception as query_exc:
                    failed_queries += 1
                    error_row = {
                        "query_index": q_idx,
                        "query_total": total_queries,
                        "search_keyword": keyword,
                        "search_location": location,
                        "error": str(query_exc),
                    }
                    discovery_error_rows.append(error_row)
                    upsert_checkpoint_row(error_row, scope=str(q_idx))
                    save_checkpoint_if_needed(force=True, note=f"Discovery {q_idx}/{total_queries} failed checkpoint")
                    jobs.update(
                        job_id,
                        progress=q_idx,
                        total=total_queries,
                        message=f"Discovery {q_idx}/{total_queries} failed: {query_exc}",
                    )

            if not discovered_targets:
                tracked_rows, dedup_removed = _finalize_rows(
                    discovery_error_rows,
                    competitor_radius_km=competitor_radius_km,
                    dedupe_enabled=dedupe_enabled,
                )
                checkpoint_file = _write_checkpoint(job_id, tracked_rows)
                snapshot_file = _persist_history(tracked_rows, job_id=job_id)
                done_msg = f"Completed bulk discovery with no unique Maps links ({total_queries - failed_queries}/{total_queries} queries succeeded)"
                jobs.update(
                    job_id,
                    status="completed",
                    finished_at=utc_now_iso(),
                    message=done_msg,
                    results=tracked_rows,
                    progress=total_queries,
                    total=total_queries,
                    checkpoint_file=checkpoint_file,
                    checkpoint_rows=len(tracked_rows),
                    history_snapshot_file=snapshot_file,
                    dedup_removed_count=dedup_removed,
                )
                maybe_auto_import_to_crm(tracked_rows)
                maybe_auto_save_crm_job_file(tracked_rows)
                dispatch_job_notification("completed")
                return

            jobs.update(
                job_id,
                progress=0,
                total=len(discovered_targets),
                message=(
                    f"Scraping {len(discovered_targets)} unique Google Maps links "
                    f"(skipped {duplicate_target_count} duplicates before detail scrape)"
                ),
            )

            discovered_target_meta: Dict[str, Dict[str, Any]] = {}
            for target in discovered_targets:
                maps_url = str(target.get("google_maps_url", "")).strip()
                if maps_url and maps_url not in discovered_target_meta:
                    discovered_target_meta[maps_url] = {
                        "query_index": target.get("query_index"),
                        "query_total": target.get("query_total"),
                    }

            def progress_callback(progress: int, total: int, message: str) -> None:
                jobs.update(job_id, progress=progress, total=total, message=message)

            def row_callback(row: Dict[str, str], _progress: int, _total: int) -> None:
                tagged = dict(row)
                meta = discovered_target_meta.get(str(tagged.get("google_maps_url", "")).strip())
                if meta:
                    tagged.update(meta)
                upsert_checkpoint_row(tagged, scope="bulk_unique")
                save_checkpoint_if_needed(note="Bulk unique scrape: checkpoint")

            scraped_rows = scrape_place_links(
                targets=discovered_targets,
                headless=bool(params["headless"]),
                max_retries=effective_max_retries,
                min_delay=effective_min_delay,
                max_delay=effective_max_delay,
                enrich_socials=enrich_socials,
                enrich_facebook_emails=enrich_facebook_emails,
                website_max_pages=website_max_pages,
                fast_mode=fast_mode,
                speed_profile=speed_profile,
                collect_all_emails=collect_all_emails,
                max_workers=max_workers,
                adaptive_anti_block=adaptive_anti_block,
                progress_callback=progress_callback,
                row_callback=row_callback,
            )

            for row in scraped_rows:
                meta = discovered_target_meta.get(str(row.get("google_maps_url", "")).strip())
                if meta:
                    row.update(meta)

            all_rows = [*discovery_error_rows, *scraped_rows]
            tracked_rows, dedup_removed = _finalize_rows(
                all_rows,
                competitor_radius_km=competitor_radius_km,
                dedupe_enabled=dedupe_enabled,
            )
            checkpoint_file = _write_checkpoint(job_id, tracked_rows)
            snapshot_file = _persist_history(tracked_rows, job_id=job_id)
            done_msg = (
                f"Completed bulk run: {len(scraped_rows)} unique place scrapes from {total_queries} queries "
                f"({total_queries - failed_queries}/{total_queries} query discoveries succeeded)"
            )
            jobs.update(
                job_id,
                status="completed",
                finished_at=utc_now_iso(),
                message=done_msg,
                results=tracked_rows,
                progress=total_queries,
                total=total_queries,
                checkpoint_file=checkpoint_file,
                checkpoint_rows=len(tracked_rows),
                history_snapshot_file=snapshot_file,
                dedup_removed_count=dedup_removed,
            )
            maybe_auto_import_to_crm(tracked_rows)
            maybe_auto_save_crm_job_file(tracked_rows)
            dispatch_job_notification("completed")
            return

        jobs.update(
            job_id,
            message="Starting browser session",
            progress=0,
            total=int(params["max_results"]),
        )

        def progress_callback(progress: int, total: int, message: str) -> None:
            jobs.update(job_id, progress=progress, total=total, message=message)

        def row_callback(row: Dict[str, str], _progress: int, _total: int) -> None:
            upsert_checkpoint_row(row, scope="single")
            save_checkpoint_if_needed(note="Single query: checkpoint")

        results = scrape_google_maps(
            keyword=params["keyword"],
            location=params["location"],
            max_results=int(params["max_results"]),
            headless=bool(params["headless"]),
            max_retries=effective_max_retries,
            min_delay=effective_min_delay,
            max_delay=effective_max_delay,
            enrich_socials=enrich_socials,
            enrich_facebook_emails=enrich_facebook_emails,
            website_max_pages=website_max_pages,
            fast_mode=fast_mode,
            speed_profile=speed_profile,
            collect_all_emails=collect_all_emails,
            max_workers=max_workers,
            adaptive_anti_block=adaptive_anti_block,
            progress_callback=progress_callback,
            row_callback=row_callback,
        )
        tracked_rows, dedup_removed = _finalize_rows(
            results,
            competitor_radius_km=competitor_radius_km,
            dedupe_enabled=dedupe_enabled,
        )
        checkpoint_file = _write_checkpoint(job_id, tracked_rows)
        snapshot_file = _persist_history(tracked_rows, job_id=job_id)
        jobs.update(
            job_id,
            status="completed",
            finished_at=utc_now_iso(),
            message="Completed",
            results=tracked_rows,
            progress=len(tracked_rows),
            total=max(int(params["max_results"]), len(tracked_rows)),
            checkpoint_file=checkpoint_file,
            checkpoint_rows=len(tracked_rows),
            history_snapshot_file=snapshot_file,
            dedup_removed_count=dedup_removed,
        )
        maybe_auto_import_to_crm(tracked_rows)
        maybe_auto_save_crm_job_file(tracked_rows)
        dispatch_job_notification("completed")
    except Exception as exc:
        jobs.update(
            job_id,
            status="failed",
            finished_at=utc_now_iso(),
            message="Failed",
            error=f"{exc}\n{traceback.format_exc(limit=1)}",
        )
        dispatch_job_notification("failed")


@app.get("/")
def index():
    # Serve premium UI
    return app.send_static_file("premium-index.html")


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "timestamp_utc": utc_now_iso()})


@app.get("/api/config")
def get_app_config():
    """Return the current application configuration loaded from .env."""
    return jsonify({
        "flask": {
            "debug": os.environ.get("FLASK_DEBUG", "False").lower() == "true",
            "host": os.environ.get("FLASK_HOST", "127.0.0.1"),
            "port": int(os.environ.get("FLASK_PORT", "8000")),
        },
        "file_limits": {
            "max_bulk_file_size_mb": MAX_BULK_FILE_SIZE // (1024 * 1024),
            "max_checkpoint_file_size_mb": MAX_CHECKPOINT_FILE_SIZE // (1024 * 1024),
        },
        "scraper_defaults": {
            "headless": DEFAULT_HEADLESS,
            "max_retries": DEFAULT_MAX_RETRIES,
            "min_delay": DEFAULT_MIN_DELAY,
            "max_delay": DEFAULT_MAX_DELAY,
        },
    })


@app.get("/api/notifications/config")
def get_notifications_config():
    return jsonify({"config": notifications.get_config(include_secrets=False)})


@app.put("/api/notifications/config")
def update_notifications_config():
    data = request.get_json(silent=True) or {}
    try:
        config = notifications.update_config(data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"config": config})


@app.post("/api/notifications/test")
def test_notifications():
    data = request.get_json(silent=True) or {}
    channel = str(data.get("channel", "all")).strip().lower()
    message = str(data.get("message", "")).strip()
    try:
        result = notifications.send_test_notification(channel=channel, message=message)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.error(f"Notification test failed: {exc}", exc_info=True)
        return jsonify({"error": "notification test failed"}), 500
    return jsonify(result)


@app.post("/api/jobs")
def create_job():
    try:
        data = request.get_json(silent=True) or {}
        keyword = str(data.get("keyword", "")).strip()
        manual_query = str(data.get("manual_query", "")).strip()
        manual_query_mode = _to_bool(data.get("manual_query_mode", False), default=False)
        search_input_mode = str(data.get("search_input_mode", "")).strip().lower()
        if manual_query and (manual_query_mode or search_input_mode == "manual" or not keyword):
            keyword = manual_query
        location = str(data.get("location", "")).strip()
        max_results = _to_int(data.get("max_results", 20), default=20, low=1, high=200)
        headless = _to_bool(data.get("headless", DEFAULT_HEADLESS), default=DEFAULT_HEADLESS)
        max_retries = _to_int(data.get("max_retries", DEFAULT_MAX_RETRIES), default=DEFAULT_MAX_RETRIES, low=1, high=8)
        min_delay = _to_float(data.get("min_delay", DEFAULT_MIN_DELAY), default=DEFAULT_MIN_DELAY, low=0.2, high=8.0)
        max_delay = _to_float(data.get("max_delay", DEFAULT_MAX_DELAY), default=DEFAULT_MAX_DELAY, low=0.3, high=12.0)
        competitor_radius_km = _to_float(data.get("competitor_radius_km", 5.0), default=5.0, low=0.0, high=30.0)
        checkpoint_every = _to_int(data.get("checkpoint_every", 10), default=10, low=1, high=1000)
        dedupe_enabled = _to_bool(data.get("dedupe_enabled", True), default=True)
        enrich_socials = _to_bool(data.get("enrich_socials", True), default=True)
        enrich_facebook_emails = _to_bool(data.get("enrich_facebook_emails", True), default=True)
        website_max_pages = _to_int(data.get("website_max_pages", 4), default=4, low=1, high=20)
        fast_mode = _to_bool(data.get("fast_mode", True), default=True)
        max_workers = _to_int(data.get("max_workers", 1), default=1, low=1, high=8)
        collect_all_emails = _to_bool(data.get("collect_all_emails", False), default=False)
        adaptive_anti_block = _to_bool(data.get("adaptive_anti_block", True), default=True)
        auto_crm_import = _to_bool(data.get("auto_crm_import", False), default=False)
        zip_sweep_enabled = _to_bool(data.get("zip_sweep_enabled", False), default=False)
        bulk_keyword_mode = _to_bool(data.get("bulk_keyword_mode", False), default=False)
        zip_sweep_enabled = zip_sweep_enabled or bulk_keyword_mode
        zip_sweep_keywords = str(data.get("zip_sweep_keywords", "")).strip()
        bulk_keywords = str(data.get("bulk_keywords", "")).strip()
        if bulk_keywords and not zip_sweep_keywords:
            zip_sweep_keywords = bulk_keywords
        zip_sweep_max_keywords = _to_int(
            data.get("zip_sweep_max_keywords", 24),
            default=24,
            low=1,
            high=80,
        )
        zip_locations = _normalize_zip_locations(data.get("zip_locations"), max_items=500)
        zip_location_values = [
            _clean_location_phrase(item.get("location") or item.get("zip") or "")
            for item in zip_locations
            if isinstance(item, dict)
        ]
        zip_location_values = [item for item in zip_location_values if item]
        zip_first_location = zip_location_values[0] if zip_location_values else ""
        speed_profile = str(data.get("speed_profile", "balanced")).strip().lower()
        if speed_profile not in {"balanced", "max_speed", "email_fast"}:
            speed_profile = "balanced"
        if min_delay > max_delay:
            min_delay, max_delay = max_delay, min_delay

        if zip_sweep_enabled:
            if (not keyword) and (not zip_sweep_keywords):
                return jsonify({"error": "keyword or zip_sweep_keywords is required for ZIP sweep mode"}), 400

            if zip_locations:
                all_queries: List[Dict[str, Any]] = []
                merged_keywords: List[str] = []
                seen_keywords: set[str] = set()

                for zip_item in zip_locations:
                    zip_location = _clean_location_phrase(zip_item.get("location") or zip_item.get("zip") or "")
                    if not zip_location:
                        continue
                    queries, resolved_keywords = _build_zip_sweep_queries(
                        seed_keyword=keyword,
                        location=zip_location,
                        max_results=max_results,
                        custom_keywords_text=zip_sweep_keywords,
                        max_keywords=zip_sweep_max_keywords,
                    )
                    all_queries.extend(queries)
                    for kw in resolved_keywords:
                        lowered = kw.lower()
                        if lowered in seen_keywords:
                            continue
                        seen_keywords.add(lowered)
                        merged_keywords.append(kw)

                if not all_queries:
                    return jsonify({"error": "ZIP sweep produced no valid keyword queries"}), 400
                if len(all_queries) > 500:
                    return jsonify(
                        {
                            "error": "Selected ZIPs generate too many ZIP sweep queries. Reduce ZIP count or keywords (max 500 queries)."
                        }
                    ), 400

                params = {
                    "mode": "bulk",
                    "keyword": keyword or "ZIP Sweep",
                    "location": location or zip_first_location,
                    "queries": all_queries,
                    "default_max_results": max_results,
                    "headless": headless,
                    "max_retries": max_retries,
                    "min_delay": min_delay,
                    "max_delay": max_delay,
                    "competitor_radius_km": competitor_radius_km,
                    "checkpoint_every": checkpoint_every,
                    "dedupe_enabled": dedupe_enabled,
                    "enrich_socials": enrich_socials,
                    "enrich_facebook_emails": enrich_facebook_emails,
                    "website_max_pages": website_max_pages,
                    "fast_mode": fast_mode,
                    "max_workers": max_workers,
                    "collect_all_emails": collect_all_emails,
                    "adaptive_anti_block": adaptive_anti_block,
                    "auto_crm_import": auto_crm_import,
                    "speed_profile": speed_profile,
                    "search_input_mode": search_input_mode,
                    "manual_query_mode": manual_query_mode,
                    "manual_query": manual_query,
                    "zip_sweep_enabled": True,
                    "zip_sweep_keywords": merged_keywords,
                    "zip_locations": zip_locations,
                }
                job_id = _launch_job(params)
                logger.info(
                    f"ZIP sweep multi-zip job started: {job_id} | ZIPs: {len(zip_locations)} | Queries: {len(all_queries)}"
                )
                return jsonify(
                    {
                        "job_id": job_id,
                        "mode": "zip_sweep_multi_zip",
                        "zip_count": len(zip_locations),
                        "query_count": len(all_queries),
                        "keyword_count": len(merged_keywords),
                    }
                )

            if not location:
                return jsonify({"error": "location/zip is required for ZIP sweep mode"}), 400

            queries, resolved_keywords = _build_zip_sweep_queries(
                seed_keyword=keyword,
                location=location,
                max_results=max_results,
                custom_keywords_text=zip_sweep_keywords,
                max_keywords=zip_sweep_max_keywords,
            )
            if not queries:
                return jsonify({"error": "ZIP sweep produced no valid keyword queries"}), 400
            if len(queries) > 120:
                return jsonify({"error": "ZIP sweep supports at most 120 keyword queries per job"}), 400

            params = {
                "mode": "bulk",
                "keyword": keyword or "ZIP Sweep",
                "location": location,
                "queries": queries,
                "default_max_results": max_results,
                "headless": headless,
                "max_retries": max_retries,
                "min_delay": min_delay,
                "max_delay": max_delay,
                "competitor_radius_km": competitor_radius_km,
                "checkpoint_every": checkpoint_every,
                "dedupe_enabled": dedupe_enabled,
                "enrich_socials": enrich_socials,
                "enrich_facebook_emails": enrich_facebook_emails,
                "website_max_pages": website_max_pages,
                "fast_mode": fast_mode,
                "max_workers": max_workers,
                "collect_all_emails": collect_all_emails,
                "adaptive_anti_block": adaptive_anti_block,
                "auto_crm_import": auto_crm_import,
                "speed_profile": speed_profile,
                "search_input_mode": search_input_mode,
                "manual_query_mode": manual_query_mode,
                "manual_query": manual_query,
                "zip_sweep_enabled": True,
                "zip_sweep_keywords": resolved_keywords,
            }
            job_id = _launch_job(params)
            logger.info(
                f"ZIP sweep job started: {job_id} | Location: {location} | Keywords: {len(resolved_keywords)}"
            )
            return jsonify(
                {
                    "job_id": job_id,
                    "mode": "zip_sweep",
                    "query_count": len(queries),
                    "keyword_count": len(resolved_keywords),
                }
            )

        if zip_locations:
            if not keyword:
                return jsonify({"error": "keyword is required when using ZIP list"}), 400
            if len(keyword) > 200:
                return jsonify({"error": "keyword too long (max 200 characters)"}), 400

            queries = []
            for zip_item in zip_locations:
                zip_location = _clean_location_phrase(zip_item.get("location") or zip_item.get("zip") or "")
                if not zip_location:
                    continue
                queries.append(
                    {
                        "keyword": keyword,
                        "location": zip_location,
                        "max_results": max_results,
                    }
                )
            if not queries:
                return jsonify({"error": "ZIP list has no valid locations"}), 400
            if len(queries) > 500:
                return jsonify({"error": "ZIP list too large. Maximum 500 ZIPs per job."}), 400

            params = {
                "mode": "bulk",
                "keyword": keyword,
                "location": location or zip_first_location,
                "queries": queries,
                "default_max_results": max_results,
                "headless": headless,
                "max_retries": max_retries,
                "min_delay": min_delay,
                "max_delay": max_delay,
                "competitor_radius_km": competitor_radius_km,
                "checkpoint_every": checkpoint_every,
                "dedupe_enabled": dedupe_enabled,
                "enrich_socials": enrich_socials,
                "enrich_facebook_emails": enrich_facebook_emails,
                "website_max_pages": website_max_pages,
                "fast_mode": fast_mode,
                "max_workers": max_workers,
                "collect_all_emails": collect_all_emails,
                "adaptive_anti_block": adaptive_anti_block,
                "auto_crm_import": auto_crm_import,
                "speed_profile": speed_profile,
                "search_input_mode": search_input_mode,
                "manual_query_mode": manual_query_mode,
                "manual_query": manual_query,
                "zip_locations": zip_locations,
            }
            job_id = _launch_job(params)
            logger.info(f"Multi-zip job started: {job_id} | ZIPs: {len(zip_locations)} | Keyword: {keyword}")
            return jsonify(
                {
                    "job_id": job_id,
                    "mode": "multi_zip",
                    "zip_count": len(zip_locations),
                    "query_count": len(queries),
                }
            )

        if not keyword:
            return jsonify({"error": "keyword is required"}), 400
        
        if len(keyword) > 200:
            return jsonify({"error": "keyword too long (max 200 characters)"}), 400

        params = {
            "mode": "single",
            "keyword": keyword,
            "location": location,
            "max_results": max_results,
            "headless": headless,
            "max_retries": max_retries,
            "min_delay": min_delay,
            "max_delay": max_delay,
            "competitor_radius_km": competitor_radius_km,
            "checkpoint_every": checkpoint_every,
            "dedupe_enabled": dedupe_enabled,
            "enrich_socials": enrich_socials,
            "enrich_facebook_emails": enrich_facebook_emails,
            "website_max_pages": website_max_pages,
            "fast_mode": fast_mode,
            "max_workers": max_workers,
            "collect_all_emails": collect_all_emails,
            "adaptive_anti_block": adaptive_anti_block,
            "auto_crm_import": auto_crm_import,
            "speed_profile": speed_profile,
            "search_input_mode": search_input_mode,
            "manual_query_mode": manual_query_mode,
            "manual_query": manual_query,
        }
        job_id = _launch_job(params)
        logger.info(f"Single job started: {job_id} | Keyword: {keyword} | Location: {location}")
        return jsonify({"job_id": job_id})
    except RuntimeError as e:
        logger.error(f"Job creation failed: {e}")
        return jsonify({"error": str(e)}), 429
    except Exception as e:
        logger.error(f"Unexpected error in create_job: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


@app.post("/api/jobs/bulk-upload")
def create_bulk_job():
    try:
        file_storage = request.files.get("file")
        if not file_storage:
            return jsonify({"error": "file is required"}), 400
        
        # Validate file
        valid, msg = validate_file_upload(file_storage, MAX_BULK_FILE_SIZE, "bulk upload")
        if not valid:
            logger.warning(f"Bulk upload validation failed: {msg}")
            return jsonify({"error": msg}), 400

        default_location = str(request.form.get("default_location", "")).strip()
        default_max_results = _to_int(request.form.get("default_max_results", 15), default=15, low=1, high=200)
        headless = _to_bool(request.form.get("headless", "true"), default=True)
        max_retries = _to_int(request.form.get("max_retries", 2), default=2, low=1, high=8)
        min_delay = _to_float(request.form.get("min_delay", 0.35), default=0.35, low=0.2, high=8.0)
        max_delay = _to_float(request.form.get("max_delay", 0.85), default=0.85, low=0.3, high=12.0)
        competitor_radius_km = _to_float(request.form.get("competitor_radius_km", 5.0), default=5.0, low=0.0, high=30.0)
        checkpoint_every = _to_int(request.form.get("checkpoint_every", 10), default=10, low=1, high=1000)
        dedupe_enabled = _to_bool(request.form.get("dedupe_enabled", "true"), default=True)
        enrich_socials = _to_bool(request.form.get("enrich_socials", "true"), default=True)
        enrich_facebook_emails = _to_bool(request.form.get("enrich_facebook_emails", "true"), default=True)
        website_max_pages = _to_int(request.form.get("website_max_pages", 4), default=4, low=1, high=20)
        fast_mode = _to_bool(request.form.get("fast_mode", "true"), default=True)
        max_workers = _to_int(request.form.get("max_workers", 1), default=1, low=1, high=8)
        collect_all_emails = _to_bool(request.form.get("collect_all_emails", "false"), default=False)
        adaptive_anti_block = _to_bool(request.form.get("adaptive_anti_block", "true"), default=True)
        auto_crm_import = _to_bool(request.form.get("auto_crm_import", "false"), default=False)
        speed_profile = str(request.form.get("speed_profile", "balanced")).strip().lower()
        if speed_profile not in {"balanced", "max_speed", "email_fast"}:
            speed_profile = "balanced"
        if min_delay > max_delay:
            min_delay, max_delay = max_delay, min_delay

        queries = _read_bulk_queries_from_upload(
            file_storage=file_storage,
            default_location=default_location,
            default_max_results=default_max_results,
        )
        
        if not queries:
            return jsonify({"error": "No valid rows found in file"}), 400
        if len(queries) > 500:
            return jsonify({"error": "Bulk file is too large. Maximum 500 rows per job."}), 400

        params = {
            "mode": "bulk",
            "queries": queries,
            "default_max_results": default_max_results,
            "headless": headless,
            "max_retries": max_retries,
            "min_delay": min_delay,
            "max_delay": max_delay,
            "competitor_radius_km": competitor_radius_km,
            "checkpoint_every": checkpoint_every,
            "dedupe_enabled": dedupe_enabled,
            "enrich_socials": enrich_socials,
            "enrich_facebook_emails": enrich_facebook_emails,
            "website_max_pages": website_max_pages,
            "fast_mode": fast_mode,
            "max_workers": max_workers,
            "collect_all_emails": collect_all_emails,
            "adaptive_anti_block": adaptive_anti_block,
            "auto_crm_import": auto_crm_import,
            "speed_profile": speed_profile,
        }
        job_id = _launch_job(params)
        logger.info(f"Bulk job started: {job_id} | Queries: {len(queries)}")
        return jsonify({"job_id": job_id, "query_count": len(queries)})
    except RuntimeError as e:
        logger.error(f"Bulk job creation failed: {e}")
        return jsonify({"error": str(e)}), 429
    except Exception as e:
        logger.error(f"Bulk upload error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 400


@app.post("/api/jobs/resume-upload")
def create_resume_job():
    try:
        file_storage = request.files.get("file")
        if not file_storage:
            return jsonify({"error": "checkpoint file is required"}), 400
        
        # Validate file
        valid, msg = validate_file_upload(file_storage, MAX_CHECKPOINT_FILE_SIZE, "checkpoint")
        if not valid:
            logger.warning(f"Resume upload validation failed: {msg}")
            return jsonify({"error": msg}), 400

        headless = _to_bool(request.form.get("headless", "true"), default=True)
        max_retries = _to_int(request.form.get("max_retries", 2), default=2, low=1, high=8)
        min_delay = _to_float(request.form.get("min_delay", 0.35), default=0.35, low=0.2, high=8.0)
        max_delay = _to_float(request.form.get("max_delay", 0.85), default=0.85, low=0.3, high=12.0)
        competitor_radius_km = _to_float(request.form.get("competitor_radius_km", 5.0), default=5.0, low=0.0, high=30.0)
        checkpoint_every = _to_int(request.form.get("checkpoint_every", 10), default=10, low=1, high=1000)
        dedupe_enabled = _to_bool(request.form.get("dedupe_enabled", "true"), default=True)
        enrich_socials = _to_bool(request.form.get("enrich_socials", "true"), default=True)
        enrich_facebook_emails = _to_bool(request.form.get("enrich_facebook_emails", "true"), default=True)
        website_max_pages = _to_int(request.form.get("website_max_pages", 4), default=4, low=1, high=20)
        fast_mode = _to_bool(request.form.get("fast_mode", "true"), default=True)
        max_workers = _to_int(request.form.get("max_workers", 1), default=1, low=1, high=8)
        collect_all_emails = _to_bool(request.form.get("collect_all_emails", "false"), default=False)
        adaptive_anti_block = _to_bool(request.form.get("adaptive_anti_block", "true"), default=True)
        auto_crm_import = _to_bool(request.form.get("auto_crm_import", "false"), default=False)
        speed_profile = str(request.form.get("speed_profile", "balanced")).strip().lower()
        if speed_profile not in {"balanced", "max_speed", "email_fast"}:
            speed_profile = "balanced"
        if min_delay > max_delay:
            min_delay, max_delay = max_delay, min_delay

        rows = _read_rows_from_upload(file_storage, purpose="resume")
        
        if not rows:
            return jsonify({"error": "Resume file has no rows"}), 400
        if len(rows) > 5000:
            return jsonify({"error": "Resume file too large. Maximum 5000 rows."}), 400

        params = {
            "mode": "resume",
            "resume_rows": rows,
            "headless": headless,
            "max_retries": max_retries,
            "min_delay": min_delay,
            "max_delay": max_delay,
            "competitor_radius_km": competitor_radius_km,
            "checkpoint_every": checkpoint_every,
            "dedupe_enabled": dedupe_enabled,
            "enrich_socials": enrich_socials,
            "enrich_facebook_emails": enrich_facebook_emails,
            "website_max_pages": website_max_pages,
            "fast_mode": fast_mode,
            "max_workers": max_workers,
            "collect_all_emails": collect_all_emails,
            "adaptive_anti_block": adaptive_anti_block,
            "auto_crm_import": auto_crm_import,
            "speed_profile": speed_profile,
        }
        job_id = _launch_job(params)
        logger.info(f"Resume job started: {job_id} | Rows: {len(rows)}")
        return jsonify({"job_id": job_id, "resume_row_count": len(rows)})
    except RuntimeError as e:
        logger.error(f"Resume job creation failed: {e}")
        return jsonify({"error": str(e)}), 429
    except Exception as e:
        logger.error(f"Resume upload error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 400


@app.get("/api/jobs/<job_id>")
def get_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    return jsonify(jobs.to_api_payload(job))


@app.get("/api/jobs/<job_id>/results")
def get_results(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    all_rows = job.get("results", []) if isinstance(job.get("results"), list) else []
    success_rows = _successful_result_rows(all_rows)
    failed_rows = _failed_result_rows(all_rows)
    return jsonify(
        {
            "job_id": job_id,
            "results": success_rows,
            "result_count": len(success_rows),
            "error_count": len(failed_rows),
        }
    )


@app.get("/api/jobs/<job_id>/checkpoint.csv")
def download_checkpoint(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    checkpoint_file = str(job.get("checkpoint_file", "")).strip()
    if not checkpoint_file or not Path(checkpoint_file).exists():
        return jsonify({"error": "checkpoint file not available"}), 404

    return send_file(
        checkpoint_file,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"checkpoint_{job_id}.csv",
    )


@app.get("/api/jobs/<job_id>/clusters")
def get_cluster_summary(job_id: str):
    rows = jobs.results(job_id)
    if rows is None:
        return jsonify({"error": "job not found"}), 404
    summary = _build_cluster_summary(_successful_result_rows(rows))
    return jsonify({"job_id": job_id, "clusters": summary})


@app.get("/api/jobs/<job_id>/export.outreach.csv")
def export_outreach(job_id: str):
    rows = jobs.results(job_id)
    if rows is None:
        return jsonify({"error": "job not found"}), 404
    leads = _build_outreach_rows(_successful_result_rows(rows))
    if not leads:
        return jsonify({"error": "no outreach leads available"}), 400

    df = pd.DataFrame(leads)
    buf = io.StringIO()
    df.to_csv(buf, index=False, encoding="utf-8-sig")
    mem = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
    mem.seek(0)
    return send_file(
        mem,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"outreach_{job_id}.csv",
    )


@app.get("/api/jobs/<job_id>/export.crm.csv")
def export_crm(job_id: str):
    provider = str(request.args.get("provider", "salesforce")).strip().lower()
    if provider not in {"hubspot", "zoho", "salesforce"}:
        return jsonify({"error": "provider must be hubspot, zoho, or salesforce"}), 400

    rows = jobs.results(job_id)
    if rows is None:
        return jsonify({"error": "job not found"}), 404
    mapped = _build_crm_rows(_successful_result_rows(rows), provider=provider)
    if not mapped:
        return jsonify({"error": "no crm rows available"}), 400

    df = pd.DataFrame(mapped)
    buf = io.StringIO()
    df.to_csv(buf, index=False, encoding="utf-8-sig")
    mem = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
    mem.seek(0)
    return send_file(
        mem,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"{provider}_crm_{job_id}.csv",
    )


@app.get("/api/crm/statuses")
def get_crm_statuses():
    return jsonify({"statuses": CRM_ALLOWED_STATUSES})


@app.get("/api/crm/leads")
def list_crm_leads():
    status = str(request.args.get("status", "")).strip().lower()
    query = str(request.args.get("q", "")).strip()
    owner = str(request.args.get("owner", "")).strip()
    category = str(request.args.get("category", "")).strip()
    state = str(request.args.get("state", "")).strip()
    city = str(request.args.get("city", "")).strip()
    zip_code = str(request.args.get("zip", request.args.get("zip_code", ""))).strip()
    source_job_id = str(request.args.get("source_job_id", "")).strip()
    limit = _to_int(request.args.get("limit", 500), default=500, low=1, high=5000)
    leads = crm.list_leads(
        status=status,
        query=query,
        owner=owner,
        category=category,
        state=state,
        city=city,
        zip_code=zip_code,
        source_job_id=source_job_id,
        limit=limit,
    )
    return jsonify(
        {
            "leads": leads,
            "count": len(leads),
            "stats": crm.get_stats_for_rows(leads),
            "overall_stats": crm.get_stats(),
            "filter_options": crm.get_filter_options(limit=5000),
            "applied_filters": {
                "status": status or "all",
                "q": query,
                "owner": owner,
                "category": category or "all",
                "state": state or "all",
                "city": city or "all",
                "zip": zip_code or "all",
                "source_job_id": source_job_id,
            },
        }
    )


@app.get("/api/crm/segments")
def get_crm_segments():
    group_by = str(request.args.get("group_by", "category")).strip().lower()
    limit = _to_int(request.args.get("limit", 200), default=200, low=1, high=5000)
    try:
        items = crm.segment_counts(group_by=group_by, limit=limit)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"group_by": group_by, "items": items})


@app.post("/api/crm/leads")
def create_crm_lead():
    data = request.get_json(silent=True) or {}
    try:
        lead, created = crm.create_or_merge(data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"lead": lead, "created": created}), (201 if created else 200)


@app.patch("/api/crm/leads/<lead_id>")
def update_crm_lead(lead_id: str):
    data = request.get_json(silent=True) or {}
    lead = crm.update_lead(lead_id, data)
    if not lead:
        return jsonify({"error": "lead not found"}), 404
    return jsonify({"lead": lead})


@app.delete("/api/crm/leads/<lead_id>")
def delete_crm_lead(lead_id: str):
    deleted = crm.delete_lead(lead_id)
    if not deleted:
        return jsonify({"error": "lead not found"}), 404
    return jsonify({"deleted": True, "lead_id": lead_id})


@app.post("/api/crm/import-job/<job_id>")
def import_job_to_crm(job_id: str):
    rows = jobs.results(job_id)
    if rows is None:
        return jsonify({"error": "job not found"}), 404
    valid_rows = _successful_result_rows(rows)
    if not valid_rows:
        return jsonify({"error": "job has no valid results to import"}), 400

    merge_existing = _to_bool(request.args.get("merge_existing", "false"), default=False)
    job = jobs.get(job_id) or {}
    source_job_created_at = str(job.get("created_at", "")).strip()
    summary = crm.import_rows(
        rows=valid_rows,
        source_job_id=job_id,
        source_job_created_at=source_job_created_at,
        merge_existing=merge_existing,
    )
    return jsonify(summary)


@app.delete("/api/crm/import-job/<job_id>")
def delete_job_from_crm(job_id: str):
    summary = crm.delete_by_job_id(job_id)
    if int(summary.get("deleted", 0)) == 0:
        return jsonify({"error": "no crm leads found for this job", **summary}), 404
    return jsonify(summary)


@app.get("/api/crm/export.csv")
def export_crm_leads_csv():
    leads = crm.list_leads(limit=50000)
    if not leads:
        return jsonify({"error": "no crm leads available"}), 400
    df = pd.DataFrame(leads)
    buf = io.StringIO()
    df.to_csv(buf, index=False, encoding="utf-8-sig")
    mem = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
    mem.seek(0)
    return send_file(
        mem,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"mini_crm_export_{int(datetime.now().timestamp())}.csv",
    )


@app.get("/api/crm/job-files")
def list_crm_job_files():
    limit = _to_int(request.args.get("limit", 500), default=500, low=1, high=5000)
    items = _list_crm_job_files(limit=limit)
    return jsonify({"files": items, "count": len(items)})


@app.get("/api/crm/job-files/export.xlsx")
def export_crm_job_files_xlsx():
    job_ids_raw = str(request.args.get("job_ids", "")).strip()
    job_ids: List[str] = []
    if job_ids_raw:
        job_ids = [jid.strip() for jid in job_ids_raw.split(",") if jid.strip()]
    metas = []
    if job_ids:
        for jid in job_ids:
            meta = _read_crm_job_file_meta(jid)
            if meta:
                metas.append(meta)
    else:
        metas = _list_crm_job_files(limit=5000)

    if not metas:
        return jsonify({"error": "no crm job files available"}), 400

    mem = io.BytesIO()
    used_names: set[str] = set()
    sheet_count = 0
    with pd.ExcelWriter(mem, engine="openpyxl") as writer:
        for meta in metas:
            job_id = str(meta.get("job_id", "")).strip()
            if not job_id:
                continue
            df = _load_crm_job_dataframe(job_id)
            if df is None:
                continue
            sheet_name = _safe_sheet_name(_crm_job_sheet_title(job_id), used_names)
            df.to_excel(writer, index=False, sheet_name=sheet_name)
            sheet_count += 1

    if sheet_count == 0:
        return jsonify({"error": "no crm job data found to export"}), 400

    mem.seek(0)
    timestamp = int(datetime.now().timestamp())
    return send_file(
        mem,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"crm_job_sheets_{timestamp}.xlsx",
    )


@app.get("/api/crm/job-file/<job_id>")
def download_crm_job_file(job_id: str):
    fmt = str(request.args.get("format", "csv")).strip().lower()
    if fmt not in {"csv", "json", "xlsx"}:
        return jsonify({"error": "format must be csv, json, or xlsx"}), 400

    csv_path, json_path = _crm_job_file_paths(job_id)
    xlsx_path = _crm_job_file_xlsx_path(job_id)
    if fmt == "xlsx":
        if xlsx_path.exists():
            return send_file(
                xlsx_path,
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                as_attachment=True,
                download_name=f"crm_job_{_crm_job_file_key(job_id)}.xlsx",
            )
        df = _load_crm_job_dataframe(job_id)
        if df is None:
            return jsonify({"error": "crm job file not found", "job_id": job_id, "format": fmt}), 404
        mem = io.BytesIO()
        with pd.ExcelWriter(mem, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="leads")
        mem.seek(0)
        return send_file(
            mem,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"crm_job_{_crm_job_file_key(job_id)}.xlsx",
        )

    target = csv_path if fmt == "csv" else json_path
    if not target.exists():
        return jsonify({"error": "crm job file not found", "job_id": job_id, "format": fmt}), 404

    mimetype = "text/csv" if fmt == "csv" else "application/json"
    return send_file(
        target,
        mimetype=mimetype,
        as_attachment=True,
        download_name=f"crm_job_{_crm_job_file_key(job_id)}.{fmt}",
    )


@app.get("/api/crm/job-file/<job_id>/meta")
def crm_job_file_meta(job_id: str):
    meta = _read_crm_job_file_meta(job_id)
    if not meta:
        return jsonify({"error": "crm job file not found", "job_id": job_id}), 404
    return jsonify(meta)


@app.delete("/api/crm/job-file/<job_id>")
def delete_crm_job_file(job_id: str):
    csv_path, json_path, xlsx_path = _crm_job_file_paths_all(job_id)
    deleted = 0
    for path in (csv_path, json_path, xlsx_path):
        if path.exists():
            try:
                path.unlink()
                deleted += 1
            except Exception:
                pass

    if deleted == 0:
        return jsonify({"error": "crm job file not found", "job_id": job_id}), 404

    # Keep job metadata consistent if file was deleted manually.
    jobs.update(
        job_id,
        crm_file_csv="",
        crm_file_json="",
        crm_file_xlsx="",
        crm_file_saved_at="",
        crm_file_rows=0,
    )
    return jsonify({"deleted": True, "job_id": job_id, "deleted_files": deleted})


@app.post("/api/jobs/query-preview")
def query_preview():
    data = request.get_json(silent=True) or {}
    try:
        preview = _build_query_preview_from_payload(data, max_preview=_to_int(data.get("preview_limit", 250), default=250, low=10, high=1000))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.error(f"Query preview failed: {exc}", exc_info=True)
        return jsonify({"error": "failed to build query preview"}), 500
    return jsonify(preview)


@app.get("/api/presets")
def list_presets():
    limit = _to_int(request.args.get("limit", 200), default=200, low=1, high=2000)
    items = presets.list(limit=limit)
    return jsonify({"presets": items, "count": len(items)})


@app.post("/api/presets")
def save_preset():
    data = request.get_json(silent=True) or {}
    name = _store_clean_name(data.get("name"), max_len=96)
    description = _store_clean_name(data.get("description"), max_len=240)
    preset_id = str(data.get("preset_id", "")).strip()
    config = data.get("config")
    try:
        item = presets.save(name=name, config=config if isinstance(config, dict) else {}, description=description, preset_id=preset_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(item)


@app.get("/api/presets/<preset_id>")
def get_preset(preset_id: str):
    item = presets.get(preset_id)
    if not item:
        return jsonify({"error": "preset not found"}), 404
    return jsonify(item)


@app.post("/api/presets/<preset_id>/use")
def mark_preset_used(preset_id: str):
    item = presets.mark_used(preset_id)
    if not item:
        return jsonify({"error": "preset not found"}), 404
    return jsonify(item)


@app.delete("/api/presets/<preset_id>")
def delete_preset(preset_id: str):
    ok = presets.delete(preset_id)
    if not ok:
        return jsonify({"error": "preset not found"}), 404
    return jsonify({"ok": True})


@app.get("/api/zip-packs")
def list_zip_packs():
    limit = _to_int(request.args.get("limit", 200), default=200, low=1, high=2000)
    items = zip_packs.list(limit=limit)
    return jsonify({"packs": items, "count": len(items)})


@app.post("/api/zip-packs")
def save_zip_pack():
    data = request.get_json(silent=True) or {}
    name = _store_clean_name(data.get("name"), max_len=96)
    description = _store_clean_name(data.get("description"), max_len=240)
    pack_id = str(data.get("pack_id", "")).strip()
    zip_locations = _normalize_zip_locations(data.get("zip_locations"), max_items=5000)
    try:
        item = zip_packs.save(
            name=name,
            description=description,
            pack_id=pack_id,
            zip_locations=zip_locations,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(item)


@app.get("/api/zip-packs/<pack_id>")
def get_zip_pack(pack_id: str):
    item = zip_packs.get(pack_id)
    if not item:
        return jsonify({"error": "zip pack not found"}), 404
    return jsonify(item)


@app.delete("/api/zip-packs/<pack_id>")
def delete_zip_pack(pack_id: str):
    ok = zip_packs.delete(pack_id)
    if not ok:
        return jsonify({"error": "zip pack not found"}), 404
    return jsonify({"ok": True})


@app.post("/api/zip-packs/import.csv")
def import_zip_pack_csv():
    file_storage = request.files.get("file")
    if not file_storage:
        return jsonify({"error": "CSV file is required"}), 400
    filename = str(file_storage.filename or "").strip()
    if not filename.lower().endswith(".csv"):
        return jsonify({"error": "only .csv files are supported"}), 400

    raw_name = str(request.form.get("name", "")).strip()
    try:
        df = pd.read_csv(file_storage)
    except Exception as exc:
        return jsonify({"error": f"failed to read CSV: {exc}"}), 400
    if df.empty:
        return jsonify({"error": "CSV has no rows"}), 400

    zip_col = _pick_column(df, ["zip", "zipcode", "zip_code", "postal_code", "postal", "code"])
    location_col = _pick_column(df, ["location", "label", "area", "city", "place"])
    if not zip_col and not location_col:
        return jsonify({"error": "CSV must include zip/postal or location column"}), 400

    rows: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        entry = {
            "zip": "" if not zip_col else ("" if pd.isna(row.get(zip_col)) else row.get(zip_col)),
            "location": "" if not location_col else ("" if pd.isna(row.get(location_col)) else row.get(location_col)),
        }
        rows.append(entry)

    zip_locations = _normalize_zip_locations(rows, max_items=5000)
    if not zip_locations:
        return jsonify({"error": "CSV has no valid ZIP entries"}), 400

    suggested_name = raw_name
    if not suggested_name:
        suggested_name = Path(filename).stem or "Imported ZIP Pack"

    try:
        item = zip_packs.save(
            name=suggested_name,
            description="Imported from CSV",
            zip_locations=zip_locations,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(item)


@app.get("/api/zip-packs/<pack_id>/export.csv")
def export_zip_pack_csv(pack_id: str):
    item = zip_packs.get(pack_id)
    if not item:
        return jsonify({"error": "zip pack not found"}), 404
    rows = item.get("zip_locations") or []
    if not isinstance(rows, list) or not rows:
        return jsonify({"error": "zip pack has no rows"}), 400
    df = pd.DataFrame(rows)
    buf = io.StringIO()
    df.to_csv(buf, index=False, encoding="utf-8-sig")
    mem = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
    mem.seek(0)
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", str(item.get("name", "zip_pack")).strip())[:80]
    if not safe_name:
        safe_name = "zip_pack"
    return send_file(
        mem,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"{safe_name}.csv",
    )


@app.get("/api/locations/countries")
def list_location_countries():
    return jsonify({"countries": SUPPORTED_LOCATION_COUNTRIES, "count": len(SUPPORTED_LOCATION_COUNTRIES)})


@app.get("/api/locations/states")
def list_location_states():
    country = str(request.args.get("country", "US")).strip().upper() or "US"
    if country not in SUPPORTED_LOCATION_COUNTRY_CODES:
        return jsonify({"error": f"unsupported country: {country}"}), 400
    try:
        states = locations.list_states(country_code=country)
    except RuntimeError as exc:
        logger.error(f"Failed to list states for {country}: {exc}")
        return jsonify({"error": str(exc)}), 503
    return jsonify({"country": country, "states": states, "count": len(states)})


@app.get("/api/locations/cities")
def list_location_cities():
    country = str(request.args.get("country", "US")).strip().upper() or "US"
    if country not in SUPPORTED_LOCATION_COUNTRY_CODES:
        return jsonify({"error": f"unsupported country: {country}"}), 400
    state_code = str(request.args.get("state", "")).strip().upper()
    if not state_code:
        return jsonify({"error": "state query param is required"}), 400
    query = str(request.args.get("q", "")).strip()
    limit = _to_int(request.args.get("limit", 5000), default=5000, low=1, high=50000)
    try:
        cities = locations.list_cities(country_code=country, state_code=state_code, query=query, limit=limit)
    except RuntimeError as exc:
        logger.error(f"Failed to list cities for {country}/{state_code}: {exc}")
        return jsonify({"error": str(exc)}), 503
    return jsonify(
        {
            "country": country,
            "state": state_code,
            "state_name": locations.state_name(country, state_code),
            "cities": cities,
            "count": len(cities),
        }
    )


@app.get("/api/locations/zips")
def list_location_zips():
    country = str(request.args.get("country", "US")).strip().upper() or "US"
    if country not in SUPPORTED_LOCATION_COUNTRY_CODES:
        return jsonify({"error": f"unsupported country: {country}"}), 400
    state_code = str(request.args.get("state", "")).strip().upper()
    if not state_code:
        return jsonify({"error": "state query param is required"}), 400
    city = str(request.args.get("city", "")).strip()
    query = str(request.args.get("q", "")).strip()
    limit = _to_int(request.args.get("limit", 5000), default=5000, low=1, high=50000)
    try:
        zips = locations.list_zips(
            country_code=country,
            state_code=state_code,
            city=city,
            query=query,
            limit=limit,
        )
    except RuntimeError as exc:
        logger.error(f"Failed to list zips for {country}/{state_code}/{city}: {exc}")
        return jsonify({"error": str(exc)}), 503
    return jsonify(
        {
            "country": country,
            "state": state_code,
            "state_name": locations.state_name(country, state_code),
            "city": city,
            "zips": zips,
            "count": len(zips),
        }
    )


@app.get("/api/locations/area-zips")
def list_location_area_zips():
    country = str(request.args.get("country", "US")).strip().upper() or "US"
    if country not in SUPPORTED_LOCATION_COUNTRY_CODES:
        return jsonify({"error": f"unsupported country: {country}"}), 400
    state_code = str(request.args.get("state", "")).strip().upper()
    if not state_code:
        return jsonify({"error": "state query param is required"}), 400
    area = str(request.args.get("area", "")).strip()
    if not area:
        return jsonify({"error": "area query param is required"}), 400
    limit = _to_int(request.args.get("limit", 5000), default=5000, low=1, high=50000)
    try:
        zips, matched_cities = locations.list_area_zips(
            country_code=country,
            state_code=state_code,
            area_query=area,
            limit=limit,
        )
    except RuntimeError as exc:
        logger.error(f"Failed to list area zips for {country}/{state_code}/{area}: {exc}")
        return jsonify({"error": str(exc)}), 503
    return jsonify(
        {
            "country": country,
            "state": state_code,
            "state_name": locations.state_name(country, state_code),
            "area": area,
            "matched_cities": matched_cities[:200],
            "matched_city_count": len(matched_cities),
            "zips": zips,
            "count": len(zips),
        }
    )


@app.get("/api/schedules")
def list_schedules():
    with SCHEDULES_LOCK:
        items = []
        for sid, sched in SCHEDULES.items():
            row = {k: v for k, v in sched.items() if k not in {"stop_event", "thread"}}
            row["schedule_id"] = sid
            items.append(row)
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return jsonify({"schedules": items})


@app.post("/api/schedules")
def create_schedule():
    data = request.get_json(silent=True) or {}
    keyword = str(data.get("keyword", "")).strip()
    if not keyword:
        return jsonify({"error": "keyword is required"}), 400

    interval_minutes = _to_int(data.get("interval_minutes", 60), default=60, low=5, high=10080)
    params = {
        "mode": "single",
        "keyword": keyword,
        "location": str(data.get("location", "")).strip(),
        "max_results": _to_int(data.get("max_results", 20), default=20, low=1, high=200),
        "headless": _to_bool(data.get("headless", True), default=True),
        "max_retries": _to_int(data.get("max_retries", 2), default=2, low=1, high=8),
        "min_delay": _to_float(data.get("min_delay", 0.35), default=0.35, low=0.2, high=8.0),
        "max_delay": _to_float(data.get("max_delay", 0.85), default=0.85, low=0.3, high=12.0),
        "competitor_radius_km": _to_float(data.get("competitor_radius_km", 5.0), default=5.0, low=0.0, high=30.0),
        "checkpoint_every": _to_int(data.get("checkpoint_every", 10), default=10, low=1, high=1000),
        "dedupe_enabled": _to_bool(data.get("dedupe_enabled", True), default=True),
        "enrich_socials": _to_bool(data.get("enrich_socials", True), default=True),
        "enrich_facebook_emails": _to_bool(data.get("enrich_facebook_emails", True), default=True),
        "website_max_pages": _to_int(data.get("website_max_pages", 4), default=4, low=1, high=20),
        "fast_mode": _to_bool(data.get("fast_mode", True), default=True),
        "adaptive_anti_block": _to_bool(data.get("adaptive_anti_block", True), default=True),
        "auto_crm_import": _to_bool(data.get("auto_crm_import", False), default=False),
        "speed_profile": str(data.get("speed_profile", "balanced")).strip().lower(),
    }
    if params["speed_profile"] not in {"balanced", "max_speed", "email_fast"}:
        params["speed_profile"] = "balanced"

    sid = str(uuid.uuid4())
    stop_event = threading.Event()
    thread = threading.Thread(target=_run_schedule_loop, args=(sid,), daemon=True)

    with SCHEDULES_LOCK:
        SCHEDULES[sid] = {
            "name": str(data.get("name", f"Schedule {keyword}")).strip(),
            "status": "active",
            "interval_minutes": interval_minutes,
            "job_params": params,
            "created_at": utc_now_iso(),
            "last_run_at": "",
            "last_job_id": "",
            "run_count": 0,
            "last_error": "",
            "stop_event": stop_event,
            "thread": thread,
        }

    run_now = _to_bool(data.get("run_now", True), default=True)
    if run_now:
        try:
            job_id = _launch_job(params, schedule_id=sid)
            with SCHEDULES_LOCK:
                cur = SCHEDULES.get(sid)
                if cur:
                    cur["last_job_id"] = job_id
                    cur["last_run_at"] = utc_now_iso()
                    cur["run_count"] = 1
        except Exception as exc:
            with SCHEDULES_LOCK:
                cur = SCHEDULES.get(sid)
                if cur:
                    cur["last_error"] = str(exc)

    thread.start()
    return jsonify({"schedule_id": sid})


@app.post("/api/schedules/<schedule_id>/run-now")
def run_schedule_now(schedule_id: str):
    with SCHEDULES_LOCK:
        sched = SCHEDULES.get(schedule_id)
        if not sched:
            return jsonify({"error": "schedule not found"}), 404
        params = dict(sched["job_params"])

    job_id = _launch_job(params, schedule_id=schedule_id)
    with SCHEDULES_LOCK:
        cur = SCHEDULES.get(schedule_id)
        if cur:
            cur["last_job_id"] = job_id
            cur["last_run_at"] = utc_now_iso()
            cur["run_count"] = int(cur.get("run_count", 0)) + 1
    return jsonify({"job_id": job_id, "schedule_id": schedule_id})


@app.delete("/api/schedules/<schedule_id>")
def delete_schedule(schedule_id: str):
    with SCHEDULES_LOCK:
        sched = SCHEDULES.get(schedule_id)
        if not sched:
            return jsonify({"error": "schedule not found"}), 404
        sched["status"] = "stopped"
        stop_event: threading.Event = sched["stop_event"]
        stop_event.set()
        SCHEDULES.pop(schedule_id, None)
    return jsonify({"deleted": True, "schedule_id": schedule_id})


@app.get("/api/jobs/<job_id>/export.csv")
def export_csv(job_id: str):
    rows = jobs.results(job_id)
    if rows is None:
        return jsonify({"error": "job not found"}), 404
    valid_rows = _successful_result_rows(rows)
    if not valid_rows:
        return jsonify({"error": "no valid results available"}), 400

    df = pd.DataFrame(valid_rows)
    buf = io.StringIO()
    df.to_csv(buf, index=False, encoding="utf-8-sig")
    mem = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
    mem.seek(0)

    return send_file(
        mem,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"gmaps_results_{job_id}.csv",
    )


@app.get("/api/jobs/<job_id>/export.xlsx")
def export_xlsx(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404

    saved_xlsx_value = str(job.get("crm_file_xlsx", "")).strip()
    if saved_xlsx_value:
        saved_xlsx = Path(saved_xlsx_value)
    else:
        saved_xlsx = None
    if saved_xlsx and saved_xlsx.exists():
        return send_file(
            saved_xlsx,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"gmaps_results_{job_id}.xlsx",
        )

    rows = jobs.results(job_id)
    if rows is None:
        return jsonify({"error": "job not found"}), 404
    valid_rows = _successful_result_rows(rows)
    if not valid_rows:
        return jsonify({"error": "no valid results available"}), 400

    df = pd.DataFrame(valid_rows)
    mem = io.BytesIO()
    with pd.ExcelWriter(mem, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="results")
    mem.seek(0)

    return send_file(
        mem,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"gmaps_results_{job_id}.xlsx",
    )


@app.get("/api/history")
def get_job_history():
    return jsonify({"history": jobs.list_all()})

@app.delete("/api/history/<job_id>")
def delete_job_history(job_id: str):
    success = jobs.delete(job_id)
    if not success:
        return jsonify({"error": "Job not found"}), 404
    # Cleanup auto-saved CRM job file snapshots for this job id.
    for path in _crm_job_file_paths_all(job_id):
        if path.exists():
            try:
                path.unlink()
            except Exception:
                pass
    return jsonify({"deleted": True})

@app.get("/api/export/all")
def export_all_data():
    all_jobs = jobs.list_all()
    all_rows = []
    
    for meta in all_jobs:
        results = jobs.results(meta["job_id"])
        if results:
            for row in _successful_result_rows(results):
                # Enrich with source job info if needed
                enriched_row = dict(row)
                enriched_row["_source_job_date"] = meta["created_at"]
                all_rows.append(enriched_row)
    
    if not all_rows:
        return jsonify({"error": "No data available to export"}), 400

    df = pd.DataFrame(all_rows)
    mem = io.BytesIO()
    with pd.ExcelWriter(mem, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="All Leads")
    mem.seek(0)

    return send_file(
        mem,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"titanflow_bulk_export_{int(datetime.now().timestamp())}.xlsx",
    )

if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    flask_host = os.environ.get("FLASK_HOST", "127.0.0.1")
    flask_port = int(os.environ.get("FLASK_PORT", "8000"))
    app.run(host=flask_host, port=flask_port, debug=debug_mode)
