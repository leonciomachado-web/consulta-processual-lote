"""Limpeza da planilha de entrada e sorteio do piloto.

O formato da planilha varia por quem usa. Um arquivo de mapeamento local diz quais
colunas são quais (expressão regular sobre o cabeçalho). Nada aqui conhece cliente.
"""
from __future__ import annotations

import csv
import random
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook

from .cnj import Cnj, tratar
from .config import proteger_escrita
from .textos import norm

PAPEIS = ("cnj", "tribunal", "tipo_pasta", "tipo_vara", "fase_base", "rito")


@dataclass
class Linha:
    n: int
    cnj_bruto: str
    cnj: Cnj | None
    atributos: dict[str, str]


def _acha_colunas(cabecalho: list, mapa: dict[str, str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for papel, padrao in mapa.items():
        rx = re.compile(padrao, re.I)
        for i, h in enumerate(cabecalho):
            if h is not None and rx.search(str(h)):
                out[papel] = i
                break
    return out


def ler_planilha(caminho: Path, mapa: dict[str, str], aba: str | None = None) -> list[Linha]:
    wb = load_workbook(caminho, read_only=True, data_only=True)
    ws = wb[aba] if aba else wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    cols = _acha_colunas(list(rows[0]), mapa)
    if "cnj" not in cols:
        raise ValueError("coluna do número do processo não encontrada com o mapeamento dado")
    out: list[Linha] = []
    for n, r in enumerate(rows[1:], start=2):
        bruto = "" if r[cols["cnj"]] is None else str(r[cols["cnj"]])
        attrs = {k: ("" if r[i] is None else str(r[i]).strip()) for k, i in cols.items() if k != "cnj"}
        out.append(Linha(n=n, cnj_bruto=bruto, cnj=tratar(bruto), atributos=attrs))
    return out


def classificar(linhas: list[Linha], regras: dict) -> tuple[list[Linha], list[tuple[Linha, str]], list[tuple[Linha, str]]]:
    """Devolve (elegíveis, excluídos com motivo, alertas). Ordem das regras = ordem do texto."""
    elegiveis: list[Linha] = []
    excluidos: list[tuple[Linha, str]] = []
    alertas: list[tuple[Linha, str]] = []
    jtr = regras.get("jtr_alvo")  # ex.: "8.19"
    for l in linhas:
        a = l.atributos
        motivo = None
        for termo in regras.get("excluir_tipo_pasta_contem", []):
            if termo.lower() in norm(a.get("tipo_pasta", "")):
                motivo = f"tipo da pasta: {termo}"
        if motivo is None and not l.cnj_bruto.strip():
            motivo = "sem número de processo"
        elif motivo is None and l.cnj is None:
            motivo = "número fora do padrão"
        elif motivo is None and jtr and l.cnj.jtr != jtr:
            motivo = "número de outro tribunal"
        elif motivo is None and not l.cnj.dv_confere:
            motivo = "dígito verificador inválido"
        if motivo is None:
            for termo in regras.get("excluir_tipo_vara_contem", []):
                if termo.lower() in norm(a.get("tipo_vara", "")):
                    motivo = f"tipo de vara: {termo}"
        if motivo:
            excluidos.append((l, motivo))
            continue
        rotulo = norm(a.get("tribunal", ""))
        esperado = regras.get("rotulo_tribunal_esperado")
        if esperado and rotulo and norm(esperado) not in rotulo:
            alertas.append((l, "rótulo do tribunal na base não bate com o número do processo"))
        elegiveis.append(l)
    return elegiveis, excluidos, alertas


def categoria_fase(fase_base: str) -> str:
    t = norm(fase_base)
    # "extin" antes de "julgamento": "extinção sem julgamento de mérito" contém as duas palavras
    for chave, cat in (("inicial", "inicial"), ("pagamento", "pagamento_final"), ("instrut", "instrutoria"),
                       ("extin", "extincao"), ("julgamento", "julgamento")):
        if chave in t:
            return cat
    return "outras"


def sortear_piloto(elegiveis: list[Linha], quotas: dict[str, int], semente: int, incluir: list[str] | None = None) -> list[Linha]:
    """Sorteio estratificado por fase da base, com semente fixa e registrada."""
    rnd = random.Random(semente)
    por_cat: dict[str, list[Linha]] = {}
    for l in elegiveis:
        por_cat.setdefault(categoria_fase(l.atributos.get("fase_base", "")), []).append(l)
    escolhidos: list[Linha] = []
    for cat, q in quotas.items():
        pool = sorted(por_cat.get(cat, []), key=lambda x: x.n)
        escolhidos += rnd.sample(pool, min(q, len(pool)))
    fixos = set(incluir or [])
    for l in elegiveis:
        if l.cnj and l.cnj.formatado in fixos and l not in escolhidos:
            escolhidos.append(l)
    return escolhidos


def gravar_csv(destino: Path, cabecalho: list[str], linhas: list[list[str]]) -> Path:
    destino = proteger_escrita(destino)
    with open(destino, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(cabecalho)
        w.writerows(linhas)
    return destino


def resumo(elegiveis, excluidos, alertas) -> dict:
    return {
        "total": len(elegiveis) + len(excluidos),
        "elegiveis": len(elegiveis),
        "excluidos_por_motivo": dict(Counter(m for _, m in excluidos)),
        "alertas": dict(Counter(m for _, m in alertas)),
    }
