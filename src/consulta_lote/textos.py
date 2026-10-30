"""Normalização de texto usada nas regras (acento, caixa, espaço)."""
from __future__ import annotations

import re
import unicodedata


def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", sem_acento(s).lower()).strip()


def espaco(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()
