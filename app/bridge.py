"""Arduino <-> Python <-> Vosk <-> classificador <-> API local."""
import argparse
import time
from uuid import uuid4
import serial
import requests
from .voice import Gravador, Transcritor, MODELO_PADRAO, TAXA, MAX_GRAVACAO_S
from .classifier import classificar

class Ponte:
    def __init__(self, porta, api_url, modelo, dispositivo=None, confianca_minima=0.26):
        self.porta = porta
        self.api_url = api_url.rstrip("/")
        self.gravador = Gravador(dispositivo)
        self.transcritor = Transcritor(modelo)
        self.confianca_minima = confianca_minima
        if not 0 <= confianca_minima <= 1:
            raise ValueError("Confianca minima deve estar entre 0 e 1")
        self.pendente = None
        self.estado = "AGUARDANDO"
        self.iniciou_estado = time.monotonic()
        self.chave = None
        self.ultimo_id = None

    def mudar(self, estado):
        self.estado = estado
        self.iniciou_estado = time.monotonic()

    def cancelar(self):
        self.gravador.cancelar()
        self.pendente = None
        self.chave = None
        self.ultimo_id = None
        self.mudar("AGUARDANDO")

    def verificar_prazos(self, placa):
        decorrido = time.monotonic() - self.iniciou_estado
        if self.estado == "GRAVANDO" and decorrido > MAX_GRAVACAO_S:
            self.cancelar()
            self.escrever(placa, "RESULT:ERROR:TEMPO ESGOTADO")
        elif self.estado == "CONFIRMANDO" and decorrido > 45:
            self.cancelar()  # O Arduino tambem abandona a confirmacao em 45 s.

    @staticmethod
    def escrever(serial_arduino, comando):
        serial_arduino.write((comando + "\n").encode("ascii"))
        print(f"[PC -> Arduino] {comando}")

    def processar(self, evento, placa):
        self.verificar_prazos(placa)
        if evento in ("QUEM_FAZ_INICIADO", "EVENT:PRESENCE"):
            self.cancelar()
            print("[Arduino] Inicializacao detectada; sessao descartada"
                  if evento == "QUEM_FAZ_INICIADO" else "[PIR] Movimento detectado")
        elif evento == "EVENT:START_RECORD":
            if self.estado == "GRAVANDO":
                return  # Evento repetido nao interrompe a captura em andamento.
            self.cancelar()
            try:
                self.gravador.iniciar()
                self.mudar("GRAVANDO")
                print("[Microfone] GRAVANDO. Fale e pressione o botao novamente para parar.")
            except Exception as erro:
                print(f"[ERRO] Microfone: {erro}")
                self.escrever(placa, "RESULT:ERROR:MICROFONE")
        elif evento == "EVENT:STOP_RECORD":
            if self.estado != "GRAVANDO":
                return
            self.mudar("PROCESSANDO")
            try:
                audio = self.gravador.parar()
                if len(audio) < TAXA:  # Menos que meio segundo a 16 kHz x 16 bits
                    raise ValueError("Gravacao muito curta")
                texto = self.transcritor.transcrever(audio)
                print(f"[Voz reconhecida] {texto or '(vazio)'}")
                if not texto:
                    raise ValueError("Nao foi possivel reconhecer a fala")
                resultado = classificar(texto)
                print(f"[Classificacao ML] {resultado.categoria} - {resultado.confianca:.1%}")
                if resultado.confianca < self.confianca_minima:
                    raise ValueError(f"Classificacao incerta ({resultado.confianca:.1%}); fale novamente")
                if time.monotonic() - self.iniciou_estado > 85:
                    raise ValueError("Processamento excedeu o prazo do Arduino")
                self.pendente = (texto, resultado)
                self.chave = uuid4().hex
                self.escrever(placa, f"CLASSIFIED:{resultado.categoria}")
                self.mudar("CONFIRMANDO")
                print("[Confirmacao] Confira a categoria no LCD e aperte o botao novamente para registrar.")
            except Exception as erro:
                print(f"[ERRO] Processamento: {erro}")
                self.cancelar()
                self.escrever(placa, "RESULT:ERROR:REFAZER")
        elif evento == "EVENT:CONFIRM":
            if self.ultimo_id is not None:
                self.escrever(placa, f"RESULT:OK:{self.ultimo_id}")
                return
            if self.pendente is None:
                self.escrever(placa, "RESULT:ERROR:SEM PEDIDO")
                return
            texto, resultado = self.pendente
            try:
                resposta = requests.post(
                    f"{self.api_url}/api/solicitacoes",
                    json={"descricao": texto, "categoria": resultado.categoria,
                          "confianca": round(resultado.confianca, 4),
                          "origem": "smart_point_voz", "chave_idempotencia": self.chave},
                    timeout=8,
                )
                resposta.raise_for_status()
                dados = resposta.json()
                if (dados.get("status") != "REGISTRADO"
                        or type(dados.get("id")) is not int or dados["id"] <= 0
                        or dados.get("categoria") != resultado.categoria):
                    raise ValueError("Backend nao confirmou o registro")
                self.escrever(placa, f"RESULT:OK:{dados['id']}")
                print(f"[SUCESSO] Pedido #{dados['id']} salvo no backend LOCAL. Nao ha envio para profissionais reais.")
                self.pendente = None
                self.ultimo_id = dados["id"]
                self.mudar("RESULTADO")
            except Exception as erro:
                print(f"[ERRO] Nao foi possivel registrar: {erro}")
                self.escrever(placa, "RESULT:ERROR:SERVIDOR")
        else:
            print(f"[Evento nao reconhecido] {evento}")

    def executar(self):
        print(f"Conectando ao Arduino na {self.porta} (115200 baud)...")
        with serial.Serial(self.porta, 115200, timeout=0.2, write_timeout=2) as placa:
            # Leia tambem a inicializacao: nao descarte o banner nem eventos.
            print("Pronto. Aguarde a inicializacao do PIR e aproxime-se do sensor.")
            buffer = bytearray()
            try:
                while True:
                    self.verificar_prazos(placa)
                    buffer.extend(placa.read(placa.in_waiting or 1))
                    while b"\n" in buffer:
                        bruto, _, restante = buffer.partition(b"\n")
                        buffer = bytearray(restante)
                        linha = bruto.decode("ascii", errors="replace").strip()
                        if linha:
                            print(f"[Arduino -> PC] {linha}")
                            self.processar(linha, placa)
                    if len(buffer) > 256:
                        raise ValueError("Linha serial excedeu 256 bytes; confira firmware e baud rate")
            except KeyboardInterrupt:
                print("\nEncerrando conexao...")
            finally:
                self.cancelar()

def main():
    ap = argparse.ArgumentParser(description="Ponte entre Arduino e Quem Faz")
    ap.add_argument("--porta", required=True, help="Ex.: COM3 no Windows")
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--modelo", default=str(MODELO_PADRAO))
    ap.add_argument("--mic", type=int, help="Indice do microfone; obtenha em python -m app.voice")
    ap.add_argument("--confianca-minima", type=float, default=0.26)
    args = ap.parse_args()
    try:
        Ponte(args.porta, args.api, args.modelo, args.mic, args.confianca_minima).executar()
    except (serial.SerialException, OSError, ValueError, RuntimeError) as erro:
        ap.exit(1, f"Erro na ponte: {erro}\nConfira a porta COM, feche o Monitor Serial e verifique o modelo Vosk.\n")

if __name__ == "__main__":
    main()
