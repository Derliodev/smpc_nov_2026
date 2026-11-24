"""Shamir 2 de 3; adaptación del listado 4.8 de clase_4.pdf y E3 §3.4.

Los índices públicos son 1, 2 y 3. Un coeficiente cero también es válido:
el sorteo debe cubrir todo Zp, sin excluirlo ni reutilizar coeficientes.
"""

from math import isqrt
import secrets


def validar_campo(p: int):
    if type(p) is not int or p <= 3 or any(p % d == 0 for d in range(2, isqrt(p) + 1)):
        raise ValueError("Shamir 2 de 3 requiere p primo mayor que 3")


def compartir_shamir(x: int, p: int) -> list[int]:
    validar_campo(p)
    if type(x) is not int or not 0 <= x < p:
        raise ValueError("el secreto debe ser un entero de Zp")
    a = secrets.randbelow(p)
    return [(x + a * j) % p for j in (1, 2, 3)]


def reconstruir_par(u: int, yu: int, v: int, yv: int, p: int) -> int:
    """Interpolación de Lagrange en cero, para dos índices distintos."""
    validar_campo(p)
    if (any(type(j) is not int or j not in (1, 2, 3) for j in (u, v)) or u == v):
        raise ValueError("se requieren dos índices distintos de {1,2,3}")
    if any(type(y) is not int or not 0 <= y < p for y in (yu, yv)):
        raise ValueError("los parciales deben ser enteros de Zp")
    lu = v * pow(v - u, -1, p)
    lv = u * pow(u - v, -1, p)
    return (lu * yu + lv * yv) % p


def residuo_consistencia(z1: int, z2: int, z3: int, p: int) -> int:
    """Cero si los tres puntos pertenecen a un polinomio de grado <= 1.

    Un residuo no nulo detecta inconsistencia, sin identificar al responsable.
    """
    validar_campo(p)
    if any(type(z) is not int or not 0 <= z < p for z in (z1, z2, z3)):
        raise ValueError("los parciales deben ser enteros de Zp")
    return (z1 - 2 * z2 + z3) % p
