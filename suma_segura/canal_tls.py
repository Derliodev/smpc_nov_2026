"""Canal local mínimo de datos H→S y S→A, con TLS 1.3 mutuo.

La identidad procede del SAN del certificado validado por la CA del ensayo.
La membresía y el rol se contrastan con los parámetros públicos del receptor.
Solo transporta Share y Parcial; el control del simulador sigue siendo local.
No registra valores privados ni proporciona una infraestructura desplegable.
"""

from dataclasses import asdict
import json
from queue import Queue
import socket
import socketserver
import ssl
from threading import Thread

from .mensajes import Parcial, Share


LIMITE = 4096


def contexto_tls(ca, certificado=None, clave=None, *, servidor=False):
    contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER if servidor else ssl.PROTOCOL_TLS_CLIENT)
    contexto.minimum_version = ssl.TLSVersion.TLSv1_3
    contexto.maximum_version = ssl.TLSVersion.TLSv1_3
    contexto.verify_mode = ssl.CERT_REQUIRED
    contexto.verify_flags |= ssl.VERIFY_X509_STRICT
    contexto.load_verify_locations(cafile=str(ca))
    if not servidor:
        contexto.hostname_checks_common_name = False
    if certificado is not None:
        contexto.load_cert_chain(str(certificado), str(clave))
    return contexto


def _leer(socket_tls, cantidad):
    datos = bytearray()
    while len(datos) < cantidad:
        bloque = socket_tls.recv(cantidad - len(datos))
        if not bloque:
            raise ValueError("mensaje truncado")
        datos.extend(bloque)
    return bytes(datos)


def _codificar(mensaje):
    if type(mensaje) not in (Share, Parcial):
        raise ValueError("el canal de datos solo admite Share y Parcial")
    datos = json.dumps({"tipo": type(mensaje).__name__, **asdict(mensaje)},
                       separators=(",", ":")).encode("utf-8")
    if len(datos) > LIMITE:
        raise ValueError("mensaje demasiado grande")
    return len(datos).to_bytes(4, "big") + datos


def _decodificar(conexion):
    cantidad = int.from_bytes(_leer(conexion, 4), "big")
    if not 0 < cantidad <= LIMITE:
        raise ValueError("longitud inválida")
    datos = json.loads(_leer(conexion, cantidad))
    if type(datos) is not dict:
        raise ValueError("mensaje inválido")
    tipo = datos.pop("tipo", None)
    clases = {"Share": Share, "Parcial": Parcial}
    if type(tipo) is not str or tipo not in clases:
        raise ValueError("tipo inválido")
    clase = clases[tipo]
    if set(datos) != set(clase.__dataclass_fields__):
        raise ValueError("campos inválidos")
    if type(datos['sid']) is not str or not datos['sid']:
        raise ValueError("sid inválido")
    if any(type(v) is not int for k, v in datos.items() if k != 'sid'):
        raise ValueError("se requieren enteros estrictos")
    return clase(**datos)


def _autorizado(identidad, receptor, mensaje):
    par = receptor.par
    if type(mensaje) is Share:
        return (identidad in {f"H{i}" for i in range(1, par.n + 1)}
                and identidad == f"H{mensaje.origen}"
                and receptor.nombre == f"S{mensaje.destino}"
                and 1 <= mensaje.destino <= par.m)
    return (identidad in {f"S{j}" for j in range(1, par.m + 1)}
            and identidad == f"S{mensaje.servidor}" and receptor.nombre == "A")


class _Servidor(socketserver.ThreadingTCPServer):
    # No se dejan hilos vivos al terminar el contexto del ensayo.
    daemon_threads = False
    block_on_close = True


class ReceptorTLS:
    """Un puerto efímero de loopback, con un hilo por conexión y auditoría mínima.

    El receptor del protocolo serializa sus transiciones. Sus callbacks deben
    terminar sin esperar una devolución por red al mismo ejecutor bloqueado.
    """
    def __init__(self, receptor, contexto):
        self.receptor = receptor
        self.contexto = contexto
        self.eventos = Queue()
        canal = self

        class Manejador(socketserver.BaseRequestHandler):
            def handle(self):
                canal._atender(self.request)

        self.servidor = _Servidor(("127.0.0.1", 0), Manejador)
        self.direccion = self.servidor.server_address
        self.hilo = Thread(target=self.servidor.serve_forever,
                           kwargs={"poll_interval": 0.05}, name="receptor-tls")

    def __enter__(self):
        self.hilo.start()
        return self

    def __exit__(self, *args):
        self.servidor.shutdown()
        self.servidor.server_close()
        self.hilo.join(timeout=5)
        if self.hilo.is_alive():
            raise RuntimeError("el receptor TLS no terminó")

    def _atender(self, conexion):
        evento = {"resultado": "TLS_RECHAZADO", "identidad": "", "version": "", "cifrado": ""}
        conexion.settimeout(3)
        try:
            with self.contexto.wrap_socket(conexion, server_side=True) as tls:
                evento['version'] = tls.version()
                evento['cifrado'] = tls.cipher()[0]
                nombres = tls.getpeercert().get('subjectAltName', ())
                identidad = nombres[0][1] if len(nombres) == 1 and nombres[0][0] == 'DNS' else ''
                evento['identidad'] = identidad
                evento['resultado'] = 'MENSAJE_RECHAZADO'
                mensaje = _decodificar(tls)
                if not _autorizado(identidad, self.receptor, mensaje):
                    evento['resultado'] = 'NO_AUTORIZADO'
                    tls.sendall(b'0')
                    return
                aceptado = self.receptor.recibir(mensaje, identidad)
                evento['resultado'] = 'ACEPTADO' if aceptado else 'PROTOCOLO_RECHAZADO'
                tls.sendall(b'1' if aceptado else b'0')
        except (OSError, ValueError):
            # No se guardan cuerpos ni excepciones que puedan contener datos.
            pass
        finally:
            self.eventos.put(evento)


def enviar_tls(direccion, destino, mensaje, contexto):
    """Comprueba cadena y SAN del destino; devuelve aceptación del receptor."""
    datos = _codificar(mensaje)
    with socket.create_connection(direccion, timeout=3) as conexion:
        with contexto.wrap_socket(conexion, server_hostname=destino) as tls:
            tls.sendall(datos)
            return _leer(tls, 1) == b'1'
