"""Otros n y m del núcleo BASE, manteniendo p > n*M y el umbral m de m."""

from dataclasses import replace

import pytest

from suma_segura.mensajes import Parcial
from suma_segura.parametros import BASE


@pytest.mark.parametrize('n,m', [(2, 2), (2, 4), (4, 2), (5, 5)])
@pytest.mark.parametrize('caso', ['cero', 'maximo', 'mixto'])
def test_T01_T02_base_otras_dimensiones(sistema, n, m, caso):
    par = replace(BASE, n=n, m=m, p=n*40+1, umbral=m)
    entradas = [0 if caso == 'cero' else 40 if caso == 'maximo' else i*7 for i in range(n)]
    sim = sistema(entradas, par=par)
    sid = sim.iniciar(f'dimensiones-{n}-{m}-{caso}')
    assert [p.total for p in sim.analista.publicaciones] == [sum(entradas)]
    assert sim.entregados['Share'] == n*m
    assert sim.entregados['Acuse'] == n*m
    assert sim.entregados['Parcial'] == m and sim.entregados['Publicacion'] == 1
    assert not sim.analista.avisos
    assert all(s.sesiones[sid].parciales_emitidos == 1 for s in sim.servidores.values())


@pytest.mark.parametrize('n,m', [(2, 4), (4, 2)])
@pytest.mark.parametrize('perdida', ['silencio', 'rechazo'])
def test_T11_base_otras_dimensiones_requiere_todos(sistema, n, m, perdida):
    par = replace(BASE, n=n, m=m, p=n*40+1, umbral=m)
    sim = sistema([40]*n, par=par)
    emitir = sim.servidores[m].emitir

    def perder(destino, mensaje):
        if isinstance(mensaje, Parcial):
            # Silencio tras aceptación del transporte frente a rechazo explícito.
            return perdida == 'silencio'
        return emitir(destino, mensaje)

    sim.servidores[m].emitir = perder
    sid = sim.iniciar('dimensiones-incompleta')
    if perdida == 'silencio':
        assert len(sim.analista.sesiones[sid].parciales) == m-1
        assert not sim.analista.avisos
    else:
        assert sim.analista.sesiones[sid].estado == 'Incompleta'
        assert sim.analista.avisos[0].codigo == 'TIEMPO_EMISION'
    sim.avanzar(par.delta)
    assert not sim.analista.publicaciones
    assert len(sim.analista.avisos) == 1
    assert sim.analista.avisos[0].codigo == ('FALTAN_PARCIALES' if perdida == 'silencio' else 'TIEMPO_EMISION')
    assert sim.analista.sesiones[sid].estado == 'Incompleta'
