"""Planilha .xlsx para a equipe: uma linha por processo, gerada do banco.

A planilha nunca é fonte de verdade. Juízos de IA ou inferências saem em vermelho.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .campos import NV, Campo, compara_fase
from .config import proteger_escrita

CAMPOS_ORDEM = [
    ("parte_alvo_no_polo_passivo", "Parte-alvo no polo passivo", False),
    ("fase", "Fase no tribunal", True),
    ("pericia", "Perícia", False),
    ("pericia_laudo_juizo", "Laudo: favorável ou desfavorável (humano)", True),
    ("acordo", "Acordo", False),
    ("desistencia_ou_renuncia", "Desistência ou renúncia", False),
    ("decisao", "Sentença ou acórdão", False),
    ("decisao_juizo", "Decisão: favorável ou desfavorável (humano)", True),
    ("transito_em_julgado", "Trânsito em julgado", False),
]
VERMELHO = Font(color="C00000")
CINZA = PatternFill("solid", fgColor="EDEDED")


def _txt(estado: str, valor: str, motivo: str) -> str:
    if estado == NV:
        return f"NÃO VISÍVEL NO ACESSO PÚBLICO ({motivo})" + (f": {valor}" if valor else "")
    return f"{estado}: {valor}" if valor else estado


def gerar(con: sqlite3.Connection, destino: Path) -> Path:
    destino = proteger_escrita(destino)
    wb = Workbook()
    ws = wb.active
    ws.title = "Processos"
    cab = ["Processo", "Sistema", "Fase na base do cliente"] + [n for _, n, _ in CAMPOS_ORDEM] + [
        "Fase: base x tribunal", "Evidências (campo: trecho literal, onde)",
        "Conferido por", "Correção", "Observação",
    ]
    ws.append(cab)
    for cel in ws[1]:
        cel.font = Font(bold=True)
        cel.fill = CINZA
        cel.alignment = Alignment(wrap_text=True, vertical="top")
    for h, cnj, sistema, fase_base in con.execute(
        "SELECT hash,cnj,sistema,fase_base FROM processo ORDER BY cnj"
    ).fetchall():
        linhas = {
            r[0]: r
            for r in con.execute(
                "SELECT campo,estado,valor,motivo_nao_visivel,evidencia_literal,localizacao FROM campo WHERE hash=?",
                (h,),
            )
        }
        linha = [cnj, sistema, fase_base or ""]
        evid = []
        for chave, _nome, _ia in CAMPOS_ORDEM:
            r = linhas.get(chave)
            if r is None:
                linha.append("não extraído")
                continue
            linha.append(_txt(r[1], r[2] or "", r[3] or ""))
            if r[4]:
                evid.append(f"{chave}: “{r[4]}” ({r[5]})")
        fase_c = linhas.get("fase")
        cmp_ = "indeterminado"
        if fase_c:
            cmp_ = compara_fase(fase_base, Campo(campo="fase", estado=fase_c[1], valor=fase_c[2] or ""))
        linha += [cmp_, "\n".join(evid), "", "", ""]
        ws.append(linha)
        for i, (_c, _n, ia) in enumerate(CAMPOS_ORDEM):
            cel = ws.cell(row=ws.max_row, column=4 + i)
            cel.alignment = Alignment(wrap_text=True, vertical="top")
            if ia:
                cel.font = VERMELHO
        ws.cell(row=ws.max_row, column=len(cab) - 3).alignment = Alignment(wrap_text=True, vertical="top")
    for col, larg in zip("ABCDEFGHIJKLMNOPQRS", [27, 12, 22] + [30] * 9 + [16, 80, 16, 24, 24]):
        ws.column_dimensions[col].width = larg
    ws.freeze_panes = "B2"

    leg = wb.create_sheet("Legenda")
    for linha in [
        ["Estado", "Significado"],
        ["SIM", "texto positivo encontrado; o trecho literal está na coluna de evidências"],
        ["NAO", "só com texto positivo que afirme o negativo, ou lista completa lida"],
        ["NÃO VISÍVEL NO ACESSO PÚBLICO", "o que foi colado não permite afirmar. Ausência nunca vira “não houve”"],
        ["Vermelho", "inferência ou juízo que exige revisão humana (favorável ou desfavorável)"],
        ["Fase: base x tribunal", "coincide, diverge ou indeterminado. Divergência é reportada, não corrigida"],
    ]:
        leg.append(linha)
    leg.column_dimensions["A"].width = 34
    leg.column_dimensions["B"].width = 100
    wb.save(destino)
    return destino
