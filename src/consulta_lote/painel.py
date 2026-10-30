"""Dados e painel HTML de análise. Os mesmos dados alimentam a planilha de saída (saida.py).

Fontes, em ordem de confiança: análise do texto colado e dos documentos (banco local), marcos do
DataJud (levantamento) e base do cliente (planilha de entrada). O painel é um arquivo único, sem
biblioteca externa, para abrir offline: os dados são privados e não saem da máquina.
"""
from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .campos import NV, compara_fase, mascara_cpf
from .cnj import hash_do_processo, tratar
from .config import proteger_escrita
from .levantamento import linha as linha_datajud
from .lista import categoria_fase

PERGUNTAS = [
    ("partes", "A parte-alvo integra o polo passivo da ação?", "parte_alvo_no_polo_passivo"),
    ("fase", "Qual a fase processual atual?", "fase"),
    ("pericia", "Houve perícia? O laudo foi favorável ou desfavorável?", "pericia"),
    ("acordo", "Existe acordo nos autos?", "acordo"),
    ("desistencia", "Há petição de renúncia ou pedido de desistência?", "desistencia_ou_renuncia"),
    ("decisao", "Já houve sentença ou acórdão? Foi favorável ou desfavorável à parte-alvo?", "decisao"),
    ("transito", "Houve trânsito em julgado? Em que data?", "transito_em_julgado"),
]
CAMPOS_DB = [c for _, _, c in PERGUNTAS] + ["pericia_laudo_juizo", "decisao_juizo", "parte_alvo_citada"]

# filtros do painel: (chave da linha, rótulo). Ordem = ordem na tela.
FILTROS = [
    ("analise", "Situação da análise"), ("sistema", "Sistema do tribunal"), ("fase_tribunal", "Fase no tribunal"),
    ("base_x_tribunal", "Fase: base do cliente x tribunal"), ("fase_base_cat", "Fase na base do cliente"),
    ("resultado", "Resultado da decisão (critério do cliente)"), ("sentenca", "Sentença ou acórdão"),
    ("transito", "Trânsito em julgado"), ("pericia", "Perícia"), ("acordo", "Acordo"),
    ("desistencia", "Desistência ou renúncia"), ("parte_alvo", "Parte-alvo no polo passivo"),
    ("proximo_cat", "Próximo passo"), ("revisao", "Revisão humana"), ("acesso", "Acesso dos documentos"),
    ("tipo_pasta", "Tipo da pasta"), ("rito", "Rito"), ("tipo_acao", "Tipo de ação"), ("comarca", "Comarca"),
    ("ano", "Ano do processo"), ("faixa_valor", "Valor da causa"), ("atividade", "Atividade atual (base)"),
    ("motivo_acao", "Motivo da ação (base)"),
]
GRAFICOS = [("sistema", "Sistema"), ("fase_tribunal", "Fase no tribunal"), ("resultado", "Resultado da decisão"),
            ("base_x_tribunal", "Base x tribunal"), ("proximo_cat", "Próximo passo")]


def _faixa(v: float | None) -> str:
    if v is None:
        return "sem valor"
    if v <= 20000:
        return "até 20 mil"
    if v <= 50000:
        return "20 a 50 mil"
    if v <= 100000:
        return "50 a 100 mil"
    return "acima de 100 mil"


def _num(s: str) -> float | None:
    try:
        return float(str(s).replace(",", "."))
    except ValueError:
        return None


def _ler_csv(arq: Path) -> list[dict]:
    if not arq.exists():
        return []
    with open(arq, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter=";"))


def _categoria_proximo(texto: str, analisado: bool, pendente: bool) -> str:
    t = texto.lower()
    if analisado and pendente:
        return "revisar a análise (juízo humano pendente)"
    if "não achado" in t:
        return "não achado no DataJud: procurar no tribunal"
    if "encerrado" in t or "baixado" in t or "trânsito" in t:
        return "encerrado: conferir trânsito e baixa"
    if "sentenciado" in t or "sentença" in t:
        return "ler a sentença"
    if "acordo" in t or "desistência" in t or "perícia" in t:
        return "ler documento (acordo, desistência ou perícia)"
    return "ler os eventos no tribunal"


def _faz_linha(el: dict, dj: dict | None, campos: dict | None, sistema_db: str | None, fase_base_db: str | None) -> dict:
    numero = el["numero"]
    c = tratar(numero)
    analisado = campos is not None
    r = {k: "" for k in ("tipo_pasta", "rito", "tipo_vara", "tipo_acao", "comarca", "foro", "vara", "atividade", "motivo_acao")}
    r.update(numero=numero, ano=c.ano, tipo_pasta=el.get("tipo_pasta", ""), rito=el.get("rito", ""),
             tipo_vara=el.get("tipo_vara", ""), tipo_acao=el.get("tipo_acao", ""), comarca=el.get("comarca", ""),
             foro=el.get("foro", ""), vara=el.get("vara", ""), atividade=el.get("atividade_atual", ""),
             motivo_acao=el.get("motivo_acao", ""), distribuicao=(el.get("data_distribuicao") or "")[:10])
    valor = _num(el.get("valor_causa", ""))
    r["valor_causa"] = valor
    r["faixa_valor"] = _faixa(valor)
    fase_base = el.get("fase_base") or fase_base_db or ""
    r["fase_base"] = fase_base
    r["fase_base_cat"] = categoria_fase(fase_base) if fase_base else "sem fase"
    d = dj or {}
    r["datajud"] = {k: d.get(k, "") for k in ("sistema_datajud", "orgao", "atualizado", "movimentos", "migrado_em",
                                              "sentenca_em", "transito_em", "baixa_em", "acordo_em",
                                              "desistencia_em", "pericia_em", "ultimo_movimento")}
    r["orgao"] = d.get("orgao", "")
    r["analise"] = "análise completa" if analisado else ("só DataJud" if d.get("encontrado") == "sim" else
                                                          ("não achado no DataJud" if dj else "não consultado"))
    r["sistema"] = (sistema_db if analisado and sistema_db and sistema_db != "nao_informado" else d.get("sistema_provavel")) or "desconhecido"
    r["campos"] = {}
    estado = lambda k: (campos or {}).get(k, {}).get("estado")
    valorc = lambda k: (campos or {}).get(k, {}).get("valor", "")
    if analisado:
        r["campos"] = campos
        fase_c = campos.get("fase", {})
        r["fase_tribunal"] = fase_c.get("valor") if fase_c.get("estado") == "SIM" else "não classificada"
        from .campos import Campo
        r["base_x_tribunal"] = compara_fase(fase_base, Campo(campo="fase", estado=fase_c.get("estado", NV), valor=fase_c.get("valor", "")))
        pa = estado("parte_alvo_no_polo_passivo")
        r["parte_alvo"] = {"SIM": "sim", "NAO": "não"}.get(pa, "não visível")
        r["sentenca"] = {"SIM": "sim", "NAO": "não"}.get(estado("decisao"), "não visível")
        dj_valor = valorc("decisao_juizo")
        r["resultado"] = ("favorável (sugestão)" if dj_valor.startswith("FAVOR") else
                          "desfavorável (sugestão)" if dj_valor.startswith("DESFAVOR") else
                          "sem decisão registrada" if r["sentenca"] != "sim" else "a classificar")
        r["data_sentenca"] = campos.get("decisao", {}).get("data", "")
        r["transito"] = {"SIM": "sim", "NAO": "não"}.get(estado("transito_em_julgado"), "não visível")
        r["data_transito"] = valorc("transito_em_julgado") if estado("transito_em_julgado") == "SIM" else ""
        for chave, campo in (("pericia", "pericia"), ("acordo", "acordo"), ("desistencia", "desistencia_ou_renuncia")):
            r[chave] = {"SIM": "sim", "NAO": "não"}.get(estado(campo), "não visível")
        rev = {c.get("revisao", "pendente") for c in campos.values()}
        r["revisao"] = "conferido" if rev == {"conferido"} else ("pendente" if "pendente" in rev else "corrigido")
        r["acesso"] = sorted({c.get("acesso") for c in campos.values() if c.get("acesso") and c.get("estado") != NV}) or ["sem documento"]
        pend = r["resultado"] in ("favorável (sugestão)", "desfavorável (sugestão)", "a classificar")
    else:
        r.update(parte_alvo="-", sentenca="-", transito="-", pericia="-", acordo="-", desistencia="-", data_sentenca="",
                 data_transito="", revisao="-", acesso=["sem documento"], base_x_tribunal="indeterminado")
        if dj and dj.get("encontrado") == "sim":
            r["sentenca"] = "sim (DataJud)" if d.get("sentenca_em") else "não registrada (DataJud)"
            r["transito"] = "sim (DataJud)" if d.get("transito_em") else "não registrado (DataJud)"
            r["fase_tribunal"] = ("baixado ou arquivado" if d.get("baixa_em") else "sentenciado" if d.get("sentenca_em") else "sem marco (DataJud)")
            r["resultado"] = "sem decisão registrada" if not d.get("sentenca_em") else "a classificar"
            r["data_sentenca"], r["data_transito"] = d.get("sentenca_em", ""), d.get("transito_em", "")
        else:
            r["fase_tribunal"], r["resultado"] = "-", "-"
        pend = False
    r["proximo_passo"] = d.get("proximo_passo") or ("ler os eventos no tribunal" if analisado else "consultar o DataJud e o tribunal")
    r["proximo_cat"] = _categoria_proximo(r["proximo_passo"], analisado, pend) if (dj or analisado) else "ainda não consultado"
    return r


def montar_dados(d: Path) -> dict:
    """Une base do cliente (elegiveis.csv), levantamento do DataJud (cache) e análises (banco local)."""
    from .db import segredo_local

    seg = segredo_local(d)
    elegiveis = _ler_csv(d / "saida" / "elegiveis.csv")
    con = sqlite3.connect(d / "base.sqlite") if (d / "base.sqlite").exists() else None
    por_hash: dict[str, dict] = {}
    sistema_por_hash: dict[str, tuple] = {}
    if con:
        for h, sis, fb in con.execute("SELECT hash, sistema, fase_base FROM processo"):
            sistema_por_hash[h] = (sis, fb)
        for h, campo, est, val, mot, ev, loc, ac, dat, rev, conf in con.execute(
            "SELECT hash,campo,estado,valor,motivo_nao_visivel,evidencia_literal,localizacao,acesso_documento,"
            "data_da_fonte,revisao_humana,confianca FROM campo WHERE fonte IS NULL OR fonte!='DataJud'"
        ):
            if campo in CAMPOS_DB:
                por_hash.setdefault(h, {})[campo] = dict(estado=est, valor=val or "", motivo=mot or "", evidencia=ev or "",
                                                         localizacao=loc or "", acesso=ac or "", data=dat or "",
                                                         revisao=rev or "pendente", confianca=conf or "")
    linhas = []
    for el in elegiveis:
        c = tratar(el["numero"])
        h = hash_do_processo(c, seg)
        arq = d / "datajud" / f"{h}.json"
        dj = linha_datajud(c, json.loads(arq.read_text(encoding="utf-8"))) if arq.exists() else None
        sis, fb = sistema_por_hash.get(h, (None, None))
        campos = por_hash.get(h) if h in por_hash and sis and sis != "nao_informado" else None
        linhas.append(_faz_linha(el, dj, campos, sis, fb))
    if con:
        con.close()
    return {"gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"), "processos": linhas,
            "filtros": [{"chave": k, "rotulo": r} for k, r in FILTROS],
            "graficos": [{"chave": k, "rotulo": r} for k, r in GRAFICOS],
            "perguntas": [{"id": i, "texto": t, "campo": c} for i, t, c in PERGUNTAS]}


def _limpa(obj):
    """CPF mascarado em qualquer texto que vá para a saída."""
    if isinstance(obj, str):
        return mascara_cpf(obj)
    if isinstance(obj, list):
        return [_limpa(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _limpa(v) for k, v in obj.items()}
    return obj


def renderizar_html(dados: dict) -> str:
    modelo = (Path(__file__).parent / "templates" / "painel.html.tpl").read_text(encoding="utf-8")
    # "<" vira \u003c: o texto do processo nunca abre nem fecha tag dentro do bloco de dados
    corpo = json.dumps(_limpa(dados), ensure_ascii=False).replace("<", chr(92) + "u003c")
    return modelo.replace("/*__DADOS__*/", corpo)


def gerar_html(dados: dict, destino: Path) -> Path:
    destino = proteger_escrita(destino)
    destino.write_text(renderizar_html(dados), encoding="utf-8", newline="\n")
    return destino
