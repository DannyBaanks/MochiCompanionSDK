# VERDICT — MOCHI-REA-04 / perfil del contenedor factory (`evidence/profile_v1`)

Sello: 2026-11-06. Cero escrituras al dispositivo: todas las lecturas son de
la copia local `~/megamochi-backup/volume_files`.

## QUESTION

Que restricciones del envase AVI son propiedades medidas del firmware que ya
reproduce estos 62 archivos, y cuales siguen siendo suposicion. Sin esta tabla
no se puede generar un asset nuevo con base para esperar que el Mochi lo lea.

## PRIOR_EVIDENCE

- `evidence/profile_v0` — la misma medicion, en una version anterior. Queda **SUPERSEDED**: su
  manifest registro los sha256 de `profiles/mochi-factory-v1.json` y de
  `mochisdk/container.py` antes de que ambos cambiaran en disco, así que
  `verify` daba FAIL. Su `CORRECCIONES.md` explica el drift; el crudo no se
  reescribio.
- MOCHI-REA-02 — inventario del volumen MSC: 62 videos y `playlist.lst` de
  7936 B = 62 registros de 128 B latin1 con relleno NUL.
- MOCHI-REA-03 — la seleccion de animacion no vive en los artefactos del
  volumen; sigue abierta.

## HYPOTHESIS

- H0: los 62 archivos comparten la misma cabecera byte a byte y el mismo
  quantum de audio, o sea existe un blueprint reutilizable.
- H1: varian entre archivos y habria que parametrizar el escritor por archivo.

Criterio de falsacion de H0: `blueprint_unicas == 1` y
`audio_total_eq_3200_x_video` en 62/62. Un solo archivo fuera de la regla la
hubiera falsado.

## METRIC

Sobre N = 62 archivos (113 450 456 B; sha256 de la lista concatenada
`0c05fea119d21611cb938b6485ddf093392ea4f34d4442b20bc8baa9b1c1d338`): fps,
dimensiones, handler/fourcc de video, WAVEFORMATEX, tamanos de `strh`, patron
de intercalado, `idx1` contra los registros de `movi`, segmentos JPEG, maximo
de bytes por frame y bitrate real por segundo.

## EXPERIMENT / MEASURE

```
python3 tools/measure_corpus.py        (dos corridas consecutivas)
sha256sum profiles/mochi-factory-v1.json
```

Crudo: `stdout.raw.txt` (18 935 B, dos corridas + la linea de sha). Exit 0.
Herramienta: `mochisdk/container.py`, RIFF puro, sin ffmpeg.

## CONTROLES

- **Positivo (reproducibilidad del perfil):** las dos corridas dan el mismo
  sha256 `e3ef250444f57706c59f044126800db304f92e1c2c9146ba8488f15f33aff21e`,
  porque el perfil ya no lleva marca de tiempo. Con reloj embebido este
  control no puede pasar.
- **Negativo / mutante (el lector no es decorativo):** el pack hermano
  `evidence/refusals_v0` rompe a mano el tamano declarado de un registro
  `01wb` (3200 → 3000 B) y el mismo parser reporta 5 hallazgos duros; en la
  suite, 10 mutantes rechazados y 0 de los 62 originales rechazados.
- **Integridad de la entrada:** `sha256_lista` coincide entre las dos corridas.

## HALLAZGOS MEDIDOS (todos los numeros salen del crudo hasheado)

| propiedad | valor observado | cobertura |
|---|---|---|
| fps / dimensiones | 30.0 exactos, 480x480 | 62/62 |
| handler / fourcc de video | `MJPG` / `MJPG` | 62/62 |
| WAVEFORMATEX | tag 1, 1 canal, 16 bits, 48 000 Hz, 96 000 B/s, block_align 2 | 62/62 |
| tamano de `strh` | 56 B en ambas streams (rcFrame como 4 x int16) | 62/62 |
| blueprints de cabecera | **1** | 62/62 |
| patron de intercalado | `vavavavavava` | 62/62 |
| quantum de audio | 3200 B por frame de video; `audio_total == 3200 x frames` | 62/62 |
| frames JPEG del corpus | 9650 | todos |
| JPEG | SOI/EOI/SOF presentes, histograma SOF `192`, precision 8, submuestreo 4:2:0, 0 frames sin SOS | 9650/9650 |
| `idx1` | calza con los registros de `movi` (`idx1_full_match`) | 62/62 |
| mayor frame reproducido por el firmware | 31 893 B | 1 frame |
| mayor bitrate real | 745 702 B/s | 62/62 |
| `max_bytes_per_sec` declarado | 121 000 → placeholder, no techo | 62/62 |
| payloads de chunk constantes | 8 payloads identicos | 62/62 |

## CLAIMS (espejo del `manifest.json`)

| # | claim | estado |
|---|---|---|
| 1 | El perfil factory es byte-reproducible: dos corridas de tools/measure_corpus.py dan el mismo sha256 (e3ef250444f5...) porque ya no embeddean marca de tiempo | PASS |
| 2 | 62/62 archivos factory comparten un unico blueprint de cabecera (blueprint_unicas=1) | PASS |
| 3 | audio_total == 3200 x frames de video en 62/62 (audio_total_eq_3200_x_video = true x62) | PASS |
| 4 | idx1 calza con los registros de movi en 62/62 archivos (idx1_full_match = 62) | PASS |
| 5 | el mayor frame JPEG medido en el corpus es 31893 B y el mayor bitrate real 745702 B/s; max_bytes_per_sec declarado 121000 es un placeholder, no un techo | PASS |
| 6 | profile_v0 queda SUPERSEDED: su manifest registro sha256 de mochi-factory-v1.json y container.py antes de que ambos cambiaran en disco | SUPERSEDED |


## ALCANCE DEMOSTRADO

Alcanza para escribir un generador cuyo envase sea indistinguible del de los
archivos que el dispositivo ya reproduce, y para fijar politicas de budget
(`max_frame_bytes`) sobre un piso empirico. No alcanza para afirmar que el
firmware va a reproducir un archivo nuevo, ni donde esta su limite real.

## NO DEMOSTRADO (explicito)

- Aceptacion por el firmware de un AVI generado: exige una escritura
  autorizada al volumen y observacion fisica.
- Techo real de bitrate o de bytes por frame: se midio el maximo observado en
  el corpus, no el maximo aceptado por el dispositivo.
- Que `playlist.lst` admita un numero de entradas distinto de 62.
- Que el firmware relea el volumen sin quitar el cable.

## VERIFICACION

```
python3 /home/danny/Development/ISyCo/.agents/skills/openisy-researcher/scripts/evidence_tool.py \
    verify evidence/profile_v1
```

Artefactos sellados: 7 — `profiles/mochi-factory-v1.json`,
`profiles/mochi-header-v1.json`, `tools/measure_corpus.py`, `mochisdk/writer.py`,
`mochisdk/profile.py`, este `VERDICT.md` y `evidence/profile_v0/CORRECCIONES.md`
(el hilo del pack superseded), mas `stdout.raw.txt`.
