from unittest.mock import Mock

import pytest
import sounddevice

from app.voice import Gravador, TAXA, MAX_GRAVACAO_S


@pytest.fixture
def captura(monkeypatch):
    stream = Mock()
    monkeypatch.setattr(sounddevice, "check_input_settings", Mock())
    monkeypatch.setattr(sounddevice, "RawInputStream", Mock(return_value=stream))
    return Gravador(), stream


def test_captura_so_inicia_quando_solicitada_e_descarta_blocos(captura):
    gravador, stream = captura
    stream.start.assert_not_called()
    gravador.iniciar()
    gravador._callback(b"\1\0" * 8000, 8000, None, False)
    assert gravador.parar() == b"\1\0" * 8000
    stream.stop.assert_called_once()
    stream.close.assert_called_once()
    assert gravador.stream is None
    assert gravador.blocos == []


@pytest.mark.parametrize("metodo", ["start", "stop"])
def test_falha_no_stream_sempre_libera_microfone(captura, metodo):
    gravador, stream = captura
    getattr(stream, metodo).side_effect = RuntimeError("Falha de audio")
    with pytest.raises(RuntimeError):
        gravador.iniciar()
        gravador.parar()
    stream.close.assert_called_once()
    assert gravador.stream is None


def test_perda_de_audio_nao_e_tratada_como_captura_valida(captura):
    gravador, stream = captura
    gravador.iniciar()
    gravador._callback(b"\0" * 100, 50, None, "input overflow")
    with pytest.raises(RuntimeError, match="input overflow"):
        gravador.parar()
    assert gravador.blocos == []
    assert gravador.stream is None


def test_memoria_limitada_mesmo_sem_stop(captura):
    gravador, _ = captura
    gravador.iniciar()
    bloco = b"\0" * (TAXA * 2)
    for _ in range(MAX_GRAVACAO_S + 10):
        gravador._callback(bloco, TAXA, None, False)
    assert sum(map(len, gravador.blocos)) == MAX_GRAVACAO_S * TAXA * 2
    gravador.cancelar()
    assert gravador.stream is None


def test_microfone_incompativel_com_16khz_nao_abre_stream(captura, monkeypatch):
    gravador, stream = captura
    monkeypatch.setattr(sounddevice, "check_input_settings", Mock(side_effect=RuntimeError("Taxa nao suportada")))
    with pytest.raises(RuntimeError, match="Taxa nao suportada"):
        gravador.iniciar()
    assert gravador.stream is None
    stream.start.assert_not_called()
