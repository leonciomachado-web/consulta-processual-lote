"""Segundo olhar: movimentos do DataJud (API pública do CNJ), por código da tabela unificada.

Só metadados e movimentos, sem nome de parte. O usuário informa o alias do índice e a chave
pública (arquivo local, nunca no repositório). Ritmo máximo de 1 consulta por segundo, bem
abaixo do limite de 120 por minuto dos termos de uso da API.
O DataJud mostra que o tribunal registrou um movimento, não o conteúdo.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from .campos import NV, SIM, Campo
from .cnj import Cnj
from .config import proteger_escrita

URL = "https://api-publica.datajud.cnj.jus.br/api_publica_{alias}/_search"
INTERVALO_S = 1.2

# código da tabela processual unificada -> (campo, rótulo)
CODIGOS = {
    848: ("transito_em_julgado_datajud", "Trânsito em julgado"),
    22: ("baixa_datajud", "Baixa Definitiva"),
    193: ("decisao_datajud", "Julgamento"),
    219: ("decisao_datajud", "Procedência"),
    220: ("decisao_datajud", "Improcedência"),
    466: ("acordo_datajud", "Homologação de Transação"),
    15238: ("acordo_datajud", "Homologação de Acordo ou Transação"),
    14099: ("acordo_datajud", "Homologação de Acordo em Execução ou Cumprimento de Sentença"),
    463: ("desistencia_datajud", "Desistência"),
    12467: ("desistencia_datajud", "Desistência de pedido"),
    944: ("desistencia_datajud", "Desistência de Recurso"),
    14901: ("pericia_datajud", "Perícia"),
    14902: ("pericia_datajud", "Perícia"),
    15417: ("migracao_datajud", "Migração de Sistema Eletrônico"),
}
CAMPOS_DATAJUD = sorted({v[0] for v in CODIGOS.values()})


def consultar(cnj: Cnj, chave: str, alias: str, timeout: int = 60) -> dict:
    corpo = json.dumps({"query": {"match": {"numeroProcesso": cnj.digitos}}}).encode()
    req = urllib.request.Request(
        URL.format(alias=alias), data=corpo, method="POST",
        headers={"Authorization": f"APIKey {chave}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def consultar_e_guardar(cnj: Cnj, chave: str, alias: str, pasta: Path, h: str) -> dict:
    arq = proteger_escrita(pasta / f"{h}.json")
    if arq.exists():  # cache: não repete consulta
        return json.loads(arq.read_text(encoding="utf-8"))
    dados = None
    for espera in (30, 90, 180, None):  # limite do servidor (429): espera e tenta de novo, depois para
        try:
            dados = consultar(cnj, chave, alias)
            break
        except urllib.error.HTTPError as e:
            if e.code != 429 or espera is None:
                raise
            time.sleep(espera)
    arq.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    time.sleep(INTERVALO_S)
    return dados


def _fonte(resposta: dict) -> dict | None:
    hits = resposta.get("hits", {}).get("hits", [])
    return hits[0]["_source"] if hits else None


def resumo(resposta: dict) -> dict:
    src = _fonte(resposta)
    if src is None:
        return {"encontrado": False}
    return {
        "encontrado": True,
        "classe": src.get("classe", {}).get("nome"),
        "orgao": src.get("orgaoJulgador", {}).get("nome"),
        "distribuicao": (src.get("dataAjuizamento") or "")[:8],
        "atualizado": src.get("dataHoraUltimaAtualizacao"),
        "sistema_no_datajud": src.get("sistema", {}).get("nome"),
        "movimentos": len(src.get("movimentos", [])),
    }


def campos_do_datajud(resposta: dict) -> list[Campo]:
    """Um campo por tipo de sinal. Evidência: o registro do movimento (nome, código, data)."""
    src = _fonte(resposta)
    if src is None:
        return [Campo(campo=c, estado=NV, motivo="nao_consultado", fonte="DataJud") for c in CAMPOS_DATAJUD]
    achados: dict[str, list[str]] = {}
    for m in src.get("movimentos", []):
        cod = m.get("codigo")
        if cod in CODIGOS:
            campo, rotulo = CODIGOS[cod]
            nome = m.get("nome") or rotulo
            achados.setdefault(campo, []).append(f"movimento {cod} {nome} em {(m.get('dataHora') or '')[:10]}")
    consulta = (src.get("dataHoraUltimaAtualizacao") or "")[:10]
    out: list[Campo] = []
    for campo in CAMPOS_DATAJUD:
        if campo in achados:
            ev = "; ".join(sorted(set(achados[campo])))
            out.append(Campo(campo=campo, estado=SIM, valor=f"{len(achados[campo])} registro(s)", fonte="DataJud",
                             acesso_documento="publico", data_da_fonte=consulta, evidencia=ev,
                             localizacao="movimentos do DataJud", confianca="regra"))
        else:
            out.append(Campo(campo=campo, estado=NV, motivo="sem_mencao_em_movimento", fonte="DataJud",
                             valor="código não registrado (o tribunal pode usar código genérico)"))
    return out
