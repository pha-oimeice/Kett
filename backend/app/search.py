import os
from dataclasses import dataclass

import httpx

SEARCH_TIMEOUT = 10
SNIPPET_LIMIT = 300


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


class SearchError(Exception):
    pass


def shorten(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= SNIPPET_LIMIT:
        return text
    return text[: SNIPPET_LIMIT - 1].rstrip() + "…"


async def web_search(
    query: str,
    max_results: int = 5,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[SearchResult]:
    base_url = os.getenv("SEARXNG_URL", "http://127.0.0.1:8888").rstrip("/")
    search_url = f"{base_url}/search"
    params = {"q": query, "format": "json"}

    try:
        if client is None:
            async with httpx.AsyncClient() as own_client:
                response = await own_client.get(
                    search_url, params=params, timeout=SEARCH_TIMEOUT
                )
        else:
            response = await client.get(
                search_url, params=params, timeout=SEARCH_TIMEOUT
            )
    except httpx.TimeoutException:
        raise SearchError("Web search timed out") from None
    except httpx.HTTPError:
        raise SearchError("Could not reach the search service") from None

    if response.status_code != 200:
        raise SearchError(f"Search service returned {response.status_code}")

    try:
        data = response.json()
    except ValueError:
        raise SearchError("Search service returned an invalid response") from None

    raw_results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(raw_results, list):
        raise SearchError("Search service returned an invalid response")

    results: list[SearchResult] = []
    seen_urls: set[str] = set()
    for item in raw_results:
        if len(results) >= max_results:
            break
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)

        title = item.get("title")
        snippet = item.get("content")
        results.append(
            SearchResult(
                title=title.strip() if isinstance(title, str) else "",
                url=url,
                snippet=shorten(snippet) if isinstance(snippet, str) else "",
            )
        )
    return results


def format_results(results: list[SearchResult]) -> str:
    if not results:
        return "No results found."
    return "\n\n".join(
        f"[{number}] {result.title or result.url}\n{result.url}\n{result.snippet}".rstrip()
        for number, result in enumerate(results, start=1)
    )
