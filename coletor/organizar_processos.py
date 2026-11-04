"""Organiza a pasta de dados em processos/<CNJ>/ (fontes, convertido, analises, _MAPA-CASO.md).

Copia, nunca move nem apaga. Padrão: simulação. Use --gravar para executar.
Lê o banco do programa em modo somente leitura.

Uso: python -I coletor/organizar_processos.py --dados <pasta-fora-do-repo> [--gravar]
"""
import argparse
import json
import pathlib
import re
import shutil
import sqlite3

CNJ = re.compile(r"[0-9]{7}-[0-9]{2}\.[0-9]{4}\.[0-9]\.[0-9]{2}\.[0-9]{4}")


def coletar(dados, dest):
    itens = {}
    novo = lambda: {"tela": None, "pecas": [], "pdfs": []}
    entrada = dados / "entrada"
    if entrada.is_dir():
        for f in entrada.glob("*.txt"):
            if CNJ.fullmatch(f.stem):
                itens.setdefault(f.stem, novo())["tela"] = f
    docs = dados / "documentos"
    if docs.is_dir():
        for d in docs.iterdir():
            if d.is_dir() and CNJ.fullmatch(d.name):
                itens.setdefault(d.name, novo())["pecas"] = sorted(d.glob("*.txt"))
    for d in dest.glob("*/fontes"):
        if CNJ.fullmatch(d.parent.name):
            itens.setdefault(d.parent.name, novo())["pdfs"] = sorted(d.glob("*.pdf"))
    return itens


def campos(dados, cnj):
    banco = dados / "base.sqlite"
    if not banco.exists():
        return []
    con = sqlite3.connect(f"file:{banco}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    linhas = con.execute(
        "select c.campo,c.estado,c.motivo_nao_visivel,c.valor,c.fonte,c.data_da_fonte,"
        "c.evidencia_literal,c.localizacao from campo c join processo p on p.hash=c.hash "
        "where p.cnj=? order by c.campo", (cnj,)).fetchall()
    con.close()
    return [dict(x) for x in linhas]


def mapa(cnj, e, cmp):
    sim = [c for c in cmp if c["estado"] == "SIM"]
    nv = [c for c in cmp if c["estado"] not in ("SIM", "NAO")]
    ids_pdf = {p.stem.split("-", 1)[0] for p in e["pdfs"]}
    sem_pdf = [p.name for p in e["pecas"] if p.stem.split("-", 1)[0] not in ids_pdf]
    L = [f"# _MAPA-CASO: processo {cnj}", "",
         "> Estado derivável do disco: em dúvida, o disco vence. Gerado por `coletor/organizar_processos.py`.", "",
         "## Fontes (PDF original)"]
    L += [f"- `fontes/{p.name}`" for p in e["pdfs"]] or ["- (nenhum PDF baixado)"]
    L += ["", "## Convertido (texto)"]
    L += ["- `convertido/00-texto-da-tela.txt`"] if e["tela"] else ["- (sem texto da tela)"]
    L += [f"- `convertido/{p.name}`" for p in e["pecas"]]
    L += ["", "## Análise (sugestão por regra; a revisão humana confirma)",
          f"- Campos com evidência literal (SIM): {len(sim)}",
          f"- Campos não visíveis no acesso público: {len(nv)}",
          "- Detalhe: `analises/campos.json`", "", "## Lacunas",
          f"- Peças só em texto, sem PDF original: {len(sem_pdf)}"]
    L += [f"- {c['campo']}: {c['motivo_nao_visivel'] or c['estado']}" for c in nv]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dados", required=True, type=pathlib.Path)
    ap.add_argument("--gravar", action="store_true")
    a = ap.parse_args()
    dados = a.dados.resolve()
    repo = pathlib.Path(__file__).resolve().parent.parent
    if dados == repo or repo in dados.parents:
        raise SystemExit("A pasta de dados não pode ficar dentro do repositório.")
    dest = dados / "processos"
    itens = coletar(dados, dest)
    arquivos = 0
    for cnj, e in sorted(itens.items()):
        cmp = campos(dados, cnj)
        raiz = dest / cnj
        if a.gravar:
            for sub in ("fontes", "convertido", "analises"):
                (raiz / sub).mkdir(parents=True, exist_ok=True)
            if e["tela"]:
                shutil.copy2(e["tela"], raiz / "convertido" / "00-texto-da-tela.txt")
            for p in e["pecas"]:
                shutil.copy2(p, raiz / "convertido" / p.name)
            (raiz / "analises" / "campos.json").write_text(
                json.dumps(cmp, ensure_ascii=False, indent=1), encoding="utf-8")
            (raiz / "_MAPA-CASO.md").write_text(mapa(cnj, e, cmp), encoding="utf-8")
        arquivos += len(e["pecas"]) + (1 if e["tela"] else 0)
    print(f"{'GRAVADO' if a.gravar else 'SIMULACAO'}: {len(itens)} processos, {arquivos} arquivos de texto")


if __name__ == "__main__":
    main()
