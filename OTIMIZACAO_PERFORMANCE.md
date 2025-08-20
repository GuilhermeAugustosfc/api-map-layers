# Otimização e Performance - HERE Proxy API

## Visão Geral

Este documento detalha as recomendações e próximos passos para otimizar a performance, escalabilidade e observabilidade da API de proxy do HERE Maps.

## Estado Atual (Bom)

- ✅ **Async com httpx**: Pool de conexões e keep-alive configurados
- ✅ **Cache em memória**: TTL por tile e por índice
- ✅ **Métricas**: Contadores de hits/misses/upstream por índice
- ✅ **CORS**: Configurado para frontend
- ✅ **Docker**: Configuração básica funcional

## Plano de Otimizações

### 1. Streaming de Respostas (Latência/Memória)

**Objetivo**: Reduzir TTFB e pico de memória

**Implementação**:

```python
# Usar StreamingResponse com httpx.stream()
async def here_proxy_streaming(path: str, request: Request):
    # ... lógica de cache ...

    if cached:
        return StreamingResponse(
            iter([content_bytes]),
            media_type=content_type,
            headers={"X-Cache": "HIT", "X-Index": indice}
        )

    # Para upstream
    async with client.stream("GET", here_url, params=params_items) as resp:
        return StreamingResponse(
            resp.aiter_bytes(),
            media_type=resp.headers.get("content-type", "image/png"),
            headers={"X-Cache": "MISS", "X-Index": indice}
        )
```

**Benefícios**:

- Menor TTFB (Time To First Byte)
- Menor pico de memória em tiles grandes
- Melhor experiência do usuário

### 2. HTTP/2 no Upstream (Paralelismo)

**Objetivo**: Habilitar multiplexação para melhor performance

**Implementação**:

```bash
# Instalar suporte HTTP/2
pip install "httpx[http2]"
```

```python
# Ativar no cliente
app.state.http_client = httpx.AsyncClient(
    http2=True,  # Habilitar HTTP/2
    timeout=httpx.Timeout(10.0, read=30.0, connect=5.0),
    limits=httpx.Limits(max_connections=200, max_keepalive_connections=100),
)
```

**Benefícios**:

- Multiplexação de conexões
- Redução de latência média em alto RPS
- Melhor utilização de banda

### 3. Servidor Mais Rápido (Uvicorn Standard)

**Objetivo**: Otimizar o servidor ASGI

**Implementação**:

```bash
# Instalar uvicorn com otimizações
pip install "uvicorn[standard]"
```

```bash
# Executar com otimizações
uvicorn main:app --host 0.0.0.0 --port 8000 \
  --http httptools \
  --loop uvloop \
  --workers 2
```

**Benefícios**:

- httptools: Parser HTTP mais rápido
- uvloop: Loop de eventos otimizado
- Workers: Paralelismo de processos

### 4. Cache com Limites (Evicção/LRU)

**Objetivo**: Evitar crescimento indefinido de memória

**Opção A - In-Memory LRU**:

```python
from cachetools import LRUCache

# Substituir dict por LRU
tile_cache = LRUCache(maxsize=50000)  # 50k entradas máximas
```

**Opção B - Redis (Recomendado para multi-worker)**:

```python
import redis.asyncio as redis

# Cliente Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Cache com TTL
async def get_cached_tile(cache_key: str):
    return await redis_client.get(cache_key)

async def set_cached_tile(cache_key: str, content: bytes, ttl: int):
    await redis_client.setex(cache_key, ttl, content)
```

**Benefícios**:

- Controle de memória
- Cache compartilhado entre workers
- Latência estável em alto tráfego

### 5. Redução de Contenção de Locks

**Objetivo**: Otimizar para alto RPS

**Implementação**:

```python
# Fast-path sem lock para leitura
async def get_cached_tile_fast(cache_key: str):
    # Leitura sem lock (thread-safe para dict em Python)
    cached = tile_cache.get(cache_key)
    if cached and cached[2] > time.time():
        return cached
    return None

# Lock apenas para escrita
async def set_cached_tile_safe(cache_key: str, content: bytes, ttl: int):
    async with cache_lock:
        tile_cache[cache_key] = (content, content_type, time.time() + ttl)
```

**Benefícios**:

- Menor latência em hits
- Melhor throughput
- Menos contenção

### 6. Observabilidade Avançada

**Objetivo**: Métricas e logs estruturados

**Prometheus/Grafana**:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: "here-proxy"
    static_configs:
      - targets: ["localhost:8000"]
    metrics_path: "/metrics/prometheus"
```

**Dashboards Sugeridos**:

- Hit ratio por índice
- Upstream calls vs cache hits
- Latência p50/p95/p99
- Erros por índice

**Logs Estruturados**:

```python
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def log_request(path: str, indice: str, cache_status: str, status: int, latency: float):
    logger.info(json.dumps({
        "method": "GET",
        "path": path,
        "indice": indice,
        "cache_status": cache_status,
        "status": status,
        "latency_ms": round(latency * 1000, 2),
        "timestamp": time.time()
    }))
```

### 7. Resiliência (Upstream HERE)

**Objetivo**: Lidar com falhas do HERE

**Implementação**:

```python
import tenacity

@tenacity.retry(
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, min=4, max=10),
    retry=tenacity.retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError))
)
async def fetch_from_here_with_retry(client, url, params):
    return await client.get(url, params=params)
```

**Benefícios**:

- Retry automático para falhas transitórias
- Backoff exponencial
- Melhor disponibilidade

### 8. CDN/Proxy na Frente

**Objetivo**: Cache externo adicional

**Cloudflare**:

- Cache por query (inclui índice)
- Respeitar Cache-Control
- DDoS protection

**NGINX**:

```nginx
proxy_cache_path /tmp/nginx_cache levels=1:2 keys_zone=here_cache:10m max_size=10g inactive=60m;

location /here-proxy/ {
    proxy_cache here_cache;
    proxy_cache_key "$request_uri";
    proxy_cache_valid 200 1h;
    proxy_pass http://backend:8000;
}
```

### 9. Segurança e Rate Limiting

**Objetivo**: Proteger contra abuso

**Rate Limiting por Índice**:

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.get("/here-proxy/{path:path}")
@limiter.limit("100/minute")  # 100 requests por minuto por IP
async def here_proxy(path: str, request: Request):
    # ... implementação ...
```

**API Key no Servidor**:

```python
import os

HERE_API_KEY = os.getenv("HERE_API_KEY")

# Remover apiKey do request e usar a do servidor
params_items = [
    (k, v) for (k, v) in request.query_params.multi_items()
    if k not in ["indice", "apiKey"]
]
params_items.append(("apiKey", HERE_API_KEY))
```

### 10. Escala Horizontal

**Objetivo**: Suportar múltiplos workers/containers

**Docker Compose com Redis**:

```yaml
version: "3.8"
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  here-proxy:
    build: .
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://redis:6379
    depends_on:
      - redis
    deploy:
      replicas: 3
```

**Kubernetes HPA**:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: here-proxy-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: here-proxy
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

## Roteiro de Implementação

### Fase 1 - Otimizações Básicas (1-2 semanas)

1. ✅ Uvicorn standard + ajustar healthcheck do Docker
2. 🔄 LRU no cache in-memory (maxsize) ou Redis
3. 🔄 Streaming de respostas
4. 🔄 HTTP/2 no httpx

### Fase 2 - Observabilidade (1 semana)

1. 🔄 Logs estruturados
2. 🔄 Dashboards Grafana
3. 🔄 Métricas avançadas

### Fase 3 - Produção (1-2 semanas)

1. 🔄 Rate limiting por índice
2. 🔄 CDN/NGINX opcional
3. 🔄 Resiliência e retry
4. 🔄 Escala horizontal

### Fase 4 - Monitoramento (Contínuo)

1. 🔄 Alertas baseados em métricas
2. 🔄 SLOs/SLIs definidos
3. 🔄 Otimizações baseadas em dados reais

## Métricas de Sucesso

### Performance

- **Latência**: p95 < 200ms para cache hits
- **Throughput**: 1000+ RPS por worker
- **Hit Ratio**: > 80% em produção

### Recursos

- **CPU**: < 70% média
- **Memória**: < 2GB por container
- **Rede**: < 100MB/s upstream

### Disponibilidade

- **Uptime**: > 99.9%
- **Erros**: < 0.1% upstream errors
- **Cache**: Hit ratio estável

## Ferramentas de Benchmark

### K6 (Teste de Carga)

```javascript
import http from "k6/http";
import { check } from "k6";

export const options = {
  stages: [
    { duration: "2m", target: 100 }, // Ramp up
    { duration: "5m", target: 100 }, // Stay
    { duration: "2m", target: 0 }, // Ramp down
  ],
};

export default function () {
  const url =
    "http://localhost:8000/here-proxy/mc/5/15/13/png?indice=123&size=512&apiKey=test&style=explore.day&lang=en";

  const response = http.get(url);

  check(response, {
    "status is 200": (r) => r.status === 200,
    "response time < 200ms": (r) => r.timings.duration < 200,
    "cache header present": (r) => r.headers["X-Cache"] !== undefined,
  });
}
```

### wrk (Teste Simples)

```bash
# Teste básico
wrk -t12 -c400 -d30s http://localhost:8000/here-proxy/mc/5/15/13/png?indice=123&size=512

# Teste com Lua para variar índices
wrk -t12 -c400 -d30s -s test.lua http://localhost:8000/here-proxy/mc/5/15/13/png
```

## Riscos e Atenções

### Riscos Técnicos

- **Multi-worker sem cache compartilhado**: Reduz hit ratio
- **Streaming**: Aumenta conexões abertas; monitore limites do SO
- **HTTP/2**: Requer `h2`; teste bem antes de ativar em produção

### Riscos de Negócio

- **Custo HERE**: Monitorar uso para evitar surpresas
- **SLA**: Definir expectativas claras com stakeholders
- **Cache invalidation**: Estratégia para atualizações de tiles

## Checklist de Configuração

### Variáveis de Ambiente

```bash
# Obrigatórias
HERE_API_KEY=your_api_key_here

# Opcionais
CACHE_MAXSIZE=50000
CACHE_TTL_CAP=3600
REDIS_URL=redis://localhost:6379
LOG_LEVEL=INFO
```

### Recursos do Sistema

```bash
# Aumentar limites do SO
ulimit -n 65536  # File descriptors
sysctl -w net.core.somaxconn=65535  # TCP backlog
```

### Monitoramento

- [ ] Prometheus configurado
- [ ] Grafana dashboards criados
- [ ] Alertas configurados
- [ ] Logs centralizados
- [ ] Métricas de negócio definidas

## Conclusão

Este roteiro de otimização visa transformar a API de proxy do HERE em uma solução de produção robusta, escalável e observável. As implementações devem ser feitas incrementalmente, sempre medindo o impacto antes e depois de cada mudança.

**Prioridade**: Foque primeiro nas otimizações que trazem maior impacto (cache LRU, streaming, HTTP/2) e depois evolua para recursos mais avançados conforme a necessidade do negócio.
