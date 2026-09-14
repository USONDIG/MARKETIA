import requests

import contact_search_providers as providers


def test_bing_parser_extracts_result(monkeypatch):
    class Response:
        text = '<li class="b_algo"><h2><a href="https://example.com/jane">Jane Doe - IT Director</a></h2><p>Jane Doe leads IT at Example Corp.</p></li>'

        def raise_for_status(self):
            return None

    monkeypatch.setattr(providers.requests, "get", lambda *args, **kwargs: Response())
    rows = providers.search_bing("Example Corp IT Director", 5, "MARKETIA-test", 5)
    assert rows[0]["url"] == "https://example.com/jane"
    assert "Jane Doe" in rows[0]["title"]
    assert rows[0]["provider"] == "bing"


def test_fallback_to_bing_when_duckduckgo_fails(monkeypatch):
    def fail(*args, **kwargs):
        raise requests.RequestException("blocked")

    monkeypatch.setattr(providers, "search_duckduckgo", fail)
    monkeypatch.setattr(providers, "search_bing", lambda *args, **kwargs: [{"url": "https://example.com", "title": "Example", "snippet": "", "provider": "bing"}])
    rows = providers.search_public_web("Example", 5, "MARKETIA-test", 5)
    assert rows[0]["provider"] == "bing"
