"""Pruebas de preparación. No acreditan ningún escenario operativo T01–T18."""

import csv
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from suma_segura.parametros import BASE, UMBRAL


ROOT = Path(__file__).resolve().parents[1]


def test_perfiles_del_caso_e3():
    assert (BASE.perfil, BASE.n, BASE.m, BASE.M, BASE.p, BASE.umbral) == (
        "BASE", 3, 3, 40, 121, 3
    )
    assert (UMBRAL.perfil, UMBRAL.n, UMBRAL.m, UMBRAL.M, UMBRAL.p, UMBRAL.umbral) == (
        "UMBRAL", 3, 3, 40, 127, 2
    )
    for perfil in (BASE, UMBRAL):
        assert perfil.p > perfil.n * perfil.M
        with pytest.raises(FrozenInstanceError):
            perfil.p = 97


def test_plan_e3_completo_y_trazable():
    with (ROOT / "docs/plan_pruebas.csv").open(encoding="utf-8", newline="") as f:
        plan = list(csv.DictReader(f))
    with (ROOT / "docs/matriz_trazabilidad.csv").open(encoding="utf-8", newline="") as f:
        matriz = list(csv.DictReader(f))
    ids = {f"T{i:02d}" for i in range(1, 19)}
    requisitos = {"RF1", "RF2", "RF3", "P1", "P2", "P3", "D1", "R1", "R2",
                  "RF1-U", "RF3-U", "D1-U", "R2-U"}
    assert len(plan) == 18 and {fila["id"] for fila in plan} == ids
    assert len(matriz) == 13 and {fila["requisito"] for fila in matriz} == requisitos
    pares_plan = set()
    for fila in plan:
        asociados = set(fila["requisitos"].split(";"))
        assert asociados and asociados <= requisitos
        assert fila["caso"] and fila["resultado_esperado"] and fila["fuente"]
        pares_plan.update((req, fila["id"]) for req in asociados)
    pares_matriz = set()
    for fila in matriz:
        pruebas = set(fila["pruebas"].split(";"))
        assert pruebas and pruebas <= ids
        assert fila["componente_previsto"] and fila["decision"]
        pares_matriz.update((fila["requisito"], prueba) for prueba in pruebas)
    assert pares_plan == pares_matriz
