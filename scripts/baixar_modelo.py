"""Baixa apenas o modelo publico de portugues do Vosk (~31 MB comprimido)."""
from pathlib import Path
from urllib.request import urlretrieve
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
PASTA = ROOT / "models"
NOME = "vosk-model-small-pt-0.3"
URL = f"https://alphacephei.com/vosk/models/{NOME}.zip"


def main():
    PASTA.mkdir(parents=True, exist_ok=True)
    destino = PASTA / NOME
    if destino.exists():
        print(f"Modelo ja existe em: {destino}")
        return
    zip_destino = PASTA / f"{NOME}.zip"
    print(f"Baixando modelo de {URL}")
    urlretrieve(URL, zip_destino)
    with ZipFile(zip_destino) as zipf:
        for item in zipf.infolist():
            path_alvo = (PASTA / item.filename).resolve()
            if not path_alvo.is_relative_to(PASTA.resolve()):
                raise RuntimeError("Caminho inseguro no arquivo ZIP")
        zipf.extractall(PASTA)
    zip_destino.unlink()
    print(f"Modelo pronto: {destino}")

if __name__ == "__main__":
    main()
