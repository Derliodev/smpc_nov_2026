"""Transporte local secuencial; adaptación del listado 4.6, sin TLS ni red.

Las etiquetas de origen permiten probar guardas, no autentican identidades.
El filtro sirve para ensayos de pérdidas; no se guardan mensajes de datos.
"""

from collections import Counter
from math import isfinite

from .analista import Analista
from .eventos import RelojManual, atomico
from threading import RLock
from .hospital import Hospital
from .parametros import BASE
from .servidor import Servidor


class Simulacion:
    def __init__(self, entradas, par=BASE, filtro=None, registrar=True):
        par.validar()
        if len(entradas) != par.n:
            raise ValueError("debe haber exactamente una entrada por hospital")
        self.reloj = RelojManual()
        self.traza = []
        self.intentos, self.entregados = Counter(), Counter()
        self.filtro = filtro
        self.caidos = set()
        self.salidas = []
        observador = self.traza.append if registrar else None
        emisor = lambda origen: lambda destino, mensaje: self._enviar(origen, destino, mensaje)
        self.hospitales = {i: Hospital(i, x, par, self.reloj, emisor(f"H{i}"), observador)
                           for i, x in enumerate(entradas, 1)}
        self.servidores = {j: Servidor(j, par, self.reloj, emisor(f"S{j}"), observador)
                           for j in range(1, par.m + 1)}
        self.analista = Analista(par, self.reloj, emisor("A"), observador)
        # Los callbacks síncronos forman un único ejecutor local reentrante.
        # Compartir el cerrojo evita invertir el orden de cerrojos entre entidades.
        self.cerrojo = RLock()
        for entidad in [self.analista, *self.hospitales.values(), *self.servidores.values()]:
            entidad.cerrojo = self.cerrojo

    @atomico
    def _enviar(self, origen, destino, mensaje):
        tipo = type(mensaje).__name__
        self.intentos[tipo] += 1
        if destino in self.caidos or origen in self.caidos:
            return False
        if self.filtro is not None and not self.filtro(origen, destino, mensaje):
            return False
        self.entregados[tipo] += 1
        if destino == "D":
            self.salidas.append(mensaje)  # solo salida autorizada, nunca shares
        elif destino == "A":
            self.analista.recibir(mensaje, origen)
        elif destino.startswith("H"):
            self.hospitales[int(destino[1:])].recibir(mensaje, origen)
        else:
            self.servidores[int(destino[1:])].recibir(mensaje, origen)
        return True  # entrega de transporte distinta de aceptación por el receptor

    def iniciar(self, sid=None):
        return self.analista.abrir(sid)

    @atomico
    def avanzar(self, incremento):
        if (type(incremento) not in (int, float) or not isfinite(incremento)
                or incremento < 0 or not isfinite(self.reloj() + incremento)):
            raise ValueError("el reloj solo admite incrementos finitos no negativos")
        objetivo = self.reloj() + incremento
        # Procesar los plazos intermedios, sin saltarse T al avanzar hasta Δ.
        while True:
            plazos = [s.vencimiento for s in self.analista.sesiones.values()
                      if s.estado not in ("Completa", "Incompleta")]
            plazos += [s.vencimiento for j, srv in self.servidores.items()
                       if f"S{j}" not in self.caidos for s in srv.sesiones.values()
                       if s.estado in ("Recibiendo", "Agregando")]
            plazos += [s.vencimiento for h in self.hospitales.values() for s in h.sesiones.values()
                       if s.estado in ("Enviando", "EsperandoAcuses")]
            if not plazos or min(plazos) > objetivo:
                break
            self.reloj.avanzar(max(0, min(plazos) - self.reloj()))
            self._vencer_todos()
        self.reloj.avanzar(max(0, objetivo - self.reloj()))
        self._vencer_todos()

    def _vencer_todos(self):
        # Si varios plazos coinciden, todos vencen antes del próximo mensaje.
        self.analista.vencer()
        for j, srv in self.servidores.items():
            if f"S{j}" not in self.caidos:
                srv.vencer()
        for hospital in self.hospitales.values():
            hospital.vencer()


def ejecutar(entradas, par=BASE):
    simulacion = Simulacion(entradas, par)
    sid = simulacion.iniciar()
    simulacion.avanzar(par.delta)
    return simulacion, sid
