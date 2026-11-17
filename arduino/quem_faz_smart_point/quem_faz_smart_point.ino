
/*
  QUEM FAZ SMART POINT
  GLOBAL SOLUTION - MAKER LAB

  Componentes:
  - Arduino UNO R3
  - LCD 16x2 I2C (SDA=A4, SCL=A5)
  - Sensor PIR (D7)
  - Botao fisico (D8 e GND)
  - Buzzer opcional (D9)

  Funcionamento:
  1. Detecta presenca pelo PIR
  2. Botao inicia gravacao de voz
  3. Botao encerra gravacao
  4. Python reconhece e classifica o servico
  5. LCD mostra a categoria identificada
  6. Botao confirma o pedido
  7. LCD mostra o resultado do registro local
*/

#include <Wire.h>
#include <hd44780.h>
#include <hd44780ioClass/hd44780_I2Cexp.h>

// LCD I2C
hd44780_I2Cexp lcd;

// Pinos do Arduino
const byte PIN_PIR = 7;
const byte PIN_BOTAO = 8;
const byte PIN_BUZZER = 9;

// Tempos em milissegundos
const unsigned long AQUECIMENTO_PIR_MS = 30000;
const unsigned long TEMPO_PRESENCA_MS = 15000; // 15 s para apertar o botao
const unsigned long TEMPO_GRAVACAO_MS = 30000;
const unsigned long TEMPO_PROCESSAMENTO_MS = 90000;
const unsigned long TEMPO_CONFIRMACAO_MS = 45000;
const unsigned long TEMPO_ENVIO_MS = 30000;
const unsigned long TEMPO_RESULTADO_MS = 10000;

// Estados do sistema
enum Estado {
  AGUARDANDO,
  PRONTO,
  GRAVANDO,
  PROCESSANDO,
  CONFIRMANDO,
  ENVIANDO,
  RESULTADO
};

Estado estado = AGUARDANDO;

// Variaveis de controle
unsigned long iniciouEstado = 0;
unsigned long iniciouSistema = 0;
unsigned long ultimoDebounce = 0;
unsigned long ultimaTela = 0;

bool ultimoBotaoBruto = HIGH;
bool botaoEstavel = HIGH;
bool exibindoCategoria = true;

// Dados da IA
char categoria[17] = "";
char linhaSerial[48];
byte posSerial = 0;


// =====================================
// CONTROLE DO LCD
// =====================================

void tela(const char *linha1, const char *linha2) {
  lcd.clear();

  lcd.setCursor(0, 0);
  lcd.print(linha1);

  lcd.setCursor(0, 1);
  lcd.print(linha2);
}


// =====================================
// CONTROLE DOS ESTADOS
// =====================================

void mudar(Estado novoEstado) {
  estado = novoEstado;
  iniciouEstado = millis();
}


// =====================================
// SINAL SONORO
// =====================================

void sinalizar(bool sucesso) {
  tone(
    PIN_BUZZER,
    sucesso ? 1300 : 380,
    sucesso ? 100 : 250
  );
}


// =====================================
// AGUARDAR NOVO USUARIO
// =====================================

void esperarNovoUsuario() {
  mudar(AGUARDANDO);

  tela(
    "AGUARDANDO",
    "PRESENCA..."
  );
}


// =====================================
// EXIBIR ERRO
// =====================================

void mostrarErro(const char *tipo) {
  mudar(RESULTADO);

  tela(
    "ERRO NO PEDIDO",
    tipo
  );

  sinalizar(false);
}


// =====================================
// CONTROLE DO BOTAO
// =====================================

void pressionouBotao() {

  // PRIMEIRO CLIQUE: INICIAR GRAVACAO
  if (estado == PRONTO) {

    mudar(GRAVANDO);

    tela(
      "GRAVANDO VOZ",
      "BOTAO = PARAR"
    );

    Serial.println("EVENT:START_RECORD");

    sinalizar(true);
  }

  // SEGUNDO CLIQUE: PARAR GRAVACAO
  else if (estado == GRAVANDO) {

    mudar(PROCESSANDO);

    tela(
      "PROCESSANDO",
      "AGUARDE..."
    );

    Serial.println("EVENT:STOP_RECORD");
  }

  // TERCEIRO CLIQUE: CONFIRMAR PEDIDO
  else if (estado == CONFIRMANDO) {

    mudar(ENVIANDO);

    tela(
      "REGISTRANDO",
      "PEDIDO..."
    );

    Serial.println("EVENT:CONFIRM");
  }

  // REINICIAR APOS RESULTADO
  else if (estado == RESULTADO) {

    esperarNovoUsuario();
  }
}


// =====================================
// RECEBER RESPOSTAS DO PYTHON
// =====================================

void receberComando(const char *comando) {

  // CLASSIFICACAO RECEBIDA
  if (
    strncmp(comando, "CLASSIFIED:", 11) == 0 &&
    estado == PROCESSANDO
  ) {

    strncpy(categoria, comando + 11, 16);
    categoria[16] = '\0';

    mudar(CONFIRMANDO);

    exibindoCategoria = true;
    ultimaTela = millis();

    tela(
      "CATEGORIA:",
      categoria
    );

    sinalizar(true);
  }

  // PEDIDO REGISTRADO
  else if (
    strncmp(comando, "RESULT:OK:", 10) == 0 &&
    estado == ENVIANDO
  ) {

    char id[17] = "ID ";

    strncat(id, comando + 10, 13);

    mudar(RESULTADO);

    tela(
      "PEDIDO REGISTR.",
      id
    );

    sinalizar(true);
  }

  // ERRO RECEBIDO
  else if (
    strncmp(comando, "RESULT:ERROR:", 13) == 0
  ) {

    mostrarErro(comando + 13);
  }
}


// =====================================
// COMUNICACAO SERIAL
// =====================================

void lerSerial() {

  while (Serial.available()) {

    char c = (char)Serial.read();

    if (c == '\r') {
      continue;
    }

    if (c == '\n') {

      linhaSerial[posSerial] = '\0';

      if (posSerial > 0) {
        receberComando(linhaSerial);
      }

      posSerial = 0;
    }

    else if (
      posSerial < sizeof(linhaSerial) - 1
    ) {

      linhaSerial[posSerial++] = c;
    }

    else {
      posSerial = 0;
    }
  }
}


// =====================================
// LEITURA DO BOTAO COM DEBOUNCE
// =====================================

void lerBotao() {

  bool leitura = digitalRead(PIN_BOTAO);

  if (leitura != ultimoBotaoBruto) {
    ultimoDebounce = millis();
  }

  if (
    millis() - ultimoDebounce > 55 &&
    leitura != botaoEstavel
  ) {

    botaoEstavel = leitura;

    if (botaoEstavel == LOW) {
      pressionouBotao();
    }
  }

  ultimoBotaoBruto = leitura;
}


// =====================================
// CONFIGURACAO INICIAL
// =====================================

void setup() {

  Serial.begin(115200);

  pinMode(PIN_PIR, INPUT);
  pinMode(PIN_BOTAO, INPUT_PULLUP);
  pinMode(PIN_BUZZER, OUTPUT);

  // INICIAR LCD I2C
  int status = lcd.begin(16, 2);

  if (status != 0) {
    Serial.println("ERRO_LCD");
    hd44780::fatalError(status);
  }

  iniciouSistema = millis();

  tela(
    "QUEM FAZ",
    "AQUECENDO PIR"
  );

  Serial.println("QUEM_FAZ_INICIADO");
}


// =====================================
// LOOP PRINCIPAL
// =====================================

void loop() {

  // Leia millis() em cada comparacao: lerSerial/lerBotao podem chamar mudar().
  // Um horario capturado antes disso pode ser menor que iniciouEstado e causar
  // estouro unsigned, encerrando uma gravacao nova como se o prazo tivesse passado.
  // Comunicacao com Python
  lerSerial();

  // Leitura do botao
  lerBotao();

  // Aguarda o aquecimento do PIR
  if (
    millis() - iniciouSistema <
    AQUECIMENTO_PIR_MS
  ) {
    return;
  }

  // Inicializar tela de espera
  if (
    estado == AGUARDANDO &&
    iniciouEstado == 0
  ) {
    esperarNovoUsuario();
  }

  // DETECTAR PRESENCA
  if (
    estado == AGUARDANDO &&
    digitalRead(PIN_PIR) == HIGH
  ) {

    mudar(PRONTO);

    tela(
      "PRESENCA OK",
      "APERTE BOTAO"
    );

    Serial.println("EVENT:PRESENCE");

    sinalizar(true);
  }

  // TEMPO LIMITE DE PRESENCA
  if (
    estado == PRONTO &&
    millis() - iniciouEstado > TEMPO_PRESENCA_MS
  ) {

    esperarNovoUsuario();
  }

  // TEMPO MAXIMO DE GRAVACAO
  if (
    estado == GRAVANDO &&
    millis() - iniciouEstado > TEMPO_GRAVACAO_MS
  ) {

    mudar(PROCESSANDO);

    tela(
      "PROCESSANDO",
      "AGUARDE..."
    );

    Serial.println("EVENT:STOP_RECORD");
  }

  // TEMPO LIMITE DE PROCESSAMENTO
  if (
    estado == PROCESSANDO &&
    millis() - iniciouEstado > TEMPO_PROCESSAMENTO_MS
  ) {

    mostrarErro("TEMPO ESGOTADO");
  }

  // AGUARDANDO CONFIRMACAO
  if (estado == CONFIRMANDO) {

    if (
      millis() - iniciouEstado >
      TEMPO_CONFIRMACAO_MS
    ) {

      esperarNovoUsuario();
    }

    else if (
      millis() - ultimaTela > 3500
    ) {

      exibindoCategoria = !exibindoCategoria;
      ultimaTela = millis();

      if (exibindoCategoria) {

        tela(
          "CATEGORIA:",
          categoria
        );

      } else {

        tela(
          "CONFIRMAR PEDIDO",
          "APERTE BOTAO"
        );
      }
    }
  }

  // TEMPO LIMITE PARA REGISTRO
  if (
    estado == ENVIANDO &&
    millis() - iniciouEstado > TEMPO_ENVIO_MS
  ) {

    mostrarErro("SEM RESPOSTA");
  }

  // RETORNAR AO INICIO
  if (
    estado == RESULTADO &&
    millis() - iniciouEstado > TEMPO_RESULTADO_MS
  ) {

    esperarNovoUsuario();
  }
}
