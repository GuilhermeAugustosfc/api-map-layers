from fastapi import FastAPI, Request
from fastapi.responses import Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio
import time
import re

# Criando a instância do FastAPI
app = FastAPI(title="API Simples", description="Uma API simples criada com FastAPI")

# Configurando CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cliente HTTP global e cache em memória
CACHE_TTL_SECONDS = 3600  # TTL padrão (1h)
tile_cache: dict[str, tuple[bytes, str, float]] = {}
cache_lock = asyncio.Lock()


@app.on_event("startup")
async def startup() -> None:
    app.state.http_client = httpx.AsyncClient(
        http2=False,
        timeout=httpx.Timeout(10.0, read=30.0, connect=5.0),
        limits=httpx.Limits(max_connections=200, max_keepalive_connections=100),
        headers={
            # Pode ajustar cabeçalhos padrão se necessário
            "Accept": "*/*",
        },
    )


@app.on_event("shutdown")
async def shutdown() -> None:
    await app.state.http_client.aclose()


def _compute_ttl_seconds_from_headers(headers: dict) -> int:
    cache_control = headers.get("cache-control", "")
    match = re.search(r"max-age=(\d+)", cache_control)
    if match:
        try:
            ttl = int(match.group(1))
            return max(1, min(ttl, CACHE_TTL_SECONDS))
        except ValueError:
            pass
    return CACHE_TTL_SECONDS


@app.get("/here-proxy/{path:path}")
async def here_proxy(path: str, request: Request):
    """
    Proxy assíncrono para tiles do HERE Maps com pool de conexões e cache em memória.
    """
    # Normaliza o path para evitar duplicação de "mc/"
    if path.startswith("mc/"):
        path = path[3:]

    here_base_url = "https://maps.hereapi.com/v3/base/mc/"
    here_url = f"{here_base_url}{path}"

    from urllib.parse import urlencode

    params_items = list(request.query_params.multi_items())
    params_items.sort()
    cache_key = f"{here_url}?{urlencode(params_items)}"

    now = time.time()
    async with cache_lock:
        cached = tile_cache.get(cache_key)
    if cached is not None:
        content_bytes, content_type, expires_at = cached
        if expires_at > now:
            remaining = int(max(1, expires_at - now))
            return Response(
                content=content_bytes,
                media_type=content_type,
                headers={"Cache-Control": f"public, max-age={remaining}"},
            )

    # Busca upstream de forma assíncrona
    client: httpx.AsyncClient = app.state.http_client
    try:
        resp = await client.get(here_url, params=request.query_params)
    except httpx.HTTPError as exc:
        return Response(
            content=f'{{"error":"Upstream error","detail":"{str(exc)}"}}',
            media_type="application/json",
            status_code=502,
        )

    if resp.status_code == 200:
        content_bytes = resp.content
        content_type = resp.headers.get("content-type", "image/png")
        ttl = _compute_ttl_seconds_from_headers(resp.headers)
        expires_at = time.time() + ttl
        async with cache_lock:
            tile_cache[cache_key] = (content_bytes, content_type, expires_at)

        return Response(
            content=content_bytes,
            media_type=content_type,
            headers={"Cache-Control": f"public, max-age={ttl}"},
        )

    return Response(
        content=f'{{"error":"Erro ao acessar HERE API","status":{resp.status_code},"url":"{resp.request.url}"}}',
        media_type="application/json",
        status_code=resp.status_code,
    )


@app.options("/here-proxy/{path:path}")
async def here_proxy_options():
    return Response(
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Credentials": "true",
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
