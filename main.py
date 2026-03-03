from __future__ import annotations

import csv
import hashlib
import io
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("APP_DB_PATH", str(ROOT / "finance.db"))).resolve()
STATIC_DIR = ROOT / "static"

app = FastAPI(title="Financeiro Familiar MVP", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none"}:
        return ""
    return text


def to_float(value: Any) -> float:
    text = normalize_text(value)
    if not text:
        return 0.0
    text = text.replace("R$", "").replace(" ", "")
    # handle pt-BR and en formats
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def to_bool(value: Any) -> int:
    text = normalize_text(value).lower()
    return 1 if text in {"1", "true", "sim", "yes"} else 0


def build_fallback_id(row: dict[str, Any]) -> str:
    raw = "|".join(
        [
            normalize_text(row.get("banco")),
            normalize_text(row.get("produto")),
            normalize_text(row.get("cartao_final_texto") or row.get("cartao_final")),
            normalize_text(row.get("data_compra_iso")),
            normalize_text(row.get("descricao_original")),
            str(to_float(row.get("valor_brl"))),
            normalize_text(row.get("parcela_texto")),
            normalize_text(row.get("fatura_referencia_vencimento")),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(get_connection()) as conn, conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS imports (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              filename TEXT NOT NULL,
              imported_at TEXT NOT NULL,
              source TEXT NOT NULL,
              row_count INTEGER NOT NULL,
              inserted_count INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              id_lancamento_sistema TEXT NOT NULL UNIQUE,
              chave_deduplicacao_sistema TEXT,
              banco TEXT,
              produto TEXT,
              cartao_final TEXT,
              eixo_titular TEXT,
              eixo_centro_custo TEXT,
              categoria_macro TEXT,
              categoria_subcategoria TEXT,
              descricao_original TEXT,
              parcela_texto TEXT,
              eh_parcelado INTEGER NOT NULL DEFAULT 0,
              sinal TEXT,
              valor_brl REAL NOT NULL DEFAULT 0,
              data_compra_iso TEXT,
              fatura_referencia_vencimento TEXT,
              fatura_referencia_competencia TEXT,
              fatura_chave TEXT,
              fatura_rotulo TEXT,
              arquivo_origem TEXT,
              tipo_documento_origem TEXT,
              created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tx_filters ON transactions (banco, produto, fatura_referencia_vencimento, eixo_titular)"
        )


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/")
def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "timestamp": now_iso()}


@app.post("/api/import/base-csv")
async def import_base_csv(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Envie um arquivo CSV.")

    payload = await file.read()
    try:
        decoded = payload.decode("utf-8")
    except UnicodeDecodeError:
        decoded = payload.decode("latin-1")

    sample = decoded[:2048]
    delimiter = ";" if sample.count(";") >= sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(decoded), delimiter=delimiter)

    rows = 0
    inserted = 0
    with closing(get_connection()) as conn, conn:
        for raw in reader:
            rows += 1
            tx_id = normalize_text(raw.get("id_lancamento_sistema")) or build_fallback_id(raw)
            try:
                conn.execute(
                    """
                    INSERT INTO transactions (
                      id_lancamento_sistema,chave_deduplicacao_sistema,banco,produto,cartao_final,
                      eixo_titular,eixo_centro_custo,categoria_macro,categoria_subcategoria,
                      descricao_original,parcela_texto,eh_parcelado,sinal,valor_brl,data_compra_iso,
                      fatura_referencia_vencimento,fatura_referencia_competencia,fatura_chave,fatura_rotulo,
                      arquivo_origem,tipo_documento_origem,created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        tx_id,
                        normalize_text(raw.get("chave_deduplicacao_sistema")),
                        normalize_text(raw.get("banco")),
                        normalize_text(raw.get("produto")),
                        normalize_text(raw.get("cartao_final_texto") or raw.get("cartao_final")),
                        normalize_text(raw.get("eixo_titular")),
                        normalize_text(raw.get("eixo_centro_custo")),
                        normalize_text(raw.get("categoria_macro")),
                        normalize_text(raw.get("categoria_subcategoria")),
                        normalize_text(raw.get("descricao_original")),
                        normalize_text(raw.get("parcela_texto")),
                        to_bool(raw.get("eh_parcelado")),
                        normalize_text(raw.get("sinal")).upper(),
                        to_float(raw.get("valor_brl")),
                        normalize_text(raw.get("data_compra_iso")),
                        normalize_text(raw.get("fatura_referencia_vencimento")),
                        normalize_text(raw.get("fatura_referencia_competencia")),
                        normalize_text(raw.get("fatura_chave")),
                        normalize_text(raw.get("fatura_rotulo")),
                        normalize_text(raw.get("arquivo_origem")),
                        normalize_text(raw.get("tipo_documento_origem")),
                        now_iso(),
                    ),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                # duplicate id_lancamento_sistema -> ignore safely
                pass

        conn.execute(
            "INSERT INTO imports (filename, imported_at, source, row_count, inserted_count) VALUES (?,?,?,?,?)",
            (file.filename, now_iso(), "csv", rows, inserted),
        )

    return {
        "filename": file.filename,
        "rows_read": rows,
        "rows_inserted": inserted,
        "rows_ignored_duplicates": rows - inserted,
    }


@app.get("/api/stats")
def stats() -> dict[str, Any]:
    with closing(get_connection()) as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"]
        soma = conn.execute("SELECT COALESCE(SUM(valor_brl), 0) AS s FROM transactions").fetchone()["s"]
        deb = conn.execute(
            "SELECT COALESCE(SUM(valor_brl), 0) AS s FROM transactions WHERE UPPER(sinal) = 'DEBITO'"
        ).fetchone()["s"]
        cre = conn.execute(
            "SELECT COALESCE(SUM(valor_brl), 0) AS s FROM transactions WHERE UPPER(sinal) = 'CREDITO'"
        ).fetchone()["s"]
        parc = conn.execute("SELECT COUNT(*) AS c FROM transactions WHERE eh_parcelado = 1").fetchone()["c"]
        fats = conn.execute("SELECT COUNT(DISTINCT fatura_chave) AS c FROM transactions").fetchone()["c"]
        imports = conn.execute(
            "SELECT id, filename, imported_at, row_count, inserted_count FROM imports ORDER BY id DESC LIMIT 10"
        ).fetchall()

    return {
        "total_registros": total,
        "saldo_liquido": float(soma),
        "debitos": float(deb),
        "creditos": float(cre),
        "parcelados": parc,
        "faturas_distintas": fats,
        "ultimas_importacoes": [dict(r) for r in imports],
    }


@app.get("/api/filters")
def filters() -> dict[str, Any]:
    with closing(get_connection()) as conn:
        def unique(col: str) -> list[str]:
            rows = conn.execute(
                f"SELECT DISTINCT {col} AS v FROM transactions WHERE {col} IS NOT NULL AND TRIM({col}) <> '' ORDER BY {col}"
            ).fetchall()
            return [r["v"] for r in rows]

        return {
            "bancos": unique("banco"),
            "produtos": unique("produto"),
            "titulares": unique("eixo_titular"),
            "categorias_macro": unique("categoria_macro"),
            "faturas_ref": unique("fatura_referencia_vencimento"),
            "cartoes": unique("cartao_final"),
        }


@app.get("/api/transactions")
def transactions(
    q: str = "",
    banco: str = "",
    produto: str = "",
    titular: str = "",
    categoria_macro: str = "",
    fatura_ref: str = "",
    cartao_final: str = "",
    limit: int = Query(default=300, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    where = ["1=1"]
    params: list[Any] = []

    if q.strip():
        where.append("(UPPER(descricao_original) LIKE ? OR UPPER(categoria_subcategoria) LIKE ?)")
        token = f"%{q.strip().upper()}%"
        params.extend([token, token])

    for key, col in [
        (banco, "banco"),
        (produto, "produto"),
        (titular, "eixo_titular"),
        (categoria_macro, "categoria_macro"),
        (fatura_ref, "fatura_referencia_vencimento"),
        (cartao_final, "cartao_final"),
    ]:
        if key.strip():
            where.append(f"{col} = ?")
            params.append(key.strip())

    where_sql = " AND ".join(where)

    with closing(get_connection()) as conn:
        total = conn.execute(f"SELECT COUNT(*) AS c FROM transactions WHERE {where_sql}", params).fetchone()["c"]
        rows = conn.execute(
            f"""
            SELECT *
            FROM transactions
            WHERE {where_sql}
            ORDER BY data_compra_iso DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        ).fetchall()

    return {"total": total, "rows": [dict(r) for r in rows]}


@app.get("/api/reconciliation")
def reconciliation() -> list[dict[str, Any]]:
    query = """
    WITH cc AS (
      SELECT
        banco,
        fatura_referencia_vencimento AS ref,
        SUM(valor_brl) AS total_conta,
        GROUP_CONCAT(DISTINCT descricao_original) AS descricoes
      FROM transactions
      WHERE produto = 'Conta Corrente'
        AND UPPER(categoria_subcategoria) = 'PAGAMENTO FATURA CARTAO'
      GROUP BY banco, ref
    ),
    cart AS (
      SELECT
        banco,
        fatura_referencia_vencimento AS ref,
        SUM(CASE WHEN UPPER(sinal)='DEBITO' THEN valor_brl ELSE 0 END) AS total_cartao
      FROM transactions
      WHERE produto = 'Cartao de Credito'
      GROUP BY banco, ref
    )
    SELECT
      COALESCE(cart.banco, cc.banco) AS banco,
      COALESCE(cart.ref, cc.ref) AS ref,
      COALESCE(cart.total_cartao, 0) AS total_cartao,
      COALESCE(cc.total_conta, 0) AS total_conta,
      COALESCE(cart.total_cartao, 0) + COALESCE(cc.total_conta, 0) AS diferenca,
      COALESCE(cc.descricoes, '') AS vinculos
    FROM cart
    LEFT JOIN cc ON cart.banco = cc.banco AND cart.ref = cc.ref
    UNION
    SELECT
      cc.banco,
      cc.ref,
      0 AS total_cartao,
      cc.total_conta,
      cc.total_conta AS diferenca,
      cc.descricoes
    FROM cc
    LEFT JOIN cart ON cart.banco = cc.banco AND cart.ref = cc.ref
    WHERE cart.banco IS NULL
    ORDER BY ref DESC, banco
    """

    with closing(get_connection()) as conn:
        rows = [dict(r) for r in conn.execute(query).fetchall()]

    for r in rows:
        diff = float(r["diferenca"])
        r["status"] = "OK" if abs(diff) < 0.01 else "DIVERGENTE"
    return rows


@app.delete("/api/reset")
def reset_db() -> dict[str, str]:
    with closing(get_connection()) as conn, conn:
        conn.execute("DELETE FROM transactions")
        conn.execute("DELETE FROM imports")
    return {"status": "ok"}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
