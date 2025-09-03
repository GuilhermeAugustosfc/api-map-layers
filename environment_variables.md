# Variáveis de Ambiente - Map Layer Cache

Este documento descreve todas as variáveis de ambiente que podem ser configuradas para personalizar o comportamento da aplicação.

## Como usar

### Arquivo config.env
1. Use o arquivo `config.env` criado no projeto
2. Renomeie para `.env` 


## Variáveis Disponíveis

### Configuração do Redis

| Variável | Descrição | Valor Padrão | Exemplo |
|----------|-----------|--------------|---------|
| `REDIS_HOST` | Host do servidor Redis | `redis-dev.ops.ftrack.me` | `localhost` |
| `REDIS_PORT` | Porta do servidor Redis | `6379` | `6379` |
| `REDIS_DB` | Banco de dados Redis (0-15) | `0` | `1` |
| `REDIS_PASSWORD` | Senha do Redis | *(vazio)* | `minha_senha` |
| `REDIS_KEY_PREFIX` | Prefixo para chaves do cache | `tile_cache:` | `prod_cache:` |
| `REDIS_SOCKET_TIMEOUT` | Timeout do socket (segundos) | `1.0` | `2.0` |
| `REDIS_SOCKET_CONNECT_TIMEOUT` | Timeout de conexão (segundos) | `1.0` | `2.0` |
| `REDIS_HEALTH_CHECK_INTERVAL` | Intervalo health check (segundos) | `30` | `60` |

### Configuração do Cache

| Variável | Descrição | Valor Padrão | Exemplo |
|----------|-----------|--------------|---------|
| `CACHE_TTL_SECONDS` | TTL padrão do cache (segundos) | `3600` | `7200` |
| `AVERAGE_IMAGE_SIZE_KB` | Tamanho médio das imagens (KB) | `400` | `500` |
| `MAX_MEMORY_PERCENT` | % máxima da memória para cache | `20` | `30` |

### Configuração HTTP

| Variável | Descrição | Valor Padrão | Exemplo |
|----------|-----------|--------------|---------|
| `HTTP_TIMEOUT_CONNECT` | Timeout de conexão (segundos) | `3.0` | `5.0` |
| `HTTP_TIMEOUT_READ` | Timeout de leitura (segundos) | `15.0` | `20.0` |
| `HTTP_TIMEOUT_TOTAL` | Timeout total (segundos) | `5.0` | `10.0` |
| `HTTP_MAX_CONNECTIONS` | Máximo de conexões simultâneas | `500` | `1000` |
| `HTTP_MAX_KEEPALIVE_CONNECTIONS` | Máximo de conexões keep-alive | `200` | `400` |

### Configuração do Servidor

| Variável | Descrição | Valor Padrão | Exemplo |
|----------|-----------|--------------|---------|
| `SERVER_HOST` | Host do servidor | `0.0.0.0` | `127.0.0.1` |
| `SERVER_PORT` | Porta do servidor | `8000` | `8080` |

### Configuração HERE Maps

| Variável | Descrição | Valor Padrão | Exemplo |
|----------|-----------|--------------|---------|
| `HERE_MAPS_BASE_URL` | URL base da API HERE Maps | `https://maps.hereapi.com/v3/base/mc/` | `https://api.here.com/maps/v3/base/mc/` |

## Exemplo de arquivo .env

```bash
# Redis
REDIS_HOST=redis-prod.company.com
REDIS_PORT=6379
REDIS_PASSWORD=minha_senha_segura
REDIS_KEY_PREFIX=prod_tile_cache:

# Cache
CACHE_TTL_SECONDS=7200
MAX_MEMORY_PERCENT=30

# HTTP
HTTP_MAX_CONNECTIONS=1000
HTTP_TIMEOUT_TOTAL=10.0

# Servidor
SERVER_PORT=8080

# HERE Maps
HERE_MAPS_BASE_URL=https://api.here.com/maps/v3/base/mc/
```
