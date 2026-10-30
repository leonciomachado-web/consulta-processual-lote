"""Localização da pasta de dados e recusa de gravar dentro de repositório.

O programa nunca guarda dado de processo no repositório. A pasta de dados vem da
variável CONSULTA_LOTE_DADOS (ou do argumento --dados) e precisa estar fora da
árvore deste programa. Se estiver dentro de outro repositório git, precisa estar
ignorada por ele. Na dúvida, o programa recusa (falha fechada).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

VARIAVEL = "CONSULTA_LOTE_DADOS"
RAIZ_DO_PROGRAMA = Path(__file__).resolve().parents[2]


class DadosDirInvalido(RuntimeError):
    """A pasta de dados não pode ser usada."""


def _dentro(filho: Path, pai: Path) -> bool:
    try:
        filho.relative_to(pai)
        return True
    except ValueError:
        return False


def _raiz_git(p: Path) -> Path | None:
    for cand in [p, *p.parents]:
        if (cand / ".git").exists():
            return cand
    return None


ARTEFATOS = (
    ".dados-locais", "base.sqlite", "segredo.local", "saida/x.csv", "saida/x.xlsx", "original/x.xlsx",
    "entrada/x.txt", "datajud/x.json", "partes_alvo.local.yaml", "datajud.local.yaml",
    "analises/x/blocos/x.md", "analises/x/blocos/versoes/x.md", "documentos/x/x.txt", "documentos/x/x.pdf",
)


def _ignorado_pelo_git(raiz: Path, p: Path) -> bool:
    """Todos os arquivos que o programa grava precisam estar ignorados, não só a pasta."""
    for nome in ARTEFATOS:
        try:
            r = subprocess.run(
                ["git", "-C", str(raiz), "check-ignore", "-q", str(p / nome)],
                capture_output=True,
                timeout=20,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False  # sem git para conferir: recusa
        if r.returncode != 0:
            return False
    return True


def garantir_fora_do_repo(p: Path) -> None:
    if _dentro(p, RAIZ_DO_PROGRAMA):
        raise DadosDirInvalido(
            f"A pasta de dados ({p}) está dentro do repositório do programa. "
            "Escolha uma pasta fora dele."
        )
    raiz = _raiz_git(p)
    if raiz is not None and not _ignorado_pelo_git(raiz, p):
        raise DadosDirInvalido(
            f"A pasta de dados ({p}) está dentro do repositório git {raiz} e não é "
            "ignorada por ele. Escolha outra pasta ou ignore-a no .gitignore."
        )


def dados_dir(valor: str | os.PathLike | None = None, criar: bool = True) -> Path:
    bruto = valor or os.environ.get(VARIAVEL)
    if not bruto:
        raise DadosDirInvalido(
            f"Defina a pasta de dados com --dados ou com a variável {VARIAVEL}."
        )
    p = Path(bruto).expanduser().resolve()
    garantir_fora_do_repo(p)
    if criar:
        p.mkdir(parents=True, exist_ok=True)
    return p


def proteger_escrita(destino: Path) -> Path:
    """Chame antes de gravar qualquer arquivo. Recusa caminho dentro do programa."""
    d = destino.resolve()
    if _dentro(d, RAIZ_DO_PROGRAMA):
        raise DadosDirInvalido(f"Recusei gravar dentro do repositório do programa: {d}")
    return d
