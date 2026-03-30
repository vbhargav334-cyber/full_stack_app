import base64
import binascii
import sys
import asyncio
import html as html_lib
import json
import logging
import math
import queue
import random
import re
import ssl
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs, parse_qsl, quote_plus, unquote, urlencode, urljoin, urlparse, urlunparse

# Configure stdout to handle UTF-8 (Fixes Windows Console UnicodeEncodeError)
try:
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

try:
    import usaddress
    USADDRESS_AVAILABLE = True
except ImportError:
    USADDRESS_AVAILABLE = False

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

# Configure logging
logger = logging.getLogger(__name__)


ProgressCallback = Callable[[int, int, str], None]
RowCallback = Callable[[Dict[str, str], int, int], None]


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

DEFAULT_COUNTRY_GEO: Dict[str, tuple[float, float]] = {
    "US": (39.8283, -98.5795),
    "IN": (22.3511, 78.6677),
}

US_STATE_NAME_TO_CODE: Dict[str, str] = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "district of columbia": "DC",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
}
US_STATE_CODES = set(US_STATE_NAME_TO_CODE.values())
US_STATE_CODE_TO_NAME = {code: name for name, code in US_STATE_NAME_TO_CODE.items()}

_GEO_INDEX_LOCK = threading.Lock()
_ZIP_GEO_CACHE: Dict[str, Dict[str, tuple[float, float, str, str]]] = {}
_CITY_STATE_GEO_CACHE: Dict[str, Dict[str, tuple[float, float]]] = {}
_CITY_ONLY_GEO_CACHE: Dict[str, Dict[str, tuple[float, float]]] = {}
_CITY_STATE_COMPACT_GEO_CACHE: Dict[str, Dict[str, tuple[float, float]]] = {}
_CITY_ONLY_COMPACT_GEO_CACHE: Dict[str, Dict[str, tuple[float, float]]] = {}
_STATE_NAME_TO_CODE_CACHE: Dict[str, Dict[str, str]] = {}
_FACEBOOK_EMAIL_CACHE_LOCK = threading.Lock()
_FACEBOOK_EMAIL_CACHE: Dict[str, List[str]] = {}
_WEBSITE_CONTACT_CACHE_LOCK = threading.Lock()
_WEBSITE_CONTACT_CACHE: Dict[str, Dict[str, Any]] = {}


def _normalize_location_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _compact_location_key(value: str) -> str:
    return _normalize_location_key(value).replace(" ", "")


def _copy_cached_email_list(items: List[str]) -> List[str]:
    return [str(item).strip() for item in (items or []) if str(item).strip()]


def _copy_cached_contacts(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "emails": _copy_cached_email_list(list(data.get("emails") or [])),
        "socials": {
            str(key).strip(): str(value).strip()
            for key, value in dict(data.get("socials") or {}).items()
            if str(key).strip() and str(value).strip()
        },
        "intelligence": {
            str(key).strip(): list(value) if isinstance(value, list) else value
            for key, value in dict(data.get("intelligence") or {}).items()
            if str(key).strip()
        },
    }


def _get_cached_facebook_emails(cache_key: str) -> Optional[List[str]]:
    if not cache_key:
        return None
    with _FACEBOOK_EMAIL_CACHE_LOCK:
        cached = _FACEBOOK_EMAIL_CACHE.get(cache_key)
    if cached is None:
        return None
    return _copy_cached_email_list(cached)


def _store_cached_facebook_emails(cache_key: str, emails: List[str]) -> None:
    if not cache_key:
        return
    with _FACEBOOK_EMAIL_CACHE_LOCK:
        _FACEBOOK_EMAIL_CACHE[cache_key] = _copy_cached_email_list(emails)


def _get_cached_website_contacts(cache_key: str) -> Optional[Dict[str, Any]]:
    if not cache_key:
        return None
    with _WEBSITE_CONTACT_CACHE_LOCK:
        cached = _WEBSITE_CONTACT_CACHE.get(cache_key)
    if cached is None:
        return None
    return _copy_cached_contacts(cached)


def _store_cached_website_contacts(cache_key: str, contacts: Dict[str, Any]) -> None:
    if not cache_key:
        return
    with _WEBSITE_CONTACT_CACHE_LOCK:
        _WEBSITE_CONTACT_CACHE[cache_key] = _copy_cached_contacts(contacts)


def _load_geo_index(country_code: str) -> None:
    code = str(country_code or "").strip().upper()
    if not code:
        return
    with _GEO_INDEX_LOCK:
        if code in _ZIP_GEO_CACHE:
            return
        zip_map: Dict[str, tuple[float, float, str, str]] = {}
        city_state_map: Dict[str, tuple[float, float]] = {}
        city_only_map: Dict[str, tuple[float, float]] = {}
        city_state_compact_map: Dict[str, tuple[float, float]] = {}
        city_only_compact_map: Dict[str, tuple[float, float]] = {}
        state_name_to_code: Dict[str, str] = {}
        city_state_seen: Dict[str, str] = {}
        city_state_ambig: set[str] = set()
        city_state_seen_compact: Dict[str, str] = {}
        city_state_ambig_compact: set[str] = set()

        data_path = Path(__file__).resolve().parent / "data" / f"{code}.txt"
        if not data_path.exists():
            _ZIP_GEO_CACHE[code] = zip_map
            _CITY_STATE_GEO_CACHE[code] = city_state_map
            _CITY_ONLY_GEO_CACHE[code] = city_only_map
            _STATE_NAME_TO_CODE_CACHE[code] = state_name_to_code
            return

        try:
            with data_path.open("r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) < 11:
                        continue
                    zip_code = parts[1].strip()
                    city = parts[2].strip()
                    state_name = parts[3].strip()
                    state_code = parts[4].strip().upper()
                    try:
                        lat = float(parts[9])
                        lng = float(parts[10])
                    except Exception:
                        continue

                    if zip_code and zip_code not in zip_map:
                        zip_map[zip_code] = (lat, lng, city, state_code)

                    if state_name and state_code:
                        key = _normalize_location_key(state_name)
                        if key and key not in state_name_to_code:
                            state_name_to_code[key] = state_code

                    if city and state_code:
                        city_key = _normalize_location_key(city)
                        if not city_key:
                            continue
                        city_state_key = f"{city_key}|{state_code}"
                        if city_state_key not in city_state_map:
                            city_state_map[city_state_key] = (lat, lng)

                        prev_state = city_state_seen.get(city_key)
                        if prev_state is None:
                            city_state_seen[city_key] = state_code
                            city_only_map[city_key] = (lat, lng)
                        elif prev_state != state_code:
                            city_state_ambig.add(city_key)

                        compact_key = city_key.replace(" ", "")
                        if compact_key:
                            compact_state_key = f"{compact_key}|{state_code}"
                            if compact_state_key not in city_state_compact_map:
                                city_state_compact_map[compact_state_key] = (lat, lng)

                            prev_compact = city_state_seen_compact.get(compact_key)
                            if prev_compact is None:
                                city_state_seen_compact[compact_key] = state_code
                                city_only_compact_map[compact_key] = (lat, lng)
                            elif prev_compact != state_code:
                                city_state_ambig_compact.add(compact_key)
        except Exception:
            pass

        for key in city_state_ambig:
            city_only_map.pop(key, None)
        for key in city_state_ambig_compact:
            city_only_compact_map.pop(key, None)

        _ZIP_GEO_CACHE[code] = zip_map
        _CITY_STATE_GEO_CACHE[code] = city_state_map
        _CITY_ONLY_GEO_CACHE[code] = city_only_map
        _CITY_STATE_COMPACT_GEO_CACHE[code] = city_state_compact_map
        _CITY_ONLY_COMPACT_GEO_CACHE[code] = city_only_compact_map
        _STATE_NAME_TO_CODE_CACHE[code] = state_name_to_code


def _extract_zip_from_location(location: str) -> tuple[str, str] | None:
    if not location:
        return None
    match = re.search(r"\b(\d{6})\b", location)
    if match:
        return ("IN", match.group(1))
    match = re.search(r"\b(\d{5})(?:-\d{4})?\b", location)
    if match:
        return ("US", match.group(1))
    return None


def _infer_country_from_location(location: str) -> str | None:
    norm = _normalize_location_key(location)
    if not norm:
        return None
    if "india" in norm.split():
        return "IN"
    if "united states" in norm or "usa" in norm.split():
        return "US"
    tokens = {token.upper() for token in norm.split()}
    if tokens & US_STATE_CODES:
        return "US"
    return None


def _strip_country_tokens(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"\b(united\s+states|usa|india)\b", " ", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _resolve_state_code(state_part: str, country_code: str) -> str:
    if not state_part:
        return ""
    raw = str(state_part).strip()
    if not raw:
        return ""
    if country_code == "US":
        token = raw.upper()
        if len(token) == 2 and token in US_STATE_CODES:
            return token
        key = _normalize_location_key(raw)
        return US_STATE_NAME_TO_CODE.get(key, "")
    _load_geo_index(country_code)
    key = _normalize_location_key(raw)
    return _STATE_NAME_TO_CODE_CACHE.get(country_code, {}).get(key, "")


def _extract_city_state(location: str, country_code: str) -> tuple[str, str]:
    cleaned = _strip_country_tokens(location)
    cleaned = re.sub(r"\b\d{6}\b", " ", cleaned)
    cleaned = re.sub(r"\b\d{5}(?:-\d{4})?\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return ("", "")

    parts = [part.strip() for part in cleaned.split(",") if part.strip()]
    city_part = ""
    state_part = ""
    if len(parts) >= 2:
        state_part = parts[-1]
        city_part = parts[-2]
    else:
        match = re.match(r"^(.*?)[\s]+([A-Za-z]{2})$", cleaned)
        if match:
            city_part = match.group(1).strip()
            state_part = match.group(2).strip()
        else:
            city_part = cleaned

    city_key = _normalize_location_key(city_part)
    state_code = _resolve_state_code(state_part, country_code)
    return (city_key, state_code)


def _resolve_location_context(location: str) -> tuple[str | None, tuple[float, float] | None]:
    loc = str(location or "").strip()
    if not loc:
        return (None, None)

    zip_hit = _extract_zip_from_location(loc)
    if zip_hit:
        country, zip_code = zip_hit
        _load_geo_index(country)
        geo = _ZIP_GEO_CACHE.get(country, {}).get(zip_code)
        if geo:
            return (country, (geo[0], geo[1]))
        return (country, DEFAULT_COUNTRY_GEO.get(country))

    country = _infer_country_from_location(loc)
    if country:
        _load_geo_index(country)
        city_key, state_code = _extract_city_state(loc, country)
        if city_key and state_code:
            key = f"{city_key}|{state_code}"
            coords = _CITY_STATE_GEO_CACHE.get(country, {}).get(key)
            if coords:
                return (country, coords)
            compact_key = city_key.replace(" ", "")
            if compact_key:
                compact_state_key = f"{compact_key}|{state_code}"
                coords = _CITY_STATE_COMPACT_GEO_CACHE.get(country, {}).get(compact_state_key)
                if coords:
                    return (country, coords)
        if city_key:
            coords = _CITY_ONLY_GEO_CACHE.get(country, {}).get(city_key)
            if coords:
                return (country, coords)
            compact_key = city_key.replace(" ", "")
            if compact_key:
                coords = _CITY_ONLY_COMPACT_GEO_CACHE.get(country, {}).get(compact_key)
                if coords:
                    return (country, coords)
        default_geo = DEFAULT_COUNTRY_GEO.get(country)
        if default_geo:
            return (country, default_geo)

    city_key = _normalize_location_key(_strip_country_tokens(loc))
    if city_key and len(city_key) >= 3:
        compact_key = city_key.replace(" ", "")
        found: tuple[str, tuple[float, float]] | None = None
        for code in ("US", "IN"):
            _load_geo_index(code)
            coords = _CITY_ONLY_GEO_CACHE.get(code, {}).get(city_key)
            if coords:
                if found:
                    return (None, None)
                found = (code, coords)
            elif compact_key:
                coords = _CITY_ONLY_COMPACT_GEO_CACHE.get(code, {}).get(compact_key)
                if coords:
                    if found:
                        return (None, None)
                    found = (code, coords)
        if found:
            return found

    return (None, None)


def _build_search_url(query: str, country_hint: str | None, geo_hint: tuple[float, float] | None = None) -> str:
    base = f"https://www.google.com/maps/search/{quote_plus(query)}"
    params: Dict[str, str] = {"hl": "en"}
    if country_hint == "US":
        params["gl"] = "us"
    elif country_hint == "IN":
        params["gl"] = "in"
    url = f"{base}?{urlencode(params)}" if params else base
    if geo_hint:
        url = f"{url}/@{geo_hint[0]:.6f},{geo_hint[1]:.6f},13z"
    return url


def _build_search_queries(keyword: str, location: str) -> List[str]:
    kw = re.sub(r"\s+", " ", str(keyword or "").strip())
    loc = re.sub(r"\s+", " ", str(location or "").strip())
    location_without_country = _strip_country_tokens(loc) or loc
    queries: List[str] = []

    def _add(candidate: str) -> None:
        cleaned = re.sub(r"\s+", " ", str(candidate or "").strip())
        if cleaned and cleaned not in queries:
            queries.append(cleaned)

    if kw and loc:
        kw_compact = _compact_location_key(kw)
        loc_compact = _compact_location_key(location_without_country)
        padded_kw = f" {kw.lower()} "
        has_location_connector = any(
            connector in padded_kw
            for connector in (" in ", " near ", " around ", " within ", " at ")
        )
        if loc_compact and loc_compact in kw_compact:
            _add(kw)
        elif has_location_connector:
            _add(f"{kw} {location_without_country}")
            _add(f"{kw} {loc}")
        else:
            zip_hit = _extract_zip_from_location(loc)
            if zip_hit:
                _add(f"{kw} in {zip_hit[1]}")
            _add(f"{kw} in {location_without_country}")
            _add(f"{kw} near {location_without_country}")
            _add(f"{kw} {location_without_country}")
            _add(f"{kw} {loc}")
    else:
        _add(f"{kw} {loc}".strip())

    return queries or [f"{kw} {loc}".strip()]


def _normalize_zip_value(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", str(value or "").strip()).upper()


def _safe_float(value: Any) -> float | None:
    try:
        text = str(value or "").strip()
        if not text:
            return None
        return float(text)
    except Exception:
        return None


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))


def _build_location_guard(location: str) -> Dict[str, Any]:
    raw_location = str(location or "").strip()
    if not raw_location:
        return {}

    country, geo_hint = _resolve_location_context(raw_location)
    guard: Dict[str, Any] = {
        "location": raw_location,
        "country": str(country or "").strip().upper(),
        "geo_hint": geo_hint,
        "expected_zip": "",
        "expected_state": "",
        "expected_city_key": "",
        "max_distance_km": 0.0,
    }

    zip_hit = _extract_zip_from_location(raw_location)
    if zip_hit:
        country_code, zip_code = zip_hit
        guard["country"] = country_code
        guard["expected_zip"] = zip_code
        _load_geo_index(country_code)
        geo_row = _ZIP_GEO_CACHE.get(country_code, {}).get(zip_code)
        if geo_row:
            guard["expected_city_key"] = _normalize_location_key(str(geo_row[2]).strip())
            guard["expected_state"] = str(geo_row[3]).strip().upper()
        # ZIP searches should stay local; use a generous radius for sparse regions like Alaska.
        # Increased radius for Alaska and other sparse areas
        guard["max_distance_km"] = 800.0 if country_code == "US" else 300.0
        return guard

    if guard["country"]:
        city_key, state_code = _extract_city_state(raw_location, guard["country"])
        guard["expected_city_key"] = city_key
        guard["expected_state"] = state_code
        if city_key and state_code:
            guard["max_distance_km"] = 250.0 if guard["country"] == "US" else 120.0
        return guard if (city_key or state_code or geo_hint) else {}

    return {}


def _row_matches_location_guard(row: Dict[str, Any], guard: Dict[str, Any]) -> tuple[bool, str]:
    if not guard:
        return True, ""

    country = str(guard.get("country", "")).strip().upper()
    expected_zip = _normalize_zip_value(guard.get("expected_zip", ""))
    expected_state = str(guard.get("expected_state", "")).strip().upper()
    geo_hint = guard.get("geo_hint")
    max_distance_km = float(guard.get("max_distance_km", 0.0) or 0.0)

    row_zip = _normalize_zip_value(row.get("zip_code", ""))
    if expected_zip and row_zip == expected_zip:
        return True, ""

    row_state_raw = str(row.get("state", "")).strip()
    row_state = (
        _resolve_state_code(row_state_raw, country)
        if country == "US"
        else row_state_raw.upper()
    )
    # More lenient state matching - only reject if we're very confident it's wrong
    if expected_state and row_state and row_state != expected_state:
        # Allow if no ZIP code to verify (might be a chain/franchise)
        if not expected_zip and not row_zip:
            logger.warning(f"State mismatch but no ZIP to verify: expected {expected_state}, got {row_state}")
            return True, ""  # Allow it through
        return False, f"Location mismatch: expected {expected_state}, got {row_state}"



    lat = _safe_float(row.get("latitude"))
    lng = _safe_float(row.get("longitude"))
    if geo_hint and lat is not None and lng is not None and max_distance_km > 0:
        distance_km = _haversine_km(float(geo_hint[0]), float(geo_hint[1]), lat, lng)
        if distance_km > max_distance_km:
            return False, f"Location mismatch: {distance_km:.0f} km away from target"

    return True, ""


def _card_matches_location_guard(card_text: str, guard: Dict[str, Any]) -> tuple[bool, str]:
    if not guard:
        return True, ""

    text = str(card_text or "").strip()
    if not text:
        # Missing card text is inconclusive, so allow the detail scrape to decide.
        return True, ""

    normalized = _normalize_location_key(text)
    compact = normalized.replace(" ", "")
    country = str(guard.get("country", "")).strip().upper()
    expected_zip = _normalize_zip_value(guard.get("expected_zip", ""))
    expected_state = str(guard.get("expected_state", "")).strip().upper()
    expected_city_key = _normalize_location_key(guard.get("expected_city_key", ""))

    if expected_zip:
        found_zips = [_normalize_zip_value(z) for z in re.findall(r"\b\d{5}(?:-\d{4})?\b", text)]
        if expected_zip in found_zips:
            return True, ""

    if country == "US" and expected_state:
        strong_expected_pattern = re.compile(
            rf"(?:,\s*{re.escape(expected_state)}\b|\b{re.escape(expected_state)}\s+\d{{5}}(?:-\d{{4}})?\b)",
            re.IGNORECASE,
        )
        if strong_expected_pattern.search(text):
            return True, ""

        expected_state_name = _normalize_location_key(US_STATE_CODE_TO_NAME.get(expected_state, ""))
        if expected_state_name and re.search(rf"\b{re.escape(expected_state_name)}\b", normalized):
            return True, ""

        for state_code, state_name in US_STATE_CODE_TO_NAME.items():
            if state_code == expected_state:
                continue
            strong_other_pattern = re.compile(
                rf"(?:,\s*{re.escape(state_code)}\b|\b{re.escape(state_code)}\s+\d{{5}}(?:-\d{{4}})?\b)",
                re.IGNORECASE,
            )
            if strong_other_pattern.search(text):
                return False, f"Search result state mismatch: expected {expected_state}, got {state_code}"
            normalized_state_name = _normalize_location_key(state_name)
            if normalized_state_name and re.search(rf"\b{re.escape(normalized_state_name)}\b", normalized):
                return False, f"Search result state mismatch: expected {expected_state}, got {state_code}"

    if expected_city_key:
        compact_city = expected_city_key.replace(" ", "")
        if expected_city_key in normalized or (compact_city and compact_city in compact):
            return True, ""

    return True, ""

BLOCK_SIGNAL_TERMS = [
    "unusual traffic",
    "our systems have detected",
    "automated queries",
    "captcha",
    "verify you are human",
    "are you a robot",
    "sorry",
]

TECHNOLOGY_SIGNATURES: List[tuple[str, List[str]]] = [
    ("WordPress", [r"wp-content", r"wp-includes", r"wordpress"]),
    ("WooCommerce", [r"woocommerce", r"wc-ajax"]),
    ("Shopify", [r"cdn\.shopify\.com", r"shopify-payment-button", r"shopify"]),
    ("Wix", [r"wixstatic\.com", r"wixpress\.com", r"\b_wix\b"]),
    ("Squarespace", [r"squarespace", r"static1\.squarespace"]),
    ("Webflow", [r"webflow", r"webflow\.io"]),
    ("Next.js", [r"_next/", r"__next_data__"]),
    ("React", [r"data-reactroot", r"__reactfiber", r"react-dom"]),
    ("Vue", [r"vue\.js", r"__vue__", r"vue-router"]),
    ("Angular", [r"ng-version", r"angular\.js", r"angular\.min\.js"]),
    ("Bootstrap", [r"bootstrap(?:\.min)?\.(?:css|js)"]),
    ("Google Tag Manager", [r"googletagmanager\.com/gtm\.js", r"\bgtm-[a-z0-9]+\b"]),
    ("Google Analytics", [r"google-analytics\.com", r"googletagmanager\.com/gtag", r"gtag\("]),
    ("Cloudflare", [r"\bcf-ray\b", r"cdn-cgi", r"cloudflare"]),
    ("HubSpot", [r"js\.hs-scripts\.com", r"hubspot"]),
]

CONTACT_PAGE_KEYWORDS = ["contact", "support", "help", "reach-us", "get-in-touch"]
TEAM_PAGE_KEYWORDS = ["team", "staff", "leadership", "our-team", "people"]
ABOUT_PAGE_KEYWORDS = ["about", "company", "our-story", "who-we-are"]
CAREERS_PAGE_KEYWORDS = ["career", "careers", "job", "jobs", "hiring", "work-with-us"]


class AdaptiveAntiBlockController:
    """Thread-safe adaptive slowdown controller for anti-block handling."""

    def __init__(self, enabled: bool = True, history_size: int = 28) -> None:
        self.enabled = bool(enabled)
        self._lock = threading.Lock()
        self._recent_outcomes = deque(maxlen=max(8, min(int(history_size), 120)))
        self._delay_multiplier = 1.0
        self._cooldown_until = 0.0
        self._total_navigations = 0
        self._blocked_navigations = 0

    def _recent_block_rate_locked(self) -> float:
        if not self._recent_outcomes:
            return 0.0
        return float(sum(self._recent_outcomes)) / float(len(self._recent_outcomes))

    def register_success(self) -> Dict[str, float]:
        if not self.enabled:
            return {"block_rate": 0.0, "delay_multiplier": 1.0, "cooldown_seconds": 0.0}
        with self._lock:
            self._total_navigations += 1
            self._recent_outcomes.append(0)
            block_rate = self._recent_block_rate_locked()
            if block_rate <= 0.15:
                self._delay_multiplier = max(1.0, self._delay_multiplier * 0.90)
            elif block_rate <= 0.30:
                self._delay_multiplier = max(1.0, self._delay_multiplier * 0.95)
            cooldown = max(0.0, self._cooldown_until - time.time())
            return {
                "block_rate": block_rate,
                "delay_multiplier": self._delay_multiplier,
                "cooldown_seconds": cooldown,
            }

    def register_block(self) -> Dict[str, float]:
        if not self.enabled:
            return {"block_rate": 0.0, "delay_multiplier": 1.0, "cooldown_seconds": 0.0, "recommended_wait": 0.0}
        with self._lock:
            self._total_navigations += 1
            self._blocked_navigations += 1
            self._recent_outcomes.append(1)
            block_rate = self._recent_block_rate_locked()

            if block_rate >= 0.60:
                factor = 1.75
            elif block_rate >= 0.40:
                factor = 1.55
            elif block_rate >= 0.25:
                factor = 1.35
            else:
                factor = 1.20

            self._delay_multiplier = min(8.0, max(1.0, self._delay_multiplier * factor))

            cooldown = min(40.0, 2.0 + (block_rate * 18.0) + min(self._blocked_navigations * 0.4, 10.0))
            self._cooldown_until = max(self._cooldown_until, time.time() + cooldown)
            recommended_wait = min(35.0, 1.2 + block_rate * 12.0 + min(self._blocked_navigations * 0.25, 8.0))
            return {
                "block_rate": block_rate,
                "delay_multiplier": self._delay_multiplier,
                "cooldown_seconds": cooldown,
                "recommended_wait": recommended_wait,
            }

    def scaled_delay_range(self, min_delay: float, max_delay: float) -> tuple[float, float]:
        if not self.enabled:
            lo = max(0.1, float(min_delay))
            hi = max(lo, float(max_delay))
            return lo, hi
        with self._lock:
            multiplier = self._delay_multiplier
        lo = max(0.1, float(min_delay) * multiplier)
        hi = max(lo, float(max_delay) * multiplier)
        return min(lo, 20.0), min(hi, 30.0)

    def wait_if_cooling_down(self, max_wait: float = 25.0) -> float:
        if not self.enabled:
            return 0.0
        with self._lock:
            wait_seconds = max(0.0, self._cooldown_until - time.time())
        if wait_seconds <= 0:
            return 0.0
        sleep_for = min(float(max_wait), wait_seconds)
        time.sleep(sleep_for)
        return sleep_for

    def snapshot(self) -> Dict[str, float]:
        if not self.enabled:
            return {
                "enabled": 0.0,
                "block_rate": 0.0,
                "delay_multiplier": 1.0,
                "cooldown_seconds": 0.0,
                "total_navigations": 0.0,
                "blocked_navigations": 0.0,
            }
        with self._lock:
            return {
                "enabled": 1.0,
                "block_rate": self._recent_block_rate_locked(),
                "delay_multiplier": self._delay_multiplier,
                "cooldown_seconds": max(0.0, self._cooldown_until - time.time()),
                "total_navigations": float(self._total_navigations),
                "blocked_navigations": float(self._blocked_navigations),
            }


def _looks_like_block_text(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(term in lowered for term in BLOCK_SIGNAL_TERMS)


def _is_probable_block_exception(error: Any) -> bool:
    return _looks_like_block_text(str(error or ""))


def _new_website_intelligence() -> Dict[str, Any]:
    return {
        "schema_types": set(),
        "technologies": set(),
        "contact_pages": set(),
        "team_pages": set(),
        "about_pages": set(),
        "careers_pages": set(),
        "_scanned_urls": set(),
    }


def _collect_jsonld_types(value: Any, output: set[str]) -> None:
    if value is None:
        return
    if isinstance(value, dict):
        raw_type = value.get("@type")
        if isinstance(raw_type, str):
            cleaned = re.sub(r"\s+", " ", raw_type).strip()
            if cleaned:
                output.add(cleaned)
        elif isinstance(raw_type, list):
            for item in raw_type:
                if isinstance(item, str):
                    cleaned = re.sub(r"\s+", " ", item).strip()
                    if cleaned:
                        output.add(cleaned)
        for nested in value.values():
            _collect_jsonld_types(nested, output)
        return
    if isinstance(value, list):
        for item in value:
            _collect_jsonld_types(item, output)


def _extract_jsonld_schema_types(html: str) -> List[str]:
    if not html:
        return []
    matches = re.findall(
        r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    output: set[str] = set()
    for raw_script in matches:
        payload = html_lib.unescape(str(raw_script or "").strip())
        if not payload:
            continue
        try:
            parsed = json.loads(payload)
        except Exception:
            continue
        _collect_jsonld_types(parsed, output)
    return sorted(output)


def _detect_technologies_from_html(html: str) -> List[str]:
    text = str(html or "")
    if not text:
        return []
    lowered = text.lower()
    detected: List[str] = []
    for name, patterns in TECHNOLOGY_SIGNATURES:
        for pattern in patterns:
            if re.search(pattern, lowered, flags=re.IGNORECASE):
                detected.append(name)
                break
    return sorted(dict.fromkeys(detected))


def _classify_page_url(url: str, intelligence: Dict[str, Any]) -> None:
    if not url or not isinstance(intelligence, dict):
        return
    parsed = urlparse(url)
    path_text = f"{parsed.path} {parsed.query}".lower()
    if any(token in path_text for token in CONTACT_PAGE_KEYWORDS):
        intelligence.setdefault("contact_pages", set()).add(url)
    if any(token in path_text for token in TEAM_PAGE_KEYWORDS):
        intelligence.setdefault("team_pages", set()).add(url)
    if any(token in path_text for token in ABOUT_PAGE_KEYWORDS):
        intelligence.setdefault("about_pages", set()).add(url)
    if any(token in path_text for token in CAREERS_PAGE_KEYWORDS):
        intelligence.setdefault("careers_pages", set()).add(url)


def _update_website_intelligence(intelligence: Dict[str, Any], current_url: str, html_content: str) -> None:
    if not isinstance(intelligence, dict):
        return
    if current_url:
        scanned = intelligence.setdefault("_scanned_urls", set())
        scanned.add(current_url)
        _classify_page_url(current_url, intelligence)
    schema_types = _extract_jsonld_schema_types(html_content)
    if schema_types:
        intelligence.setdefault("schema_types", set()).update(schema_types)
    technologies = _detect_technologies_from_html(html_content)
    if technologies:
        intelligence.setdefault("technologies", set()).update(technologies)


def _finalize_website_intelligence(intelligence: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(intelligence, dict):
        return {
            "schema_types": [],
            "technologies": [],
            "contact_pages": [],
            "team_pages": [],
            "about_pages": [],
            "careers_pages": [],
            "pages_scanned": 0,
        }
    scanned_urls = intelligence.get("_scanned_urls")
    if isinstance(scanned_urls, set):
        pages_scanned = len(scanned_urls)
    else:
        pages_scanned = 0
    return {
        "schema_types": sorted(str(x).strip() for x in intelligence.get("schema_types", set()) if str(x).strip()),
        "technologies": sorted(str(x).strip() for x in intelligence.get("technologies", set()) if str(x).strip()),
        "contact_pages": sorted(str(x).strip() for x in intelligence.get("contact_pages", set()) if str(x).strip()),
        "team_pages": sorted(str(x).strip() for x in intelligence.get("team_pages", set()) if str(x).strip()),
        "about_pages": sorted(str(x).strip() for x in intelligence.get("about_pages", set()) if str(x).strip()),
        "careers_pages": sorted(str(x).strip() for x in intelligence.get("careers_pages", set()) if str(x).strip()),
        "pages_scanned": pages_scanned,
    }


def _merge_website_intelligence(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    list_keys = [
        "schema_types",
        "technologies",
        "contact_pages",
        "team_pages",
        "about_pages",
        "careers_pages",
    ]
    merged = {}
    for key in list_keys:
        merged[key] = sorted(
            {
                str(item).strip()
                for item in ([*(base.get(key) or []), *(extra.get(key) or [])])
                if str(item).strip()
            }
        )
    merged["pages_scanned"] = int(base.get("pages_scanned", 0) or 0) + int(extra.get("pages_scanned", 0) or 0)
    return merged


def _sleep(low: float = 0.5, high: float = 1.1) -> None:
    lo = min(low, high)
    hi = max(low, high)
    time.sleep(random.uniform(lo, hi))


def _is_running_in_async_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _install_resource_blocker(route_target, blocked_resource_types: set[str] | None = None):
    blocked = set(blocked_resource_types or {"image", "media", "font"})

    def _route_handler(route, request=None) -> None:
        req = request or getattr(route, "request", None)
        resource_type = ""
        if req is not None:
            try:
                resource_type = str(getattr(req, "resource_type", "") or "")
            except Exception:
                resource_type = ""
        try:
            if resource_type in blocked:
                route.abort()
            else:
                route.continue_()
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            message = str(exc).lower()
            if any(
                token in message
                for token in (
                    "cancelled",
                    "context closed",
                    "browser has been closed",
                    "page closed",
                    "target page, context or browser has been closed",
                )
            ):
                return
            try:
                route.continue_()
            except BaseException as followup_exc:
                if isinstance(followup_exc, (KeyboardInterrupt, SystemExit)):
                    raise
                return

    route_target.route("**/*", _route_handler)
    return _route_handler


def _remove_route_handler(route_target, route_handler) -> None:
    if not route_target or not route_handler:
        return
    try:
        route_target.unroute("**/*", route_handler)
    except Exception:
        pass


def _safe_text(page, selectors: List[str], timeout_ms: int = 1200) -> str:
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            value = locator.inner_text(timeout=timeout_ms).strip()
            if value:
                return value
        except Exception:
            continue
    return ""


def _safe_attr(page, selector: str, attr: str, timeout_ms: int = 1200) -> str:
    try:
        locator = page.locator(selector).first
        value = locator.get_attribute(attr, timeout=timeout_ms)
        return (value or "").strip()
    except Exception:
        return ""

def _safe_body_text(page, timeout_ms: int = 2500) -> str:
    try:
        return page.locator("body").inner_text(timeout=timeout_ms)
    except Exception:
        return ""


def _clean_field(value: str) -> str:
    if not value:
        return ""
    text = re.sub(r"[\uE000-\uF8FF]", " ", str(value))
    text = re.sub(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    for prefix in (
        "Address:",
        "Phone:",
        "Website:",
        "Plus code:",
        "Located in:",
    ):
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
    return text


def _parse_usa_address_fallback(address: str) -> Dict[str, str]:
    cleaned = _clean_field(address)
    if not cleaned:
        return {
            "street_number": "",
            "street_name": "",
            "city": "",
            "state": "",
            "zip_code": "",
        }

    cleaned = re.sub(r",?\s*(United States|USA)\s*$", "", cleaned, flags=re.IGNORECASE).strip()
    match = re.search(
        r"^(?P<street>.+?),\s*(?P<city>[^,]+),\s*(?P<state>[A-Z]{2})\s+(?P<zip>\d{5}(?:-\d{4})?)$",
        cleaned,
    )
    if not match:
        return {
            "street_number": "",
            "street_name": "",
            "city": "",
            "state": "",
            "zip_code": "",
        }

    street = match.group("street").strip()
    street_number_match = re.match(r"^(?P<number>\d+[A-Za-z-]*)\s+(?P<rest>.+)$", street)
    return {
        "street_number": street_number_match.group("number") if street_number_match else "",
        "street_name": street,
        "city": match.group("city").strip(),
        "state": match.group("state").strip(),
        "zip_code": match.group("zip").strip(),
    }


def _parse_usa_address(address: str) -> Dict[str, str]:
    """Parse USA address into structured components using usaddress library."""
    if not address:
        return {
            "street_number": "",
            "street_name": "",
            "city": "",
            "state": "",
            "zip_code": "",
        }

    normalized = _clean_field(address)
    looks_us = bool(
        re.search(r"\b(united states|usa)\b", normalized, flags=re.IGNORECASE)
        or re.search(r"\b[A-Z]{2}\s+\d{5}(?:-\d{4})?\b", normalized)
    )
    if not looks_us:
        return {
            "street_number": "",
            "street_name": "",
            "city": "",
            "state": "",
            "zip_code": "",
        }
    if not USADDRESS_AVAILABLE:
        return _parse_usa_address_fallback(normalized)
    
    try:
        parsed, address_type = usaddress.tag(normalized)
        
        # Extract components
        street_parts = []
        if parsed.get("AddressNumber"):
            street_parts.append(parsed["AddressNumber"])
        if parsed.get("StreetNamePreDirectional"):
            street_parts.append(parsed["StreetNamePreDirectional"])
        if parsed.get("StreetName"):
            street_parts.append(parsed["StreetName"])
        if parsed.get("StreetNamePostType"):
            street_parts.append(parsed["StreetNamePostType"])
        if parsed.get("StreetNamePostDirectional"):
            street_parts.append(parsed["StreetNamePostDirectional"])
        if parsed.get("OccupancyType"):
            street_parts.append(parsed["OccupancyType"])
        if parsed.get("OccupancyIdentifier"):
            street_parts.append(parsed["OccupancyIdentifier"])
        
        return {
            "street_number": parsed.get("AddressNumber", ""),
            "street_name": " ".join(street_parts),
            "city": parsed.get("PlaceName", ""),
            "state": parsed.get("StateName", ""),
            "zip_code": parsed.get("ZipCode", ""),
        }
    except Exception as e:
        fallback = _parse_usa_address_fallback(normalized)
        if any(fallback.values()):
            return fallback
        logger.warning(f"Failed to parse USA address '{address}': {e}")
        return {
            "street_number": "",
            "street_name": "",
            "city": "",
            "state": "",
            "zip_code": "",
        }


def _extract_from_data_item(
    page,
    data_item_ids: List[str],
    element_tag: str = "button",
    timeout_ms: int = 1200,
) -> str:
    for data_item_id in data_item_ids:
        selectors = [
            f"{element_tag}[data-item-id='{data_item_id}']",
            f"{element_tag}[data-item-id^='{data_item_id}']",
            f"[data-item-id='{data_item_id}']",
            f"[data-item-id^='{data_item_id}']",
        ]
        value = _safe_text(page, selectors, timeout_ms=timeout_ms)
        if value:
            return _clean_field(value)
        for selector in selectors:
            for attr in ("aria-label", "data-tooltip", "title"):
                value = _safe_attr(page, selector, attr, timeout_ms=timeout_ms)
                cleaned = _clean_field(value)
                if cleaned:
                    return cleaned
    return ""


def _extract_coords(url: str) -> tuple[str, str]:
    if not url:
        return "", ""
    match = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", url)
    if not match:
        return "", ""
    return match.group(1), match.group(2)


def _extract_cid(url: str) -> str:
    if not url:
        return ""
    match = re.search(r"[?&]cid=(\d+)", url)
    return match.group(1) if match else ""


def _extract_feature_id(url: str) -> str:
    if not url:
        return ""
    match = re.search(r"!1s([^!]+)!", url)
    if not match:
        return ""
    return unquote(match.group(1)).strip()


def _clean_place_name(value: str) -> str:
    text = html_lib.unescape(_clean_field(value or "")).strip()
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s*[-|]\s*google maps.*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*·\s*google maps.*$", "", text, flags=re.IGNORECASE)
    return text.strip(" -|·")


def _looks_like_bad_place_name(value: str) -> bool:
    text = _clean_place_name(value).strip()
    if not text:
        return True
    lowered = text.lower()
    if lowered.startswith("unknown_"):
        return True
    if re.fullmatch(r"[0-9\W_]+", lowered):
        return True
    blocked = {
        "see photos",
        "photos",
        "photo",
        "reviews",
        "review",
        "directions",
        "website",
        "call",
        "save",
        "share",
        "overview",
        "menu",
        "order online",
        "book a table",
    }
    return lowered in blocked


def _extract_place_name_from_maps_url(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(_normalize_url(url))
        path = unquote(parsed.path or "")
    except Exception:
        return ""
    match = re.search(r"/maps/place/([^/]+)", path, flags=re.IGNORECASE)
    if not match:
        return ""
    candidate = unquote(match.group(1)).replace("+", " ")
    candidate = _clean_place_name(candidate)
    return "" if _looks_like_bad_place_name(candidate) else candidate


def _looks_like_location_redirect_result(link: str, keyword: str, location: str) -> bool:
    if not link or not location:
        return False

    place_name = _compact_location_key(_extract_place_name_from_maps_url(link))
    if not place_name:
        return False

    location_candidates = [
        _compact_location_key(location),
        _compact_location_key(_strip_country_tokens(location)),
    ]
    location_match = any(
        candidate and (place_name in candidate or candidate in place_name)
        for candidate in location_candidates
    )
    if not location_match:
        return False

    keyword_key = _compact_location_key(keyword)
    if keyword_key and (keyword_key in place_name or place_name in keyword_key):
        return False

    return True


def _extract_place_name(page, current_url: str = "", timeout_ms: int = 1200) -> str:
    selector_name = _clean_place_name(
        _safe_text(
            page,
            [
                "h1.DUwDvf",
                "h1.fontHeadlineLarge",
                "h1[role='heading']",
                "div[role='main'] h1",
                "h1",
            ],
            timeout_ms=timeout_ms,
        )
    )
    if not _looks_like_bad_place_name(selector_name):
        return selector_name

    title_candidates = [
        _safe_attr(page, "meta[property='og:title']", "content", timeout_ms=timeout_ms),
        _safe_attr(page, "meta[name='title']", "content", timeout_ms=timeout_ms),
        _safe_attr(page, "meta[itemprop='name']", "content", timeout_ms=timeout_ms),
    ]
    try:
        page_title = (page.title() or "").strip()
        if page_title:
            title_candidates.append(page_title)
    except Exception:
        pass

    for raw in title_candidates:
        candidate = _clean_place_name(raw)
        if not candidate:
            continue
        probes = [candidate]
        for sep in (" · ", " - ", " | "):
            if sep in candidate:
                probes.append(candidate.split(sep, 1)[0].strip())
        for probe in probes:
            cleaned = _clean_place_name(probe)
            if not _looks_like_bad_place_name(cleaned):
                return cleaned

    og_url = _safe_attr(page, "meta[property='og:url']", "content", timeout_ms=timeout_ms)
    canonical_url = _safe_attr(page, "link[rel='canonical']", "href", timeout_ms=timeout_ms)
    for source_url in (current_url, og_url, canonical_url):
        candidate = _extract_place_name_from_maps_url(source_url)
        if candidate:
            return candidate
    return ""


def _looks_like_place_id(value: str) -> bool:
    token = str(value or "").strip()
    if not token:
        return False
    if len(token) < 16 or len(token) > 128:
        return False
    if re.fullmatch(r"(?:ChI|GhI)[A-Za-z0-9_-]{16,120}", token):
        return True
    if re.fullmatch(r"0x[0-9a-fA-F]{8,40}:0x[0-9a-fA-F]{8,40}", token):
        return True
    return False


def _extract_place_id(page, current_url: str, feature_id: str) -> str:
    place_id_pattern = r"(?:ChI[A-Za-z0-9_-]{16,120}|GhI[A-Za-z0-9_-]{16,120}|0x[0-9a-fA-F]{8,40}:0x[0-9a-fA-F]{8,40})"
    candidate_urls = [current_url]
    try:
        og_url = _safe_attr(page, "meta[property='og:url']", "content")
        canonical_url = _safe_attr(page, "link[rel='canonical']", "href")
        if og_url:
            candidate_urls.append(og_url)
        if canonical_url:
            candidate_urls.append(canonical_url)
    except Exception:
        pass

    url_patterns = [
        rf"[?&]query_place_id=({place_id_pattern})",
        rf"[?&]place_id=({place_id_pattern})",
        rf"!1s({place_id_pattern})!",
    ]
    for source in candidate_urls:
        for pattern in url_patterns:
            m = re.search(pattern, source or "")
            if m and _looks_like_place_id(m.group(1)):
                return m.group(1)

    if _looks_like_place_id(feature_id):
        return feature_id

    try:
        html = page.content()
    except Exception:
        return ""

    html_patterns = [
        rf'"place_id":"({place_id_pattern})"',
        rf'"placeid":"({place_id_pattern})"',
        rf"place_id\\u003d({place_id_pattern})",
        rf"query_place_id\\u003d({place_id_pattern})",
    ]
    for pattern in html_patterns:
        m = re.search(pattern, html)
        if m and _looks_like_place_id(m.group(1)):
            return m.group(1)

    # Limited-view fallback: parse place_id from the maps preview payload.
    try:
        preview_url = _extract_preview_place_url(page)
        if preview_url:
            headers = {
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "text/plain,application/json,text/html,*/*",
            }
            preview_text = _fetch_url(preview_url, timeout=8, headers=headers)
            if preview_text:
                payload = preview_text.strip()
                if payload.startswith(")]}'"):
                    parts = payload.split("\n", 1)
                    payload = parts[1] if len(parts) > 1 else payload[4:]
                fallback_patterns = [
                    rf'"place_id":"({place_id_pattern})"',
                    rf'"placeid":"({place_id_pattern})"',
                    rf"({place_id_pattern})",
                ]
                for pattern in fallback_patterns:
                    m = re.search(pattern, payload)
                    if m and _looks_like_place_id(m.group(1)):
                        return m.group(1)
    except Exception:
        pass

    generic = re.search(rf"\b({place_id_pattern})\b", html)
    if generic and _looks_like_place_id(generic.group(1)):
        return generic.group(1)

    return ""


def _extract_price_level(category_text: str, body_text: str) -> str:
    combined = f"{category_text} {body_text}"
    match = re.search(r"(\${1,4}|USD|INR|GBP|EUR)", combined, flags=re.IGNORECASE)
    return match.group(1).upper() if match else ""


def _is_placeholder_text(value: str) -> bool:
    if not value:
        return True
    cleaned = re.sub(r"[\uE000-\uF8FF]", "", str(value))
    cleaned = re.sub(r"[\s\W_]+", "", cleaned, flags=re.UNICODE)
    return cleaned == ""


def _normalize_count_token(token: str) -> str:
    raw = str(token or "").strip().replace(",", "")
    if not raw:
        return ""
    match = re.match(r"^(\d+(?:\.\d+)?)([kKmM])$", raw)
    if match:
        number = float(match.group(1))
        suffix = match.group(2).lower()
        multiplier = 1000 if suffix == "k" else 1000000
        return str(int(number * multiplier))
    digits = re.sub(r"[^\d]", "", raw)
    return digits


def _extract_rating_value(text: str) -> str:
    if not text:
        return ""
    match = re.search(r"\b([0-5](?:\.\d+)?)\b", text)
    return match.group(1) if match else ""


def _extract_review_count_value(text: str) -> str:
    if not text:
        return ""
    normalized_text = re.sub(r"[\u202f\u00a0]", " ", str(text))

    # Common standalone card format: "(8,809)"
    standalone = re.fullmatch(r"\(\s*([\d.,]+[kKmM]?)\s*\)", normalized_text.strip())
    if standalone:
        token = _normalize_count_token(standalone.group(1))
        if token:
            return token

    patterns = [
        r"\b[0-5](?:\.\d+)?[^\d\n]{0,24}\(\s*([\d.,]+[kKmM]?)\s*\)",
        r"\b[0-5](?:\.\d+)?\s*\(\s*([\d.,]+[kKmM]?)\s*\)",
        r"\(\s*([\d.,]+[kKmM]?)\s*reviews?\s*\)",
        r"\b([\d.,]+[kKmM]?)\s+reviews?\b",
        r"\breviews?\s*[:\-]?\s*([\d.,]+[kKmM]?)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized_text, flags=re.IGNORECASE)
        if match:
            normalized = _normalize_count_token(match.group(1))
            if normalized:
                return normalized
    return ""


def _extract_rating_review_from_rating_panel(page, timeout_ms: int = 1200) -> Dict[str, str]:
    snippets: List[str] = []

    panel_text = _safe_text(
        page,
        [
            "div.F7nice",
            "div.skqShb div.fontBodyMedium.dmRWX",
            "div.skqShb",
        ],
        timeout_ms=timeout_ms,
    )
    if panel_text:
        snippets.append(panel_text)

    for selector in (
        "div.F7nice span[role='img'][aria-label*='review']",
        "span[role='img'][aria-label*='review']",
        "span[aria-label*='reviews']",
        "span.ceNzKf[aria-label]",
    ):
        label = _safe_attr(page, selector, "aria-label", timeout_ms=timeout_ms)
        if label:
            snippets.append(label)

    try:
        panel_payload = page.evaluate(
            """() => {
                const panel = document.querySelector("div.F7nice");
                if (!panel) return "";
                const labels = [...panel.querySelectorAll("[aria-label]")]
                    .map((el) => (el.getAttribute("aria-label") || "").trim())
                    .filter(Boolean)
                    .join(" | ");
                const text = (panel.innerText || "").trim();
                return [labels, text].filter(Boolean).join(" || ");
            }"""
        )
        if panel_payload:
            snippets.append(str(panel_payload))
    except Exception:
        pass

    probe = " ".join([s for s in snippets if s]).strip()
    return {
        "rating": _extract_rating_value(probe),
        "review_count": _extract_review_count_value(probe),
    }


def _extract_hours_hint(body_text: str) -> str:
    if not body_text:
        return ""
    normalized = re.sub(r"[\u202f\u00a0]", " ", body_text)
    patterns = [
        r"\bOpen\s*24\s*hours\b",
        r"\bClosed\s*[·•⋅-]\s*Opens?\s*[^\n|]{1,32}",
        r"\bOpen\s*[·•⋅-]\s*Closes?\s*[^\n|]{1,32}",
        r"\bOpens?\s+[^\n|]{1,20}",
        r"\bCloses?\s+[^\n|]{1,20}",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            value = re.sub(r"\s+", " ", match.group(0)).strip(" .,-")
            if value:
                return value[:64]
    return ""


def _normalize_hours_text(value: str) -> str:
    if not value:
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    text = re.sub(r"^[·•⋅\-–—\s]+", "", text)
    text = re.sub(r",?\s*copy open hours\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r",?\s*copy hours\b", "", text, flags=re.IGNORECASE)
    return text.strip(" ,")


def _extract_preview_place_url(page, timeout_ms: int = 1200) -> str:
    href = _safe_attr(page, "head link[href*='/maps/preview/place']", "href", timeout_ms=timeout_ms)
    if not href:
        return ""
    href = html_lib.unescape(href.strip())
    if not href:
        return ""
    if href.startswith("/"):
        return f"https://www.google.com{href}"
    return href if href.startswith("http") else ""


def _extract_rating_review_from_preview_text(preview_text: str) -> Dict[str, str]:
    if not preview_text:
        return {"rating": "", "review_count": ""}

    payload = preview_text.strip()
    if payload.startswith(")]}'"):
        parts = payload.split("\n", 1)
        payload = parts[1] if len(parts) > 1 else payload[4:]

    rating = ""
    review_count = ""

    for pattern in (
        r'"ratingValue"\s*:\s*"?([0-5](?:\.\d+)?)"?',
        r"\[null,null,null,null,null,null,null,([0-5](?:\.\d+)?)\]",
        r"\b([0-5](?:\.\d+)?)\s+stars?\b",
    ):
        match = re.search(pattern, payload, flags=re.IGNORECASE)
        if match:
            rating = _extract_rating_value(match.group(1))
            if rating:
                break

    for pattern in (
        r'"reviewCount"\s*:\s*"?([\d,]+)"?',
        r'"ratingCount"\s*:\s*"?([\d,]+)"?',
        r"\[null,null,null,null,null,null,null,[0-5](?:\.\d+)?,([\d,]{1,9})\]",
        r"\(([\d,]{1,9})\s*reviews?\)",
        r"([\d,]{1,9})\s+reviews?\b",
    ):
        match = re.search(pattern, payload, flags=re.IGNORECASE)
        if match:
            review_count = _normalize_count_token(match.group(1))
            if review_count:
                break

    return {"rating": rating, "review_count": review_count}


def _extract_rating_review_from_preview(page, fast_mode: bool = True) -> Dict[str, str]:
    preview_url = _extract_preview_place_url(page)
    if not preview_url:
        return {"rating": "", "review_count": ""}
    timeout = 7 if fast_mode else 10
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/plain,application/json,text/html,*/*",
    }
    preview_text = _fetch_url(preview_url, timeout=timeout, headers=headers)
    return _extract_rating_review_from_preview_text(preview_text)


def _extract_business_status(body_text: str, hours_text: str = "") -> str:
    probe = f"{hours_text} {body_text}".lower()
    if "permanently closed" in probe:
        return "Permanently closed"
    if "temporarily closed" in probe:
        return "Temporarily closed"
    if re.search(r"\bopen now\b", probe):
        return "Open"
    if re.search(r"\bclosed\b", probe):
        return "Closed"
    if re.search(r"\bopen\b", probe):
        return "Open"
    return ""


def _extract_open_now(hours_text: str, business_status: str, body_text: str) -> str:
    status_lower = business_status.lower()
    if "temporarily closed" in status_lower:
        return "Temporarily closed"
    if "permanently closed" in status_lower:
        return "Permanently closed"

    probe = f"{hours_text} {body_text}".lower()
    if "open 24 hours" in probe:
        return "Open 24 hours"
    if re.search(r"\bopen\b", probe):
        return "Open"
    if re.search(r"\bclosed\b", probe):
        return "Closed"
    return ""


def _collect_labels_from_keywords(body_text: str, keyword_pairs: List[tuple[str, str]]) -> str:
    lower = body_text.lower()
    seen = set()
    labels: List[str] = []
    for needle, label in keyword_pairs:
        if needle in lower and label not in seen:
            labels.append(label)
            seen.add(label)
    return ", ".join(labels)


def _extract_latest_review_hint(body_text: str) -> str:
    lower = body_text.lower()
    patterns = [
        r"\b\d+\s+(?:seconds?|minutes?|hours?|days?|weeks?|months?|years?)\s+ago\b",
        r"\ban?\s+(?:hour|day|week|month|year)\s+ago\b",
        r"\byesterday\b",
        r"\btoday\b",
    ]
    best: tuple[int, str] | None = None
    for pattern in patterns:
        match = re.search(pattern, lower)
        if match:
            idx = match.start()
            value = match.group(0)
            if best is None or idx < best[0]:
                best = (idx, value)
    if not best:
        return ""
    hint = best[1]
    return hint[:1].upper() + hint[1:]


def _extract_photos_count(body_text: str) -> str:
    match = re.search(r"\b(\d[\d,]*)\s+photos?\b", body_text, flags=re.IGNORECASE)
    return match.group(1).replace(",", "") if match else ""


def _extract_external_links(page) -> Dict[str, str]:
    links: List[str] = []
    seen = set()
    try:
        anchors = page.locator("a[href^='http']")
        count = min(anchors.count(), 120)
        for i in range(count):
            href = anchors.nth(i).get_attribute("href")
            if not href:
                continue
            href_lower = href.lower()
            if "google." in href_lower and "/maps" in href_lower:
                continue
            if href not in seen:
                links.append(href)
                seen.add(href)
    except Exception:
        return {
            "external_links": "",
            "menu_links": "",
            "booking_links": "",
            "order_links": "",
        }

    menu_domains = [
        "zomato",
        "swiggy",
        "ubereats",
        "doordash",
        "grubhub",
        "tripadvisor",
        "restaurantguru",
        "menu",
    ]
    booking_domains = [
        "opentable",
        "resy",
        "booksy",
        "setmore",
        "fresha",
        "calendly",
        "booking.",
    ]
    order_domains = [
        "swiggy",
        "zomato",
        "ubereats",
        "doordash",
        "grubhub",
        "order",
    ]

    def pick(domain_keywords: List[str]) -> str:
        selected = [link for link in links if any(key in link.lower() for key in domain_keywords)]
        return "; ".join(selected[:4])

    return {
        "external_links": "; ".join(links[:8]),
        "menu_links": pick(menu_domains),
        "booking_links": pick(booking_domains),
        "order_links": pick(order_domains),
    }


def _detect_delivery_partners(external_links: Dict[str, str]) -> str:
    candidates = []
    fields = ["order_links", "menu_links", "external_links"]
    partner_domains = {
        "swiggy": "Swiggy",
        "zomato": "Zomato",
        "ubereats": "Uber Eats",
        "doordash": "DoorDash",
        "grubhub": "Grubhub",
        "postmates": "Postmates",
        "deliveroo": "Deliveroo",
        "justeat": "Just Eat",
        "just-eat": "Just Eat",
        "foodpanda": "Foodpanda",
        "seamless": "Seamless",
        "talabat": "Talabat",
        "menulog": "Menulog",
    }

    for field in fields:
        value = external_links.get(field, "") or ""
        for link in value.split(";"):
            link_lower = link.strip().lower()
            for needle, label in partner_domains.items():
                if needle in link_lower:
                    candidates.append(label)

    uniq = []
    seen = set()
    for c in candidates:
        if c not in seen:
            uniq.append(c)
            seen.add(c)
    return ", ".join(uniq)


def _normalize_url(url: str) -> str:
    if not url:
        return ""
    cleaned = url.replace("\u00a0", " ")
    cleaned = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", cleaned)
    cleaned = re.sub(r"[\uE000-\uF8FF]", "", cleaned)
    cleaned = cleaned.strip()
    cleaned = cleaned.replace(" ", "%20")
    if cleaned.startswith("//"):
        cleaned = "https:" + cleaned
    if not re.match(r"^https?://", cleaned, flags=re.IGNORECASE):
        cleaned = "https://" + cleaned
    return cleaned


def _canonicalize_crawl_url(url: str) -> str:
    normalized = _normalize_url(url)
    if not normalized:
        return ""
    try:
        parsed = urlparse(normalized)
        scheme = (parsed.scheme or "https").lower()
        netloc = parsed.netloc.lower()
        path = parsed.path or "/"
        if path != "/":
            path = path.rstrip("/")
        if not path:
            path = "/"

        tracking_keys = {
            "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
            "gclid", "fbclid", "msclkid", "mc_cid", "mc_eid", "ref",
        }
        kept_pairs = [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if k.lower() not in tracking_keys
        ]
        query = urlencode(kept_pairs, doseq=True)
        return urlunparse((scheme, netloc, path, "", query, ""))
    except Exception:
        return normalized


NON_HTML_EXTENSIONS = (
    ".7z", ".avi", ".bmp", ".css", ".csv", ".doc", ".docx", ".eot", ".gif", ".gz",
    ".ico", ".jpeg", ".jpg", ".js", ".json", ".map", ".m4a", ".m4v", ".mov", ".mp3",
    ".mp4", ".mpeg", ".mpg", ".pdf", ".png", ".ppt", ".pptx", ".rar", ".svg", ".tar",
    ".ttf", ".txt", ".wav", ".webm", ".webp", ".woff", ".woff2", ".xls", ".xlsx",
    ".xml", ".zip",
)


PLACEHOLDER_EMAIL_DOMAINS = {
    "domain.com",
    "email.com",
    "example.com",
    "example.org",
    "mystore.com",
}


def _is_probable_html_page_url(url: str) -> bool:
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    path_lower = (parsed.path or "/").lower()
    if path_lower.endswith(NON_HTML_EXTENSIONS):
        return False
    return True


def _unwrap_google_redirect(url: str) -> str:
    normalized = _normalize_url(url)
    if not normalized:
        return ""
    try:
        parsed = urlparse(normalized)
        host = parsed.netloc.lower().split(":")[0]
        if "google." in host and parsed.path.startswith("/url"):
            query = parse_qs(parsed.query)
            target = (query.get("q", [""])[0] or query.get("url", [""])[0]).strip()
            if target:
                return _normalize_url(target)
    except Exception:
        pass
    return normalized


def _extract_domain(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(_normalize_url(url))
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain.split(":")[0]
    except Exception:
        return ""


def _decode_cfemail(encoded: str) -> str:
    if not encoded or len(encoded) < 4 or len(encoded) % 2 != 0:
        return ""
    try:
        key = int(encoded[:2], 16)
    except ValueError:
        return ""
    chars: List[str] = []
    for idx in range(2, len(encoded), 2):
        chunk = encoded[idx : idx + 2]
        try:
            chars.append(chr(int(chunk, 16) ^ key))
        except ValueError:
            return ""
    return "".join(chars)


def _extract_cfemails_from_text(text: str) -> List[str]:
    if not text:
        return []
    matches = re.findall(r'data-cfemail="([0-9a-fA-F]+)"', text)
    matches.extend(re.findall(r'/cdn-cgi/l/email-protection#([0-9a-fA-F]+)', text))
    emails: List[str] = []
    for encoded in matches:
        decoded = _decode_cfemail(encoded)
        if decoded:
            emails.append(decoded)
    return emails


def _decode_unicode_escape_sequences(text: str) -> str:
    if not text or "\\" not in text:
        return text
    normalized = re.sub(r"\\\\u([0-9a-fA-F]{4})", r"\\u\1", text)
    normalized = re.sub(r"\\\\x([0-9a-fA-F]{2})", r"\\x\1", normalized)

    def _replace(match: re.Match[str]) -> str:
        token = match.group(0)
        try:
            if token.lower().startswith("\\u"):
                return chr(int(token[2:], 16))
            if token.lower().startswith("\\x"):
                return chr(int(token[2:], 16))
        except Exception:
            return token
        return token

    normalized = re.sub(r"\\u[0-9a-fA-F]{4}|\\x[0-9a-fA-F]{2}", _replace, normalized)
    return re.sub(r"\\([@.])", r"\1", normalized)


def _decode_base64_candidate(candidate: str) -> str:
    token = str(candidate or "").strip()
    if not token or len(token) < 8 or len(token) > 512:
        return ""
    if not re.fullmatch(r"[A-Za-z0-9+/=]+", token):
        return ""
    padded = token + ("=" * (-len(token) % 4))
    try:
        decoded = base64.b64decode(padded, validate=True)
    except (ValueError, binascii.Error):
        return ""
    if not decoded or len(decoded) > 2048:
        return ""
    text = decoded.decode("utf-8", errors="ignore").strip()
    if not text:
        return ""
    lowered = text.lower()
    if "@" not in lowered and " at " not in lowered and "mailto:" not in lowered:
        return ""
    return text


def _extract_embedded_email_strings(text: str, max_fragments: int = 20) -> List[str]:
    if not text:
        return []

    fragments: List[str] = []
    seen: set[str] = set()

    def _add(candidate: str) -> None:
        value = _decode_unicode_escape_sequences(str(candidate or "").strip())
        if not value:
            return
        lowered = value.lower()
        if "@" not in lowered and " at " not in lowered and "mailto:" not in lowered:
            return
        if value in seen:
            return
        seen.add(value)
        fragments.append(value[:1200])

    for token in re.findall(r"""atob\s*\(\s*['"]([A-Za-z0-9+/=]{8,512})['"]\s*\)""", text, flags=re.IGNORECASE):
        _add(_decode_base64_candidate(token))
        if len(fragments) >= max_fragments:
            return fragments

    for token in re.findall(r"""['"]([A-Za-z0-9+/=]{16,512})['"]""", text):
        _add(_decode_base64_candidate(token))
        if len(fragments) >= max_fragments:
            return fragments

    for args in re.findall(r"""(?:string\.)?fromcharcode\s*\(([^)]{3,400})\)""", text, flags=re.IGNORECASE):
        chars: List[str] = []
        for number in re.findall(r"\b\d{2,3}\b", args):
            try:
                code = int(number)
            except ValueError:
                continue
            if 9 <= code <= 255:
                chars.append(chr(code))
        _add("".join(chars))
        if len(fragments) >= max_fragments:
            return fragments

    join_pattern = re.compile(
        r"""\[((?:\s*['"][^'"]{0,80}['"]\s*,?){2,8})\]\s*\.join\(\s*['"]([^'"]*)['"]\s*\)""",
        flags=re.IGNORECASE,
    )
    for match in join_pattern.finditer(text):
        parts = re.findall(r"""['"]([^'"]{0,80})['"]""", match.group(1))
        separator = match.group(2)
        _add(separator.join(parts))
        if len(fragments) >= max_fragments:
            return fragments

    return fragments


def _extract_emails_from_text(text: str) -> List[str]:
    if not text:
        return []

    cf_emails = _extract_cfemails_from_text(text)

    # Decode HTML entities
    normalized = html_lib.unescape(text)
    normalized = normalized.replace("&commat;", "@").replace("&#64;", "@").replace("&#x40;", "@")
    normalized = normalized.replace("&period;", ".").replace("&#46;", ".").replace("&#x2e;", ".")
    normalized = normalized.replace("&nbsp;", " ").replace("&lt;", "<").replace("&gt;", ">")
    normalized = re.sub(r"[\u200b-\u200f\u2060\ufeff]", "", normalized)
    normalized = _decode_unicode_escape_sequences(normalized)
    embedded_fragments = _extract_embedded_email_strings(normalized)
    if embedded_fragments:
        normalized = f"{normalized}\n" + "\n".join(embedded_fragments)
    
    # Handle obfuscated emails
    normalized = normalized.lower()
    normalized = normalized.replace("\\n", " ").replace("\\r", " ").replace("\\t", " ")
    normalized = re.sub(r'[,;|\t\r\n]', ' ', normalized)
    
    # Handle bracketed obfuscation like "info [at] domain [dot] com"
    normalized = re.sub(
        r"[\[\(\{<]\s*at\s*[\]\)\}>]",
        "@",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"[\[\(\{<]\s*dot\s*[\]\)\}>]",
        ".",
        normalized,
        flags=re.IGNORECASE,
    )
    
    # Handle dash variations like "info - at - domain - dot - com"
    normalized = re.sub(r"\s*-\s*at\s*-\s*", "@", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s*-\s*dot\s*-\s*", ".", normalized, flags=re.IGNORECASE)
    
    # Remove excessive spaces around @ and .
    normalized = re.sub(r"\s*@\s*", "@", normalized)
    normalized = re.sub(r"\s*\.\s*", ".", normalized)
    
    normalized = unquote(normalized)
    raw_normalized = normalized
    normalized = re.sub(r"<[^>]+>", " ", normalized)

    emails = set()
    
    # More aggressive email patterns
    patterns = [
        r"[A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9][A-Za-z0-9.-]*\.[A-Za-z]{2,15}",
        r"[A-Za-z0-9._%+-]+\+[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,15}",
        r"([A-Za-z0-9._-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,15})",  # Catch more variations
    ]

    for cf_email in cf_emails:
        candidate = cf_email.strip().lower()
        if _validate_email(candidate):
            emails.add(candidate)

    js_concat_patterns = [
        re.compile(
            r"""['"]([a-z0-9._%+-]{1,64})['"]\s*\+\s*['"]@['"]\s*\+\s*['"]([a-z0-9.-]+\.[a-z]{2,15})['"]""",
            flags=re.IGNORECASE,
        ),
        re.compile(
            r"""['"]([a-z0-9._%+-]{1,64})['"]\s*\+\s*['"]@['"]\s*\+\s*['"]([a-z0-9.-]{1,253})['"]\s*\+\s*['"]\.['"]\s*\+\s*['"]([a-z]{2,15})['"]""",
            flags=re.IGNORECASE,
        ),
    ]
    for pattern in js_concat_patterns:
        for match in pattern.finditer(normalized):
            if len(match.groups()) == 2:
                candidate = f"{match.group(1).strip().lower()}@{match.group(2).strip().lower()}"
            else:
                candidate = (
                    f"{match.group(1).strip().lower()}@"
                    f"{match.group(2).strip().lower().strip('.')}.{match.group(3).strip().lower()}"
                )
            if _validate_email(candidate):
                emails.add(candidate)

    attribute_pair_patterns = [
        re.compile(
            r"""(?:data-(?:user|name|account|mailbox)|email_user|user)\s*[:=]\s*["']([a-z0-9._%+-]{1,64})["'][^<>]{0,220}?(?:data-(?:domain|host)|email_domain|domain)\s*[:=]\s*["']([a-z0-9.-]+\.[a-z]{2,15})["']""",
            flags=re.IGNORECASE,
        ),
        re.compile(
            r"""(?:data-(?:domain|host)|email_domain|domain)\s*[:=]\s*["']([a-z0-9.-]+\.[a-z]{2,15})["'][^<>]{0,220}?(?:data-(?:user|name|account|mailbox)|email_user|user)\s*[:=]\s*["']([a-z0-9._%+-]{1,64})["']""",
            flags=re.IGNORECASE,
        ),
    ]
    for pattern in attribute_pair_patterns:
        for match in pattern.finditer(raw_normalized):
            if len(match.groups()) != 2:
                continue
            first = match.group(1).strip().lower()
            second = match.group(2).strip().lower()
            candidate = f"{first}@{second}" if "." in second else f"{second}@{first}"
            if _validate_email(candidate):
                emails.add(candidate)

    # Handle explicit plain obfuscation only when "at" and "dot" are both present.
    obfuscated_pattern = re.compile(
        r"\b([a-z0-9][a-z0-9._%+-]{0,63})\s+at\s+([a-z0-9][a-z0-9.-]{0,252})\s+dot\s+([a-z]{2,15}(?:\s+dot\s+[a-z]{2,15})*)\b",
        flags=re.IGNORECASE,
    )
    for match in obfuscated_pattern.finditer(normalized):
        local = match.group(1).strip().lower()
        domain_head = match.group(2).strip().lower().strip(".")
        domain_tail = re.sub(r"\s+dot\s+", ".", match.group(3).strip().lower())
        candidate = f"{local}@{domain_head}.{domain_tail}"
        candidate = re.sub(r"\.+", ".", candidate)
        if _validate_email(candidate):
            emails.add(candidate)

    for pattern in patterns:
        for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
            email_candidate = match.group(0).strip().lower()
            if _validate_email(email_candidate):
                emails.add(email_candidate)

    # Remove escaped-newline artifacts like "ninfo@domain.com" when "info@domain.com" exists.
    cleaned_emails = set(emails)
    for email in list(cleaned_emails):
        local, domain = email.split("@", 1)
        if local.startswith("n") and len(local) > 2:
            without_prefix = f"{local[1:]}@{domain}"
            if without_prefix in cleaned_emails:
                cleaned_emails.discard(email)

    return sorted(cleaned_emails)


def _extract_links_from_html(html: str, include_mailto: bool = False) -> List[str]:
    if not html:
        return []
    links = []
    attr_names = (
        "href",
        "action",
        "formaction",
        "data-href",
        "data-url",
        "data-link",
        "data-action",
        "data-cta",
        "data-cta-href",
    )
    attr_pattern = "|".join(re.escape(name) for name in attr_names)
    for href in re.findall(rf'(?:{attr_pattern})=["\\\']([^"\\\']+)["\\\']', html, flags=re.IGNORECASE):
        candidate = _unwrap_known_redirect(href.strip())
        if not candidate or candidate.lower().startswith(("tel:", "javascript:")):
            continue
        if not include_mailto and candidate.lower().startswith("mailto:"):
            continue
        links.append(candidate)
    if include_mailto:
        for candidate in re.findall(r'mailto:[^"\'\s<>]+', html, flags=re.IGNORECASE):
            links.append(candidate.strip())
    return links


def _extract_internal_priority_urls_from_text(
    current_url: str,
    text: str,
    base_netloc: str,
    max_urls: int = 40,
) -> List[str]:
    if not current_url or not text or not base_netloc:
        return []

    keywords = (
        "contact",
        "about",
        "team",
        "staff",
        "leadership",
        "location",
        "locations",
        "catering",
        "private",
        "reservation",
        "book",
        "menu",
        "support",
        "help",
        "faq",
        "info",
        "legal",
        "privacy",
        "terms",
        "career",
    )
    candidates: List[str] = []
    seen: set[str] = set()
    normalized_text = html_lib.unescape(str(text or "")).replace("\\/", "/")

    for raw in re.findall(r"""['"]((?:https?://|/)[^"'<>]{1,280})['"]""", normalized_text, flags=re.IGNORECASE):
        probe = raw.strip()
        if not probe or probe.lower().startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absolute = _canonicalize_crawl_url(urljoin(current_url, probe))
        if not absolute or absolute in seen:
            continue
        parsed = urlparse(absolute)
        if parsed.netloc.lower() != base_netloc:
            continue
        path_lower = f"{parsed.path} {parsed.query}".lower()
        if parsed.path.lower().startswith(("/api/", "/wp-json/")):
            continue
        if not any(keyword in path_lower for keyword in keywords):
            continue
        if not _is_probable_html_page_url(absolute):
            continue
        seen.add(absolute)
        candidates.append(absolute)
        if len(candidates) >= max_urls:
            break

    return candidates


def _unwrap_known_redirect(url: str) -> str:
    raw_url = str(url or "").strip()
    if raw_url.lower().startswith(("mailto:", "tel:", "javascript:")):
        return raw_url
    normalized = _normalize_url(url)
    if not normalized:
        return ""
    if normalized.lower().startswith(("mailto:", "tel:", "javascript:")):
        return normalized
    try:
        parsed = urlparse(normalized)
        host = (parsed.netloc or "").lower().split(":")[0]
        query = parse_qs(parsed.query)

        if "google." in host and parsed.path.startswith("/url"):
            target = (query.get("q", [""])[0] or query.get("url", [""])[0]).strip()
            if target:
                if target.lower().startswith("mailto:"):
                    return target
                return _normalize_url(target)

        if _domain_matches(host, ["facebook.com", "fb.com", "instagram.com"]):
            if parsed.path.startswith("/l.php"):
                target = (
                    query.get("u", [""])[0]
                    or query.get("url", [""])[0]
                    or query.get("q", [""])[0]
                ).strip()
                if target:
                    target = unquote(target)
                    if target.lower().startswith("mailto:"):
                        return target
                    return _normalize_url(target)
    except Exception:
        return normalized
    return normalized


def _extract_emails_from_links(links: List[str]) -> List[str]:
    emails = set()
    for link in links:
        if not link:
            continue
        candidate_link = _unwrap_known_redirect(link)
        if candidate_link.lower().startswith("mailto:"):
            value = candidate_link.split(":", 1)[1]
            value = value.split("?")[0]
            value = unquote(value)
            value = value.replace("[at]", "@").replace("(at)", "@")
            value = value.replace("[dot]", ".").replace("(dot)", ".")
            for match in re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", value, flags=re.IGNORECASE):
                clean_email = match.strip().lower()
                if _validate_email(clean_email):
                    emails.add(clean_email)
    return sorted(emails)


def _validate_email(email: str) -> bool:
    """Enhanced email validation - more permissive."""
    if not email or "@" not in email:
        return False
    if email.count("@") != 1:
        return False
    
    parts = email.split("@")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return False
    
    local, domain = parts
    
    # Length checks
    if len(local) > 64 or len(domain) > 255 or len(email) > 320:
        return False
    
    # Domain must have at least one dot
    if "." not in domain:
        return False
    
    # Check for invalid patterns
    if local.startswith(".") or local.endswith(".") or ".." in email:
        return False
    
    # Domain validation
    domain_parts = domain.split(".")
    if len(domain_parts) < 2:
        return False
    
    # TLD validation
    tld = domain_parts[-1].lower()
    if len(tld) < 2 or len(tld) > 15:
        return False
        
    # Invalid file extensions
    invalid_extensions = {
        'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'pdf', 'css', 'js', 'ico', 
        'woff', 'woff2', 'ttf', 'eot', 'mp4', 'mp3', 'wav', 'avi', 'mov', 'xml',
        'json', 'zip', 'rar', 'exe', 'msi', 'dmg',
        'this', 'that', 'the'
    }
    if tld in invalid_extensions:
        return False
    
    # Invalid patterns - slightly relaxed
    invalid_patterns = [
        r"^no-?reply", r"^noreply", r"^do-?not-?reply", r"^bounce", r"^mailer-daemon",
        r"^postmaster", r"example\.com", r"localhost", r"@test\.", r"@fake\.",
        r"sentry\.io", r"w3\.org", r"schema\.org",
    ]
    
    for pattern in invalid_patterns:
        if re.search(pattern, email, flags=re.IGNORECASE):
            return False
    
    # Basic character validation
    if not re.match(r"^[A-Za-z0-9._%+.-]+@(?![.-])[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", email):
        return False
    
    return True


def _pick_primary_email(
    website_url: str,
    website_emails: List[str],
    facebook_emails: List[str],
    map_emails: List[str],
) -> str:
    website_emails = [e for e in website_emails if e]
    facebook_emails = [e for e in facebook_emails if e]
    map_emails = [e for e in map_emails if e]

    if facebook_emails:
        return facebook_emails[0]

    if website_emails:
        domain = _extract_domain(website_url)
        if domain:
            for email in website_emails:
                if domain in email:
                    return email
        return website_emails[0]

    if map_emails:
        return map_emails[0]

    return ""


def _combine_emails_priority(
    facebook_emails: List[str],
    website_emails: List[str],
    map_emails: List[str],
) -> List[str]:
    merged: List[str] = []
    seen = set()
    for bucket in (facebook_emails, website_emails, map_emails):
        for email in bucket:
            candidate = str(email or "").strip().lower()
            if not candidate or candidate in seen:
                continue
            if not _validate_email(candidate):
                continue
            seen.add(candidate)
            merged.append(candidate)
    return merged


def _join_email_values(emails: List[str]) -> str:
    return "; ".join(str(email or "").strip() for email in emails if str(email or "").strip())


def _primary_email_source(
    primary_email: str,
    facebook_emails: List[str],
    website_emails: List[str],
    map_emails: List[str],
) -> str:
    if not primary_email:
        return ""
    if primary_email in facebook_emails:
        return "facebook"
    if primary_email in website_emails:
        return "website"
    if primary_email in map_emails:
        return "maps"
    return ""


def _resolve_store_status(business_status: str, open_now: str) -> str:
    status = str(business_status or "").strip().lower()
    open_flag = str(open_now or "").strip().lower()
    if "temporarily closed" in status or "temporarily closed" in open_flag:
        return "Temporarily closed"
    if "permanently closed" in status or "permanently closed" in open_flag:
        return "Permanently closed"
    if "open" in open_flag and "closed" not in open_flag:
        return "Open"
    if "open" in status and "closed" not in status:
        return "Open"
    if "closed" in open_flag or "closed" in status:
        return "Closed"
    return ""


def _filter_emails_for_source(emails: List[str], source: str = "") -> List[str]:
    if not emails:
        return []
    source = (source or "").strip().lower()
    banned_domain_suffixes = {
        ".react", ".graphql", ".jsx", ".tsx", ".css", ".scss", ".sass", ".less",
        ".js", ".json", ".xml", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp",
        ".ico", ".woff", ".woff2", ".ttf", ".eot", ".bundle", ".chunk", ".min",
        ".protocol", ".href", ".hostname", ".pathname", ".search", ".hash",
        ".indexof", ".split", ".replace", ".substring", ".slice", ".length",
    }
    blocked_domain_fragments = {
        "facebook", "fbcdn", "doubleclick", "googlesyndication",
        "google-analytics", "googletagmanager", "gstatic",
        "wixpress", "wixstatic", "parastorage",
    }

    filtered: List[str] = []
    for email in emails:
        if "@" not in email:
            continue
        local, domain = email.split("@", 1)
        domain_lower = domain.lower()
        email_lower = email.lower()
        if domain_lower in PLACEHOLDER_EMAIL_DOMAINS:
            continue
        if email_lower in {
            "user@domain.com",
            "email@email.com",
            "test@test.com",
            "name@example.com",
            "hi@mystore.com",
            "contact@example.com",
        }:
            continue
        if re.search(r"(?:^|[._-])(temp|dummy|sample|placeholder)(?:$|[._-])", local.lower()):
            continue
        if source in {"facebook", "website", "maps"}:
            if any(domain_lower.endswith(sfx) for sfx in banned_domain_suffixes):
                continue
            if any(fragment in domain_lower for fragment in blocked_domain_fragments):
                continue
        filtered.append(email)
    return filtered


def _domain_matches(domain: str, roots: List[str]) -> bool:
    cleaned = (domain or "").lower().split(":")[0]
    if cleaned.startswith("www."):
        cleaned = cleaned[4:]
    for root in roots:
        if cleaned == root or cleaned.endswith(f".{root}"):
            return True
    return False


def _is_valid_facebook_profile_url(url: str) -> bool:
    normalized = _normalize_facebook_url(url)
    if not normalized:
        return False
    parsed = urlparse(normalized)
    if not _domain_matches(parsed.netloc, ["facebook.com", "fb.com", "fb.me"]):
        return False

    path = (parsed.path or "").strip("/").lower()
    if not path:
        return False

    first_segment = path.split("/", 1)[0]
    blocked_roots = {
        "about", "ads", "business", "contact", "dialog", "events", "gaming",
        "groups", "hashtag", "help", "legal", "login", "marketplace", "messages",
        "notifications", "people", "photo.php", "plugins", "policies",
        "policy.php", "privacy", "reel", "search", "settings", "sharer.php",
        "share.php", "support", "terms", "watch",
    }
    if first_segment in blocked_roots:
        return False

    if first_segment == "pages" and len(path.split("/")) < 3:
        return False

    if first_segment.endswith(".php") and first_segment != "profile.php":
        return False

    if first_segment == "profile.php" and "id=" not in parsed.query.lower():
        return False

    return True


def _is_valid_instagram_profile_url(url: str) -> bool:
    normalized = _normalize_url(url)
    if not normalized:
        return False
    parsed = urlparse(normalized)
    if not _domain_matches(parsed.netloc, ["instagram.com", "instagr.am"]):
        return False
    path = (parsed.path or "").strip("/")
    if not path:
        return False
    first_segment = path.split("/", 1)[0].lower()
    blocked = {
        "accounts",
        "about",
        "developer",
        "direct",
        "explore",
        "legal",
        "privacy",
        "reel",
        "reels",
        "stories",
        "terms",
        "tv",
    }
    return first_segment not in blocked


def _is_valid_twitter_profile_url(url: str) -> bool:
    normalized = _normalize_url(url)
    if not normalized:
        return False
    parsed = urlparse(normalized)
    if not _domain_matches(parsed.netloc, ["twitter.com", "x.com", "t.co"]):
        return False
    path = (parsed.path or "").strip("/")
    if not path:
        return False
    first_segment = path.split("/", 1)[0].lower()
    blocked = {
        "explore",
        "hashtag",
        "home",
        "i",
        "intent",
        "messages",
        "notifications",
        "privacy",
        "search",
        "settings",
        "share",
        "tos",
    }
    return first_segment not in blocked


def _is_valid_linkedin_profile_url(url: str) -> bool:
    normalized = _normalize_url(url)
    if not normalized:
        return False
    parsed = urlparse(normalized)
    if not _domain_matches(parsed.netloc, ["linkedin.com", "lnkd.in"]):
        return False
    if _domain_matches(parsed.netloc, ["lnkd.in"]):
        return bool((parsed.path or "").strip("/"))
    path = (parsed.path or "").strip("/")
    if not path:
        return False
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        return False
    first_segment = parts[0].lower()
    return first_segment in {"in", "company", "school", "showcase", "pub"}


def _is_valid_tiktok_profile_url(url: str) -> bool:
    normalized = _normalize_url(url)
    if not normalized:
        return False
    parsed = urlparse(normalized)
    if not _domain_matches(parsed.netloc, ["tiktok.com", "vm.tiktok.com"]):
        return False
    path = (parsed.path or "").strip("/")
    if not path:
        return False
    first_segment = path.split("/", 1)[0].strip()
    return first_segment.startswith("@") and len(first_segment) > 1


def _collect_social_links(urls: List[str]) -> Dict[str, str]:
    """Enhanced social link collection with better pattern matching."""
    buckets = {
        "facebook_url": [],
        "instagram_url": [],
        "twitter_url": [],
        "linkedin_url": [],
        "youtube_url": [],
        "tiktok_url": [],
    }
    
    for url in urls:
        if not url:
            continue

        normalized = _normalize_url(url)
        if not normalized:
            continue
        parsed = urlparse(normalized)
        domain = parsed.netloc.lower()

        if _domain_matches(domain, ["facebook.com", "fb.com", "fb.me"]):
            if _is_valid_facebook_profile_url(normalized):
                buckets["facebook_url"].append(_normalize_facebook_url(normalized))
        elif _domain_matches(domain, ["instagram.com", "instagr.am"]):
            if _is_valid_instagram_profile_url(normalized):
                buckets["instagram_url"].append(normalized)
        elif _domain_matches(domain, ["twitter.com", "x.com", "t.co"]):
            if _is_valid_twitter_profile_url(normalized):
                buckets["twitter_url"].append(normalized)
        elif _domain_matches(domain, ["linkedin.com", "lnkd.in"]):
            if _is_valid_linkedin_profile_url(normalized):
                buckets["linkedin_url"].append(normalized)
        elif _domain_matches(domain, ["youtube.com", "youtu.be"]):
            buckets["youtube_url"].append(normalized)
        elif _domain_matches(domain, ["tiktok.com", "vm.tiktok.com"]):
            if _is_valid_tiktok_profile_url(normalized):
                buckets["tiktok_url"].append(normalized)

    return {key: (vals[0] if vals else "") for key, vals in buckets.items()}


def _normalize_facebook_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(_normalize_url(url))
    netloc = parsed.netloc.lower()
    if not _domain_matches(netloc, ["facebook.com", "fb.com", "fb.me"]):
        return ""
    # Keep profile.php?id=... query when present; otherwise drop query.
    path = parsed.path or "/"
    path_parts = [part for part in path.split("/") if part]
    if path_parts[:1] == ["pg"] and len(path_parts) >= 2:
        path = f"/{path_parts[1]}"
    elif path_parts[:3] == ["pages", "category"] and len(path_parts) >= 4:
        path = f"/{path_parts[-1]}"
    elif path_parts and path_parts[0].lower() not in {"p", "profile.php"} and len(path_parts) >= 2:
        trailing = path_parts[1].lower()
        if trailing in {
            "about",
            "photos",
            "posts",
            "reviews",
            "videos",
            "events",
            "community",
            "mentions",
            "services",
            "contact-info",
            "about_contact_and_basic_info",
            "contact_and_basic_info",
        }:
            path = f"/{path_parts[0]}"
    query = parsed.query if "profile.php" in path else ""
    cleaned = urlunparse(("https", "www.facebook.com", path.rstrip("/"), "", query, ""))
    return cleaned


def _swap_facebook_host(url: str, host: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    scheme = parsed.scheme or "https"
    return urlunparse((scheme, host, parsed.path, "", parsed.query, ""))


def _append_unique(values: List[str], item: str) -> None:
    if item and item not in values:
        values.append(item)


def _build_facebook_variants(normalized: str, *, fast_mode: bool) -> List[str]:
    base = normalized.rstrip("/")
    parsed = urlparse(normalized)
    variants: List[str] = []

    def add(path_suffix: str) -> None:
        if not path_suffix:
            _append_unique(variants, base)
            return
        suffix = path_suffix if path_suffix.startswith("/") else f"/{path_suffix}"
        _append_unique(variants, f"{base}{suffix}")

    def add_sk(value: str) -> None:
        joiner = "&" if parsed.query else "?"
        _append_unique(variants, f"{base}{joiner}sk={value}")

    priority_paths = [
        "about",
        "about/contact_and_basic_info",
        "about_contact_and_basic_info",
        "contact-info",
        "",
        "info",
        "posts",
    ]
    if not fast_mode:
        priority_paths.extend(["services", "reviews", "photos"])

    for path_suffix in priority_paths:
        add(path_suffix)

    add_sk("about")
    add_sk("about_contact_and_basic_info")

    # Prefer the modern/mobile hosts first. mbasic is kept as fallback because
    # many pages no longer expose contact info there.
    hosts = ["m.facebook.com", "www.facebook.com", "mbasic.facebook.com"]
    ordered: List[str] = []
    for url in variants:
        for host in hosts:
            _append_unique(ordered, _swap_facebook_host(url, host))

    if fast_mode:
        # Trim noisy variants for speed, while still covering multiple hosts.
        return ordered[: max(6, min(len(ordered), 10))]
    return ordered


def _extract_facebook_emails(
    facebook_url: str,
    context: Any,
    max_pages: int = 5,
    fast_mode: bool = False,
    collect_all: bool = False,
) -> List[str]:
    normalized = _normalize_facebook_url(facebook_url)
    if not normalized:
        return []

    max_pages = max(1, min(max_pages, 6))
    if fast_mode:
        max_pages = min(max_pages, 3)

    cache_key = (
        f"{normalized}|pages={max_pages}|fast={1 if fast_mode else 0}|all={1 if collect_all else 0}"
    )
    cached = _get_cached_facebook_emails(cache_key)
    if cached is not None:
        logger.info(f"Facebook cache hit for: {normalized} ({len(cached)} emails)")
        return cached

    variants = _build_facebook_variants(normalized, fast_mode=fast_mode)

    nav_timeout_ms = 9000 if fast_mode else 15000
    body_timeout_ms = 2500 if fast_mode else 5000
    fallback_timeout = 6 if fast_mode else 10
    post_nav_delay = (0.35, 0.8) if fast_mode else (1.1, 1.9)
    scroll_rounds = 1 if fast_mode else 3
    see_more_limit = 1 if fast_mode else 3

    emails: set[str] = set()
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    logger.info(f"Starting Facebook email extraction for: {normalized}")

    def _http_fallback() -> None:
        fallback_limit = min(len(variants), max_pages + (2 if fast_mode else 6))
        for link in variants[:fallback_limit]:
            try:
                html = _fetch_url(link, timeout=fallback_timeout, headers=headers)
                if not html:
                    continue
                emails.update(_extract_emails_from_text(html))
                emails.update(_extract_emails_from_links(_extract_links_from_html(html, include_mailto=True)))
                emails.update(_extract_cfemails_from_text(html))
                if fast_mode and emails:
                    break
            except Exception:
                continue

    try:
        # When a sync Playwright context is already provided (the normal scraper path),
        # we can safely reuse it even though sync_playwright runs its own event loop.
        if context is None and _is_running_in_async_loop():
            _http_fallback()
            result = _filter_emails_for_source(sorted(emails), source="facebook")
            if result:
                logger.info(f"Facebook complete: {len(result)} emails - {result}")
            _store_cached_facebook_emails(cache_key, result)
            return result

        if fast_mode:
            _http_fallback()
            if emails and not collect_all:
                result = _filter_emails_for_source(sorted(emails), source="facebook")
                if result:
                    logger.info(f"Facebook complete: {len(result)} emails - {result}")
                _store_cached_facebook_emails(cache_key, result)
                return result

        page = context.new_page()
        route_handler = None
        if fast_mode:
            try:
                route_handler = _install_resource_blocker(
                    page,
                    blocked_resource_types={"image", "media", "font", "stylesheet"},
                )
            except Exception:
                route_handler = None
        try:
            for link in variants[:max_pages]:
                logger.info(f"Checking Facebook page: {link}")
                try:
                    page.goto(link, wait_until="domcontentloaded", timeout=nav_timeout_ms)
                    _sleep(*post_nav_delay)
                except Exception as e:
                    logger.warning(f"Failed to load {link}: {e}")
                    continue

                try:
                    for _ in range(scroll_rounds):
                        page.evaluate("window.scrollBy(0, 900)")
                        _sleep(0.2, 0.45)
                except Exception:
                    pass

                try:
                    buttons = page.locator("div[role='button']:has-text('See more'), button:has-text('See more')")
                    for i in range(min(buttons.count(), see_more_limit)):
                        try:
                            buttons.nth(i).click(timeout=900)
                            _sleep(0.2, 0.4)
                        except Exception:
                            pass
                except Exception:
                    pass

                try:
                    body_text = page.locator("body").inner_text(timeout=body_timeout_ms)
                    extracted_emails = _extract_emails_from_text(body_text)
                    if extracted_emails:
                        logger.info(f"Found {len(extracted_emails)} emails: {extracted_emails}")
                        emails.update(extracted_emails)
                except Exception:
                    pass

                try:
                    html_content = page.content()
                    emails.update(_extract_emails_from_links(_extract_links_from_html(html_content, include_mailto=True)))
                    emails.update(_extract_cfemails_from_text(html_content))
                except Exception:
                    pass

                if not collect_all and fast_mode and emails:
                    break
                if not collect_all and len(emails) >= 2:
                    break
        finally:
            _remove_route_handler(page, route_handler)
            page.close()
    except Exception as e:
        logger.error(f"Playwright Facebook extraction failed: {e}")
        _http_fallback()

    if not emails:
        _http_fallback()

    result = _filter_emails_for_source(sorted(emails), source="facebook")
    if result:
        logger.info(f"Facebook complete: {len(result)} emails - {result}")
    _store_cached_facebook_emails(cache_key, result)
    return result


def _fetch_url(url: str, timeout: int = 12, headers: Dict[str, str] | None = None) -> str:
    if not url:
        return ""
    base_headers = {
        "User-Agent": USER_AGENTS[0],
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
    }
    if headers:
        base_headers.update(headers)
    for attempt_url in [url, url.replace("https://", "http://")]:
        contexts = [None, ssl._create_unverified_context()]
        for ctx in contexts:
            try:
                req = urllib.request.Request(
                    attempt_url,
                    headers=base_headers,
                )
                with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                    content = resp.read(1024 * 1024)
                    return content.decode("utf-8", errors="ignore")
            except urllib.error.URLError as exc:
                reason = getattr(exc, "reason", None)
                should_retry_insecure = ctx is None and isinstance(reason, ssl.SSLCertVerificationError)
                if should_retry_insecure:
                    continue
            except (ValueError, ssl.SSLError):
                if ctx is None:
                    continue
            break
    return ""


def _extract_website_contacts_http_fast(
    website_url: str,
    max_pages: int = 2,
    collect_all: bool = False,
) -> Dict[str, Any]:
    """Fast, HTTP-only website email extraction (no Playwright).

    Designed for speed profiles where email is important but full browser crawling is too slow.
    """
    normalized = _canonicalize_crawl_url(_unwrap_google_redirect(website_url))
    if not normalized:
        return {"emails": [], "socials": {}, "intelligence": _finalize_website_intelligence(_new_website_intelligence())}

    max_pages = max(1, min(int(max_pages or 1), 12 if collect_all else 5))
    cache_key = f"http|{normalized}|pages={max_pages}|all={1 if collect_all else 0}"
    cached = _get_cached_website_contacts(cache_key)
    if cached is not None:
        logger.info(
            f"Website contact cache hit for: {normalized} "
            f"({len(cached.get('emails', []))} emails)"
        )
        return cached
    parsed_base = urlparse(normalized)
    base_netloc = parsed_base.netloc.lower()
    site_domain = _extract_domain(normalized)

    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    # Only a small set of high-yield pages.
    priority_paths = [
        "/",
        "/contact",
        "/contact-us",
        "/contactus",
        "/contact-info",
        "/about",
        "/about-us",
        "/team",
    ]
    if collect_all:
        priority_paths.extend(
            [
                "/staff",
                "/leadership",
                "/locations",
                "/location",
                "/catering",
                "/private-dining",
                "/private-events",
                "/events",
                "/reservations",
                "/book",
                "/menu",
                "/menus",
                "/privacy",
                "/privacy-policy",
                "/terms",
                "/terms-and-conditions",
                "/legal",
                "/faq",
                "/support",
                "/help",
                "/info",
            ]
        )
    candidates: List[str] = []
    for path in priority_paths:
        url = _canonicalize_crawl_url(f"{parsed_base.scheme}://{base_netloc}{path}")
        if url and _is_probable_html_page_url(url) and url not in candidates:
            candidates.append(url)

    # Ensure homepage first
    if normalized in candidates:
        candidates.remove(normalized)
    candidates.insert(0, normalized)
    if collect_all:
        sitemap_links = _extract_sitemap_links(normalized, base_netloc, max_urls=min(40, max_pages * 4))
        for link in sitemap_links:
            canonical_link = _canonicalize_crawl_url(link)
            if canonical_link and canonical_link not in candidates:
                candidates.append(canonical_link)

    emails: set[str] = set()
    socials: Dict[str, str] = {}
    intelligence = _new_website_intelligence()
    visited: set[str] = set()
    queue: List[str] = list(dict.fromkeys(candidates))

    def _has_strong_hit(pages_visited: int) -> bool:
        filtered = _filter_emails_for_source(sorted(emails), source="website")
        if not filtered:
            return False
        if site_domain:
            for e in filtered:
                dom = e.split("@", 1)[1].lower()
                if dom == site_domain or dom.endswith(f".{site_domain}"):
                    return True
        return pages_visited >= 1

    while queue and len(visited) < max_pages:
        current_url = queue.pop(0)
        if current_url in visited:
            continue
        visited.add(current_url)

        html = _fetch_url(current_url, timeout=6, headers=headers)
        if not html:
            continue

        _update_website_intelligence(intelligence, current_url=current_url, html_content=html)
        emails.update(_extract_emails_from_text(html))
        links = _extract_links_from_html(html, include_mailto=True)
        emails.update(_extract_emails_from_links(links))
        emails.update(_extract_cfemails_from_text(html))
        hidden_priority_urls = _extract_internal_priority_urls_from_text(
            current_url,
            html,
            base_netloc,
            max_urls=max_pages * 4,
        )

        # Collect socials from links (including absolute + relative)
        resolved: List[str] = []
        for raw in [*links, *hidden_priority_urls]:
            if not raw or raw.lower().startswith(("mailto:", "tel:", "javascript:")):
                continue
            abs_url = _canonicalize_crawl_url(urljoin(current_url, raw))
            if abs_url:
                resolved.append(abs_url)
                parsed_abs = urlparse(abs_url)
                if parsed_abs.netloc.lower() == base_netloc:
                    _classify_page_url(abs_url, intelligence)
        current_socials = _collect_social_links(resolved)
        for key, val in current_socials.items():
            if val and not socials.get(key):
                socials[key] = val

        # Queue a small number of internal high-yield links discovered on the page.
        if (collect_all or not emails) and len(visited) < max_pages:
            for raw in [*links, *hidden_priority_urls]:
                if not raw or raw.lower().startswith(("mailto:", "tel:", "javascript:")):
                    continue
                abs_url = _canonicalize_crawl_url(urljoin(current_url, raw))
                if not abs_url or abs_url in visited or abs_url in queue:
                    continue
                parsed = urlparse(abs_url)
                if parsed.netloc.lower() != base_netloc:
                    continue
                path_lower = (parsed.path or "").lower()
                if any(
                    k in path_lower
                    for k in (
                        "contact",
                        "about",
                        "team",
                        "staff",
                        "email",
                        "privacy",
                        "terms",
                        "legal",
                        "support",
                        "help",
                        "faq",
                        "info",
                        "locations",
                        "location",
                        "staff",
                        "leadership",
                        "catering",
                        "events",
                        "private",
                        "reservation",
                        "book",
                        "menu",
                    )
                ):
                    if _is_probable_html_page_url(abs_url):
                        queue.insert(0, abs_url)
                if len(queue) >= max_pages * 3:
                    break

        if not collect_all and _has_strong_hit(len(visited)):
            break

    result = {
        "emails": _filter_emails_for_source(sorted(emails), source="website"),
        "socials": socials,
        "intelligence": _finalize_website_intelligence(intelligence),
    }
    _store_cached_website_contacts(cache_key, result)
    return result


def _scrape_emails_selenium(url: str, max_pages: int = 5) -> List[str]:
    """Use Selenium for aggressive email extraction - Like the working scraper"""
    if not SELENIUM_AVAILABLE or not url:
        return []
    
    driver = None
    all_emails = set()
    
    try:
        # Setup Chrome with Selenium
        chrome_options = ChromeOptions()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument(f"--user-agent={random.choice(USER_AGENTS)}")
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(12)
        
        # Parse base URL
        parsed_base = urlparse(url)
        base_netloc = parsed_base.netloc.lower()
        
        # Contact pages to check
        contact_pages = [
            url,
            urljoin(url, "/contact"),
            urljoin(url, "/contact-us"),
            urljoin(url, "/about"),
            urljoin(url, "/about-us"),
            urljoin(url, "/team"),
            urljoin(url, "/reach-us"),
            urljoin(url, "/get-in-touch"),
            urljoin(url, "/connect"),
        ]
        
        pages_checked = 0
        for page_url in contact_pages:
            if pages_checked >= max_pages:
                break
            if len(all_emails) >= 5:  # Stop if we found enough
                break
                
            try:
                driver.get(page_url)
                time.sleep(1.5)
                
                # Aggressive scrolling
                for _ in range(3):
                    driver.execute_script("window.scrollBy(0, 1000);")
                    time.sleep(0.4)
                
                # Click "See more" buttons
                try:
                    see_more_buttons = driver.find_elements(By.XPATH, "//button[contains(translate(text(), 'SEE MORE', 'see more'), 'see more')] | //a[contains(translate(text(), 'SEE MORE', 'see more'), 'see more')]")
                    for btn in see_more_buttons[:5]:
                        try:
                            btn.click()
                            time.sleep(0.5)
                        except:
                            pass
                except:
                    pass
                
                # Extract emails from page source
                page_source = driver.page_source
                extracted = _extract_emails_from_text(page_source)
                all_emails.update(extracted)
                
                pages_checked += 1
                logger.info(f"Selenium: Found {len(extracted)} emails on {page_url}")
                
            except Exception as e:
                logger.warning(f"Selenium: Failed to load {page_url}: {e}")
                continue
        
        logger.info(f"Selenium extraction complete: {len(all_emails)} total emails")
        return sorted(all_emails)
        
    except Exception as e:
        logger.error(f"Selenium email extraction failed: {e}")
        return []
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


def _extract_sitemap_links(base_url: str, base_netloc: str, max_urls: int = 20) -> List[str]:
    if not base_url or not base_netloc:
        return []
    sitemap_candidates = [
        urljoin(base_url, "/sitemap.xml"),
        urljoin(base_url, "/sitemap_index.xml"),
    ]
    keywords = [
        "contact", "about", "team", "staff", "support", "help",
        "privacy", "terms", "legal", "company", "info",
        "customer", "service", "locations", "location",
    ]
    results: List[str] = []
    for sitemap_url in sitemap_candidates:
        xml = _fetch_url(sitemap_url, timeout=8)
        if not xml:
            continue
        for loc in re.findall(r"<loc>([^<]+)</loc>", xml, flags=re.IGNORECASE):
            loc = html_lib.unescape(loc.strip())
            if not loc:
                continue
            normalized = _normalize_url(loc)
            if not normalized:
                continue
            parsed = urlparse(normalized)
            if parsed.netloc.lower() != base_netloc:
                continue
            path_lower = parsed.path.lower()
            if any(keyword in path_lower for keyword in keywords):
                if normalized not in results:
                    results.append(normalized)
            if len(results) >= max_urls:
                break
        if results:
            break
    return results


def _expand_hidden_email_sections(page, base_netloc: str, fast_mode: bool = True) -> int:
    reveal_terms = [
        "contact",
        "email",
        "about",
        "team",
        "staff",
        "leadership",
        "private event",
        "private dining",
        "reservation",
        "reserve",
        "book",
        "catering",
        "faq",
        "help",
        "support",
        "info",
        "see more",
        "show more",
        "read more",
    ]
    try:
        clicked = page.evaluate(
            """({ baseHost, revealTerms, maxClicks }) => {
                const lowerTerms = revealTerms.map(term => String(term || '').toLowerCase());
                const selectors = ['summary', 'button', 'a', '[role="button"]', '[aria-expanded="false"]'];
                const clicked = [];
                const isVisible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style && style.display !== 'none' && style.visibility !== 'hidden' && rect.width >= 2 && rect.height >= 2;
                };

                try {
                    document.querySelectorAll('details').forEach(el => { el.open = true; });
                } catch (e) {}

                const canFollow = (el) => {
                    if (!el || el.tagName !== 'A') return true;
                    const rawHref = (el.getAttribute('href') || '').trim();
                    if (!rawHref || rawHref.startsWith('#') || rawHref.startsWith('/') || rawHref.toLowerCase().startsWith('mailto:') || rawHref.toLowerCase().startsWith('javascript:')) {
                        return true;
                    }
                    try {
                        const target = new URL(el.href, window.location.href);
                        const host = String(target.hostname || '').toLowerCase();
                        return !host || host === baseHost || host.endsWith('.' + baseHost);
                    } catch (e) {
                        return false;
                    }
                };

                for (const selector of selectors) {
                    for (const el of Array.from(document.querySelectorAll(selector))) {
                        if (clicked.length >= maxClicks) {
                            return clicked.length;
                        }
                        if (!isVisible(el) || !canFollow(el)) {
                            continue;
                        }
                        const text = `${el.innerText || el.textContent || ''} ${el.getAttribute('aria-label') || ''} ${el.getAttribute('title') || ''}`.trim().toLowerCase();
                        if (!text || text.length > 160) {
                            continue;
                        }
                        if (!lowerTerms.some(term => text.includes(term))) {
                            continue;
                        }
                        try {
                            el.click();
                            clicked.push(text);
                        } catch (e) {}
                    }
                }
                return clicked.length;
            }""",
            {
                "baseHost": str(base_netloc or "").lower(),
                "revealTerms": reveal_terms,
                "maxClicks": 4 if fast_mode else 10,
            },
        ) or 0
    except Exception:
        return 0

    try:
        click_count = max(0, int(clicked))
    except Exception:
        click_count = 0
    if click_count:
        _sleep(0.15, 0.35) if fast_mode else _sleep(0.35, 0.65)
    return click_count


def _extract_website_contacts(
    website_url: str,
    context: Any,
    max_pages: int = 4,
    fast_mode: bool = True,
    collect_all: bool = False,
) -> Dict[str, Any]:
    normalized = _canonicalize_crawl_url(_unwrap_google_redirect(website_url))
    if not normalized:
        return {"emails": [], "socials": {}, "intelligence": _finalize_website_intelligence(_new_website_intelligence())}

    max_pages = max(1, min(max_pages, 25))
    if fast_mode and not collect_all:
        max_pages = min(max_pages, 4)
    elif fast_mode:
        max_pages = min(max_pages, 12)

    cache_key = (
        f"playwright|{normalized}|pages={max_pages}|fast={1 if fast_mode else 0}|all={1 if collect_all else 0}"
    )
    cached = _get_cached_website_contacts(cache_key)
    if cached is not None:
        logger.info(
            f"Website contact cache hit for: {normalized} "
            f"({len(cached.get('emails', []))} emails)"
        )
        return cached

    emails: set[str] = set()
    socials: Dict[str, str] = {}
    intelligence = _new_website_intelligence()
    visited_urls: set[str] = set()
    to_visit: List[str] = [normalized]
    parsed_base = urlparse(normalized)
    base_netloc = parsed_base.netloc.lower()
    site_domain = _extract_domain(normalized)

    priority_slugs = [
        "contact",
        "contact-us",
        "contactus",
        "contact-info",
        "get-in-touch",
        "about",
        "about-us",
        "aboutus",
        "team",
    ]
    if not fast_mode:
        priority_slugs.extend(["contact-info", "support", "help", "info", "faq"])
    if collect_all:
        priority_slugs.extend([
            "staff",
            "leadership",
            "locations",
            "location",
            "careers",
            "privacy",
            "legal",
            "terms",
            "catering",
            "private-dining",
            "private-events",
            "events",
            "reservations",
            "book",
            "menu",
            "menus",
        ])

    priority_suffixes = ["", "/"] if fast_mode else ["", "/", ".html"]
    priority_paths: List[str] = []
    for slug in priority_slugs:
        slug = slug.strip("/")
        for suffix in priority_suffixes:
            priority_paths.append(f"/{slug}{suffix}")
    priority_paths = list(dict.fromkeys(priority_paths))

    for path in reversed(priority_paths):
        priority_url = _canonicalize_crawl_url(f"{parsed_base.scheme}://{base_netloc}{path}")
        if priority_url and _is_probable_html_page_url(priority_url) and priority_url not in to_visit:
            to_visit.insert(1, priority_url)

    if max_pages >= 6 and (collect_all or not fast_mode):
        sitemap_links = _extract_sitemap_links(normalized, base_netloc, max_urls=min(30, max_pages * 3))
        for link in reversed(sitemap_links):
            canonical_link = _canonicalize_crawl_url(link)
            if canonical_link and _is_probable_html_page_url(canonical_link) and canonical_link not in to_visit:
                to_visit.insert(1, canonical_link)

    crawl_keywords = ["contact", "email", "about", "team", "location", "locations"]
    if not fast_mode:
        crawl_keywords.extend(["support", "help", "info", "faq", "service"])
    if collect_all:
        crawl_keywords.extend([
            "staff",
            "leadership",
            "careers",
            "privacy",
            "legal",
            "terms",
            "catering",
            "events",
            "private",
            "reservation",
            "book",
            "menu",
        ])

    queue_limit = 30 if collect_all and fast_mode else (12 if fast_mode else 25)
    fallback_attempted = False

    def _has_strong_email_hit(pages_visited_count: int) -> bool:
        filtered = _filter_emails_for_source(sorted(emails), source="website")
        if not filtered:
            return False
        if site_domain:
            for email in filtered:
                email_domain = email.split("@", 1)[1].lower()
                if email_domain == site_domain or email_domain.endswith(f".{site_domain}"):
                    return True
        if fast_mode and filtered:
            return pages_visited_count >= 2
        if len(filtered) >= 2:
            return True
        return pages_visited_count >= min(max_pages, 6)

    def _extract_from_html(current_url: str, html_content: str) -> List[str]:
        if not html_content:
            return []

        _update_website_intelligence(intelligence, current_url=current_url, html_content=html_content)
        extracted = _extract_emails_from_text(html_content)
        if extracted:
            emails.update(extracted)

        raw_links = _extract_links_from_html(html_content, include_mailto=True)
        mailto_emails = _extract_emails_from_links(raw_links)
        if mailto_emails:
            emails.update(mailto_emails)
        cf_emails = _extract_cfemails_from_text(html_content)
        if cf_emails:
            emails.update(cf_emails)
        hidden_priority_urls = _extract_internal_priority_urls_from_text(
            current_url,
            html_content,
            base_netloc,
            max_urls=queue_limit,
        )

        extracted_urls: List[str] = []
        for raw in [*raw_links, *hidden_priority_urls]:
            if raw.lower().startswith("mailto:"):
                continue
            normalized_link = _canonicalize_crawl_url(urljoin(current_url, raw))
            if normalized_link and _is_probable_html_page_url(normalized_link):
                extracted_urls.append(normalized_link)
                parsed_link = urlparse(normalized_link)
                if parsed_link.netloc.lower() == base_netloc:
                    _classify_page_url(normalized_link, intelligence)

        current_socials = _collect_social_links(extracted_urls)
        for key, value in current_socials.items():
            if value and not socials.get(key):
                socials[key] = value

        return extracted_urls

    def _queue_internal_links(extracted_urls: List[str], queue: List[str], seen: set[str]) -> None:
        for link in extracted_urls:
            if link in seen or link in queue:
                continue
            if not _is_probable_html_page_url(link):
                continue
            parsed_link = urlparse(link)
            if not parsed_link.netloc or parsed_link.netloc.lower() != base_netloc:
                continue
            _classify_page_url(link, intelligence)
            path_lower = parsed_link.path.lower()
            if any(keyword in path_lower for keyword in crawl_keywords):
                queue.insert(0, link)
            elif len(queue) < queue_limit:
                queue.append(link)

    def _run_http_fallback(seed_urls: List[str], seen_urls: Optional[set[str]] = None) -> None:
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        queue = []
        for url in seed_urls:
            canonical = _canonicalize_crawl_url(url)
            if canonical and _is_probable_html_page_url(canonical) and canonical not in queue:
                queue.append(canonical)
        seen = set(seen_urls or set())
        pages_visited = 0
        fetch_timeout = 8 if fast_mode else 12

        while queue and pages_visited < max_pages:
            current_url = queue.pop(0)
            if current_url in seen:
                continue
            seen.add(current_url)

            html_content = _fetch_url(current_url, timeout=fetch_timeout, headers=headers)
            if not html_content:
                continue
            pages_visited += 1

            extracted_urls = _extract_from_html(current_url, html_content)
            _queue_internal_links(extracted_urls, queue, seen)
            if not collect_all and _has_strong_email_hit(pages_visited):
                break

    if context is None and _is_running_in_async_loop():
        logger.info("Async loop detected during website enrichment; using HTTP fallback")
        fallback_attempted = True
        _run_http_fallback([normalized, *to_visit], seen_urls=visited_urls)
        result = {
            "emails": _filter_emails_for_source(sorted(emails), source="website"),
            "socials": socials,
            "intelligence": _finalize_website_intelligence(intelligence),
        }
        _store_cached_website_contacts(cache_key, result)
        return result

    try:
        page = context.new_page()

        try:
            def _network_response_handler(response) -> None:
                try:
                    response_url = _canonicalize_crawl_url(getattr(response, "url", ""))
                    if not response_url:
                        return
                    parsed_response = urlparse(response_url)
                    if parsed_response.netloc.lower() != base_netloc:
                        return
                    headers = getattr(response, "headers", None) or {}
                    content_type = str(headers.get("content-type", "") or "").lower()
                    if content_type and not any(
                        token in content_type
                        for token in ("html", "json", "javascript", "text", "xml")
                    ):
                        return
                    payload = response.text()
                    if not payload:
                        return
                    payload = payload[: 1024 * 1024]
                    extracted = _extract_emails_from_text(payload)
                    if extracted:
                        emails.update(extracted)
                    link_emails = _extract_emails_from_links(
                        _extract_links_from_html(payload, include_mailto=True)
                    )
                    if link_emails:
                        emails.update(link_emails)
                    hidden_urls = _extract_internal_priority_urls_from_text(
                        response_url,
                        payload,
                        base_netloc,
                        max_urls=10,
                    )
                    _queue_internal_links(hidden_urls, to_visit, visited_urls)
                except Exception:
                    pass

            try:
                page.on("response", _network_response_handler)
            except Exception:
                pass

            pages_visited = 0

            while to_visit and pages_visited < max_pages:
                current_url = to_visit.pop(0)
                if current_url in visited_urls:
                    continue
                visited_urls.add(current_url)

                try:
                    if fast_mode:
                        page.goto(current_url, wait_until="domcontentloaded", timeout=9000)
                        _sleep(0.2, 0.45)
                    else:
                        page.goto(current_url, wait_until="networkidle", timeout=15000)
                        _sleep(0.8, 1.2)
                except Exception:
                    if not fast_mode:
                        try:
                            page.goto(current_url, wait_until="domcontentloaded", timeout=12000)
                            _sleep(0.6, 1.0)
                        except Exception:
                            continue
                    else:
                        continue
                pages_visited += 1

                try:
                    scroll_rounds = 1 if fast_mode else 5
                    for _ in range(scroll_rounds):
                        page.evaluate("window.scrollBy(0, 1100);")
                        _sleep(0.15, 0.35) if fast_mode else _sleep(0.4, 0.6)
                    if not fast_mode:
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                        _sleep(0.5, 0.8)
                except Exception:
                    pass

                try:
                    see_more_selectors = [
                        "button:has-text('See more')",
                        "button:has-text('see more')",
                        "button:has-text('Show more')" if not fast_mode else "",
                        "a:has-text('See more')" if not fast_mode else "",
                        "div[role='button']:has-text('See more')",
                    ]
                    for selector in see_more_selectors:
                        if not selector:
                            continue
                        try:
                            buttons = page.locator(selector)
                            count = min(buttons.count(), 2 if fast_mode else 8)
                            for i in range(count):
                                try:
                                    buttons.nth(i).click(timeout=1000 if fast_mode else 2000)
                                    _sleep(0.15, 0.35) if fast_mode else _sleep(0.3, 0.5)
                                except Exception:
                                    pass
                        except Exception:
                            pass
                except Exception:
                    pass

                _expand_hidden_email_sections(page, base_netloc=base_netloc, fast_mode=fast_mode)

                rendered_url = _canonicalize_crawl_url(page.url) or current_url
                if rendered_url != current_url:
                    parsed_rendered = urlparse(rendered_url)
                    if parsed_rendered.netloc.lower() == base_netloc:
                        visited_urls.add(rendered_url)
                        _classify_page_url(rendered_url, intelligence)

                try:
                    body_text = page.locator("body").inner_text(timeout=2500 if fast_mode else 5000)
                    extracted = _extract_emails_from_text(body_text)
                    emails.update(extracted)
                    logger.info(f"Found {len(extracted)} emails in body text of {rendered_url}")
                except Exception:
                    pass

                try:
                    html_content = page.content()
                    extracted_urls = _extract_from_html(rendered_url, html_content)
                    _queue_internal_links(extracted_urls, to_visit, visited_urls)
                except Exception as e:
                    logger.warning(f"Error extracting from {rendered_url}: {e}")

                try:
                    for frame in page.frames:
                        if frame == page.main_frame:
                            continue
                        frame_url = _canonicalize_crawl_url(getattr(frame, "url", "") or "") or rendered_url
                        parsed_frame = urlparse(frame_url)
                        if parsed_frame.netloc and parsed_frame.netloc.lower() != base_netloc:
                            continue
                        try:
                            frame_body_text = frame.locator("body").inner_text(timeout=1200 if fast_mode else 2500)
                            emails.update(_extract_emails_from_text(frame_body_text))
                        except Exception:
                            pass
                        try:
                            frame_html = frame.content()
                            frame_urls = _extract_from_html(frame_url, frame_html)
                            _queue_internal_links(frame_urls, to_visit, visited_urls)
                        except Exception:
                            pass
                except Exception:
                    pass

                if not collect_all and _has_strong_email_hit(pages_visited):
                    break

        finally:
            page.close()
            logger.info(f"Website scan complete: {len(emails)} total emails found - {sorted(emails)}")

    except Exception as e:
        logger.error(f"Error in website contact extraction: {e}")
        fallback_attempted = True
        _run_http_fallback([normalized, *to_visit], seen_urls=visited_urls)

    if not emails and not fallback_attempted:
        _run_http_fallback([normalized, *to_visit], seen_urls=visited_urls)

    result = {
        "emails": _filter_emails_for_source(sorted(emails), source="website"),
        "socials": socials,
        "intelligence": _finalize_website_intelligence(intelligence),
    }
    _store_cached_website_contacts(cache_key, result)
    return result


def _dismiss_consent_if_present(page) -> None:
    selectors = [
        "button:has-text('Accept all')",
        "button:has-text('I agree')",
        "button:has-text('Agree')",
    ]
    for selector in selectors:
        try:
            loc = page.locator(selector).first
            if loc.count() > 0:
                loc.click(timeout=1000)
                _sleep(0.8, 1.4)
                return
        except Exception:
            continue


def _is_blocked_or_challenged(page) -> bool:
    if _looks_like_block_text(page.url):
        return True
    try:
        body = page.locator("body").inner_text(timeout=2000)
    except Exception:
        return False
    return _looks_like_block_text(body)


def _goto_with_retry(
    page,
    url: str,
    retries: int,
    min_delay: float,
    max_delay: float,
    fast_mode: bool = False,
    max_speed_mode: bool = False,
    email_fast_mode: bool = False,
    adaptive_controller: Optional[AdaptiveAntiBlockController] = None,
) -> None:
    last_exc: Exception | None = None
    # Increased timeouts to handle slow loading
    nav_timeout_ms = 15000 if max_speed_mode else (25000 if email_fast_mode else (45000 if fast_mode else 60000))
    for attempt in range(1, retries + 1):
        post_nav_low = min_delay if not fast_mode else min(0.35, min_delay)
        post_nav_high = max_delay if not fast_mode else min(0.9, max_delay)
        if max_speed_mode:
            post_nav_low = min(post_nav_low, 0.15)
            post_nav_high = min(post_nav_high, 0.35)
        elif email_fast_mode:
            post_nav_low = min(post_nav_low, 0.2)
            post_nav_high = min(post_nav_high, 0.5)
        if adaptive_controller:
            cooldown_wait = adaptive_controller.wait_if_cooling_down(max_wait=20.0 if fast_mode else 30.0)
            if cooldown_wait > 0.15:
                logger.warning(f"Adaptive anti-block cooldown active: {cooldown_wait:.1f}s")
            post_nav_low, post_nav_high = adaptive_controller.scaled_delay_range(post_nav_low, post_nav_high)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=nav_timeout_ms)
            _dismiss_consent_if_present(page)
            # Longer wait after navigation to let content load
            _sleep(post_nav_low * 1.5, post_nav_high * 1.5)
            if _is_blocked_or_challenged(page):
                raise RuntimeError("Blocked/challenged by Google (captcha or unusual traffic)")
            if adaptive_controller:
                adaptive_controller.register_success()
            return
        except Exception as exc:
            last_exc = exc
            logger.warning(f"Navigation attempt {attempt}/{retries} failed: {exc}")
            blocked_error = _is_probable_block_exception(exc)
            adaptive_wait = 0.0
            if adaptive_controller and blocked_error:
                snapshot = adaptive_controller.register_block()
                adaptive_wait = float(snapshot.get("recommended_wait", 0.0))
                logger.warning(
                    "Adaptive anti-block triggered | "
                    f"rate={snapshot.get('block_rate', 0.0):.2f} "
                    f"multiplier={snapshot.get('delay_multiplier', 1.0):.2f} "
                    f"cooldown~{snapshot.get('cooldown_seconds', 0.0):.1f}s"
                )
            if attempt >= retries:
                break
            if max_speed_mode:
                backoff = min(3.0, (2 ** (attempt - 1)) * random.uniform(0.4, 1.0))
            elif email_fast_mode:
                backoff = min(6.0, (2 ** (attempt - 1)) * random.uniform(0.6, 1.6))
            else:
                backoff = min(20.0 if fast_mode else 45.0, (2 ** (attempt - 1)) * random.uniform(1.5, 4.0))
            if adaptive_wait > 0:
                backoff = max(backoff, min(35.0, adaptive_wait))
            time.sleep(backoff)
    logger.error(f"Navigation failed after {retries} attempts: {last_exc}")
    raise RuntimeError(f"Navigation failed after {retries} attempts: {last_exc}")


def _extract_place_details(
    page,
    search_keyword: str,
    search_location: str,
    enrich_socials: bool = False,
    enrich_facebook_emails: bool = False,
    website_max_pages: int = 4,
    fast_mode: bool = True,
    speed_profile: str = "balanced",
    collect_all_emails: bool = False,
    context: Optional[Any] = None,  # Added context parameter
    fallback_review_count: str = "",
    fallback_rating: str = "",
) -> Dict[str, str]:
    profile = str(speed_profile or "").strip().lower()
    max_speed_mode = profile == "max_speed"
    email_fast_mode = profile == "email_fast"
    field_timeout = 320 if max_speed_mode else (450 if email_fast_mode else (650 if fast_mode else 1200))
    body_timeout = 900 if max_speed_mode else (1200 if email_fast_mode else (1500 if fast_mode else 2500))
    website_nav_timeout = 7000 if max_speed_mode else (9000 if email_fast_mode else 15000)
    current_url = page.url
    name_timeout = max(field_timeout, 700)
    name = _extract_place_name(page, current_url=current_url, timeout_ms=name_timeout)
    category = _safe_text(
        page,
        [
            "button[jsaction*='pane.rating.category']",
            "button.DkEaL",
            "div[role='main'] button:has(span)",
        ],
        timeout_ms=field_timeout,
    )
    rating_raw = _safe_text(
        page,
        ["div.F7nice span[aria-hidden='true']", "span.ceNzKf"],
        timeout_ms=field_timeout,
    )
    rating = _extract_rating_value(rating_raw)
    if not rating:
        rating = _extract_rating_value(
            _safe_attr(page, "span.ceNzKf[aria-label]", "aria-label", timeout_ms=field_timeout)
        )
    
    # Enhanced review count extraction with multiple selectors and better timeout
    review_count_raw = _safe_text(
        page,
        [
            "button[jsaction*='pane.reviewChart.moreReviews']",
            "button[jsaction*='pane.reviewChart']",
            "div.F7nice",
            "span[aria-label*='review']",
            "button.HHrUdb",
            "span.RDApEe",
            "div.fontBodyMedium",
        ],
        timeout_ms=max(field_timeout, 1500),
    )
    # Try aria-label attributes if text extraction failed
    if not review_count_raw:
        try:
            # Get all elements with review-related aria-labels
            review_elements = page.locator("[aria-label*='review']").all()
            for elem in review_elements[:5]:  # Check first 5 elements
                try:
                    label = elem.get_attribute("aria-label", timeout=500)
                    if label and "review" in label.lower():
                        review_count_raw = label
                        break
                except:
                    continue
        except:
            pass
    
    # Extract just the number from review count (e.g., "(1,234)" -> "1234")
    review_count = _extract_review_count_value(review_count_raw)
    
    # Log what we extracted for debugging
    logger.info(f"Extracted review_count_raw: '{review_count_raw}' -> review_count: '{review_count}'")

    rating_block = _safe_text(
        page,
        [
            "div.skqShb div.fontBodyMedium.dmRWX",
            "div.skqShb",
        ],
        timeout_ms=field_timeout,
    )
    if not rating:
        rating = _extract_rating_value(rating_block)
        if rating:
            logger.info(f"Found rating from rating_block: {rating}")
    if not review_count:
        review_count = _extract_review_count_value(rating_block)
        if review_count:
            logger.info(f"Found review_count from rating_block: {review_count}")
    if not rating or not review_count:
        panel_meta = _extract_rating_review_from_rating_panel(page, timeout_ms=field_timeout)
        if not rating:
            rating = panel_meta.get("rating", "")
            if rating:
                logger.info(f"Found rating from panel: {rating}")
        if not review_count:
            review_count = panel_meta.get("review_count", "")
            if review_count:
                logger.info(f"Found review_count from panel: {review_count}")

    address = _extract_from_data_item(page, ["address"], timeout_ms=field_timeout)
    phone = _extract_from_data_item(page, ["phone"], timeout_ms=field_timeout)
    plus_code = _extract_from_data_item(page, ["oloc"], timeout_ms=field_timeout)
    website = _safe_attr(
        page,
        "a[data-item-id='authority'], a[data-item-id^='authority'], [data-item-id='authority'] a, [data-item-id^='authority'] a",
        "href",
        timeout_ms=field_timeout,
    )
    if not website:
        website = _extract_from_data_item(page, ["authority"], element_tag="a", timeout_ms=field_timeout)
    website = _unwrap_google_redirect(website)
    located_in = _extract_from_data_item(page, ["locatedin"], timeout_ms=field_timeout)

    hours = _safe_text(
        page,
        [
            "button[jsaction*='pane.openhours']",
            "div[aria-label*='Hours']",
            "span:has-text('Open')",
        ],
        timeout_ms=field_timeout,
    )
    if _is_placeholder_text(hours):
        hours = _safe_attr(
            page,
            "button[jsaction*='pane.openhours']",
            "aria-label",
            timeout_ms=field_timeout,
        )
    hours = _normalize_hours_text(hours)

    description = _safe_text(
        page,
        [
            "div.PYvSYb",
            "div[aria-label='From business'] div",
            "div[jsaction*='pane.about'] span",
        ],
        timeout_ms=field_timeout,
    )
    body_text = _safe_body_text(page, timeout_ms=body_timeout)
    limited_maps_view = "limited view of google maps" in body_text.lower()
    if not rating:
        rating = _extract_rating_value(body_text)
    if not review_count:
        review_count = _extract_review_count_value(body_text)

    # Fallback 1: parse Maps preview payload, which can expose structured rating/review info.
    if not rating or not review_count:
        preview_meta = _extract_rating_review_from_preview(page, fast_mode=fast_mode)
        if not rating:
            rating = preview_meta.get("rating", "")
        if not review_count:
            review_count = preview_meta.get("review_count", "")

    # Fallback 2: when Google serves a limited view, retry lightweight reload(s) and probe again.
    if not review_count and limited_maps_view and not (max_speed_mode or email_fast_mode):
        retry_attempts = 1 if fast_mode else 2
        logger.info(
            "Limited Maps view detected with missing review_count. "
            f"Trying {retry_attempts} retry attempt(s) for: {search_keyword} | {search_location}"
        )
        for _ in range(retry_attempts):
            try:
                page.reload(
                    wait_until="domcontentloaded",
                    timeout=9000 if fast_mode else 15000,
                )
                _sleep(0.2, 0.55) if fast_mode else _sleep(0.5, 1.0)
            except Exception:
                break

            retry_review_raw = _safe_text(
                page,
                [
                    "button[jsaction*='pane.reviewChart.moreReviews'] span",
                    "button[jsaction*='pane.reviewChart'] span",
                    "span[aria-label*='reviews']",
                    "div.F7nice span:nth-child(2)",
                    "button.HHrUdb span",
                    "span.RDApEe",
                ],
                timeout_ms=field_timeout,
            )
            if not retry_review_raw:
                retry_review_raw = _safe_attr(
                    page,
                    "button[jsaction*='pane.reviewChart.moreReviews']",
                    "aria-label",
                    timeout_ms=field_timeout,
                )
            if not retry_review_raw:
                retry_review_raw = _safe_attr(
                    page,
                    "button[jsaction*='pane.reviewChart']",
                    "aria-label",
                    timeout_ms=field_timeout,
                )
            if not retry_review_raw:
                retry_review_raw = _safe_attr(
                    page,
                    "div.F7nice span[role='img'][aria-label*='review']",
                    "aria-label",
                    timeout_ms=field_timeout,
                )
            if not retry_review_raw:
                retry_review_raw = _safe_attr(
                    page,
                    "span[role='img'][aria-label*='review']",
                    "aria-label",
                    timeout_ms=field_timeout,
                )
            if not retry_review_raw:
                retry_review_raw = _safe_text(page, ["div.F7nice"], timeout_ms=field_timeout)

            retry_rating_block = _safe_text(
                page,
                [
                    "div.skqShb div.fontBodyMedium.dmRWX",
                    "div.skqShb",
                ],
                timeout_ms=field_timeout,
            )
            retry_body = _safe_body_text(page, timeout_ms=body_timeout)
            if retry_body:
                body_text = retry_body
                limited_maps_view = "limited view of google maps" in body_text.lower()

            retry_probe = " ".join([retry_review_raw, retry_rating_block, body_text]).strip()
            retry_review = _extract_review_count_value(retry_probe)
            if retry_review:
                review_count = retry_review
            if not rating:
                rating = _extract_rating_value(" ".join([retry_rating_block, body_text]))
            if not rating or not review_count:
                retry_panel_meta = _extract_rating_review_from_rating_panel(page, timeout_ms=field_timeout)
                if not rating:
                    rating = retry_panel_meta.get("rating", "")
                if not review_count:
                    review_count = retry_panel_meta.get("review_count", "")

            if _is_placeholder_text(hours):
                retry_hours = _safe_attr(
                    page,
                    "button[jsaction*='pane.openhours']",
                    "aria-label",
                    timeout_ms=field_timeout,
                )
                retry_hours = _normalize_hours_text(retry_hours)
                if not retry_hours:
                    retry_hours = _extract_hours_hint(body_text)
                if retry_hours:
                    hours = _normalize_hours_text(retry_hours)

            if review_count:
                break

    if not rating and fallback_rating:
        rating = _extract_rating_value(fallback_rating)
    if not review_count and fallback_review_count:
        review_count = _extract_review_count_value(fallback_review_count)

    business_status = _extract_business_status(body_text=body_text, hours_text=hours)
    open_now = _extract_open_now(hours_text=hours, business_status=business_status, body_text=body_text)
    store_status = _resolve_store_status(business_status=business_status, open_now=open_now)
    if _is_placeholder_text(hours):
        hours_fallback = _extract_hours_hint(body_text)
        if hours_fallback:
            hours = hours_fallback
        elif open_now:
            hours = open_now
        elif business_status:
            hours = business_status
    hours = _normalize_hours_text(hours)
    price_level = _extract_price_level(category_text=category, body_text=body_text)

    service_keywords = [
        ("dine-in", "Dine-in"),
        ("takeaway", "Takeaway"),
        ("takeout", "Takeout"),
        ("delivery", "Delivery"),
        ("curbside pickup", "Curbside pickup"),
        ("no-contact delivery", "No-contact delivery"),
        ("online appointments", "Online appointments"),
        ("online estimates", "Online estimates"),
        ("in-store shopping", "In-store shopping"),
        ("in-store pickup", "In-store pickup"),
        ("same-day delivery", "Same-day delivery"),
    ]
    amenities_keywords = [
        ("wheelchair accessible entrance", "Wheelchair access"),
        ("wheelchair accessible parking", "Wheelchair parking"),
        ("wheelchair accessible restroom", "Wheelchair restroom"),
        ("wheelchair accessible seating", "Wheelchair seating"),
        ("free wi-fi", "Free Wi-Fi"),
        ("wi-fi", "Wi-Fi"),
        ("parking", "Parking"),
        ("restroom", "Restroom"),
        ("toilet", "Toilet"),
        ("family friendly", "Family-friendly"),
        ("good for kids", "Good for kids"),
    ]
    payment_keywords = [
        ("credit cards", "Credit cards"),
        ("debit cards", "Debit cards"),
        ("nfc mobile payments", "NFC payments"),
        ("google pay", "Google Pay"),
        ("upi", "UPI"),
        ("cash only", "Cash only"),
    ]
    services = _collect_labels_from_keywords(body_text, service_keywords)
    amenities = _collect_labels_from_keywords(body_text, amenities_keywords)
    payment_options = _collect_labels_from_keywords(body_text, payment_keywords)
    latest_review_hint = _extract_latest_review_hint(body_text)
    has_owner_responses = "Yes" if "response from the owner" in body_text.lower() else "No"
    photos_count = _extract_photos_count(body_text)
    external_links = _extract_external_links(page)
    external_urls = [u.strip() for u in external_links.get("external_links", "").split(";") if u.strip()]
    social_from_maps = _collect_social_links(external_urls)
    website_social_hint = _collect_social_links([website]) if website else {}
    for key, value in website_social_hint.items():
        if value and not social_from_maps.get(key):
            social_from_maps[key] = value
    website_scan_url = website
    if any(website_social_hint.values()):
        logger.info(f"Website URL is a social profile; skipping website crawl: {website}")
        website_scan_url = ""
    delivery_partners = _detect_delivery_partners(external_links)
    map_emails = []
    if not max_speed_mode:
        map_emails = _extract_emails_from_text(body_text)
        try:
            map_emails = sorted({*map_emails, *_extract_emails_from_text(page.content())})
        except Exception:
            map_emails = sorted(map_emails)
    map_emails = _filter_emails_for_source(map_emails, source="maps")

    if max_speed_mode:
        fb_max_pages = 1
    elif email_fast_mode:
        fb_max_pages = 2 if collect_all_emails else 1
    else:
        fb_max_pages = 3 if fast_mode else 5
    facebook_emails: List[str] = []
    facebook_attempted_urls: set[str] = set()

    def _extract_facebook_emails_once(candidate_url: str) -> List[str]:
        facebook_url = _normalize_facebook_url(candidate_url)
        if not facebook_url or facebook_url in facebook_attempted_urls:
            return []
        facebook_attempted_urls.add(facebook_url)
        logger.info(f"Extracting Facebook emails from: {facebook_url}")
        emails = _extract_facebook_emails(
            facebook_url,
            context=context,
            max_pages=fb_max_pages,
            fast_mode=fast_mode,
            collect_all=collect_all_emails,
        )
        logger.info(f"Facebook extraction complete: {len(emails)} emails found")
        return emails

    if enrich_facebook_emails and context and not email_fast_mode:
        facebook_emails = _extract_facebook_emails_once(social_from_maps.get("facebook_url", ""))

    website_emails: List[str] = []
    website_socials: Dict[str, str] = {}
    website_intelligence: Dict[str, Any] = _finalize_website_intelligence(_new_website_intelligence())
    nested_playwright_safe = context is not None and not _is_running_in_async_loop()

    def _should_keep_chasing_emails() -> bool:
        if collect_all_emails:
            return True
        return not (map_emails or website_emails or facebook_emails)

    if enrich_socials and website_scan_url and context:
        logger.info(f"Extracting website emails from: {website_scan_url}")
        pages_to_scan = website_max_pages
        if max_speed_mode:
            pages_to_scan = 1
        elif email_fast_mode:
            pages_to_scan = min(5 if collect_all_emails else 2, website_max_pages)
        elif fast_mode:
            pages_to_scan = min(4, website_max_pages)
        if fast_mode and facebook_emails:
            pages_to_scan = min(2, pages_to_scan)

        if email_fast_mode:
            contacts = _extract_website_contacts_http_fast(
                website_scan_url,
                max_pages=pages_to_scan,
                collect_all=collect_all_emails,
            )
        else:
            contacts = _extract_website_contacts(
                website_scan_url,
                context=context,
                max_pages=pages_to_scan,
                fast_mode=fast_mode,
                collect_all=collect_all_emails,
            )
        website_emails = contacts.get("emails", [])
        website_socials = contacts.get("socials", {})
        website_intelligence = contacts.get("intelligence", website_intelligence)
        scan_label = "HTTP" if email_fast_mode else "Playwright"
        logger.info(f"{scan_label} found {len(website_emails)} emails from website")

        if email_fast_mode and collect_all_emails and nested_playwright_safe:
            try:
                browser_pages_to_scan = min(12, max(pages_to_scan, website_max_pages, 6))
                logger.info(
                    f"Merging Playwright deep crawl for: {website_scan_url} "
                    f"(pages={browser_pages_to_scan}, collect_all={collect_all_emails})"
                )
                browser_contacts = _extract_website_contacts(
                    website_scan_url,
                    context=context,
                    max_pages=browser_pages_to_scan,
                    fast_mode=True,
                    collect_all=True,
                )
                browser_emails = browser_contacts.get("emails", [])
                if browser_emails:
                    merged_emails = sorted(
                        {
                            *[email for email in website_emails if email],
                            *[email for email in browser_emails if email],
                        }
                    )
                    if len(merged_emails) > len(website_emails):
                        logger.info(
                            f"Playwright deep crawl added {len(merged_emails) - len(website_emails)} "
                            f"extra website emails"
                        )
                    website_emails = merged_emails
                browser_socials = browser_contacts.get("socials", {})
                for key, value in browser_socials.items():
                    if value and not website_socials.get(key):
                        website_socials[key] = value
                browser_intelligence = browser_contacts.get("intelligence", website_intelligence)
                website_intelligence = _merge_website_intelligence(website_intelligence, browser_intelligence)
            except Exception:
                pass

        # Playwright fallback: fetch website in-browser if still no emails (using existing context).
        # Useful for JS-heavy sites; keep it lightweight (single page).
        should_escalate_website = (
            not website_emails
            and not max_speed_mode
            and nested_playwright_safe
            and (not email_fast_mode or _should_keep_chasing_emails())
        )
        if should_escalate_website:
            try:
                logger.info(f"HTTP found 0 emails from {website_scan_url}; trying Playwright fallback")
                # Reuse context for fallback page
                wp = context.new_page()
                try:
                    wp.goto(_normalize_url(website_scan_url), wait_until="domcontentloaded", timeout=website_nav_timeout)
                    if max_speed_mode:
                        _sleep(0.15, 0.35)
                    elif email_fast_mode:
                        _sleep(0.25, 0.5)
                    else:
                        _sleep(0.6, 1.3)
                    body_text_site = _safe_body_text(wp, timeout_ms=body_timeout)
                    html_site = wp.content()
                    extracted = set(website_emails)
                    extracted.update(_extract_emails_from_text(body_text_site))
                    extracted.update(_extract_emails_from_text(html_site))
                    extracted.update(
                        _extract_emails_from_links(_extract_links_from_html(html_site, include_mailto=True))
                    )
                    website_emails = sorted(extracted)
                    if website_emails:
                        logger.info(f"Playwright fallback found {len(website_emails)} emails from website")

                    site_links = _extract_links_from_html(html_site)
                    site_socials = _collect_social_links([_normalize_url(u) for u in site_links if u])
                    for key, value in site_socials.items():
                        if value and not website_socials.get(key):
                            website_socials[key] = value

                    fallback_intel_raw = _new_website_intelligence()
                    fallback_url = _normalize_url(website_scan_url)
                    if fallback_url:
                        _update_website_intelligence(
                            fallback_intel_raw,
                            current_url=fallback_url,
                            html_content=html_site,
                        )
                    for link in site_links:
                        normalized_link = _canonicalize_crawl_url(urljoin(fallback_url or "", link))
                        if normalized_link:
                            parsed_link = urlparse(normalized_link)
                            parsed_base = urlparse(fallback_url or "")
                            if parsed_base.netloc and parsed_link.netloc.lower() == parsed_base.netloc.lower():
                                _classify_page_url(normalized_link, fallback_intel_raw)
                    fallback_intel = _finalize_website_intelligence(fallback_intel_raw)
                    website_intelligence = _merge_website_intelligence(website_intelligence, fallback_intel)
                finally:
                    wp.close()
            except Exception:
                pass

            if email_fast_mode and not website_emails:
                try:
                    browser_pages_to_scan = min(5 if collect_all_emails else 3, max(2, pages_to_scan))
                    logger.info(
                        f"Escalating to Playwright contact crawl for: {website_scan_url} "
                        f"(pages={browser_pages_to_scan}, collect_all={collect_all_emails})"
                    )
                    browser_contacts = _extract_website_contacts(
                        website_scan_url,
                        context=context,
                        max_pages=browser_pages_to_scan,
                        fast_mode=True,
                        collect_all=collect_all_emails,
                    )
                    browser_emails = browser_contacts.get("emails", [])
                    if browser_emails:
                        website_emails = browser_emails
                        logger.info(
                            f"Playwright contact crawl found {len(browser_emails)} emails from website"
                        )
                    browser_socials = browser_contacts.get("socials", {})
                    for key, value in browser_socials.items():
                        if value and not website_socials.get(key):
                            website_socials[key] = value
                    browser_intelligence = browser_contacts.get(
                        "intelligence",
                        _finalize_website_intelligence(_new_website_intelligence()),
                    )
                    website_intelligence = _merge_website_intelligence(website_intelligence, browser_intelligence)
                except Exception:
                    pass

    socials = dict(social_from_maps)
    for key, value in website_socials.items():
        if value:
            socials[key] = value

    if enrich_facebook_emails and context and not facebook_emails:
        facebook_url = _normalize_facebook_url(socials.get("facebook_url", ""))
        should_fetch_facebook = True
        if email_fast_mode and not collect_all_emails and (website_emails or map_emails):
            should_fetch_facebook = False
        if facebook_url and should_fetch_facebook:
            facebook_emails = _extract_facebook_emails_once(facebook_url)
        elif facebook_url and email_fast_mode and not should_fetch_facebook:
            logger.info(
                f"Skipping Facebook email extraction for {facebook_url} "
                "because website/maps already found an email in email_fast mode"
            )

    website_emails = _filter_emails_for_source(website_emails, source="website")
    facebook_emails = _filter_emails_for_source(facebook_emails, source="facebook")

    primary_email = _pick_primary_email(
        website_url=website,
        website_emails=website_emails,
        facebook_emails=facebook_emails,
        map_emails=map_emails,
    )
    final_emails = _combine_emails_priority(
        facebook_emails=facebook_emails,
        website_emails=website_emails,
        map_emails=map_emails,
    )
    final_email = "; ".join(final_emails)
    final_email_source = _primary_email_source(
        primary_email=primary_email,
        facebook_emails=facebook_emails,
        website_emails=website_emails,
        map_emails=map_emails,
    )
    email_sources = f"maps:{len(map_emails)}|website:{len(website_emails)}|facebook:{len(facebook_emails)}"

    current_url = page.url
    og_url = _safe_attr(page, "meta[property='og:url']", "content")
    canonical_url = _safe_attr(page, "link[rel='canonical']", "href")
    maps_url = og_url or canonical_url or current_url
    if _looks_like_bad_place_name(name):
        name = _extract_place_name(page, current_url=maps_url, timeout_ms=name_timeout)
    if _looks_like_bad_place_name(name):
        name = _extract_place_name_from_maps_url(maps_url or current_url)
    latitude, longitude = _extract_coords(current_url)
    cid = _extract_cid(current_url)
    feature_id = _extract_feature_id(current_url)
    place_id = _extract_place_id(page, current_url=current_url, feature_id=feature_id)

    # Parse USA address into components
    parsed_address = _parse_usa_address(_clean_field(address))

    return {
        "search_keyword": search_keyword,
        "search_location": search_location,
        "name": _clean_field(name),
        "category": _clean_field(category),
        "rating": _clean_field(rating),
        "review_count": _clean_field(review_count),
        "address": _clean_field(address),
        "street_number": parsed_address["street_number"],
        "street_name": parsed_address["street_name"],
        "city": parsed_address["city"],
        "state": parsed_address["state"],
        "zip_code": parsed_address["zip_code"],
        "phone": _clean_field(phone),
        "website": _clean_field(website),
        "open_now": open_now,
        "business_status": business_status,
        "store_status": store_status,
        "maps_view_mode": "limited" if limited_maps_view else "full",
        "price_level": price_level,
        "plus_code": _clean_field(plus_code),
        "located_in": _clean_field(located_in),
        "hours": _clean_field(hours),
        "description": _clean_field(description),
        "services": services,
        "amenities": amenities,
        "payment_options": payment_options,
        "latest_review_hint": latest_review_hint,
        "has_owner_responses": has_owner_responses,
        "photos_count": photos_count,
        "external_links": external_links["external_links"],
        "menu_links": external_links["menu_links"],
        "booking_links": external_links["booking_links"],
        "order_links": external_links["order_links"],
        "delivery_partners": delivery_partners,
        "emails": primary_email,
        "emails_count": str(len(final_emails)),
        "final_email": final_email,
        "final_email_primary": primary_email,
        "final_email_source": final_email_source,
        "emails_maps": _join_email_values(map_emails),
        "emails_website": _join_email_values(website_emails),
        "emails_facebook": _join_email_values(facebook_emails),
        "email_sources": email_sources,
        "facebook_url": socials.get("facebook_url", ""),
        "instagram_url": socials.get("instagram_url", ""),
        "twitter_url": socials.get("twitter_url", ""),
        "linkedin_url": socials.get("linkedin_url", ""),
        "youtube_url": socials.get("youtube_url", ""),
        "tiktok_url": socials.get("tiktok_url", ""),
        "website_schema_types": "; ".join(website_intelligence.get("schema_types", [])),
        "website_technologies": "; ".join(website_intelligence.get("technologies", [])),
        "website_contact_pages": "; ".join(website_intelligence.get("contact_pages", [])),
        "website_team_pages": "; ".join(website_intelligence.get("team_pages", [])),
        "website_about_pages": "; ".join(website_intelligence.get("about_pages", [])),
        "website_careers_pages": "; ".join(website_intelligence.get("careers_pages", [])),
        "website_pages_scanned": str(website_intelligence.get("pages_scanned", 0)),
        "latitude": latitude,
        "longitude": longitude,
        "feature_id": feature_id,
        "place_id": place_id,
        "cid": cid,
        "google_maps_url": maps_url,
    }


def _collect_place_links(
    page,
    max_results: int,
    fast_mode: bool = True,
    max_speed_mode: bool = False,
    email_fast_mode: bool = False,
    fallback_by_link: Optional[Dict[str, Dict[str, str]]] = None,
    location_guard: Optional[Dict[str, Any]] = None,
    discovery_stats: Optional[Dict[str, int]] = None,
) -> List[str]:
    links: List[str] = []
    seen = set()

    if "/maps/place/" in page.url:
        return [page.url]

    feed = None
    use_page_scroll = False
    for selector in (
        "div[role='feed']",
        "div[role='main'] div[role='feed']",
        "div.m6QErb[role='feed']",
    ):
        try:
            candidate = page.locator(selector).first
            candidate.wait_for(state="visible", timeout=3500)
            feed = candidate
            break
        except PlaywrightTimeoutError:
            continue
        except Exception:
            continue
    if feed is None:
        try:
            if page.locator("a[href*='/maps/place/']").count() == 0:
                return [page.url] if "/maps/place/" in page.url else []
            use_page_scroll = True
        except Exception:
            return [page.url] if "/maps/place/" in page.url else []

    if max_speed_mode:
        max_idle_rounds = 2
    elif email_fast_mode:
        max_idle_rounds = 3
    else:
        max_idle_rounds = 5 if fast_mode else 8
    idle_rounds = 0
    anchor_root = page if use_page_scroll else feed
    while len(links) < max_results and idle_rounds < max_idle_rounds:
        before = len(links)
        anchors = anchor_root.locator("a[href*='/maps/place/']")
        count = anchors.count()
        if max_speed_mode:
            scan_limit = min(count, max_results * 2)
        elif email_fast_mode:
            scan_limit = min(count, max_results * 3)
        else:
            scan_limit = min(count, max_results * (3 if fast_mode else 4))
        for i in range(scan_limit):
            href = anchors.nth(i).get_attribute("href")
            if not href or "/maps/place/" not in href:
                continue
            full_url = href.split("&")[0]
            if full_url.startswith("/"):
                full_url = "https://www.google.com" + full_url

            if discovery_stats is not None:
                discovery_stats["raw_links"] = int(discovery_stats.get("raw_links", 0)) + 1

            card_probe = ""
            try:
                aria = anchors.nth(i).get_attribute("aria-label") or ""
                card_text = anchors.nth(i).evaluate(
                    """el => {
                        const card = el.closest(
                            "div.Nv2PK, div[role='article'], div[jsaction*='mouseover:pane']"
                        );
                        return (card && card.innerText) ? card.innerText : (el.innerText || "");
                    }"""
                ) or ""
                card_probe = " ".join([str(aria), str(card_text)]).strip()
            except Exception:
                card_probe = ""

            if location_guard:
                card_ok, _card_reason = _card_matches_location_guard(card_probe, location_guard)
                if not card_ok:
                    if discovery_stats is not None:
                        discovery_stats["filtered_location"] = int(discovery_stats.get("filtered_location", 0)) + 1
                    continue

            if fallback_by_link is not None and full_url not in fallback_by_link:
                fallback_by_link[full_url] = {
                    "rating": _extract_rating_value(card_probe),
                    "review_count": _extract_review_count_value(card_probe),
                }

            if full_url not in seen:
                seen.add(full_url)
                links.append(full_url)
                if len(links) >= max_results:
                    break

        scroll_distance = random.randint(1000, 2200) if max_speed_mode else random.randint(800, 1800)
        if use_page_scroll:
            page.evaluate("(dist) => window.scrollBy(0, dist)", scroll_distance)
        else:
            feed.evaluate("(el, dist) => el.scrollBy(0, dist)", scroll_distance)
        if max_speed_mode:
            _sleep(0.08, 0.2)
        elif email_fast_mode:
            _sleep(0.12, 0.3)
        else:
            _sleep(0.45, 1.0) if fast_mode else _sleep(1.1, 2.1)
        idle_rounds = idle_rounds + 1 if len(links) == before else 0

    return links[:max_results]


def _build_error_row(
    keyword: str,
    location: str,
    link: str,
    error_message: str,
    resume_key: str = "",
) -> Dict[str, str]:
    row = {
        "search_keyword": keyword,
        "search_location": location,
        "name": "",
        "category": "",
        "rating": "",
        "review_count": "",
        "address": "",
        "street_number": "",
        "street_name": "",
        "city": "",
        "state": "",
        "zip_code": "",
        "phone": "",
        "website": "",
        "open_now": "",
        "business_status": "",
        "store_status": "",
        "price_level": "",
        "plus_code": "",
        "located_in": "",
        "hours": "",
        "description": "",
        "services": "",
        "amenities": "",
        "payment_options": "",
        "latest_review_hint": "",
        "has_owner_responses": "",
        "photos_count": "",
        "external_links": "",
        "menu_links": "",
        "booking_links": "",
        "order_links": "",
        "delivery_partners": "",
        "emails": "",
        "emails_count": "",
        "final_email": "",
        "final_email_primary": "",
        "final_email_source": "",
        "emails_maps": "",
        "emails_website": "",
        "emails_facebook": "",
        "email_sources": "",
        "facebook_url": "",
        "instagram_url": "",
        "twitter_url": "",
        "linkedin_url": "",
        "youtube_url": "",
        "tiktok_url": "",
        "website_schema_types": "",
        "website_technologies": "",
        "website_contact_pages": "",
        "website_team_pages": "",
        "website_about_pages": "",
        "website_careers_pages": "",
        "website_pages_scanned": "0",
        "latitude": "",
        "longitude": "",
        "feature_id": "",
        "place_id": "",
        "cid": "",
        "google_maps_url": link,
        "error": error_message,
    }
    if resume_key:
        row["resume_key"] = resume_key
    return row


def _compact_progress_error(error_message: str, max_length: int = 110) -> str:
    text = str(error_message or "").strip()
    if not text:
        return ""
    for marker in ("Call log:", "Traceback", "Stacktrace"):
        if marker in text:
            text = text.split(marker, 1)[0].strip()
    text = " ".join(text.replace("\r", " ").replace("\n", " ").split())
    if text.lower().startswith("page.goto:"):
        text = text.split(":", 1)[1].strip()
    if len(text) > max_length:
        text = text[: max_length - 3].rstrip() + "..."
    return text


def _progress_label_for_row(row: Dict[str, Any]) -> str:
    name = _clean_place_name(str(row.get("name", "")).strip())
    if name:
        return name
    error_text = _compact_progress_error(str(row.get("error", "")).strip())
    if error_text:
        return f"error - {error_text}"
    return "error"


RETRYABLE_PLACE_ERROR_SNIPPETS = (
    "blocked/challenged by google",
    "captcha",
    "unusual traffic",
    "timed out",
    "timeout",
    "page crashed",
    "navigation failed",
    "worker did not return a result",
    "execution context was destroyed",
    "target page, context or browser has been closed",
    "net::err",
    "connection reset",
    "read operation timed out",
)


def _is_retryable_place_error(error_message: str) -> bool:
    lowered = str(error_message or "").strip().lower()
    if not lowered:
        return False
    return any(snippet in lowered for snippet in RETRYABLE_PLACE_ERROR_SNIPPETS)


def _recover_retryable_place_rows(
    rows: List[Dict[str, str]],
    tasks: List[Dict[str, Any]],
    *,
    headless: bool,
    max_retries: int,
    min_delay: float,
    max_delay: float,
    enrich_socials: bool,
    enrich_facebook_emails: bool,
    website_max_pages: int,
    collect_all_emails: bool,
    progress_callback: ProgressCallback | None,
    row_callback: RowCallback | None,
) -> List[Dict[str, str]]:
    if not rows or not tasks:
        return rows

    retry_indexes: List[int] = []
    retry_targets: List[Dict[str, str]] = []
    for task in tasks:
        idx = int(task.get("index", -1))
        if idx < 0 or idx >= len(rows):
            continue
        row = rows[idx] if isinstance(rows[idx], dict) else {}
        if not _is_retryable_place_error(str(row.get("error", "")).strip()):
            continue
        retry_indexes.append(idx)
        retry_targets.append(
            {
                "google_maps_url": str(task.get("link", "")).strip(),
                "search_keyword": str(task.get("keyword", "")).strip(),
                "search_location": str(task.get("location", "")).strip(),
                "fallback_review_count": str(task.get("fallback_review_count", "")).strip(),
                "fallback_rating": str(task.get("fallback_rating", "")).strip(),
            }
        )

    retry_total = len(retry_targets)
    if retry_total == 0:
        return rows

    recovery_min_delay = max(0.9, min_delay * 2.0)
    recovery_max_delay = max(recovery_min_delay + 0.5, max_delay * 2.5, 1.8)
    recovery_retries = max(2, min(int(max_retries) + 1, 4))

    logger.info(
        f"Recovery pass starting for {retry_total} failed place rows "
        f"(retries={recovery_retries}, delay={recovery_min_delay:.2f}-{recovery_max_delay:.2f}s)"
    )
    if progress_callback:
        progress_callback(
            len(rows),
            len(rows),
            f"Recovery pass: retrying {retry_total} failed stores with a fresh browser session",
        )

    def recovery_progress(progress: int, total: int, message: str) -> None:
        if progress_callback:
            progress_callback(len(rows), len(rows), f"Recovery {progress}/{total}: {message}")

    recovered_rows = scrape_place_links(
        targets=retry_targets,
        headless=headless,
        max_retries=recovery_retries,
        min_delay=recovery_min_delay,
        max_delay=recovery_max_delay,
        enrich_socials=enrich_socials,
        enrich_facebook_emails=enrich_facebook_emails,
        website_max_pages=website_max_pages,
        fast_mode=False,
        speed_profile="balanced",
        collect_all_emails=collect_all_emails,
        max_workers=1,
        adaptive_anti_block=True,
        progress_callback=recovery_progress,
        row_callback=row_callback,
    )

    recovered_ok = 0
    for idx, recovered_row in zip(retry_indexes, recovered_rows):
        if not isinstance(recovered_row, dict):
            continue
        rows[idx] = dict(recovered_row)
        if not str(recovered_row.get("error", "")).strip():
            recovered_ok += 1

    logger.info(f"Recovery pass finished: {recovered_ok}/{retry_total} failed place rows recovered")
    if progress_callback:
        progress_callback(
            len(rows),
            len(rows),
            f"Recovery pass finished: {recovered_ok}/{retry_total} failed stores recovered",
        )
    return rows


PLAYWRIGHT_INSTALL_HINT = (
    "Playwright Chromium browser is missing for this Python environment. "
    "Run `python -m playwright install chromium` using the same interpreter that launches this app."
)


def _is_missing_playwright_browser_error(error: Any) -> bool:
    message = str(error).lower()
    return (
        "executable doesn't exist" in message
        and ("chromium" in message or "headless_shell" in message)
    )


def _with_runtime_hint(error: Any) -> str:
    message = str(error).strip()
    if _is_missing_playwright_browser_error(error):
        hint_lower = PLAYWRIGHT_INSTALL_HINT.lower()
        if hint_lower not in message.lower():
            if message:
                return f"{message}. {PLAYWRIGHT_INSTALL_HINT}"
            return PLAYWRIGHT_INSTALL_HINT
    return message or error.__class__.__name__


def _clamp_max_workers(max_workers: int, total_tasks: int, *, hard_cap: int = 8) -> int:
    try:
        workers = int(max_workers)
    except Exception:
        workers = 1
    workers = max(1, min(workers, int(hard_cap)))
    return min(workers, max(1, int(total_tasks)))


def _partition_round_robin(items: List[Dict[str, Any]], buckets: int) -> List[List[Dict[str, Any]]]:
    parts: List[List[Dict[str, Any]]] = [[] for _ in range(buckets)]
    for i, item in enumerate(items):
        parts[i % buckets].append(item)
    return parts


def _scrape_tasks_parallel(
    tasks: List[Dict[str, Any]],
    *,
    headless: bool,
    max_retries: int,
    min_delay: float,
    max_delay: float,
    enrich_socials: bool,
    enrich_facebook_emails: bool,
    website_max_pages: int,
    fast_mode: bool,
    speed_profile: str,
    collect_all_emails: bool,
    max_workers: int,
    adaptive_controller: Optional[AdaptiveAntiBlockController] = None,
    progress_callback: ProgressCallback | None,
    row_callback: RowCallback | None,
) -> List[Dict[str, str]]:
    total = len(tasks)
    if total == 0:
        return []

    profile = str(speed_profile or "").strip().lower()
    max_speed_mode = fast_mode and profile == "max_speed"
    email_fast_mode = fast_mode and profile == "email_fast"

    workers = _clamp_max_workers(max_workers, total_tasks=total, hard_cap=8)
    if workers <= 1:
        # Caller should use the sequential code path; keep this defensive.
        workers = 1

    task_by_index = {int(t["index"]): t for t in tasks}
    out_q: queue.Queue = queue.Queue()

    def _safe_close(obj: Any, label: str) -> None:
        if not obj:
            return
        try:
            obj.close()
        except Exception as cleanup_err:
            msg = str(cleanup_err).lower()
            if "event loop is closed" in msg or "playwright already stopped" in msg:
                return
            logger.warning(f"Browser cleanup error ({label}): {cleanup_err}")

    def _worker(task_chunk: List[Dict[str, Any]]) -> None:
        processed: set[int] = set()
        guard_cache: Dict[str, Dict[str, Any]] = {}
        browser = None
        context = None
        route_handler = None
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=headless,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                context = browser.new_context(
                    user_agent=random.choice(USER_AGENTS),
                    locale="en-US",
                    viewport={"width": 1366, "height": 768},
                )
                if max_speed_mode or email_fast_mode:
                    route_handler = _install_resource_blocker(context)

                page = context.new_page()
                nav_retries = 1 if fast_mode else min(2, max_retries)

                for t in task_chunk:
                    idx = int(t["index"])
                    processed.add(idx)
                    link = str(t.get("link", "")).strip()
                    keyword = str(t.get("keyword", "")).strip()
                    location = str(t.get("location", "")).strip()
                    resume_key = str(t.get("resume_key", "")).strip()
                    fallback_review_count = str(t.get("fallback_review_count", "")).strip()
                    fallback_rating = str(t.get("fallback_rating", "")).strip()

                    if not link:
                        out_q.put(
                            (
                                idx,
                                _build_error_row(
                                    keyword=keyword,
                                    location=location,
                                    link="",
                                    error_message="Missing google_maps_url",
                                    resume_key=resume_key,
                                ),
                            )
                        )
                        continue

                    try:
                        _goto_with_retry(
                            page,
                            link,
                            retries=nav_retries,
                            min_delay=min_delay,
                            max_delay=max_delay,
                            fast_mode=fast_mode,
                            max_speed_mode=max_speed_mode,
                            email_fast_mode=email_fast_mode,
                            adaptive_controller=adaptive_controller,
                        )
                        row = _extract_place_details(
                            page,
                            search_keyword=keyword,
                            search_location=location,
                            enrich_socials=enrich_socials,
                            enrich_facebook_emails=enrich_facebook_emails,
                            website_max_pages=website_max_pages,
                            fast_mode=fast_mode,
                            speed_profile=speed_profile,
                            collect_all_emails=collect_all_emails,
                            context=context,
                            fallback_review_count=fallback_review_count,
                            fallback_rating=fallback_rating,
                        )
                        maps_url = str(row.get("google_maps_url", "")).strip()
                        if not maps_url or "/maps/place/" not in maps_url:
                            row["google_maps_url"] = link
                        row["error"] = ""
                        if resume_key:
                            row["resume_key"] = resume_key
                        name_value = _clean_place_name(str(row.get("name", "")).strip())
                        if _looks_like_bad_place_name(name_value):
                            fallback_name = _extract_place_name_from_maps_url(
                                str(row.get("google_maps_url", "")).strip() or link
                            )
                            row["name"] = fallback_name or f"Unknown_{idx + 1}"
                        guard = guard_cache.get(location)
                        if guard is None:
                            guard = _build_location_guard(location)
                            guard_cache[location] = guard
                        location_ok, location_error = _row_matches_location_guard(row, guard)
                        if not location_ok:
                            logger.info(
                                "Rejected off-target place result | "
                                f"query='{keyword}' location='{location}' "
                                f"name='{row.get('name', '')}' reason='{location_error}'"
                            )
                            out_q.put(
                                (
                                    idx,
                                    _build_error_row(
                                        keyword=keyword,
                                        location=location,
                                        link=link,
                                        error_message=location_error,
                                        resume_key=resume_key,
                                    ),
                                )
                            )
                            continue
                        out_q.put((idx, row))
                    except Exception as exc:
                        out_q.put(
                            (
                                idx,
                                _build_error_row(
                                    keyword=keyword,
                                    location=location,
                                    link=link,
                                    error_message=_with_runtime_hint(exc),
                                    resume_key=resume_key,
                                ),
                            )
                        )
        except Exception as fatal_exc:
            # Ensure we don't deadlock the collector if Playwright/session died.
            for t in task_chunk:
                idx = int(t["index"])
                if idx in processed:
                    continue
                link = str(t.get("link", "")).strip()
                keyword = str(t.get("keyword", "")).strip()
                location = str(t.get("location", "")).strip()
                resume_key = str(t.get("resume_key", "")).strip()
                out_q.put(
                    (
                        idx,
                        _build_error_row(
                            keyword=keyword,
                            location=location,
                            link=link,
                            error_message=f"Worker fatal error: {_with_runtime_hint(fatal_exc)}",
                            resume_key=resume_key,
                        ),
                    )
                )
        finally:
            _remove_route_handler(context, route_handler)
            _safe_close(context, "context")
            _safe_close(browser, "browser")

    chunks = _partition_round_robin(tasks, workers)
    futures = []
    results: List[Dict[str, str] | None] = [None] * total
    completed = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        for chunk in chunks:
            if chunk:
                futures.append(executor.submit(_worker, chunk))

        while completed < total:
            try:
                idx, row = out_q.get(timeout=0.5)
            except queue.Empty:
                if futures and all(f.done() for f in futures) and out_q.empty():
                    break
                continue

            if 0 <= int(idx) < total:
                results[int(idx)] = dict(row)
            completed += 1

            if row_callback:
                try:
                    row_callback(dict(row), completed, total)
                except Exception:
                    pass
            if progress_callback:
                label = _progress_label_for_row(row)
                progress_callback(completed, total, f"Scraped {completed}/{total}: {label}")

        for f in futures:
            try:
                f.result()
            except Exception as exc:
                logger.warning(f"Worker thread failed: {exc}")

    # Fill missing rows (should be rare; protects caller from hangs / missing output).
    for idx, task in task_by_index.items():
        if 0 <= idx < total and results[idx] is None:
            results[idx] = _build_error_row(
                keyword=str(task.get("keyword", "")).strip(),
                location=str(task.get("location", "")).strip(),
                link=str(task.get("link", "")).strip(),
                error_message="Worker did not return a result for this row",
                resume_key=str(task.get("resume_key", "")).strip(),
            )

    return [r for r in results if r is not None]


def scrape_google_maps(
    keyword: str,
    location: str = "",
    max_results: int = 20,
    headless: bool = True,
    max_retries: int = 2,
    min_delay: float = 0.35,
    max_delay: float = 0.85,
    enrich_socials: bool = False,
    enrich_facebook_emails: bool = False,
    website_max_pages: int = 4,
    fast_mode: bool = True,
    speed_profile: str = "balanced",
    collect_all_emails: bool = False,
    max_workers: int = 1,
    adaptive_anti_block: bool = True,
    progress_callback: ProgressCallback | None = None,
    row_callback: RowCallback | None = None,
    links_only: bool = False,
) -> List[Dict[str, str]]:
    country_hint, geo_hint = _resolve_location_context(location)
    location_guard = _build_location_guard(location)
    search_queries = _build_search_queries(keyword, location)
    profile = str(speed_profile or "").strip().lower()
    max_speed_mode = fast_mode and profile == "max_speed"
    email_fast_mode = fast_mode and profile == "email_fast"

    max_retries = max(1, min(max_retries, 8))
    min_delay = max(0.2, min_delay)
    max_delay = max(min_delay, max_delay)
    if max_speed_mode:
        min_delay = min(min_delay, 0.2)
        max_delay = min(max_delay, 0.45)
        max_retries = 1
    elif email_fast_mode:
        min_delay = min(min_delay, 0.22)
        max_delay = min(max_delay, 0.5)
        max_retries = 1
    elif fast_mode:
        min_delay = min(min_delay, 0.45)
        max_delay = min(max_delay, 0.95)
        max_retries = min(max_retries, 3)
    adaptive_controller = AdaptiveAntiBlockController(enabled=adaptive_anti_block)
    last_exc: Exception | None = None
    last_exc_message = ""

    def _safe_close(obj: Any, label: str) -> None:
        if not obj:
            return
        try:
            obj.close()
        except Exception as cleanup_err:
            msg = str(cleanup_err).lower()
            if "event loop is closed" in msg or "playwright already stopped" in msg:
                return
            logger.warning(f"Browser cleanup error ({label}): {cleanup_err}")

    for attempt in range(1, max_retries + 1):
        results: List[Dict[str, str]] = []
        browser = None
        context = None
        route_handler = None
        place_links: List[str] = []
        place_fallbacks: Dict[str, Dict[str, str]] = {}
        worker_count = 1
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=headless,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                context_kwargs: Dict[str, Any] = {
                    "user_agent": random.choice(USER_AGENTS),
                    "locale": "en-US",
                    "viewport": {"width": 1366, "height": 768},
                }
                if geo_hint:
                    context_kwargs["geolocation"] = {"latitude": geo_hint[0], "longitude": geo_hint[1]}
                    context_kwargs["permissions"] = ["geolocation"]
                    logger.info(
                        f"Using geolocation hint for '{location}': "
                        f"{geo_hint[0]:.4f},{geo_hint[1]:.4f} ({country_hint or 'unknown'})"
                    )
                elif country_hint:
                    logger.info(f"Using country hint for '{location}': {country_hint}")
                context = browser.new_context(**context_kwargs)
                if max_speed_mode or email_fast_mode:
                    route_handler = _install_resource_blocker(context)
                page = context.new_page()

                nav_retries = 1 if fast_mode else 2
                saw_any_candidate_cards = False
                saw_filtered_off_target_cards = False
                for query_index, query in enumerate(search_queries, start=1):
                    search_url = _build_search_url(query, country_hint, geo_hint)
                    candidate_fallbacks: Dict[str, Dict[str, str]] = {}
                    candidate_stats: Dict[str, int] = {"raw_links": 0, "filtered_location": 0}
                    _goto_with_retry(
                        page,
                        search_url,
                        retries=nav_retries,
                        min_delay=min_delay,
                        max_delay=max_delay,
                        fast_mode=fast_mode,
                        max_speed_mode=max_speed_mode,
                        email_fast_mode=email_fast_mode,
                        adaptive_controller=adaptive_controller,
                    )
                    candidate_links = _collect_place_links(
                        page,
                        max_results=max_results,
                        fast_mode=fast_mode,
                        max_speed_mode=max_speed_mode,
                        email_fast_mode=email_fast_mode,
                        fallback_by_link=candidate_fallbacks,
                        location_guard=location_guard,
                        discovery_stats=candidate_stats,
                    )
                    saw_any_candidate_cards = saw_any_candidate_cards or candidate_stats.get("raw_links", 0) > 0
                    saw_filtered_off_target_cards = (
                        saw_filtered_off_target_cards or candidate_stats.get("filtered_location", 0) > 0
                    )
                    if (
                        candidate_links
                        and len(candidate_links) == 1
                        and query_index < len(search_queries)
                        and _looks_like_location_redirect_result(
                            candidate_links[0],
                            keyword=keyword,
                            location=location,
                        )
                    ):
                        logger.info(
                            "Maps query redirected to a generic location result. "
                            f"Trying alternate search phrasing ({query_index}/{len(search_queries)}): {query}"
                        )
                        continue
                    if candidate_links:
                        place_links = candidate_links
                        place_fallbacks = candidate_fallbacks
                        if query_index > 1:
                            logger.info(
                                f"Using alternate Maps query phrasing ({query_index}/{len(search_queries)}): {query}"
                            )
                        break
                    if candidate_stats.get("filtered_location", 0) > 0:
                        logger.info(
                            "Google Maps returned only off-target result cards for this phrasing. "
                            f"Trying alternate phrasing ({query_index}/{len(search_queries)}): {query}"
                        )
                if not place_links:
                    no_results_message = (
                        "No local Google Maps results found for this query"
                        if saw_filtered_off_target_cards or saw_any_candidate_cards
                        else "No Google Maps results found for this query"
                    )
                    logger.info(
                        f"{no_results_message} | keyword='{keyword}' location='{location}'"
                    )
                    if progress_callback:
                        progress_callback(0, max_results, no_results_message)
                    return []

                tasks: List[Dict[str, Any]] = []
                for idx, link in enumerate(place_links):
                    fallback = place_fallbacks.get(link, {})
                    tasks.append(
                        {
                            "index": idx,
                            "link": link,
                            "keyword": keyword,
                            "location": location,
                            "fallback_review_count": str(fallback.get("review_count", "")).strip(),
                            "fallback_rating": str(fallback.get("rating", "")).strip(),
                        }
                    )

                if links_only:
                    unique_targets: List[Dict[str, str]] = []
                    seen_link_keys: set[str] = set()
                    for task in tasks:
                        link = str(task.get("link", "")).strip()
                        if not link:
                            continue
                        key = link.lower()
                        if key in seen_link_keys:
                            continue
                        seen_link_keys.add(key)
                        unique_targets.append(
                            {
                                "google_maps_url": link,
                                "search_keyword": keyword,
                                "search_location": location,
                                "fallback_review_count": str(task.get("fallback_review_count", "")).strip(),
                                "fallback_rating": str(task.get("fallback_rating", "")).strip(),
                            }
                        )
                    return unique_targets

                total = len(tasks)
                worker_count = _clamp_max_workers(max_workers, total_tasks=total, hard_cap=8)
                if worker_count <= 1:
                    for task in tasks:
                        idx = int(task["index"]) + 1
                        link = str(task.get("link", "")).strip()
                        try:
                            _goto_with_retry(
                                page,
                                link,
                                retries=nav_retries,
                                min_delay=min_delay,
                                max_delay=max_delay,
                                fast_mode=fast_mode,
                                max_speed_mode=max_speed_mode,
                                email_fast_mode=email_fast_mode,
                                adaptive_controller=adaptive_controller,
                            )
                            row = _extract_place_details(
                                page,
                                search_keyword=keyword,
                                search_location=location,
                                enrich_socials=enrich_socials,
                                enrich_facebook_emails=enrich_facebook_emails,
                                website_max_pages=website_max_pages,
                                fast_mode=fast_mode,
                                speed_profile=speed_profile,
                                collect_all_emails=collect_all_emails,
                                context=context,  # Pass context
                                fallback_review_count=str(task.get("fallback_review_count", "")).strip(),
                                fallback_rating=str(task.get("fallback_rating", "")).strip(),
                            )
                            maps_url = str(row.get("google_maps_url", "")).strip()
                            if not maps_url or "/maps/place/" not in maps_url:
                                row["google_maps_url"] = link
                            name_value = _clean_place_name(str(row.get("name", "")).strip())
                            if _looks_like_bad_place_name(name_value):
                                fallback_name = _extract_place_name_from_maps_url(
                                    str(row.get("google_maps_url", "")).strip() or link
                                )
                                row["name"] = fallback_name or f"Unknown_{idx}"
                            location_ok, location_error = _row_matches_location_guard(row, location_guard)
                            if not location_ok:
                                logger.info(
                                    "Rejected off-target place result | "
                                    f"query='{keyword}' location='{location}' "
                                    f"name='{row.get('name', '')}' reason='{location_error}'"
                                )
                                error_row = _build_error_row(
                                    keyword=keyword,
                                    location=location,
                                    link=link,
                                    error_message=location_error,
                                )
                                results.append(error_row)
                                if row_callback:
                                    try:
                                        row_callback(dict(error_row), idx, total)
                                    except Exception:
                                        pass
                                if progress_callback:
                                    progress_callback(
                                        idx,
                                        total,
                                        f"Scraped {idx}/{total}: {_progress_label_for_row(error_row)}",
                                    )
                                continue
                            results.append(row)
                            if row_callback:
                                try:
                                    row_callback(dict(row), idx, total)
                                except Exception:
                                    pass
                            if progress_callback:
                                progress_callback(idx, total, f"Scraped {idx}/{total}: {row['name']}")
                        except Exception as exc:
                            error_row = _build_error_row(
                                keyword=keyword,
                                location=location,
                                link=link,
                                error_message=_with_runtime_hint(exc),
                            )
                            results.append(error_row)
                            if row_callback:
                                try:
                                    row_callback(dict(error_row), idx, total)
                                except Exception:
                                    pass
                            if progress_callback:
                                progress_callback(
                                    idx,
                                    total,
                                    f"Scraped {idx}/{total}: {_progress_label_for_row(error_row)}",
                                )

                    return _recover_retryable_place_rows(
                        results,
                        tasks,
                        headless=headless,
                        max_retries=max_retries,
                        min_delay=min_delay,
                        max_delay=max_delay,
                        enrich_socials=enrich_socials,
                        enrich_facebook_emails=enrich_facebook_emails,
                        website_max_pages=website_max_pages,
                        collect_all_emails=collect_all_emails,
                        progress_callback=progress_callback,
                        row_callback=row_callback,
                    )
            if worker_count > 1:
                parallel_rows = _scrape_tasks_parallel(
                    tasks,
                    headless=headless,
                    max_retries=max_retries,
                    min_delay=min_delay,
                    max_delay=max_delay,
                    enrich_socials=enrich_socials,
                    enrich_facebook_emails=enrich_facebook_emails,
                    website_max_pages=website_max_pages,
                    fast_mode=fast_mode,
                    speed_profile=speed_profile,
                    collect_all_emails=collect_all_emails,
                    max_workers=worker_count,
                    adaptive_controller=adaptive_controller,
                    progress_callback=progress_callback,
                    row_callback=row_callback,
                )
                return _recover_retryable_place_rows(
                    parallel_rows,
                    tasks,
                    headless=headless,
                    max_retries=max_retries,
                    min_delay=min_delay,
                    max_delay=max_delay,
                    enrich_socials=enrich_socials,
                    enrich_facebook_emails=enrich_facebook_emails,
                    website_max_pages=website_max_pages,
                    collect_all_emails=collect_all_emails,
                    progress_callback=progress_callback,
                    row_callback=row_callback,
                )
        except Exception as exc:
            last_exc = exc
            last_exc_message = _with_runtime_hint(exc)
            logger.error(f"Scrape attempt {attempt}/{max_retries} failed: {last_exc_message}")
            if progress_callback:
                progress_callback(0, max_results, f"Attempt {attempt}/{max_retries} failed: {last_exc_message}")
            if _is_missing_playwright_browser_error(exc):
                break
            if attempt < max_retries:
                cooloff = min(60.0, (attempt**2) * random.uniform(2.0, 5.0))
                logger.info(f"Retrying after {cooloff:.1f}s cooldown...")
                time.sleep(cooloff)
                continue
            break
        finally:
            # Ensure cleanup
            _remove_route_handler(context, route_handler)
            _safe_close(context, "context")
            _safe_close(browser, "browser")

    final_error = last_exc_message or (str(last_exc) if last_exc else "Unknown scraper error")
    logger.error(f"Scraping failed after {max_retries} attempts: {final_error}")
    raise RuntimeError(f"Failed after {max_retries} attempts: {final_error}")


def scrape_place_links(
    targets: List[Dict[str, str]],
    headless: bool = True,
    max_retries: int = 2,
    min_delay: float = 0.35,
    max_delay: float = 0.85,
    enrich_socials: bool = False,
    enrich_facebook_emails: bool = False,
    website_max_pages: int = 4,
    fast_mode: bool = True,
    speed_profile: str = "balanced",
    collect_all_emails: bool = False,
    max_workers: int = 1,
    adaptive_anti_block: bool = True,
    progress_callback: ProgressCallback | None = None,
    row_callback: RowCallback | None = None,
) -> List[Dict[str, str]]:
    if not targets:
        logger.warning("scrape_place_links called with empty targets")
        return []

    profile = str(speed_profile or "").strip().lower()
    max_speed_mode = fast_mode and profile == "max_speed"
    email_fast_mode = fast_mode and profile == "email_fast"
    max_retries = max(1, min(max_retries, 8))
    min_delay = max(0.2, min_delay)
    max_delay = max(min_delay, max_delay)
    if max_speed_mode:
        min_delay = min(min_delay, 0.2)
        max_delay = min(max_delay, 0.45)
        max_retries = 1
    elif email_fast_mode:
        min_delay = min(min_delay, 0.22)
        max_delay = min(max_delay, 0.5)
        max_retries = 1
    elif fast_mode:
        min_delay = min(min_delay, 0.45)
        max_delay = min(max_delay, 0.95)
        max_retries = min(max_retries, 3)
    adaptive_controller = AdaptiveAntiBlockController(enabled=adaptive_anti_block)
    location_guard_cache: Dict[str, Dict[str, Any]] = {}

    worker_count = _clamp_max_workers(max_workers, total_tasks=len(targets), hard_cap=8)
    if worker_count > 1:
        tasks: List[Dict[str, Any]] = []
        for idx, target in enumerate(targets):
            tasks.append(
                {
                    "index": idx,
                    "link": str(target.get("google_maps_url", "")).strip(),
                    "keyword": str(target.get("search_keyword", "")).strip(),
                    "location": str(target.get("search_location", "")).strip(),
                    "resume_key": str(target.get("resume_key", "")).strip(),
                    "fallback_review_count": str(target.get("fallback_review_count", "")).strip(),
                    "fallback_rating": str(target.get("fallback_rating", "")).strip(),
                }
            )
        return _scrape_tasks_parallel(
            tasks,
            headless=headless,
            max_retries=max_retries,
            min_delay=min_delay,
            max_delay=max_delay,
            enrich_socials=enrich_socials,
            enrich_facebook_emails=enrich_facebook_emails,
            website_max_pages=website_max_pages,
            fast_mode=fast_mode,
            speed_profile=speed_profile,
            collect_all_emails=collect_all_emails,
            max_workers=worker_count,
            adaptive_controller=adaptive_controller,
            progress_callback=progress_callback,
            row_callback=row_callback,
        )
    results: List[Dict[str, str]] = []
    
    browser = None
    context = None
    route_handler = None

    def _safe_close(obj: Any, label: str) -> None:
        if not obj:
            return
        try:
            obj.close()
        except Exception as cleanup_err:
            msg = str(cleanup_err).lower()
            if "event loop is closed" in msg or "playwright already stopped" in msg:
                return
            logger.warning(f"Browser cleanup error in scrape_place_links ({label}): {cleanup_err}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                locale="en-US",
                viewport={"width": 1366, "height": 768},
            )
            if max_speed_mode or email_fast_mode:
                route_handler = _install_resource_blocker(context)
            page = context.new_page()

            total = len(targets)
            logger.info(f"Starting place links scrape: {total} targets")
            
            for idx, target in enumerate(targets, start=1):
                link = str(target.get("google_maps_url", "")).strip()
                keyword = str(target.get("search_keyword", "")).strip()
                location = str(target.get("search_location", "")).strip()
                resume_key = str(target.get("resume_key", "")).strip()
                fallback_review_count = str(target.get("fallback_review_count", "")).strip()
                fallback_rating = str(target.get("fallback_rating", "")).strip()

                if not link:
                    row = _build_error_row(
                        keyword=keyword,
                        location=location,
                        link="",
                        error_message="Missing google_maps_url in checkpoint row",
                        resume_key=resume_key,
                    )
                    results.append(row)
                    if row_callback:
                        row_callback(dict(row), idx, total)
                    if progress_callback:
                        progress_callback(
                            idx,
                            total,
                            f"Scraped {idx}/{total}: {_progress_label_for_row(row)}",
                        )
                    continue

                try:
                    _goto_with_retry(
                        page,
                        link,
                        retries=1 if fast_mode else max_retries,
                        min_delay=min_delay,
                        max_delay=max_delay,
                        fast_mode=fast_mode,
                        max_speed_mode=max_speed_mode,
                        email_fast_mode=email_fast_mode,
                        adaptive_controller=adaptive_controller,
                    )
                    row = _extract_place_details(
                        page,
                        search_keyword=keyword,
                        search_location=location,
                        enrich_socials=enrich_socials,
                        enrich_facebook_emails=enrich_facebook_emails,
                        website_max_pages=website_max_pages,
                        fast_mode=fast_mode,
                        speed_profile=speed_profile,
                        collect_all_emails=collect_all_emails,
                        context=context, # Pass context
                        fallback_review_count=fallback_review_count,
                        fallback_rating=fallback_rating,
                    )
                    maps_url = str(row.get("google_maps_url", "")).strip()
                    if not maps_url or "/maps/place/" not in maps_url:
                        row["google_maps_url"] = link
                    row["error"] = ""
                    if resume_key:
                        row["resume_key"] = resume_key
                    name_value = _clean_place_name(str(row.get("name", "")).strip())
                    if _looks_like_bad_place_name(name_value):
                        fallback_name = _extract_place_name_from_maps_url(
                            str(row.get("google_maps_url", "")).strip() or link
                        )
                        row["name"] = fallback_name or f"Recovered_{idx}"
                    guard = location_guard_cache.get(location)
                    if guard is None:
                        guard = _build_location_guard(location)
                        location_guard_cache[location] = guard
                    location_ok, location_error = _row_matches_location_guard(row, guard)
                    if not location_ok:
                        logger.info(
                            "Rejected off-target recovered place result | "
                            f"query='{keyword}' location='{location}' "
                            f"name='{row.get('name', '')}' reason='{location_error}'"
                        )
                        row = _build_error_row(
                            keyword=keyword,
                            location=location,
                            link=link,
                            error_message=location_error,
                            resume_key=resume_key,
                        )
                    results.append(row)
                    if row_callback:
                        row_callback(dict(row), idx, total)
                    if progress_callback:
                        label = _progress_label_for_row(row)
                        progress_callback(idx, total, f"Scraped {idx}/{total}: {label}")
                except Exception as exc:
                    row = _build_error_row(
                        keyword=keyword,
                        location=location,
                        link=link,
                        error_message=_with_runtime_hint(exc),
                        resume_key=resume_key,
                    )
                    results.append(row)
                    if row_callback:
                        row_callback(dict(row), idx, total)
                    if progress_callback:
                        progress_callback(
                            idx,
                            total,
                            f"Scraped {idx}/{total}: {_progress_label_for_row(row)}",
                        )

            logger.info(f"Place links scrape completed: {len(results)}/{total} processed")
            return results
    except Exception as e:
        logger.error(f"Fatal error in scrape_place_links: {e}", exc_info=True)
        raise
    finally:
        _remove_route_handler(context, route_handler)
        _safe_close(context, "context")
        _safe_close(browser, "browser")
