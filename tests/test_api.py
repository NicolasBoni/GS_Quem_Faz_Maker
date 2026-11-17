from fastapi.testclient import TestClient
from app.api import app
import pytest

def test_health():
    response = TestClient(app).get('/health')
    assert response.status_code == 200
    assert response.json()['modo'] == 'demonstracao_local'

def test_criar_solicitacao_local(tmp_path, monkeypatch):
    import app.api as api
    monkeypatch.setattr(api, 'DB_PATH', tmp_path / 'teste.sqlite3')
    cliente = TestClient(app)
    pedido = {'descricao': 'Preciso trocar uma torneira com vazamento', 'categoria': 'HIDRAULICA', 'confianca': 0.8}
    resp = cliente.post('/api/solicitacoes', json=pedido)
    assert resp.status_code == 201
    assert resp.json()['status'] == 'REGISTRADO'
    lista = cliente.get('/api/solicitacoes').json()
    assert len(lista) == 1
    assert lista[0]['descricao'] == pedido['descricao']


@pytest.mark.parametrize('campo,valor', [('descricao', ' ' * 10), ('categoria', 'OUTRA'),
                                       ('confianca', -0.1), ('confianca', 1.1)])
def test_rejeitar_pedido_invalido(tmp_path, monkeypatch, campo, valor):
    import app.api as api
    monkeypatch.setattr(api, 'DB_PATH', tmp_path / 'teste.sqlite3')
    pedido = {'descricao': 'Preciso trocar uma torneira', 'categoria': 'HIDRAULICA', 'confianca': 0.8}
    pedido[campo] = valor
    cliente = TestClient(app)
    assert cliente.post('/api/solicitacoes', json=pedido).status_code == 422
    assert cliente.get('/api/solicitacoes').json() == []


def test_chave_idempotente_e_conflito(tmp_path, monkeypatch):
    import app.api as api
    monkeypatch.setattr(api, 'DB_PATH', tmp_path / 'teste.sqlite3')
    cliente = TestClient(app)
    pedido = {'descricao': 'Preciso trocar uma torneira', 'categoria': 'HIDRAULICA',
              'confianca': 0.8, 'chave_idempotencia': 'teste-123'}
    primeira = cliente.post('/api/solicitacoes', json=pedido)
    segunda = cliente.post('/api/solicitacoes', json=pedido)
    assert primeira.json()['id'] == segunda.json()['id']
    pedido['descricao'] = 'Preciso trocar o registro de agua'
    assert cliente.post('/api/solicitacoes', json=pedido).status_code == 409
    assert len(cliente.get('/api/solicitacoes').json()) == 1


def test_migracao_preserva_pedido_antigo(tmp_path, monkeypatch):
    import sqlite3
    import app.api as api
    caminho = tmp_path / 'antigo.sqlite3'
    con = sqlite3.connect(caminho)
    con.execute('''CREATE TABLE solicitacoes (id INTEGER PRIMARY KEY AUTOINCREMENT,
                descricao TEXT NOT NULL, categoria TEXT NOT NULL, confianca REAL NOT NULL,
                origem TEXT NOT NULL, status TEXT NOT NULL, criado_em TEXT NOT NULL)''')
    con.execute("INSERT INTO solicitacoes VALUES (7, 'Trocar torneira antiga', 'HIDRAULICA', 0.8, 'smart_point_voz', 'REGISTRADO', '2026-11-15T12:00:00+00:00')")
    con.commit()
    con.close()
    monkeypatch.setattr(api, 'DB_PATH', caminho)
    cliente = TestClient(app)
    for _ in range(2):
        pedidos = cliente.get('/api/solicitacoes').json()
        assert len(pedidos) == 1
        assert pedidos[0]['id'] == 7
        assert pedidos[0]['descricao'] == 'Trocar torneira antiga'
    novo = cliente.post('/api/solicitacoes', json={'descricao': 'Pintar parede da sala', 'categoria': 'PINTURA', 'confianca': 0.8})
    assert novo.json()['id'] == 8


def test_requisicoes_simultaneas_nao_duplicam(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import app.api as api
    monkeypatch.setattr(api, 'DB_PATH', tmp_path / 'concorrente.sqlite3')
    pedido = api.SolicitacaoEntrada(descricao='Preciso trocar uma torneira', categoria='HIDRAULICA',
                                   confianca=0.8, chave_idempotencia='concorrente-123')
    with ThreadPoolExecutor(max_workers=4) as pool:
        resultados = list(pool.map(lambda _: api.criar_pedido(pedido), range(8)))
    assert len({r['id'] for r in resultados}) == 1
    assert len(api.listar_pedidos()) == 1
