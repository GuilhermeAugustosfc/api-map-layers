#!/bin/bash
# Script de Deploy Simples - API Map Layers (Versão Corrigida)
# Uso: ./deploy_fixed.sh [branch_name] (default: main)

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

# 1. Parar TODOS os containers relacionados (incluindo órfãos)
log "Parando todos os containers relacionados..."
if [ -d "${PROJECT_DIR}" ]; then
    cd "${PROJECT_DIR}"
    # Para containers órfãos e relacionados
    docker-compose down --remove-orphans 2>/dev/null || true
    # Para containers específicos por nome
    docker stop map-tiles-api 2>/dev/null || true
    docker rm map-tiles-api 2>/dev/null || true
    # Para qualquer container usando a porta 8000
    docker ps -q --filter "publish=8000" | xargs -r docker stop 2>/dev/null || true
    docker ps -aq --filter "publish=8000" | xargs -r docker rm 2>/dev/null || true
fi

# 2. Verificar se há processos usando a porta 8000
log "Verificando processos usando a porta 8000..."
if command -v netstat >/dev/null 2>&1; then
    if netstat -tuln | grep -q ":8000 "; then
        warn "Porta 8000 ainda está em uso. Tentando liberar..."
        # Tenta matar processos usando a porta 8000
        PID=$(lsof -ti:8000 2>/dev/null || true)
        if [ ! -z "$PID" ]; then
            warn "Matando processo $PID que está usando a porta 8000..."
            kill -9 $PID 2>/dev/null || true
            sleep 2
        fi
    fi
fi

# 3. Baixar projeto do Git
log "Baixando projeto do repositório..."
rm -rf "${TEMP_DIR}"
git clone --branch "${BRANCH}" --depth 1 "${REPO_URL}" "${TEMP_DIR}"

# 4. Verificar se pasta do projeto existe
if [ -d "${PROJECT_DIR}" ]; then
    log "Pasta do projeto existe. Removendo versão atual..."
    rm -rf "${PROJECT_DIR}"
fi

# 5. Mover projeto para pasta de destino
log "Movendo projeto para pasta de destino..."
mv "${TEMP_DIR}" "${PROJECT_DIR}"

# 6. Entrar na pasta do projeto
cd "${PROJECT_DIR}"

# 7. Verificar arquivos essenciais
log "Verificando arquivos essenciais..."
if [ ! -f "main.py" ]; then
    error "Arquivo main.py não encontrado!"
fi
if [ ! -f "ativos_endpoints.py" ]; then
    error "Arquivo ativos_endpoints.py não encontrado!"
fi
if [ ! -f "docker-compose.yml" ]; then
    error "Arquivo docker-compose.yml não encontrado!"
fi
if [ ! -f "Dockerfile" ]; then
    error "Arquivo Dockerfile não encontrado!"
fi
if [ ! -f "requirements.txt" ]; then
    error "Arquivo requirements.txt não encontrado!"
fi
log "✅ Todos os arquivos essenciais encontrados"

# 8. Build e start da nova aplicação
log "Build e start da nova aplicação..."
docker-compose up -d --build --force-recreate --remove-orphans

# 9. Aguardar aplicação estar pronta
log "Aguardando aplicação estar pronta..."
for i in {1..60}; do
    if curl -f http://localhost:8000/metrics >/dev/null 2>&1; then
        log "Aplicação está respondendo!"
        break
    fi
    if [ $i -eq 60 ]; then
        error "Aplicação não está respondendo após 60 segundos"
    fi
    sleep 1
done

# 10. Verificar se tudo está funcionando
log "Verificando se tudo está funcionando..."
sleep 5

if curl -f http://localhost:8000/metrics >/dev/null 2>&1; then
    log "Deploy realizado com sucesso!"
    
    # Testar os novos endpoints
    log "Testando novos endpoints..."
    
    # Teste do endpoint ativos_mapa_atual (com timeout)
    if timeout 10 curl -f http://localhost:8000/ativos_mapa_atual >/dev/null 2>&1; then
        log "✅ Endpoint /ativos_mapa_atual funcionando"
    else
        warn "⚠️  Endpoint /ativos_mapa_atual pode ter problemas (timeout esperado)"
    fi
    
    # Teste do endpoint ativos_mapa_atualizado
    if curl -f http://localhost:8000/ativos_mapa_atualizado >/dev/null 2>&1; then
        log "✅ Endpoint /ativos_mapa_atualizado funcionando"
    else
        warn "⚠️  Endpoint /ativos_mapa_atualizado pode ter problemas"
    fi
    
    # Mostrar status dos containers
    log "Status dos containers:"
    docker-compose ps
    
    # Mostrar logs recentes
    log "Logs recentes:"
    docker-compose logs --tail=10 map-tiles
    
else
    error "Deploy falhou. Aplicação não está respondendo."
fi

log "Deploy concluído!"
