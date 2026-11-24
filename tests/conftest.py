"""Evidencia opcional de ensayos: metadatos y resultados públicos únicamente."""

import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

import pytest

from suma_segura.simulacion import Simulacion


@pytest.fixture
def sistema(request):
    creados = []

    def crear(entradas=(10, 20, 30), **kwargs):
        sim = Simulacion(entradas, **kwargs)
        creados.append(sim)
        return sim

    yield crear
    destino = os.environ.get("SMPC_EVIDENCIA")
    if destino:
        with Path(destino).open("a", encoding="utf-8") as archivo:
            for sim in creados:
                archivo.write(json.dumps({
                    "prueba": request.node.nodeid, "traza": sim.traza,
                    "intentos": dict(sim.intentos), "entregados": dict(sim.entregados),
                    "publicaciones": [vars(p) for p in sim.analista.publicaciones],
                    "avisos": [vars(a) for a in sim.analista.avisos],
                }, ensure_ascii=False) + "\n")


@pytest.fixture(scope="session")
def pki():
    """CA y certificados efímeros: no se versionan ni se incluyen en evidencia."""
    openssl = shutil.which("openssl")
    assert openssl, "T08/T09 requieren el ejecutable openssl; no se omiten las pruebas"
    with TemporaryDirectory(prefix="emi311-pki-") as carpeta:
        raiz = Path(carpeta)

        def ejecutar(*args):
            subprocess.run([openssl, *map(str, args)], check=True,
                           capture_output=True, timeout=30)

        for ca in ("ca", "ajena"):
            ejecutar("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
                     "-subj", f"/CN=EMI311-{ca}", "-keyout", raiz/f"{ca}.key",
                     "-out", raiz/f"{ca}.crt", "-addext", "basicConstraints=critical,CA:TRUE",
                     "-addext", "keyUsage=critical,keyCertSign,cRLSign",
                     "-addext", "subjectKeyIdentifier=hash")
            (raiz/f"{ca}.key").chmod(0o600)
        nombres = ("H1", "H2", "H3", "H99", "S1", "S2", "S3", "S99", "A")
        for etiqueta, identidad, ca in [(n, n, 'ca') for n in nombres] + [
                ('ajeno-H1', 'H1', 'ajena'), ('ajeno-S1', 'S1', 'ajena'), ('ajeno-A', 'A', 'ajena')]:
            ejecutar("req", "-new", "-newkey", "rsa:2048", "-nodes", "-subj", f"/CN={identidad}",
                     "-keyout", raiz/f"{etiqueta}.key", "-out", raiz/f"{etiqueta}.csr")
            (raiz/f"{etiqueta}.key").chmod(0o600)
            ext = raiz/f"{etiqueta}.ext"
            ext.write_text("basicConstraints=critical,CA:FALSE\n"
                           "keyUsage=critical,digitalSignature,keyEncipherment\n"
                           "extendedKeyUsage=clientAuth,serverAuth\n"
                           f"subjectAltName=DNS:{identidad}\nsubjectKeyIdentifier=hash\n"
                           "authorityKeyIdentifier=keyid:always\n")
            ejecutar("x509", "-req", "-in", raiz/f"{etiqueta}.csr", "-CA", raiz/f"{ca}.crt",
                     "-CAkey", raiz/f"{ca}.key", "-CAcreateserial", "-days", "1",
                     "-extfile", ext, "-out", raiz/f"{etiqueta}.crt")
        yield raiz


@pytest.fixture
def auditar_tls(request):
    """Guarda solo el resultado del canal, identidad pública y TLS negociado."""
    def observar(canal, esperado):
        evento = canal.eventos.get(timeout=5)
        request.node.user_properties.append(("canal_tls", json.dumps(evento, ensure_ascii=False)))
        assert evento['resultado'] == esperado
        return evento
    return observar
