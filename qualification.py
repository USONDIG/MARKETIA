from __future__ import annotations

from typing import Any

EMPLOYEE_RANGES = {
    "NN": (0, 0, "Non employeuse"),
    "00": (0, 0, "0 salarie"),
    "01": (1, 2, "1-2 salaries"),
    "02": (3, 5, "3-5 salaries"),
    "03": (6, 9, "6-9 salaries"),
    "11": (10, 19, "10-19 salaries"),
    "12": (20, 49, "20-49 salaries"),
    "21": (50, 99, "50-99 salaries"),
    "22": (100, 199, "100-199 salaries"),
    "31": (200, 249, "200-249 salaries"),
    "32": (250, 499, "250-499 salaries"),
    "41": (500, 999, "500-999 salaries"),
    "42": (1000, 1999, "1 000-1 999 salaries"),
    "51": (2000, 4999, "2 000-4 999 salaries"),
    "52": (5000, 9999, "5 000-9 999 salaries"),
    "53": (10000, None, "10 000 salaries et plus"),
}


def employee_info(code: Any) -> dict[str, Any]:
    normalized = str(code or "").strip().upper()
    minimum, maximum, label = EMPLOYEE_RANGES.get(normalized, (None, None, "Inconnu"))
    return {
        "employee_code": normalized or None,
        "employee_min": minimum,
        "employee_max": maximum,
        "employee_range": label,
    }


def naf_division(naf: Any) -> str | None:
    raw = str(naf or "").strip().upper().replace(" ", "")
    if len(raw) < 2:
        return None
    digits = "".join(ch for ch in raw[:3] if ch.isdigit())
    return digits[:2] if len(digits) >= 2 else None


def is_service_naf(naf: Any, config: dict) -> bool:
    division = naf_division(naf)
    if division is None:
        return False
    allowed = {str(value).zfill(2) for value in config.get("qualification", {}).get("allowed_naf_divisions", [])}
    return division in allowed


def qualifies_company(company: Any, config: dict) -> bool:
    settings = config.get("qualification", {})
    if not settings.get("enabled", True):
        return True
    if company is None:
        return not settings.get("require_company_metadata", True)

    country = str(company["headquarters_country"] or "").upper() if "headquarters_country" in company.keys() else ""
    target_hq = {str(c).upper() for c in config.get("target", {}).get("headquarters_country", [])}
    if target_hq and country not in target_hq:
        return False

    if not is_service_naf(company["naf"] if "naf" in company.keys() else None, config):
        return False

    info = employee_info(company["employees"] if "employees" in company.keys() else None)
    minimum_required = int(settings.get("min_employees", 50))
    employee_min = info["employee_min"]
    return employee_min is not None and employee_min >= minimum_required
