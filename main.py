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

# Métricas em memória (globais)
metrics = {
    "total_requests": 0,
    "cache_hits": 0,
    "upstream_calls": 0,
    "upstream_errors": 0,
}
# Métricas por índice
metrics_by_index: dict[str, dict[str, int]] = {
    "total_requests": {},
    "cache_hits": {},
    "upstream_calls": {},
    "upstream_errors": {},
}
metrics_lock = asyncio.Lock()


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
    Suporta um parâmetro de métrica `indice`, que NÃO é encaminhado ao HERE.
    Pode ser enviado como query (?indice=123) ou no final do path (/indice=123).
    """
    # Extrai indice do path se presente como sufixo /indice=...
    indice_from_path = None
    m = re.match(r"^(.*)/indice=([^/]+)$", path)
    if m:
        path = m.group(1)
        indice_from_path = m.group(2)

    # Normaliza o path para evitar duplicação de "mc/"
    if path.startswith("mc/"):
        path = path[3:]

    here_base_url = "https://maps.hereapi.com/v3/base/mc/"
    here_url = f"{here_base_url}{path}"

    from urllib.parse import urlencode

    # Lê indice da query (prioridade ao sufixo no path)
    indice_q = request.query_params.get("indice")
    indice = indice_from_path or indice_q or "unknown"

    # Monta params sem o "indice" para NÃO repassar ao HERE
    params_items = [
        (k, v) for (k, v) in request.query_params.multi_items() if k != "indice"
    ]
    params_items.sort()
    cache_key = f"{here_url}?{urlencode(params_items)}|indice={indice}"

    now = time.time()
    async with cache_lock:
        cached = tile_cache.get(cache_key)
    if cached is not None:
        content_bytes, content_type, expires_at = cached
        if expires_at > now:
            remaining = int(max(1, expires_at - now))
            async with metrics_lock:
                metrics["total_requests"] += 1
                metrics["cache_hits"] += 1
                d = metrics_by_index["total_requests"]
                d[indice] = d.get(indice, 0) + 1
                d = metrics_by_index["cache_hits"]
                d[indice] = d.get(indice, 0) + 1
            return Response(
                content=content_bytes,
                media_type=content_type,
                headers={
                    "Cache-Control": f"public, max-age={remaining}",
                    "X-Cache": "HIT",
                    "X-Index": indice,
                },
            )

    # Busca upstream de forma assíncrona
    client: httpx.AsyncClient = app.state.http_client
    async with metrics_lock:
        metrics["total_requests"] += 1
        metrics["upstream_calls"] += 1
        d = metrics_by_index["total_requests"]
        d[indice] = d.get(indice, 0) + 1
        d = metrics_by_index["upstream_calls"]
        d[indice] = d.get(indice, 0) + 1
    try:
        resp = await client.get(here_url, params=params_items)
    except httpx.HTTPError as exc:
        async with metrics_lock:
            metrics["upstream_errors"] += 1
            d = metrics_by_index["upstream_errors"]
            d[indice] = d.get(indice, 0) + 1
        return Response(
            content=f'{{"error":"Upstream error","detail":"{str(exc)}"}}',
            media_type="application/json",
            status_code=502,
            headers={"X-Cache": "MISS", "X-Index": indice},
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
            headers={
                "Cache-Control": f"public, max-age={ttl}",
                "X-Cache": "MISS",
                "X-Index": indice,
            },
        )

    # Conta erro upstream (status != 200)
    if resp.status_code >= 400:
        async with metrics_lock:
            metrics["upstream_errors"] += 1
            d = metrics_by_index["upstream_errors"]
            d[indice] = d.get(indice, 0) + 1

    return Response(
        content=f'{{"error":"Erro ao acessar HERE API","status":{resp.status_code},"url":"{resp.request.url}"}}',
        media_type="application/json",
        status_code=resp.status_code,
        headers={"X-Cache": "MISS", "X-Index": indice},
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


@app.get("/metrics")
async def metrics_json():
    async with metrics_lock:
        data = dict(metrics)
    total = data.get("total_requests", 0)
    hits = data.get("cache_hits", 0)
    hit_ratio = (hits / total) if total else 0.0
    data["cache_hit_ratio"] = round(hit_ratio, 6)
    return data


@app.get("/metrics/prometheus")
async def metrics_prometheus():
    async with metrics_lock:
        m = dict(metrics)
        mbi = {k: dict(v) for k, v in metrics_by_index.items()}
    total = m.get("total_requests", 0)
    hits = m.get("cache_hits", 0)
    upstream_calls = m.get("upstream_calls", 0)
    upstream_errors = m.get("upstream_errors", 0)
    hit_ratio = (hits / total) if total else 0.0

    lines = [
        f"here_proxy_total_requests {total}",
        f"here_proxy_cache_hits_total {hits}",
        f"here_proxy_upstream_calls_total {upstream_calls}",
        f"here_proxy_upstream_errors_total {upstream_errors}",
        f"here_proxy_cache_hit_ratio {hit_ratio}",
    ]

    # Por índice (com label indice="...")
    indices = set()
    for d in mbi.values():
        indices.update(d.keys())
    for idx in sorted(indices):
        t = mbi["total_requests"].get(idx, 0)
        h = mbi["cache_hits"].get(idx, 0)
        u = mbi["upstream_calls"].get(idx, 0)
        e = mbi["upstream_errors"].get(idx, 0)
        hr = (h / t) if t else 0.0
        lines.append(f'here_proxy_total_requests{{indice="{idx}"}} {t}')
        lines.append(f'here_proxy_cache_hits_total{{indice="{idx}"}} {h}')
        lines.append(f'here_proxy_upstream_calls_total{{indice="{idx}"}} {u}')
        lines.append(f'here_proxy_upstream_errors_total{{indice="{idx}"}} {e}')
        lines.append(f'here_proxy_cache_hit_ratio{{indice="{idx}"}} {hr}')

    body = "\n".join(lines) + "\n"
    return Response(content=body, media_type="text/plain; version=0.0.4")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
