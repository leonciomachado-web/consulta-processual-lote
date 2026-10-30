"""Lê o texto que uma pessoa copiou da tela de um processo e separa as partes.

Formato aceito (ver examples/processo_sintetico.txt):
- linhas `#! chave: valor` no começo (metadados que a pessoa preenche);
- corpo colado da tela: capa, personagens, movimentos;
- blocos opcionais `=== INTEGRA <rótulo> ===` ... `=== FIM ===` com o texto de um
  documento que a pessoa conseguiu abrir sem login.

O parser não decide nada jurídico. Ele só organiza e preserva o texto bruto para que
cada campo extraído aponte para um trecho literal.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .cnj import PADRAO as PADRAO_CNJ
from .cnj import Cnj, tratar
from .textos import espaco, norm

PAPEIS_ATIVO = {"autor", "autora", "requerente", "exequente", "reclamante", "embargante", "impetrante"}
PAPEIS_PASSIVO = {"reu", "re", "requerido", "requerida", "executado", "reclamado", "embargado", "impetrado"}
PAPEIS_ADV = {"advogado", "advogados", "advogado(s)", "advogada"}
PAPEIS_OUTROS = {"terceiro", "interessado", "assistente", "litisconsorte", "perito", "denunciado"}
PAPEIS = PAPEIS_ATIVO | PAPEIS_PASSIVO | PAPEIS_ADV | PAPEIS_OUTROS

ROTULOS_CAPA = {
    "comarca": "comarca",
    "vara": "vara",
    "serventia": "serventia",
    "competencia": "competencia",
    "assunto": "assunto",
    "classe": "classe",
    "localizacao na serventia": "localizacao",
    "oficio de registro": "oficio",
}

_RE_META = re.compile(r"^#!\s*([\w\-]+)\s*:\s*(.*)$")
_RE_INTEGRA = re.compile(r"^=== INTEGRA (.+?) ===\s*$")
_RE_DATA = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")
_RE_ADV = re.compile(r"^\(?[A-Z]{2}\s?\d+\)?\s*[-–]?\s*(.+)$")


@dataclass
class Personagem:
    papel: str
    polo: str  # ativo | passivo | advogado | outro
    nome: str
    linha: str  # texto literal de onde saiu


@dataclass
class Movimento:
    indice: int
    tipo: str
    data: str | None
    texto: str  # bloco bruto do movimento, para evidência literal


@dataclass
class Documento:
    rotulo: str
    texto: str
    acesso: str = "publico"


@dataclass
class Processo:
    cnj: Cnj | None
    meta: dict[str, str] = field(default_factory=dict)
    capa: dict[str, str] = field(default_factory=dict)
    distribuicao: str | None = None
    personagens: list[Personagem] = field(default_factory=list)
    movimentos: list[Movimento] = field(default_factory=list)
    documentos: list[Documento] = field(default_factory=list)
    texto: str = ""  # corpo bruto, sem metadados

    @property
    def sistema(self) -> str:
        return self.meta.get("sistema", "nao_informado")

    @property
    def partes_lista_completa(self) -> bool:
        return norm(self.meta.get("partes_lista_completa", "")) in {"sim", "s", "true"}

    @property
    def movimentos_lista_completa(self) -> bool:
        return norm(self.meta.get("movimentos_lista_completa", "")) in {"sim", "s", "true"}


def _linhas_nao_vazias(linhas: list[str]) -> list[tuple[int, str]]:
    return [(i, l.strip()) for i, l in enumerate(linhas) if l.strip()]


def _extrai_personagens(linhas: list[str]) -> list[Personagem]:
    out: list[Personagem] = []
    papel_atual: str | None = None
    for raw in linhas:
        l = raw.strip()
        if not l:
            continue
        # linha de tabela: "Autor<TAB>NOME" ou "Autor   NOME"
        partes = re.split(r"\t+|\s{2,}", l, maxsplit=1)
        if len(partes) == 2 and norm(partes[0]) in PAPEIS:
            _adiciona(out, norm(partes[0]), partes[1], l)
            papel_atual = None
            continue
        if norm(l) in PAPEIS:
            papel_atual = norm(l)
            continue
        if papel_atual:
            if papel_atual in PAPEIS_ADV:
                m = _RE_ADV.match(l)
                if m:
                    _adiciona(out, papel_atual, m.group(1), l)
                    continue
                papel_atual = None
            else:
                _adiciona(out, papel_atual, l, l)
                papel_atual = None
    return out


def _adiciona(out: list[Personagem], papel: str, nome: str, linha: str) -> None:
    if papel in PAPEIS_ATIVO:
        polo = "ativo"
    elif papel in PAPEIS_PASSIVO:
        polo = "passivo"
    elif papel in PAPEIS_ADV:
        polo = "advogado"
        m = _RE_ADV.match(nome.strip())
        if m:
            nome = m.group(1)
    else:
        polo = "outro"
    out.append(Personagem(papel=papel, polo=polo, nome=espaco(nome), linha=espaco(linha)))


def _extrai_movimentos(linhas: list[str]) -> list[Movimento]:
    blocos: list[list[str]] = []
    atual: list[str] | None = None
    for l in linhas:
        if l.strip().lower().startswith("tipo do movimento:"):
            atual = [l.rstrip()]
            blocos.append(atual)
        elif atual is not None:
            if l.strip().lower().startswith(("libras", "voz", "+ acessibilidade")):
                atual = None
                continue
            atual.append(l.rstrip())
    movs: list[Movimento] = []
    for i, b in enumerate(blocos):
        tipo = espaco(b[0].split(":", 1)[1])
        texto = "\n".join(b).strip()
        m = _RE_DATA.search("\n".join(b[1:]))
        movs.append(Movimento(indice=i, tipo=tipo, data=m.group(1) if m else None, texto=texto))
    return movs


def ler(texto_bruto: str) -> Processo:
    linhas = texto_bruto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    meta: dict[str, str] = {}
    corpo: list[str] = []
    docs: list[Documento] = []
    i = 0
    while i < len(linhas):
        l = linhas[i]
        m = _RE_META.match(l.strip())
        if m:
            meta[m.group(1).lower()] = m.group(2).strip()
            i += 1
            continue
        mi = _RE_INTEGRA.match(l.strip())
        if mi:
            rotulo = mi.group(1)
            bloco: list[str] = []
            i += 1
            while i < len(linhas) and linhas[i].strip() != "=== FIM ===":
                bloco.append(linhas[i])
                i += 1
            i += 1
            docs.append(Documento(rotulo=rotulo, texto="\n".join(bloco).strip()))
            continue
        corpo.append(l)
        i += 1

    texto = "\n".join(corpo)
    mc = re.search(r"Processo\s+N[ºo°]?\s*(" + PADRAO_CNJ.pattern + r")", texto)
    cnj = tratar(mc.group(1)) if mc else None
    if cnj is None:
        m2 = PADRAO_CNJ.search(texto)
        cnj = tratar(m2.group(0)) if m2 else tratar(meta.get("cnj"))

    # capa: rótulo numa linha, valor na linha seguinte
    capa: dict[str, str] = {}
    nz = _linhas_nao_vazias(corpo)
    for k, (_, l) in enumerate(nz[:-1]):
        chave = ROTULOS_CAPA.get(norm(l))
        if chave and chave not in capa:
            capa[chave] = nz[k + 1][1]

    dist = None
    md = re.search(r"Distribu[ií]do em (\d{2}/\d{2}/\d{4})", texto)
    if md:
        dist = md.group(1)

    return Processo(
        cnj=cnj,
        meta=meta,
        capa=capa,
        distribuicao=dist,
        personagens=_extrai_personagens(corpo),
        movimentos=_extrai_movimentos(corpo),
        documentos=docs,
        texto=texto,
    )
