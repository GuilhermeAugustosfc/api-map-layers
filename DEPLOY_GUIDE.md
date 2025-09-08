# Guia de Deploy - Solução para Erro de Porta

## 🚨 Problemas Identificados

### Problema 1: Porta em Uso

```
ERROR: Cannot start service map-tiles: driver failed programming external connectivity on endpoint map-tiles-api: Bind for 0.0.0.0:8000 failed: port is already allocated
```

**Causa**: A porta 8000 já está sendo usada por outro processo ou container.

### Problema 2: Arquivo Não Encontrado

```
ModuleNotFoundError: No module named 'ativos_endpoints'
```

**Causa**: O Dockerfile não estava copiando o arquivo `ativos_endpoints.py` para o container.

**✅ CORRIGIDO**: Atualizei o Dockerfile para copiar o arquivo `ativos_endpoints.py`.

## 🔧 Soluções Disponíveis

### Opção 1: Script de Deploy Completo (Recomendado)

```bash
# Tornar executável
chmod +x deploy_complete.sh

# Executar deploy completo
./deploy_complete.sh main
```

### Opção 2: Limpeza Manual + Deploy Corrigido

```bash
# 1. Primeiro, limpar o ambiente
chmod +x cleanup_deploy.sh
./cleanup_deploy.sh

# 2. Depois, executar o deploy corrigido
chmod +x deploy_fixed.sh
./deploy_fixed.sh main
```

### Opção 3: Teste Local + Deploy

```bash
# 1. Testar localmente primeiro
chmod +x test_local.sh
./test_local.sh

# 2. Se o teste passou, fazer o deploy
./deploy_complete.sh main
```

### Opção 4: Comandos Manuais (Para Debug)

```bash
# 1. Parar todos os containers relacionados
cd /var/www/html/api-map-layer
docker-compose down --remove-orphans

# 2. Parar containers específicos
docker stop map-tiles-api
docker rm map-tiles-api

# 3. Verificar processos usando a porta 8000
lsof -ti:8000 | xargs kill -9

# 4. Verificar se a porta está livre
netstat -tuln | grep :8000

# 5. Executar o deploy
./deploy_fixed.sh main
```

## 📋 O que os Scripts Corrigidos Fazem

### `deploy_complete.sh` (Recomendado)

- ✅ **Limpeza completa** do ambiente
- ✅ **Parada forçada** de containers órfãos
- ✅ **Liberação da porta** 8000
- ✅ **Verificação de arquivos** essenciais
- ✅ **Testes automáticos** dos endpoints
- ✅ **Relatório detalhado** do deploy

### `deploy_fixed.sh`

- ✅ **Parada melhorada** de containers
- ✅ **Remoção de órfãos** com `--remove-orphans`
- ✅ **Verificação de porta** em uso
- ✅ **Testes dos novos endpoints**

### `cleanup_deploy.sh`

- ✅ **Limpeza completa** do ambiente
- ✅ **Parada de todos os containers** relacionados
- ✅ **Liberação da porta** 8000
- ✅ **Limpeza de containers órfãos**

### `test_local.sh`

- ✅ **Verificação de arquivos** essenciais
- ✅ **Teste de importação** Python
- ✅ **Teste de build** Docker
- ✅ **Teste de funcionamento** do container

## 🆕 Novos Endpoints Testados

Os scripts agora testam automaticamente os novos endpoints:

1. **`/ativos_mapa_atual`** - Retorna 20k objetos após 2 segundos
2. **`/ativos_mapa_atualizado`** - Retorna dados em formato columnar com gzip

## 🔍 Verificações Automáticas

Os scripts verificam:

- ✅ Arquivo `ativos_endpoints.py` existe
- ✅ Arquivo `main.py` existe
- ✅ Arquivo `docker-compose.yml` existe
- ✅ Porta 8000 está livre
- ✅ Aplicação responde em `/metrics`
- ✅ Novos endpoints funcionam

## 🚀 Como Usar

### Deploy Simples

```bash
./deploy_complete.sh
```

### Deploy de Branch Específica

```bash
./deploy_complete.sh develop
```

### Deploy com Logs Detalhados

```bash
./deploy_complete.sh main 2>&1 | tee deploy.log
```

## 🐛 Troubleshooting

### Se ainda der erro de porta:

```bash
# Verificar o que está usando a porta 8000
sudo netstat -tulpn | grep :8000
sudo lsof -i :8000

# Matar processo específico
sudo kill -9 <PID>
```

### Se o container não subir:

```bash
# Ver logs do container
docker-compose logs map-tiles

# Verificar status
docker-compose ps
```

### Se os endpoints não funcionarem:

```bash
# Testar manualmente
curl http://localhost:8000/metrics
curl http://localhost:8000/ativos_mapa_atualizado
```

## 📊 Monitoramento

Após o deploy, você pode monitorar:

- **Métricas**: `http://localhost:8000/metrics`
- **Status do Sistema**: `http://localhost:8000/system-status`
- **Logs**: `docker-compose logs -f map-tiles`

## 🎯 Próximos Passos

1. Execute o deploy com o script corrigido
2. Verifique se todos os endpoints estão funcionando
3. Monitore as métricas de performance
4. Teste os novos endpoints de ativos

## 📞 Suporte

Se ainda tiver problemas:

1. Execute `./cleanup_deploy.sh` primeiro
2. Verifique os logs com `docker-compose logs map-tiles`
3. Teste manualmente os endpoints
4. Verifique se a porta 8000 está realmente livre
