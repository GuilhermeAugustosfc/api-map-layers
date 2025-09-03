# 🗺️ Map Layer Cache - Proxy Inteligente HERE Maps

Um proxy assíncrono de alta performance para tiles do HERE Maps com sistema de cache multi-nível (local + Redis) e monitoramento avançado.

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.116+-green.svg)](https://fastapi.tiangolo.com/)
[![Redis](https://img.shields.io/badge/Redis-Latest-red.svg)](https://redis.io/)
[![Docker](https://img.shields.io/badge/Docker-Supported-blue.svg)](https://www.docker.com/)

## 📋 Visão Geral

Este projeto implementa um **proxy inteligente** para a API de tiles do HERE Maps com as seguintes características principais:

- 🚀 **Cache Multi-Nível**: Memória local + Redis distribuído
- ⚡ **Alta Performance**: HTTP/2, pool de conexões e algoritmos otimizados
- 📊 **Monitoramento**: Métricas detalhadas e status do sistema
- 🔧 **Configurável**: Variáveis de ambiente para todos os parâmetros
- 🐳 **Container Ready**: Docker e Docker Compose incluídos
- 🔄 **Auto-invalidação**: Cache inteligente com tracking Redis

## 🏗️ Arquitetura
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Cliente       │───▶│  Map Layer     │───▶│   HERE Maps     │
│   (Browser)     │    │   Cache Proxy  │    │   API           │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │ Local Memory    │
                       │   Cache         │
                       └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │   Redis Cache   │
                       │  (Distribuído)  │
                       └─────────────────┘

### Componentes Principais

1. **FastAPI Application**: Servidor web assíncrono
2. **Local Cache**: Cache em memória com limite dinâmico
3. **Redis Cache**: Cache distribuído com invalidação automática
4. **HTTP Client**: Pool otimizado para HERE Maps API
5. **Metrics System**: Sistema de métricas e monitoramento
6. **Configuration**: Configuração via variáveis de ambiente

## 🎯 Funcionalidades

### ✅ Proxy HERE Maps
- Proxy transparente para tiles do HERE Maps
- Suporte completo aos parâmetros da API original
- Headers HTTP preservados e otimizados

### ✅ Cache Multi-Nível
- **Cache Local**: Acesso em ~0ms (memória RAM)
- **Cache Redis**: Cache distribuído e compartilhado
- **TTL Inteligente**: Baseado nos headers `Cache-Control` da API
- **Invalidação Automática**: Via Redis keyspace notifications

### ✅ Monitoramento Avançado
- Métricas de performance em tempo real
- Status do sistema (CPU, memória, disco)
- Taxas de cache hit/miss
- Monitoramento de erros

### ✅ Otimizações de Performance
- HTTP/2 para melhor throughput
- Pool de conexões configurável
- Timeouts otimizados
- Cache de funções e regex compiladas

## 🚀 Instalação e Execução

### Pré-requisitos

- Python 3.11+
- Redis Server (local ou remoto)
- Conta HERE Maps API (opcional para desenvolvimento)

### Instalação

```bash
# Clone o repositório
git clone <repository-url>
cd map-layer-cache

# Instale as dependências
pip install -r requirements.txt
```

### Configuração

1. **Arquivo de configuração**:
```bash
# Copie o arquivo de configuração
cp config.env .env

# Edite as variáveis conforme necessário
nano .env
```

2. **Variáveis principais**:
```bash
# Redis
REDIS_HOST=redis-dev.ops.ftrack.me
REDIS_PORT=6379
REDIS_PASSWORD=sua_senha

# Cache
CACHE_TTL_SECONDS=3600
MAX_MEMORY_PERCENT=20

# Servidor
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
```

### Execução

```bash
# Desenvolvimento
python main.py

# Produção com Uvicorn
uvicorn main:app --host 0.0.0.0 --port 8000

# Com reload automático
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## 🐳 Docker

### Docker Compose (Recomendado)

```bash
# Subir toda a stack
docker-compose up -d

# Apenas a aplicação
docker-compose up app -d

# Com logs
docker-compose up -d && docker-compose logs -f
```

### Docker Standalone

```bash
# Build da imagem
docker build -t map-layer-cache .

# Executar
docker run -p 8000:8000 \
  -e REDIS_HOST=host.docker.internal \
  map-layer-cache
```

## 📡 API Endpoints

### Proxy HERE Maps

```http
GET /here-proxy/{path}
```

**Exemplo**:
```bash
# Tile normal
GET /here-proxy/mc/15/26480/16920/256/png8?apiKey=YOUR_API_KEY

# Satellite
GET /here-proxy/mc/15/26480/16920/256/jpg?apiKey=YOUR_API_KEY
```

**Parâmetros suportados**:
- `apiKey`: Chave da API HERE Maps
- `style`: Estilo do mapa (normal, satellite, etc.)
- Todos os parâmetros originais da API HERE

### Monitoramento

#### Status do Sistema
```http
GET /system-status
```

Retorna informações detalhadas sobre:
- Recursos do sistema (CPU, memória, disco)
- Status da aplicação
- Utilização do cache local
- Uptime do sistema

#### Métricas de Performance
```http
GET /metrics
```

Retorna métricas JSON:
```json
{
  "total_requests": 1500,
  "cache_hits": 1200,
  "local_cache_hits": 800,
  "redis_cache_hits": 400,
  "upstream_calls": 300,
  "cache_hit_ratio": 0.8,
  "redis_error_rate": 0.0
}
```

#### Métricas Prometheus
```http
GET /metrics/prometheus
```

Formato compatível com Prometheus:
```text
proxy_total_requisicoes 1500
proxy_cache_acertos_total 1200
proxy_cache_local_acertos_total 800
proxy_taxa_cache_acerto 0.8
```

## ⚙️ Configuração Avançada

### Variáveis de Ambiente

#### Redis Configuration
| Variável | Descrição | Padrão |
|----------|-----------|---------|
| `REDIS_HOST` | Host do Redis | `redis-dev.ops.ftrack.me` |
| `REDIS_PORT` | Porta do Redis | `6379` |
| `REDIS_DB` | Database Redis | `0` |
| `REDIS_PASSWORD` | Senha Redis | *(vazio)* |
| `REDIS_KEY_PREFIX` | Prefixo das chaves | `tile_cache:` |

#### Cache Configuration
| Variável | Descrição | Padrão |
|----------|-----------|---------|
| `CACHE_TTL_SECONDS` | TTL padrão (segundos) | `3600` |
| `AVERAGE_IMAGE_SIZE_KB` | Tamanho médio tiles (KB) | `400` |
| `MAX_MEMORY_PERCENT` | % memória para cache local | `20` |

#### HTTP Configuration
| Variável | Descrição | Padrão |
|----------|-----------|---------|
| `HTTP_TIMEOUT_CONNECT` | Timeout conexão (s) | `3.0` |
| `HTTP_TIMEOUT_READ` | Timeout leitura (s) | `15.0` |
| `HTTP_TIMEOUT_TOTAL` | Timeout total (s) | `5.0` |
| `HTTP_MAX_CONNECTIONS` | Máx. conexões simultâneas | `500` |
| `HTTP_MAX_KEEPALIVE_CONNECTIONS` | Conexões keep-alive | `200` |

### Cache Strategy

O sistema utiliza uma estratégia de cache em **duas camadas**:

1. **Cache Local (L1)**:
   - Armazenamento em memória RAM
   - Acesso ultra-rápido (~0ms)
   - Limitado a 20% da memória disponível
   - Algoritmo LRU para remoção

2. **Cache Redis (L2)**:
   - Cache distribuído
   - Compartilhado entre instâncias
   - Persistência automática
   - Invalidação via keyspace notifications

### Fluxo de Cache

```
Requisição → Cache Local → Cache Redis → HERE Maps API
     ↓             ↓             ↓             ↓
   HIT           MISS         HIT           MISS
     ↓             ↓             ↓             ↓
 Retornar     Verificar      Retornar     Buscar
  cache         Redis          cache       upstream
```

## 📊 Monitoramento

### Métricas Principais

- **Total de Requisições**: Contador global
- **Cache Hit Ratio**: Taxa de acertos no cache
- **Latência**: Tempo de resposta médio
- **Erros**: Taxa de erro por componente
- **Uso de Recursos**: CPU, memória, rede

### Dashboards

As métricas são expostas em formato Prometheus, permitindo integração com:
- Grafana
- Prometheus
- DataDog
- New Relic

## 🔧 Desenvolvimento

### Estrutura do Projeto

```
map-layer-cache/
├── main.py                 # Aplicação principal
├── config.env             # Configuração base
├── environment_variables.md # Documentação variáveis
├── requirements.txt       # Dependências Python
├── Dockerfile            # Container Docker
├── docker-compose.yml    # Stack completa
├── deploy.sh            # Script de deploy
└── test_redis_connection.py # Testes de conectividade
```

### Scripts Úteis

```bash
# Testar conexão Redis
python test_redis_connection.py

# Executar em modo desenvolvimento
python main.py

# Deploy com Docker
./deploy.sh
```

### Debugging

```bash
# Logs detalhados
docker-compose logs -f app

# Acessar container
docker-compose exec app bash

# Verificar métricas
curl http://localhost:8000/metrics
```

## 🚀 Deploy em Produção

### Pré-requisitos

- Redis cluster ou instância dedicada
- Load balancer (nginx, traefik, etc.)
- Monitoramento (Prometheus + Grafana)
- Certificado SSL

### Configuração Produção

```bash
# config.env para produção
REDIS_HOST=redis-prod.company.com
REDIS_PASSWORD=super_secret_password
REDIS_DB=1

CACHE_TTL_SECONDS=7200
MAX_MEMORY_PERCENT=30

HTTP_MAX_CONNECTIONS=1000
HTTP_MAX_KEEPALIVE_CONNECTIONS=500

SERVER_HOST=0.0.0.0
SERVER_PORT=8080
```

### Docker Compose Produção

```yaml
version: '3.8'
services:
  app:
    image: map-layer-cache:latest
    environment:
      - REDIS_HOST=redis-prod.company.com
      - REDIS_PASSWORD=${REDIS_PASSWORD}
    env_file:
      - .env
    deploy:
      replicas: 3
      resources:
        limits:
          memory: 1G
        reservations:
          memory: 512M
```

## 🔐 Segurança

### Recomendações

- ✅ Use HTTPS em produção
- ✅ Configure firewall adequado
- ✅ Use senhas fortes para Redis
- ✅ Monitore logs de acesso
- ✅ Implemente rate limiting
- ✅ Use secrets management (Vault, AWS Secrets, etc.)

### Headers de Segurança

O proxy automaticamente adiciona headers de segurança:
- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `X-Cache: HIT/LOCAL/REDIS/MISS`

## 🐛 Troubleshooting

### Problemas Comuns

#### Cache não funcionando
```bash
# Verificar conexão Redis
python test_redis_connection.py

# Verificar métricas
curl http://localhost:8000/metrics
```

#### Alto uso de memória
```bash
# Ajustar limite de cache
export MAX_MEMORY_PERCENT=15

# Verificar status
curl http://localhost:8000/system-status
```

#### Lentidão
```bash
# Ajustar timeouts
export HTTP_TIMEOUT_TOTAL=10.0
export HTTP_MAX_CONNECTIONS=1000

# Verificar performance Redis
redis-cli --latency
```

## 📈 Performance

### Benchmarks

- **Cache Local**: ~0.1ms latency
- **Cache Redis**: ~1-5ms latency
- **HERE Maps API**: ~100-500ms latency
- **Throughput**: 1000+ req/s (com cache)
- **Memory Usage**: < 500MB (configurável)

### Otimizações

- HTTP/2 multiplexing
- Connection pooling
- Gzip compression
- Lazy loading
- Memory-efficient data structures


