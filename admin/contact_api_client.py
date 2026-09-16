from __future__ import annotations

import base64
import json
from typing import Any

import requests

DEFAULT_REPO = "USONDIG/MARKETIA"
DEFAULT_DATA_BRANCH = "data/contact-results"
DEFAULT_CONTACTS_PATH = "output/grafana/contacts.json"


def search_contacts(api_url: str, company: str, timeout: int = 30) -> dict:
    base = api_url.rstrip("/")
    response = requests.post(
        f"{base}/search",
        json={"company": company},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def _contact_key(contact: dict[str, Any]) -> str:
    linkedin = str(contact.get("linkedin_url") or "").strip().lower().rstrip("/")
    if linkedin:
        return f"linkedin:{linkedin}"
    company = str(contact.get("company_name") or "").strip().lower()
    name = str(contact.get("full_name") or "").strip().lower()
    title = str(contact.get("job_title") or "").strip().lower()
    return f"fallback:{company}|{name}|{title}"


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def _merge_contact(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Update with new evidence without erasing previously known coordinates."""
    merged = dict(existing)
    for key, value in incoming.items():
        if not _has_value(value):
            continue
        if key.endswith("_status") and str(value).upper() == "NOT_FOUND":
            old_status = str(existing.get(key) or "").strip().upper()
            if old_status and old_status != "NOT_FOUND":
                continue
        merged[key] = value
    return merged


def persist_contacts_to_github(
    github_token: str,
    contacts: list[dict[str, Any]],
    repo: str = DEFAULT_REPO,
    branch: str = DEFAULT_DATA_BRANCH,
    path: str = DEFAULT_CONTACTS_PATH,
    timeout: int = 30,
) -> dict:
    """Merge qualified contacts into a Git-backed JSON feed without touching main."""
    if not github_token:
        raise ValueError("github_token is required")

    api_url = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {github_token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "MARKETIA-Streamlit-contact-persistence/1.1",
    }

    current = requests.get(api_url, headers=headers, params={"ref": branch}, timeout=timeout)
    current.raise_for_status()
    payload = current.json()
    sha = payload["sha"]
    existing_raw = base64.b64decode(payload["content"]).decode("utf-8")
    existing = json.loads(existing_raw or "[]")
    if not isinstance(existing, list):
        raise ValueError("contacts.json must contain a JSON list")

    merged: dict[str, dict[str, Any]] = {}
    for item in existing:
        if isinstance(item, dict):
            merged[_contact_key(item)] = item
    before = len(merged)
    for item in contacts:
        if isinstance(item, dict):
            key = _contact_key(item)
            if key in merged:
                merged[key] = _merge_contact(merged[key], item)
            else:
                merged[key] = item

    output = sorted(
        merged.values(),
        key=lambda row: (
            str(row.get("company_name") or "").casefold(),
            -int(row.get("relevance_score") or 0),
            str(row.get("full_name") or "").casefold(),
        ),
    )
    body = {
        "message": "data: persist qualified contact results",
        "content": base64.b64encode((json.dumps(output, ensure_ascii=False, indent=2) + "\n").encode("utf-8")).decode("ascii"),
        "sha": sha,
        "branch": branch,
    }
    saved = requests.put(api_url, headers=headers, json=body, timeout=timeout)
    saved.raise_for_status()
    result = saved.json()
    return {
        "branch": branch,
        "path": path,
        "before": before,
        "after": len(output),
        "added_or_updated": len(contacts),
        "commit_sha": result.get("commit", {}).get("sha"),
    }
