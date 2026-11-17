"""Protocolo real com serial/microfone simulados; nao valida hardware fisico."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from fastapi.testclient import TestClient

from app import api, bridge
from app.classifier import Resultado


FALA = "preciso de um encanador para consertar o vazamento na cozinha"


class GravadorSimulado:
    def __init__(self, dispositivo=None):
        self.stream = None
        self.inicios = 0
        self.audio = b"\0" * 32000

    def iniciar(self):
        self.inicios += 1
        self.stream = object()

    def parar(self):
        assert self.stream is not None
        self.stream = None
        return self.audio

    def cancelar(self):
        self.stream = None


@pytest.fixture
def contexto(monkeypatch):
    monkeypatch.setattr(bridge, "Gravador", GravadorSimulado)
    monkeypatch.setattr(bridge, "Transcritor", lambda modelo: SimpleNamespace(transcrever=lambda audio: FALA))
    ponte = bridge.Ponte("COM_TESTE", "http://127.0.0.1:8000", "modelo_simulado")
    placa = Mock()
    post = Mock()
    monkeypatch.setattr(bridge.requests, "post", post)
    return ponte, placa, post


def classificar_pedido(ponte, placa):
    ponte.processar("EVENT:START_RECORD", placa)
    ponte.processar("EVENT:STOP_RECORD", placa)


def ultima_resposta(placa):
    return placa.write.call_args.args[0].decode().strip()


def test_fluxo_completo_com_api_e_sqlite(contexto, tmp_path, monkeypatch):
    ponte, placa, post = contexto
    monkeypatch.setattr(api, "DB_PATH", tmp_path / "fluxo.sqlite3")
    cliente = TestClient(api.app)
    post.side_effect = lambda url, **kw: cliente.post("/api/solicitacoes", json=kw["json"])
    ponte.processar("EVENT:PRESENCE", placa)
    assert ponte.gravador.inicios == 0
    classificar_pedido(ponte, placa)
    assert ultima_resposta(placa) == "CLASSIFIED:HIDRAULICA"
    assert cliente.get("/api/solicitacoes").json() == []
    ponte.processar("EVENT:CONFIRM", placa)
    assert ultima_resposta(placa) == "RESULT:OK:1"
    ponte.processar("EVENT:CONFIRM", placa)
    assert ultima_resposta(placa) == "RESULT:OK:1"
    assert post.call_count == 1
    pedidos = cliente.get("/api/solicitacoes").json()
    assert len(pedidos) == 1
    assert pedidos[0]["descricao"] == FALA
    assert pedidos[0]["origem"] == "smart_point_voz"


def test_start_stop_duplicados_preservam_gravacao_e_categoria(contexto):
    ponte, placa, post = contexto
    ponte.processar("EVENT:START_RECORD", placa)
    ponte.processar("EVENT:START_RECORD", placa)
    assert ponte.gravador.inicios == 1
    ponte.processar("EVENT:STOP_RECORD", placa)
    ponte.processar("EVENT:STOP_RECORD", placa)
    assert ponte.estado == "CONFIRMANDO"
    assert placa.write.call_count == 1
    post.assert_not_called()


def test_confirmacao_sem_pedido_nao_registra(contexto):
    ponte, placa, post = contexto
    ponte.processar("EVENT:CONFIRM", placa)
    assert ultima_resposta(placa) == "RESULT:ERROR:SEM PEDIDO"
    post.assert_not_called()


@pytest.mark.parametrize("evento", ["QUEM_FAZ_INICIADO", "EVENT:PRESENCE"])
def test_reinicio_ou_nova_presenca_descarta_pendente(contexto, evento):
    ponte, placa, post = contexto
    classificar_pedido(ponte, placa)
    ponte.processar(evento, placa)
    ponte.processar("EVENT:CONFIRM", placa)
    assert ponte.pendente is None
    post.assert_not_called()


def test_reinicio_libera_microfone(contexto):
    ponte, placa, _ = contexto
    ponte.processar("EVENT:START_RECORD", placa)
    ponte.processar("QUEM_FAZ_INICIADO", placa)
    assert ponte.gravador.stream is None


def test_microfone_indisponivel(contexto):
    ponte, placa, post = contexto
    ponte.gravador.iniciar = Mock(side_effect=RuntimeError("Microfone indisponivel"))
    ponte.processar("EVENT:START_RECORD", placa)
    assert ultima_resposta(placa) == "RESULT:ERROR:MICROFONE"
    post.assert_not_called()


@pytest.mark.parametrize("audio,texto", [(b"", FALA), (b"\0" * 100, FALA), (b"\0" * 32000, ""), (b"\0" * 32000, "oi")])
def test_audio_ou_fala_invalidos(contexto, audio, texto):
    ponte, placa, post = contexto
    ponte.gravador.audio = audio
    ponte.transcritor.transcrever = lambda audio: texto
    classificar_pedido(ponte, placa)
    assert ultima_resposta(placa) == "RESULT:ERROR:REFAZER"
    assert ponte.pendente is None
    post.assert_not_called()


def test_baixa_confianca(contexto, monkeypatch):
    ponte, placa, post = contexto
    monkeypatch.setattr(bridge, "classificar", lambda texto: Resultado("HIDRAULICA", 0.20))
    classificar_pedido(ponte, placa)
    assert ultima_resposta(placa) == "RESULT:ERROR:REFAZER"
    post.assert_not_called()


def test_sem_confirmacao_expira(contexto, monkeypatch):
    ponte, placa, post = contexto
    classificar_pedido(ponte, placa)
    monkeypatch.setattr(bridge.time, "monotonic", lambda: ponte.iniciou_estado + 46)
    ponte.processar("EVENT:CONFIRM", placa)
    assert ponte.pendente is None
    post.assert_not_called()


def test_stop_perdido_nao_deixa_microfone_aberto(contexto, monkeypatch):
    ponte, placa, post = contexto
    ponte.processar("EVENT:START_RECORD", placa)
    agora = ponte.iniciou_estado + 33
    monkeypatch.setattr(bridge.time, "monotonic", lambda: agora)
    ponte.verificar_prazos(placa)
    assert ponte.gravador.stream is None
    assert ultima_resposta(placa) == "RESULT:ERROR:TEMPO ESGOTADO"
    post.assert_not_called()


def test_processamento_lento_nao_envia_classificacao_atrasada(contexto, monkeypatch):
    ponte, placa, _ = contexto
    agora = [0]
    monkeypatch.setattr(bridge.time, "monotonic", lambda: agora[0])
    def transcrever(audio):
        agora[0] = 86
        return FALA
    ponte.transcritor.transcrever = transcrever
    classificar_pedido(ponte, placa)
    assert ultima_resposta(placa) == "RESULT:ERROR:REFAZER"


def test_backend_fora_do_ar(contexto):
    ponte, placa, post = contexto
    post.side_effect = requests.ConnectionError("Backend indisponivel")
    classificar_pedido(ponte, placa)
    ponte.processar("EVENT:CONFIRM", placa)
    assert ultima_resposta(placa) == "RESULT:ERROR:SERVIDOR"


@pytest.mark.parametrize("dados", [{"status": "ERRO", "id": 1}, {"status": "REGISTRADO"},
                                     {"status": "REGISTRADO", "id": True},
                                     {"status": "REGISTRADO", "id": -1},
                                     {"status": "REGISTRADO", "id": 1, "categoria": "LIMPEZA"}])
def test_backend_sem_confirmacao_valida_nao_exibe_sucesso(contexto, dados):
    ponte, placa, post = contexto
    post.return_value.json.return_value = dados
    classificar_pedido(ponte, placa)
    ponte.processar("EVENT:CONFIRM", placa)
    assert ultima_resposta(placa) == "RESULT:ERROR:SERVIDOR"


def test_resposta_http_perdida_repete_mesma_chave_sem_duplicar(contexto, tmp_path, monkeypatch):
    ponte, placa, post = contexto
    monkeypatch.setattr(api, "DB_PATH", tmp_path / "repeticao.sqlite3")
    cliente = TestClient(api.app)
    chamadas = []
    def registrar(url, **kw):
        chamadas.append(kw["json"]["chave_idempotencia"])
        resposta = cliente.post("/api/solicitacoes", json=kw["json"])
        if len(chamadas) == 1:
            raise requests.Timeout("Resposta perdida apos commit")
        return resposta
    post.side_effect = registrar
    classificar_pedido(ponte, placa)
    ponte.processar("EVENT:CONFIRM", placa)
    assert ultima_resposta(placa) == "RESULT:ERROR:SERVIDOR"
    ponte.processar("EVENT:CONFIRM", placa)
    assert ultima_resposta(placa) == "RESULT:OK:1"
    assert chamadas[0] == chamadas[1]
    assert len(cliente.get("/api/solicitacoes").json()) == 1


def test_serial_fragmentada_nao_perde_inicio(contexto, monkeypatch):
    ponte, _, _ = contexto
    placa = Mock()
    placa.__enter__ = Mock(return_value=placa)
    placa.__exit__ = Mock(return_value=False)
    placa.in_waiting = 1
    placa.read.side_effect = [b"QUEM_FAZ_INICIADO\r\nEVENT:STA", b"RT_RECORD\n", KeyboardInterrupt()]
    monkeypatch.setattr(bridge.serial, "Serial", Mock(return_value=placa))
    ponte.executar()
    assert ponte.gravador.inicios == 1
    assert ponte.gravador.stream is None
    placa.reset_input_buffer.assert_not_called()


def test_desconexao_serial_libera_microfone(contexto, monkeypatch):
    ponte, _, _ = contexto
    placa = Mock()
    placa.__enter__ = Mock(return_value=placa)
    placa.__exit__ = Mock(return_value=False)
    placa.in_waiting = 1
    placa.read.side_effect = [b"EVENT:START_RECORD\n", bridge.serial.SerialException("Desconectado")]
    monkeypatch.setattr(bridge.serial, "Serial", Mock(return_value=placa))
    with pytest.raises(bridge.serial.SerialException):
        ponte.executar()
    assert ponte.gravador.stream is None
