"""Modelos da planilha de saída e do painel, com processos inventados (números fictícios).

`python -m consulta_lote modelo` grava os dois arquivos na pasta de dados, para a equipe ver o formato
antes de haver dado real. Nada aqui vem de caso real.
"""
from __future__ import annotations

from pathlib import Path

from . import painel, saida
from .campos import Campo, compara_fase
from .cnj import Cnj


def _numero(seq: int, ano: str = "2025") -> str:
    base = f"{seq:07d}{ano}89" + "9" + "0000"
    base_dv = f"{seq:07d}{ano}899" + "0000" + "00"
    dv = 98 - (int(base_dv) % 97)
    return Cnj(f"{seq:07d}", f"{dv:02d}", ano, "8", "99", "0000").formatado


def _campo(estado, valor="", evidencia="", loc="", acesso="publico", motivo="", data="", revisao="pendente"):
    return dict(estado=estado, valor=valor, motivo=motivo, evidencia=evidencia, localizacao=loc, acesso=acesso,
                data=data, revisao=revisao, confianca="regra")


def dados_modelo() -> dict:
    nv = "NAO_VISIVEL_NO_ACESSO_PUBLICO"
    base = dict(tipo_pasta="AÇÃO JUDICIAL", rito="COMUM", tipo_vara="CÍVEL", tipo_acao="INDENIZATÓRIA", foro="ÚNICO",
                vara="1ª", atividade="Andamentos", motivo_acao="NÃO COBERTURA", orgao="1ª VARA CÍVEL SINTÉTICA")
    exemplos = [
        # número, sistema, fase_base, fase_tribunal, decisão, trânsito, perícia, acordo, resultado, comarca, valor, ano
        (1, "eproc", "FASE INICIAL", "instrutória", None, None, "sim", "não visível", "sem decisão registrada", "COMARCA ALFA", 40000, "2024"),
        (2, "eproc", "FASE INSTRUTÓRIA", "sentenciado", "improcedente", None, "não visível", "não visível", "favorável (sugestão)", "COMARCA ALFA", 25000, "2025"),
        (3, "eproc", "FASE INSTRUTÓRIA", "sentenciado", "procedente em parte", None, "não visível", "não visível", "desfavorável (sugestão)", "COMARCA BETA", 80000, "2025"),
        (4, "pje", "EXTINÇÃO SEM JULGAMENTO DE MÉRITO", "baixado ou arquivado", "extinção", "16/03/2026", "não", "não", "favorável (sugestão)", "COMARCA ALFA", 20000, "2025"),
        (5, "pje", "FASE INICIAL", "postulatória", None, None, "não visível", "não visível", "sem decisão registrada", "COMARCA GAMA", 120000, "2026"),
        (6, "legado", "FASE INICIAL", "não classificada", None, None, "não visível", "não visível", "sem decisão registrada", "COMARCA BETA", 60000, "2026"),
    ]
    linhas = []
    for seq, sis, fb, ft, dec, tr, per, aco, res, com, val, ano in exemplos:
        num = _numero(seq, ano)
        cat = {"FASE INICIAL": "inicial", "FASE INSTRUTÓRIA": "instrutoria"}.get(fb, "extincao")
        campos = {
            "parte_alvo_no_polo_passivo": _campo("SIM", "parte-alvo no polo passivo", "(RÉU - EMPRESA ALFA SINTETICA LTDA)", "evento 63"),
            "fase": _campo("SIM", ft, "ARQUIVADO DEFINITIVAMENTE" if "arquiv" in ft else "Decisão de saneamento", "evento 47"),
            "pericia": _campo("SIM" if per == "sim" else ("NAO" if per == "não" else nv), "há menção a perícia" if per == "sim" else "",
                              "Expedida a intimação eletrônica - Perito" if per == "sim" else "", "evento 76", motivo="" if per != "não visível" else "sem_mencao_em_movimento"),
            "acordo": _campo("NAO" if aco == "não" else nv, "acordo não alcançado" if aco == "não" else "",
                             "Realizada proposta de conciliação, esta não foi alcançada." if aco == "não" else "",
                             "documento ata-1", acesso="restrito_login_ou_senha", motivo="" if aco == "não" else "sem_mencao_em_movimento"),
            "desistencia_ou_renuncia": _campo(nv, motivo="sem_mencao_em_movimento"),
            "decisao": _campo("SIM" if dec else nv, "sentença registrada" if dec else "", "Julgado %s o pedido" % dec if dec else "", "evento 61", motivo="" if dec else "sem_mencao_em_movimento", data="22/07/2026" if dec else ""),
            "decisao_juizo": _campo("SIM" if dec else nv, (res.split(" ")[0].upper() + " (sugestão por regra; revisão humana pendente)") if dec else "revisão humana", "Julgado %s o pedido" % dec if dec else "", "evento 61", motivo="" if dec else "juizo_humano"),
            "transito_em_julgado": _campo("SIM" if tr else nv, f"trânsito em julgado em {tr} (certidão); o histórico registra o movimento em 27/03/2026" if tr else "",
                                          "Certifico que a sentença transitou em julgado em 16 de março de 2026." if tr else "", "documento certidao-1", acesso="restrito_login_ou_senha", motivo="" if tr else "sem_mencao_em_movimento"),
        }
        linha = {**{k: "" for k in ("data_sentenca", "data_transito")}, **base, "numero": num, "ano": ano, "comarca": com,
                 "valor_causa": float(val), "faixa_valor": painel._faixa(float(val)), "fase_base": fb, "fase_base_cat": cat,
                 "fase_tribunal": ft, "sistema": sis, "analise": "análise completa", "campos": campos,
                 "parte_alvo": "sim", "sentenca": "sim" if dec else "não visível", "resultado": res,
                 "transito": "sim" if tr else "não visível", "data_transito": f"trânsito em julgado em {tr} (certidão)" if tr else "",
                 "data_sentenca": "22/07/2026" if dec else "", "pericia": per, "acordo": aco, "desistencia": "não visível",
                 "revisao": "pendente", "acesso": ["publico"] + (["restrito_login_ou_senha"] if aco == "não" or tr else []),
                 "base_x_tribunal": compara_fase(fb, Campo(campo="fase", estado="NAO_VISIVEL_NO_ACESSO_PUBLICO" if ft == "não classificada" else "SIM", valor=ft)),
                 "distribuicao": "2025-01-10", "proximo_passo": "ler a sentença no eproc" if dec else "ler os eventos no eproc",
                 "proximo_cat": "revisar a análise (juízo humano pendente)" if dec else "ler os eventos no tribunal",
                 "datajud": {"sistema_datajud": "", "orgao": "", "atualizado": "01/09/2026", "movimentos": 40, "migrado_em": "03/05/2026" if sis == "eproc" else "",
                             "sentenca_em": "22/07/2026" if dec else "", "transito_em": "27/03/2026" if tr else "", "baixa_em": "",
                             "acordo_em": "", "desistencia_em": "", "pericia_em": "", "ultimo_movimento": "01/09/2026 Conclusão"}}
        linhas.append(linha)
    # processos só com DataJud e ainda não consultados
    for seq in (7, 8):
        num = _numero(seq, "2026")
        linhas.append({**base, "numero": num, "ano": "2026", "comarca": "COMARCA GAMA", "valor_causa": 30000.0, "faixa_valor": "20 a 50 mil",
                       "fase_base": "FASE INICIAL", "fase_base_cat": "inicial", "fase_tribunal": "-" if seq == 8 else "sem marco (DataJud)",
                       "sistema": "desconhecido", "analise": "não achado no DataJud" if seq == 8 else "só DataJud", "campos": {},
                       "parte_alvo": "-", "sentenca": "-" if seq == 8 else "não registrada (DataJud)", "resultado": "-" if seq == 8 else "sem decisão registrada",
                       "transito": "-", "data_sentenca": "", "data_transito": "", "pericia": "-", "acordo": "-", "desistencia": "-", "revisao": "-",
                       "acesso": ["sem documento"], "base_x_tribunal": "indeterminado", "distribuicao": "2026-05-10",
                       "proximo_passo": "não achado no DataJud: procurar no eproc, no PJe e no portal do tribunal" if seq == 8 else "sem marco de decisão no DataJud: ler os eventos no tribunal",
                       "proximo_cat": "não achado no DataJud: procurar no tribunal" if seq == 8 else "ler os eventos no tribunal",
                       "datajud": {k: "" for k in ("sistema_datajud", "orgao", "atualizado", "movimentos", "migrado_em", "sentenca_em", "transito_em",
                                                    "baixa_em", "acordo_em", "desistencia_em", "pericia_em", "ultimo_movimento")}})
    return {"gerado_em": "MODELO COM DADOS INVENTADOS", "processos": linhas,
            "filtros": [{"chave": k, "rotulo": r} for k, r in painel.FILTROS],
            "graficos": [{"chave": k, "rotulo": r} for k, r in painel.GRAFICOS],
            "perguntas": [{"id": i, "texto": t, "campo": c} for i, t, c in painel.PERGUNTAS]}


def gravar(pasta: Path) -> list[Path]:
    pasta.mkdir(parents=True, exist_ok=True)
    d = dados_modelo()
    return [saida.gerar(d, pasta / "modelo-planilha-saida.xlsx"), painel.gerar_html(d, pasta / "modelo-painel.html")]
