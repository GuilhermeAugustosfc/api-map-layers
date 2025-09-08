import asyncio
import json
import gzip
import random
from datetime import datetime
from typing import Dict, List, Any, Iterator
from fastapi import FastAPI
from fastapi.responses import StreamingResponse


def generate_sample_vehicle_data() -> Dict[str, Any]:
    """Gera dados de exemplo para um veículo"""
    # Lista de modelos e cores para variação
    models = ["Fiorino", "Civic", "Corolla", "HB20", "Onix", "Argo", "Ka", "Gol"]
    colors = ["Branca", "Prata", "Preta", "Azul", "Vermelha", "Verde"]
    producers = [
        "Fiat",
        "Honda",
        "Toyota",
        "Hyundai",
        "Chevrolet",
        "Ford",
        "Volkswagen",
    ]
    fuel_types = ["1", "2", "3"]  # 1=Gasolina, 2=Diesel, 3=Flex

    # Coordenadas aleatórias em São Paulo
    lat = round(random.uniform(-23.8, -23.3), 6)
    lng = round(random.uniform(-47.0, -46.3), 6)

    model = random.choice(models)
    color = random.choice(colors)
    producer = random.choice(producers)
    plate = f"{random.choice(['ABC', 'DEF', 'GHI', 'JKL', 'MNO'])}{random.randint(1000, 9999)}"

    return {
        "speed": {"val": random.randint(0, 120), "unit_measurement": "km/h"},
        "client_id": random.randint(1000, 9999),
        "direction": random.randint(0, 359),
        "lat_lng": [lat, lng],
        "validate": 1,
        "ativo_id": random.randint(1000, 9999),
        "is_bloqued": random.choice([0, 1]),
        "ativo": {
            "horimeter": random.randint(0, 10000),
            "consume": random.randint(5, 20),
            "model": model,
            "type": random.randint(1, 5),
            "description": f"{plate} - {model.upper()}",
            "fuel": random.choice(fuel_types),
            "producer": producer,
            "odometer": random.randint(0, 200000),
            "plate": plate,
            "ativo_name": model.upper(),
            "color": color,
        },
        "field_extra": {},
        "tracker_message": None,
        "dt_gps": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "ignition": random.choice([0, 1]),
    }


def generate_columnar_data(vehicles: List[Dict[str, Any]]) -> Dict[str, List]:
    """Converte dados de veículos para formato columnar"""
    columnar = {
        "speed_val": [],
        "speed_unit": [],
        "client_id": [],
        "direction": [],
        "lat": [],
        "lng": [],
        "validate": [],
        "ativo_id": [],
        "is_bloqued": [],
        "ativo_horimeter": [],
        "ativo_consume": [],
        "ativo_model": [],
        "ativo_type": [],
        "ativo_description": [],
        "ativo_fuel": [],
        "ativo_producer": [],
        "ativo_odometer": [],
        "ativo_plate": [],
        "ativo_name": [],
        "ativo_color": [],
        "field_extra": [],
        "tracker_message": [],
        "dt_gps": [],
        "ignition": [],
    }

    for vehicle in vehicles:
        columnar["speed_val"].append(vehicle["speed"]["val"])
        columnar["speed_unit"].append(vehicle["speed"]["unit_measurement"])
        columnar["client_id"].append(vehicle["client_id"])
        columnar["direction"].append(vehicle["direction"])
        columnar["lat"].append(vehicle["lat_lng"][0])
        columnar["lng"].append(vehicle["lat_lng"][1])
        columnar["validate"].append(vehicle["validate"])
        columnar["ativo_id"].append(vehicle["ativo_id"])
        columnar["is_bloqued"].append(vehicle["is_bloqued"])
        columnar["ativo_horimeter"].append(vehicle["ativo"]["horimeter"])
        columnar["ativo_consume"].append(vehicle["ativo"]["consume"])
        columnar["ativo_model"].append(vehicle["ativo"]["model"])
        columnar["ativo_type"].append(vehicle["ativo"]["type"])
        columnar["ativo_description"].append(vehicle["ativo"]["description"])
        columnar["ativo_fuel"].append(vehicle["ativo"]["fuel"])
        columnar["ativo_producer"].append(vehicle["ativo"]["producer"])
        columnar["ativo_odometer"].append(vehicle["ativo"]["odometer"])
        columnar["ativo_plate"].append(vehicle["ativo"]["plate"])
        columnar["ativo_name"].append(vehicle["ativo"]["ativo_name"])
        columnar["ativo_color"].append(vehicle["ativo"]["color"])
        columnar["field_extra"].append(vehicle["field_extra"])
        columnar["tracker_message"].append(vehicle["tracker_message"])
        columnar["dt_gps"].append(vehicle["dt_gps"])
        columnar["ignition"].append(vehicle["ignition"])

    return columnar


def generate_vehicles_streaming(batch_size: int = 1000) -> Iterator[bytes]:
    """Gera dados de veículos em streaming para o formato columnar"""
    total_vehicles = 20000
    vehicles_generated = 0

    # Primeiro, enviamos o início do JSON
    yield b'{"speed_val": ['

    # Geramos os dados em lotes
    while vehicles_generated < total_vehicles:
        batch_vehicles = []
        current_batch_size = min(batch_size, total_vehicles - vehicles_generated)

        for _ in range(current_batch_size):
            batch_vehicles.append(generate_sample_vehicle_data())

        # Converte para formato columnar
        columnar_data = generate_columnar_data(batch_vehicles)

        # Se é o primeiro lote, enviamos o início
        if vehicles_generated == 0:
            # Enviamos os primeiros valores de speed_val
            speed_vals = columnar_data["speed_val"]
            yield json.dumps(speed_vals[0]).encode()
            for val in speed_vals[1:]:
                yield b"," + json.dumps(val).encode()
        else:
            # Continuamos com os valores de speed_val
            for val in columnar_data["speed_val"]:
                yield b"," + json.dumps(val).encode()

        vehicles_generated += current_batch_size

        # Pequena pausa para simular processamento
        if vehicles_generated < total_vehicles:
            yield b""  # Permite que o cliente processe os dados

    # Agora enviamos os outros campos
    yield b'], "speed_unit": ['

    # Reset para gerar os mesmos dados novamente (para consistência)
    vehicles_generated = 0
    while vehicles_generated < total_vehicles:
        batch_vehicles = []
        current_batch_size = min(batch_size, total_vehicles - vehicles_generated)

        for _ in range(current_batch_size):
            batch_vehicles.append(generate_sample_vehicle_data())

        columnar_data = generate_columnar_data(batch_vehicles)

        if vehicles_generated == 0:
            speed_units = columnar_data["speed_unit"]
            yield json.dumps(speed_units[0]).encode()
            for unit in speed_units[1:]:
                yield b"," + json.dumps(unit).encode()
        else:
            for unit in columnar_data["speed_unit"]:
                yield b"," + json.dumps(unit).encode()

        vehicles_generated += current_batch_size

    # Continuamos com os outros campos...
    # Por simplicidade, vamos gerar um JSON completo e enviar em chunks
    yield b"]}"


async def generate_vehicles_data(total: int = 20000) -> List[Dict[str, Any]]:
    """Gera lista de veículos com dados de exemplo"""
    vehicles = []
    for _ in range(total):
        vehicles.append(generate_sample_vehicle_data())
    return vehicles


def create_ativos_endpoints(app: FastAPI):
    """Cria e registra os endpoints de ativos no FastAPI"""

    @app.get("/ativos_mapa_atual")
    async def ativos_mapa_atual():
        """
        Endpoint que retorna 20.000 objetos de veículos após 2 segundos
        """
        # Aguarda 2 segundos conforme solicitado
        await asyncio.sleep(2)

        # Gera 20.000 veículos
        vehicles = await generate_vehicles_data(20000)

        return vehicles

    @app.get("/ativos_mapa_atualizado")
    async def ativos_mapa_atualizado():
        """
        Endpoint que retorna 20.000 objetos em formato columnar com streaming e gzip
        """

        def generate_streaming_response():
            """Gera resposta em streaming com dados columnar comprimidos"""
            # Gera todos os dados primeiro
            vehicles = []
            for _ in range(20000):
                vehicles.append(generate_sample_vehicle_data())

            # Converte para formato columnar
            columnar_data = generate_columnar_data(vehicles)

            # Converte para JSON
            json_data = json.dumps(columnar_data, ensure_ascii=False)

            # Comprime com gzip
            compressed_data = gzip.compress(json_data.encode("utf-8"))

            # Envia em chunks para simular streaming
            chunk_size = 8192  # 8KB por chunk
            for i in range(0, len(compressed_data), chunk_size):
                chunk = compressed_data[i : i + chunk_size]
                yield chunk
                # Pequena pausa para simular streaming
                if i + chunk_size < len(compressed_data):
                    import time

                    time.sleep(0.001)  # 1ms de pausa

        return StreamingResponse(
            generate_streaming_response(),
            media_type="application/json",
            headers={
                "Content-Encoding": "gzip",
                "Content-Type": "application/json; charset=utf-8",
                "Cache-Control": "no-cache",
                "Transfer-Encoding": "chunked",
            },
        )
