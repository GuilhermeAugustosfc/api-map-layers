from fastapi import FastAPI, Request
from fastapi.responses import Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio
import time
import re
import redis.asyncio as aioredis
from collections import OrderedDict

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

# Cliente HTTP global e Redis
CACHE_TTL_SECONDS = 3600  # TTL padrão (1h)

# Config Redis (ajuste se necessário)
REDIS_HOST = "redis-dev.ops.ftrack.me"
REDIS_PORT = 6379
REDIS_DB = 0
REDIS_PASSWORD = None
REDIS_KEY_PREFIX = "tile_cache:"

# Cache local (client-side caching) com invalidação por tracking
LOCAL_CACHE_MAX_ENTRIES = 5000
local_cache: "OrderedDict[str, tuple[bytes, str, float]]" = OrderedDict()
local_cache_lock = asyncio.Lock()


def _now() -> float:
    return time.time()


async def _local_cache_get(key: str) -> "tuple[bytes, str, float] | None":
    now = _now()
    async with local_cache_lock:
        item = local_cache.get(key)
        if item is None:
            return None
        body, content_type, expires_at = item
        if expires_at <= now:
            # Expirado localmente
            local_cache.pop(key, None)
            return None
        # Move para o fim (uso recente)
        local_cache.move_to_end(key)
        return body, content_type, expires_at


async def _local_cache_set(
    key: str, body: bytes, content_type: str, ttl_seconds: int
) -> None:
    if ttl_seconds <= 0:
        return
    expires_at = _now() + ttl_seconds
    async with local_cache_lock:
        local_cache[key] = (body, content_type, expires_at)
        local_cache.move_to_end(key)
        # Evict LRU se exceder limite
        while len(local_cache) > LOCAL_CACHE_MAX_ENTRIES:
            local_cache.popitem(last=False)


async def _local_cache_evict(keys: list[str]) -> None:
    if not keys:
        return
    async with local_cache_lock:
        for k in keys:
            local_cache.pop(k, None)


async def _tracking_listener(redis: aioredis.Redis) -> None:
    # Escuta push messages de invalidação e remove do cache local
    try:
        while True:
            msg = await redis.get_push_data()
            # Esperado: [b'invalidate', [b'key1', b'key2', ...]]
            try:
                if (
                    isinstance(msg, (list, tuple))
                    and len(msg) >= 2
                    and msg[0] == b"invalidate"
                ):
                    raw_keys = msg[1] or []
                    keys: list[str] = []
                    for rk in raw_keys:
                        if isinstance(rk, (bytes, bytearray)):
                            keys.append(rk.decode("utf-8", "ignore"))
                        elif isinstance(rk, str):
                            keys.append(rk)
                    if keys:
                        await _local_cache_evict(keys)
            except Exception:
                # Ignora problemas no parse sem derrubar o listener
                pass
    except asyncio.CancelledError:
        return


# Métricas em memória
metrics = {
    "total_requests": 0,
    "cache_hits": 0,
    "local_cache_hits": 0,
    "redis_cache_hits": 0,
    "upstream_calls": 0,
    "upstream_errors": 0,
    "redis_errors": 0,
    "redis_tracking_active": 0,
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
    app.state.redis = aioredis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        password=REDIS_PASSWORD,
        socket_timeout=3,
        socket_connect_timeout=3,
        retry_on_timeout=True,
        decode_responses=False,
        health_check_interval=30,
    )

    # Inicializa tracking em background com retry (não bloqueia startup)
    async def _enable_tracking_with_retry() -> None:
        backoff = 1
        while True:
            try:
                # Força conexão e habilita tracking
                await app.state.redis.ping()
                await app.state.redis.client_tracking(
                    on=True,
                    bcast=True,
                    prefixes=[REDIS_KEY_PREFIX.encode()],
                    noloop=True,
                )
                app.state.redis_tracking_listener = asyncio.create_task(
                    _tracking_listener(app.state.redis)
                )
                app.state.redis_tracking_active = True
                async with metrics_lock:
                    metrics["redis_tracking_active"] = 1
                return
            except Exception:
                app.state.redis_tracking_active = False
                async with metrics_lock:
                    metrics["redis_tracking_active"] = 0
                await asyncio.sleep(backoff)
                backoff = min(30, backoff * 2)

    app.state.redis_tracking_task = asyncio.create_task(_enable_tracking_with_retry())


@app.on_event("shutdown")
async def shutdown() -> None:
    await app.state.http_client.aclose()
    try:
        # redis-py 5 fornece aclose() no cliente assíncrono
        await app.state.redis.aclose()  # type: ignore[attr-defined]
    except Exception:
        pass
    # Encerra listener de tracking
    tracking_task = getattr(app.state, "redis_tracking_task", None)
    tracking_listener = getattr(app.state, "redis_tracking_listener", None)
    for t in (tracking_listener, tracking_task):
        if t is not None:
            t.cancel()
            try:
                await t
            except Exception:
                pass


def _computar_ttl_dos_cabecalhos(cabecalhos: dict) -> int:
    cache_control = cabecalhos.get("cache-control", "")
    match = re.search(r"max-age=(\d+)", cache_control)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    return CACHE_TTL_SECONDS


def _normalizar_path_here(path: str) -> str:
    """Normaliza o path para evitar duplicação de 'mc/'"""
    if path.startswith("mc/"):
        return path[3:]
    return path


def _gerar_chave_cache(url_completa: str, parametros: dict) -> str:
    """Gera chave única para o cache baseada na URL e parâmetros"""
    from urllib.parse import urlencode

    parametros_ordenados = sorted(parametros.multi_items())
    return f"{url_completa}?{urlencode(parametros_ordenados)}"


def _gerar_chave_redis(chave_cache: str) -> str:
    """Gera chave Redis com prefixo"""
    return f"{REDIS_KEY_PREFIX}{chave_cache}"


async def _verificar_cache_local(chave_redis: str) -> "tuple[bytes, str, int] | None":
    """Verifica se o item existe no cache local e retorna os dados"""
    resultado = await _local_cache_get(chave_redis)
    if resultado is not None:
        conteudo, tipo_conteudo, expira_em = resultado
        tempo_restante = int(max(1, expira_em - _now()))
        return conteudo, tipo_conteudo, tempo_restante
    return None


async def _verificar_cache_redis(chave_redis: str) -> "tuple[bytes, str, int] | None":
    """Verifica se o item existe no Redis e retorna os dados"""
    redis: aioredis.Redis = app.state.redis
    pipe = redis.pipeline()
    pipe.hmget(chave_redis, "b", "ct")
    pipe.ttl(chave_redis)

    try:
        valores_hm, ttl_restante = await pipe.execute()
    except Exception:
        async with metrics_lock:
            metrics["redis_errors"] += 1
        return None

    if not isinstance(valores_hm, (list, tuple)) or len(valores_hm) != 2:
        return None

    corpo_cache, tipo_conteudo_cache = valores_hm

    if corpo_cache is not None and isinstance(ttl_restante, int) and ttl_restante > 0:

        tempo_restante = int(max(1, ttl_restante))
        tipo_midia = (
            tipo_conteudo_cache.decode("utf-8", "ignore")
            if isinstance(tipo_conteudo_cache, (bytes, bytearray))
            else (tipo_conteudo_cache or "image/png")
        )
        return corpo_cache, tipo_midia, tempo_restante

    return None


async def _buscar_dados_upstream(
    url_here: str, parametros: dict
) -> "tuple[bytes, str, int] | None":
    """Busca dados do serviço HERE Maps"""
    client: httpx.AsyncClient = app.state.http_client

    try:
        resposta = await client.get(url_here, params=parametros)
    except httpx.HTTPError as erro:
        async with metrics_lock:
            metrics["upstream_errors"] += 1
        return None

    if resposta.status_code == 200:
        conteudo_bytes = resposta.content
        tipo_conteudo = resposta.headers.get("content-type", "image/png")
        ttl = _computar_ttl_dos_cabecalhos(resposta.headers)
        return conteudo_bytes, tipo_conteudo, ttl

    # Conta erro upstream (status != 200)
    if resposta.status_code >= 400:
        async with metrics_lock:
            metrics["upstream_errors"] += 1

    return None


async def _salvar_no_cache_redis(
    chave_redis: str, conteudo: bytes, tipo_conteudo: str, ttl: int
) -> None:
    """Salva dados no Redis usando pipeline para melhor performance"""
    redis: aioredis.Redis = app.state.redis

    try:
        pipe = redis.pipeline()
        pipe.hset(chave_redis, mapping={"b": conteudo, "ct": tipo_conteudo})
        pipe.expire(chave_redis, ttl)
        await pipe.execute()
    except Exception:
        # Se falhar o cache, ainda retorna a resposta
        async with metrics_lock:
            metrics["redis_errors"] += 1


async def _atualizar_metricas(tipo_acesso: str) -> None:
    """Atualiza métricas baseado no tipo de acesso ao cache"""
    async with metrics_lock:
        metrics["total_requests"] += 1

        if tipo_acesso == "local":
            metrics["cache_hits"] += 1
            metrics["local_cache_hits"] += 1
        elif tipo_acesso == "redis":
            metrics["cache_hits"] += 1
            metrics["redis_cache_hits"] += 1
        elif tipo_acesso == "upstream":
            metrics["upstream_calls"] += 1


def _criar_resposta_cache_hit(
    conteudo: bytes, tipo_midia: str, tempo_restante: int, tipo_cache: str
) -> Response:
    """Cria resposta HTTP para cache hit"""
    return Response(
        content=conteudo,
        media_type=tipo_midia,
        headers={
            "Cache-Control": f"public, max-age={tempo_restante}",
            "X-Cache": f"HIT-{tipo_cache}",
        },
    )


def _criar_resposta_cache_miss(conteudo: bytes, tipo_midia: str, ttl: int) -> Response:
    """Cria resposta HTTP para cache miss"""
    return Response(
        content=conteudo,
        media_type=tipo_midia,
        headers={
            "Cache-Control": f"public, max-age={ttl}",
            "X-Cache": "MISS",
        },
    )


def _criar_resposta_erro_upstream(erro: str, status_code: int = 502) -> Response:
    """Cria resposta HTTP para erros do upstream"""
    return Response(
        content=f'{{"error":"Erro ao acessar HERE API","detail":"{erro}"}}',
        media_type="application/json",
        status_code=status_code,
        headers={"X-Cache": "MISS"},
    )


@app.get("/here-proxy/{path:path}")
async def here_proxy(path: str, request: Request):
    """
    Proxy assíncrono para tiles do HERE Maps com pool de conexões e cache em memória.
    """
    # Normaliza o path
    path_normalizado = _normalizar_path_here(path)

    # Constrói URL do HERE
    url_base_here = "https://maps.hereapi.com/v3/base/mc/"
    url_here = f"{url_base_here}{path_normalizado}"

    # Gera chaves para cache
    chave_cache = _gerar_chave_cache(url_here, request.query_params)
    chave_redis = _gerar_chave_redis(chave_cache)

    # 1. Verifica cache local (0-RTT)
    resultado_local = await _verificar_cache_local(chave_redis)
    if resultado_local is not None:
        conteudo, tipo_midia, tempo_restante = resultado_local
        await _atualizar_metricas("local")
        return _criar_resposta_cache_hit(conteudo, tipo_midia, tempo_restante, "LOCAL")

    # 2. Verifica cache Redis
    resultado_redis = await _verificar_cache_redis(chave_redis)
    if resultado_redis is not None:
        conteudo, tipo_midia, tempo_restante = resultado_redis
        # Popula cache local para futuras requisições
        await _local_cache_set(chave_redis, conteudo, tipo_midia, tempo_restante)
        await _atualizar_metricas("redis")
        return _criar_resposta_cache_hit(conteudo, tipo_midia, tempo_restante, "REDIS")

    # 3. Busca dados do upstream
    resultado_upstream = await _buscar_dados_upstream(url_here, request.query_params)
    if resultado_upstream is None:
        return _criar_resposta_erro_upstream("Erro na comunicação com HERE API")

    conteudo, tipo_midia, ttl = resultado_upstream
    await _atualizar_metricas("upstream")

    # 4. Salva no Redis e cache local
    await _salvar_no_cache_redis(chave_redis, conteudo, tipo_midia, ttl)
    await _local_cache_set(chave_redis, conteudo, tipo_midia, ttl)

    # 5. Retorna resposta
    return _criar_resposta_cache_miss(conteudo, tipo_midia, ttl)


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
    local_hits = data.get("local_cache_hits", 0)
    redis_hits = data.get("redis_cache_hits", 0)
    redis_errors = data.get("redis_errors", 0)
    tracking_active = data.get("redis_tracking_active", 0)

    hit_ratio = (hits / total) if total else 0.0
    local_hit_ratio = (local_hits / total) if total else 0.0
    redis_hit_ratio = (redis_hits / total) if total else 0.0

    data["cache_hit_ratio"] = round(hit_ratio, 6)
    data["local_cache_hit_ratio"] = round(local_hit_ratio, 6)
    data["redis_cache_hit_ratio"] = round(redis_hit_ratio, 6)
    data["redis_error_rate"] = round((redis_errors / total) if total else 0.0, 6)
    data["redis_tracking_status"] = "active" if tracking_active else "inactive"

    return data


@app.get("/metrics/prometheus")
async def metrics_prometheus():
    async with metrics_lock:
        m = dict(metrics)
    total = m.get("total_requests", 0)
    hits = m.get("cache_hits", 0)
    local_hits = m.get("local_cache_hits", 0)
    redis_hits = m.get("redis_cache_hits", 0)
    upstream_calls = m.get("upstream_calls", 0)
    upstream_errors = m.get("upstream_errors", 0)
    redis_errors = m.get("redis_errors", 0)
    tracking_active = m.get("redis_tracking_active", 0)

    hit_ratio = (hits / total) if total else 0.0
    local_hit_ratio = (local_hits / total) if total else 0.0
    redis_hit_ratio = (redis_hits / total) if total else 0.0
    redis_error_rate = (redis_errors / total) if total else 0.0

    lines = [
        f"proxy_total_requisicoes {total}",
        f"proxy_cache_acertos_total {hits}",
        f"proxy_cache_local_acertos_total {local_hits}",
        f"proxy_cache_redis_acertos_total {redis_hits}",
        f"proxy_chamadas_HERE_total {upstream_calls}",
        f"proxy_erros_HERE_total {upstream_errors}",
        f"proxy_erros_redis_total {redis_errors}",
        f"proxy_taxa_cache_acerto {hit_ratio}",
        f"proxy_taxa_cache_local_acerto {local_hit_ratio}",
        f"proxy_taxa_cache_redis_acerto {redis_hit_ratio}",
        f"proxy_taxa_erro_redis {redis_error_rate}",
        f"proxy_redis_tracking_ativo {tracking_active}",
    ]
    body = "\n".join(lines) + "\n"
    return Response(content=body, media_type="text/plain; version=0.0.4")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
