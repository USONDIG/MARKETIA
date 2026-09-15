from fastapi import FastAPI, Query
from pydantic import BaseModel

from search_providers import search_public_web

app = FastAPI(title="MARKETIA Contact API")


class SearchRequest(BaseModel):
    company: str


def _run_search(company: str) -> dict:
    company = company.strip()
    queries = [
        f'site:linkedin.com/in "{company}" "Infrastructure"',
        f'site:linkedin.com/in "{company}" "DSI"',
        f'site:linkedin.com/in "{company}" "IT Director"',
        f'"{company}" "Infrastructure Director" LinkedIn',
    ]
    rows = []
    for query in queries:
        try:
            results = search_public_web(query, timeout=8, user_agent="MARKETIA-contact-api/0.2", max_results=5)
        except Exception as exc:
            rows.append({"query": query, "error": str(exc), "results": []})
            continue
        rows.append({"query": query, "error": None, "results": results})
    return {"company": company, "queries": rows}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/search")
def search(payload: SearchRequest):
    return _run_search(payload.company)


@app.get("/search")
def search_get(company: str = Query(..., min_length=2)):
    return _run_search(company)
