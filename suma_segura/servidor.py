"""Servidor BASE/UMBRAL: suma una columna completa, con guardas de E3 §3.2."""

from dataclasses import dataclass, field

from .eventos import Entidad, atomico
from .mensajes import Acuse, Error, Inicio, Listo, Parcial, Share


@dataclass
class SesionServidor:
    vencimiento: float
    estado: str = "Recibiendo"
    vista: dict = field(default_factory=dict)
    parciales_emitidos: int = 0

    @property
    def k(self):
        return len(self.vista)


class Servidor(Entidad):
    def __init__(self, j, par, reloj, emitir, registrar=None):
        if type(j) is not int or not 1 <= j <= par.m:
            raise ValueError("índice de servidor inválido")
        super().__init__(f"S{j}", par, reloj, emitir, registrar)
        self.j = j
        self.sesiones = {}

    @atomico
    def recibir(self, mensaje, emisor):
        self.vencer()  # el plazo gana incluso si el mensaje llega exactamente en T
        if isinstance(mensaje, Inicio):
            if not self.inicio_valido(mensaje, emisor) or mensaje.sid in self.sesiones:
                self.evento(mensaje.sid, "InicioDescartado", "SinCambio")
                return False
            self.sesiones[mensaje.sid] = SesionServidor(self.reloj() + self.par.T)
            self.evento(mensaje.sid, "InicioAceptado", "Recibiendo")
            self.emitir("A", Listo(mensaje.sid, self.j))
            return True
        if not isinstance(mensaje, Share):
            return False
        s = self.sesiones.get(mensaje.sid)
        if (s is None or s.estado != "Recibiendo" or type(mensaje.destino) is not int
                or mensaje.destino != self.j or type(mensaje.origen) is not int
                or not 1 <= mensaje.origen <= self.par.n or emisor != f"H{mensaje.origen}"):
            self.evento(mensaje.sid, "ShareDescartado", s.estado if s else "Inactivo", "RUTA_O_SESION")
            return False
        if type(mensaje.valor) is not int or not 0 <= mensaje.valor < self.par.p:
            self.evento(mensaje.sid, "ShareDescartado", s.estado, "SHARE_FUERA_DE_ZP", s.k)
            self.emitir("A", Error(mensaje.sid, self.nombre, "SHARE_FUERA_DE_ZP"))
            return False
        clave = (mensaje.sid, mensaje.origen)
        if clave in s.vista:
            self.evento(mensaje.sid, "ShareDescartado", s.estado, "DUPLICADO", s.k, emisor)
            return False
        # Guarda e inserción pertenecen a una única transición bajo el cerrojo.
        s.vista[clave] = mensaje.valor
        self.evento(mensaje.sid, "ShareAceptado", s.estado, conteo=s.k, origen=emisor)
        self.emitir(emisor, Acuse(mensaje.sid, mensaje.origen, self.j))
        if s.k == self.par.n:
            s.estado = "Agregando"
            self._agregar(mensaje.sid, s)
        return True

    def _agregar(self, sid, s):
        if self.reloj() >= s.vencimiento:
            self._abortar(sid, s, "TIEMPO_EMISION")
            return
        z = sum(s.vista.values()) % self.par.p
        if self.reloj() >= s.vencimiento:
            self._abortar(sid, s, "TIEMPO_EMISION")
            return
        # Cerrar antes del callback evita una segunda emisión por reentrada local.
        s.estado = "Enviado"
        s.vista.clear()
        if self.emitir("A", Parcial(sid, self.j, z)):
            s.parciales_emitidos = 1
            self.evento(sid, "ParcialEmitido", s.estado, conteo=1)
        else:
            self._abortar(sid, s, "TIEMPO_EMISION")

    def _abortar(self, sid, s, codigo):
        s.estado = "Abortado"
        s.vista.clear()
        self.evento(sid, "Aborto", s.estado, codigo)
        self.emitir("A", Error(sid, self.nombre, codigo))

    @atomico
    def vencer(self):
        for sid, s in self.sesiones.items():
            if s.estado in ("Recibiendo", "Agregando") and self.reloj() >= s.vencimiento:
                self._abortar(sid, s, "TIEMPO_SHARES" if s.estado == "Recibiendo" else "TIEMPO_EMISION")
