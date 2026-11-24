import argparse
import json

from .parametros import BASE, UMBRAL
from .simulacion import ejecutar


def main():
    parser = argparse.ArgumentParser(description="Caso sintético 10, 20 y 30 de E3")
    parser.add_argument("--perfil", choices=("BASE", "UMBRAL"), default="BASE")
    par = UMBRAL if parser.parse_args().perfil == "UMBRAL" else BASE
    simulacion, sid = ejecutar([10, 20, 30], par)
    print(json.dumps({"perfil": par.perfil, "sid": sid,
                      "estado": simulacion.analista.sesiones[sid].estado,
                      "totales": [p.total for p in simulacion.analista.publicaciones],
                      "avisos": [a.codigo for a in simulacion.analista.avisos],
                      "mensajes_entregados": dict(simulacion.entregados)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
