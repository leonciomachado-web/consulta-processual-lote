"""Linha de comando: python -m consulta_lote <comando>.

Comandos:
  init       cria a pasta de dados local (fora do repositório) e os modelos de configuração
  limpar     lê a planilha de entrada, separa elegíveis e excluídos, sorteia o piloto
  importar   lê arquivos .txt colados da tela, extrai os campos e grava no banco local
  planilha   gera a planilha .xlsx para a equipe
  verificar  confere o banco: SIM ou NAO sem evidência, evidência que não confere
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path

import yaml

from . import campos as campos_mod
from . import blocos, datajud, db, lista, parser, planilha
from .config import RAIZ_DO_PROGRAMA, DadosDirInvalido, dados_dir, proteger_escrita


def _yaml(caminho: Path) -> dict:
    return yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}


def cmd_init(a) -> int:
    d = dados_dir(a.dados)
    db.segredo_local(d)
    for sub in ("entrada", "original", "saida"):
        proteger_escrita(d / sub).mkdir(exist_ok=True)
    for nome in ("partes_alvo", "mapa_planilha"):
        dest = d / f"{nome}.local.yaml"
        ex = RAIZ_DO_PROGRAMA / "examples" / f"{nome}.example.yaml"
        if not dest.exists() and ex.exists():
            shutil.copy(ex, dest)
    print(f"Pasta de dados pronta: {d}")
    print("Edite partes_alvo.local.yaml e mapa_planilha.local.yaml com os dados reais (ficam só aqui).")
    return 0


def cmd_limpar(a) -> int:
    d = dados_dir(a.dados)
    mapa_cfg = _yaml(d / "mapa_planilha.local.yaml")
    origem = Path(a.planilha)
    copia = proteger_escrita(d / "original" / origem.name)
    if not copia.exists():
        shutil.copy2(origem, copia)  # a original não é tocada; trabalha-se na cópia
    linhas = lista.ler_planilha(copia, mapa_cfg["colunas"], mapa_cfg.get("aba"))
    eleg, excl, alertas = lista.classificar(linhas, mapa_cfg.get("regras", {}))
    saida = d / "saida"
    lista.gravar_csv(saida / "elegiveis.csv", ["linha", "numero", "fase_base", "tipo_pasta", "rito"],
                     [[l.n, l.cnj.formatado, l.atributos.get("fase_base", ""), l.atributos.get("tipo_pasta", ""),
                       l.atributos.get("rito", "")] for l in eleg])
    lista.gravar_csv(saida / "excluidos.csv", ["linha", "numero_bruto", "motivo"],
                     [[l.n, l.cnj_bruto, m] for l, m in excl])
    lista.gravar_csv(saida / "alertas.csv", ["linha", "numero", "alerta"],
                     [[l.n, l.cnj.formatado, m] for l, m in alertas])
    r = lista.resumo(eleg, excl, alertas)
    piloto_cfg = mapa_cfg.get("piloto")
    if piloto_cfg:
        sel = lista.sortear_piloto(eleg, piloto_cfg["quotas"], piloto_cfg["semente"], piloto_cfg.get("incluir"))
        lista.gravar_csv(saida / "piloto.csv", ["linha", "numero", "fase_base", "estrato"],
                         [[l.n, l.cnj.formatado, l.atributos.get("fase_base", ""),
                           lista.categoria_fase(l.atributos.get("fase_base", ""))] for l in sel])
        r["piloto"] = len(sel)
        r["semente"] = piloto_cfg["semente"]
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0


def _carregar_documentos(d: Path, proc) -> int:
    """Lê dados/documentos/<numero>/*.txt (um por documento do processo, já convertido).
    O arquivo do processo inteiro não entra: a análise usa os documentos separados."""
    pasta = d / "documentos" / proc.cnj.formatado
    n = 0
    if not pasta.is_dir():
        return 0
    # Sigilo falha fechado: só entra documento com sigilo explicitamente 0 (público). Valor ilegível
    # ou diferente de 0 é tratado como não público. Cabeçalho ausente fica "nao_testado".
    completo = pasta / "processo-completo.txt"
    niveis_proc = _niveis_de_sigilo(completo.read_text(encoding="utf-8")) if completo.exists() else []
    if any(not _e_publico(v) for v in niveis_proc):
        print(f"  pulei todos os documentos de {proc.cnj.formatado}: o processo não tem sigilo 0 (público)")
        return 0
    processo_publico = bool(niveis_proc)
    for arq in sorted(pasta.glob("*.txt")):
        if arq.stem == "processo-completo":
            continue
        texto = arq.read_text(encoding="utf-8")
        niveis = _niveis_de_sigilo(texto)
        if any(not _e_publico(v) for v in niveis):
            print(f"  pulei {arq.name}: sigilo não é 0 (público)")
            continue
        if niveis or processo_publico:
            acesso = "restrito_login_ou_senha"  # sigilo 0 confirmado, obtido com login
        else:
            acesso = "nao_testado"
            print(f"  atenção: {arq.name} sem cabeçalho de sigilo; carregado como nao_testado (confirmar à mão)")
        proc.documentos.append(parser.Documento(rotulo=arq.stem, texto=texto, acesso=acesso))
        n += 1
    return n


_SIGILO_VALOR = re.compile("sigilo" + "\s*:[ " + chr(9) + "]*([^" + chr(10) + "]*)")
_SIGILO_ROTULO = re.compile("nivel" + "\s+de\s+sigilo")
# valor aceito como público: exatamente "0", "0 (publico)", "0 - publico" ou "publico"
_VALOR_PUBLICO = re.compile("0([ ]*[-]?[ ]*[(]?publico[)]?)?|publico")


def _normaliza(texto: str) -> str:
    """NFKC (espaço sem quebra vira espaço), sem acento, minúsculas."""
    t = unicodedata.normalize("NFKC", texto)
    t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))
    return t.lower()


def _niveis_de_sigilo(texto: str) -> list[str]:
    """Valor escrito depois de 'sigilo:' em cada ocorrência (qualquer espaço ou quebra antes dos dois-pontos).
    Rótulo sem valor na mesma linha só aceita a linha seguinte se ela for, inteira, um valor público
    estrito; senão entra como string vazia (não público). Rótulo 'nivel de sigilo' sem nenhum valor
    legível também conta como não público."""
    n = _normaliza(texto)
    linhas_pos = [(m.start(), m.end(), m.group(1).strip()) for m in _SIGILO_VALOR.finditer(n)]
    valores: list[str] = []
    for ini, fim, v in linhas_pos:
        if not v:
            resto = n[fim:].lstrip(chr(10)).split(chr(10), 1)[0].strip() if n[fim:fim + 1] == chr(10) else ""
            seguinte = n[fim + 1:].split(chr(10), 1)[0].strip() if n[fim:fim + 1] == chr(10) else ""
            v = seguinte if _VALOR_PUBLICO.fullmatch(seguinte) else ""
        valores.append(v)
    faltam = len(_SIGILO_ROTULO.findall(n)) - len(valores)
    valores.extend([""] * max(0, faltam))
    return valores


def _e_publico(valor: str) -> bool:
    return _VALOR_PUBLICO.fullmatch(_normaliza(valor).strip()) is not None


def cmd_importar(a) -> int:
    d = dados_dir(a.dados)
    alvo = _yaml(d / "partes_alvo.local.yaml").get("partes_alvo", [])
    con = db.abrir(d)
    n = 0
    for arq in a.arquivos:
        p = Path(arq)
        proc = parser.ler(p.read_text(encoding="utf-8"))
        if proc.cnj is None:
            print(f"[{p.name}] sem número de processo reconhecível; pulei")
            continue
        ndocs = _carregar_documentos(d, proc)
        cs = campos_mod.extrair(proc, alvo)
        h = db.gravar(con, d, proc.cnj, proc.sistema, proc.meta.get("data_consulta", ""),
                      proc.meta.get("fase_base"), p.name, cs)
        n += 1
        res = {c.campo: c.estado for c in cs}
        print(f"[{p.name}] {proc.cnj.formatado} hash={h} documentos={ndocs}")
        for c in cs:
            print(f"   {c.campo:32} {c.estado}" + (f" ({c.motivo})" if c.motivo else "") + (f" | {c.valor}" if c.valor else ""))
    print(f"{n} processo(s) importado(s).")
    return 0


def cmd_datajud(a) -> int:
    from .cnj import tratar, hash_do_processo
    d = dados_dir(a.dados)
    cfg = _yaml(d / "datajud.local.yaml")
    chave, alias = cfg["chave"], cfg["alias"]
    if a.numeros:
        nums = list(a.numeros)
    else:
        import csv
        with open(d / "saida" / "piloto.csv", encoding="utf-8-sig") as f:
            nums = [r["numero"] for r in csv.DictReader(f, delimiter=";")]
    pasta = proteger_escrita(d / "datajud")
    pasta.mkdir(exist_ok=True)
    con = db.abrir(d)
    seg = db.segredo_local(d)
    achou = 0
    for n in nums:
        c = tratar(n)
        if c is None:
            print(f"{n}: número inválido, pulei")
            continue
        h = hash_do_processo(c, seg)
        try:
            resp = datajud.consultar_e_guardar(c, chave, alias, pasta, h)
        except Exception as e:  # rede, chave, limite: para e reporta, não insiste
            print(f"PAROU em {c.formatado}: {type(e).__name__}: {e}", file=sys.stderr)
            return 3
        db.gravar_extra(con, d, c, datajud.campos_do_datajud(resp))
        r = datajud.resumo(resp)
        achou += 1 if r["encontrado"] else 0
        print(f"{c.formatado} {h} encontrado={r['encontrado']} movimentos={r.get('movimentos')} sistema_datajud={r.get('sistema_no_datajud')}")
    print(f"{achou}/{len(nums)} encontrados no DataJud.")
    return 0


def cmd_blocos(a) -> int:
    from .cnj import tratar
    d = dados_dir(a.dados)
    alvo = _yaml(d / "partes_alvo.local.yaml").get("partes_alvo", [])
    arq = Path(a.arquivo)
    proc = parser.ler(arq.read_text(encoding="utf-8"))
    if proc.cnj is None:
        print("sem número de processo reconhecível")
        return 1
    _carregar_documentos(d, proc)
    cs = campos_mod.extrair(proc, alvo)
    pasta = d / "analises" / proc.cnj.formatado / "blocos"
    for f in blocos.gerar(proc, cs, pasta):
        print(f)
    return 0


def cmd_planilha(a) -> int:
    d = dados_dir(a.dados)
    con = db.abrir(d)
    destino = Path(a.saida) if a.saida else d / "saida" / "planilha-equipe.xlsx"
    print(planilha.gerar(con, destino, incluir_trechos_restritos=not a.sem_trechos_restritos))
    return 0


def cmd_verificar(a) -> int:
    d = dados_dir(a.dados)
    con = db.abrir(d)
    sem_ev = con.execute(
        "SELECT count(*) FROM campo WHERE estado IN ('SIM','NAO') AND length(coalesce(evidencia_literal,''))=0"
    ).fetchone()[0]
    nao_confere = con.execute("SELECT count(*) FROM campo WHERE evidencia_confere=0").fetchone()[0]
    por_estado = dict(con.execute("SELECT estado, count(*) FROM campo GROUP BY estado").fetchall())
    por_motivo = dict(con.execute(
        "SELECT motivo_nao_visivel, count(*) FROM campo WHERE estado!='SIM' AND estado!='NAO' GROUP BY 1").fetchall())
    print(json.dumps({"SIM_ou_NAO_sem_evidencia": sem_ev, "evidencia_nao_confere": nao_confere,
                      "campos_por_estado": por_estado, "nao_visivel_por_motivo": por_motivo},
                     ensure_ascii=False, indent=2))
    return 0 if sem_ev == 0 and nao_confere == 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="consulta_lote", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dados", help="pasta de dados local (ou variável CONSULTA_LOTE_DADOS)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(f=cmd_init)
    s = sub.add_parser("limpar")
    s.add_argument("planilha")
    s.set_defaults(f=cmd_limpar)
    s = sub.add_parser("importar")
    s.add_argument("arquivos", nargs="+")
    s.set_defaults(f=cmd_importar)
    s = sub.add_parser("planilha")
    s.add_argument("--saida")
    s.add_argument("--sem-trechos-restritos", action="store_true",
                   help="omite o trecho literal de documentos obtidos com login (mostra só o estado)")
    s.set_defaults(f=cmd_planilha)
    sub.add_parser("verificar").set_defaults(f=cmd_verificar)
    s = sub.add_parser("blocos")
    s.add_argument("arquivo", help="texto colado do processo (.txt)")
    s.set_defaults(f=cmd_blocos)
    s = sub.add_parser("datajud")
    s.add_argument("numeros", nargs="*", help="números a consultar; sem argumento, usa o piloto.csv")
    s.set_defaults(f=cmd_datajud)
    a = ap.parse_args(argv)
    try:
        return a.f(a)
    except DadosDirInvalido as e:
        print(f"RECUSADO: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
