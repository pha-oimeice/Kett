import asyncio
import json
import os
from collections.abc import AsyncIterator, Callable
from datetime import date
from typing import Literal

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .search import SearchError, SearchResult, format_results, web_search

MAX_QUERIES = 3
MAX_SOURCES = 6
QUERY_CONTEXT_MESSAGES = 6
QUERY_CONTEXT_CHARS = 1000
# Search results are prepended to the conversation, so give the model more room.
SEARCH_CONTEXT_TOKENS = 8192
OLLAMA_TIMEOUT = httpx.Timeout(10, read=300)

QUERY_SCHEMA = {
    "type": "object",
    "properties": {"queries": {"type": "array", "items": {"type": "string"}}},
    "required": ["queries"],
}


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=200_000)


class ChatRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    messages: list[ChatMessage] = Field(min_length=1, max_length=400)
    search: bool = False


class ChatError(Exception):
    pass


def ollama_url() -> str:
    return os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")


def event(kind: str, **fields) -> str:
    return json.dumps({"type": kind, **fields}) + "\n"


async def list_models(client: httpx.AsyncClient) -> list[str]:
    try:
        response = await client.get(f"{ollama_url()}/api/tags", timeout=5)
        models = response.json().get("models", [])
    except (httpx.HTTPError, ValueError, AttributeError):
        return []
    return [
        model["name"]
        for model in models
        if isinstance(model, dict)
        and isinstance(model.get("name"), str)
        and "completion" in model.get("capabilities", ["completion"])
    ]


async def stream_reply(
    client: httpx.AsyncClient, model: str, messages: list[dict], options: dict
) -> AsyncIterator[str]:
    payload = {"model": model, "messages": messages, "stream": True, "options": options}
    try:
        async with client.stream(
            "POST", f"{ollama_url()}/api/chat", json=payload, timeout=OLLAMA_TIMEOUT
        ) as response:
            if response.status_code != 200:
                detail = (await response.aread()).decode(errors="replace")[:300]
                raise ChatError(detail or f"Ollama returned {response.status_code}")
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                chunk = json.loads(line)
                if chunk.get("error"):
                    raise ChatError(str(chunk["error"]))
                if text := (chunk.get("message") or {}).get("content"):
                    yield text
    except httpx.HTTPError:
        raise ChatError("Could not reach Ollama") from None
    except ValueError:
        raise ChatError("Ollama returned an invalid response") from None


async def plan_queries(
    client: httpx.AsyncClient, model: str, messages: list[ChatMessage]
) -> list[str]:
    question = " ".join(messages[-1].content.split())[:300]
    transcript = "\n".join(
        f"{message.role}: {message.content[:QUERY_CONTEXT_CHARS]}"
        for message in messages[-QUERY_CONTEXT_MESSAGES:]
    )
    payload = {
        "model": model,
        "stream": False,
        "format": QUERY_SCHEMA,
        "options": {"temperature": 0},
        "messages": [
            {
                "role": "system",
                "content": (
                    f"Today's date is {date.today().isoformat()}. Write 1 to "
                    f"{MAX_QUERIES} short web search queries that would find the "
                    "information needed to answer the user's latest message in the "
                    'conversation below. Reply as JSON: {"queries": ["..."]}'
                ),
            },
            {"role": "user", "content": transcript},
        ],
    }
    try:
        response = await client.post(
            f"{ollama_url()}/api/chat", json=payload, timeout=OLLAMA_TIMEOUT
        )
        planned = json.loads(response.json()["message"]["content"])["queries"]
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        planned = []
    queries: list[str] = []
    for query in planned if isinstance(planned, list) else []:
        if isinstance(query, str) and (query := " ".join(query.split())[:200]):
            if query.lower() not in (seen.lower() for seen in queries):
                queries.append(query)
    # A small model can fail to plan; the question itself is a usable query.
    return queries[:MAX_QUERIES] or [question]


async def gather_sources(
    client: httpx.AsyncClient, queries: list[str]
) -> list[SearchResult]:
    outcomes = await asyncio.gather(
        *(web_search(query, client=client) for query in queries),
        return_exceptions=True,
    )
    failures = [outcome for outcome in outcomes if isinstance(outcome, SearchError)]
    for outcome in outcomes:
        if isinstance(outcome, BaseException) and not isinstance(outcome, SearchError):
            raise outcome
    if len(failures) == len(outcomes):
        raise failures[0]
    result_lists = [outcome for outcome in outcomes if isinstance(outcome, list)]
    sources: list[SearchResult] = []
    seen_urls: set[str] = set()
    # Take each query's best result before anyone's second best.
    for rank in range(max(map(len, result_lists), default=0)):
        for results in result_lists:
            if rank < len(results) and results[rank].url not in seen_urls:
                seen_urls.add(results[rank].url)
                sources.append(results[rank])
    return sources[:MAX_SOURCES]


async def respond(
    request: ChatRequest, transport: httpx.AsyncBaseTransport | None
) -> AsyncIterator[str]:
    messages = [message.model_dump() for message in request.messages]
    options: dict = {}
    async with httpx.AsyncClient(transport=transport) as client:
        try:
            if request.search:
                yield event("status", text="Planning the search…")
                queries = await plan_queries(client, request.model, request.messages)
                yield event("status", text=f"Searching: {' · '.join(queries)}")
                try:
                    sources = await gather_sources(client, queries)
                    note = (
                        "Web search results for the user's latest message are below. "
                        "Base your answer on them and cite the ones you use inline "
                        "by number, like [1]. If they do not contain the answer, "
                        "say so.\n\n" + format_results(sources)
                    )
                except SearchError as error:
                    sources = []
                    yield event("status", text=f"{error}. Answering without it.")
                    note = (
                        "The user asked for a web search, but it failed. Tell them "
                        "so briefly, then answer from your own knowledge."
                    )
                yield event(
                    "sources",
                    sources=[{"title": s.title, "url": s.url} for s in sources],
                )
                messages.insert(
                    0,
                    {
                        "role": "system",
                        "content": f"Today's date is {date.today().isoformat()}. "
                        + note,
                    },
                )
                options["num_ctx"] = SEARCH_CONTEXT_TOKENS
            async for text in stream_reply(client, request.model, messages, options):
                yield event("text", text=text)
        except ChatError as error:
            yield event("error", message=str(error))


def create_router(
    require_same_origin: Callable, transport: httpx.AsyncBaseTransport | None = None
) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/models")
    async def models() -> list[str]:
        async with httpx.AsyncClient(transport=transport) as client:
            return await list_models(client)

    @router.post("/chat", dependencies=[Depends(require_same_origin)])
    async def chat(request: ChatRequest) -> StreamingResponse:
        return StreamingResponse(
            respond(request, transport), media_type="application/x-ndjson"
        )

    return router
