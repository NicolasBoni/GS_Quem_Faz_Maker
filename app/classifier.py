"""Classificador ML local: TF-IDF por caracteres + regressao logistica."""
from functools import lru_cache
from dataclasses import dataclass
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from .dataset import EXEMPLOS

@dataclass(frozen=True)
class Resultado:
    categoria: str
    confianca: float

@lru_cache(maxsize=1)
def criar_modelo():
    frases, rotulos = [], []
    for rotulo, exemplos in EXEMPLOS.items():
        for frase in exemplos:
            frases.append(frase)
            rotulos.append(rotulo)
    modelo = make_pipeline(
        TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), strip_accents="unicode", lowercase=True),
        LogisticRegression(max_iter=3000, random_state=42),
    )
    modelo.fit(frases, rotulos)
    return modelo


def classificar(texto: str) -> Resultado:
    if not texto or len(texto.strip()) < 8:
        raise ValueError("Descricao muito curta para classificacao")
    modelo = criar_modelo()
    probabilidades = modelo.predict_proba([texto.strip()])[0]
    indice = probabilidades.argmax()
    return Resultado(categoria=str(modelo.classes_[indice]), confianca=float(probabilidades[indice]))
