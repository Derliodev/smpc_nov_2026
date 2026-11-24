# Suma segura entre hospitales

Prototipo local en Python que calcula la suma de aportes de tres hospitales sin entregar sus entradas individuales al analista. Incluye el perfil **BASE**, que necesita los tres servidores, y **UMBRAL**, que reconstruye el total con dos de tres servidores mediante Shamir. La ejecución por consola usa los datos sintéticos `10`, `20` y `30` y devuelve `60`.

## Requisitos e instalación

- Python 3.13 y `pip`.
- Para la suite completa: el ejecutable `openssl` en `PATH` y permiso para usar puertos efímeros en `127.0.0.1`. Las pruebas crean certificados temporales y no necesitan conectarse a un servicio remoto.

Desde la raíz del proyecto:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

El protocolo usa la biblioteca estándar de Python. `requirements.txt` fija las dependencias de las pruebas; instalarlas requiere acceso al índice de paquetes o una copia local de esos paquetes.

## Ejecutar

```sh
.venv/bin/python -m suma_segura
.venv/bin/python -m suma_segura --perfil UMBRAL
```

El primer comando selecciona BASE por defecto. También se puede indicar `--perfil BASE`. La consola ejecuta una sesión completa con las entradas fijas `(10, 20, 30)`; no recibe datos clínicos ni otros valores por línea de comandos. Su salida es un objeto JSON con estos campos:

| Campo | Significado |
| --- | --- |
| `perfil` | Perfil seleccionado. |
| `sid` | Identificador nuevo de la sesión; cambia entre ejecuciones. |
| `estado` | Estado final del analista. |
| `totales` | Totales publicados; contiene `60` en el ejemplo nominal. |
| `avisos` | Códigos de advertencia o fallo; queda vacío en el ejemplo nominal. |
| `mensajes_entregados` | Cantidad de mensajes entregados, agrupados por tipo. |

Con los tres servidores disponibles, ambos perfiles terminan en `Completa`, publican un único total `60` y entregan 31 mensajes: 6 `Inicio`, 3 `Listo`, 9 `Share`, 9 `Acuse`, 3 `Parcial` y 1 `Publicacion`. La salida no incluye las participaciones privadas.

## Funcionamiento

Cada hospital valida su entero de entrada, crea participaciones aleatorias nuevas con `secrets` y envía una a cada servidor. Un servidor recibe una columna, acepta una participación por hospital y sesión, suma sus tres aportes y envía un parcial al analista. Este publica el total una sola vez cuando se cumple el umbral del perfil. Los identificadores de sesión, los duplicados, los orígenes y los vencimientos se comprueban antes de aceptar mensajes.

| Perfil | Hospitales | Servidores | Entrada por hospital | Módulo | Parciales necesarios |
| --- | ---: | ---: | --- | ---: | ---: |
| BASE | 3 | 3 | Entero entre 0 y 40 | 121 | 3 |
| UMBRAL | 3 | 3 | Entero entre 0 y 40 | 127 | 2 |

BASE divide cada entrada mediante suma modular y necesita los tres parciales. UMBRAL usa un polinomio de grado uno sobre el campo primo de módulo 127; cualquier par de parciales permite interpolar el total. Con los tres, el analista comprueba su consistencia antes de publicar. Si solo llegan dos, espera hasta el plazo `Δ` para publicar; con menos de dos termina como sesión incompleta. Dos parciales no permiten detectar un parcial alterado.

Los perfiles usan `T=10` y `Δ=20` unidades de un reloj manual. El simulador procesa los vencimientos intermedios en orden. La condición `p > n × M` evita que el total válido se reduzca por el módulo. La API permite otros tamaños BASE que cumplan las validaciones; el perfil UMBRAL está fijado a Shamir 2 de 3. La consola usa únicamente la configuración de tres hospitales y tres servidores de la tabla.

La ejecución de consola usa un transporte secuencial dentro del proceso y etiquetas locales de origen. El módulo `suma_segura/canal_tls.py` permite transportar mensajes `Share` y `Parcial` por TLS 1.3 mutuo en loopback; la suite comprueba certificados, identidades y autorización de origen y destino. Los mensajes de coordinación, los plazos y la publicación permanecen locales. Los cierres protegen las transiciones concurrentes dentro de un proceso; el proyecto no despliega hospitales y servidores en equipos separados ni conserva sesiones entre procesos.

## Pruebas y archivos producidos

```sh
.venv/bin/python -m pytest -v -rs
```

La suite comprueba ambos perfiles, límites y errores de entrada, plazos, pérdidas y duplicados, reconstrucción Shamir, TLS mutuo en loopback y recepción concurrente. Si falta `openssl` o el entorno impide usar loopback, las pruebas correspondientes fallan; no se reemplazan por simulaciones.

Para guardar un informe JUnit y trazas de la ejecución:

```sh
mkdir -p tmp/reproduccion
SMPC_EVIDENCIA=tmp/reproduccion/trazas.jsonl .venv/bin/python -m pytest -v -rs --junitxml=tmp/reproduccion/pytest.xml
```

`pytest.xml` contiene el resultado de las pruebas. `trazas.jsonl` registra eventos, identificadores sintéticos, estados, conteos, publicaciones y avisos; se añade al archivo existente si se repite el comando. La ejecución por consola solo escribe el JSON en la salida estándar. Los certificados de prueba se crean en un directorio temporal y se eliminan al finalizar la fixture.

El código está en `suma_segura/` y las pruebas en `tests/`. Los CSV de `docs/` forman parte de las comprobaciones automatizadas. Los archivos generados bajo `tmp/` están ignorados por Git.

## Alcance de la privacidad

El diseño supone servidores honestos pero curiosos y publicación fiel. En BASE, reunir las tres columnas permite recuperar cada entrada; en UMBRAL, dos servidores que colaboren pueden hacerlo. El total también puede revelar la entrada de un hospital si los demás conocen las suyas. Se valida el rango de los aportes, no la veracidad de su origen. Python no garantiza el borrado seguro de datos de memoria.
