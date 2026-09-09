from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", value).strip().lower()


def flatten_record(record: dict[str, Any]) -> str:
    return normalize_text(record)


def stable_id(source: str, record: Any) -> str:
    raw = source + "|" + json.dumps(record, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def first_value(record: dict[str, Any], keys: list[str]) -> Any:
    lowered = {str(k).lower(): v for k, v in record.items()}
    for key in keys:
        if key.lower() in lowered and lowered[key.lower()] not in (None, "", []):
            return lowered[key.lower()]
    return None


def extract_siren(text: str | None) -> str | None:
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    if len(digits) == 9:
        return digits
    match = re.search(r"(?<!\d)(\d{9})(?!\d)", text)
    return match.group(1) if match else None


def safe_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]
