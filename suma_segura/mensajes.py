"""Mensajes inmutables F01–F08 de E2; adaptación del listado 4.2 de clase."""

from dataclasses import dataclass

from .parametros import Parametros


@dataclass(frozen=True)
class Inicio:
    sid: str
    cfg: Parametros


@dataclass(frozen=True)
class Share:
    sid: str
    origen: int
    destino: int
    valor: int


@dataclass(frozen=True)
class Parcial:
    sid: str
    servidor: int
    valor: int


@dataclass(frozen=True)
class Listo:
    sid: str
    servidor: int


@dataclass(frozen=True)
class Acuse:
    sid: str
    origen: int
    destino: int


@dataclass(frozen=True)
class Error:
    sid: str
    emisor: str
    codigo: str


@dataclass(frozen=True)
class Publicacion:
    sid: str
    total: int


@dataclass(frozen=True)
class AvisoIncompleta:
    sid: str
    codigo: str
