"""Hospital BASE/UMBRAL. Listados 4.3 y 4.8; ciclos de E3 §§3.1 y 3.4."""

from dataclasses import dataclass, field
import secrets

from .eventos import Entidad, atomico
from .mensajes import Acuse, Error, Inicio, Share
from .shamir import compartir_shamir


def compartir(x: int, m: int, p: int) -> list[int]:
    """Núcleo aditivo en Zp; el rango clínico se valida en Hospital."""
    if (any(type(v) is not int for v in (x, m, p)) or m < 2 or p < 2
            or not 0 <= x < p):
        raise ValueError("reparto requiere enteros, m>=2, p>=2 y x en Zp")
    shares = [secrets.randbelow(p) for _ in range(m - 1)]
    shares.append((x - sum(shares)) % p)
    return shares


@dataclass
class SesionHospital:
    vencimiento: float
    estado: str = "Enviando"
    pendientes: dict = field(default_factory=dict)
    acuses: set = field(default_factory=set)


class Hospital(Entidad):
    def __init__(self, i, x, par, reloj, emitir, registrar=None):
        if type(i) is not int or not 1 <= i <= par.n:
            raise ValueError("índice de hospital inválido")
        super().__init__(f"H{i}", par, reloj, emitir, registrar)
        self.i, self._x = i, x
        self.sesiones = {}

    @atomico
    def recibir(self, mensaje, emisor):
        self.vencer()
        if isinstance(mensaje, Inicio):
            if (emisor != "A" or type(mensaje.sid) is not str or not mensaje.sid
                    or mensaje.sid in self.sesiones):
                self.evento(mensaje.sid, "InicioDescartado", "SinCambio")
                return False
            sid = mensaje.sid
            sesion = SesionHospital(self.reloj() + self.par.delta)
            self.sesiones[sid] = sesion  # reserva antes de generar o emitir
            if not self.inicio_valido(mensaje, emisor):
                sesion.estado = "Abortado"
                self.evento(sid, "InicioRechazado", sesion.estado, "PARAMETROS_INVALIDOS")
                self.emitir("A", Error(sid, self.nombre, "PARAMETROS_INVALIDOS"))
                return False
            if type(self._x) is not int or not 0 <= self._x <= self.par.M:
                sesion.estado = "Abortado"
                self.evento(sid, "EntradaRechazada", sesion.estado, "ENTRADA_INVALIDA")
                self.emitir("A", Error(sid, self.nombre, "ENTRADA_INVALIDA"))
                return False
            valores = (compartir_shamir(self._x, self.par.p) if self.par.perfil == "UMBRAL"
                       else compartir(self._x, self.par.m, self.par.p))
            sesion.pendientes = dict(enumerate(valores, 1))
            self.evento(sid, "InicioAceptado", sesion.estado)
            for j in range(1, self.par.m + 1):
                if self.reloj() >= sesion.vencimiento:
                    self.vencer()
                    break
                # Un destino caído no impide intentar los restantes.
                self.emitir(f"S{j}", Share(sid, self.i, j, sesion.pendientes[j]))
            if sesion.estado == "Enviando":
                sesion.estado = "EsperandoAcuses"
            return True
        if isinstance(mensaje, Acuse):
            s = self.sesiones.get(mensaje.sid)
            if (s is None or s.estado not in ("Enviando", "EsperandoAcuses")
                    or type(mensaje.origen) is not int or mensaje.origen != self.i
                    or type(mensaje.destino) is not int or not 1 <= mensaje.destino <= self.par.m
                    or emisor != f"S{mensaje.destino}" or mensaje.destino in s.acuses):
                return False
            s.acuses.add(mensaje.destino)
            s.pendientes.pop(mensaje.destino, None)
            self.evento(mensaje.sid, "AcuseAceptado", s.estado, conteo=len(s.acuses))
            if self.par.perfil == "BASE" and len(s.acuses) == self.par.m:
                s.estado = "Cerrado"
                s.pendientes.clear()
                self.evento(mensaje.sid, "Cierre", s.estado)
            return True
        return False

    @atomico
    def vencer(self):
        for sid, s in self.sesiones.items():
            if s.estado in ("Enviando", "EsperandoAcuses") and self.reloj() >= s.vencimiento:
                suficientes = self.par.perfil == "UMBRAL" and len(s.acuses) >= self.par.umbral
                s.estado = "Cerrado" if suficientes else "Abortado"
                s.pendientes.clear()
                self.evento(sid, "Vencimiento", s.estado,
                            "" if suficientes else "FALTAN_ACUSES", len(s.acuses))
