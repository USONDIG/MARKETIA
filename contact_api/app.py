from fastapi import FastAPI
from pydantic import BaseModel

from search_providers import search_public_web

app = FastAPI(title="MARKETIA Contact API")

class SearchRequest(BaseModel):
    company: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/search")
def search(payload: SearchRequest):
    company = payload.company.strip()
    queries = [
        f'site:linkedin.com/in "{company}" "Infrastructure"',
        f'site:linkedin.com/in "{company}" "DSI"',
        f'site:linkedin.com/in "{company}" "IT Director"',
        f'"{company}" "Infrastructure Director" LinkedIn',
    ]
    rows = []
    for query in queries:
        try:
            results = search_public_web(query, timeout=8, user_agent="MARKETIA-contact-api/0.1", max_results=5)
        except Exception as exc:
            rows.append({"query": query, "error": str(exc), "results": []})
            continue
        rows.append({"query": query, "error": None, "results": results})
    return {"company": company, "queries": rows}
