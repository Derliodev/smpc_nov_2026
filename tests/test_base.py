"""Escenarios propios E3 de etapa 2. Datos y máscaras fijos solo en tests."""

from collections import Counter
from dataclasses import replace
from itertools import cycle, product
import secrets

import pytest

from suma_segura.hospital import compartir
from suma_segura.hospital import Hospital
from suma_segura.mensajes import Acuse, Error, Inicio, Listo, Parcial, Share
from suma_segura.parametros import BASE, UMBRAL
from suma_segura.simulacion import Simulacion


FILAS = ((15, 25, 91), (40, 50, 51), (60, 70, 21))
PARCIALES = (115, 24, 42)


@pytest.fixture
def mascaras(monkeypatch):
    valores = cycle((15, 25, 40, 50, 60, 70))
    monkeypatch.setattr(secrets, "randbelow", lambda p: next(valores))


def sin_shares(origen, destino, mensaje):
    return not isinstance(mensaje, Share)


def comprobar_incompleta(sim, sid, codigo):
    assert sim.analista.sesiones[sid].estado == "Incompleta"
    assert sim.analista.publicaciones == []
    assert len(sim.analista.avisos) == 1
    assert sim.analista.avisos[0].codigo == codigo
    assert sim.entregados["Publicacion"] == 0
    assert sim.entregados["AvisoIncompleta"] == 1


def test_T01_nominal_filas_parciales_publicacion(sistema, mascaras):
    observados = Counter()

    def inspeccionar(origen, destino, mensaje):
        # Se compara con fixtures sintéticos, sin almacenar una colección de secretos.
        if isinstance(mensaje, Share):
            assert mensaje.valor == FILAS[mensaje.origen - 1][mensaje.destino - 1]
            observados["Share"] += 1
        if isinstance(mensaje, Parcial):
            assert mensaje.valor == PARCIALES[mensaje.servidor - 1]
            observados["Parcial"] += 1
        return True

    sim = sistema(filtro=inspeccionar)
    sid = sim.iniciar("T01-nominal")
    assert observados == {"Share": 9, "Parcial": 3}
    assert [sum(fila) % BASE.p for fila in FILAS] == [10, 20, 30]
    assert [p.total for p in sim.analista.publicaciones] == [60]
    assert sim.analista.avisos == []
    assert sim.entregados == {"Inicio": 6, "Listo": 3, "Share": 9,
                              "Acuse": 9, "Parcial": 3, "Publicacion": 1}
    for j, srv in sim.servidores.items():
        assert srv.sesiones[sid].estado == "Enviado"
        assert srv.sesiones[sid].vista == {}
        assert srv.sesiones[sid].parciales_emitidos == 1
        assert [e["conteo"] for e in sim.traza if e["actor"] == f"S{j}"
                and e["evento"] == "ShareAceptado"] == [1, 2, 3]
        assert [e["origen"] for e in sim.traza if e["actor"] == f"S{j}"
                and e["evento"] == "ShareAceptado"] == ["H1", "H2", "H3"]
    assert all(h.sesiones[sid].pendientes == {} for h in sim.hospitales.values())
    assert all(h.sesiones[sid].estado == "Cerrado" for h in sim.hospitales.values())
    assert sim.analista.sesiones[sid].parciales == {}
    sim.avanzar(BASE.delta * 2)
    sim.analista.recibir(Parcial(sid, 1, 0), "S1")
    assert len(sim.analista.publicaciones) == 1
    assert not sim.analista.avisos


@pytest.mark.parametrize("entradas,total", [((0, 0, 0), 0), ((40, 40, 40), 120)])
def test_T02_extremos(sistema, entradas, total):
    sim = sistema(entradas)
    sim.iniciar(f"T02-{total}")
    assert [p.total for p in sim.analista.publicaciones] == [total]
    assert sim.entregados["Share"] == 9


def test_T03_68921_combinaciones(monkeypatch, request):
    # Comprobar además todas las filas posibles de cada posición de hospital.
    for x, pares in product(range(41), ((15, 25), (40, 50), (60, 70))):
        valores = iter(pares)
        monkeypatch.setattr(secrets, "randbelow", lambda p: next(valores))
        assert sum(compartir(x, 3, 121)) % 121 == x
    valores = cycle((15, 25, 40, 50, 60, 70))
    monkeypatch.setattr(secrets, "randbelow", lambda p: next(valores))
    comprobadas = 0
    for entradas in product(range(41), repeat=3):
        # Protocolo completo; sin acumular 68.921 trazas ni entradas privadas.
        sim = Simulacion(entradas, registrar=False)
        sim.iniciar("T03-ensayo-aislado")
        assert [p.total for p in sim.analista.publicaciones] == [sum(entradas)], entradas
        assert sim.entregados["Parcial"] == 3 and sim.entregados["Share"] == 9
        assert not sim.analista.avisos
        comprobadas += 1
    assert comprobadas == 68_921
    request.node.user_properties.append(("combinaciones_verificadas", comprobadas))


@pytest.mark.parametrize("p", [97, 120])
def test_T04_base_rechaza_modulo_antes_de_share(monkeypatch, p):
    emisiones = []
    monkeypatch.setattr(Simulacion, "_enviar", lambda *args: emisiones.append(type(args[-1]).__name__))
    with pytest.raises(ValueError, match="p > n"):
        sim = Simulacion((10, 20, 30), replace(BASE, p=p))
        sim.iniciar("T04-invalido")
    assert emisiones == []


def test_T04_base_acepta_121(sistema):
    sim = sistema(par=replace(BASE, p=121))
    sim.iniciar("T04-valido")
    assert sim.analista.publicaciones[0].total == 60


@pytest.mark.parametrize("x", [-1, 41, 1.5, True])
def test_T05_entrada_invalida_sin_share(sistema, x):
    aportes_h2 = []

    def observar(origen, destino, mensaje):
        if origen == "H2" and isinstance(mensaje, Share):
            aportes_h2.append(mensaje.destino)
        return True

    sim = sistema((10, x, 30), filtro=observar)
    sid = sim.iniciar("T05-invalido")
    comprobar_incompleta(sim, sid, "ENTRADA_INVALIDA")
    assert aportes_h2 == []
    assert sim.hospitales[2].sesiones[sid].estado == "Abortado"
    assert sim.entregados["Share"] == 3  # solo H1 había aportado
    sim.avanzar(BASE.delta)
    comprobar_incompleta(sim, sid, "ENTRADA_INVALIDA")


def test_T06_duplicado_conserva_primero(sistema, mascaras):
    sim = sistema(filtro=lambda o, d, m: not (isinstance(m, Share) and d == "S1" and m.origen > 1))
    sid = sim.iniciar("T06-duplicado")
    srv, s = sim.servidores[1], sim.servidores[1].sesiones[sid]
    assert s.k == 1 and s.vista[(sid, 1)] == 15
    assert not srv.recibir(Share(sid, 1, 1, 16), "H1")
    assert s.k == 1 and s.vista[(sid, 1)] == 15
    assert srv.recibir(Share(sid, 2, 1, 40), "H2")
    assert s.k == 2
    assert srv.recibir(Share(sid, 3, 1, 60), "H3")
    assert [p.total for p in sim.analista.publicaciones] == [60]
    assert not srv.recibir(Share(sid, 1, 1, 17), "H1")
    assert s.parciales_emitidos == 1


@pytest.mark.parametrize("share", [Share("anterior", 1, 1, 15), Share("T07-ruta", 1, 2, 25)])
def test_T07_sesion_y_destino_ajenos(sistema, share):
    sim = sistema(filtro=sin_shares)
    sid = sim.iniciar("T07-ruta")
    srv = sim.servidores[1]
    assert not srv.recibir(share, "H1")
    assert srv.sesiones[sid].vista == {} and srv.sesiones[sid].k == 0
    assert sim.analista.publicaciones == []


def test_T10_falta_share_en_T(sistema):
    sim = sistema(filtro=lambda o, d, m: not (isinstance(m, Share) and o == "H3" and d == "S1"))
    sid = sim.iniciar("T10-vencimiento")
    assert sim.servidores[1].sesiones[sid].k == 2
    assert len(sim.analista.sesiones[sid].parciales) == 2
    sim.avanzar(BASE.T)
    comprobar_incompleta(sim, sid, "TIEMPO_SHARES")
    assert sim.servidores[1].sesiones[sid].estado == "Abortado"
    assert sim.servidores[1].sesiones[sid].vista == {}
    assert any(e["actor"] == "S1" and e["codigo"] == "TIEMPO_SHARES" for e in sim.traza)
    sim.avanzar(BASE.delta)
    comprobar_incompleta(sim, sid, "TIEMPO_SHARES")


def test_T11_servidor_caido_despues_de_listo(sistema):
    sim = sistema()

    def caer(origen, destino, mensaje):
        if isinstance(mensaje, Listo) and mensaje.servidor == 2:
            sim.caidos.add("S2")
        return True

    sim.filtro = caer
    sid = sim.iniciar("T11-caida")
    assert sim.analista.sesiones[sid].listos == {1, 2, 3}
    assert set(sim.analista.sesiones[sid].parciales) == {1, 3}
    sim.avanzar(BASE.T)
    assert sim.analista.avisos == []  # S2 caído no ejecuta su propio temporizador
    sim.avanzar(BASE.delta - BASE.T)
    comprobar_incompleta(sim, sid, "FALTAN_PARCIALES")
    assert sim.entregados["Error"] == 0
    sim.avanzar(1)
    comprobar_incompleta(sim, sid, "FALTAN_PARCIALES")


def test_T12_parciales_invalidos_y_duplicados(sistema):
    sim = sistema(filtro=sin_shares)
    sid = sim.iniciar("T12-parciales")
    a = sim.analista
    assert a.recibir(Parcial(sid, 1, 115), "S1")
    for mensaje, emisor in [(Parcial(sid, 1, 116), "S1"), (Parcial("ajeno", 2, 24), "S2"),
                            (Parcial(sid, 2, -1), "S2"), (Parcial(sid, 2, 121), "S2"),
                            (Parcial(sid, 2, True), "S2"), (Parcial(sid, 2, 1.5), "S2")]:
        assert not a.recibir(mensaje, emisor)
        assert a.sesiones[sid].parciales == {1: 115}
    assert a.recibir(Parcial(sid, 2, 24), "S2")
    assert a.recibir(Parcial(sid, 3, 42), "S3")
    assert [p.total for p in a.publicaciones] == [60]
    assert not a.recibir(Parcial(sid, 3, 43), "S3")
    assert len(a.publicaciones) == 1


@pytest.mark.parametrize("valor", [-1, 121, True, 1.5])
def test_T12_share_fuera_de_zp_advierte_sin_abortar(sistema, valor):
    sim = sistema(filtro=sin_shares)
    sid = sim.iniciar("T12-share")
    srv = sim.servidores[1]
    assert not srv.recibir(Share(sid, 1, 1, valor), "H1")
    assert srv.sesiones[sid].estado == "Recibiendo" and srv.sesiones[sid].k == 0
    assert sim.analista.sesiones[sid].estado == "EsperandoParciales"
    assert sim.analista.avisos == []
    assert any(e["evento"] == "Advertencia" and e["codigo"] == "SHARE_FUERA_DE_ZP" for e in sim.traza)
    assert srv.recibir(Share(sid, 1, 1, 15), "H1")
    assert srv.sesiones[sid].k == 1


@pytest.mark.parametrize("instante,completa", [(BASE.T - 0.001, True), (BASE.T, False), (BASE.T + 1, False)])
def test_T13_ultimo_share_en_frontera(sistema, mascaras, instante, completa):
    sim = sistema(filtro=lambda o, d, m: not (isinstance(m, Share) and o == "H3" and d == "S1"))
    sid = sim.iniciar("T13-share")
    sim.reloj.avanzar(instante)  # recibir debe revisar T sin depender de un tick previo
    aceptado = sim.servidores[1].recibir(Share(sid, 3, 1, 60), "H3")
    assert aceptado == completa
    if completa:
        assert [p.total for p in sim.analista.publicaciones] == [60]
    else:
        comprobar_incompleta(sim, sid, "TIEMPO_SHARES")
        assert not sim.servidores[1].recibir(Inicio(sid, BASE), "A")
        assert not sim.servidores[1].recibir(Share(sid, 3, 1, 60), "H3")


@pytest.mark.parametrize("instante,completa", [(BASE.delta - 0.001, True), (BASE.delta, False), (BASE.delta + 1, False)])
def test_T13_ultimo_parcial_en_frontera(sistema, instante, completa):
    sim = sistema(filtro=sin_shares)
    sid = sim.iniciar("T13-parcial")
    a = sim.analista
    a.recibir(Parcial(sid, 1, 115), "S1")
    a.recibir(Parcial(sid, 2, 24), "S2")
    sim.reloj.avanzar(instante)
    aceptado = a.recibir(Parcial(sid, 3, 42), "S3")
    assert aceptado == completa
    if completa:
        assert [p.total for p in a.publicaciones] == [60]
    else:
        comprobar_incompleta(sim, sid, "FALTAN_PARCIALES")
        assert not a.recibir(Parcial(sid, 3, 42), "S3")
        with pytest.raises(ValueError, match="ya utilizado"):
            a.abrir(sid)


@pytest.mark.parametrize("coincidencias", [False, True])
def test_T14_base_seis_sorteos_nuevos_por_sid(sistema, monkeypatch, coincidencias):
    original = secrets.randbelow
    sorteos = []

    def observar(p):
        sorteos.append(p)
        return 0 if coincidencias else original(p)

    monkeypatch.setattr(secrets, "randbelow", observar)
    sim = sistema()
    for numero in (1, 2):
        sid = sim.iniciar(f"T14-sesion-{numero}")
        assert sorteos == [121] * (6 * numero)
        assert sim.analista.sesiones[sid].estado == "Completa"
    assert [p.total for p in sim.analista.publicaciones] == [60, 60]


def test_T15_uniformidad_exacta_z5(monkeypatch):
    for secreto in range(5):
        cuentas = [Counter() for _ in range(3)]
        for a, b in product(range(5), repeat=2):
            valores = iter((a, b))
            monkeypatch.setattr(secrets, "randbelow", lambda p: next(valores))
            shares = compartir(secreto, 3, 5)
            assert sum(shares) % 5 == secreto
            for j, valor in enumerate(shares):
                cuentas[j][valor] += 1
        assert cuentas == [Counter({v: 5 for v in range(5)}) for _ in range(3)]


@pytest.mark.parametrize("cambios", [dict(n=True), dict(m=1), dict(M=-1), dict(p=1), dict(p=121.0),
                                    dict(umbral=2), dict(T=0), dict(T=20), dict(delta=5),
                                    dict(T=float("nan")), dict(delta=float("inf")), dict(T=True)])
def test_configuracion_base_invalida(cambios):
    with pytest.raises(ValueError):
        replace(BASE, **cambios)


def test_umbral_no_se_ejecuta_accidentalmente_como_base(monkeypatch):
    # Etapa 3: se conserva la protección contra mezclar algoritmos. Ahora UMBRAL
    # está implementado; tres coeficientes cero producen tres parciales 60.
    # Sumarlos como BASE daría 53 mod 127, no el total correcto 60.
    sorteos = []
    monkeypatch.setattr(secrets, "randbelow", lambda p: sorteos.append(p) or 0)
    sim = Simulacion((10, 20, 30), UMBRAL)
    sim.iniciar("umbral-no-aditivo")
    assert sorteos == [127, 127, 127]
    assert [p.total for p in sim.analista.publicaciones] == [60]


def test_faltan_listo_sin_habilitar_hospitales(sistema):
    sim = sistema()
    sim.caidos.add("S2")
    sid = sim.iniciar("faltan-listo")
    assert sim.entregados["Share"] == 0
    # Bloquear además avisos de los servidores para comprobar el silencio en Δ.
    sim.filtro = lambda o, d, m: not isinstance(m, Error)
    sim.avanzar(BASE.delta)
    comprobar_incompleta(sim, sid, "FALTAN_LISTO")


def test_error_emision_parcial_no_publica(sistema):
    sim = sistema(filtro=lambda o, d, m: not (isinstance(m, Parcial) and o == "S1"))
    sid = sim.iniciar("fallo-emision")
    comprobar_incompleta(sim, sid, "TIEMPO_EMISION")
    assert sim.servidores[1].sesiones[sid].estado == "Abortado"
    assert sim.servidores[1].sesiones[sid].parciales_emitidos == 0


def test_acuses_perdidos_limpian_temporales(sistema):
    sim = sistema(filtro=lambda o, d, m: not isinstance(m, Acuse))
    sid = sim.iniciar("sin-acuses")
    assert [p.total for p in sim.analista.publicaciones] == [60]
    assert all(h.sesiones[sid].pendientes for h in sim.hospitales.values())
    sim.avanzar(BASE.delta)
    assert all(h.sesiones[sid].pendientes == {} for h in sim.hospitales.values())
    assert all(h.sesiones[sid].estado == "Abortado" for h in sim.hospitales.values())
    assert len(sim.analista.publicaciones) == 1 and sim.analista.avisos == []


def test_guardas_logicas_no_equivalen_a_tls(sistema):
    sim = sistema(filtro=sin_shares)
    sid = sim.iniciar("guardas-logicas")
    srv = sim.servidores[1]
    for mensaje, emisor in [(Share(sid, 1, 1, 15), "H2"), (Share(sid, 4, 1, 15), "H4"),
                            (Share(sid, True, 1, 15), "H1")]:
        assert not srv.recibir(mensaje, emisor)
    assert srv.sesiones[sid].k == 0
    assert not sim.analista.recibir(Parcial(sid, 1, 115), "S2")
    assert not sim.analista.recibir(Error(sid, "H1", "ENTRADA_INVALIDA"), "H2")
    assert sim.analista.sesiones[sid].estado == "EsperandoParciales"


def test_trazas_sin_valores_privados(sistema):
    sim = sistema()
    sim.iniciar("sin-secretos-en-traza")
    assert sim.traza
    campos = {"tiempo", "sid", "actor", "evento", "estado", "codigo", "conteo", "origen"}
    assert all(set(evento) == campos for evento in sim.traza)


def test_salto_reloj_respeta_orden_de_vencimientos(sistema):
    sim = sistema(filtro=lambda o, d, m: not (isinstance(m, Share) and o == "H3" and d == "S1"))
    sid = sim.iniciar("salto-de-reloj")
    sim.avanzar(BASE.delta)
    comprobar_incompleta(sim, sid, "TIEMPO_SHARES")
    abortos = [e for e in sim.traza if e["actor"] == "S1" and e["evento"] == "Aborto"]
    assert [e["tiempo"] for e in abortos] == [BASE.T]
    assert sim.reloj() == BASE.delta


def test_inicio_hospital_configuracion_incompatible(sistema):
    sim = sistema()
    errores = []
    h = Hospital(1, 10, BASE, sim.reloj, lambda destino, mensaje: errores.append(mensaje), sim.traza.append)
    assert not h.recibir(Inicio("configuracion-ajena", replace(BASE, p=122)), "A")
    assert errores == [Error("configuracion-ajena", "H1", "PARAMETROS_INVALIDOS")]
    assert not h.recibir(Inicio("configuracion-ajena", BASE), "A")
    assert len(errores) == 1
