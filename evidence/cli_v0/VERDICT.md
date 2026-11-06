# VERDICT — superficie del SDK y puente Companion (`evidence/cli_v0`)

Sello: 2026-11-06. Cero escrituras al dispositivo: el volumen es un arbol de
copias locales en `/tmp/mochi-fake-vol`, y el backup `~/megamochi-backup` solo
se leyó.

## QUESTION

Existe un camino reproducible, de punta a punta, que va desde el arte de un
pack de Companion hasta un AVI con forma factory, planificado y aplicado contra un volumen, sin
que ninguna escritura quede fuera de un token y sin tocar el dispositivo. Y
si existe, donde se rompe.

## PRIOR_EVIDENCE

- `evidence/profile_v1` — las restricciones medidas del envase (blueprint
  unico, 3200 B de audio por frame, 30 fps, 480x480, MJPEG 4:2:0).
- `Companion/src/companion/protocol.py` — el contrato `companion-event-v1`
  espejado en `mochisdk/bridge.py`.
- MOCHI-REA-02/03 — inventario del volumen y la seleccion de animacion
  todavía sin resolver.

## HYPOTHESIS

- H0: `spec → build → validate → plan → apply → rollback` corre end-to-end
  sobre un volumen falso, y `watch` consume eventos del inbox de Companion sin
  escribir nada en el volumen (`escribio_volumen: false` siempre).
- H1: alguna etapa necesita el dispositivo real o escribe sin token.

Criterio de falsacion de H0: cualquier bloque con exit != 0 fuera de los dos
casos de rechazo esperados, cualquier `escribio_volumen: true`, o un `apply`
sin token correcto que modifique un destino.

## METRIC

26 bloques de comando con stdout+stderr y exit code crudos (24× 0, un 4 por
token incorrecto, un 3 por origen inexistente); sha256 de cada AVI generado;
numero de hallazgos duros/suaves del validator; eventos consumidos y cursor de
bytes; `180 passed` de la suite; interoperabilidad real contra el validador de
Companion.

## EXPERIMENT / MEASURE

```
python3 tools/capture_cli.py
```

Crudo: `stdout.raw.txt` (29 108 B). Exit 0 del capturer. Los tres codigos que
aqui no se observan (1, 2, 5) estan en el pack hermano `evidence/refusals_v0`.

## CONTROLES

- **Positivo del validator:** `mochic profile --control` en el bloque 2 —
  0 de 62 archivos factory rechazados.
- **Negativo / mutantes:** 10 mutantes rechazados en la suite; el mutante
  conservado en `evidence/refusals_v0` produce 5 hallazgos duros.
- **Puerta de seguridad:** `apply --token TOKEN-MALO` → exit 4 y "nada
  escrito"; despues `apply --token 4cce25869afb` → exit 0, journal y backup.
  `rollback` restaura el sha previo `eceb82700b1f…`.
- **Cursor:** la segunda pasada de `watch` sobre el mismo inbox devuelve
  `eventos: 0` con `hasta_bytes: 976` idéntico — no re-procesa.
- **Interoperabilidad real:** 3 eventos pipeados al `hook` de Companion
  (2 validos + 1 con `value: "imposible"`) → Companion respondio
  `queued, queued, error` y escribio su propio inbox; `mochic watch` sobre ese
  inbox consumo 2 eventos (`hasta_bytes 281`) y renderizo dos AVI validos
  (`497eec8b…`, `ef46f9ee…`).
- **Dedupe por determinismo:** el AVI del spec `demo-thinking` dio el mismo
  sha256 `77a9df099345f584…` en dos corridas distintas.
- **Fail closed del capturer:** `python3 tools/capture_cli.py` contra este pack
  ya sellado responde `REFUSAL` y sale con 1; el sha256 del crudo verificado
  antes y despues de esa corrida es el mismo (`59dbff2aede581a6…`). Cubierto
  por `test_guard_out_niega_pisar_un_crudo_sellado`.

## LO QUE SALIO MAL (y como quedo cubierto)

`render.resample_to_30` comparaba milisegundos contra segundos: `t` en
segundos contra bordes en milisegundos, de modo que toda secuencia caia en el
primer frame y cada AVI generado era una imagen fija. El bug paso desapercibido
hasta que una prueba exigió 4 colores distintos con conteos 4/6/3/9 en la
secuencia. Corregido en `mochisdk/render.py` y cubierto por `tests/`.

## CLAIMS (espejo del `manifest.json`)

| # | claim | estado |
|---|---|---|
| 1 | Los 26 bloques documentados en GUIA.md fueron ejecutados por tools/capture_cli.py; crudo y exit codes en stdout.raw.txt (24x0, un 4 por token malo, un 3 por origen inexistente) | PASS |
| 2 | spec->build->validate->plan->apply->rollback corre sobre un volumen falso en /tmp sin tocar el dispositivo | PASS |
| 3 | apply con token incorrecto devuelve codigo 4 y no escribe; apply con el token del plan devuelve 0 y deja journal | PASS |
| 4 | plan de un origen inexistente devuelve codigo 3 (crudo aqui); el rechazo a destinos fuera del playlist (codigo 5) esta capturado en evidence/refusals_v0 | PASS |
| 5 | watch consume eventos companion-event-v1, renderiza, planifica y reporta escribio_volumen=false; la segunda pasada devuelve eventos=0 por el cursor de bytes | PASS |
| 6 | En el crudo sellado: 180 pruebas pasan, incluidos 62 round-trips byte-exactos, el control positivo 0/62 rechazados, 10 mutantes y el control de contrato contra validate_event de Companion (hoy la suite es 182; ver claim 12 y CORRECCIONES.md) | PASS |
| 7 | render.resample_to_30 tenia un error de unidades (ms vs s) que producia video de un solo frame; corregido y cubierto por un test que exige 4 colores y conteos 4/6/3/9 | PASS |
| 8 | el render es determinista: dos capturas del mismo spec dieron el mismo sha256 de AVI (77a9df099345) | PASS |
| 9 | el firmware reproduce un AVI generado por este SDK | NOT_DEMONSTRATED |
| 10 | que el slot reemplazado se vea ante el estimulo esperado (MOCHI-REA-03 abierto) | NOT_DEMONSTRATED |
| 11 | los codigos contractuales 1, 2 y 5 no aparecen en este crudo: quedan observados en el pack hermano evidence/refusals_v0 | PASS |
| 12 | El crudo de este pack fue reescrito a las 10:59Z por una segunda corrida del capturer, seis minutos despues del sello de las 10:53Z: el manifest anterior hasheaba stdout 845ebc48 (24 bloques) y el disco tenia 59dbff2a (26 bloques). Hoy guard_out() lo niega y dos pruebas nuevas (180->182) lo cubren; la diferencia 180/182 queda documentada, no re-capturada | PASS |

## ALCANCE DEMOSTRADO

Todo lo que ocurre **antes** de la tarjeta: generar, validar, planificar,
aplicar contra un volumen cualquiera, revertir, y responder a eventos de
Companion. Nada de esto autoriza afirmar que el dispositivo muestra el
resultado; eso necesita una escritura autorizada al volumen real y observacion
fisica del Mochi.

## NO DEMOSTRADO (explicito)

- Aceptacion por el firmware de un AVI generado (el unico gap que cierra una
  corrida fisica).
- Que `playlist.lst` admita un numero de entradas distinto de 62 — por eso el
  SDK rehusa agregados.
- Que el firmware relea el volumen sin quitar el cable.
- Techo real de bytes por frame / bitrate.
- El comando `companion hook` como **binario instalado**: en esta máquina
  `companion` no esta en el PATH, la interoperabilidad se probó invocando
  `python3 -c "from companion.cli import main; …"` con `PYTHONPATH=src`.
  `NO PROBADO` como binario.

## VERIFICACION

```
python3 /home/danny/Development/ISyCo/.agents/skills/openisy-researcher/scripts/evidence_tool.py \
    verify evidence/cli_v0
python3 -m pytest tests/ -q          # 180 passed
./mochic profile --control           # 0 de 62 rechazados
```
