from dataclasses import dataclass, field
import secrets

from .eventos import Entidad, atomico
from .mensajes import AvisoIncompleta, Error, Inicio, Listo, Parcial, Publicacion
from .shamir import reconstruir_par, residuo_consistencia


@dataclass
class SesionAnalista:
    vencimiento: float
    estado: str = "EsperandoListos"
    listos: set = field(default_factory=set)
    parciales: dict = field(default_factory=dict)
    iniciando: bool = True


class Analista(Entidad):
    def __init__(self, par, reloj, emitir, registrar=None):
        super().__init__("A", par, reloj, emitir, registrar)
        self.sesiones = {}
        self.publicaciones = []
        self.avisos = []

    @atomico
    def abrir(self, sid=None):
        self.vencer()
        sid = secrets.token_hex(16) if sid is None else sid
        if type(sid) is not str or not sid or sid in self.sesiones:
            raise ValueError("sid vacío, inválido o ya utilizado")
        self.par.validar()
        self.sesiones[sid] = SesionAnalista(self.reloj() + self.par.delta)
        self.evento(sid, "Apertura", "EsperandoListos")
        for j in range(1, self.par.m + 1):
            self.vencer()
            if self.sesiones[sid].estado in ("Completa", "Incompleta"):
                break
            self.emitir(f"S{j}", Inicio(sid, self.par))
        s = self.sesiones[sid]
        s.iniciando = False
        self._habilitar_hospitales(sid, s)
        return sid

    def _habilitar_hospitales(self, sid, s):
        # En el transporte síncrono, enviar antes los tres Inicio evita que el
        # segundo Listo dispare shares hacia S3 antes de iniciar ese servidor.
        if s.iniciando or s.estado != "EsperandoListos" or len(s.listos) < self.par.umbral:
            return
        self.vencer()
        if s.estado != "EsperandoListos":
            return
        s.estado = "EsperandoParciales"
        for i in range(1, self.par.n + 1):
            self.vencer()
            if s.estado != "EsperandoParciales":
                break
            self.emitir(f"H{i}", Inicio(sid, self.par))

    @atomico
    def recibir(self, mensaje, emisor):
        self.vencer()
        s = self.sesiones.get(getattr(mensaje, "sid", None))
        if s is None or s.estado in ("Completa", "Incompleta"):
            self.evento(getattr(mensaje, "sid", ""), "MensajeDescartado", s.estado if s else "Inactivo")
            return False
        sid = mensaje.sid
        if isinstance(mensaje, Listo):
            if (s.estado not in ("EsperandoListos", "EsperandoParciales")
                    or type(mensaje.servidor) is not int
                    or not 1 <= mensaje.servidor <= self.par.m or emisor != f"S{mensaje.servidor}"
                    or mensaje.servidor in s.listos):
                return False
            s.listos.add(mensaje.servidor)
            self.evento(sid, "ListoAceptado", s.estado, conteo=len(s.listos))
            self._habilitar_hospitales(sid, s)
            return True
        if isinstance(mensaje, Error):
            if emisor != mensaje.emisor:
                return False
            hospital = emisor in {f"H{i}" for i in range(1, self.par.n + 1)}
            servidor = emisor in {f"S{j}" for j in range(1, self.par.m + 1)}
            if servidor and mensaje.codigo == "SHARE_FUERA_DE_ZP":
                self.evento(sid, "Advertencia", s.estado, mensaje.codigo)
                return True
            if ((hospital and mensaje.codigo in ("ENTRADA_INVALIDA", "PARAMETROS_INVALIDOS"))
                    or (servidor and mensaje.codigo in ("TIEMPO_SHARES", "TIEMPO_EMISION"))):
                if self.par.perfil == "UMBRAL" and servidor:
                    self.evento(sid, "ServidorAusente", s.estado, mensaje.codigo, origen=emisor)
                    return True
                self._incompleta(sid, s, mensaje.codigo)
                return True
            return False
        if isinstance(mensaje, Parcial):
            if (s.estado != "EsperandoParciales" or type(mensaje.servidor) is not int
                    or not 1 <= mensaje.servidor <= self.par.m or emisor != f"S{mensaje.servidor}"
                    or type(mensaje.valor) is not int or not 0 <= mensaje.valor < self.par.p
                    or mensaje.servidor in s.parciales):
                self.evento(sid, "ParcialDescartado", s.estado)
                return False
            s.parciales[mensaje.servidor] = mensaje.valor
            self.evento(sid, "ParcialAceptado", s.estado, conteo=len(s.parciales), origen=emisor)
            if len(s.parciales) == self.par.m:
                if self.reloj() >= s.vencimiento:
                    self._incompleta(sid, s, "PLAZO")
                else:
                    self._completar(sid, s)
            return True
        return False

    def _completar(self, sid, s):
        if self.par.perfil == "UMBRAL":
            if len(s.parciales) == 3 and residuo_consistencia(
                    s.parciales[1], s.parciales[2], s.parciales[3], self.par.p) != 0:
                self._incompleta(sid, s, "PARCIALES_INCONSISTENTES")
                return
            u, v = sorted(s.parciales)[:2]
            total = reconstruir_par(u, s.parciales[u], v, s.parciales[v], self.par.p)
        else:
            total = sum(s.parciales.values()) % self.par.p
        s.estado = "Completa"
        s.parciales.clear()
        salida = Publicacion(sid, total)
        self.publicaciones.append(salida)
        self.evento(sid, "Publicacion", s.estado)
        self.emitir("D", salida)

    def _incompleta(self, sid, s, codigo):
        if s.estado in ("Completa", "Incompleta"):
            return
        s.estado = "Incompleta"
        s.parciales.clear()
        aviso = AvisoIncompleta(sid, codigo)
        self.avisos.append(aviso)
        self.evento(sid, "AvisoIncompleta", s.estado, codigo)
        self.emitir("D", aviso)

    @atomico
    def vencer(self):
        for sid, s in self.sesiones.items():
            if s.estado not in ("Completa", "Incompleta") and self.reloj() >= s.vencimiento:
                if (self.par.perfil == "UMBRAL" and s.estado == "EsperandoParciales"
                        and len(s.parciales) >= self.par.umbral):
                    self._completar(sid, s)
                    continue
                codigo = "FALTAN_LISTO" if s.estado == "EsperandoListos" else "FALTAN_PARCIALES"
                self._incompleta(sid, s, codigo)
