"""Banco SQLite local: fonte da verdade. Uma linha por processo e campo, com evidência."""
from __future__ import annotations

import secrets
import sqlite3
from pathlib import Path

from .campos import Campo
from .cnj import Cnj, hash_do_processo
from .config import proteger_escrita

ESQUEMA = """
CREATE TABLE IF NOT EXISTS processo (
  hash TEXT PRIMARY KEY, cnj TEXT NOT NULL, sistema TEXT, data_consulta TEXT,
  fase_base TEXT, arquivo TEXT, importado_em TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS campo (
  hash TEXT NOT NULL REFERENCES processo(hash), campo TEXT NOT NULL,
  estado TEXT NOT NULL CHECK (estado IN ('SIM','NAO','NAO_VISIVEL_NO_ACESSO_PUBLICO')),
  motivo_nao_visivel TEXT, valor TEXT, fonte TEXT, documento_origem TEXT,
  acesso_documento TEXT, data_da_fonte TEXT, evidencia_literal TEXT, localizacao TEXT,
  confianca TEXT, revisao_humana TEXT DEFAULT 'pendente', evidencia_confere INTEGER DEFAULT 1,
  extraido_em TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (hash, campo),
  CHECK (estado = 'NAO_VISIVEL_NO_ACESSO_PUBLICO' OR length(coalesce(evidencia_literal,'')) > 0)
);
"""


def segredo_local(dados: Path) -> bytes:
    arq = proteger_escrita(dados / "segredo.local")
    if not arq.exists():
        arq.write_bytes(secrets.token_bytes(32))
    return arq.read_bytes()


def abrir(dados: Path) -> sqlite3.Connection:
    arq = proteger_escrita(dados / "base.sqlite")
    con = sqlite3.connect(arq)
    con.executescript(ESQUEMA)
    return con


def _upsert_campos(con: sqlite3.Connection, h: str, campos: list[Campo]) -> None:
    for c in campos:
        antigo = con.execute(
            "SELECT estado, valor, revisao_humana FROM campo WHERE hash=? AND campo=?", (h, c.campo)
        ).fetchone()
        revisao = c.revisao
        if antigo and antigo[0] == c.estado and antigo[1] == c.valor:
            revisao = antigo[2]  # mesmo resultado: mantém a conferência já feita
        con.execute(
            "INSERT OR REPLACE INTO campo(hash,campo,estado,motivo_nao_visivel,valor,fonte,documento_origem,"
            "acesso_documento,data_da_fonte,evidencia_literal,localizacao,confianca,revisao_humana,evidencia_confere) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (h, c.campo, c.estado, c.motivo, c.valor, c.fonte, c.documento_origem, c.acesso_documento,
             c.data_da_fonte, c.evidencia, c.localizacao, c.confianca, revisao, int(c.evidencia_confere)),
        )
    con.commit()


def gravar(con: sqlite3.Connection, dados: Path, cnj: Cnj, sistema: str, data_consulta: str,
           fase_base: str | None, arquivo: str, campos: list[Campo]) -> str:
    h = hash_do_processo(cnj, segredo_local(dados))
    con.execute(
        "INSERT OR REPLACE INTO processo(hash,cnj,sistema,data_consulta,fase_base,arquivo) VALUES (?,?,?,?,?,?)",
        (h, cnj.formatado, sistema, data_consulta, fase_base, arquivo),
    )
    _upsert_campos(con, h, campos)
    return h


def gravar_extra(con: sqlite3.Connection, dados: Path, cnj: Cnj, campos: list[Campo],
                 fase_base: str | None = None) -> str:
    """Campos de outra fonte (DataJud). Não sobrescreve o processo já importado."""
    h = hash_do_processo(cnj, segredo_local(dados))
    con.execute(
        "INSERT OR IGNORE INTO processo(hash,cnj,sistema,fase_base) VALUES (?,?,?,?)",
        (h, cnj.formatado, "nao_informado", fase_base),
    )
    _upsert_campos(con, h, campos)
    return h
