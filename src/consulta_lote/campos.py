"""Extração dos sete itens por regra, sempre com estado e evidência literal.

Estados:
  SIM                              texto positivo encontrado
  NAO                              só com texto positivo que afirme o negativo, ou com
                                   lista completa lida (ver cada regra)
  NAO_VISIVEL_NO_ACESSO_PUBLICO    todo o resto. Ausência nunca vira "não houve".

Regra sem exceção: sem trecho literal de evidência, o estado é NAO_VISIVEL.
Juízos (laudo favorável, decisão favorável) nunca saem por regra: ficam para
revisão humana.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone

from .parser import Movimento, Personagem, Processo
from .textos import espaco, norm

SIM = "SIM"
NAO = "NAO"
NV = "NAO_VISIVEL_NO_ACESSO_PUBLICO"

MOTIVOS = (
    "sigilo",
    "documento_restrito",
    "sistema_nao_liberado",
    "captcha_ou_bloqueio",
    "nao_consultado",
    "sem_mencao_em_movimento",
    "lista_parcial",
    "juizo_humano",
    "evidencia_nao_confere",
    "conflito_entre_fontes",
)


@dataclass
class Campo:
    campo: str
    estado: str
    valor: str = ""
    motivo: str = ""
    fonte: str = ""
    documento_origem: str = ""
    acesso_documento: str = "nao_testado"
    data_da_fonte: str = ""
    evidencia: str = ""
    localizacao: str = ""
    confianca: str = "regra"
    revisao: str = "pendente"
    evidencia_confere: bool = True


# ---- padrões (sobre texto sem acento e em minúsculas) -------------------------
R_PERICIA = re.compile(r"\bperit[oa]s?\b|laudo pericial|honorarios periciais|prova pericial|\bpericia\b")
R_PERICIA_NAO = re.compile(
    r"(indefiro|dispenso|dispensad\w+|desnecessari\w+)\W+(?:\w+\W+){0,4}(prova pericial|pericia)"
    r"|descaber pericia|nao cabe pericia|incabivel\w* (a )?pericia"
)
R_ACORDO = re.compile(
    r"homolog\w*\W+(?:\w+\W+){0,3}(acordo|transacao)|acordo homologado|termo de acordo|transacao homologada"
)
R_DESIST = re.compile(r"desistencia|renuncia ao direito|renuncio|renuncia a")
R_SENTENCA_TIPO = re.compile(r"\bsentenca\b|\bacordao\b")
R_DISPOSITIVO = re.compile(
    r"julgo (parcialmente )?(procedente|improcedente)|extingo o processo|dou provimento|nego provimento"
)
R_TRANSITO = re.compile(r"transit\w+ em julgado")
R_BAIXA = re.compile(r"baixa definitiva|arquivamento definitivo|arquivado definitivamente|arquivados? os autos")
R_ACORDO_NAO = re.compile(r"conciliacao,? esta nao foi alcancada|nao houve acordo|nao (foi|restou) alcancad\w+ (o )?acordo|sem acordo")
R_CERT_TRANSITO = re.compile(r"transit\w+ em julgado em (\d{1,2}) de ([a-z]+) de (\d{4})")
R_PERICIA_FORTE = re.compile(r"nomeio .{0,25}perit|laudo pericial|honorarios periciais|laudo do perito")
_MESES_EXT = {"janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7,
              "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}
R_DOC_DECISAO = re.compile(r"^\d{5,} - (sentenca|acordao)\b")
R_TIPO_DECISAO = re.compile(r"^(sentenca|acordao|julgad[oa]s? (parcialmente )?(procedente|improcedente)|julgad[oa]s? procedente em parte|extint[oa] o processo)")
R_EV_DESFAV = re.compile(r"^julgad[oa]s? (parcialmente )?procedente|^julgad[oa]s? procedente em parte")
R_EV_FAV = re.compile(r"^julgad[oa]s? improcedente|^extint[oa] o processo")
R_SANEAMENTO = re.compile(r"saneamento|audiencia de instrucao|audiencia de conciliacao")
R_POSTULATORIA = re.compile(r"citacao|contestacao|\bresposta\b|carta de citacao")


def _mov_norm(m: Movimento) -> str:
    return norm(m.texto)


def _trecho(texto_bruto: str, padrao: re.Pattern[str], janela: int = 90) -> str | None:
    """Acha o padrão no texto sem acento e devolve o trecho LITERAL (com acento) do bruto."""
    # Mapeia posição do texto normalizado para o bruto caractere a caractere.
    # O NFKD pode mudar o tamanho; por isso a busca é feita por linha do bruto.
    for linha in texto_bruto.split("\n"):
        ln = norm(linha)
        m = padrao.search(ln)
        if m:
            return espaco(linha)[: janela * 2]
    return None


def _acha_em_movimentos(p: Processo, padrao: re.Pattern[str]):
    for mv in p.movimentos:
        t = _trecho(mv.texto, padrao)
        if t:
            return mv, t
    return None


def _acha_em_documentos(p: Processo, padrao: re.Pattern[str]):
    for d in p.documentos:
        t = _trecho(d.texto, padrao)
        if t:
            return d, t
    return None


def _confere(p: Processo, c: Campo) -> Campo:
    """A evidência tem de existir, palavra por palavra, no texto bruto colado."""
    if not c.evidencia:
        return c
    bruto = espaco(p.texto + " " + " ".join(d.texto for d in p.documentos))
    if espaco(c.evidencia) not in bruto:
        c.evidencia_confere = False
        c.estado, c.motivo = NV, "evidencia_nao_confere"
    return c


def _campo_de_mov(nome: str, estado: str, valor: str, mv: Movimento, trecho: str) -> Campo:
    return Campo(
        campo=nome,
        estado=estado,
        valor=valor,
        fonte=f"movimento: {mv.tipo}",
        documento_origem=f"movimento {mv.indice}",
        acesso_documento="publico",
        data_da_fonte=mv.data or "",
        evidencia=trecho,
        localizacao=f"movimento {mv.indice} ({mv.tipo})",
    )


def _campo_de_doc(nome: str, estado: str, valor: str, d, trecho: str) -> Campo:
    return Campo(
        campo=nome,
        estado=estado,
        valor=valor,
        fonte=f"documento: {d.rotulo}",
        documento_origem=d.rotulo,
        acesso_documento=d.acesso,
        evidencia=trecho,
        localizacao=f"documento {d.rotulo}",
    )


def _nv(nome: str, motivo: str, valor: str = "") -> Campo:
    return Campo(campo=nome, estado=NV, motivo=motivo, valor=valor)


def _motivo_ausencia(p: Processo) -> str:
    if not p.movimentos and not p.documentos:
        return "nao_consultado"
    if not p.movimentos_lista_completa:
        return "lista_parcial"
    return "sem_mencao_em_movimento"


# ---- extratores ----------------------------------------------------------------
R_PARTE_DOC = re.compile(r"^(autor|autora|requerente|reu|re|requerido|requerida):\s*(.+)$")
R_PARTE_DOC_SUF = re.compile(r"^(.+?)\s*\((autor|autora|reu|re|requerente|requerido)\)\s*$")


def _personagens_de_documentos(p: Processo) -> list[Personagem]:
    """Cabeçalho de sentença ou ata: 'RÉU: NOME' ou 'NOME (RÉU)'. Só lê o que está escrito."""
    out: list[Personagem] = []
    for d in p.documentos:
        for linha in d.texto.split("\n")[:60]:  # só o cabeçalho do documento
            s = espaco(linha)
            m = R_PARTE_DOC.match(norm(s))
            if m:
                nome = s.split(":", 1)[1].strip()
                papel = m.group(1)
            else:
                m2 = R_PARTE_DOC_SUF.match(s) if s == s.upper() else None
                if not m2:
                    continue
                nome, papel = m2.group(1).strip(), norm(m2.group(2))
            polo = "ativo" if papel in ("autor", "autora", "requerente") else "passivo"
            out.append(Personagem(papel=papel, polo=polo, nome=nome, linha=s, documento=d.rotulo, acesso=d.acesso))
    return out


def partes(p: Processo, partes_alvo: list[str]) -> Campo:
    if not partes_alvo:
        return _nv("parte_alvo_no_polo_passivo", "nao_consultado", "nenhuma parte-alvo configurada")
    de_documento = not p.personagens
    personagens = p.personagens or _personagens_de_documentos(p)
    if not personagens:
        return _nv("parte_alvo_no_polo_passivo", "nao_consultado", "lista de partes não colada; abra a aba de partes")
    alvos = [norm(a) for a in partes_alvo]
    for per in personagens:
        if per.polo == "passivo" and any(a in norm(per.nome) for a in alvos):
            return Campo(
                campo="parte_alvo_no_polo_passivo",
                estado=SIM,
                valor="parte-alvo no polo passivo",
                fonte=(f"{per.documento}" if per.documento.startswith("evento") else f"documento: {per.documento}")
                if per.documento else "lista de personagens",
                documento_origem=per.documento,
                acesso_documento=per.acesso or "publico",
                evidencia=per.linha,
                localizacao=(per.documento if per.documento.startswith("evento") else f"cabeçalho de {per.documento}")
                if per.documento else f"personagem ({per.papel})",
            )
    if p.partes_lista_completa and not de_documento:
        # lista inteira lida e a parte-alvo não está no polo passivo
        no_ativo = any(per.polo == "ativo" and any(a in norm(per.nome) for a in alvos) for per in personagens)
        ev = personagens[0].linha
        return Campo(
            campo="parte_alvo_no_polo_passivo",
            estado=NAO,
            valor="parte-alvo está no polo ativo" if no_ativo else "parte-alvo não consta na lista completa",
            fonte="lista de personagens (lista completa lida)",
            acesso_documento="publico",
            evidencia=ev,
            localizacao="lista completa de personagens",
            confianca="regra",
        )
    # parte vinda só do cabeçalho de documento nunca vira NAO: não é lista completa
    return _nv("parte_alvo_no_polo_passivo", "lista_parcial", "a capa ou o cabeçalho mostram só parte dos personagens")


def pericia(p: Processo) -> list[Campo]:
    laudo_juizo = _nv("pericia_laudo_juizo", "documento_restrito", "ler o laudo; juízo é humano")
    forte = _acha_em_movimentos(p, R_PERICIA_FORTE) or _acha_em_documentos(p, R_PERICIA_FORTE)
    neg = _acha_em_movimentos(p, R_PERICIA_NAO) or _acha_em_documentos(p, R_PERICIA_NAO)
    if neg and not forte:  # "descabe perícia" também contém a palavra perícia: negativo primeiro
        origem, trecho = neg
        c = (
            _campo_de_mov("pericia", NAO, "perícia dispensada, indeferida ou incabível", origem, trecho)
            if isinstance(origem, Movimento)
            else _campo_de_doc("pericia", NAO, "perícia dispensada, indeferida ou incabível", origem, trecho)
        )
        return [c, laudo_juizo]
    achado = _acha_em_movimentos(p, R_PERICIA) or _acha_em_documentos(p, R_PERICIA)
    if achado:
        origem, trecho = achado
        c = (
            _campo_de_mov("pericia", SIM, "há menção a perícia", origem, trecho)
            if isinstance(origem, Movimento)
            else _campo_de_doc("pericia", SIM, "há menção a perícia", origem, trecho)
        )
        laudo_juizo.revisao = "pendente"
        return [c, laudo_juizo]
    neg = _acha_em_movimentos(p, R_PERICIA_NAO) or _acha_em_documentos(p, R_PERICIA_NAO)
    if neg:
        origem, trecho = neg
        c = (
            _campo_de_mov("pericia", NAO, "perícia dispensada ou indeferida", origem, trecho)
            if isinstance(origem, Movimento)
            else _campo_de_doc("pericia", NAO, "perícia dispensada ou indeferida", origem, trecho)
        )
        return [c, laudo_juizo]
    return [_nv("pericia", _motivo_ausencia(p)), laudo_juizo]


def acordo(p: Processo) -> Campo:
    neg = _acha_em_movimentos(p, R_ACORDO_NAO) or _acha_em_documentos(p, R_ACORDO_NAO)
    pos = _acha_em_movimentos(p, R_ACORDO) or _acha_em_documentos(p, R_ACORDO)
    if neg and pos:  # as fontes se contradizem: não decide, manda para revisão
        origem, trecho = pos
        valor = "há texto de acordo homologado e texto de acordo não alcançado"
        c = (_campo_de_mov("acordo", NV, valor, origem, trecho) if isinstance(origem, Movimento)
             else _campo_de_doc("acordo", NV, valor, origem, trecho))
        c.estado, c.motivo = NV, "conflito_entre_fontes"  # mantém origem e acesso do trecho
        return c
    if neg:  # texto positivo que afirma o negativo (ex.: ata: conciliação não alcançada)
        origem, trecho = neg
        if isinstance(origem, Movimento):
            return _campo_de_mov("acordo", NAO, "acordo não alcançado", origem, trecho)
        return _campo_de_doc("acordo", NAO, "acordo não alcançado", origem, trecho)
    achado = _acha_em_movimentos(p, R_ACORDO) or _acha_em_documentos(p, R_ACORDO)
    if achado:
        origem, trecho = achado
        if isinstance(origem, Movimento):
            return _campo_de_mov("acordo", SIM, "há menção a acordo ou transação", origem, trecho)
        return _campo_de_doc("acordo", SIM, "há menção a acordo ou transação", origem, trecho)
    return _nv("acordo", _motivo_ausencia(p))


def desistencia(p: Processo) -> Campo:
    achado = _acha_em_movimentos(p, R_DESIST) or _acha_em_documentos(p, R_DESIST)
    if achado:
        origem, trecho = achado
        if isinstance(origem, Movimento):
            return _campo_de_mov("desistencia_ou_renuncia", SIM, "há menção a desistência ou renúncia", origem, trecho)
        return _campo_de_doc("desistencia_ou_renuncia", SIM, "há menção a desistência ou renúncia", origem, trecho)
    return _nv("desistencia_ou_renuncia", _motivo_ausencia(p))


def _evidencia_de_decisao(mv: Movimento) -> str | None:
    """Linha que prova sentença ou acórdão: o tipo do movimento ou um documento 'número - Sentença'.
    'Projeto de Sentença' não conta: é minuta, não decisão."""
    if R_TIPO_DECISAO.match(norm(mv.tipo)):
        for linha in mv.texto.split("\n"):
            if espaco(mv.tipo) in espaco(linha):
                return espaco(linha)
        return espaco(mv.texto.split("\n")[0])
    for linha in mv.texto.split("\n"):
        if R_DOC_DECISAO.match(norm(linha)):
            return espaco(linha)
    return None


def parte_citada(p: Processo, partes_alvo: list[str]) -> Campo:
    """A parte-alvo aparece no texto (por exemplo, 'decorrido prazo de ...'), sem dizer o polo."""
    alvos = [norm(a) for a in partes_alvo]
    for mv in p.movimentos:
        for linha in mv.texto.split("\n"):
            if any(a in norm(linha) for a in alvos):
                return _campo_de_mov("parte_alvo_citada", SIM, "parte-alvo citada; o polo não consta deste texto", mv, espaco(linha))
    for per in p.personagens:
        if any(a in norm(per.nome) for a in alvos):
            return Campo(campo="parte_alvo_citada", estado=SIM, valor="parte-alvo na lista de personagens",
                         fonte="lista de personagens", acesso_documento="publico", evidencia=per.linha,
                         localizacao=f"personagem ({per.papel})")
    return _nv("parte_alvo_citada", "sem_mencao_em_movimento" if p.movimentos_lista_completa else "lista_parcial")


def _decisao_existencia(p: Processo) -> list[Campo]:
    """Existência de sentença ou acórdão."""
    juizo = _nv("decisao_juizo", "juizo_humano", "revisão humana: favorável ou desfavorável à parte-alvo")
    for mv in p.movimentos:
        t = _evidencia_de_decisao(mv)
        if t:
            disp = _trecho(mv.texto, R_DISPOSITIVO)
            c = _campo_de_mov("decisao", SIM, "sentença ou acórdão registrado", mv, t)
            if disp:
                juizo.evidencia = disp
                juizo.localizacao = c.localizacao
                juizo.fonte = c.fonte
                juizo.data_da_fonte = c.data_da_fonte
                juizo.acesso_documento = c.acesso_documento
            return [c, juizo]
    achado = _acha_em_documentos(p, R_DISPOSITIVO)
    if achado:
        d, trecho = achado
        c = _campo_de_doc("decisao", SIM, "dispositivo de sentença ou acórdão no texto", d, trecho)
        juizo.evidencia = trecho
        juizo.localizacao = c.localizacao
        juizo.fonte = c.fonte
        juizo.acesso_documento = c.acesso_documento
        return [c, juizo]
    return [_nv("decisao", _motivo_ausencia(p)), juizo]


# ---- resultado da decisão pelo critério do cliente ------------------------------
# Critério (definido pelo Luís em 30/10/2026): para a parte-alvo no polo passivo e a seguradora,
# DESFAVORÁVEL = condenação a pagar ou ressarcir; FAVORÁVEL = decisão sem condenação.
# A regra só sugere. A revisão humana continua pendente.
R_DISP_INICIO = re.compile(r"^(dispositivo|isto posto|ante o exposto|pelo exposto|diante do exposto)\b")
R_FIM_DOC = re.compile(r"este documento foi gerado|assinado eletronicamente")
R_DESFAV = re.compile(r"julgo (parcialmente )?procedente|julgo procedentes?\b|\bcondeno\b|\bcondenar\b|condenad[oa]s? (a|ao)\b")
R_FAV = re.compile(
    r"julgo improcedente|julgo extinto|extingo o processo|extinto o processo sem|homologo a desistencia|indefiro a (peticao )?inicial"
)


def _segmentos_dispositivo(p: Processo):
    for d in p.documentos:
        rot = norm(d.rotulo)
        if not any(k in rot for k in ("sentenca", "acordao", "decisao")):
            continue
        linhas = d.texto.split("\n")
        for i, l in enumerate(linhas):
            if R_DISP_INICIO.match(norm(espaco(l))):
                fim = len(linhas)
                for j in range(i, len(linhas)):
                    if R_FIM_DOC.search(norm(linhas[j])):
                        fim = j
                        break
                yield d, linhas[i:fim]
                break


def classificar_resultado(p: Processo):
    """Devolve (rotulo, trecho literal, localizacao, fonte) ou None. Só lê o dispositivo."""
    for d, seg in _segmentos_dispositivo(p):
        for linha in seg:
            n = norm(linha)
            if R_DESFAV.search(n):
                return "DESFAVORÁVEL", espaco(linha), f"documento {d.rotulo}", f"documento: {d.rotulo}", d.acesso
        for linha in seg:
            if R_FAV.search(norm(linha)):
                return "FAVORÁVEL", espaco(linha), f"documento {d.rotulo}", f"documento: {d.rotulo}", d.acesso
    for mv in p.movimentos:  # título do evento (eproc): "Julgado improcedente o pedido"
        nt = norm(mv.tipo)
        evid = _evidencia_de_decisao(mv)
        if evid and R_EV_DESFAV.match(nt):
            return "DESFAVORÁVEL", evid, f"movimento {mv.indice} ({mv.tipo})", f"movimento: {mv.tipo}", "publico"
        if evid and R_EV_FAV.match(nt):
            return "FAVORÁVEL", evid, f"movimento {mv.indice} ({mv.tipo})", f"movimento: {mv.tipo}", "publico"
    for mv in p.movimentos:  # texto de sentença no próprio movimento
        if _evidencia_de_decisao(mv) or "sentenca" in norm(mv.tipo):
            for linha in mv.texto.split("\n"):
                n = norm(linha)
                if R_DESFAV.search(n):
                    return "DESFAVORÁVEL", espaco(linha), f"movimento {mv.indice} ({mv.tipo})", f"movimento: {mv.tipo}", "publico"
                if R_FAV.search(n):
                    return "FAVORÁVEL", espaco(linha), f"movimento {mv.indice} ({mv.tipo})", f"movimento: {mv.tipo}", "publico"
    return None


def decisao(p: Processo, parte_passiva: bool = False) -> list[Campo]:
    """Existência de sentença ou acórdão e sugestão de resultado pelo critério do cliente."""
    campos = _decisao_existencia(p)
    juizo = next(c for c in campos if c.campo == "decisao_juizo")
    if not parte_passiva:
        juizo.valor = "revisão humana: a parte-alvo no polo passivo não foi confirmada"
        return campos
    r = classificar_resultado(p)
    if r is None:
        return campos
    rotulo, trecho, loc, fonte, acesso = r
    juizo.estado, juizo.motivo = SIM, ""
    juizo.valor = (f"{rotulo} (sugestão por regra; revisão humana pendente). Critério: condenação a pagar ou "
                   "ressarcir é desfavorável; sem condenação é favorável.")
    juizo.evidencia, juizo.localizacao, juizo.fonte = trecho, loc, fonte
    juizo.acesso_documento = acesso  # vem do Documento, não é inferido pelo prefixo da fonte
    juizo.confianca, juizo.revisao = "regra", "pendente"
    return campos



def _data_certidao_transito(p: Processo):
    """Data do trânsito escrita numa certidão ('transitou em julgado em 16 de março de 2026')."""
    for d in p.documentos:
        if "certidao" not in norm(d.rotulo):  # só documento que se declara certidão
            continue
        for linha in d.texto.split("\n"):
            n = norm(linha)
            m = R_CERT_TRANSITO.search(n)
            if not m or m.group(2) not in _MESES_EXT or re.search(r"\bnao\b|aguardando", n):
                continue
            try:
                data = date(int(m.group(3)), _MESES_EXT[m.group(2)], int(m.group(1)))
            except ValueError:
                continue  # data inexistente
            return d, espaco(linha), data.strftime("%d/%m/%Y")
    return None


def transito(p: Processo) -> Campo:
    cert = _data_certidao_transito(p)
    if cert:  # o documento vence o movimento: o cartório lança o movimento depois do fato
        d, linha, data = cert
        c = _campo_de_doc("transito_em_julgado", SIM, f"trânsito em julgado em {data} (certidão)", d, linha)
        mv = _acha_em_movimentos(p, R_TRANSITO)
        if mv and mv[0].data and mv[0].data != data and "aguardando" not in norm(mv[1]):
            c.valor += f"; o histórico registra o movimento em {mv[0].data}"
        return c
    achado = _acha_em_movimentos(p, R_TRANSITO)
    if achado:
        mv, trecho = achado
        # a localização "Aguardando Trânsito Julgado" não é o trânsito: tratada à parte
        if "aguardando" not in norm(trecho):
            return _campo_de_mov("transito_em_julgado", SIM, f"trânsito em julgado em {mv.data or 'data não lida'}", mv, trecho)
    loc = p.capa.get("localizacao", "")
    if "aguardando" in norm(loc) and "transito" in norm(loc):
        return Campo(
            campo="transito_em_julgado",
            estado=NAO,
            valor="ainda não transitou (aguarda trânsito)",
            fonte="capa: localização na serventia",
            acesso_documento="publico",
            evidencia=loc,
            localizacao="capa",
        )
    return _nv("transito_em_julgado", _motivo_ausencia(p))


def fase(p: Processo) -> Campo:
    for mv in p.movimentos:  # baixa e arquivamento vêm depois do trânsito: checar primeiro
        t = _trecho(mv.texto, R_BAIXA)
        if t:
            return _campo_de_mov("fase", SIM, "baixado ou arquivado", mv, t)
    for mv in p.movimentos:
        t = _trecho(mv.texto, R_TRANSITO)
        if t and "aguardando" not in norm(t):
            return _campo_de_mov("fase", SIM, "trânsito em julgado", mv, t)
    loc = p.capa.get("localizacao", "")
    if "aguardando" in norm(loc) and "transito" in norm(loc):
        return Campo(
            campo="fase",
            estado=SIM,
            valor="aguardando trânsito em julgado",
            fonte="capa: localização na serventia",
            acesso_documento="publico",
            evidencia=loc,
            localizacao="capa",
            confianca="regra",
        )
    for mv in p.movimentos:
        t = _evidencia_de_decisao(mv)
        if t:
            return _campo_de_mov("fase", SIM, "sentenciado", mv, t)
    achado = _acha_em_movimentos(p, R_SANEAMENTO)
    if achado:
        mv, t = achado
        return _campo_de_mov("fase", SIM, "instrutória", mv, t)
    achado = _acha_em_movimentos(p, R_POSTULATORIA)
    if achado:
        mv, t = achado
        return _campo_de_mov("fase", SIM, "postulatória", mv, t)
    return _nv("fase", _motivo_ausencia(p))


# ---- comparação com a fase que o cliente registrou na base ----------------------
# Etapas em ordem. A base do cliente costuma ficar numa etapa anterior à do tribunal: isso é
# defasagem, não divergência de fato. "Arquivado" vem DEPOIS de "extinção sem julgamento de mérito".
ETAPAS = {"inicial": 1, "instrutoria": 2, "sentenca": 3, "transito": 4, "encerrado": 5}
_ETAPA_TRIBUNAL = {
    "postulatória": "inicial",
    "instrutória": "instrutoria",
    "sentenciado": "sentenca",
    "aguardando trânsito em julgado": "sentenca",
    "trânsito em julgado": "transito",
    "baixado ou arquivado": "encerrado",
}


def _etapa_base(fase_base: str) -> str | None:
    t = norm(fase_base)
    if "inicial" in t:
        return "inicial"
    if "instrut" in t:
        return "instrutoria"
    if any(k in t for k in ("pagamento", "encerr", "arquiv", "baixa")):
        return "encerrado"
    if "transitado" in t:
        return "transito"
    if "extin" in t or "julgamento" in t:  # extinção sem julgamento de mérito é sentença
        return "sentenca"
    return None


def compara_fase(fase_base: str | None, fase_tribunal: Campo) -> str:
    """Reporta, não corrige. Devolve: coincide, base_defasada, base_adiantada ou indeterminado."""
    if not fase_base or fase_tribunal.estado != SIM:
        return "indeterminado"
    eb = _etapa_base(fase_base)
    et = _ETAPA_TRIBUNAL.get(fase_tribunal.valor)
    if eb is None or et is None:
        return "indeterminado"
    if ETAPAS[eb] == ETAPAS[et]:
        return "coincide"
    return "base_defasada" if ETAPAS[eb] < ETAPAS[et] else "base_adiantada"


_CPF = re.compile("[0-9]{3}[.][0-9]{3}[.][0-9]{3}-[0-9]{2}")


def mascara_cpf(texto: str) -> str:
    """CPF de pessoa física não é gravado em evidência nem em valor (CNPJ de empresa permanece)."""
    return _CPF.sub("***.***.***-**", texto or "")


def extrair(p: Processo, partes_alvo: list[str]) -> list[Campo]:
    pc = partes(p, partes_alvo)
    campos: list[Campo] = [pc, parte_citada(p, partes_alvo), fase(p)]
    campos += pericia(p)
    campos += [acordo(p), desistencia(p)]
    campos += decisao(p, parte_passiva=pc.estado == SIM)
    campos.append(transito(p))
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for c in campos:
        _confere(p, c)
        c.evidencia, c.valor = mascara_cpf(c.evidencia), mascara_cpf(c.valor)  # depois da conferência literal
        c.revisao = c.revisao or "pendente"
        c.data_da_fonte = c.data_da_fonte or ""
        # regra final: SIM ou NAO sem trecho literal viram NAO_VISIVEL
        if c.estado in (SIM, NAO) and not c.evidencia:
            c.estado, c.motivo = NV, c.motivo or "sem_mencao_em_movimento"
    return campos
