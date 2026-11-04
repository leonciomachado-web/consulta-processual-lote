"""Planilha de saída completa (.xlsx): uma linha por processo da carteira, mais evidências, pendências de
revisão, as perguntas e um resumo com fórmulas. Mesmos dados do painel (painel.montar_dados).

Todo texto passa pela máscara de CPF e pela neutralização de fórmula. As fórmulas do resumo são escritas
pelo programa, não vêm de dado externo.
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from .campos import mascara_cpf
from .config import proteger_escrita
from .painel import PERGUNTAS
from .seguro import neutraliza

CINZA = PatternFill("solid", fgColor="E9ECF2")
VERDE = PatternFill("solid", fgColor="DFF3E7")
VERMELHO = PatternFill("solid", fgColor="FBE3E6")
AMARELO = PatternFill("solid", fgColor="FFF1CF")
NEGRITO = Font(bold=True)
AZUL_REVISAO = PatternFill("solid", fgColor="E3EEFF")

# (título da coluna, chave na linha, largura)
COLUNAS = [
    ("Processo", "numero", 27), ("Análise", "analise", 18), ("Sistema", "sistema", 11), ("Tipo da pasta", "tipo_pasta", 14),
    ("Rito", "rito", 16), ("Comarca", "comarca", 18), ("Ano", "ano", 6), ("Valor da causa", "valor_causa", 14),
    ("Fase na base do cliente", "fase_base", 26), ("Fase no tribunal", "fase_tribunal", 22),
    ("Base x tribunal", "base_x_tribunal", 16), ("Parte-alvo no polo passivo", "parte_alvo", 14),
    ("Quais partes-alvo no polo passivo", "partes_quais", 18),
    ("Sentença ou acórdão", "sentenca", 14), ("Resultado da decisão (sugestão)", "resultado", 22),
    ("Data da sentença", "data_sentenca", 12), ("Trânsito em julgado", "transito", 12), ("Data do trânsito", "data_transito", 30),
    ("Perícia", "pericia", 10), ("Acordo", "acordo", 10), ("Desistência ou renúncia", "desistencia", 12),
    ("Próximo passo", "proximo_passo", 46), ("Revisão", "revisao", 11),
]
REVISAO = ["Conferido por", "Correção", "Observação"]


def _txt(v):
    if isinstance(v, list):
        v = ", ".join(map(str, v))
    return neutraliza(mascara_cpf(v)) if isinstance(v, str) else v


def _folha_processos(wb: Workbook, linhas: list[dict]):
    ws = wb.active
    ws.title = "Processos"
    cab = [c[0] for c in COLUNAS] + ["DataJud: último movimento"] + REVISAO
    ws.append(cab)
    for r in linhas:
        ws.append([_txt(r.get(k)) for _, k, _ in COLUNAS] + [_txt(r["datajud"].get("ultimo_movimento", ""))] + ["", "", ""])
    for i, cel in enumerate(ws[1], start=1):
        cel.font, cel.fill = NEGRITO, (AZUL_REVISAO if i > len(COLUNAS) + 1 else CINZA)
        cel.alignment = Alignment(wrap_text=True, vertical="top")
    for i, (_t, _k, larg) in enumerate(COLUNAS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = larg
    ws.column_dimensions[get_column_letter(len(COLUNAS) + 1)].width = 34
    for j, larg in enumerate((16, 30, 30), start=len(COLUNAS) + 2):
        ws.column_dimensions[get_column_letter(j)].width = larg
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = ws.dimensions
    n = ws.max_row
    col = {k: get_column_letter(i) for i, (_t, k, _l) in enumerate(COLUNAS, start=1)}
    rc = f"{col['resultado']}2:{col['resultado']}{n}"
    ws.conditional_formatting.add(rc, FormulaRule(formula=[f'LEFT({col["resultado"]}2,5)="desfa"'], fill=VERMELHO))
    ws.conditional_formatting.add(rc, FormulaRule(formula=[f'LEFT({col["resultado"]}2,5)="favor"'], fill=VERDE))
    ws.conditional_formatting.add(rc, FormulaRule(formula=[f'{col["resultado"]}2="a classificar"'], fill=AMARELO))
    bx = f"{col['base_x_tribunal']}2:{col['base_x_tribunal']}{n}"
    ws.conditional_formatting.add(bx, CellIsRule(operator="equal", formula=['"coincide"'], fill=VERDE))
    ws.conditional_formatting.add(bx, FormulaRule(formula=[f'LEFT({col["base_x_tribunal"]}2,5)="base_"'], fill=AMARELO))
    rv = DataValidation(type="list", formula1='"pendente,conferido,corrigido"', allow_blank=True)
    ws.add_data_validation(rv)
    rv.add(f"{col['revisao']}2:{col['revisao']}{n}")
    for linha in ws.iter_rows(min_row=2):
        for cel in linha:
            cel.alignment = Alignment(wrap_text=True, vertical="top")
    return ws


def _folha_evidencias(wb: Workbook, linhas: list[dict]) -> None:
    ws = wb.create_sheet("Evidências")
    ws.append(["Processo", "Campo", "Estado", "Valor", "Motivo (se não visível)", "Evidência literal", "Onde", "Acesso",
               "Data da fonte", "Confiança", "Revisão"])
    for r in linhas:
        for nome, c in (r.get("campos") or {}).items():
            ws.append([_txt(x) for x in (r["numero"], nome, c.get("estado"), c.get("valor"), c.get("motivo"), c.get("evidencia"),
                                         c.get("localizacao"), c.get("acesso"), c.get("data"), c.get("confianca"), c.get("revisao"))])
    for i, larg in enumerate((27, 28, 16, 40, 22, 70, 30, 22, 12, 11, 11), start=1):
        ws.column_dimensions[get_column_letter(i)].width = larg
    for cel in ws[1]:
        cel.font, cel.fill = NEGRITO, CINZA
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def _folha_pendencias(wb: Workbook, linhas: list[dict]) -> None:
    ws = wb.create_sheet("Pendências de revisão")
    ws.append(["Processo", "Pendência", "Detalhe", "Evidência literal", "Conferido por", "Decisão da revisora", "Observação"])
    for r in linhas:
        c = r.get("campos") or {}
        if not c:
            continue
        j = c.get("decisao_juizo", {})
        if j.get("estado") == "SIM" and j.get("revisao") != "conferido":
            ws.append([_txt(x) for x in (r["numero"], "Confirmar o resultado sugerido da decisão", j.get("valor"), j.get("evidencia"), "", "", "")])
        for nome, cc in c.items():
            if cc.get("motivo") == "conflito_entre_fontes":
                ws.append([_txt(x) for x in (r["numero"], "Fontes se contradizem", nome, cc.get("evidencia"), "", "", "")])
        if r.get("base_x_tribunal") in ("base_defasada", "base_adiantada"):
            ws.append([_txt(x) for x in (r["numero"], "Atualizar a fase na base do cliente",
                                         f"base: {r['fase_base']} | tribunal: {r['fase_tribunal']} ({r['base_x_tribunal']})", "", "", "", "")])
        t = c.get("transito_em_julgado", {})
        if t.get("estado") == "SIM" and "histórico registra" in (t.get("valor") or ""):
            ws.append([_txt(x) for x in (r["numero"], "Data do trânsito: certidão difere do histórico", t.get("valor"), t.get("evidencia"), "", "", "")])
        if any(cc.get("acesso") == "nao_testado" for cc in c.values()):
            ws.append([_txt(x) for x in (r["numero"], "Documento com acesso não testado", "confirmar o sigilo à mão", "", "", "", "")])
    for i, larg in enumerate((27, 44, 60, 70, 16, 24, 30), start=1):
        ws.column_dimensions[get_column_letter(i)].width = larg
    for cel in ws[1]:
        cel.font, cel.fill = NEGRITO, CINZA
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def _folha_perguntas(wb: Workbook) -> None:
    ws = wb.create_sheet("Perguntas e legenda")
    ws.append(["Pergunta", "Campo no banco", "Como é respondida"])
    como = {
        "parte_alvo_no_polo_passivo": "Polo escrito nas intimações, lista de partes ou cabeçalho da sentença. Nunca NÃO a partir de lista parcial.",
        "fase": "Último marco real (baixa, trânsito, sentença, saneamento, citação). Compara com a fase da base: coincide, base defasada ou base adiantada.",
        "pericia": "Texto que afirma a perícia ou o seu descabimento. O juízo sobre o laudo é sempre humano.",
        "acordo": "Homologação de acordo ou ata que diz que a conciliação não foi alcançada. Fontes contraditórias vão para revisão.",
        "desistencia_ou_renuncia": "Menção a desistência ou renúncia em evento, petição ou decisão.",
        "decisao": "Sentença ou acórdão. Resultado pelo critério do cliente: condenação a pagar ou ressarcir é desfavorável; sem condenação é favorável (sugestão).",
        "transito_em_julgado": "Certidão de trânsito (vale sobre o movimento do histórico) ou movimento de trânsito.",
    }
    for _i, texto, campo in PERGUNTAS:
        ws.append([texto, campo, como[campo]])
    ws.append([])
    ws.append(["Estado", "", "Significado"])
    for e, s in (("SIM", "texto positivo encontrado, com trecho literal"),
                 ("NAO", "só com texto positivo que afirme o negativo, ou lista completa lida"),
                 ("NÃO VISÍVEL", "o texto lido não permite afirmar. Ausência nunca vira “não houve”. O motivo fica registrado"),
                 ("Resultado (sugestão)", "regra do critério do cliente, com revisão humana pendente"),
                 ("Acesso", "publico, restrito_login_ou_senha ou nao_testado, por documento")):
        ws.append([e, "", s])
    ws.column_dimensions["A"].width = 56
    ws.column_dimensions["B"].width = 28
    ws.column_dimensions["C"].width = 110
    for linha in ws.iter_rows():
        for cel in linha:
            cel.alignment = Alignment(wrap_text=True, vertical="top")
    ws["A1"].font = ws["B1"].font = ws["C1"].font = NEGRITO


def _folha_resumo(wb: Workbook, n: int) -> None:
    ws = wb.create_sheet("Resumo", 0)
    ws["A1"], ws["A1"].font = "Resumo da carteira (fórmulas sobre a aba Processos)", Font(bold=True, size=13)
    nomes = {k: get_column_letter(i) for i, (_t, k, _l) in enumerate(COLUNAS, start=1)}
    linhas = [("Processos", f"=COUNTA(Processos!{nomes['numero']}2:{nomes['numero']}{n})")]
    for rot, k, v in (("Análise completa", "analise", "análise completa"), ("Só DataJud", "analise", "só DataJud"),
                      ("Sistema eproc", "sistema", "eproc"), ("Sistema PJe", "sistema", "pje"), ("Sistema legado", "sistema", "legado"),
                      ("Sentença registrada", "sentenca", "sim*"), ("Resultado desfavorável (sugestão)", "resultado", "desfavor*"),
                      ("Resultado favorável (sugestão)", "resultado", "favor*"), ("Base defasada", "base_x_tribunal", "base_defasada"),
                      ("Base adiantada", "base_x_tribunal", "base_adiantada"), ("Revisão pendente", "revisao", "pendente")):
        c = nomes[k]
        linhas.append((rot, f'=COUNTIF(Processos!{c}2:{c}{n},"{v}")'))
    for i, (rot, f) in enumerate(linhas, start=3):
        ws.cell(row=i, column=1, value=rot)
        ws.cell(row=i, column=2, value=f)
    ws.column_dimensions["A"].width = 42
    ws.column_dimensions["B"].width = 12


def gerar(dados: dict, destino: Path) -> Path:
    destino = proteger_escrita(destino)
    wb = Workbook()
    linhas = dados["processos"]
    _folha_processos(wb, linhas)
    _folha_evidencias(wb, linhas)
    _folha_pendencias(wb, linhas)
    _folha_perguntas(wb)
    _folha_resumo(wb, len(linhas) + 1)
    wb.save(destino)
    return destino
