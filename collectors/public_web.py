from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
import re
from typing import Any

import requests

from utils import now_iso, stable_id

TAG_RE = re.compile(r"<[^>]+>")


def _headers(config: dict) -> dict[str, str]:
    return {"User-Agent": config["automation"].get("user_agent", "MARKETIA/1.0")}


def _clean_html(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", unescape(TAG_RE.sub(" ", value))).strip()


def collect_jobs(config: dict) -> list[dict[str, Any]]:
    source_cfg = config.get("sources", {}).get("arbeitnow", {})
    if not source_cfg.get("enabled", True):
        return []

    url = source_cfg.get("base_url", "https://www.arbeitnow.com/api/job-board-api")
    timeout = int(config["automation"].get("request_timeout_seconds", 45))
    max_pages = int(source_cfg.get("max_pages", 5))
    events: list[dict[str, Any]] = []

    next_url = url
    for page in range(max_pages):
        response = requests.get(next_url, headers=_headers(config), timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("data") or []
        for row in rows:
            title = row.get("title") or ""
            company = row.get("company_name") or row.get("company") or "Unknown employer"
            description = _clean_html(row.get("description"))
            tags = " ".join(row.get("tags") or [])
            location = row.get("location") or ""
            created = row.get("created_at") or row.get("created_at_timestamp")
            if isinstance(created, (int, float)):
                created = datetime.fromtimestamp(created, tz=timezone.utc).isoformat()
            raw_text = " ".join(filter(None, [title, description, tags, location]))
            events.append({
                "id": stable_id("ARBEITNOW", row),
                "siren": None,
                "company_name": str(company),
                "source": "ARBEITNOW",
                "event_type": "job_posting",
                "event_date": str(created) if created else None,
                "title": str(title),
                "content": raw_text,
                "url": row.get("url") or row.get("job_url"),
                "country": None,
                "raw": row,
                "collected_at": now_iso(),
            })

        links = payload.get("links") or {}
        candidate = links.get("next") if isinstance(links, dict) else None
        if not candidate or candidate == next_url:
            break
        next_url = candidate

    return events


def collect_news(config: dict) -> list[dict[str, Any]]:
    source_cfg = config.get("sources", {}).get("gdelt", {})
    if not source_cfg.get("enabled", True):
        return []

    base = source_cfg.get("base_url", "https://api.gdeltproject.org/api/v2/doc/doc")
    timeout = int(config["automation"].get("request_timeout_seconds", 45))
    timespan = source_cfg.get("timespan", "14d")
    maxrecords = min(int(source_cfg.get("max_records", 250)), 250)
    query = source_cfg.get(
        "query",
        '(server OR servers OR datacenter OR "data center" OR GPU OR HPC OR "private cloud" OR storage OR backup OR virtualisation OR virtualization OR Kubernetes OR "artificial intelligence")',
    )
    params = {
        "query": query,
        "mode": "artlist",
        "maxrecords": maxrecords,
        "format": "json",
        "timespan": timespan,
        "sort": "datedesc",
    }
    response = requests.get(base, params=params, headers=_headers(config), timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    events: list[dict[str, Any]] = []
    for article in payload.get("articles") or []:
        title = article.get("title") or ""
        domain = article.get("domain") or article.get("sourcecountry") or "Web source"
        url = article.get("url")
        events.append({
            "id": stable_id("GDELT", {"url": url, "title": title}),
            "siren": None,
            "company_name": str(domain),
            "source": "GDELT",
            "event_type": "web_news",
            "event_date": article.get("seendate"),
            "title": str(title),
            "content": " ".join(filter(None, [title, article.get("language"), article.get("sourcecountry")])),
            "url": url,
            "country": article.get("sourcecountry"),
            "raw": article,
            "collected_at": now_iso(),
        })
    return events
