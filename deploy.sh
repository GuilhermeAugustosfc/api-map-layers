#!/bin/bash

# Script de Deploy Simples - API Map Layers
# Uso: ./deploy.sh [branch_name] (default: main)

set -e

# Configurações
REPO_URL="https://github.com/GuilhermeAugustosfc/api-map-layers.git"
BRANCH="${1:-main}"
PROJECT_DIR="/var/www/html/api-map-layer"
TEMP_DIR="/tmp/api-map-layers-$(date +%Y%m%d_%H%M%S)"

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

log "Iniciando deploy da branch: ${BRANCH}"

# 1. Baixar projeto do Git
log "Baixando projeto do repositório..."
rm -rf "${TEMP_DIR}"
git clone --branch "${BRANCH}" --depth 1 "${REPO_URL}" "${TEMP_DIR}"

# 2. Verificar se pasta do projeto existe
if [ -d "${PROJECT_DIR}" ]; then
    log "Pasta do projeto existe. Removendo versão atual..."
    rm -rf "${PROJECT_DIR}"
fi

# 3. Mover projeto para pasta de destino
log "Movendo projeto para pasta de destino..."
mv "${TEMP_DIR}" "${PROJECT_DIR}"

# 4. Entrar na pasta do projeto
cd "${PROJECT_DIR}"

# 5. Parar aplicação atual se estiver rodando
log "Verificando se aplicação está rodando..."
if [ -f "docker-compose.yml" ] && docker-compose ps | grep -q "Up"; then
    log "Parando aplicação atual..."
    docker-compose down
fi

# 6. Build e start da nova aplicação
log "Build e start da nova aplicação..."
docker-compose up -d --build --force-recreate

# 7. Aguardar aplicação estar pronta
log "Aguardando aplicação estar pronta..."
for i in {1..45}; do
    if curl -f http://localhost:8000/metrics >/dev/null 2>&1; then
        log "Aplicação está respondendo!"
        break
    fi
    if [ $i -eq 45 ]; then
        error "Aplicação não está respondendo após 45 segundos"
    fi
    sleep 1
done

# 8. Verificar se tudo está funcionando
log "Verificando se tudo está funcionando..."
sleep 5

if curl -f http://localhost:8000/metrics >/dev/null 2>&1; then
    log "Deploy realizado com sucesso!"
    
    # Mostrar status dos containers
    log "Status dos containers:"
    docker-compose ps
    
    # Mostrar logs recentes
    log "Logs recentes:"
    docker-compose logs --tail=5 here-proxy
    
else
    error "Deploy falhou. Aplicação não está respondendo."
fi

log "Deploy concluído!"
