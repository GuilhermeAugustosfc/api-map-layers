#!/bin/bash
# Script de Deploy Completo - API Map Layers
# Combina limpeza + deploy em um só comando
# Uso: ./deploy_complete.sh [branch_name] (default: main)

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
BLUE='\033[0;34m'
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

info() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')] $1${NC}"
}

log "🚀 Iniciando deploy completo da branch: ${BRANCH}"

# ===== FASE 1: LIMPEZA COMPLETA =====
info "🧹 FASE 1: Limpeza completa do ambiente..."

# 1.1 Parar todos os containers relacionados
log "Parando todos os containers relacionados..."
if [ -d "${PROJECT_DIR}" ]; then
    cd "${PROJECT_DIR}"
    docker-compose down --remove-orphans 2>/dev/null || true
fi

# 1.2 Parar containers específicos por nome
log "Parando containers específicos..."
docker stop map-tiles-api 2>/dev/null || true
docker rm map-tiles-api 2>/dev/null || true

# 1.3 Parar qualquer container usando a porta 8000
log "Parando containers usando a porta 8000..."
CONTAINERS_USING_PORT=$(docker ps -q --filter "publish=8000" 2>/dev/null || true)
if [ ! -z "$CONTAINERS_USING_PORT" ]; then
    echo "$CONTAINERS_USING_PORT" | xargs docker stop 2>/dev/null || true
    echo "$CONTAINERS_USING_PORT" | xargs docker rm 2>/dev/null || true
fi

# 1.4 Verificar processos usando a porta 8000
log "Verificando processos usando a porta 8000..."
if command -v lsof >/dev/null 2>&1; then
    PIDS=$(lsof -ti:8000 2>/dev/null || true)
    if [ ! -z "$PIDS" ]; then
        warn "Encontrados processos usando a porta 8000: $PIDS"
        echo "$PIDS" | xargs kill -9 2>/dev/null || true
        sleep 2
    fi
fi

# 1.5 Limpar containers órfãos
log "Limpando containers órfãos..."
docker container prune -f 2>/dev/null || true

# 1.6 Verificar se porta está livre
if command -v netstat >/dev/null 2>&1; then
    if netstat -tuln | grep -q ":8000 "; then
        warn "⚠️  Porta 8000 ainda está em uso após limpeza"
    else
        log "✅ Porta 8000 está livre"
    fi
fi

# ===== FASE 2: DOWNLOAD E PREPARAÇÃO =====
info "📥 FASE 2: Download e preparação do código..."

# 2.1 Baixar projeto do Git
log "Baixando projeto do repositório..."
rm -rf "${TEMP_DIR}"
git clone --branch "${BRANCH}" --depth 1 "${REPO_URL}" "${TEMP_DIR}"

# 2.2 Verificar se pasta do projeto existe
if [ -d "${PROJECT_DIR}" ]; then
    log "Pasta do projeto existe. Removendo versão atual..."
    rm -rf "${PROJECT_DIR}"
fi

# 2.3 Mover projeto para pasta de destino
log "Movendo projeto para pasta de destino..."
mv "${TEMP_DIR}" "${PROJECT_DIR}"

# 2.4 Entrar na pasta do projeto
cd "${PROJECT_DIR}"

# 2.5 Verificar arquivos essenciais
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

# ===== FASE 3: BUILD E DEPLOY =====
info "🔨 FASE 3: Build e deploy da aplicação..."

# 3.1 Build e start da nova aplicação
log "Build e start da nova aplicação..."
docker-compose up -d --build --force-recreate --remove-orphans

# 3.2 Aguardar aplicação estar pronta
log "Aguardando aplicação estar pronta..."
for i in {1..60}; do
    if curl -f http://localhost:8000/metrics >/dev/null 2>&1; then
        log "✅ Aplicação está respondendo!"
        break
    fi
    if [ $i -eq 60 ]; then
        error "❌ Aplicação não está respondendo após 60 segundos"
    fi
    if [ $((i % 10)) -eq 0 ]; then
        warn "Aguardando... (${i}/60 segundos)"
    fi
    sleep 1
done

# ===== FASE 4: TESTES E VERIFICAÇÃO =====
info "🧪 FASE 4: Testes e verificação..."

# 4.1 Aguardar estabilização
log "Aguardando estabilização da aplicação..."
sleep 5

# 4.2 Testar endpoint de métricas
if curl -f http://localhost:8000/metrics >/dev/null 2>&1; then
    log "✅ Endpoint /metrics funcionando"
else
    error "❌ Endpoint /metrics não está funcionando"
fi

# 4.3 Testar endpoint de status do sistema
if curl -f http://localhost:8000/system-status >/dev/null 2>&1; then
    log "✅ Endpoint /system-status funcionando"
else
    warn "⚠️  Endpoint /system-status pode ter problemas"
fi

# 4.4 Testar novos endpoints
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

# ===== FASE 5: RELATÓRIO FINAL =====
info "📊 FASE 5: Relatório final..."

# 5.1 Mostrar status dos containers
log "Status dos containers:"
docker-compose ps

# 5.2 Mostrar logs recentes
log "Logs recentes:"
docker-compose logs --tail=10 map-tiles

# 5.3 Mostrar informações do sistema
log "Informações do sistema:"
if curl -s http://localhost:8000/system-status | grep -q "memory"; then
    log "✅ Sistema está coletando métricas corretamente"
fi

# 5.4 Mostrar resumo
log "🎉 Deploy realizado com sucesso!"
log "📋 Resumo:"
log "   - Branch: ${BRANCH}"
log "   - Projeto: ${PROJECT_DIR}"
log "   - Porta: 8000"
log "   - Endpoints disponíveis:"
log "     • GET /metrics"
log "     • GET /system-status"
log "     • GET /ativos_mapa_atual"
log "     • GET /ativos_mapa_atualizado"
log "     • GET /map-tiles/{path:path}"

log "🚀 Deploy completo finalizado!"
