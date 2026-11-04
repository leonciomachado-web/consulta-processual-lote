"""Converte o que o coletor gravou em entradas do programa (dados/entrada/<CNJ>.txt) e peças
(dados/documentos/<CNJ>/*.txt). Não importa nada: depois rode `importar` com a lista impressa.

A lista de processos vem de <dados>/saida/elegiveis.csv (gerado por `limpar`; separador ";",
colunas `numero` e `fase_base`). Número fora da lista é pulado.

Uso: python -I coletor/converter.py --dados <pasta-fora-do-repo> <modo> [arquivos ou números]

Modos
  eproc | pje | legado   leem o que o receptor gravou em <dados>/entrada/_recebido/<CNJ>.txt
                         (e _recebido_docs/<CNJ>.json, quando houver). Sem números: converte todos os
                         que ainda não têm entrada/<CNJ>.txt.
                         - legado: o texto precisa ter as marcas `=== PERSONAGENS (modal) ===` e
                           `=== CAPA E MOVIMENTOS` (o laço as escreve entre capa, modal e movimentos).
  pje-publico  <json>... despejo da consulta pública do PJe: {cnj: {capa, movs[], docs[{rot, texto}], erro?}}
                         `movs` são linhas "dd/mm/aaaa hh:mm:ss - texto"; `capa` traz as partes como
                         "NOME - CPF: ... (PAPEL)".
  eproc-despejo <json>... despejo do eproc: {cnj: texto da tela}. Segredo de justiça (eventos vazios)
                         vai para saida/sigilosos.txt e não vira entrada.
  pecas-eproc  <json>... {cnj: [{ev, label, text, erro?}]} -> documentos/<cnj>/ev<ev>-<tipo><n>.txt
"""
import argparse
import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

NL = chr(10)
CNJ = re.compile(r"^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$")
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
LIMPA = re.compile("[⁦-⁩​-‏]")   # marcas invisíveis de direção de texto
DATA_PJE = re.compile(r"(?m)^\d{1,2} (jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez) \d{4}$")
LINHA_MOV = re.compile(r"^(\d{2})/(\d{2})/(\d{4}) (\d{2}:\d{2}):\d{2} - (.*)$", re.S)
PARTE = re.compile(r"([^\n\t]+?) - (?:CPF|CNPJ): [^\n(]*\(([^)\n]+)\)")
TIPO_PECA = {"senten": "sentenca", "acórd": "acordao", "acord": "acordao", "decis": "decisao", "despach": "despacho",
             "certid": "certidao", "laudo": "laudo", "termo": "termo", "ata": "ata", "parecer": "parecer",
             "transa": "transacao"}
ROTULO_EPROC = {"SENT": "sentenca", "DEC": "decisao", "ACOR": "acordao", "RELVOTO": "relatorio",
                "TERMOAUD": "termoaud", "LAUDO": "laudo"}


def limpa(s):
    return LIMPA.sub("", s or "")


def compacta(t):
    return re.sub(r"\n{3,}", NL + NL, t).strip() + NL


def carrega_base(dados):
    base = {}
    with open(dados / "saida" / "elegiveis.csv", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f, delimiter=";"):
            base[r["numero"]] = r.get("fase_base", "")
    return base


def cabecalho(sistema, n, base, data, extra=()):
    linhas = [f"#! sistema: {sistema}", f"#! cnj: {n}", f"#! data_consulta: {data}", f"#! fase_base: {base[n]}",
              *extra, "#! movimentos_lista_completa: sim"]
    return NL.join(linhas) + NL + NL


def carrega_json(caminho):
    """Lê um despejo JSON; ignora lixo antes do primeiro `{` (a ferramenta do navegador às vezes põe um prefixo)."""
    raw = Path(caminho).read_text(encoding="utf-8")
    return json.loads(raw[max(raw.find("{"), 0):])


def json_possivelmente_duplo(caminho):
    """Alguns sistemas reescrevem JSON.stringify: o corpo chega como JSON dentro de string."""
    d = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return json.loads(d) if isinstance(d, str) else d


def grava_docs_eproc(dados, n, docs):
    pasta = dados / "documentos" / n
    k = ruins = 0
    for x in docs:
        t = limpa(x.get("text")).strip()
        if not t or x.get("erro"):
            ruins += 1
            continue
        lab = re.sub(r"[^A-Za-z0-9]", "", x.get("label", ""))
        nome = ROTULO_EPROC.get(re.sub(r"\d+$", "", lab), "outros")
        num = re.sub(r"\D", "", lab)
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / f"ev{x['ev']}-{nome}{num}.txt").write_text(compacta(t), encoding="utf-8", newline=NL)
        k += 1
    return k, ruins


def grava_docs_pje(dados, n, docs):
    """Peças do PJe vistas pela pessoa logada: [{lab: "<id> - <Tipo>", text, pdf?}]. PDF sem texto é pulado."""
    pasta = dados / "documentos" / n
    k = 0
    for x in docs:
        if x.get("pdf") or not x.get("text"):
            continue
        m = re.match(r"(\d{6,}) - (.+)", x.get("lab", ""))
        if not m:
            continue
        tipo = m.group(2).lower()
        nome = next((v for kk, v in TIPO_PECA.items() if tipo.startswith(kk)), re.sub(r"[^a-z0-9]", "", tipo)[:12] or "doc")
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / f"{m.group(1)}-{nome}.txt").write_text(compacta(limpa(x["text"])), encoding="utf-8", newline=NL)
        k += 1
    return k


def converte_tela(dados, sistema, numeros, base, data):
    """Texto da tela gravado pelo receptor -> entrada/<CNJ>.txt (+ peças)."""
    rec, recd = dados / "entrada" / "_recebido", dados / "entrada" / "_recebido_docs"
    alvo = numeros or sorted(p.stem for p in rec.glob("*.txt")
                             if CNJ.match(p.stem) and not (dados / "entrada" / f"{p.stem}.txt").exists())
    feitos, pulados, pecas = [], [], 0
    for n in alvo:
        arq = rec / f"{n}.txt"
        if not arq.exists() or n not in base:
            pulados.append(n)
            continue
        tl, extra = limpa(arq.read_text(encoding="utf-8")), []
        if sistema == "pje":
            m = DATA_PJE.search(tl)
            if not m:
                pulados.append(n)
                continue
            pedacos = [x.strip() for x in re.split(r"\s\|\s|\n", tl[: m.start()]) if x.strip()]
            topo = ""
            for i, x in enumerate(pedacos[:-1]):   # linha "Classe NNNNNNN-DD..." seguida de "AUTOR X RÉU"
                if re.match(r"^[A-Za-zÀ-ÿ]{2,20} \d{7}-\d{2}\.", x) and " X " in pedacos[i + 1]:
                    topo = x + NL + pedacos[i + 1]
                    break
            corpo = (topo + NL + NL if topo else "") + tl[m.start():]
        elif sistema == "legado":
            a, b = tl.find("=== PERSONAGENS (modal) ==="), tl.find("=== CAPA E MOVIMENTOS")
            if a < 0 or b < 0 or n not in tl:
                pulados.append(n)
                continue
            pers = tl[a + len("=== PERSONAGENS (modal) ==="):b].strip()
            i = pers.find("TipoPersonagem")
            linhas = ([x.strip() for x in re.split(r"\s{2,}", pers[i + len("TipoPersonagem"):].strip()) if x.strip()]
                      if i >= 0 else [])
            modal = NL.join(["Todos os Personagens", "Tipo", "Personagem"] + linhas) if linhas else ""
            corpo = "=== PERSONAGENS (modal) ===" + NL + modal + NL + tl[b:]
            extra = ["#! partes_lista_completa: sim"] if linhas else []
        else:   # eproc
            if len(tl) < 800 or n not in tl:
                pulados.append(n)
                continue
            corpo = tl
        (dados / "entrada" / f"{n}.txt").write_text(cabecalho(sistema, n, base, data, extra) + corpo,
                                                    encoding="utf-8", newline=NL)
        j = recd / f"{n}.json"
        if j.exists():
            docs = json_possivelmente_duplo(j)
            pecas += grava_docs_pje(dados, n, docs) if sistema == "pje" else grava_docs_eproc(dados, n, docs)[0]
        feitos.append(n)
    return feitos, pulados, pecas, []


def topo_pje_publico(n, capa):
    autores, reus = [], []
    for nome, papel in PARTE.findall(capa):
        p = papel.upper()
        if "ADVOGADO" in p or "PERITO" in p:
            continue
        (autores if any(k in p for k in ("AUTOR", "REQUERENTE", "EXEQUENTE")) else reus).append(nome.strip())
    a = autores[0] + (" e outros" if len(autores) > 1 else "") if autores else "?"
    r = reus[0] + (" e outros" if len(reus) > 1 else "") if reus else "?"
    return f"Processo {n}" + NL + f"{a} X {r}" + NL + NL


def linha_do_tempo(movs):
    """'dd/mm/aaaa hh:mm:ss - texto' -> blocos 'dd mês aaaa' / texto / hh:mm (formato do parser do PJe)."""
    saida, data, tem_ultimo = [], None, False
    for linha in movs:
        linha = limpa(linha).strip()
        m = LINHA_MOV.match(linha)
        if not m:
            if saida and tem_ultimo:   # continuação da linha anterior: entra antes da hora
                saida.insert(len(saida) - 1, linha)
            continue
        d = f"{int(m.group(1)):02d} {MESES[int(m.group(2)) - 1]} {m.group(3)}"
        if d != data:
            saida.append(d)
            data = d
        saida += [m.group(5).strip(), m.group(4)]
        tem_ultimo = True
    return NL.join(saida) + NL


def docs_pje_publico(dados, n, docs):
    pasta = dados / "documentos" / n
    k = 0
    for i, x in enumerate(docs):
        t = limpa(x.get("texto"))
        if not t.strip() or t.startswith("ERRO"):
            continue
        rot = x.get("rot", "").lower().split(" - ")[-1]
        nome = next((v for kk, v in TIPO_PECA.items() if kk in rot), "doc")
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / f"doc{i + 1}-{nome}.txt").write_text(compacta(t), encoding="utf-8", newline=NL)
        k += 1
    return k


def converte_despejo(dados, modo, arquivos, base, data):
    feitos, pulados, pecas, sigilo = [], [], 0, []
    for arq in arquivos:
        for n, v in carrega_json(arq).items():
            if n not in base:
                pulados.append(n)
                continue
            if modo == "eproc-despejo":
                if len(v) < 2500 and "Segredo de Justi" in v:
                    sigilo.append(n)
                    continue
                if len(v) < 800 or n not in v:
                    pulados.append(n)
                    continue
                sistema, corpo = "eproc", limpa(v)
            else:
                if v.get("erro") or not v.get("movs"):
                    pulados.append(n)
                    continue
                sistema, corpo = "pje", topo_pje_publico(n, v.get("capa", "")) + linha_do_tempo(v["movs"])
                pecas += docs_pje_publico(dados, n, v.get("docs", []))
            (dados / "entrada" / f"{n}.txt").write_text(cabecalho(sistema, n, base, data) + corpo,
                                                        encoding="utf-8", newline=NL)
            feitos.append(n)
    return feitos, pulados, pecas, sigilo


def converte_pecas_eproc(dados, arquivos):
    k = ruins = 0
    for arq in arquivos:
        for n, lista in carrega_json(arq).items():
            a, b = grava_docs_eproc(dados, n, lista)
            k, ruins = k + a, ruins + b
    print(f"peças gravadas {k} | sem texto {ruins}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dados", required=True, type=Path)
    ap.add_argument("--data", default=date.today().isoformat(), help="data da consulta (padrão: hoje)")
    ap.add_argument("modo", choices=["eproc", "pje", "legado", "pje-publico", "eproc-despejo", "pecas-eproc"])
    ap.add_argument("itens", nargs="*", help="números CNJ (modos de tela) ou arquivos JSON (modos de despejo)")
    a = ap.parse_args()
    dados = a.dados.resolve()
    repo = Path(__file__).resolve().parent.parent
    if dados == repo or repo in dados.parents:
        raise SystemExit("A pasta de dados não pode ficar dentro do repositório.")
    (dados / "entrada").mkdir(parents=True, exist_ok=True)
    if a.modo == "pecas-eproc":
        converte_pecas_eproc(dados, a.itens)
        return 0
    base = carrega_base(dados)
    if a.modo in ("eproc", "pje", "legado"):
        feitos, pulados, pecas, sigilo = converte_tela(dados, a.modo, a.itens, base, a.data)
    else:
        feitos, pulados, pecas, sigilo = converte_despejo(dados, a.modo, a.itens, base, a.data)
    (dados / "entrada" / "lista-convertidos.txt").write_text(
        NL.join(str(dados / "entrada" / f"{n}.txt") for n in feitos) + NL, encoding="utf-8")
    print(f"convertidos {len(feitos)} | pulados {len(pulados)} | peças {pecas}")
    if pulados:
        print("pulados:", pulados[:10])
    if sigilo:
        (dados / "saida").mkdir(exist_ok=True)
        (dados / "saida" / "sigilosos.txt").write_text(NL.join(sorted(set(sigilo))) + NL, encoding="utf-8", newline=NL)
        print("sigilosos (segredo de justiça, sem eventos visíveis):", len(sigilo))
    print("Importe com a lista em entrada/lista-convertidos.txt (um arquivo por linha).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
