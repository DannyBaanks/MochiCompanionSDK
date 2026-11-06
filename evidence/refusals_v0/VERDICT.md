# VERDICT — codigos de salida contractuales de `mochic` (`evidence/refusals_v0`)

Sello: 2026-11-06. Cero lecturas y cero escrituras al dispositivo: el volumen
es un arbol de copias locales en `/tmp/mochi-fake-vol`.

## QUESTION

`GUIA.md` §4 declara seis codigos de salida contractuales (0, 1, 2, 3, 4, 5).
El pack `evidence/cli_v0` dejo crudo solo 0, 3 y 4. Faltaba evidencia propia
de 1 (hallazgo duro), 2 (uso) y 5 (operacion rehusada porque NO esta
demostrada), y faltaba probar que el 5 es especifico y no un rechazo
generalizado del comando `plan`.

## HYPOTHESIS

- H0: el codigo 5 aparece si y solo si el destino no esta en el volumen; con
  un destino existente el mismo comando devuelve 0.
- H1: el 5 es un rechazo contextual y podria aparecer con destinos validos
  (falsaria la promesa de GUIA §4).

Criterio de falsacion de H0: cualquier bloque donde `plan` devuelva 5 con un
destino listado por `mochic playlist`, o devuelva != 0 con un destino que si
existe.

## METRIC

12 comandos `mochic` ejecutados como proceso real (`subprocess` sobre `./mochic`), con
stdout+stderr y exit code crudos. Metricas: exit code por comando; numero y
reglas de los hallazgos `hard` del mutante; presencia/ausencia del inbox.

## EXPERIMENT / MEASURE

```
python3 tools/capture_refusals.py
```

Crudo: `stdout.raw.txt` (11 824 B, 15 bloques: 2 de cabecera, 12 comandos
`mochic` y 1 sonda de sistema).
El mutante se conserva en `mutante.avi` (sha256
`5942f22da0bef11437e8feb068fd4acaa435ddbef4dea2db92fe130989eecb7c`) para que
cualquiera pueda volver a validarlo byte a byte.

## CONTROLES

- **Positivo, especificidad del 5:** `plan <vol> --par build/demo-thinking.avi
  video/Squint.avi` → exit 0 y el plan resultante declara `video/Squint.avi`
  (lineas finales del crudo). El mismo `--par` con `video/NoExiste.avi` → 5.
- **Positivo, el parser no rechaza todo:** `mochic validate build/demo-thinking.avi`
  → exit 0 con 0 duros.
- **Negativo / mutante:** unico byte-change declarado — `dwSize` de un registro
  `01wb` de 3200 a 3000 B. Resultado: 5 hallazgos duros
  (`movi.interleave`, `movi.patron`, `audio.quantum`, `idx1.entries`,
  `idx1.alineado`) + 1 suave (`bitrate.real`), `valido: false`, exit 1. Que un
  solo campo rompa cinco reglas es coherente: el parser avanza por tamano
  declarado, así que el desalineamiento es consecuencia, no bug.
- **Negativo, contrato de eventos:** `emit state --valor flotante` → exit 1 y
  el inbox **no se crea**; la sonda `test -e /tmp/mochi-refusals/in.jsonl` esta dentro
  del crudo hasheado y responde `NO EXISTE: el evento invalido no se escribio`.
- **Piso medido del render:** `spec --fotogramas 2` → exit 1 con el rango
  15..2000, donde 15 es el minimo observado en el corpus.

## TABLA DE LO QUE SE OBSERVO (del crudo)

| comando (abreviado) | exit | lectura |
|---|---|---|
| `validate mutante.avi` | 1 | 5 duros, 1 suave, `valido: false` |
| `validate demo-thinking.avi` | 0 | control: 0 duros |
| `spec --fotogramas 2` | 1 | fuera de 15..2000 (15 medido) |
| `emit state --valor flotante` | 1 | valor fuera de companion-event-v1 |
| `test -e in.jsonl` | 0 | `NO EXISTE` — el rechazo no deja efecto en disco |
| `plan <vol>` | 2 | "no hay nada que planear" |
| `playlist` | 2 | argparse exige `volumen` |
| `playlist <vol>` | 0 | 62 entradas, 7936 B |
| `map --mostrar` | 0 | el mapa animacion→slot |
| `plan <vol> --par … video/NoExiste.avi` | 5 | agregar entradas NO esta demostrado |
| `spec --slot NoExiste.avi` | 0 | crear el spec es local, todavia no se escribe |
| `plan <vol> spec-rehusa.json` | 5 | mismo rechazo por la via del spec |
| `plan <vol> --par … video/Squint.avi` | 0 | control positivo del 5 |

## CLAIMS (espejo del `manifest.json`)

| # | claim | estado |
|---|---|---|
| 1 | Los codigos contractuales 1, 2 y 5 que GUIA seccion 4 declara fueron ejecutados y observados en crudo: 12 bloques sobre un volumen falso en /tmp, cero lecturas del dispositivo | PASS |
| 2 | Hallazgo duro: cambiar el tamano declarado de un registro 01wb de 3200 a 3000 B produce 5 hallazgos duros (movi.interleave, movi.patron, audio.quantum, idx1.entries, idx1.alineado) y exit 1; el mismo AVI sin mutar devuelve exit 0 | PASS |
| 3 | Uso: plan sin spec ni --par y playlist sin volumen devuelven exit 2 | PASS |
| 4 | Rechazo especifico: plan contra video/NoExiste.avi devuelve exit 5 por spec y por --par, y el mismo --par contra video/Squint.avi devuelve exit 0 con ese destino | PASS |
| 5 | El puente no escribe un evento con un valor fuera de companion-event-v1: exit 1 y el inbox ni siquiera se crea | PASS |
| 6 | La captura es repetible salvo dos campos de reloj (creado_utc del plan de control y su token derivado); los codigos de salida afirmados no dependen de ellos | CONDITIONAL_PASS |
| 7 | Que el firmware acepte alguno de estos archivos o rechace el mutante | NOT_DEMONSTRATED |


## ALCANCE DEMOSTRADO

La tabla de exit codes de GUIA §4 pasa de "declarada" a "observada" para los
seis codigos: 0, 3 y 4 en `evidence/cli_v0`; 1, 2 y 5 aqui. Tambien queda
demostrado que el refusal 5 no es un fallo generalizado del comando `plan`.

## NO DEMOSTRADO (explicito)

- Que el firmware rechace el mutante o acepte el archivo valido: ninguna de
  las dos cosas se probo en el dispositivo.
- Techo real de bytes por frame / bitrate.
- Disparo fisico de cada animacion (MOCHI-REA-03 abierto).

## VERIFICACION

```
python3 /home/danny/Development/ISyCo/.agents/skills/openisy-researcher/scripts/evidence_tool.py \
    verify evidence/refusals_v0
```
