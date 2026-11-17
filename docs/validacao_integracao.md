# Diagnóstico e validação da integração — 15/11/2026

## Erro de gravação encerrada imediatamente

O `loop()` lia `agora = millis()` antes de `lerSerial()` e `lerBotao()`.
Essas funções podem chamar `mudar()`, que atualiza `iniciouEstado` com um horário posterior.
Na aritmética `unsigned long` de 32 bits do UNO, `40000 - 40001` resulta em
`4294967295`. Assim, uma gravação recém-iniciada podia ultrapassar aparentemente
o limite de 30000 ms. A mesma falha afetava processamento, confirmação e resultado.

Todas as comparações agora consultam `millis()` no momento de verificar o prazo,
após a possível transição. Foram preservados debounce de 55 ms, ligação D8/GND,
limites de tempo, protocolo serial e biblioteca hd44780_I2Cexp.
O firmware precisa ser **carregado novamente pela Arduino IDE** para a correção
ter efeito na placa física.

## Outras correções

- Ponte mantém estado próprio e ignora START/STOP repetidos. A captura só começa com START.
- Banner `QUEM_FAZ_INICIADO` e nova presença descartam áudio e pedido pendente.
- Confirmação pendente expira em 45 s. Sem confirmação, não há POST ao backend.
- Serial é acumulada até a quebra de linha, mesmo com leituras fragmentadas.
  Não há descarte do buffer de inicialização do UNO.
- Microfone é liberado após falhas, desconexão e encerramento. Captura em PCM
  mono de 16 bits/16000 Hz é verificada antes de abrir o stream. Dispositivos sem
  suporte a essa configuração exigem outro índice de entrada; não há reamostragem.
- Captura limitada a 32 s no PC (margem para STOP automático aos 30 s do Arduino).
  Perda de áudio é tratada como erro; blocos são descartados após uso.
- Limiar do classificador preservado em **0,26**. Confiança é do classificador,
  não uma medida de precisão da transcrição.
- Cada classificação aceita recebe chave UUID. POSTs repetidos com a mesma chave
  retornam o mesmo ID; conteúdo diferente com a mesma chave retorna HTTP 409.
  Repetir a confirmação após sucesso não produz outro POST.
- A API adiciona coluna e índice de idempotência sem apagar pedidos existentes.
  Descrições com apenas espaços são rejeitadas.
- Sucesso serial exige ID inteiro positivo, status REGISTRADO e categoria esperada.
- Interface exibe origem; o teste por texto identifica seus pedidos como `demo_texto`.
- README e sketch auxiliar 02 foram alinhados ao LCD I²C real.

## Evidências automatizadas

Os 9 testes originais passaram antes das modificações. A suíte ampliada teve
**46 testes aprovados** (um aviso de descontinuação de httpx/Starlette, sem falhas) e cobre
API, classificação, áudio simulado, eventos duplicados, falhas de servidor,
reinicialização, expiração, serial fragmentada, desconexão, migração de banco,
concorrência e fluxo completo com API e SQLite temporário.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

Testes de integração usam microfone e serial simulados. Não gravam no banco de
uso do projeto e não comprovam funcionamento físico. Na validação de 15/11, o
firmware principal e dois sketches auxiliares então existentes foram compilados
para `arduino:avr:uno`; os auxiliares não estão na versão atual da pasta.
Compilação não equivale a teste na placa.
O principal usa 10338 bytes de programa (32%) e 975 bytes de variáveis globais (47%).
`pip check` não encontrou dependências quebradas; o modelo Vosk real carregou e
retornou texto vazio para PCM de silêncio. O JavaScript passou em `node --check`.
O banco original permaneceu com seu pedido existente, sem alterações nesta validação.

## Arquivos alterados ou adicionados

- `arduino/quem_faz_smart_point/quem_faz_smart_point.ino`: correção dos temporizadores.
- `app/bridge.py`: estados, prazos, leitura serial, confirmação e chave idempotente.
- `app/voice.py`: validação da captura, limites e liberação de recursos.
- `app/api.py`: validação e persistência idempotente, com migração aditiva.
- `app/demo.py`: origem específica para teste por texto.
- `web/index.html`: exibição da origem na listagem.
- `tests/test_api.py`: novos cenários de API, migração e concorrência.
- `tests/test_bridge.py` e `tests/test_voice.py`: novos testes de integração e áudio.
- `README.md` e `docs/validacao_integracao.md`: instruções e evidências.

## Iniciar no Windows

Feche a ponte Python antes de carregar o sketch principal. Na Arduino IDE,
selecione Arduino Uno e a porta correta, verifique e carregue
`arduino/quem_faz_smart_point/quem_faz_smart_point.ino`. Feche o Monitor Serial.

Terminal 1, dentro da pasta do projeto:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.api:app --host 127.0.0.1 --port 8000
```

Terminal 2:

```powershell
.\.venv\Scripts\python.exe -m serial.tools.list_ports
.\.venv\Scripts\python.exe -m app.bridge --porta COM3
```

Nesta inspeção, COM3 correspondia ao adaptador **Silicon Labs CP210x**. Confirme
na Arduino IDE que é a porta da placa; COM1 e COM2 também estavam listadas.
Abrir a serial pode reiniciar o UNO; aguarde os 30 s de aquecimento do PIR.
Para escolher outro microfone:

```powershell
.\.venv\Scripts\python.exe -m app.voice
.\.venv\Scripts\python.exe -m app.bridge --porta COM3 --mic 1
```

Substitua `1` pelo índice real de entrada; não abra duas pontes simultaneamente.

## Roteiro físico obrigatório

1. Abra `http://127.0.0.1:8000` e anote o último ID já existente.
2. Após aquecimento, aproxime-se: LCD deve mostrar presença e pedir botão.
3. Pressione e solte o botão uma vez; aguarde 3–5 s. Deve continuar GRAVANDO,
   sem passar imediatamente para processamento ou erro.
4. Fale: “Preciso de um encanador para consertar um vazamento na cozinha”.
5. Pressione e solte novamente: deve passar para PROCESSANDO. Confira no terminal
   START, STOP, transcrição e `CLASSIFIED:HIDRAULICA`.
6. Confirme que **ainda não existe um novo pedido** na interface.
7. Confira a categoria e pressione pela terceira vez. Aguarde ID no LCD.
8. Na interface, confira mesmo ID, texto, categoria, confiança, status, origem e horário.
9. Repita sem segundo clique: só deve parar automaticamente após aproximadamente 30 s.
10. Repita e não confirme: após aproximadamente 45 s, deve voltar à espera e não salvar.
11. Teste silêncio: deve apresentar REFAZER, sem novo registro.
12. Pare o backend, faça novo pedido e confirme: deve apresentar SERVIDOR, sem sucesso falso.
13. Reinicie o backend. Reinicie a placa durante gravação: a ponte deve receber o banner,
    liberar o microfone e permitir nova jornada após aquecimento.
14. Desconecte o USB: a ponte deve encerrar com erro legível. Reconecte e execute-a novamente.

## Limitações e entrega

- Ainda é necessária a validação física deste firmware corrigido com a ponte.
- Transcrição e HTTP são síncronos. O PC só lê novos eventos após essas operações;
  há limites de tempo, mas não há cancelamento imediato de uma transcrição em andamento.
  Se a placa reiniciar nessa etapa, aguarde retorno ao início antes de tentar outro pedido.
- Se o backend salvar e a resposta HTTP se perder, pode existir pedido na interface
  mesmo com erro no LCD. A mesma chave impede duplicidade em uma retransmissão;
  iniciar uma nova gravação cria uma nova solicitação. Confira a interface antes de repetir.
- Não há reconexão serial automática nem protocolo com identificação da sessão no firmware.
- Dataset sintético pequeno e Vosk leve podem errar. Não há envio a profissionais reais.
- Preencher nomes/RMs e link do vídeo; confirmar com professor a aceitação do assistente
  estacionário, evolução de robô anterior e requisito de sensor adicional.
- Preservar `.gitignore` para ambiente virtual, banco, modelos e áudio ao publicar.
