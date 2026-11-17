"""Backend local de demonstracao (NAO envia para profissionais reais)."""
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from contextlib import closing
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from .dataset import CATEGORIAS

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "solicitacoes.sqlite3"
app = FastAPI(title="Quem Faz - Maker Lab", version="1.0")

class SolicitacaoEntrada(BaseModel):
    descricao: str = Field(min_length=8, max_length=600)
    categoria: str
    confianca: float = Field(ge=0, le=1)
    origem: str = "smart_point_voz"
    chave_idempotencia: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("descricao")
    @classmethod
    def validar_descricao(cls, valor):
        valor = valor.strip()
        if len(valor) < 8:
            raise ValueError("Descricao muito curta")
        return valor


def conectar():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    # Serializa tambem a primeira migracao se duas requisicoes chegarem juntas.
    con.execute("BEGIN IMMEDIATE")
    con.execute("""CREATE TABLE IF NOT EXISTS solicitacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        descricao TEXT NOT NULL,
        categoria TEXT NOT NULL,
        confianca REAL NOT NULL,
        origem TEXT NOT NULL,
        status TEXT NOT NULL,
        criado_em TEXT NOT NULL
    )""")
    # Migracao aditiva: preserva IDs e todos os pedidos anteriores.
    colunas = {linha[1] for linha in con.execute("PRAGMA table_info(solicitacoes)")}
    if "chave_idempotencia" not in colunas:
        con.execute("ALTER TABLE solicitacoes ADD COLUMN chave_idempotencia TEXT")
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_solicitacao_chave ON solicitacoes(chave_idempotencia)")
    con.commit()
    return con

@app.get("/")
def pagina():
    return FileResponse(ROOT / "web" / "index.html")

@app.get("/health")
def health():
    return {"status": "ok", "modo": "demonstracao_local"}

@app.post("/api/solicitacoes", status_code=201)
def criar_pedido(pedido: SolicitacaoEntrada):
    if pedido.categoria not in CATEGORIAS:
        raise HTTPException(status_code=422, detail="Categoria nao reconhecida")
    agora = datetime.now(timezone.utc).isoformat()
    with closing(conectar()) as con:
        with con:
            cursor = con.execute(
                """INSERT INTO solicitacoes
                   (descricao, categoria, confianca, origem, status, criado_em, chave_idempotencia)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(chave_idempotencia) DO NOTHING""",
                (pedido.descricao, pedido.categoria, pedido.confianca, pedido.origem,
                 "REGISTRADO", agora, pedido.chave_idempotencia),
            )
            id_pedido = cursor.lastrowid
            if cursor.rowcount == 0:
                anterior = con.execute("SELECT * FROM solicitacoes WHERE chave_idempotencia = ?",
                                       (pedido.chave_idempotencia,)).fetchone()
                if any(anterior[campo] != getattr(pedido, campo)
                       for campo in ("descricao", "categoria", "confianca", "origem")):
                    raise HTTPException(status_code=409, detail="Chave ja utilizada em outro pedido")
                id_pedido = anterior["id"]
    return {"id": id_pedido, "status": "REGISTRADO", "categoria": pedido.categoria, "modo": "demonstracao_local"}

@app.get("/api/solicitacoes")
def listar_pedidos():
    with closing(conectar()) as con:
        linhas = con.execute("SELECT * FROM solicitacoes ORDER BY id DESC LIMIT 100").fetchall()
    return [dict(linha) for linha in linhas]
