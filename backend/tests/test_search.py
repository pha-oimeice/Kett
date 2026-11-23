import asyncio

import httpx
import pytest

from app.search import SearchError, SearchResult, format_results, web_search


def search(handler, **kwargs):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await web_search("svelte runes", client=client, **kwargs)

    return asyncio.run(run())


def test_cleans_and_limits_results():
    def handler(request):
        assert request.url.path == "/search"
        assert request.url.params["q"] == "svelte runes"
        assert request.url.params["format"] == "json"
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": " Runes ", "url": "https://a.example", "content": "x\n y"},
                    {"title": "Duplicate", "url": "https://a.example", "content": ""},
                    {"title": "No link", "content": "ignored"},
                    {"title": "Script", "url": "javascript:alert(1)"},
                    "not a result",
                    {"title": None, "url": "https://b.example", "content": "z" * 500},
                    {"title": "Third", "url": "https://c.example", "content": None},
                ]
            },
        )

    results = search(handler, max_results=2)
    assert results[0] == SearchResult("Runes", "https://a.example", "x y")
    assert results[1].url == "https://b.example"
    assert results[1].title == ""
    assert len(results[1].snippet) == 300 and results[1].snippet.endswith("…")
    assert len(results) == 2


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(403),
        httpx.Response(200, text="<html>"),
        httpx.Response(200, json={"results": None}),
        httpx.Response(200, json=[]),
    ],
)
def test_bad_responses_raise_search_error(response):
    with pytest.raises(SearchError):
        search(lambda request: response)


def test_network_failures_raise_search_error():
    def refuse(request):
        raise httpx.ConnectError("refused")

    def stall(request):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(SearchError, match="reach"):
        search(refuse)
    with pytest.raises(SearchError, match="timed out"):
        search(stall)


def test_formats_numbered_results():
    assert format_results([]) == "No results found."
    text = format_results(
        [
            SearchResult("One", "https://a.example", "First snippet"),
            SearchResult("", "https://b.example", ""),
        ]
    )
    assert text == (
        "[1] One\nhttps://a.example\nFirst snippet\n\n"
        "[2] https://b.example\nhttps://b.example"
    )
