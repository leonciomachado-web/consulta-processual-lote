"""Levantamento geral pelo DataJud: uma linha por processo, para decidir onde olhar a fundo.

Lê só o cache local das respostas do DataJud (sem rede). O DataJud mostra que o tribunal registrou um
movimento, não o conteúdo: serve para triagem, não para afirmar o resultado de nenhum campo.
"""
from __future__ import annotations

import csv
from pathlib import Path

from .cnj import Cnj
from .datajud import CODIGOS

COLUNAS = [
    "numero", "encontrado", "sistema_datajud", "sistema_provavel", "grau", "instancias", "orgao", "classe", "distribuicao",
    "atualizado", "movimentos", "migrado_em", "sentenca_em", "transito_em", "baixa_em", "acordo_em",
    "desistencia_em", "pericia_em", "ultimo_movimento", "proximo_passo",
]
_GRUPOS = {
    "sentenca": {193, 219, 220},
    "transito": {848},
    "baixa": {22},
    "acordo": {466, 15238, 14099},
    "desistencia": {463, 12467, 944},
    "pericia": {14901, 14902},
    "migrado": {15417},
}


def _data(valor: str | None) -> str:
    v = (valor or "")[:10]
    return f"{v[8:10]}/{v[5:7]}/{v[0:4]}" if len(v) == 10 and v[4] == "-" else v


def _fonte(resposta: dict) -> dict | None:
    hits = resposta.get("hits", {}).get("hits", [])
    return hits[0]["_source"] if hits else None


def linha(cnj: Cnj, resposta: dict | None) -> dict:
    base = {c: "" for c in COLUNAS}
    base["numero"] = cnj.formatado
    src = _fonte(resposta) if resposta else None
    if src is None:
        base.update(encontrado="nao", sistema_provavel="desconhecido",
                    proximo_passo="não achado no DataJud: procurar no eproc, no PJe e no portal do tribunal")
        return base
    fontes = [h["_source"] for h in resposta.get("hits", {}).get("hits", []) if h.get("_source")]
    movs = [m for s in fontes for m in s.get("movimentos", [])]  # todas as instâncias juntas
    datas: dict[str, list[str]] = {g: [] for g in _GRUPOS}
    for m in movs:
        for g, codigos in _GRUPOS.items():
            if m.get("codigo") in codigos:
                datas[g].append(m.get("dataHora", ""))
    ultimo = max(movs, key=lambda m: m.get("dataHora", ""), default=None)
    sistema = (src.get("sistema") or {}).get("nome") or ""
    migrado = bool(datas["migrado"])
    provavel = "eproc" if migrado else ("pje" if sistema == "PJe" else ("legado" if sistema == "Projudi" else "desconhecido"))
    base.update(
        encontrado="sim", sistema_datajud=sistema, sistema_provavel=provavel, grau=src.get("grau", ""),
        instancias="+".join(s.get("grau", "") for s in fontes),
        orgao=(src.get("orgaoJulgador") or {}).get("nome", ""), classe=(src.get("classe") or {}).get("nome", ""),
        distribuicao=_data(f"{(src.get('dataAjuizamento') or '')[:4]}-{(src.get('dataAjuizamento') or '')[4:6]}-{(src.get('dataAjuizamento') or '')[6:8]}"),
        atualizado=_data(src.get("dataHoraUltimaAtualizacao")), movimentos=len(movs),
        migrado_em=_data(max(datas["migrado"])) if migrado else "",
        sentenca_em=_data(max(datas["sentenca"])) if datas["sentenca"] else "",
        transito_em=_data(max(datas["transito"])) if datas["transito"] else "",
        baixa_em=_data(max(datas["baixa"])) if datas["baixa"] else "",
        acordo_em=_data(max(datas["acordo"])) if datas["acordo"] else "",
        desistencia_em=_data(max(datas["desistencia"])) if datas["desistencia"] else "",
        pericia_em=_data(max(datas["pericia"])) if datas["pericia"] else "",
        ultimo_movimento=f"{_data(ultimo.get('dataHora'))} {ultimo.get('nome') or 'código ' + str(ultimo.get('codigo'))}" if ultimo else "",
    )
    base["proximo_passo"] = _proximo_passo(base)
    return base


def _proximo_passo(l: dict) -> str:
    onde = {"eproc": "eproc", "pje": "PJe", "legado": "portal do legado", "desconhecido": "tribunal"}[l["sistema_provavel"]]
    if "G2" in l["instancias"].split("+"):
        return f"há registro no 2º grau (recurso): ver o acórdão e o trânsito no {onde}"
    if l["baixa_em"] and l["transito_em"]:
        return f"encerrado (trânsito e baixa registrados): conferir a data do trânsito na certidão, no {onde}"
    if l["baixa_em"]:
        return f"baixado: ver no {onde} se houve trânsito e qual decisão"
    if l["sentenca_em"] and l["transito_em"]:
        return f"sentença e trânsito registrados: conferir a data pela certidão, no {onde}"
    if l["sentenca_em"]:
        return f"sentenciado sem trânsito: ler a sentença no {onde} (critério favorável ou desfavorável)"
    if l["acordo_em"] or l["desistencia_em"]:
        return f"acordo ou desistência registrados: ler o documento no {onde}"
    if l["pericia_em"]:
        return f"perícia registrada: ver laudo no {onde}"
    return f"sem marco de decisão no DataJud: ler os eventos no {onde}"


def gerar(entradas: list[tuple[Cnj, dict | None]], destino: Path) -> tuple[Path, list[dict]]:
    from .lista import gravar_csv

    linhas = [linha(c, r) for c, r in sorted(entradas, key=lambda x: x[0].formatado)]
    arq = gravar_csv(destino, COLUNAS, [[l[c] for c in COLUNAS] for l in linhas])
    return arq, linhas
