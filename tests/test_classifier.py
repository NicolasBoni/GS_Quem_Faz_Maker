from app.classifier import classificar
import pytest

@pytest.mark.parametrize("frase,esperado", [
    ("Preciso contratar encanador para trocar a torneira que esta vazando", "HIDRAULICA"),
    ("Quero um eletricista para instalar tomadas e trocar o disjuntor", "ELETRICA"),
    ("Preciso de um pintor para pintar toda a parede da sala", "PINTURA"),
    ("Quero uma diarista para fazer faxina no apartamento", "LIMPEZA"),
    ("Preciso de montador de moveis para montar guarda roupa", "MONTAGEM"),
    ("Preciso de tecnico de informatica para formatar notebook", "INFORMATICA"),
])
def test_classificacao_basica(frase, esperado):
    assert classificar(frase).categoria == esperado

def test_frase_curta():
    with pytest.raises(ValueError):
        classificar("oi")
