"""Captura de microfone e transcricao de voz local com Vosk (portugues)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELO_PADRAO = ROOT / "models" / "vosk-model-small-pt-0.3"
TAXA = 16000
MAX_GRAVACAO_S = 32  # Margem para o STOP automatico de 30 s do firmware.

class Gravador:
    def __init__(self, dispositivo=None):
        self.dispositivo = dispositivo
        self.stream = None
        self.blocos = []
        self.erro_audio = None
        self.bytes_capturados = 0

    def _callback(self, indata, frames, time_info, status):
        if status:
            self.erro_audio = str(status)
        if self.bytes_capturados + len(indata) > MAX_GRAVACAO_S * TAXA * 2:
            self.erro_audio = "Tempo maximo de gravacao excedido"
            return
        self.blocos.append(bytes(indata))
        self.bytes_capturados += len(indata)

    def iniciar(self):
        import sounddevice as sd
        if self.stream is not None:
            raise RuntimeError("Ja esta gravando")
        self.blocos = []
        self.erro_audio = None
        self.bytes_capturados = 0
        sd.check_input_settings(device=self.dispositivo, channels=1,
                                dtype="int16", samplerate=TAXA)
        self.stream = sd.RawInputStream(samplerate=TAXA, blocksize=4000,
                                        dtype="int16", channels=1,
                                        device=self.dispositivo, callback=self._callback)
        try:
            self.stream.start()
        except Exception:
            try:
                self.stream.close()
            finally:
                self.stream = None
            raise

    def parar(self) -> bytes:
        if self.stream is None:
            raise RuntimeError("Nao ha gravacao ativa")
        try:
            self.stream.stop()
            if self.erro_audio:
                raise RuntimeError(f"Falha na captura de audio: {self.erro_audio}")
            return b"".join(self.blocos)
        finally:
            try:
                self.stream.close()
            finally:
                self.stream = None
                self.blocos = []

    def cancelar(self):
        """Libera o microfone e descarta o audio mesmo apos falha da captura."""
        if self.stream is not None:
            try:
                self.parar()
            except Exception as erro:
                print(f"[Microfone] Captura encerrada: {erro}")

class Transcritor:
    def __init__(self, pasta_modelo=MODELO_PADRAO):
        from vosk import Model, SetLogLevel
        pasta_modelo = Path(pasta_modelo)
        if not pasta_modelo.is_dir():
            raise FileNotFoundError(f"Modelo Vosk ausente em: {pasta_modelo}. Execute: python scripts/baixar_modelo.py")
        SetLogLevel(-1)
        self.modelo = Model(str(pasta_modelo))

    def transcrever(self, audio_pcm: bytes) -> str:
        from vosk import KaldiRecognizer
        if not audio_pcm:
            return ""
        rec = KaldiRecognizer(self.modelo, TAXA)
        partes = []
        for i in range(0, len(audio_pcm), 8000):
            if rec.AcceptWaveform(audio_pcm[i:i + 8000]):
                partes.append(json.loads(rec.Result()).get("text", ""))
        partes.append(json.loads(rec.FinalResult()).get("text", ""))
        return " ".join(parte for parte in partes if parte).strip()

if __name__ == "__main__":
    import sounddevice as sd
    print(sd.query_devices())
