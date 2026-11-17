"""Permite testar a classificacao e a API sem Arduino ou microfone."""
import argparse
import requests
from .classifier import classificar

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--texto", required=True)
    parser.add_argument("--salvar", action="store_true", help="Gravar no backend local")
    args = parser.parse_args()
    res = classificar(args.texto)
    print(f"Descricao: {args.texto}\nCategoria: {res.categoria}\nConfianca: {res.confianca:.1%}")
    if args.salvar:
        resposta = requests.post("http://127.0.0.1:8000/api/solicitacoes", json={
            "descricao": args.texto, "categoria": res.categoria, "confianca": res.confianca,
            "origem": "demo_texto"}, timeout=5)
        resposta.raise_for_status()
        print(f"Registro no backend local: {resposta.json()}")

if __name__ == "__main__":
    main()
