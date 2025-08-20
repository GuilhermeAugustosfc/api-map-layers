# Exemplo de Uso do Proxy HERE Maps

## Como funciona

Sua API agora funciona como um proxy que intercepta as requisições do frontend e repassa para a API do HERE Maps.

## URLs Originais vs Proxy

### URLs Originais do HERE:

```
https://maps.hereapi.com/v3/base/mc/3/3/3/png?size=512&apiKey=mZCLZ7aTQGDtmSngdiQOeIinWS9lcEpSjbPwOIgpNs4&style=explore.day&lang=en
https://maps.hereapi.com/v3/base/mc/3/3/5/png?size=512&apiKey=mZCLZ7aTQGDtmSngdiQOeIinWS9lcEpSjbPwOIgpNs4&style=explore.day&lang=en
https://maps.hereapi.com/v3/base/mc/3/4/2/png?size=512&apiKey=mZCLZ7aTQGDtmSngdiQOeIinWS9lcEpSjbPwOIgpNs4&style=explore.day&lang=en
```

### URLs do Proxy (sua API):

```
http://localhost:8000/here-proxy/3/3/3/png?size=512&apiKey=mZCLZ7aTQGDtmSngdiQOeIinWS9lcEpSjbPwOIgpNs4&style=explore.day&lang=en
http://localhost:8000/here-proxy/3/3/5/png?size=512&apiKey=mZCLZ7aTQGDtmSngdiQOeIinWS9lcEpSjbPwOIgpNs4&style=explore.day&lang=en
http://localhost:8000/here-proxy/3/4/2/png?size=512&apiKey=mZCLZ7aTQGDtmSngdiQOeIinWS9lcEpSjbPwOIgpNs4&style=explore.day&lang=en
```

## Como usar no Frontend

### Antes (acesso direto ao HERE):

```javascript
const mapUrl = `https://maps.hereapi.com/v3/base/mc/${z}/${x}/${y}/png?size=512&apiKey=${apiKey}&style=explore.day&lang=en`;
```

### Depois (usando seu proxy):

```javascript
const mapUrl = `http://localhost:8000/here-proxy/${z}/${x}/${y}/png?size=512&apiKey=${apiKey}&style=explore.day&lang=en`;
```

## Endpoints Disponíveis

1. **GET /** - Hello World
2. **GET /hello** - Hello World alternativo
3. **GET /here-proxy/{path:path}** - Proxy do HERE Maps
4. **GET /docs/here-proxy** - Documentação do proxy
5. **OPTIONS /here-proxy/{path:path}** - CORS para o proxy

## Benefícios do Proxy

- ✅ Controle total sobre as requisições
- ✅ Possibilidade de adicionar cache
- ✅ Logs das requisições
- ✅ Controle de CORS
- ✅ Possibilidade de adicionar autenticação
- ✅ Monitoramento de uso
- ✅ Rate limiting (se necessário)

## Testando

1. Acesse: `http://localhost:8000/docs/here-proxy` para ver a documentação
2. Teste uma imagem: `http://localhost:8000/here-proxy/3/3/3/png?size=512&apiKey=mZCLZ7aTQGDtmSngdiQOeIinWS9lcEpSjbPwOIgpNs4&style=explore.day&lang=en`
