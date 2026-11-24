"""T18: eventos que compiten desde hilos, sin depender de la atomicidad del GIL."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from time import sleep

import pytest

from suma_segura.mensajes import Inicio, Parcial, Share
from suma_segura.parametros import BASE, UMBRAL


def simultaneos(funciones):
    barrera = Barrier(len(funciones))

    def ejecutar(funcion):
        barrera.wait(timeout=5)
        return funcion()

    with ThreadPoolExecutor(max_workers=len(funciones)) as ejecutor:
        futuros = [ejecutor.submit(ejecutar, f) for f in funciones]
        return [f.result(timeout=5) for f in futuros]


class VistaConPausa(dict):
    def __contains__(self, clave):
        existe = super().__contains__(clave)
        # Soltar el GIL entre consulta e inserción expone una carrera sin cerrojo.
        sleep(0.01)
        return existe


@pytest.mark.parametrize('par', [BASE, UMBRAL], ids=['BASE', 'UMBRAL'])
@pytest.mark.parametrize('ronda', range(3))
def test_T18_share_simultaneo_y_reinicio_tras_cierre(sistema, par, ronda, request):
    sim = sistema(par=par, filtro=lambda o, d, m: not isinstance(m, Share))
    sid = sim.iniciar(f'T18-{par.perfil}-{ronda}')
    # Usar los shares privados solo desde la vista local de cada hospital.
    for j, srv in sim.servidores.items():
        s = srv.sesiones[sid]
        s.vista = VistaConPausa()
        for i in range(1, 4):
            valor = sim.hospitales[i].sesiones[sid].pendientes[j]
            share = Share(sid, i, j, valor)
            resultados = simultaneos([lambda: srv.recibir(share, f'H{i}') for _ in range(2)])
            assert sorted(resultados) == [False, True]
            if i < 3:
                assert s.k == i and s.vista[(sid, i)] == valor
        assert s.estado == 'Enviado' and s.parciales_emitidos == 1 and s.vista == {}
        assert simultaneos([lambda: srv.recibir(Inicio(sid, par), 'A') for _ in range(2)]) == [False, False]
    assert [p.total for p in sim.analista.publicaciones] == [60]
    assert sim.entregados['Parcial'] == 3 and sim.entregados['Publicacion'] == 1
    assert not sim.analista.avisos
    sim.avanzar(par.delta)
    for hospital in sim.hospitales.values():
        assert hospital.sesiones[sid].estado == 'Cerrado'
        assert not hospital.recibir(Inicio(sid, par), 'A')
    with pytest.raises(ValueError, match='ya utilizado'):
        sim.iniciar(sid)
    assert len([e for e in sim.traza if e['evento'] == 'ShareAceptado']) == 9
    request.node.user_properties.append(('inserciones_unicas', 9))
    request.node.user_properties.append(('publicaciones', 1))


@pytest.mark.parametrize('par', [BASE, UMBRAL], ids=['BASE', 'UMBRAL'])
def test_T18_parciales_simultaneos_salida_unica(sistema, par):
    # Dejar al analista esperando aportes; rechazar un envío Parcial provocaría
    # TIEMPO_EMISION y el cierre correcto de BASE antes de esta inyección.
    sim = sistema(par=par, filtro=lambda o, d, m: not isinstance(m, Share))
    sid = sim.iniciar('T18-parciales')
    valores = (115, 24, 42) if par == BASE else (91, 122, 26)
    funciones = [lambda j=j, v=v: sim.analista.recibir(Parcial(sid, j, v), f'S{j}')
                 for j, v in enumerate(valores, 1) for _ in range(2)]
    assert sum(simultaneos(funciones)) == 3
    assert [p.total for p in sim.analista.publicaciones] == [60]
    assert sim.entregados['Publicacion'] == 1 and not sim.analista.avisos
    assert sim.analista.sesiones[sid].parciales == {}
