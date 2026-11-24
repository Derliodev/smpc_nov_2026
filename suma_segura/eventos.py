"""Reloj de ensayo y trazas sin entradas, shares ni parciales."""

from math import isfinite
from functools import wraps
from threading import RLock


def atomico(metodo):
    """Serializa cada transición, incluidas guardas, inserción y cierre."""
    @wraps(metodo)
    def protegido(self, *args, **kwargs):
        with self.cerrojo:
            return metodo(self, *args, **kwargs)
    return protegido


class RelojManual:
    def __init__(self):
        self._tiempo = 0.0

    def __call__(self):
        return self._tiempo

    def avanzar(self, incremento):
        if (type(incremento) not in (int, float) or not isfinite(incremento)
                or incremento < 0 or not isfinite(self._tiempo + incremento)):
            raise ValueError("el reloj solo admite incrementos finitos no negativos")
        self._tiempo += incremento


class Entidad:
    def __init__(self, nombre, par, reloj, emitir, registrar=None):
        par.validar()
        self.nombre, self.par, self.reloj = nombre, par, reloj
        self.emitir, self.registrar = emitir, registrar
        self.cerrojo = RLock()

    def evento(self, sid, evento, estado, codigo="", conteo=0, origen=""):
        if self.registrar is not None:
            self.registrar({"tiempo": self.reloj(), "sid": sid, "actor": self.nombre,
                            "evento": evento, "estado": estado, "codigo": codigo,
                            "conteo": conteo, "origen": origen})

    def inicio_valido(self, mensaje, emisor):
        return (emisor == "A" and type(mensaje.sid) is str and bool(mensaje.sid)
                and type(mensaje.cfg) is type(self.par) and mensaje.cfg == self.par)
