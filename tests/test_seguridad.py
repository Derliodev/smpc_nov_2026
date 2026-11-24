"""T08/T09: TCP loopback y TLS reales contra los receptores del protocolo."""

from contextlib import ExitStack
from dataclasses import replace
import json
import socket
import ssl

import pytest

from suma_segura.analista import Analista
from suma_segura.canal_tls import ReceptorTLS, contexto_tls, enviar_tls
from suma_segura.eventos import RelojManual
from suma_segura.hospital import Hospital
from suma_segura.mensajes import Acuse, Inicio, Listo, Parcial, Share
from suma_segura.parametros import BASE, UMBRAL
from suma_segura.servidor import Servidor


def contexto(pki, nombre=None, servidor=False):
    return contexto_tls(pki/'ca.crt', pki/f'{nombre}.crt' if nombre else None,
                        pki/f'{nombre}.key' if nombre else None, servidor=servidor)


@pytest.fixture(params=['H-S', 'S-A'])
def enlace(request):
    traza = []
    reloj = RelojManual()
    if request.param == 'H-S':
        receptor = Servidor(1, BASE, reloj, lambda *args: True, traza.append)
        receptor.recibir(Inicio('tls', BASE), 'A')
        mensaje, cliente = Share('tls', 1, 1, 15), 'H1'
    else:
        receptor = Analista(BASE, reloj, lambda *args: True, traza.append)
        receptor.abrir('tls')
        for j in range(1, 4):
            receptor.recibir(Listo('tls', j), f'S{j}')
        mensaje, cliente = Parcial('tls', 1, 115), 'S1'
    traza.clear()
    return receptor, mensaje, cliente, traza


def sin_aportes(receptor, traza):
    sesion = receptor.sesiones['tls']
    assert getattr(sesion, 'vista', getattr(sesion, 'parciales', None)) == {}
    assert not any(e['evento'] in ('ShareAceptado', 'ParcialAceptado', 'Publicacion') for e in traza)


def test_T09_tls13_mutuo_acepta_aporte_valido(pki, enlace, auditar_tls):
    receptor, mensaje, cliente, traza = enlace
    with ReceptorTLS(receptor, contexto(pki, receptor.nombre, True)) as canal:
        assert enviar_tls(canal.direccion, receptor.nombre, mensaje, contexto(pki, cliente))
        evento = auditar_tls(canal, 'ACEPTADO')
    assert evento['version'] == 'TLSv1.3' and evento['identidad'] == cliente
    assert evento['cifrado']
    assert len(traza) == 1
    assert traza[0]['conteo'] == 1


@pytest.mark.parametrize('ataque', ['sin_membresia', 'suplantacion', 'rol_incorrecto'])
def test_T08_rechaza_identidad_antes_de_registro(pki, enlace, ataque, auditar_tls):
    receptor, mensaje, cliente, traza = enlace
    if ataque == 'sin_membresia':
        identidad = 'H99' if cliente == 'H1' else 'S99'
        mensaje = replace(mensaje, **({'origen': 99} if cliente == 'H1' else {'servidor': 99}))
    elif ataque == 'suplantacion':
        identidad = 'H2' if cliente == 'H1' else 'S2'
    else:
        identidad = 'S1' if cliente == 'H1' else 'H1'
    with ReceptorTLS(receptor, contexto(pki, receptor.nombre, True)) as canal:
        assert not enviar_tls(canal.direccion, receptor.nombre, mensaje, contexto(pki, identidad))
        evento = auditar_tls(canal, 'NO_AUTORIZADO')
    assert evento['version'] == 'TLSv1.3' and evento['identidad'] == identidad
    sin_aportes(receptor, traza)
    assert traza == []  # el algoritmo ni siquiera recibe el mensaje no autorizado


@pytest.mark.parametrize('ataque', ['claro', 'certificado_ajeno', 'sin_certificado', 'tls12'])
def test_T09_rechaza_conexion_invalida(pki, enlace, ataque, auditar_tls):
    receptor, mensaje, cliente, traza = enlace
    with ReceptorTLS(receptor, contexto(pki, receptor.nombre, True)) as canal:
        if ataque == 'claro':
            with socket.create_connection(canal.direccion, timeout=3) as conexion:
                conexion.sendall(b'GET / HTTP/1.0\r\n\r\n')
                try:
                    assert conexion.recv(1024) != b'1'
                except ConnectionResetError:
                    pass
        else:
            nombre = None if ataque == 'sin_certificado' else cliente
            if ataque == 'certificado_ajeno':
                nombre = f'ajeno-{cliente}'
            ctx = contexto(pki, nombre)
            if ataque == 'tls12':
                ctx.minimum_version = ctx.maximum_version = ssl.TLSVersion.TLSv1_2
            with pytest.raises((ssl.SSLError, ConnectionError, ValueError)):
                enviar_tls(canal.direccion, receptor.nombre, mensaje, ctx)
        evento = auditar_tls(canal, 'TLS_RECHAZADO')
    assert evento['version'] == ''
    sin_aportes(receptor, traza)
    assert traza == []


@pytest.mark.parametrize('ataque', ['servidor_ajeno', 'nombre_incorrecto'])
def test_T09_cliente_valida_ca_y_nombre_del_receptor(pki, enlace, ataque, auditar_tls):
    receptor, mensaje, cliente, traza = enlace
    nombre = f'ajeno-{receptor.nombre}' if ataque == 'servidor_ajeno' else receptor.nombre
    destino = 'S2' if ataque == 'nombre_incorrecto' else receptor.nombre
    with ReceptorTLS(receptor, contexto(pki, nombre, True)) as canal:
        with pytest.raises(ssl.SSLCertVerificationError):
            enviar_tls(canal.direccion, destino, mensaje, contexto(pki, cliente))
        auditar_tls(canal, 'TLS_RECHAZADO')
    sin_aportes(receptor, traza)
    assert traza == []


@pytest.mark.parametrize('ataque', ['sid_anterior', 'destino_incorrecto', 'fuera_campo', 'bool', 'json_invalido'])
def test_T07_T08_guardas_tras_tls(pki, enlace, ataque, auditar_tls):
    receptor, mensaje, cliente, traza = enlace
    esperado = 'PROTOCOLO_RECHAZADO'
    if ataque == 'sid_anterior':
        mensaje = replace(mensaje, sid='cerrada')
    elif ataque == 'destino_incorrecto':
        mensaje = (replace(mensaje, destino=2) if cliente == 'H1'
                   else Share('tls', 1, 1, 15))
        esperado = 'NO_AUTORIZADO'
    elif ataque == 'fuera_campo':
        mensaje = replace(mensaje, valor=121)
    else:
        esperado = 'MENSAJE_RECHAZADO'
    with ReceptorTLS(receptor, contexto(pki, receptor.nombre, True)) as canal:
        if ataque in ('bool', 'json_invalido'):
            datos = (b'not-json' if ataque == 'json_invalido'
                     else json.dumps({'tipo': type(mensaje).__name__, **vars(mensaje), 'valor': True}).encode())
            with socket.create_connection(canal.direccion, timeout=3) as conexion:
                with contexto(pki, cliente).wrap_socket(conexion, server_hostname=receptor.nombre) as tls:
                    tls.sendall(len(datos).to_bytes(4, 'big') + datos)
                    assert tls.recv(1) == b''
        else:
            assert not enviar_tls(canal.direccion, receptor.nombre, mensaje, contexto(pki, cliente))
        auditar_tls(canal, esperado)
    sin_aportes(receptor, traza)


@pytest.mark.parametrize('par', [BASE, UMBRAL], ids=['BASE', 'UMBRAL'])
def test_T01_T16_datos_por_ambos_enlaces_tls(pki, par, auditar_tls):
    """Nueve Share y tres Parcial reales; Inicio/Listo/Acuse y salida son locales."""
    reloj = RelojManual()
    analista = Analista(par, reloj, lambda *args: True)
    sid = analista.abrir('nominal-tls')
    pendientes = {}  # un parcial por servidor, eliminado al entregarlo
    acuses = []
    hospitales = []

    def emitir_servidor(destino, mensaje):
        if isinstance(mensaje, Parcial):
            pendientes[mensaje.servidor] = mensaje
        elif isinstance(mensaje, Listo):
            analista.recibir(mensaje, f'S{mensaje.servidor}')
        elif isinstance(mensaje, Acuse):
            acuses.append(mensaje)
        return True

    servidores = {j: Servidor(j, par, reloj, emitir_servidor) for j in range(1, 4)}
    for servidor in servidores.values():
        servidor.recibir(Inicio(sid, par), 'A')
    with ExitStack() as pila:
        canales = {j: pila.enter_context(ReceptorTLS(s, contexto(pki, s.nombre, True)))
                   for j, s in servidores.items()}
        canal_a = pila.enter_context(ReceptorTLS(analista, contexto(pki, 'A', True)))
        for i, x in enumerate((10, 20, 30), 1):
            ctx = contexto(pki, f'H{i}')

            def emitir_hospital(destino, mensaje):
                assert isinstance(mensaje, Share)
                canal = canales[mensaje.destino]
                assert enviar_tls(canal.direccion, destino, mensaje, ctx)
                assert auditar_tls(canal, 'ACEPTADO')['version'] == 'TLSv1.3'
                return True

            hospital = Hospital(i, x, par, reloj, emitir_hospital)
            hospitales.append(hospital)
            hospital.recibir(Inicio(sid, par), 'A')
            # Acuses locales: el ensayo de datos no implementa un coordinador en red.
            for acuse in acuses:
                assert hospital.recibir(acuse, f'S{acuse.destino}')
            acuses.clear()
        assert set(pendientes) == {1, 2, 3}
        for j in range(1, 4):
            assert enviar_tls(canal_a.direccion, 'A', pendientes.pop(j), contexto(pki, f'S{j}'))
            assert auditar_tls(canal_a, 'ACEPTADO')['version'] == 'TLSv1.3'
    assert pendientes == {}
    reloj.avanzar(par.delta)
    for hospital in hospitales:
        hospital.vencer()
        assert hospital.sesiones[sid].estado == 'Cerrado'
        assert hospital.sesiones[sid].pendientes == {}
    assert [p.total for p in analista.publicaciones] == [60]
    assert not analista.avisos
    assert all(s.sesiones[sid].vista == {} for s in servidores.values())
