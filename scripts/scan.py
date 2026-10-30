"""Varredura de termos proibidos e de números de processo antes de commit.

Uso (os ganchos do git chamam isto; veja instalar_hooks.py):
  python scripts/scan.py pre-commit          # diff em stage + nome do ramo
  python scripts/scan.py commit-msg ARQUIVO  # mensagem do commit
  python scripts/scan.py historico           # todo o histórico, todos os ramos

Falha fechada: se a lista local de termos não existir, bloqueia.
A lista fica em termos_proibidos.local.txt (ignorada pelo git) ou no arquivo apontado por
CONSULTA_LOTE_TERMOS. Um termo por linha; linha com # é comentário.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CNJ = re.compile(r"\d{7}\D{0,2}\d{2}\D{0,2}\d{4}\D{0,2}\d\D{0,2}\d{2}\D{0,2}\d{4}")
EXTENSOES_PROIBIDAS = {".xlsx", ".xls", ".csv", ".pdf", ".docx", ".sqlite", ".db", ".html", ".log"}


def termos() -> list[str]:
    arq = Path(os.environ.get("CONSULTA_LOTE_TERMOS") or RAIZ / "termos_proibidos.local.txt")
    if not arq.exists():
        sys.stderr.write(
            f"BLOQUEADO: lista de termos proibidos não encontrada ({arq}).\n"
            "Crie termos_proibidos.local.txt (copie de scripts/termos_proibidos.example.txt) "
            "com nomes de cliente, partes, escritório e advogados.\n"
        )
        raise SystemExit(1)
    out = [l.strip().lower() for l in arq.read_text(encoding="utf-8").splitlines()]
    return [t for t in out if t and not t.startswith("#")]


def cnj_ficticio(achado: str) -> bool:
    d = re.sub(r"\D", "", achado)
    return len(d) == 20 and d[14:16] == "99" and d[16:] == "0000"


def varre(texto: str, onde: str, lista: list[str]) -> list[str]:
    achados: list[str] = []
    baixo = texto.lower()
    for t in lista:
        if t in baixo:
            achados.append(f"{onde}: termo proibido '{t}'")
    for m in CNJ.finditer(texto):
        if not cnj_ficticio(m.group(0)):
            achados.append(f"{onde}: número de processo (não fictício)")
    return achados


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(RAIZ), "-c", "core.quotepath=off", *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", check=True).stdout


def git_bytes(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(RAIZ), "-c", "core.quotepath=off", *args], capture_output=True,
                          check=True).stdout


def arquivos_em_stage() -> list[str]:
    """Nomes separados por NUL (sem aspas nem escape), sem arquivos apagados."""
    bruto = git_bytes("diff", "--cached", "--name-only", "--diff-filter=d", "-z")
    return [n.decode("utf-8", "replace") for n in bruto.split(chr(0).encode()) if n]


def pre_commit(lista: list[str]) -> list[str]:
    achados: list[str] = []
    for nome in arquivos_em_stage():
        sufixo = Path(nome.strip()).suffix.strip().lower()
        if sufixo in EXTENSOES_PROIBIDAS:
            achados.append(f"{nome}: tipo de arquivo que pode conter dado de processo")
        achados += varre(nome, f"nome de arquivo {nome}", lista)
        conteudo = git_bytes("show", f":{nome}")  # o que será de fato commitado
        if chr(0).encode() in conteudo:
            achados.append(f"{nome}: arquivo binário não é permitido")
            continue
        achados += varre(conteudo.decode("utf-8", "replace"), f"conteúdo de {nome}", lista)
    try:
        achados += varre(git("rev-parse", "--abbrev-ref", "HEAD"), "nome do ramo", lista)
    except subprocess.CalledProcessError:
        pass
    return achados


def historico(lista: list[str]) -> list[str]:
    log = git("log", "--all", "-p", "--format=%H%n%an%n%ae%n%s%n%b")
    return varre(log, "histórico", lista)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    modo = sys.argv[1]
    lista = termos()
    if modo == "pre-commit":
        achados = pre_commit(lista)
    elif modo == "commit-msg":
        achados = varre(Path(sys.argv[2]).read_text(encoding="utf-8", errors="replace"), "mensagem do commit", lista)
    elif modo == "historico":
        achados = historico(lista)
    else:
        print(__doc__)
        return 2
    if achados:
        sys.stderr.write("BLOQUEADO pela varredura:\n  " + "\n  ".join(sorted(set(achados))) + "\n")
        return 1
    print(f"varredura limpa ({modo})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
