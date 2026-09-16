from concurrent.futures import ThreadPoolExecutor, as_completed
import re

from fastapi import FastAPI, Query
from pydantic import BaseModel

from contact_qualifier import qualify_results
from phone_enrichment import enrich_contacts_with_public_phones
from search_providers import search_public_web

app = FastAPI(title="MARKETIA Contact API")


class SearchRequest(BaseModel):
    company: str


_GENERIC_SUFFIXES = {
    "france", "europe", "centre", "center", "distribution", "logistics", "logistique",
    "sas", "sasu", "sa", "se", "holding", "groupe", "group", "international",
}


def _company_alias(company: str) -> str:
    value = re.sub(r"\s+", " ", company.strip())
    first = re.split(r"[,;/|]", value, maxsplit=1)[0].strip()
    tokens = first.split()
    while len(tokens) > 2 and tokens[-1].casefold() in _GENERIC_SUFFIXES:
        tokens.pop()
    # Long legal names are usually less useful than the commercial brand.
    if len(tokens) >= 4:
        tokens = tokens[:2]
    return " ".join(tokens) or value


def _run_query(query: str) -> tuple[str, list[dict], str | None]:
    try:
        results = search_public_web(query, timeout=6, user_agent="MARKETIA-contact-api/0.6", max_results=5)
        return query, results, None
    except Exception as exc:
        return query, [], str(exc)


def _run_search(company: str) -> dict:
    company = company.strip()
    alias = _company_alias(company)
    queries = [
        f'site:linkedin.com/in "{alias}" "Infrastructure"',
        f'site:linkedin.com/in "{alias}" "Cloud"',
        f'site:linkedin.com/in "{alias}" "DSI"',
        f'site:linkedin.com/in "{alias}" "IT Director"',
        f'site:linkedin.com/in "{alias}" "IT procurement"',
        f'site:linkedin.com/in "{alias}" "acheteur IT"',
    ]

    rows_by_query: dict[str, dict] = {}
    total_results = 0
    providers = set()

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(_run_query, query) for query in queries]
        for future in as_completed(futures):
            query, results, error = future.result()
            total_results += len(results)
            providers.update(str(item.get("provider") or "unknown") for item in results)
            rows_by_query[query] = {"query": query, "error": error, "results": results}

    rows = [rows_by_query[q] for q in queries]
    contacts = qualify_results(alias, rows)
    contacts, phone_query_count = enrich_contacts_with_public_phones(contacts, alias)
    phone_count = sum(1 for contact in contacts if contact.get("professional_phone"))
    print(
        f"[contact-api] company={company!r} alias={alias!r} raw_results={total_results} qualified_contacts={len(contacts)} phones={phone_count} phone_queries={phone_query_count} providers={','.join(sorted(providers)) or 'none'}",
        flush=True,
    )
    return {
        "company": company,
        "search_alias": alias,
        "contacts": contacts,
        "qualified_count": len(contacts),
        "raw_result_count": total_results,
        "phone_count": phone_count,
        "phone_query_count": phone_query_count,
        "providers": sorted(providers),
        "queries": rows,
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/search")
def search(payload: SearchRequest):
    return _run_search(payload.company)


@app.get("/search")
def search_get(company: str = Query(..., min_length=2)):
    return _run_search(company)
