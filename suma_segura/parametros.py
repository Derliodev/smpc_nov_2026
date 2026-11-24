"""Perfiles públicos del caso E3, sección 3.

Estructura inmutable adaptada de clase_4.pdf, listado 4.1 (Julio Fenner).
Los plazos por defecto son unidades sintéticas del ensayo, no un SLA.
"""

from dataclasses import dataclass
from math import isfinite

from .shamir import validar_campo


@dataclass(frozen=True)
class Parametros:
    perfil: str
    n: int
    m: int
    M: int
    p: int
    umbral: int
    T: float = 10.0
    delta: float = 20.0

    def __post_init__(self):
        if self.perfil not in ("BASE", "UMBRAL"):
            raise ValueError("perfil desconocido")
        if any(type(v) is not int for v in (self.n, self.m, self.M, self.p, self.umbral)):
            raise ValueError("n, m, M, p y umbral deben ser enteros estrictos")
        if self.n < 2 or self.m < 2 or self.M < 0 or self.p < 2:
            raise ValueError("se requiere n>=2, m>=2, M>=0 y p>=2")
        if self.p <= self.n * self.M:
            raise ValueError("se requiere p > n*M")
        if any(type(v) not in (int, float) or not isfinite(v) for v in (self.T, self.delta)):
            raise ValueError("los plazos deben ser números finitos")
        if not 0 < self.T < self.delta:
            raise ValueError("se requiere 0 < T < delta")
        if self.perfil == "BASE" and self.umbral != self.m:
            raise ValueError("BASE requiere los m parciales")
        if self.perfil == "UMBRAL" and (self.m != 3 or self.umbral != 2):
            raise ValueError("UMBRAL está reservado para Shamir 2 de 3")
        if self.perfil == "UMBRAL":
            validar_campo(self.p)

    def validar(self):
        """Revalidar el contrato del perfil antes de abrir una sesión."""
        self.__post_init__()


BASE = Parametros(perfil="BASE", n=3, m=3, M=40, p=121, umbral=3)
UMBRAL = Parametros(perfil="UMBRAL", n=3, m=3, M=40, p=127, umbral=2)
