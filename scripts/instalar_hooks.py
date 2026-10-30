"""Instala os ganchos pre-commit e commit-msg que chamam scripts/scan.py."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
HOOKS = RAIZ / ".git" / "hooks"
CORPO = '#!/bin/sh\nexec python "$(git rev-parse --show-toplevel)/scripts/scan.py" {modo} "$@"\n'

if not HOOKS.exists():
    raise SystemExit("Rode 'git init' antes.")
for modo in ("pre-commit", "commit-msg"):
    (HOOKS / modo).write_text(CORPO.format(modo=modo), encoding="utf-8", newline="\n")
print("ganchos instalados:", ", ".join(("pre-commit", "commit-msg")))
