# 🏗️ Arquitetura Técnica - Map Layer Cache

Documentação técnica detalhada da arquitetura, algoritmos e decisões de design do sistema.

## 📊 Visão Geral da Arquitetura

### Componentes Principais

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Application                       │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐ │
│  │               HTTP Layer (Endpoints)                    │ │
│  ├─────────────────────────────────────────────────────────┤ │
│  │  • /here-proxy/{path} - Proxy principal                 │ │
│  │  • /system-status - Status do sistema                   │ │
│  │  • /metrics - Métricas JSON                             │ │
│  │  • /metrics/prometheus - Métricas Prometheus           │ │
│  └─────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐ │
│  │            Cache Layer (Multi-Level)                   │ │
│  ├─────────────────────────────────────────────────────────┤ │
│  │  L1: Local Memory Cache (LRU, ~0.1ms)                  │ │
│  │  L2: Redis Distributed Cache (~1-5ms)                   │ │
│  │  L3: HERE Maps API (100-500ms)                          │ │
│  └─────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐ │
│  │             HTTP Client Layer                           │ │
│  ├─────────────────────────────────────────────────────────┤ │
│  │  • HTTP/2 Support                                       │ │
│  │  • Connection Pooling                                   │ │
│  │  • Automatic Retries                                    │ │
│  │  • Timeout Management                                   │ │
│  └─────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐ │
│  │             Metrics & Monitoring                        │ │
│  ├─────────────────────────────────────────────────────────┤ │
│  │  • Real-time Statistics                                 │ │
│  │  • System Resource Monitoring                           │ │
│  │  • Error Tracking                                       │ │
│  │  • Prometheus Integration                               │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## 🔄 Fluxo de Dados

### Sequência de Processamento

```
┌─────────────────┐
│ Requisição HTTP │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐     ┌─────────────┐
│  Path válido?   │────▶│  Erro 404   │
└─────────┬───────┘     └─────────────┘
          │
          ▼
┌─────────────────┐
│ Normalizar Path │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ Gerar Cache Key │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐     ┌─────────────────────┐
│  Cache Local?   │────▶│ Retornar Cache Local│
└─────────┬───────┘     └─────────────────────┘
          │ HIT
          ▼ MISS
┌─────────────────┐     ┌─────────────────────┐
│  Cache Redis?   │────▶│ Retornar Cache Redis│
└─────────┬───────┘     └─────────┬───────────┘
          │ HIT                   │
          ▼ MISS                  ▼
┌─────────────────┐     ┌─────────────────────┐
│ Buscar HERE API │────▶│ Popular Cache Local │
└─────────┬───────┘     └─────────────────────┘
          │                       │
          ▼                       ▼
┌─────────────────┐     ┌─────────────────────┐
│   Sucesso?      │────▶│ Salvar Cache Redis  │
└─────────┬───────┘     └─────────┬───────────┘
          │                       │
          ▼                       ▼
┌─────────────────┐     ┌─────────────────────┐
│ Erro Upstream   │     │ Salvar Cache Local  │
└─────────────────┘     └─────────┬───────────┘
                                  │
                                  ▼
                        ┌─────────────────────┐
                        │  Retornar Resposta  │
                        └─────────────────────┘
```

### Legenda:
- `─────▶` : Fluxo principal
- `└─────┘` : Decisão/Split
- `│` : Conexão vertical
- `▼` : Fluxo para baixo

### Cache Strategy Algorithm

```python
async def process_request(request):
    key = generate_cache_key(request)

    # L1: Local Memory Cache (Fastest)
    if local_cache.has(key):
        update_metrics("local_hit")
        return local_cache.get(key)

    # L2: Redis Distributed Cache
    if redis_cache.has(key):
        update_metrics("redis_hit")
        data = redis_cache.get(key)
        local_cache.set(key, data)  # Warm L1
        return data

    # L3: HERE Maps API (Slowest)
    data = await fetch_from_here_api(request)
    update_metrics("upstream_call")

    # Save to both caches
    await redis_cache.set(key, data)
    local_cache.set(key, data)

    return data
```

## 🗄️ Sistema de Cache

### Cache Local (L1) - Memória RAM

#### Características
- **Tipo**: Dictionary-based in-memory cache
- **Algoritmo**: LRU (Least Recently Used)
- **Limite**: Dinâmico baseado na memória disponível (20% padrão)
- **Latência**: ~0.1ms
- **Persistência**: Não persistente (reinicia com aplicação)

#### Estrutura de Dados
```python
# Formato: chave -> (conteúdo, tipo_midia, timestamp_expiracao)
local_cache: Dict[str, Tuple[bytes, str, float]] = {}

# Exemplo de entrada:
# "tile_cache:mc/15/26480/16920/256" -> (b'<png_data>', 'image/png', 1640995200.0)
```

#### Algoritmo de Limitação de Memória
```python
def calculate_cache_limit():
    available_memory_kb = psutil.virtual_memory().available / 1024
    max_cache_memory_kb = available_memory_kb * (MAX_MEMORY_PERCENT / 100)
    max_entries = max_cache_memory_kb / AVERAGE_IMAGE_SIZE_KB
    return max(100, min(max_entries, 100000))  # Entre 100 e 100k entradas
```

#### Estratégia de Evicção LRU
```python
async def local_cache_set(key, content, content_type, ttl):
    expires_at = time.time() + ttl
    local_cache[key] = (content, content_type, expires_at)

    # Evict LRU se necessário
    while len(local_cache) > LOCAL_CACHE_MAX_ENTRIES:
        oldest_key = next(iter(local_cache))
        local_cache.pop(oldest_key)
```

### Cache Redis (L2) - Distribuído

#### Características
- **Tipo**: Redis Hash + TTL
- **Persistência**: Configurável (RDB/AOF)
- **Distribuição**: Multi-instância support
- **Latência**: ~1-5ms
- **Invalidação**: Automatic via keyspace notifications

#### Estrutura no Redis
```redis
# Chave principal (Hash)
tile_cache:mc/15/26480/16920/256
├── b: <binary_data>          # Conteúdo binário
├── ct: "image/png"          # Content-Type
└── TTL: 3600                # Expiração em segundos

# Exemplo de comandos Redis
HSET tile_cache:mc/15/26480/16920/256 b <png_data> ct "image/png"
EXPIRE tile_cache:mc/15/26480/16920/256 3600
```

#### Pipeline Optimization
```python
async def save_to_redis(key, content, content_type, ttl):
    pipe = redis.pipeline()
    pipe.hset(key, mapping={"b": content, "ct": content_type})
    pipe.expire(key, ttl)
    await pipe.execute()  # Execução atômica
```

## 🌐 HTTP Client Layer

### Configuração Otimizada

#### HTTP/2 Support
```python
httpx.AsyncClient(
    http2=True,  # Enable HTTP/2
    timeout=httpx.Timeout(
        total=5.0,      # Total timeout
        read=15.0,      # Read timeout
        connect=3.0     # Connect timeout
    ),
    limits=httpx.Limits(
        max_connections=500,           # Max concurrent connections
        max_keepalive_connections=200   # Keep-alive connections
    )
)
```

#### Connection Pool Strategy
- **Max Connections**: 500 (configurável)
- **Keep-Alive**: 200 conexões
- **Timeout Connect**: 3s
- **Timeout Read**: 15s
- **Timeout Total**: 5s

### Headers Management

#### Request Headers
```python
# Headers enviados para HERE Maps
{
    "Accept": "*/*",
    "User-Agent": "Map-Layer-Cache/1.0",
    "X-Forwarded-For": client_ip,
    "X-Real-IP": client_ip
}
```

#### Response Headers
```python
# Headers retornados ao cliente
{
    "Cache-Control": f"max-age={ttl}",
    "X-Cache": "HIT-LOCAL" | "HIT-REDIS" | "MISS",
    "Content-Type": content_type,
    "Access-Control-Allow-Origin": "*",
    "X-Powered-By": "Map-Layer-Cache"
}
```

## 📊 Sistema de Métricas

### Métricas Coletadas

#### Contadores
```python
class Metrics:
    __slots__ = [
        "total_requests",      # Total de requisições
        "cache_hits",          # Total de acertos no cache
        "local_cache_hits",    # Acertos no cache local
        "redis_cache_hits",    # Acertos no cache Redis
        "upstream_calls",      # Chamadas para HERE API
        "upstream_errors",     # Erros da API HERE
        "redis_errors",        # Erros do Redis
        "redis_tracking_active" # Status do tracking Redis
    ]
```

#### Cálculos Derivados
```python
# Taxa de acerto no cache
cache_hit_ratio = cache_hits / total_requests if total_requests > 0 else 0

# Taxa de erro do Redis
redis_error_rate = redis_errors / total_requests if total_requests > 0 else 0

# Distribuição de hits
local_hit_ratio = local_cache_hits / total_requests
redis_hit_ratio = redis_cache_hits / total_requests
upstream_ratio = upstream_calls / total_requests
```

### Formatos de Exportação

#### JSON Format (/metrics)
```json
{
  "total_requests": 1500,
  "cache_hits": 1200,
  "cache_hit_ratio": 0.8,
  "local_cache_hits": 800,
  "redis_cache_hits": 400,
  "upstream_calls": 300,
  "upstream_errors": 5,
  "redis_errors": 2,
  "redis_tracking_active": 1
}
```

#### Prometheus Format (/metrics/prometheus)
```text
# HELP proxy_total_requisicoes Total de requisições processadas
# TYPE proxy_total_requisicoes counter
proxy_total_requisicoes 1500

# HELP proxy_cache_acertos_total Total de acertos no cache
# TYPE proxy_cache_acertos_total counter
proxy_cache_acertos_total 1200

# HELP proxy_taxa_cache_acerto Taxa de acerto no cache
# TYPE proxy_taxa_cache_acerto gauge
proxy_taxa_cache_acerto 0.8
```

## 🔧 Otimizações de Performance

### Memory Optimizations

#### String Interning
```python
# Constantes frequentemente usadas são internadas
CACHE_HIT_LOCAL = "HIT-LOCAL"      # sys.intern() automático
CACHE_HIT_REDIS = "HIT-REDIS"
CACHE_MISS = "MISS"
```

#### __slots__ Classes
```python
class Metrics:
    __slots__ = ["total_requests", "cache_hits", ...]
    # Reduz overhead de memória vs __dict__
```

#### Compiled Regex
```python
MAX_AGE_PATTERN = re.compile(r"max-age=(\d+)")
# Compilado uma vez, reutilizado sempre
```

### CPU Optimizations

#### LRU Cache para Funções
```python
@lru_cache(maxsize=128)
def compute_ttl_from_headers(headers_tuple):
    # Cache de função para parsing de headers
    pass
```

#### List Comprehensions
```python
# Otimizado: List comprehension ao invés de loop
keys = [rk.decode("utf-8", "ignore") for rk in raw_keys if isinstance(rk, bytes)]
```

#### Async Context Managers
```python
async with local_cache_lock:
    # Lock assíncrono para thread safety
    local_cache[key] = value
```

### Network Optimizations

#### HTTP/2 Multiplexing
```python
# HTTP/2 permite múltiplas requisições na mesma conexão
httpx.AsyncClient(http2=True)
```

#### Connection Pooling
```python
# Reutilização de conexões TCP
limits=httpx.Limits(max_keepalive_connections=200)
```

#### Pipeline Redis
```python
# Execução atômica de múltiplos comandos
pipe = redis.pipeline()
pipe.hset(key, mapping=data)
pipe.expire(key, ttl)
await pipe.execute()
```

## 🔄 Invalidação de Cache

### Redis Keyspace Notifications

#### Configuração
```python
await redis.client_tracking(
    on=True,
    bcast=True,
    prefixes=[REDIS_KEY_PREFIX.encode()],
    noloop=True
)
```

#### Listener Assíncrono
```python
async def tracking_listener(redis):
    while True:
        msg = await redis.get_push_data()
        if msg[0] == b"invalidate":
            keys = [k.decode() for k in msg[1]]
            await local_cache_evict(keys)
```

### Estratégias de Invalidação

#### Time-Based (TTL)
- Baseado no header `Cache-Control: max-age=X`
- Automático via Redis EXPIRE
- Fallback para valor padrão (3600s)

#### Manual Invalidation
```python
# Invalidar chave específica
await redis.delete(cache_key)

# Invalidar padrão (wildcard)
await redis.eval("""
    local keys = redis.call('keys', ARGV[1])
    if #keys > 0 then
        return redis.call('del', unpack(keys))
    end
""", 0, "tile_cache:*")
```

## 🛡️ Tratamento de Erros

### Tipos de Erro

#### Upstream Errors
```python
try:
    response = await client.get(url, params=params)
    if response.status_code >= 400:
        metrics.upstream_errors += 1
        return None
except httpx.HTTPError:
    metrics.upstream_errors += 1
    return None
```

#### Redis Errors
```python
try:
    result = await redis.hmget(key, "b", "ct")
except Exception:
    metrics.redis_errors += 1
    return None
```

#### System Errors
```python
try:
    memory_info = psutil.virtual_memory()
except Exception:
    # Fallback values
    return 5000
```

### Circuit Breaker Pattern

```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    async def call(self, func, *args, **kwargs):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
            else:
                raise CircuitBreakerError("Circuit is OPEN")

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e
```

## 📈 Escalabilidade

### Horizontal Scaling

#### Stateless Design
- Sem estado local persistente
- Cache distribuído via Redis
- Métricas coletadas por instância

#### Load Balancing
```nginx
upstream map_cache {
    server cache1:8000;
    server cache2:8000;
    server cache3:8000;
}

server {
    listen 80;
    location / {
        proxy_pass http://map_cache;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

#### Redis Cluster Support
```python
# Configuração para Redis Cluster
redis.RedisCluster(
    startup_nodes=[
        {"host": "redis1", "port": 6379},
        {"host": "redis2", "port": 6380},
        {"host": "redis3", "port": 6381}
    ],
    decode_responses=False
)
```

### Vertical Scaling

#### Memory Optimization
- Cache local limitado a 20% da RAM
- Estruturas de dados eficientes
- Garbage collection tuning

#### CPU Optimization
- Async/await para I/O bound operations
- Thread pool para CPU bound tasks
- Connection pooling para reduzir overhead

## 🔍 Debugging e Observabilidade

### Structured Logging

```python
import structlog

logger = structlog.get_logger()

async def log_request(request, response, duration):
    logger.info(
        "request_processed",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration=duration,
        cache_status=get_cache_status(response),
        user_agent=request.headers.get("User-Agent")
    )
```

### Health Checks

```python
@app.get("/health")
async def health_check():
    # Verificar conectividade Redis
    try:
        await redis.ping()
        redis_status = "healthy"
    except:
        redis_status = "unhealthy"

    # Verificar conectividade HERE Maps
    try:
        response = await http_client.get("https://maps.hereapi.com/v3/base/mc/0/0/0/256/png8?apiKey=test")
        here_status = "healthy" if response.status_code != 401 else "auth_issue"
    except:
        here_status = "unhealthy"

    return {
        "status": "healthy" if redis_status == here_status == "healthy" else "degraded",
        "redis": redis_status,
        "here_maps": here_status,
        "uptime": time.time() - startup_time
    }
```

### Performance Profiling

```python
import cProfile
import pstats

async def profile_request():
    pr = cProfile.Profile()
    pr.enable()

    # Execute request
    result = await process_request(request)

    pr.disable()
    stats = pstats.Stats(pr)
    stats.sort_stats('cumulative').print_stats(20)

    return result
```

## 🚀 Deployment Patterns

### Blue-Green Deployment

```dockerfile
# Dockerfile com multi-stage build
FROM python:3.11-slim as builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user -r requirements.txt

FROM python:3.11-slim as runtime
COPY --from=builder /root/.local /root/.local
COPY . .
EXPOSE 8000
CMD ["python", "main.py"]
```

### Canary Deployment

```yaml
# Kubernetes Deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: map-cache-canary
spec:
  replicas: 1  # Começar com 1 réplica
  selector:
    matchLabels:
      app: map-cache
      version: canary
  template:
    metadata:
      labels:
        app: map-cache
        version: canary
    spec:
      containers:
      - name: map-cache
        image: map-cache:new-version
        ports:
        - containerPort: 8000
```

### Rolling Update Strategy

```yaml
# Docker Compose com rolling update
version: '3.8'
services:
  app:
    image: map-cache:${TAG}
    deploy:
      update_config:
        parallelism: 2    # Atualizar 2 containers por vez
        delay: 10s        # Esperar 10s entre atualizações
        order: start-first  # Iniciar novos antes de parar antigos
```

Esta arquitetura proporciona alta performance, escalabilidade e observabilidade para um sistema de cache de tiles de mapas robusto e eficiente.
