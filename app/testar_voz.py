"""Teste do microfone + Vosk independentemente do Arduino."""
import argparse
from .voice import Gravador, Transcritor
from .classifier import classificar

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mic', type=int, help='Numero do microfone; veja python -m app.voice')
    args = ap.parse_args()
    gravador = Gravador(args.mic)
    transcritor = Transcritor()
    input('Pressione ENTER para comecar a falar... ')
    gravador.iniciar()
    input('Fale sua solicitacao e pressione ENTER para parar... ')
    audio = gravador.parar()
    texto = transcritor.transcrever(audio)
    print('Transcricao:', texto or '(vazia)')
    if texto and len(texto.strip()) >= 8:
        resultado = classificar(texto)
        print(f'Categoria: {resultado.categoria} | Confianca: {resultado.confianca:.1%}')

if __name__ == '__main__':
    main()
