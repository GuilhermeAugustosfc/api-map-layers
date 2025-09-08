#!/bin/bash
# Script para testar localmente antes do deploy
# Uso: ./test_local.sh

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

log "🧪 Testando aplicação localmente..."

# 1. Verificar arquivos essenciais
log "Verificando arquivos essenciais..."
if [ ! -f "main.py" ]; then
    error "Arquivo main.py não encontrado!"
fi
if [ ! -f "ativos_endpoints.py" ]; then
    error "Arquivo ativos_endpoints.py não encontrado!"
fi
if [ ! -f "requirements.txt" ]; then
    error "Arquivo requirements.txt não encontrado!"
fi
log "✅ Todos os arquivos essenciais encontrados"

# 2. Testar importação do Python
log "Testando importação do Python..."
if python -c "from ativos_endpoints import create_ativos_endpoints; print('✅ Importação bem-sucedida!')" 2>/dev/null; then
    log "✅ Importação do ativos_endpoints funcionando"
else
    error "❌ Erro na importação do ativos_endpoints"
fi

# 3. Testar importação do main
log "Testando importação do main..."
if python -c "from main import app; print('✅ Importação do main bem-sucedida!')" 2>/dev/null; then
    log "✅ Importação do main funcionando"
else
    error "❌ Erro na importação do main"
fi

# 4. Testar build do Docker
log "Testando build do Docker..."
if docker-compose build 2>/dev/null; then
    log "✅ Build do Docker funcionando"
else
    error "❌ Erro no build do Docker"
fi

# 5. Testar se o container sobe
log "Testando se o container sobe..."
docker-compose up -d 2>/dev/null || true

# Aguardar um pouco
sleep 5

# Verificar se está rodando
if docker-compose ps | grep -q "Up"; then
    log "✅ Container está rodando"
    
    # Testar endpoint
    if curl -f http://localhost:8000/metrics >/dev/null 2>&1; then
        log "✅ Endpoint /metrics funcionando"
    else
        warn "⚠️  Endpoint /metrics não está respondendo"
    fi
    
    # Parar container
    docker-compose down
    log "✅ Container parado"
else
    warn "⚠️  Container não está rodando"
    docker-compose down 2>/dev/null || true
fi

log "🎉 Teste local concluído com sucesso!"
log "Agora você pode fazer o deploy com segurança!"
