"""Número único de processo (padrão de 20 dígitos, com dígito verificador módulo 97)."""
from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass

_SO_DIGITOS = re.compile(r"\D+")
PADRAO = re.compile(r"(\d{7})-?(\d{2})\.?(\d{4})\.?(\d)\.?(\d{2})\.?(\d{4})")


@dataclass(frozen=True)
class Cnj:
    sequencial: str
    dv: str
    ano: str
    justica: str
    tribunal: str
    origem: str

    @property
    def digitos(self) -> str:
        return f"{self.sequencial}{self.dv}{self.ano}{self.justica}{self.tribunal}{self.origem}"

    @property
    def formatado(self) -> str:
        return (
            f"{self.sequencial}-{self.dv}.{self.ano}.{self.justica}."
            f"{self.tribunal}.{self.origem}"
        )

    @property
    def jtr(self) -> str:
        return f"{self.justica}.{self.tribunal}"

    @property
    def dv_confere(self) -> bool:
        base = f"{self.sequencial}{self.ano}{self.justica}{self.tribunal}{self.origem}00"
        return int(self.dv) == 98 - (int(base) % 97)


def tratar(texto: str | None) -> Cnj | None:
    """Aceita espaço sobrando, com ou sem pontuação. Devolve None se não for CNJ."""
    if not texto:
        return None
    t = str(texto).strip()
    m = PADRAO.fullmatch(t)
    if m is None:
        so = _SO_DIGITOS.sub("", t)
        if len(so) != 20:
            return None
        m = PADRAO.fullmatch(so)
        if m is None:
            return None
    return Cnj(*m.groups())


def hash_do_processo(cnj: Cnj, segredo: bytes) -> str:
    """HMAC com segredo local. Hash simples de número é reversível por força bruta."""
    return hmac.new(segredo, cnj.digitos.encode(), hashlib.sha256).hexdigest()[:16]
