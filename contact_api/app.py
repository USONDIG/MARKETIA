from fastapi import FastAPI, Query
from pydantic import BaseModel

from contact_qualifier import qualify_results
from search_providers import search_public_web

app = FastAPI(title="MARKETIA Contact API")


class SearchRequest(BaseModel):
    company: str


def _run_search(company: str) -> dict:
    company = company.strip()
    queries = [
        f'site:linkedin.com/in "{company}" "Infrastructure"',
        f'site:linkedin.com/in "{company}" "Cloud"',
        f'site:linkedin.com/in "{company}" "DSI"',
        f'site:linkedin.com/in "{company}" "IT Director"',
        f'site:linkedin.com/in "{company}" "IT procurement"',
        f'site:linkedin.com/in "{company}" "acheteur IT"',
        f'"{company}" "Infrastructure Director" LinkedIn',
        f'"{company}" "Infrastructure & Cloud Director" LinkedIn',
    ]
    rows = []
    total_results = 0
    providers = set()
    for query in queries:
        try:
            results = search_public_web(query, timeout=8, user_agent="MARKETIA-contact-api/0.4", max_results=5)
        except Exception as exc:
            rows.append({"query": query, "error": str(exc), "results": []})
            continue
        total_results += len(results)
        providers.update(str(item.get("provider") or "unknown") for item in results)
        rows.append({"query": query, "error": None, "results": results})

    contacts = qualify_results(company, rows)
    print(
        f"[contact-api] company={company!r} raw_results={total_results} qualified_contacts={len(contacts)} providers={','.join(sorted(providers)) or 'none'}",
        flush=True,
    )
    return {
        "company": company,
        "contacts": contacts,
        "qualified_count": len(contacts),
        "raw_result_count": total_results,
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
