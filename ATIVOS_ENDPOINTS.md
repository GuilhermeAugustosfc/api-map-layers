# Endpoints de Ativos - Documentação

Este documento descreve os novos endpoints criados para retornar dados de veículos/ativos.

## Endpoints Disponíveis

### 1. `/ativos_mapa_atual` (GET)

**Descrição**: Retorna 20.000 objetos de veículos após 2 segundos de delay.

**Resposta**: Array de objetos no formato tradicional:

```json
[
  {
    "speed": { "val": 0, "unit_measurement": "km/h" },
    "client_id": 2469,
    "direction": 208,
    "lat_lng": [-23.544996, -46.738784],
    "validate": 1,
    "ativo_id": 5328,
    "is_bloqued": 0,
    "ativo": {
      "horimeter": 0,
      "consume": 10,
      "model": "Fiorino",
      "type": 1,
      "description": "DWL2921 - FIORINO",
      "fuel": "1",
      "producer": "Fiat",
      "odometer": 0,
      "plate": "DWL2921",
      "ativo_name": "FIORINO",
      "color": "Branca"
    },
    "field_extra": {},
    "tracker_message": null,
    "dt_gps": "05/09/2025 20:10:26",
    "ignition": 0
  }
  // ... mais 19.999 objetos
]
```

**Características**:

- ⏱️ Delay de 2 segundos antes de retornar
- 📊 20.000 objetos
- 🔄 Formato tradicional (um objeto por veículo)

---

### 2. `/ativos_mapa_atualizado` (GET)

**Descrição**: Retorna 20.000 objetos em formato columnar otimizado com streaming e compressão gzip.

**Resposta**: Objeto no formato columnar comprimido:

```json
{
  "speed_val": [0, 45, 30, ...],
  "speed_unit": ["km/h", "km/h", "km/h", ...],
  "client_id": [2469, 1234, 5678, ...],
  "direction": [208, 90, 180, ...],
  "lat": [-23.544996, -23.555000, -23.566000, ...],
  "lng": [-46.738784, -46.750000, -46.760000, ...],
  "validate": [1, 1, 1, ...],
  "ativo_id": [5328, 1234, 5678, ...],
  "is_bloqued": [0, 1, 0, ...],
  "ativo_horimeter": [0, 1000, 2000, ...],
  "ativo_consume": [10, 12, 8, ...],
  "ativo_model": ["Fiorino", "Civic", "Corolla", ...],
  "ativo_type": [1, 2, 1, ...],
  "ativo_description": ["DWL2921 - FIORINO", "ABC1234 - CIVIC", ...],
  "ativo_fuel": ["1", "2", "1", ...],
  "ativo_producer": ["Fiat", "Honda", "Toyota", ...],
  "ativo_odometer": [0, 50000, 75000, ...],
  "ativo_plate": ["DWL2921", "ABC1234", "XYZ5678", ...],
  "ativo_name": ["FIORINO", "CIVIC", "COROLLA", ...],
  "ativo_color": ["Branca", "Prata", "Preta", ...],
  "field_extra": [{}, {}, {}, ...],
  "tracker_message": [null, null, null, ...],
  "dt_gps": ["05/09/2025 20:10:26", "05/09/2025 20:11:00", ...],
  "ignition": [0, 1, 0, ...]
}
```

**Características**:

- 🚀 **Streaming**: Dados enviados em chunks para melhor performance
- 📦 **Compressão Gzip**: Reduz o tamanho do payload em ~75%
- 📊 **Formato Columnar**: Cada campo é um array, índice i corresponde ao mesmo veículo
- ⚡ **Performance**: Muito mais eficiente para grandes volumes de dados

**Headers de Resposta**:

```
Content-Encoding: gzip
Content-Type: application/json; charset=utf-8
Cache-Control: no-cache
Transfer-Encoding: chunked
```

---

## Vantagens do Formato Columnar

### 1. **Redução de Payload**

- Menos repetição de chaves JSON
- Compressão gzip mais eficiente (strings repetidas como "km/h", "Fiat", etc.)
- Economia de megabytes em datasets grandes

### 2. **Performance no Cliente**

- Parse mais rápido no navegador
- Não cria 20.000 objetos JavaScript
- Arrays grandes são mais eficientes

### 3. **Reconstrução Fácil**

No frontend, você pode reconstruir objetos individuais:

```javascript
function getVehicle(data, index) {
  return {
    speed: {
      val: data.speed_val[index],
      unit_measurement: data.speed_unit[index],
    },
    client_id: data.client_id[index],
    direction: data.direction[index],
    lat_lng: [data.lat[index], data.lng[index]],
    validate: data.validate[index],
    ativo_id: data.ativo_id[index],
    is_bloqued: data.is_bloqued[index],
    ativo: {
      horimeter: data.ativo_horimeter[index],
      consume: data.ativo_consume[index],
      model: data.ativo_model[index],
      type: data.ativo_type[index],
      description: data.ativo_description[index],
      fuel: data.ativo_fuel[index],
      producer: data.ativo_producer[index],
      odometer: data.ativo_odometer[index],
      plate: data.ativo_plate[index],
      ativo_name: data.ativo_name[index],
      color: data.ativo_color[index],
    },
    field_extra: data.field_extra[index],
    tracker_message: data.tracker_message[index],
    dt_gps: data.dt_gps[index],
    ignition: data.ignition[index],
  };
}

// Uso:
const vehicle0 = getVehicle(data, 0); // Primeiro veículo
const vehicle1 = getVehicle(data, 1); // Segundo veículo
```

---

## Exemplo de Uso

### Testando com curl:

```bash
# Endpoint tradicional
curl -X GET "http://localhost:8000/ativos_mapa_atual"

# Endpoint otimizado (com streaming e gzip)
curl -X GET "http://localhost:8000/ativos_mapa_atualizado" \
  -H "Accept-Encoding: gzip" \
  --compressed
```

### Testando com JavaScript:

```javascript
// Endpoint tradicional
const response1 = await fetch("/ativos_mapa_atual");
const vehicles = await response1.json();
console.log(`Recebidos ${vehicles.length} veículos`);

// Endpoint otimizado
const response2 = await fetch("/ativos_mapa_atualizado");
const columnarData = await response2.json();
console.log(
  `Recebidos ${columnarData.speed_val.length} veículos em formato columnar`
);

// Reconstruir primeiro veículo
const firstVehicle = getVehicle(columnarData, 0);
console.log("Primeiro veículo:", firstVehicle);
```

---

## Arquitetura

Os endpoints estão organizados no arquivo `ativos_endpoints.py` para manter o código limpo e modular:

- `generate_sample_vehicle_data()`: Gera dados de exemplo para um veículo
- `generate_columnar_data()`: Converte array de veículos para formato columnar
- `generate_vehicles_data()`: Gera lista de veículos
- `create_ativos_endpoints()`: Registra os endpoints no FastAPI

O arquivo `main.py` importa e registra os endpoints automaticamente.
