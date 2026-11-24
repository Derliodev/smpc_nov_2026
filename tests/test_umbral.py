"""Extensión Shamir 2 de 3 de E3: T04-U, T14-U, T16 y T17.

Los coeficientes fijos son únicamente fixtures. Los tests de alteración documentan
tanto la detección con tres como la ausencia de redundancia con dos parciales.
"""

from dataclasses import replace
from itertools import cycle, permutations
import secrets

import pytest

from suma_segura.mensajes import Error, Inicio, Listo, Parcial, Share
from suma_segura.parametros import BASE, UMBRAL
from suma_segura.shamir import compartir_shamir, reconstruir_par, residuo_consistencia
from suma_segura.simulacion import Simulacion


FILAS_U = ((17, 24, 31), (31, 42, 53), (43, 56, 69))
PARCIALES_U = {1: 91, 2: 122, 3: 26}


@pytest.fixture
def coeficientes(monkeypatch):
    valores = cycle((7, 11, 13))
    monkeypatch.setattr(secrets, "randbelow", lambda p: next(valores))


def test_T04_umbral_rechaza_121_antes_de_emitir(monkeypatch):
    emisiones = []
    monkeypatch.setattr(Simulacion, "_enviar", lambda *args: emisiones.append(type(args[-1]).__name__))
    with pytest.raises(ValueError, match="primo"):
        sim = Simulacion((10, 20, 30), replace(UMBRAL, p=121))
        sim.iniciar("T04-U-compuesto")
    assert emisiones == []


def test_T04_umbral_acepta_127(sistema):
    sim = sistema(par=replace(UMBRAL, p=127))
    sim.iniciar("T04-U-primo")
    assert [p.total for p in sim.analista.publicaciones] == [60]
    assert sim.entregados["Parcial"] == 3


@pytest.mark.parametrize("coincidencias", [False, True])
def test_T14_umbral_tres_coeficientes_nuevos_por_sid(sistema, monkeypatch, coincidencias):
    original = secrets.randbelow
    llamadas = []

    def observar(p):
        llamadas.append(p)
        return 0 if coincidencias else original(p)

    monkeypatch.setattr(secrets, "randbelow", observar)
    sim = sistema(par=UMBRAL)
    for numero in (1, 2):
        sim.iniciar(f"T14-U-sesion-{numero}")
        assert llamadas == [127] * (3 * numero)
    assert [p.total for p in sim.analista.publicaciones] == [60, 60]
    sim.avanzar(UMBRAL.delta)
    assert all(s.estado == "Cerrado" and not s.pendientes
               for h in sim.hospitales.values() for s in h.sesiones.values())


def test_T16_nominal_filas_parciales_y_tres_servidores(sistema, coeficientes):
    conteos = {"Share": 0, "Parcial": 0}

    def inspeccionar(origen, destino, mensaje):
        if isinstance(mensaje, Share):
            assert mensaje.valor == FILAS_U[mensaje.origen - 1][mensaje.destino - 1]
            conteos["Share"] += 1
        if isinstance(mensaje, Parcial):
            assert mensaje.valor == PARCIALES_U[mensaje.servidor]
            conteos["Parcial"] += 1
            assert sim.analista.publicaciones == []  # también al llegar el tercero
        return True

    sim = sistema(par=UMBRAL, filtro=inspeccionar)
    sid = sim.iniciar("T16-U-tres")
    assert conteos == {"Share": 9, "Parcial": 3}
    assert [p.total for p in sim.analista.publicaciones] == [60]
    assert sim.analista.avisos == []
    assert sim.entregados == {"Inicio": 6, "Listo": 3, "Share": 9, "Acuse": 9,
                              "Parcial": 3, "Publicacion": 1}
    assert residuo_consistencia(91, 122, 26, 127) == 0
    # La barrera de dos Listo no debe iniciar hospitales antes de enviar Inicio a S3.
    assert all(s.sesiones[sid].parciales_emitidos == 1 for s in sim.servidores.values())
    assert all(s.sesiones[sid].vista == {} for s in sim.servidores.values())
    sim.avanzar(UMBRAL.delta)
    assert all(h.sesiones[sid].estado == "Cerrado" and h.sesiones[sid].pendientes == {}
               for h in sim.hospitales.values())
    assert len(sim.analista.publicaciones) == 1


@pytest.mark.parametrize("u,v", list(permutations((1, 2, 3), 2)))
def test_T16_interpolacion_cualquier_par_y_orden(u, v):
    assert reconstruir_par(u, PARCIALES_U[u], v, PARCIALES_U[v], 127) == 60


@pytest.mark.parametrize("caido", [1, 2, 3])
@pytest.mark.parametrize("momento", ["antes_inicio", "despues_listo"])
def test_T16_cualquier_par_completa_solo_en_delta(sistema, coeficientes, caido, momento):
    sim = sistema(par=UMBRAL)
    if momento == "antes_inicio":
        sim.caidos.add(f"S{caido}")
    else:
        def caer(origen, destino, mensaje):
            if isinstance(mensaje, Listo) and mensaje.servidor == caido:
                sim.caidos.add(origen)
            return True
        sim.filtro = caer
    sid = sim.iniciar(f"T16-U-par-sin-{caido}-{momento}")
    a = sim.analista
    assert set(a.sesiones[sid].parciales) == {1, 2, 3} - {caido}
    assert sim.intentos["Share"] == 9  # intentar todos los destinos, aunque uno esté caído
    assert sim.entregados["Parcial"] == 2
    assert a.publicaciones == [] and a.avisos == []
    sim.avanzar(UMBRAL.delta - 0.001)
    assert a.publicaciones == [] and a.avisos == []
    sim.avanzar(UMBRAL.delta - sim.reloj())
    assert [p.total for p in a.publicaciones] == [60]
    assert a.sesiones[sid].estado == "Completa" and a.avisos == []
    assert [e["tiempo"] for e in sim.traza if e["evento"] == "Publicacion"] == [UMBRAL.delta]
    assert all(h.sesiones[sid].estado == "Cerrado" and h.sesiones[sid].pendientes == {}
               for h in sim.hospitales.values())
    assert all(len(h.sesiones[sid].acuses) == 2 for h in sim.hospitales.values())
    assert not a.recibir(Parcial(sid, caido, PARCIALES_U[caido]), f"S{caido}")
    sim.avanzar(1)
    assert len(a.publicaciones) == 1


@pytest.mark.parametrize("disponibles", [0, 1])
def test_T16_menos_de_dos_parciales_no_publica(sistema, disponibles):
    sim = sistema(par=UMBRAL)

    def caer(origen, destino, mensaje):
        if isinstance(mensaje, Listo) and mensaje.servidor > disponibles:
            sim.caidos.add(origen)
        return True

    sim.filtro = caer
    sid = sim.iniciar(f"T16-U-insuficiente-{disponibles}")
    assert len(sim.analista.sesiones[sid].parciales) == disponibles
    sim.avanzar(UMBRAL.delta)
    assert sim.analista.publicaciones == []
    assert len(sim.analista.avisos) == 1
    assert sim.analista.avisos[0].codigo == "FALTAN_PARCIALES"
    assert sim.analista.sesiones[sid].estado == "Incompleta"
    assert all(h.sesiones[sid].estado == "Abortado" and not h.sesiones[sid].pendientes
               for h in sim.hospitales.values())
    sim.avanzar(1)
    assert len(sim.analista.avisos) == 1


def test_T16_sin_dos_listo_no_habilita_hospitales(sistema):
    sim = sistema(par=UMBRAL)
    sim.caidos.update(("S2", "S3"))
    sid = sim.iniciar("T16-U-faltan-listo")
    assert sim.intentos["Share"] == 0
    sim.avanzar(UMBRAL.T)
    assert sim.analista.sesiones[sid].estado == "EsperandoListos"
    assert not sim.analista.avisos
    sim.avanzar(UMBRAL.delta - UMBRAL.T)
    assert [a.codigo for a in sim.analista.avisos] == ["FALTAN_LISTO"]
    assert not sim.analista.publicaciones


@pytest.mark.parametrize("falla", ["falta_share", "falla_emision"])
def test_T16_servidor_vencido_se_trata_como_ausente(sistema, coeficientes, falla):
    def filtrar(origen, destino, mensaje):
        if falla == "falta_share":
            return not (isinstance(mensaje, Share) and origen == "H3" and destino == "S2")
        return not (isinstance(mensaje, Parcial) and origen == "S2")

    sim = sistema(par=UMBRAL, filtro=filtrar)
    sid = sim.iniciar(f"T16-U-ausente-{falla}")
    assert set(sim.analista.sesiones[sid].parciales) == {1, 3}
    sim.avanzar(UMBRAL.T)
    assert sim.servidores[2].sesiones[sid].estado == "Abortado"
    assert sim.servidores[2].sesiones[sid].parciales_emitidos == 0
    assert any(e["evento"] == "ServidorAusente" and e["origen"] == "S2" for e in sim.traza)
    assert not sim.analista.publicaciones and not sim.analista.avisos
    sim.avanzar(UMBRAL.delta - UMBRAL.T)
    assert [p.total for p in sim.analista.publicaciones] == [60]
    assert not sim.analista.avisos


@pytest.mark.parametrize("x,total", [(0, 0), (40, 120)])
@pytest.mark.parametrize("caido", [1, 2, 3])
def test_umbral_extremos_con_cualquier_par(sistema, x, total, caido):
    sim = sistema((x, x, x), par=UMBRAL)
    sim.caidos.add(f"S{caido}")
    sim.iniciar(f"extremo-U-{total}-sin-{caido}")
    sim.avanzar(UMBRAL.delta)
    assert [p.total for p in sim.analista.publicaciones] == [total]


@pytest.mark.parametrize("x", [-1, 41, 1.5, True])
def test_umbral_entrada_invalida_sigue_siendo_fatal(sistema, x):
    sim = sistema((10, x, 30), par=UMBRAL)
    sid = sim.iniciar("U-entrada-invalida")
    assert sim.hospitales[2].sesiones[sid].estado == "Abortado"
    assert sim.intentos["Share"] == 3  # solo el hospital anterior aportó
    assert [a.codigo for a in sim.analista.avisos] == ["ENTRADA_INVALIDA"]
    sim.avanzar(UMBRAL.delta)
    assert not sim.analista.publicaciones and len(sim.analista.avisos) == 1


@pytest.mark.parametrize("par,ajeno", [(BASE, UMBRAL), (UMBRAL, BASE)])
def test_inicio_no_mezcla_perfiles(sistema, par, ajeno):
    sim = sistema(par=par)
    inicio = Inicio("perfil-ajeno", ajeno)
    assert not sim.servidores[1].recibir(inicio, "A")
    assert not sim.hospitales[1].recibir(inicio, "A")
    assert sim.hospitales[1].sesiones[inicio.sid].estado == "Abortado"
    assert sim.intentos["Share"] == 0 and sim.intentos["Listo"] == 0
    assert sim.intentos["Error"] == 1


def test_umbral_error_configuracion_hospital_cierra_sesion(sistema):
    sim = sistema(par=UMBRAL, filtro=lambda o, d, m: not isinstance(m, Share))
    sid = sim.iniciar("U-error-configuracion")
    assert sim.analista.recibir(Error(sid, "H2", "PARAMETROS_INVALIDOS"), "H2")
    sim.avanzar(UMBRAL.delta)
    assert not sim.analista.publicaciones
    assert [a.codigo for a in sim.analista.avisos] == ["PARAMETROS_INVALIDOS"]


@pytest.mark.parametrize("instante,completa", [(UMBRAL.delta - 0.001, True), (UMBRAL.delta, False)])
def test_T16_segundo_parcial_en_frontera(sistema, instante, completa):
    # Ensayo unitario del analista: las inyecciones no son conexiones autenticadas.
    sim = sistema(par=UMBRAL, filtro=lambda o, d, m: not isinstance(m, Share))
    sid = sim.iniciar("T16-U-frontera")
    assert sim.analista.recibir(Parcial(sid, 1, 91), "S1")
    sim.reloj.avanzar(instante)
    assert sim.analista.recibir(Parcial(sid, 3, 26), "S3") == completa
    sim.avanzar(max(0, UMBRAL.delta - sim.reloj()))
    assert [p.total for p in sim.analista.publicaciones] == ([60] if completa else [])
    assert [a.codigo for a in sim.analista.avisos] == ([] if completa else ["FALTAN_PARCIALES"])


def test_T17_tres_parciales_alterados_residuo_125(sistema, coeficientes, request):
    sim = sistema(par=UMBRAL)
    emitir = sim.servidores[2].emitir

    def alterar(destino, mensaje):
        if isinstance(mensaje, Parcial):
            assert mensaje.valor == 122
            mensaje = replace(mensaje, valor=123)
        return emitir(destino, mensaje)

    sim.servidores[2].emitir = alterar
    residuos = []

    def observar(origen, destino, mensaje):
        if isinstance(mensaje, Parcial) and mensaje.servidor == 3:
            parciales = sim.analista.sesiones[mensaje.sid].parciales
            residuos.append(residuo_consistencia(parciales[1], parciales[2], mensaje.valor, 127))
            assert not sim.analista.publicaciones
        return True

    sim.filtro = observar
    sid = sim.iniciar("T17-U-inconsistente")
    assert residuos == [125]
    request.node.user_properties.append(("residuo_observado", residuos[0]))
    assert not sim.analista.publicaciones
    assert [a.codigo for a in sim.analista.avisos] == ["PARCIALES_INCONSISTENTES"]
    assert sim.analista.sesiones[sid].estado == "Incompleta"
    assert sim.analista.sesiones[sid].parciales == {}
    assert sim.entregados["Parcial"] == 3
    sim.avanzar(UMBRAL.delta)
    assert not sim.analista.recibir(Parcial(sid, 2, 122), "S2")
    assert len(sim.analista.avisos) == 1 and not sim.analista.publicaciones


@pytest.mark.parametrize("caido,total_sesgado", [(3, 59), (1, 63)])
def test_T17_dos_parciales_no_detectan_alteracion(sistema, coeficientes, caido, total_sesgado):
    sim = sistema(par=UMBRAL)
    sim.caidos.add(f"S{caido}")
    emitir = sim.servidores[2].emitir
    sim.servidores[2].emitir = lambda d, m: emitir(d, replace(m, valor=123) if isinstance(m, Parcial) else m)
    sim.iniciar(f"T17-U-limite-sin-{caido}")
    assert not sim.analista.publicaciones
    sim.avanzar(UMBRAL.delta)
    # Es una limitación esperada: estos valores incorrectos se aceptan con dos.
    assert [p.total for p in sim.analista.publicaciones] == [total_sesgado]
    assert total_sesgado != 60 and sim.analista.avisos == []


@pytest.mark.parametrize("instante,codigo", [(UMBRAL.delta - 0.001, "PARCIALES_INCONSISTENTES"),
                                             (UMBRAL.delta, None)])
def test_T17_tercer_parcial_no_adelanta_publicacion(sistema, instante, codigo):
    sim = sistema(par=UMBRAL, filtro=lambda o, d, m: not isinstance(m, Share))
    sid = sim.iniciar("T17-U-tercero")
    sim.analista.recibir(Parcial(sid, 1, 91), "S1")
    sim.analista.recibir(Parcial(sid, 3, 26), "S3")
    assert not sim.analista.publicaciones
    sim.reloj.avanzar(instante)
    sim.analista.recibir(Parcial(sid, 2, 123), "S2")
    if codigo:
        assert [a.codigo for a in sim.analista.avisos] == [codigo]
        assert not sim.analista.publicaciones
    else:
        # En Δ gana el vencimiento: se usa el par previo (1,3), y el tercero es tardío.
        assert [p.total for p in sim.analista.publicaciones] == [60]
        assert not sim.analista.avisos


@pytest.mark.parametrize("p", [2, 3, 121, True, 127.0])
def test_nucleo_shamir_rechaza_campo_invalido(p):
    with pytest.raises(ValueError, match="primo"):
        compartir_shamir(1, p)


@pytest.mark.parametrize("u,yu,v,yv", [(1, 91, 1, 122), (0, 91, 2, 122),
                                      (1, 91, 4, 122), (True, 91, 2, 122),
                                      (1, -1, 2, 122), (1, 91, 2, 127),
                                      (1, True, 2, 122)])
def test_nucleo_shamir_rechaza_pares_invalidos(u, yu, v, yv):
    with pytest.raises(ValueError):
        reconstruir_par(u, yu, v, yv, 127)


@pytest.mark.parametrize("cambios", [dict(m=4), dict(umbral=3), dict(p=125)])
def test_umbral_valida_contrato_dos_de_tres(cambios):
    with pytest.raises(ValueError):
        replace(UMBRAL, **cambios)
