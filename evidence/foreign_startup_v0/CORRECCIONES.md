# CORRECCIONES — `foreign_startup_v0`

Append-only. Nada de arriba se reescribió; el crudo y los hashes del sealed
original siguen intactos y `verify` pasa sobre esta versión del pack.

## Línea de tiempo de la corrección

* Sellado original: claims 1–8, con el claim 2 afirmando que el `startup.avi` de
  fábrica **no cumple** el perfil `mochi-factory-v1` (3 hallazgos duros de audio).
  Medido sobre `evidence/profile_v1/`, eso era el comportamiento real del
  validator en ese momento, así que el claim no era falso: describía un **falso
  positivo** del validator.
* 2026-11-06 06:26Z local, en `evidence/startup_write_v0/` se midieron las
  relaciones de audio sobre los **63** archivos reales del volumen (62 de
  `video/*.avi` + `startup.avi`):

  | relación | cumple |
  |---|---|
  | `block_align == canales · bits/8` | 63/63 |
  | `avg_bytes_per_sec == samples_per_sec · block_align` | 63/63 |
  | `strh.sample_size == block_align` | 63/63 |
  | `strh.rate == strf.samples_per_sec` | 63/63 |
  | `quantum == avg_bytes_per_sec / fps == strh.auds.suggested_buf` | 63/63 |
  | `strh.vids.suggested_buf == mayor JPEG` | 63/63 |
  | canales == 1 | **62/63** (el de arranque es estéreo) |

  Es decir: "mono exacto" era una constante observada 62/63, no un invariante. El
  validator la tenía como regla dura y por eso rechazaba el activo de arranque.
* `mochisdk/profile.py` cambió a reglas derivadas. Estado actual:

  | archivo | duros antes | duros ahora |
  |---|---|---|
  | `startup__acb6afb9.avi` (fábrica) | 3 | **0** (2 suaves: `avih.max_bytes_per_sec`, `strf.audio.canales`) |
  | `startup__cfa5044a.avi` | 4 | **1** (`strh.video.suggested_buf`) |
  | `startupEJEMPLO__4f7d6b43.avi` | 7 | **6** (`header.arbol`, `strh.audio.campos`, `movi.interleave`, `movi.patron`, `audio.quantum`, `audio.chunk_final`) |
  | 62 videos del playlist | 0 | 0 (`control_positivo`: 62 archivos, 0 rechazos, veredicto PASS) |
  | controles de mutante | detectados | detectados (12 tests en `tests/test_profile_validate.py -k "mutante or rechazo"`) |

## Efecto sobre los claims de este pack

* Claim 2: se mantiene como lo observado, pero se reetiqueta — **no** era una
  propiedad del dispositivo, era un defecto del perfil. La propiedad real queda
  medida arriba.
* Claims 3, 4, 5, 6: intactos, vuelven a medirse igual con el validator nuevo
  (los conteos de duros cambiaron como se muestra; las diferencias estructurales
  de `startupEJEMPLO` siguen todas presentes, incluido `audio.quantum` derivado).
* Claim 7 (qué desviación causó la pantalla en blanco): sigue
  `NOT_DEMONSTRATED`. El paso que lo acerca — escribir un `startup.avi` con una
  sola variable cambiada — ya es posible: `startup_write_v0` dejó el slot de
  arranque operable por el SDK.
