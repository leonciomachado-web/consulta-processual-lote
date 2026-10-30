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
from datetime import datetime, timezone

from .parser import Movimento, Processo
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
)
R_ACORDO = re.compile(
    r"homolog\w*\W+(?:\w+\W+){0,3}(acordo|transacao)|acordo homologado|termo de acordo|transacao homologada"
)
R_DESIST = re.compile(r"desistencia|renuncia ao direito|renuncio|renuncia a")
R_SENTENCA_TIPO = re.compile(r"\bsentenca\b|\bacordao\b")
R_DISPOSITIVO = re.compile(
    r"julgo (parcialmente )?(procedente|improcedente)|extingo o processo|dou provimento|nego provimento"
)
R_TRANSITO = re.compile(r"transito em julgado")
R_BAIXA = re.compile(r"baixa definitiva|arquivamento definitivo|arquivados? os autos")
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
def partes(p: Processo, partes_alvo: list[str]) -> Campo:
    if not partes_alvo:
        return _nv("parte_alvo_no_polo_passivo", "nao_consultado", "nenhuma parte-alvo configurada")
    if not p.personagens:
        return _nv("parte_alvo_no_polo_passivo", "nao_consultado")
    alvos = [norm(a) for a in partes_alvo]
    for per in p.personagens:
        if per.polo == "passivo" and any(a in norm(per.nome) for a in alvos):
            return Campo(
                campo="parte_alvo_no_polo_passivo",
                estado=SIM,
                valor="parte-alvo no polo passivo",
                fonte="lista de personagens",
                acesso_documento="publico",
                evidencia=per.linha,
                localizacao=f"personagem ({per.papel})",
            )
    if p.partes_lista_completa:
        # lista inteira lida e a parte-alvo não está no polo passivo
        no_ativo = any(per.polo == "ativo" and any(a in norm(per.nome) for a in alvos) for per in p.personagens)
        ev = p.personagens[0].linha
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
    return _nv("parte_alvo_no_polo_passivo", "lista_parcial", "a capa mostra só parte dos personagens")


def pericia(p: Processo) -> list[Campo]:
    achado = _acha_em_movimentos(p, R_PERICIA) or _acha_em_documentos(p, R_PERICIA)
    laudo_juizo = _nv("pericia_laudo_juizo", "documento_restrito", "ler o laudo; juízo é humano")
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


def decisao(p: Processo) -> list[Campo]:
    """Existência de sentença ou acórdão. O juízo "favorável" é sempre humano."""
    juizo = _nv("decisao_juizo", "juizo_humano", "revisão humana: favorável ou desfavorável à parte-alvo")
    for mv in p.movimentos:
        if R_SENTENCA_TIPO.search(norm(mv.tipo)):
            t = espaco(mv.texto.split("\n")[0])
            disp = _trecho(mv.texto, R_DISPOSITIVO)
            c = _campo_de_mov("decisao", SIM, "sentença ou acórdão registrado", mv, t)
            if disp:
                juizo.evidencia = disp
                juizo.localizacao = c.localizacao
                juizo.fonte = c.fonte
                juizo.data_da_fonte = c.data_da_fonte
            return [c, juizo]
    achado = _acha_em_documentos(p, R_DISPOSITIVO)
    if achado:
        d, trecho = achado
        c = _campo_de_doc("decisao", SIM, "dispositivo de sentença ou acórdão no texto", d, trecho)
        juizo.evidencia = trecho
        juizo.localizacao = c.localizacao
        juizo.fonte = c.fonte
        return [c, juizo]
    return [_nv("decisao", _motivo_ausencia(p)), juizo]


def transito(p: Processo) -> Campo:
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
    for mv in p.movimentos:
        t = _trecho(mv.texto, R_TRANSITO)
        if t and "aguardando" not in norm(t):
            return _campo_de_mov("fase", SIM, "trânsito em julgado", mv, t)
    for mv in p.movimentos:
        t = _trecho(mv.texto, R_BAIXA)
        if t:
            return _campo_de_mov("fase", SIM, "baixado ou arquivado", mv, t)
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
        if R_SENTENCA_TIPO.search(norm(mv.tipo)):
            return _campo_de_mov("fase", SIM, "sentenciado", mv, espaco(mv.texto.split("\n")[0]))
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
_CAT_TRIBUNAL = {
    "postulatória": "inicial",
    "instrutória": "instrutoria",
    "sentenciado": "julgamento",
    "aguardando trânsito em julgado": "julgamento",
    "trânsito em julgado": "encerrado",
    "baixado ou arquivado": "encerrado",
}


def _cat_base(fase_base: str) -> str | None:
    t = norm(fase_base)
    if "inicial" in t:
        return "inicial"
    if "instrut" in t:
        return "instrutoria"
    if "julgamento" in t:
        return "julgamento"
    if any(k in t for k in ("pagamento", "extin", "encerr", "transitado")):
        return "encerrado"
    return None


def compara_fase(fase_base: str | None, fase_tribunal: Campo) -> str:
    """Reporta, não corrige. Devolve: coincide, diverge ou indeterminado."""
    if not fase_base or fase_tribunal.estado != SIM:
        return "indeterminado"
    cb = _cat_base(fase_base)
    ct = _CAT_TRIBUNAL.get(fase_tribunal.valor)
    if cb is None or ct is None:
        return "indeterminado"
    return "coincide" if cb == ct else "diverge"


def extrair(p: Processo, partes_alvo: list[str]) -> list[Campo]:
    campos: list[Campo] = [partes(p, partes_alvo), fase(p)]
    campos += pericia(p)
    campos += [acordo(p), desistencia(p)]
    campos += decisao(p)
    campos.append(transito(p))
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for c in campos:
        _confere(p, c)
        c.revisao = c.revisao or "pendente"
        c.data_da_fonte = c.data_da_fonte or ""
        # regra final: SIM ou NAO sem trecho literal viram NAO_VISIVEL
        if c.estado in (SIM, NAO) and not c.evidencia:
            c.estado, c.motivo = NV, c.motivo or "sem_mencao_em_movimento"
    return campos
