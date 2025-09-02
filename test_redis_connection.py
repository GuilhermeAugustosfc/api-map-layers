#!/usr/bin/env python3
"""
Arquivo de teste para verificar conectividade com Redis
DNS: redis-dev.ops.ftrack.me
"""

import redis
import time
import sys
from typing import Optional


def test_redis_connection(
    host: str = "redis-dev.ops.ftrack.me",
    port: int = 6379,
    password: Optional[str] = None,
    db: int = 0,
    timeout: int = 5,
) -> bool:
    """
    Testa a conexão com o Redis

    Args:
        host: Endereço do servidor Redis
        port: Porta do Redis (padrão: 6379)
        password: Senha do Redis (se necessário)
        db: Número do banco de dados (padrão: 0)
        timeout: Timeout de conexão em segundos

    Returns:
        bool: True se a conexão foi bem-sucedida, False caso contrário
    """
    print(f"🔍 Testando conexão com Redis...")
    print(f"   Host: {host}")
    print(f"   Porta: {port}")
    print(f"   Database: {db}")
    print(f"   Timeout: {timeout}s")
    print("-" * 50)

    try:
        # Criar conexão com Redis
        r = redis.Redis(
            host=host,
            port=port,
            password=password,
            db=db,
            socket_timeout=timeout,
            socket_connect_timeout=timeout,
            decode_responses=True,
        )

        # Teste 1: Ping básico
        print("📡 Testando ping básico...")
        start_time = time.time()
        response = r.ping()
        ping_time = (time.time() - start_time) * 1000

        if response:
            print(f"✅ Ping bem-sucedido! Tempo de resposta: {ping_time:.2f}ms")
        else:
            print("❌ Ping falhou!")
            return False

        # Teste 2: Informações do servidor
        print("\n📊 Obtendo informações do servidor...")
        try:
            info = r.info()
            print(f"✅ Versão do Redis: {info.get('redis_version', 'N/A')}")
            print(f"✅ Modo: {info.get('redis_mode', 'N/A')}")
            print(f"✅ Uptime: {info.get('uptime_in_seconds', 0)} segundos")
            print(
                f"✅ Conexões: {info.get('connected_clients', 0)} clientes conectados"
            )
            print(f"✅ Memória usada: {info.get('used_memory_human', 'N/A')}")
        except Exception as e:
            print(f"⚠️  Erro ao obter informações do servidor: {e}")

        # Teste 3: Operações básicas de escrita/leitura
        print("\n🔧 Testando operações básicas...")
        test_key = "test:connection:timestamp"
        test_value = f"test_{int(time.time())}"

        # SET
        print(f"   Definindo chave '{test_key}' = '{test_value}'")
        r.set(test_key, test_value, ex=60)  # Expira em 60 segundos
        print("   ✅ SET executado com sucesso")

        # GET
        print(f"   Lendo chave '{test_key}'")
        retrieved_value = r.get(test_key)
        if retrieved_value == test_value:
            print(f"   ✅ GET bem-sucedido: {retrieved_value}")
        else:
            print(
                f"   ❌ GET falhou: esperado '{test_value}', obtido '{retrieved_value}'"
            )
            return False

        # DEL
        print(f"   Removendo chave '{test_key}'")
        deleted = r.delete(test_key)
        if deleted:
            print("   ✅ DELETE bem-sucedido")
        else:
            print("   ❌ DELETE falhou")

        # Teste 4: Performance básica
        print("\n⚡ Teste de performance básica...")
        operations = 100
        start_time = time.time()

        for i in range(operations):
            r.set(f"perf_test:{i}", f"value_{i}")
            r.get(f"perf_test:{i}")
            r.delete(f"perf_test:{i}")

        total_time = time.time() - start_time
        ops_per_second = (operations * 3) / total_time  # 3 operações por iteração
        print(f"✅ {operations} ciclos (SET/GET/DEL) em {total_time:.2f}s")
        print(f"✅ Performance: {ops_per_second:.0f} operações/segundo")

        print("\n" + "=" * 50)
        print("🎉 TODOS OS TESTES PASSARAM!")
        print("✅ Conexão com Redis está funcionando corretamente")
        print("=" * 50)

        return True

    except redis.ConnectionError as e:
        print(f"❌ Erro de conexão: {e}")
        print("💡 Verifique se:")
        print("   - O servidor Redis está rodando")
        print("   - O endereço e porta estão corretos")
        print("   - Não há firewall bloqueando a conexão")
        return False

    except redis.AuthenticationError as e:
        print(f"❌ Erro de autenticação: {e}")
        print("💡 Verifique se a senha está correta")
        return False

    except redis.TimeoutError as e:
        print(f"❌ Timeout na conexão: {e}")
        print("💡 O servidor pode estar sobrecarregado ou a rede está lenta")
        return False

    except Exception as e:
        print(f"❌ Erro inesperado: {e}")
        return False


def test_redis_with_auth():
    """Teste com autenticação (descomente e ajuste se necessário)"""
    print("\n🔐 Para testar com autenticação, descomente as linhas abaixo e configure:")
    print("# return test_redis_connection(")
    print("#     host='redis-dev.ops.ftrack.me',")
    print("#     port=6379,")
    print("#     password='sua_senha_aqui'")
    print("# )")


def main():
    """Função principal"""
    print("🔄 TESTE DE CONEXÃO REDIS")
    print("=" * 50)

    # Teste básico sem autenticação
    success = test_redis_connection(host="redis-dev.ops.ftrack.me")

    if not success:
        print("\n🔐 Se o Redis requer autenticação, edite este arquivo")
        print("   e configure a senha na função test_redis_with_auth()")
        test_redis_with_auth()

    # Código de saída
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
