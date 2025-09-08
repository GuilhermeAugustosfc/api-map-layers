#!/bin/bash
# Script para limpeza completa antes do deploy
# Uso: ./cleanup_deploy.sh

set -e

# Cores para output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[$(date +'%H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%H:%M:%S')] ERRO: $1${NC}"
    exit 1
}

PROJECT_DIR="/var/www/html/api-map-layer"

log "Iniciando limpeza completa do ambiente..."

# 1. Parar todos os containers relacionados
log "Parando todos os containers relacionados..."
if [ -d "${PROJECT_DIR}" ]; then
    cd "${PROJECT_DIR}"
    docker-compose down --remove-orphans 2>/dev/null || true
fi

# 2. Parar containers específicos por nome
log "Parando containers específicos..."
docker stop map-tiles-api 2>/dev/null || true
docker rm map-tiles-api 2>/dev/null || true

# 3. Parar qualquer container usando a porta 8000
log "Parando containers usando a porta 8000..."
CONTAINERS_USING_PORT=$(docker ps -q --filter "publish=8000" 2>/dev/null || true)
if [ ! -z "$CONTAINERS_USING_PORT" ]; then
    echo "$CONTAINERS_USING_PORT" | xargs docker stop 2>/dev/null || true
    echo "$CONTAINERS_USING_PORT" | xargs docker rm 2>/dev/null || true
fi

# 4. Remover containers órfãos
log "Removendo containers órfãos..."
docker container prune -f 2>/dev/null || true

# 5. Verificar processos usando a porta 8000
log "Verificando processos usando a porta 8000..."
if command -v lsof >/dev/null 2>&1; then
    PIDS=$(lsof -ti:8000 2>/dev/null || true)
    if [ ! -z "$PIDS" ]; then
        warn "Encontrados processos usando a porta 8000: $PIDS"
        echo "$PIDS" | xargs kill -9 2>/dev/null || true
        sleep 2
    fi
fi

# 6. Verificar com netstat se disponível
if command -v netstat >/dev/null 2>&1; then
    if netstat -tuln | grep -q ":8000 "; then
        warn "Porta 8000 ainda está em uso após limpeza"
        netstat -tuln | grep ":8000 "
    else
        log "✅ Porta 8000 está livre"
    fi
fi

# 7. Limpar imagens Docker antigas (opcional)
log "Limpando imagens Docker antigas..."
docker image prune -f 2>/dev/null || true

# 8. Verificar espaço em disco
log "Verificando espaço em disco..."
df -h /var/www/html/ 2>/dev/null || true

log "Limpeza concluída!"
log "Agora você pode executar o deploy com: ./deploy_fixed.sh"
