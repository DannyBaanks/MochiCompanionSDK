# VERDICT — `foreign_startup_v0`

Experimento observacional (cero escrituras al dispositivo) sobre el reemplazo
espontáneo de `startup.avi` que Danny hizo el 2026-11-06 a las 06:01 hora local.

## QUESTION

Un AVI generado por otro modelo se copió al slot de arranque del Mochi. El
dispositivo reprodujo el audio nuevo ("hola"), la pantalla se vio en blanco y
después volvió al Mochi normal. ¿Qué dice eso del formato que el firmware espera
en el activo de arranque, y qué campo explica el fallo?

## PRIOR_EVIDENCE

* `evidence/profile_v1/` — los 62 videos del playlist medidos: MJPEG 480×480@30,
  PCM 16 bits **mono** 48 kHz, **3200 B de audio por fotograma**, intercalado
  `va·n + a`, `strh.vids.suggested_buf` = fotograma mayor.
* `evidence/cli_v0/` — `mochic validate` rechaza mutantes y acepta 62/62 reales.
* Nada medido hasta hoy sobre `startup.avi`: el backup del volumen
  (`~/megamochi-backup/volume_files/startup.avi`) nunca entró en el corpus porque
  el corpus se construyó sobre `volume_files/video/`.

## HYPOTHESIS

* H0 — el archivo ajeno está estructuralmente conforme con el formato del Mochi y
  la pantalla en blanco es un problema de *contenido* (píxeles blancos).
* H1 — el archivo ajeno viola invariantes del contenedor que el firmware usa para
  caminar `movi`, y los fotogramas no son blancos; el fallo es de decodificación
  o presentación, no de la imagen.
* Falsación de H1: que los fotogramas decodificados resulten blancos, o que el
  archivo ajeno pase el validator con 0 duros.

## METRIC

Duros reportados por `mochic validate`, conteo de registros `movi`, patrón de
intercalado, cuatum de audio, presencia de `vprp`, `strh.vids.suggested_buf` vs
fotograma mayor, y luminancia media de un fotograma decodificado (0–255).

## EXPERIMENT / MEASURE

Tres entradas congeladas con sha y mtime en `inputs.raw.txt` **antes** de analizar
(el archivo original bajo `/home/danny/Descargas` cambió de bytes dos veces durante
la mañana, así que cualquier lectura sin congelar era irrecuperable):

| archivo | sha256 (12) | bytes | mtime | quién |
|---|---|---|---|---|
| `startup__acb6afb9` | `acb6afb9d8e9` | 1 544 598 | 2024-12-08T12:34:34Z | de fábrica, desde el backup |
| `startup__cfa5044a` | `cfa5044ab749` | 1 443 076 | 2026-11-06T12:05:36Z | segundo archivo ajeno |
| `startupEJEMPLO__4f7d6b43` | `4f7d6b4325ac` | 1 439 370 | 2026-11-06T12:00:32Z | el que se pegó al volumen |

Crudo completo: `stdout.raw.txt` (10 bloques, generado por
`python3 tools/capture_foreign.py`).

## RESULTADOS

| hecho medido | de fábrica | `cfa5044a` | `4f7d6b43` (el pegado) |
|---|---|---|---|
| registros `movi` | 223 (v111/a112) | 223 (v111/a112) | **155 (v111/a44)** |
| patrón | `vavavavavava` | `vavavavavava` | **`vavvavvvavva`** |
| audio por fotograma | 6400 B | 6400 B | **16384 B (restos 5888)** |
| chunk de audio final | 0 B | 0 B | **5888 B** |
| `vprp` en el árbol | presente | presente | **ausente** |
| `strh.vids.suggested_buf` / frame mayor | 12132 / 12132 | **12132 / 7737** | 7719 / 7719 |
| JPEG | FFC0, 8 bits, (34,17,17) | igual | igual |
| luminancia del fotograma central | media 12.6–13.7 | 18.1 | **18.1 (oscuridad, no blanco)** |
| duros del validator vs perfil de playlist | 3 | 4 | **7** |
| `strf.audio` | PCM **2 canales** 192000 B/s block 4 | igual | igual |

## CONTROLES

* **Positivo:** el archivo de fábrica se parsea completo, su árbol de cabecera es
  idéntico al esperado y satisface el invariante `suggested_buf == frame mayor`
  (12132 == 12132). Si el harness estuviera roto, esto fallaría primero.
* **Negativo/mutante real:** el archivo ajeno produce 7 hallazgos duros y el
  validator responde a cada uno (`header.arbol`, `movi.interleave`, `movi.patron`,
  `audio.quantum`, `audio.chunk_final`). No es un validator saturado: sobre los 62
  videos reales devuelve 0 duros (`profile_v1`).

## CLAIMS

1. PASS — lo que hoy está en `/media/danny/MEGAMOCHI/startup.avi` es byte a byte
   `startupEJEMPLO__4f7d6b43.avi` (sha `4f7d6b4325acb5d3…`); la lectura del
   volumen no escribió nada.
2. PASS — el activo de arranque de fábrica **no** cumple el perfil medido sobre
   los 62 videos del playlist: 3 duros, todos de audio, porque es **stéreo**
   (2 canales, 192 000 B/s, block_align 4, 6400 B por fotograma). El perfil
   `mochi-factory-v1` está acotado a `video/*.avi`, no a `startup.avi`.
3. PASS — en el archivo de arranque de fábrica se cumple
   `strh.vids.suggested_buf == tamaño del mayor JPEG` (12132 == 12132), igual que
   en los 62 videos del playlist; es un invariante del contenedor, no una
   constante mágica.
4. PASS — el archivo que provocó el fallo viola 4 propiedades estructurales a la
   vez: sin `vprp`, 155 registros en lugar de 223, audio en bloques de 16384 B en
   lugar de 6400 B por fotograma, y chunk de audio final de 5888 B en lugar de 0.
5. PASS — los fotogramas del archivo ajeno no son blancos: decodificado el
   fotograma central da media 18.1/255 con desviación 64.5. La "pantalla en
   blanco" es un fallo del camino de vídeo del firmware, no la imagen del archivo.
6. PASS — el segundo archivo ajeno (`cfa5044a`) reproduce exactamente la geometría
   del activo de arranque (223 registros, 1:1, 6400 B/frame, chunk final 0, `vprp`
   presente) y solo desviaba en `suggested_buf` (12132 declarado, 7737 real).
7. NOT_DEMONSTRATED — **cuál** de las 4 desviaciones del claim 4 causó la pantalla
   en blanco. Estaban todas juntas en el mismo archivo; separarlas exige escribir
   en el dispositivo un archivo por variable, cosa que no está autorizada.
8. NOT_DEMONSTRATED — si el firmware reproduce un `startup.avi` **mono** (lo que
   produciría nuestro `mochic build` hoy): el único de arranque observado en
   pantalla es estéreo.

## ALCANCE Y LIMITACIONES

Solo tres archivos, observados sin intervención. El audio sí se reprodujo, así
que el firmware llegó a abrir el contenedor y su stream de audio; eso acota el
fallo al camino de vídeo, pero no identifica el campo. Ningún byte del dispositivo
fue escrito, movido ni reparado por este experimento. La corrección del perfil
(claim 2) se aplicó documentando el alcance; **no** se reescribió evidencia de
`profile_v1`.
