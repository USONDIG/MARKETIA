from __future__ import annotations

import requests


def search_contacts(api_url: str, company: str, timeout: int = 30) -> dict:
    base = api_url.rstrip("/")
    response = requests.post(
        f"{base}/search",
        json={"company": company},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()
