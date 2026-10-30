"""Análise por blocos retomáveis, uma pasta por processo.

Adaptação do método de blocos usado na análise de editais e das camadas de fidelidade usadas
nas análises de processos já feitas:
- cada bloco é um arquivo; a parte automática (regras, evidência literal) fica entre marcadores
  e pode ser regenerada sem apagar o que a pessoa escreveu fora dos marcadores;
- antes de substituir a parte automática, a versão atual vai para versoes/;
- três camadas em todo bloco: (a) literal, (b) paráfrase, (c) análise. Só (a) é gerado por regra;
- o que a busca não confirma vira [CONFERIR NA FONTE: ...], nunca suposição;
- só a pessoa que revisa marca um bloco como concluído.
"""
from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from .campos import NV, Campo, compara_fase, mascara_cpf
from .config import proteger_escrita
from .parser import Processo
from .textos import espaco, norm

INICIO = "<!-- auto:inicio -->"
FIM = "<!-- auto:fim -->"
AVISO = "Esta minuta requer revisão por profissional habilitado antes de qualquer uso externo."

CAMADAS = (
    "> Camadas: **(a) Literal** = trecho entre aspas com referência, conferido no texto bruto; "
    "**(b) Paráfrase** = resumo em palavras próprias, sem aspas; **(c) Análise** = leitura própria, "
    "nunca atribuída à fonte. `[CONFERIR NA FONTE: ...]` = dado que o material não permite confirmar."
)

BLOCOS = [
    ("00-identificacao", "Identificação e fontes lidas"),
    ("01-fluxo-temporal", "Fluxo temporal"),
    ("02-partes", "Partes"),
    ("03-pericia", "Perícia"),
    ("04-acordo-e-desistencia", "Acordo, desistência e renúncia"),
    ("05-decisoes", "Decisões (sentença e acórdão)"),
    ("06-transito-e-fase", "Trânsito em julgado e fase atual"),
    ("07-armadilhas", "Armadilhas de leitura"),
    ("08-chance-de-perda", "Chance de perda (só se for pedido)"),
    ("resumo", "Resumo"),
]


def _ev(c: Campo) -> str:
    base = f"- **{c.campo}**: {c.estado}"
    if c.estado == NV and c.motivo:
        base += f" ({c.motivo})"
    if c.valor:
        base += f". {c.valor}"
    if c.evidencia:
        base += f'\n  - (a) Literal: "{c.evidencia}" [{c.localizacao or c.fonte}; acesso: {c.acesso_documento}]'
    if c.estado == NV:
        base += f"\n  - [CONFERIR NA FONTE: {c.campo} ({c.motivo or 'sem motivo registrado'})]"
    return base


def _campos(cs: list[Campo], *nomes: str) -> str:
    sel = [c for c in cs if c.campo in nomes]
    return "\n".join(_ev(c) for c in sel) or "- (nenhum campo extraído)"


def _cronologia(p: Processo) -> str:
    if not p.movimentos:
        return "- [CONFERIR NA FONTE: nenhum movimento foi colado]"
    linhas = []
    for mv in p.movimentos:
        corpo = " / ".join(espaco(x) for x in mv.texto.split("\n") if x.strip())
        linhas.append(f"- {mv.data or 's/ data'} | (a) Literal: \"{corpo}\"")
    return "\n".join(linhas)


def _identificacao(p: Processo, cs: list[Campo]) -> str:
    sigilo = None
    for d in p.documentos:
        m = re.search(r"N[ií]vel de Sigilo:\s*([^\n]+)", d.texto)
        if m:
            sigilo = espaco(m.group(1))
            break
    docs = "\n".join(f"  - {d.rotulo} (acesso: {d.acesso})" for d in p.documentos) or "  - nenhum"
    return "\n".join([
        f"- Processo: {p.cnj.formatado if p.cnj else '[CONFERIR NA FONTE: número]'}",
        f"- Sistema: {p.sistema}",
        f"- Consulta feita em: {p.meta.get('data_consulta', '[CONFERIR NA FONTE: data da consulta]')}",
        f"- Fase registrada na base do cliente: {p.meta.get('fase_base', '[não informada]')}",
        f"- Histórico completo colado: {'sim' if p.movimentos_lista_completa else 'não ou não informado'}"
        f" ({len(p.movimentos)} entradas)",
        f"- Nível de sigilo lido nos documentos: {sigilo or '[CONFERIR NA FONTE: não consta nos documentos lidos]'}",
        "- Documentos lidos (acesso por documento, não por processo):",
        docs,
    ])


def _armadilhas(p: Processo, cs: list[Campo]) -> str:
    por = {c.campo: c for c in cs}
    achados = []
    tr = por.get("transito_em_julgado")
    if tr and "histórico registra" in tr.valor:
        achados.append("A1: a data do trânsito pela certidão difere da data do movimento. " + tr.valor)
    if any("projeto de sentenca" in norm(m.texto) for m in p.movimentos):
        achados.append("A2: há projeto de sentença (minuta de juiz leigo). Só a sentença homologada decide.")
    if not p.movimentos_lista_completa:
        achados.append("A3: o histórico colado é parcial. Ausência de movimento não prova que o fato não ocorreu.")
    cit, polo = por.get("parte_alvo_citada"), por.get("parte_alvo_no_polo_passivo")
    if cit and polo and cit.estado == "SIM" and polo.estado == NV:
        achados.append("A5: a parte-alvo aparece no texto, mas o polo não foi lido. Abrir a aba de partes ou o cabeçalho da sentença.")
    detectadas = "\n".join(f"- DETECTADA {a}" for a in achados) or "- Nenhuma armadilha detectada por regra."
    lista = """
| # | Armadilha de leitura | Como detectar | A quem se aplica |
|---|---|---|---|
| A1 | Data do movimento no histórico difere da data do fato no documento (trânsito, publicação) | comparar certidão, ata e movimento | todo marco com prazo |
| A2 | Projeto de sentença lido como sentença | tipo do documento "Projeto de Sentença" x "Sentença" | juizados |
| A3 | Histórico parcial lido como completo | contar páginas de movimentos; flag `movimentos_lista_completa` | todo processo |
| A4 | "Localização na serventia" lida como fase | comparar com último marco real | sistema legado |
| A5 | Polo não informado: parte citada sem dizer se é ré | campo `parte_alvo_citada` x polo | polo desconhecido |
| A6 | Rótulo do tribunal ou da parte na base do cliente diverge do número do processo | alerta da limpeza; conferir comarca e UF | base do cliente |
| A7 | Documento restrito lido como público (ou o contrário) | `acesso_documento` de cada fonte | todo documento |
| A8 | Nome da parte com variação (razão social diferente entre capa e despachos) | comparar capa, cabeçalho e despachos | partes pessoa jurídica |
"""
    return detectadas + "\n\n" + lista.strip()


def _resumo(p: Processo, cs: list[Campo]) -> str:
    linhas = ["| Item | Estado | Valor | Evidência (literal) |", "|---|---|---|---|"]
    itens = [("Partes (parte-alvo no polo passivo)", "parte_alvo_no_polo_passivo"), ("Fase", "fase"),
             ("Perícia", "pericia"), ("Acordo", "acordo"), ("Desistência ou renúncia", "desistencia_ou_renuncia"),
             ("Sentença ou acórdão", "decisao"), ("Trânsito em julgado", "transito_em_julgado")]
    por = {c.campo: c for c in cs}
    for nome, chave in itens:
        c = por.get(chave)
        if c is None:
            continue
        ev = (c.evidencia or "").replace("|", "/")[:160]
        linhas.append(f"| {nome} | {c.estado} | {(c.valor or c.motivo).replace('|', '/')} | {ev and chr(34) + ev + chr(34)} |")
    fase_c = por.get("fase")
    cmp_ = compara_fase(p.meta.get("fase_base"), fase_c) if fase_c else "indeterminado"
    linhas.append("")
    rotulo = {"coincide": "coincide", "base_defasada": "base defasada: o tribunal está em etapa posterior",
              "base_adiantada": "base adiantada: o tribunal está em etapa anterior", "indeterminado": "indeterminado"}[cmp_]
    linhas.append(f"- Fase na base do cliente x fase no tribunal: **{rotulo}** (reportado, não corrigido).")
    linhas.append("- Juízos humanos pendentes: laudo (favorável ou desfavorável) e decisão (favorável ou desfavorável).")
    return "\n".join(linhas)


def _auto(nome: str, p: Processo, cs: list[Campo]) -> str:
    if nome == "00-identificacao":
        return _identificacao(p, cs)
    if nome == "01-fluxo-temporal":
        return "(a) Literal, do mais recente para o mais antigo:\n" + _cronologia(p)
    if nome == "02-partes":
        return _campos(cs, "parte_alvo_no_polo_passivo", "parte_alvo_citada")
    if nome == "03-pericia":
        return _campos(cs, "pericia", "pericia_laudo_juizo")
    if nome == "04-acordo-e-desistencia":
        return _campos(cs, "acordo", "desistencia_ou_renuncia")
    if nome == "05-decisoes":
        return _campos(cs, "decisao", "decisao_juizo")
    if nome == "06-transito-e-fase":
        return _campos(cs, "transito_em_julgado", "fase")
    if nome == "07-armadilhas":
        return _armadilhas(p, cs)
    if nome == "08-chance-de-perda":
        return ("Só preencher se o Luís pedir. Rótulo obrigatório em material de seguro: \"chance de perda\" "
                "(provável, possível ou remota). É opinião do escritório, não fato nem decisão judicial.")
    return _resumo(p, cs)


def _manual(nome: str) -> str:
    if nome in ("07-armadilhas", "resumo"):
        return ""
    return ("\n## (b) Paráfrase\n[PREENCHER: resumo em palavras próprias, sem aspas]\n"
            "\n## (c) Análise\n[PREENCHER: leitura própria; não atribuir à fonte]\n")


def _montar(nome: str, titulo: str, auto: str, existente: str | None) -> str:
    auto = mascara_cpf(auto.replace("<!--", "&lt;!--"))  # texto do processo não forja marcadores nem leva CPF
    bloco_auto = f"{INICIO}\n{auto}\n{FIM}"
    if existente and (INICIO in existente or FIM in existente):
        if existente.count(INICIO) != 1 or existente.count(FIM) != 1 or existente.index(INICIO) > existente.index(FIM):
            raise ValueError(f"{nome}: marcadores auto:inicio e auto:fim duplicados ou fora de ordem; "
                             "corrija o arquivo antes de regenerar")
        antes = existente.split(INICIO)[0]
        depois = existente.split(FIM, 1)[1]
        return antes + bloco_auto + depois
    return (f"# {titulo}\n\n{CAMADAS}\n\n> Status: **rascunho**. Só a pessoa que revisa marca como concluído.\n\n"
            f"## (a) Literal e regras\n{bloco_auto}\n{_manual(nome)}\n> {AVISO}\n")


def gerar(proc: Processo, campos: list[Campo], pasta: Path) -> list[Path]:
    """Cria ou atualiza os blocos. Só a parte entre os marcadores é reescrita, com cópia em versoes/."""
    pasta = proteger_escrita(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    versoes = pasta / "versoes"
    escritos: list[Path] = []
    for nome, titulo in BLOCOS:
        arq = pasta / f"{nome}.md"
        existente = arq.read_text(encoding="utf-8") if arq.exists() else None
        novo = _montar(nome, titulo, _auto(nome, proc, campos), existente)
        if existente is not None and novo != existente:
            versoes.mkdir(exist_ok=True)
            carimbo = datetime.now().strftime("%Y-%m-%d-%H%M%S")
            shutil.copy2(arq, versoes / f"{nome}_{carimbo}.md")
        if existente != novo:
            arq.write_text(novo, encoding="utf-8", newline="\n")
        escritos.append(arq)
    estado = pasta / "_HANDOFF.md"
    if not estado.exists():
        linhas = ["# _HANDOFF: análise por blocos", "", "Status de cada bloco (só a revisora marca concluído):", ""]
        linhas += [f"- [ ] {n}: rascunho" for n, _ in BLOCOS]
        estado.write_text("\n".join(linhas) + "\n", encoding="utf-8", newline="\n")
    return escritos
