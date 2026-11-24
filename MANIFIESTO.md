# Entregable 4 EMI311 — manifiesto de entrega

El paquete contiene BASE y Shamir 2 de 3, código Python, pruebas, dependencias,
README, tabla T01–T18, matriz de trazabilidad, informe de cinco páginas y
registros de las etapas 1–6. Los intentos fallidos históricos permanecen en
`evidencias/etapa_2/` y `evidencias/etapa_4/`.

## Reproducción

Desde la carpeta extraída, con Python 3.13, OpenSSL y permiso para puertos
locales en 127.0.0.1:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -v -rs
.venv/bin/python -m suma_segura --perfil BASE
.venv/bin/python -m suma_segura --perfil UMBRAL
```

El resultado registrado en etapa 5 fue 165 pruebas aprobadas, 0 fallos y 0
omisiones. Las entradas 10, 20 y 30 produjeron 60 en ambos perfiles. La
instalación necesita acceso al índice de paquetes. El código usa biblioteca
estándar; `requirements.txt` fija las dependencias de pytest.

Las evidencias están en `evidencias/` y los hash SHA-256 de cada archivo en 
`SHA256SUMS.txt`. Las fuentes académicas citadas fueron
proporcionadas para el trabajo y no son requisitos de ejecución. No se incluyen
certificados ni claves privadas. El canal TLS cubre mensajes de datos en
loopback; la coordinación del ejemplo permanece local.
