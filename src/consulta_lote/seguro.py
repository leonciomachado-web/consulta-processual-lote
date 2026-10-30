"""Neutraliza texto que planilhas interpretam como fórmula (injeção de fórmula)."""
from __future__ import annotations

PERIGOSOS = ("=", "+", "-", "@", "\t", "\r")


def neutraliza(valor):
    """Prefixa apóstrofo em texto que começa com caractere de fórmula. Não altera números."""
    if isinstance(valor, str) and valor.startswith(PERIGOSOS):
        return "'" + valor
    return valor
