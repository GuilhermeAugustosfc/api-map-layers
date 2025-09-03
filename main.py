from fastapi import FastAPI, Request
from fastapi.responses import Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio
import time
import re
import redis.asyncio as aioredis
from collections import OrderedDict
from functools import lru_cache
import psutil
import os
from typing import Dict, Any

# Context manager para lifespan do FastAPI
from contextlib import asynccontextmanager


def get_config() -> Dict[str, Any]:
    """Carrega configuração das variáveis de ambiente com valores padrão"""
    return {
        # Redis Configuration
        "redis_host": os.getenv("REDIS_HOST", "redis-dev.ops.ftrack.me"),
        "redis_port": int(os.getenv("REDIS_PORT", "6379")),
        "redis_db": int(os.getenv("REDIS_DB", "0")),
        "redis_password": os.getenv("REDIS_PASSWORD"),
        "redis_key_prefix": os.getenv("REDIS_KEY_PREFIX", "tile_cache:"),
        # Cache Configuration
        "cache_ttl_seconds": int(os.getenv("CACHE_TTL_SECONDS", "3600")),
        "average_image_size_kb": int(os.getenv("AVERAGE_IMAGE_SIZE_KB", "400")),
        "max_memory_percent": int(os.getenv("MAX_MEMORY_PERCENT", "20")),
        # HTTP Configuration
        "http_timeout_connect": float(os.getenv("HTTP_TIMEOUT_CONNECT", "3.0")),
        "http_timeout_read": float(os.getenv("HTTP_TIMEOUT_READ", "15.0")),
        "http_timeout_total": float(os.getenv("HTTP_TIMEOUT_TOTAL", "5.0")),
        "http_max_connections": int(os.getenv("HTTP_MAX_CONNECTIONS", "500")),
        "http_max_keepalive": int(os.getenv("HTTP_MAX_KEEPALIVE_CONNECTIONS", "200")),
        # Server Configuration
        "server_host": os.getenv("SERVER_HOST", "0.0.0.0"),
        "server_port": int(os.getenv("SERVER_PORT", "8000")),
        # HERE Maps Configuration
        "here_maps_base_url": os.getenv(
            "HERE_MAPS_BASE_URL", "https://maps.hereapi.com/v3/base/mc/"
        ),
        # Redis Socket Configuration
        "redis_socket_timeout": float(os.getenv("REDIS_SOCKET_TIMEOUT", "1.0")),
        "redis_socket_connect_timeout": float(
            os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "1.0")
        ),
        "redis_health_check_interval": int(
            os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "30")
        ),
    }


# Carrega configuração das variáveis de ambiente
config = get_config()

# Cliente HTTP global e Redis
CACHE_TTL_SECONDS = config["cache_ttl_seconds"]

# Config Redis
REDIS_HOST = config["redis_host"]
REDIS_PORT = config["redis_port"]
REDIS_DB = config["redis_db"]
REDIS_PASSWORD = config["redis_password"]
REDIS_KEY_PREFIX = config["redis_key_prefix"]

# Cache local (client-side caching) com invalidação por tracking
# Estratégia: máximo 20% da memória disponível da máquina
# Tamanho médio das imagens: 400KB
AVERAGE_IMAGE_SIZE_KB = config["average_image_size_kb"]
MAX_MEMORY_PERCENT = config["max_memory_percent"]


def _calculate_cache_limit() -> int:
    """Calcula o limite de entradas do cache baseado na memória disponível"""
    try:
        memory = psutil.virtual_memory()
        # Converte memória disponível para KB
        available_memory_kb = memory.available / 1024
        # Calcula 20% da memória disponível
        max_cache_memory_kb = available_memory_kb * (MAX_MEMORY_PERCENT / 100)
        # Calcula quantas imagens cabem nessa memória
        max_entries = int(max_cache_memory_kb / AVERAGE_IMAGE_SIZE_KB)
        # Limite mínimo de segurança
        return max(100, min(max_entries, 100000))
    except Exception:
        # Fallback para o valor padrão em caso de erro
        return 5000


# Cache local com limite dinâmico baseado na memória
LOCAL_CACHE_MAX_ENTRIES = _calculate_cache_limit()
local_cache: "dict[str, tuple[bytes, str, float]]" = (
    {}
)  # Otimizado: dict nativo ao invés de OrderedDict
local_cache_lock = asyncio.Lock()

# Constantes para strings frequentemente usadas (otimização de memória)
CACHE_HIT_LOCAL = "HIT-LOCAL"
CACHE_HIT_REDIS = "HIT-REDIS"
CACHE_MISS = "MISS"
CACHE_CONTROL_TEMPLATE = "public, max-age={}"
X_CACHE_TEMPLATE = "HIT-{}"

# Regex compilado para melhor performance
MAX_AGE_PATTERN = re.compile(r"max-age=(\d+)")


# Classe otimizada para métricas com __slots__
class Metrics:
    __slots__ = [
        "total_requests",
        "cache_hits",
        "local_cache_hits",
        "redis_cache_hits",
        "upstream_calls",
        "upstream_errors",
        "redis_errors",
        "redis_tracking_active",
    ]

    def __init__(self):
        self.total_requests = 0
        self.cache_hits = 0
        self.local_cache_hits = 0
        self.redis_cache_hits = 0
        self.upstream_calls = 0
        self.upstream_errors = 0
        self.redis_errors = 0
        self.redis_tracking_active = 0


# Instância global das métricas
metrics = Metrics()
metrics_lock = asyncio.Lock()


def _now() -> float:
    return time.time()


# Context manager para lifespan do FastAPI
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.http_client = httpx.AsyncClient(
        http2=True,  # HTTP/2 para melhor performance
        timeout=httpx.Timeout(
            config["http_timeout_total"],
            read=config["http_timeout_read"],
            connect=config["http_timeout_connect"],
        ),  # Configurado via variáveis de ambiente
        limits=httpx.Limits(
            max_connections=config["http_max_connections"],
            max_keepalive_connections=config["http_max_keepalive"],
        ),
        headers={
            # Pode ajustar cabeçalhos padrão se necessário
            "Accept": "*/*",
        },
    )
    app.state.redis = aioredis.Redis(
        host=config["redis_host"],
        port=config["redis_port"],
        db=config["redis_db"],
        password=config["redis_password"],
        socket_timeout=config["redis_socket_timeout"],
        socket_connect_timeout=config["redis_socket_connect_timeout"],
        retry_on_timeout=True,
        decode_responses=False,
        health_check_interval=config["redis_health_check_interval"],
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
                    metrics.redis_tracking_active = 1
                return
            except Exception:
                app.state.redis_tracking_active = False
                async with metrics_lock:
                    metrics.redis_tracking_active = 0
                await asyncio.sleep(backoff)
                backoff = min(30, backoff * 2)

    app.state.redis_tracking_task = asyncio.create_task(_enable_tracking_with_retry())

    yield  # Aplicação roda aqui

    # Shutdown
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


# Criando a instância do FastAPI
app = FastAPI(
    title="API Simples",
    description="Uma API simples criada com FastAPI",
    lifespan=lifespan,
)

# Configurando CORS (movido para depois da criação do app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
        # Move para o fim (uso recente) - simula comportamento LRU
        local_cache.pop(key)
        local_cache[key] = item
        return body, content_type, expires_at


async def _local_cache_set(
    key: str, body: bytes, content_type: str, ttl_seconds: int
) -> None:
    if ttl_seconds <= 0:
        return
    expires_at = _now() + ttl_seconds
    async with local_cache_lock:
        local_cache[key] = (body, content_type, expires_at)
        # Evict LRU se exceder limite
        while len(local_cache) > LOCAL_CACHE_MAX_ENTRIES:
            # Remove o item mais antigo (primeiro da lista)
            oldest_key = next(iter(local_cache))
            local_cache.pop(oldest_key)


async def _local_cache_evict(keys: list[str]) -> None:
    if not keys:
        return
    async with local_cache_lock:
        # Otimizado: remove múltiplas chaves de uma vez
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
                    # Otimizado: list comprehension ao invés de loop
                    keys = [
                        (
                            rk.decode("utf-8", "ignore")
                            if isinstance(rk, (bytes, bytearray))
                            else rk
                        )
                        for rk in raw_keys
                        if isinstance(rk, (bytes, bytearray, str))
                    ]
                    if keys:
                        await _local_cache_evict(keys)
            except Exception:
                # Ignora problemas no parse sem derrubar o listener
                pass
    except asyncio.CancelledError:
        return


# Otimizado: regex compilado e cache de função
@lru_cache(maxsize=128)
def _computar_ttl_dos_cabecalhos(cabecalhos_tuple: tuple) -> int:
    # Converte tuple para dict para processamento
    cabecalhos = dict(cabecalhos_tuple)
    cache_control = cabecalhos.get("cache-control", "")
    match = MAX_AGE_PATTERN.search(cache_control)
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
            metrics.redis_errors += 1
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
            metrics.upstream_errors += 1
        return None

    if resposta.status_code == 200:
        conteudo_bytes = resposta.content
        tipo_conteudo = resposta.headers.get("content-type", "image/png")
        # Otimizado: converte headers para tuple para cache
        ttl = _computar_ttl_dos_cabecalhos(tuple(resposta.headers.items()))
        return conteudo_bytes, tipo_conteudo, ttl

    # Conta erro upstream (status != 200)
    if resposta.status_code >= 400:
        async with metrics_lock:
            metrics.upstream_errors += 1

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
            metrics.redis_errors += 1


# Otimizado: função de atualização de métricas em lote
async def _atualizar_metricas_batch(updates: dict[str, int]) -> None:
    """Atualiza múltiplas métricas de uma vez para melhor performance"""
    async with metrics_lock:
        for key, value in updates.items():
            setattr(metrics, key, getattr(metrics, key) + value)


async def _atualizar_metricas(tipo_acesso: str) -> None:
    """Atualiza métricas baseado no tipo de acesso ao cache"""
    if tipo_acesso == "local":
        await _atualizar_metricas_batch(
            {"total_requests": 1, "cache_hits": 1, "local_cache_hits": 1}
        )
    elif tipo_acesso == "redis":
        await _atualizar_metricas_batch(
            {"total_requests": 1, "cache_hits": 1, "redis_cache_hits": 1}
        )
    elif tipo_acesso == "upstream":
        await _atualizar_metricas_batch({"total_requests": 1, "upstream_calls": 1})


def _criar_resposta_cache_hit(
    conteudo: bytes, tipo_midia: str, tempo_restante: int, tipo_cache: str
) -> Response:
    """Cria resposta HTTP para cache hit"""
    return Response(
        content=conteudo,
        media_type=tipo_midia,
        headers={
            "Cache-Control": CACHE_CONTROL_TEMPLATE.format(tempo_restante),
            "X-Cache": X_CACHE_TEMPLATE.format(tipo_cache),
        },
    )


def _criar_resposta_cache_miss(conteudo: bytes, tipo_midia: str, ttl: int) -> Response:
    """Cria resposta HTTP para cache miss"""
    return Response(
        content=conteudo,
        media_type=tipo_midia,
        headers={
            "Cache-Control": CACHE_CONTROL_TEMPLATE.format(ttl),
            "X-Cache": CACHE_MISS,
        },
    )


def _criar_resposta_erro_upstream(erro: str, status_code: int = 502) -> Response:
    """Cria resposta HTTP para erros do upstream"""
    return Response(
        content=f'{{"error":"Erro ao acessar HERE API","detail":"{erro}"}}',
        media_type="application/json",
        status_code=status_code,
        headers={"X-Cache": CACHE_MISS},
    )


@app.get("/proxy/{path:path}")
async def proxy(path: str, request: Request):
    """
    Proxy assíncrono para tiles do HERE Maps com pool de conexões e cache em memória.
    """
    # Normaliza o path
    path_normalizado = _normalizar_path_here(path)

    # Constrói URL do HERE
    url_base_here = config["here_maps_base_url"]
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


@app.options("/proxy/{path:path}")
async def proxy_options():
    return Response(
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Credentials": "true",
        }
    )


@app.get("/system-status")
async def system_status():
    """Retorna informações sobre recursos do sistema e uso de memória"""
    try:
        # Informações de memória do sistema
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()

        # Informações de CPU
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()

        # Informações de disco
        disk = psutil.disk_usage("/")

        # Informações do processo atual
        process = psutil.Process(os.getpid())
        process_memory = process.memory_info()
        process_cpu = process.cpu_percent()

        # Informações do cache local
        async with local_cache_lock:
            local_cache_size = len(local_cache)
            # Estimativa corrigida: 400KB por entrada
            local_cache_memory_estimate = local_cache_size * AVERAGE_IMAGE_SIZE_KB

        # Informações de rede
        network = psutil.net_io_counters()

        status_data = {
            "system": {
                "memory": {
                    "total_gb": round(memory.total / (1024**3), 2),
                    "available_gb": round(memory.available / (1024**3), 2),
                    "used_gb": round(memory.used / (1024**3), 2),
                    "percent_used": memory.percent,
                    "swap_total_gb": round(swap.total / (1024**3), 2),
                    "swap_used_gb": round(swap.used / (1024**3), 2),
                    "swap_percent_used": swap.percent,
                },
                "cpu": {"count": cpu_count, "usage_percent": cpu_percent},
                "disk": {
                    "total_gb": round(disk.total / (1024**3), 2),
                    "used_gb": round(disk.used / (1024**3), 2),
                    "free_gb": round(disk.free / (1024**3), 2),
                    "percent_used": round((disk.used / disk.total) * 100, 2),
                },
                "network": {
                    "bytes_sent_mb": round(network.bytes_sent / (1024**2), 2),
                    "bytes_recv_mb": round(network.bytes_recv / (1024**2), 2),
                },
            },
            "application": {
                "process_id": os.getpid(),
                "memory": {
                    "rss_mb": round(process_memory.rss / (1024**2), 2),
                    "vms_mb": round(process_memory.vms / (1024**2), 2),
                    "percent_of_system": round(
                        (process_memory.rss / memory.total) * 100, 4
                    ),
                },
                "cpu_percent": process_cpu,
                "cache_local": {
                    "entries": local_cache_size,
                    "max_entries": LOCAL_CACHE_MAX_ENTRIES,
                    "memory_estimate_kb": local_cache_memory_estimate,
                    "memory_estimate_mb": round(local_cache_memory_estimate / 1024, 2),
                    "max_memory_percent": MAX_MEMORY_PERCENT,
                    "average_image_size_kb": AVERAGE_IMAGE_SIZE_KB,
                    "max_cache_memory_mb": round(
                        (psutil.virtual_memory().available / 1024)
                        * (MAX_MEMORY_PERCENT / 100)
                        / 1024,
                        2,
                    ),
                    "memory_usage_percent": (
                        round(
                            (local_cache_memory_estimate / 1024)
                            / (
                                (psutil.virtual_memory().available / 1024)
                                * (MAX_MEMORY_PERCENT / 100)
                                / 1024
                            )
                            * 100,
                            2,
                        )
                        if psutil.virtual_memory().available > 0
                        else 0
                    ),
                },
            },
            "timestamp": time.time(),
            "uptime_seconds": time.time() - psutil.boot_time(),
        }

        return status_data

    except Exception as e:
        return {
            "error": "Erro ao obter status do sistema",
            "detail": str(e),
            "timestamp": time.time(),
        }


@app.get("/metrics")
async def metrics_json():
    async with metrics_lock:
        data = {
            "total_requests": metrics.total_requests,
            "cache_hits": metrics.cache_hits,
            "local_cache_hits": metrics.local_cache_hits,
            "redis_cache_hits": metrics.redis_cache_hits,
            "upstream_calls": metrics.upstream_calls,
            "upstream_errors": metrics.upstream_errors,
            "redis_errors": metrics.redis_errors,
            "redis_tracking_active": metrics.redis_tracking_active,
        }

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
        m = {
            "total_requests": metrics.total_requests,
            "cache_hits": metrics.cache_hits,
            "local_cache_hits": metrics.local_cache_hits,
            "redis_cache_hits": metrics.redis_cache_hits,
            "upstream_calls": metrics.upstream_calls,
            "upstream_errors": metrics.upstream_errors,
            "redis_errors": metrics.redis_errors,
            "redis_tracking_active": metrics.redis_tracking_active,
        }

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

    uvicorn.run(app, host=config["server_host"], port=config["server_port"])
