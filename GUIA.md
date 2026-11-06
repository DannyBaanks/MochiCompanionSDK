# GUIA.md — cómo manejar `mochic` (Mochi ⇄ Companion)

Guía de operador. Todo lo que está acá fue **ejecutado** en esta máquina el
2026-11-06; las salidas son texto real copiados de
`evidence/cli_v0/stdout.raw.txt` (26 bloques, por `tools/capture_cli.py`),
`evidence/refusals_v0/stdout.raw.txt` (12 comandos + 1 sonda, por
`tools/capture_refusals.py`), `evidence/foreign_startup_v0/stdout.raw.txt` (por
`tools/capture_foreign.py`), `evidence/startup_write_v0/stdout.raw.txt` y
`evidence/boot_play_v0/stdout.raw.txt` (los dos últimos se corren a mano porque
el primero **escribe el dispositivo**), no ejemplos inventados. Cada pack trae su
`VERDICT.md` con hipótesis, controles y tabla de claims. Los tres capturers son
deterministas y niegan pisar un crudo ya sellado.

Ruta del repo: `~/Development/ISyCo Git/MochiCompanionSDK`. Todos los comandos
se corren desde ahí, con `./mochic`.

---

## 1. El comando por el que viniste

Generar un AVI que el Mochi sabe reproducir, a partir de un pack de Companion:

```
$ mochic build examples/demo-thinking.json
[exit 0]
{
 "animacion": "thinking",
 "budget_por_frame": 24000,
 "bytes_avi": 1594526,
 "duracion_s": 2.0,
 "frame_bytes": { "max": 23543, "min": 22419, "total": 1389572 },
 "frames": 60,
 "jpeg_quality": { "max": 93, "mediana": 92, "min": 91 },
 "nombre_video_destino": "Squint.avi",
 "origen": ".../Companion/packs/malbolge-cat/malbolgato-thinking.gif",
 "ruta": "build/demo-thinking.avi",
 "sha256": "77a9df099345f584edfb1c6f31d9972b19d617bd11fe9b0885e006486eef6601",
 "siguiente_paso": "mochic plan VOLUMEN examples/demo-thinking.json",
 "spec_id": "demo-thinking",
 "validacion": { "duros": 0, "suaves": 1, "valido": true, "hallazgos": [...] }
}
```

Eso **no toca el dispositivo**: escribe `build/demo-thinking.avi` y lo valida
contra el perfil medido de los 62 videos factory.

---

## 2. La regla de oro

> **Nada escribe en el Mochi sin un plan y su token.**

`build`, `watch`, `plan`, `playlist`, `inspect`, `validate`, `profile`, `map`,
`emit` y `rollback` son de solo lectura respecto del volumen. La única
excepción es `mochic apply`, que exige el `--token` que devolvió `plan`, hace
copia verificada **fuera** del volumen y deja un journal para revertir.

Y una segunda, igual de importante:

> Que el firmware reproduzca un archivo generado **todavía no está demostrado**.

Nadie ha metido un AVI propio en la tarjeta. Todo lo que este SDK garantiza es
que el contenedor es estructuralmente idéntico a los que el dispositivo ya
reproduce. Si el Mochi lo acepta, eso se comprueba en el dispositivo, no acá.

---

## 3. Comandos, uno por uno (salidas reales)

### 3.1 `version` — qué SDK y qué perfil se está usando

```
$ mochic version
[exit 0]
{
 "codigos_salida": { "0": "OK", "1": "hallazgo duro", "2": "uso",
                     "3": "entrada ilegible", "4": "token no coincide",
                     "5": "operacion no demostrada" },
 "perfil": ".../profiles/mochi-factory-v1.json",
 "perfil_sha256": "e3ef250444f57706c59f044126800db304f92e1c2c9146ba8488f15f33aff21e",
 "puente": "mochi-bridge-v1",
 "sdk": "mochisdk", "spec": "mochi-anim-v1", "version": "0.1.0"
}
```

Si `perfil_sha256` cambia, cambió la medida del corpus: no des por cierto
ningún número de este archivo sin volver a medir.

### 3.2 `profile --control` — el control positivo del validator

```
$ mochic profile --control
[exit 0]
{
 "control_positivo": {
  "archivos": 62, "esperado": 0, "lista_rechazados": [],
  "motivo": "un asset factory rechazado implica regla mala, no asset malo",
  "veredicto": "PASS"
 },
 ...
}
```

Corre el validator sobre los 62 videos factory. **Tiene que dar 0 rechazados.**
Si alguno aparece ahí, el que está roto es el validator, no el asset.

### 3.3 `inspect` / `validate` — mirar un AVI

```
$ mochic validate /home/danny/megamochi-backup/volume_files/video/Angry.avi
[exit 0]
{ "archivos": 1, "duros": 0, "invalidos": 0,
  "reportes": [{ "valido": true, "duros": 0, "suaves": 0, "hallazgos": [], ... }] }
```

`inspect` da los crudos del contenedor (`avih`, `streams`, `strf`, conteo de
registros, `audio_cuanto_ok`, forma del primer JPEG). Salida truncada acá; está
completa en el log de evidencia.

### 3.4 `playlist VOLUMEN` — qué hay en la tarjeta, sin tocarla

```
$ mochic playlist /tmp/mochi-fake-vol
[exit 0]
{ "entradas": 62, "bytes": 7936, "sha256": "af6de1fc47c2...", "slots": [ ... 62 filas ... ],
  "archivos_fuera_de_playlist": [],
  "avisos": ["agregar entradas nuevas no esta demostrado que el firmware lo acepte"] }
```

Sirve igual contra una copia local del volumen. Cada `slot` trae `existe` y
`bytes`, así se ve si el playlist y `video/` calzan.

### 3.5 `spec` — crear la receta

```
$ mochic spec --pack ".../Companion/packs/malbolge-cat" --animacion thinking \
    --slot Squint.avi --fotogramas 60 --id demo-thinking -o examples/demo-thinking.json
[exit 0]
{ "escrito": ".../examples/demo-thinking.json", "spec": "demo-thinking" }
```

El spec (`mochi-anim-v1`) declara: arte de origen, cuántos frames a 30 fps,
cuántos bytes máximo por frame, y **qué nombre del playlist existing** va a
ocupar. No es un guion de píxeles.

### 3.6 `plan` — qué se escribiría, y el token

```
$ mochic plan /tmp/mochi-fake-vol examples/demo-thinking.json --salida build/plan-demo.json
[exit 0]
{
 "accion": "mochi-deploy-v1",
 "advertencia": "Escribir en el volumen cambia el estado del dispositivo. Este plan no ha escrito nada.",
 "comando_siguiente": "mochic apply .../build/plan-demo.json --token 41a84867a009",
 "operaciones": [{
   "destino": "video/Squint.avi",
   "destino_bytes_actual": 458010,
   "destino_sha256_actual": "eceb82700b1f...",
   "origen": ".../build/demo-thinking.avi",
   "origen_bytes": 1594526,
   "origen_sha256": "77a9df099345..." }],
 "token": "41a84867a009", "total_bytes": 1594526, "volumen": "/tmp/mochi-fake-vol"
}
```

El token es `sha256(plan)[:12]`: cambia si cambia cualquier byte del plan.
Es la puerta para que un agente no pueda "aplicar lo que sea".

### 3.7 `apply` — la única escritura, y su negativa

Token malo (no escribe nada, código 4):

```
$ mochic apply build/plan-demo.json --token TOKEN-MALO
[exit 4]
{"error": "GateError", "mensaje": "el token no coincide con el plan; nada escrito", "codigo_salida": 4}
```

Token bueno:

```
$ mochic apply build/plan-demo.json --token 41a84867a009 --copia /tmp/mochi-bridge/backup --diario /tmp/mochi-bridge/journal.json
[exit 0]
{
 "avisos": ["el firmware no ha sido observado todavia con estos archivos nuevos",
            "rollback: mochic rollback /tmp/mochi-bridge/journal.json"],
 "backup_root": "/tmp/mochi-bridge/backup",
 "escritos": ["video/Squint.avi"],
 "journal": "/tmp/mochi-bridge/journal.json", "total_bytes": 1594526, "volumen": "/tmp/mochi-fake-vol"
}
```

### 3.8 `rollback` — volver al estado anterior

```
$ mochic rollback /tmp/mochi-bridge/journal.json
[exit 0]
{ "journal": "/tmp/mochi-bridge/journal.json", "restaurados": [["video/Squint.avi", "restaurado"]] }
```

### 3.9 `emit` + `watch` — el lazo con los agentes

Un agente de Companion escribe `companion-event-v1` en su inbox; `watch` lee lo
no leído, renderiza y planifica. Con `emit` se prueba sin Companion:

```
$ mochic emit state --valor working --inbox /tmp/mochi-bridge/inbox.jsonl --agente agente-demo
[exit 0]
{ "evento": { "agent": "agente-demo", "created_at": "2026-11-06T10:24:25Z",
              "id": "mochi-state-...", "type": "state", "value": "working",
              "version": "companion-event-v1" }, "inbox": "/tmp/mochi-bridge/inbox.jsonl", ... }

$ mochic watch --inbox /tmp/mochi-bridge/inbox.jsonl --pack ".../Companion/packs/malbolge-cat" \
    --volumen /tmp/mochi-fake-vol --outbox /tmp/mochi-bridge/outbox.jsonl \
    --cursor-root /tmp/mochi-bridge/cursor --fotogramas 45
[exit 0]
{ "desde_bytes": 0, "hasta_bytes": 976, "eventos": 6, "escribio_volumen": false,
  "no_demostrado": [ "el firmware reproduce el slot reemplazado ante el estimulo que se esperaba",
                     "el numero de entradas de playlist.lst puede ser distinto de 62",
                     "el firmware relee el volumen sin quitar el cable" ],
  "resultados": [ {"animacion": "working", "slot": "Revs.avi", "valido": true,
                   "plan_token": "...", ...}, ... ] }
```

La segunda pasada del mismo inbox devuelve `"eventos": 0`: el cursor guarda el
offset en bytes en `--cursor-root`. Con `--desde 0` se releé el historial sin
consumirlo.

### 3.10 `map` — la tabla animación → slot

```
$ mochic map --mostrar
[exit 0]
{ "drag": "UpsideDown.avi", "error": "Crying.avi", "idle": "Blink.avi",
  "running-left": "Look Left.avi", "running-right": "Look Right.avi",
  "success": "Smile.avi", "thinking": "Squint.avi", "waiting": "Sleepy.avi",
  "working": "Revs.avi" }
```

**Esta tabla es política de nombramiento, no una medida.** Editable con
`mochic map -o mi-mapa.json` y luego `watch --mapa mi-mapa.json`.

### 3.11 Interoperabilidad real con Companion (control cruzado)

El inbox lo escribe el **validador de Companion**, no el nuestro. Se le meten 3
eventos por stdin al `hook` real, uno con un `value` inexistente:

```
$ printf "3 eventos" | COMPANION_ROOT=/tmp/mochi-e2e \
    PYTHONPATH=".../Companion/src" python3 -c "from companion.cli import main; sys.exit(main())" hook
[exit 0]
{"line": 1, "status": "queued", "event_id": "evt-real-1"}
{"line": 2, "status": "queued", "event_id": "evt-real-2"}
{"line": 3, "status": "error", "error": "value must be one of: error, hidden, idle, success, thinking, waiting, working"}

$ mochic watch --inbox /tmp/mochi-e2e/inbox.jsonl --pack ".../Companion/packs/malbolge-cat" \
    --volumen /tmp/mochi-fake-vol --build-dir /tmp/mochi-e2e/build \
    --cursor-root /tmp/mochi-e2e/cursor --fotogramas 30
[exit 0]
{ "desde_bytes": 0, "eventos": 2, "hasta_bytes": 281, "escribio_volumen": false,
  "no_demostrado": [...], "resultados": [ ... ] }
```

Lo que esto prueba, y lo que no:

* **Prueba** que los dos validadores aceptan exactamente los mismos eventos: el
  tercero quedó rechazado por Companion y por lo tanto nunca llegó a `mochic`.
* **Prueba** que el puente consume un inbox escrito por otro proceso, con su
  propio cursor de bytes.
* **No prueba** que Companion muestre nada en pantalla ni que el Mochi
  reproduzca el archivo. Son dos dispositivos distintos y cada uno exige su
  propia verificación física.

Nota de honestidad: el comando `companion hook` **NO PROBADO** como binario
instalado (`companion` no está en el PATH de esta máquina); se corrió por
`python3 -c "from companion.cli import main..."` con `PYTHONPATH=src`, que es lo
que el paquete instala como script. Igual el `hook` no necesita instalación.

### 3.12 Los tres rechazos que la tabla §4 promete (códigos 1, 2 y 5)

`cli_v0` dejó crudo 0, 3 y 4. Los otros tres están capturados con su control
positivo al lado en `evidence/refusals_v0` (`python3 tools/capture_refusals.py`,
12 comandos + 1 sonda). Salidas literales del crudo hasheado, solo
partidas en dos líneas con `\` cuando eran demasiado largas:

```
$ mochic validate /tmp/mochi-refusals/mutante.avi
[exit 1]                 # 5 hallazgos duros: movi.interleave, movi.patron,
                         # audio.quantum, idx1.entries, idx1.alineado (+1 suave)
$ mochic validate "/home/danny/Development/ISyCo Git/MochiCompanionSDK/build/demo-thinking.avi"
[exit 0]                 # control: el mismo AVI sin mutar, 0 duros

$ mochic spec --pack "/home/danny/Development/ISyCo Git/Companion/packs/malbolge-cat" \
      --fotogramas 2 -o /tmp/mochi-refusals/s.json
[exit 1]
{"error": "AviError", "mensaje": "fotogramas=2 fuera de 15..2000 (el corpus factory va de 15 a 501; el tope alto es politica, no medida)", "codigo_salida": 1}

$ mochic emit state --inbox /tmp/mochi-refusals/in.jsonl --valor flotante
[exit 1]
{"error": "BridgeError", "mensaje": "value debe estar en ['error', 'hidden', 'idle', 'success', 'thinking', 'waiting', 'working']", "codigo_salida": 1}
$ test -e "/tmp/mochi-refusals/in.jsonl" && echo EXISTE \
      || echo "NO EXISTE: el evento invalido no se escribio"
[exit 0]
NO EXISTE: el evento invalido no se escribio

$ mochic plan /tmp/mochi-fake-vol
[exit 2]
{"error": "UsageError", "mensaje": "no hay nada que planear: pase un spec o --par ORIGEN DESTINO", "codigo_salida": 2}
$ mochic playlist
[exit 2]
usage: mochic playlist [-h] [--json] [--texto] volumen
mochic playlist: error: the following arguments are required: volumen

$ mochic plan /tmp/mochi-fake-vol --par build/demo-thinking.avi video/NoExiste.avi
[exit 5]
{"error": "RefuseError", "mensaje": "el destino 'video/NoExiste.avi' no existe en el volumen: agregar entradas nuevas al playlist NO esta demostrado", "codigo_salida": 5}
$ mochic plan /tmp/mochi-fake-vol --par build/demo-thinking.avi video/Squint.avi --salida /tmp/mochi-refusals/plan-ok.json
[exit 0]                 # control: la misma orden con un destino que SÍ existe
```

El mutante se conserva (`evidence/refusals_v0/mutante.avi`, sha256 `5942f22d…`):
es el AVI bueno con el campo `dwSize` de un registro `01wb` cambiado de 3200 a
3000 bytes. Romper un solo campo rompe cinco reglas porque el parser avanza por
tamaño declarado — así se comprueba que `validate` lee de verdad.

### 3.13 Suite de pruebas

```
$ python3 -m pytest tests/ -q
[exit 0]
180 passed in 2.99s
```

Esa es la salida que está dentro del crudo sellado de `cli_v0`. Hoy la suite es
**182**: se agregaron `test_guard_out_niega_pisar_un_crudo_sellado` y
`test_guard_out_permite_escribir_sin_manifest_o_con_fuerza` (las dos del trap
11), y por eso el hash de `tests/test_spec_render_bridge.py` que figura en el
manifest es el de la versión de 182 pruebas, no el de la corrida que produjo
`180 passed`. El número del crudo y el número actual no coinciden **a propósito**:
el crudo no se reescribió.

---

### 3.14 El slot de arranque: `startup.avi`

Esto no estaba en el diseño original del SDK. Existía porque el 2026-11-06 Danny
pegó un AVI hecho por otro modelo en `startup.avi`, el Mochi sonó pero la pantalla
se puso en blanco, y después la escritura autorizada funcionó. Los cuatro pasos,
con las salidas literales de `evidence/startup_write_v0/stdout.raw.txt` y
`evidence/boot_play_v0/stdout.raw.txt`:

**1. El portón rechaza el archivo ajeno tal cual, y no escribe nada.**

```
$ ./mochic plan /media/danny/MEGAMOCHI --par /home/danny/Descargas/startup.avi startup.avi
[exit 1]
{"error": "AviError", "mensaje": "/home/danny/Descargas/startup.avi no pasa la validacion: strh.video.suggested_buf", "codigo_salida": 1}
```

Ese rechazo era, en parte, culpa nuestra: `profile.py` exigía «PCM mono exacto»
como regla dura y el `startup.avi` **de fábrica es estéreo**. Medidas las
relaciones sobre los 63 archivos reales del volumen (62 de `video/*.avi` +
`startup.avi`), las constantes «mono / 3200 B» solo calzaban 62/63. Hoy el
validator compara contra relaciones derivadas:

```
block_align == canales * bits/8                63/63
avg_bytes_per_sec == samples_per_sec*block      63/63
strh.sample_size == block_align                 63/63
quantum == avg_Bps/fps == strh.auds.sugg        63/63
strh.vids.suggested_buf == mayor JPEG           63/63
canales == 1                                    62/63  -> regla SUAVE
```

Con eso, el archivo de fábrica pasó de 3 duros a **0 duros** y los 62 del
playlist siguen en 0 (`./mochic profile --control` → `rechazados: 0, veredicto
PASS`). El mutante que rompió la pantalla sigue cayendo, ahora con 6 duros.

**2. Reparar el único campo auto-incoherente, sobre una copia.**

```
$ python3 tools/fix_suggested_buf.py /home/danny/Descargas/startup.avi /tmp/mochi-write/startup__reparado.avi
[exit 0]
{
 "bytes": 1443076,
 "bytes_diferentes": 2,
 "declarado": 12132,
 "duros_restantes": [],
 "frame_max": 7737,
 "offset": 144,
 "sha_copia": "dbd65d1fdf1ceafc360a51bf5590bbcbcdb527daf1ededd5dbf56bf322def3a4",
 "sha_origen": "cfa5044ab749b55d37b67c3450a4ebf492eff8ce55910757487c6c993c5cdb6d"
}
```

La herramienta **refusa** si el archivo tiene cualquier otro hallazgo duro: no es
una puerta de escape del validador, es la corrección de un entero.

**3. Plan (no escribe) y apply (única escritura, con token, backup y journal).**

```
$ ./mochic plan /media/danny/MEGAMOCHI --par /tmp/mochi-write/startup__reparado.avi startup.avi --salida /tmp/mochi-write/plan.json
[exit 0]
   "destino": "startup.avi",
   "destino_sha256_actual": "4f7d6b4325acb5d309d0e66c6e409a7f62b2ea335cfd405725808e0914226db5",
   "origen_sha256": "dbd65d1fdf1ceafc360a51bf5590bbcbcdb527daf1ededd5dbf56bf322def3a4",
   "comando_siguiente": "mochic apply /tmp/mochi-write/plan.json --token 47e45cafa60e"

$ ./mochic apply /tmp/mochi-write/plan.json --token 47e45cafa60e --copia ~/megamochi-backup/deploy_2026-11-06_bootslot --diario /tmp/mochi-write/journal.json
[exit 0]
   "escritos": ["startup.avi"],
   "backup_root": "/home/danny/megamochi-backup/deploy_2026-11-06_bootslot",
   "avisos": ["el firmware no ha sido observado todavia con estos archivos nuevos",
              "rollback: mochic rollback /tmp/mochi-write/journal.json"]

$ sha256sum /media/danny/MEGAMOCHI/startup.avi
[exit 0]
dbd65d1fdf1ceafc360a51bf5590bbcbcdb527daf1ededd5dbf56bf322def3a4  /media/danny/MEGAMOCHI/startup.avi
```

El backup se verificó byte a byte **antes** de escribir (`4f7d6b43…`, igual al
congelado del pack) y el original de fábrica sigue vivo en
`~/megamochi-backup/volume_files/startup.avi` (`acb6afb9…`).

**4. Apagar y encender. Resultado: video y audio correctos.**

El operador reportó «funciono perfecto» sobre exactamente el archivo cuyo sha se
verificó antes del reinicio, así que el claim queda `CONDITIONAL_PASS` en
`evidence/boot_play_v0/`: falta una grabación con cámara para subirlo a `PASS`.
Lo que sí quedó descartado: `suggested_buf` **no** era la causa de la pantalla en
blanco, porque el archivo que falló lo tenía coherente (`7719 == 7719`). La causa
está entre las desviaciones de contenedor: audio en bloques de 16384 B en vez de
6400 B por fotograma, 155 registros en lugar de 223, sin `vprp` y chunk de audio
final de 5888 B en lugar de 0.

Para volver atrás en cualquier momento:

```
./mochic rollback ~/megamochi-backup/deploy_2026-11-06_bootslot/journal.json
```

---

## 4. Cómo leer la salida

| Código | Qué significa | Qué hacer | Dónde está el crudo |
| 0 | OK | nada | `cli_v0` (24 de sus 26 bloques) y `refusals_v0` |
| 1 | **hallazgo duro**: el AVI no calza con el perfil factory, o el spec es inválido, o el JSON del evento está roto | leer `hallazgos[].regla` / `mensaje`; bajar `budget_bytes_por_frame` o arreglar el spec | `refusals_v0` |
| 2 | error de uso (faltó un argumento) | `mochic <cmd> --help` | `refusals_v0` |
| 3 | entrada ilegible o inexistente | revisar la ruta; `build/…` aparece recién después de `build` | `cli_v0` |
| 4 | el token no coincide o falta | volver a correr `plan` y pasar el token que devolvió **ese** plan | `cli_v0` |
| 5 | operación rehusada porque **no está demostrada** | el destino no existe en el volumen: este SDK solo reemplaza archivos existentes, no agrega entradas al playlist | `refusals_v0` (x2: por spec y por `--par`) |

Advertencias *suaves* (no cambian el código de salida):

| Regla | Lectura |
|---|---|
| `bitrate.real` | el asset supera 745702 B/s, el mayor bitrate **observado** en factory. El techo real del dispositivo no se midió: es un aviso, no un fallo |
| `jpeg.frame_bytes` | algún frame supera el presupuesto declarado en el spec |

---

## 5. Trampas (cada una costó tiempo real)

1. **`fotogramas` mínimo 15.** Con 12 da código 1: `fuera de 15..2000`. El piso
   es lo más corto que hay en el corpus factory; el techo de 2000 es política.
2. **`budget_bytes_por_frame` no es un límite del dispositivo.** 31893 B es el
   frame más grande que el firmware ya reproduce. Bajarlo hace que el encoder
   baje la calidad JPEG (bisección sobre `quality`), no que el archivo "pese menos gratis".
3. **Nombres con espacio.** `Look Right.avi` y `Keep It UP.avi` existen en el
   playlist. Entrecomilla en el shell, y `--par ORIGEN DESTINO` lleva el destino tal cual.
4. **El plan caduca si cambias algo.** Si después de `plan` volvés a `build`,
   `apply` falla con "el origen cambio desde el plan". Volver a planear.
5. **`apply` sin `--token` no es "modo dry"**: es código 4. No existe una
   escritura sin token.
6. **Perder `--copia` o el journal es perder el rollback.** El backup vive
   **fuera** del volumen (por defecto `.mochisdk-backup/` en el directorio actual).
   Si llamás `deploy.apply()` desde Python sin pasar `backup_root`, el backup cae en
   `.mochisdk-rollback/<sello>/` — rutas distintas, journal distinto.
7. **El puente nunca escribe el volumen**, ni con `--volumen`: solo calcula el
   token del plan. Es deliberado; un evento de agente no es autorización.
8. **`watch` sin `--outbox` igual consume el cursor** — si querés releer el
   inbox desde cero usá `--desde 0` (esa pasada no avanza el cursor).
9. **El aviso de que "el firmware no ha sido observado con estos archivos"** no
   es burocracia: hasta que alguien meta la tarjeta y mire, todo lo que
   `apply` hace es dejar la tarjeta en un estado no probado.
10. **Un render que sale con todos los frames idénticos** fue un bug real de
    este SDK (mezclaba milisegundos con segundos al remuestrear). Si ves
    `jpeg_quality` constante y `frame_bytes.min == frame_bytes.max` sospechalo:
    el test `test_resample_to_30_pesa_cada_frame_segun_su_tiempo` lo cazó.
11. **Re-correar un capturer dentro de un pack sellado estaba destruyendo
    evidencia.** El `evidence/cli_v0/stdout.raw.txt` que se selló a las 10:53Z
    fue reemplazado a las 10:59Z por una segunda corrida (pasó de 24 a 26
    bloques) y el manifest quedó apuntando a bytes que ya no existían. Ahora
    `tools/capture_cli.py` y `tools/capture_refusals.py` niegan la escritura:

    Salida literal de esa negativa, corrida en vivo contra el pack real:

    ```
    $ python3 tools/capture_cli.py
    [exit 1]
    REFUSAL: /home/danny/Development/ISyCo Git/MochiCompanionSDK/evidence/cli_v0/stdout.raw.txt ya existe y esta sellado por /home/danny/Development/ISyCo Git/MochiCompanionSDK/evidence/cli_v0/manifest.json (sha256 disco 59dbff2aede581a6, manifest 59dbff2aede581a6).
    Re-correar el capturer aqui pisaria evidencia cruda. Abre una version nueva:
      python3 tools/capture_cli.py --out evidence/cli_v1/stdout.raw.txt
    y sella ese pack; el anterior queda SUPERSEDED, intacto.
    Si de verdad quieres reescribir dentro de cli_v0 (solo si vas a re-sellar con
    build --force y a documentarlo en CORRECCIONES.md): pasa --fuerza.
    ```

    Después de esa corrida el `sha256sum -c` del crudo coincide con el valor
    registrado antes de correrla: el refusals es previo a cualquier escritura.

    La convención es esa: un pack sellado no se reescribe, se abre `..._v1` y el
    anterior queda `SUPERSEDED`. `--fuerza` existe para el caso en que de verdad
    querés re-sellar el mismo pack (y documentarlo en `CORRECCIONES.md`).
12. **«Los permisos no permiten pegar» no es un permiso.** El 2026-11-06, después
    de que el gato desconectara el Mochi a media sesión (y de otra
    re-enumeración a las 06:19), Nautilus se negaba a pegar en el volumen. El
    kernel decía otra cosa (corrido en vivo a las 06:12, con el volumen montado;
    esta sección no tiene crudo sellado propio, el texto es la salida copiada de
    esa corrida):

    ```
    $ grep sda1 /proc/mounts
    /dev/sda1 /media/danny/MEGAMOCHI vfat rw,nosuid,nodev,relatime,uid=1000,gid=1000,\
    fmask=0022,dmask=0022,codepage=437,iocharset=iso8859-1,shortname=mixed,showexec,\
    utf8,flush,errors=remount-ro 0 0
    $ cat /sys/block/sda/ro
    0
    $ python3 -c "import os;print(os.access('/media/danny/MEGAMOCHI',os.W_OK))"
    True
    $ gio mount -l
    Drive(0): <serial del disco de la workstation, tachado: no es dato del experimento>
    Drive(1): Synwit U SB Mass Storage
      Type: GProxyDrive (GProxyVolumeMonitorUDisks2)
    ```

    Cuatro indicadores de que el volumen sí aceptaba escritura, y un `gio mount
    -l` que lista los *drives* pero **ningún Mount**. La ventana de Archivos pertenece a un `nautilus --gapplication-service` del
    día anterior y sigue apuntando al `GMount` que murió con el dispositivo
    viejo. Cerrar la ventana o `nautilus -q` lo resolve; desde terminal la
    escritura nunca estuvo bloqueada (ver §3.14, `apply` exit 0 sobre el mismo
    volumen). No hace falta desmontar ni `chmod` nada.
13. **Una constante de 62/63 disfrazada de invariante.** `profile.py` rechazaba
    el `startup.avi` de fábrica porque «PCM mono exacto» se había medido solo
    sobre `video/*.avi`. El activo de arranque es estéreo. La lección es de
    método: antes de declarar una regla *hard*, hay que preguntar si el número
    que la sustenta es una relación estructural (`quantum == avg_Bps/fps`, 63/63)
    o una coincidencia del subcorpus (`channels == 1`, 62/63). Las segundas van
    como *soft* y dicen cuántos casos las ven.
14. **Dos escrituras al mismo slot compartían un solo backup.** `deploy.apply`
    nombraba la copia por `basename(dst)`, así que al instalar el `startup.avi`
    con campana encima del `startup.avi` anterior, la segunda escritura pisó el
    archivo al que apunta el journal de la primera. El journal quedó diciendo
    `sha_previo dbd65d1f…` con un `backup` que hoy vale `86f15586…`: ese rollback
    ya no restaura nada. Está medido en el crudo de `evidence/our_build_v1`:

    ```
    journal-boot.json        sha_previo dbd65d1fdf1ceafc  backup 86f1558614b3e87d  COLISION: ya no es el estado previo
    journal-video.json       sha_previo 087788a2233cba50  backup 087788a2233cba50  OK
    journal-boot-audio.json  sha_previo 86f1558614b3e87d  backup 86f1558614b3e87d  OK
    ```

    Hoy el backup se nombra `destino_relativo__sha_previo[0:8]` y `rollback`
    verifica el backup **antes** de copiarlo (se niega en vez de instalar bytes
    ajenos). El mismo defecto existía en el journal por defecto: un único
    `journal.json` por `backup_root` hacía que la segunda `apply` borrara el
    historial de la primera; ahora es `journal-<sello>-<token>[0:12].json`. Los
    dos controles están en `tests/test_deploy_playlist.py`.
    **Consecuencia práctica:** para volver al `startup.avi` de fábrica con los
    journals de este session no uses `journal-boot.json` — instala
    `~/megamochi-backup/volume_files/startup.avi` (`acb6afb9…`) con un plan nuevo.

---

## 6. Qué NO está demostrado (y no hay que contar como hecho)

* Qué dispara cada una de las 62 animaciones en el firmware (MOCHI-REA-03 sigue
  abierto: hace falta la observación física B0–B6).
* Que el firmware acepte un AVI generado por **este** SDK en un slot del
  **playlist**. `video/Blink.avi` fue reemplazado por el nuestro (`541c29e4…`) y
  ahí sigue: sin conocer su disparo físico, nadie lo ha visto en pantalla.
* Que el clip de arranque generado por `mochic build` (**mono**) se reproduzca
  con su **audio**. El video sí: el operador vio al Malbolgato tras el reboot
  (`evidence/our_build_v1`, claim 5 `CONDITIONAL_PASS`). Condional porque no hay
  captura de cámara sellada ni relectura del volumen montado, y porque nadie
  registró si el campanazo de `boot-chime.wav` sonó.
* Que el firmware relea el volumen sin quitar el cable.
* Que `playlist.lst` admita un número de entradas distinto de 62.
* Cuál es el techo real de bitrate o de bytes por frame.
* Grabación con cámara del arranque: sin ella el claim 1 de
  `evidence/boot_play_v0/` queda en `CONDITIONAL_PASS`, no en `PASS`.

Cómo se cierra cada uno (y qué permiso hace falta):

| Gap | Acción que lo cierra | Requiere |
|---|---|---|
| Que el firmware acepte un AVI de `mochic build` en `video/` | `mochic spec` + `build` + `plan` + `apply --token` sobre un slot existente, y mirar | **autorización explícita de Danny** (una escritura) |
| `startup.avi` mono | reparar/planificar sobre el slot de arranque con un `build` propio y reiniciar | autorización + rollback preparado (ya existe el procedimiento en §3.14) |
| Qué dispara cada animación | grabar el barrido físico B0–B6 y pasar `python3 ~/megamochi-backup/MOCHI-REA-03/mochi_sweep.py detect` (procedimiento: `~/megamochi-backup/MOCHI-REA-03/GUIA_BARRIDO.md`) | presencia de Danny, cero escrituras |
| Que `playlist.lst` acepte ≠ 62 entradas | solo tiene sentido después del primer apply exitoso en `video/` | autorización + rollback preparado |
| Techo real de bytes/frame | barrido ascendente de `budget_bytes_por_frame` hasta que falle | autorización para varias escrituras |
| Si relee sin quitar el cable | observar tras un apply | nada extra: se ve en el mismo experimento |
| Claim 1 de `boot_play_v0` a PASS | una grabación del arranque, congelada con sha en el pack | cámara del operador, cero escrituras |
