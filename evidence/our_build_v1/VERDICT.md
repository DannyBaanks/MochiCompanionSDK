# MOCHI-REA — `our_build_v1` — el firmware reproduce un AVI generado por este SDK

Sello: 2026-11-06 (segunda sesión del día). Sucesor de `our_build_v0`, cuya claim 7
("el firmware reproduce nuestros archivos") quedó en `NOT_DEMONSTRATED` porque el
volumen desapareció al rebotar y no se pudo releer nada. Nada de este pack reescribe
el crudo de `our_build_v0`: se abre `v1` y el `v0` sigue vigente con sus claims.

## QUESTION

¿El Mega Mochi de fábrica reproduce un AVI producido por la cadena
`mochic spec → mochic build` de este SDK, y son los bytes instalados los mismos que
salen del repo hoy?

## PRIOR_EVIDENCE

* `our_build_v0`: tres escrituras autorizadas por la ruta gated
  (`journal-boot`, `journal-video`, `journal-boot-audio`), inputs congelados en
  `evidence/our_build_v0/input/`, determinismo demostrado el mismo día.
* `boot_play_v0` claim 1: un AVI **ajeno** sí se reprodujo en el slot de arranque
  (`CONDITIONAL_PASS`, sin captura de cámara).
* `startup_write_v0`: la primera escritura autorizada a dispositivo.

## HYPOTHESIS

* **H0:** el slot de arranque muestra el asset de fábrica con independencia de lo
  que uno escriba ahí (el firmware ignoraría el archivo o rechazaría uno propio).
* **H1:** el firmware reproduce el AVI propio en el arranque.
* **Criterio de falsación:** observación en pantalla del contenido propio (Malbolgato,
  111 fotogramas, fondo `[8,6,14]`) tras el reboot ⇒ H1. Pantalla en blanco, asset de
  fábrica o bloqueo ⇒ H0. El byte-identity y el determinismo se falsan solos si
  `journal.sha_nuevo` ≠ sha256 del input congelado, o si la re-corrida produce otro hash.

## METRIC

1. `journal.sha_nuevo == sha256(input congelado)` para las tres escrituras.
2. `mochic build <spec congelado>` devuelve el mismo sha256 que se instaló (3/3).
3. `mochic validate` de cada instalado: `duros == 0`.
4. Controles: suite de tests verde y `profile --control` con 0 rechazos en 62 factory.
5. Extraído del paso 1: integridad del `backup` que referencia cada journal.

## EXPERIMENT

`python3 tools/capture_our_build.py` (14 bloques literales, sin `shell=True`, sin
escritura al dispositivo — lo único que toca fuera del repo es `sha256sum` de los
backups ya existentes, y solo si el volumen está montado se leería `startup.avi`).

* **Control positivo:** 184 tests + `profile --control` (62 archivos de fábrica, 0
  rechazados, `veredicto PASS`).
* **Control negativo / mutante:** el propio journal de la primera escritura. Si el
  mecanismo de backup fuera sano, su `backup` debería calzar con su `sha_previo`.
  No calza: `dbd65d1f ≠ 86f15586`. Eso es un fallo real de `deploy.apply`, no un
  archivo mutado a mano.

## MEASURE

Del crudo (`stdout.raw.txt`, 10 203 B, 14 bloques):

```
journal-boot.json        destino startup.avi      sha_nuevo 86f1558614b3e87d  IDENTICO
journal-video.json       destino video/Blink.avi  sha_nuevo 541c29e4c582250e  IDENTICO
journal-boot-audio.json  destino startup.avi      sha_nuevo e7b85961ba95a3e9  IDENTICO
```

Re-corridas (mismo spec, mismo día, horas después de instalar):

| spec | sha256 re-corrido | sha instalado |
|---|---|---|
| `spec-boot.json` | `86f1558614b3e87d…` | `86f1558614b3e87d…` |
| `spec-video.json` | `541c29e4c582250e…` | `541c29e4c582250e…` |
| `spec-boot-audio.json` | `e7b85961ba95a3e9…` | `e7b85961ba95a3e9…` |

`build/boot-chime.wav` y la copia congelada comparten sha (`442e4087cf0731d3…`), así
que la tercera fila es comparable. `pytest`: **184 passed**. `profile --control`: 62
archivos, 0 rechazados.

Observación en pantalla (la parte que no se puede capturar desde el repo): tras el
reboot, Danny reportó "si salio malbolgato" — el arranque mostró el clip propio. No
hay captura de cámara sellada, así que la claim se queda en `CONDITIONAL_PASS`, no
sube a `PASS`.

## VERDICT — tabla de claims

| # | Claim | Estado |
|---|---|---|
| 1 | Los bytes instalados en el dispositivo son byte a byte los que produjeron `spec → build` en este repo (3/3 `IDENTICO`) | PASS |
| 2 | La cadena sigue siendo determinista horas después de la escritura (3/3 sha idéntico al instalado) | PASS |
| 3 | Cada archivo instalado valida `0 duros` contra `mochi-factory-v1` | PASS |
| 4 | Controles verdes: 184 tests y `profile --control` 62/0 rechazados | PASS |
| 5 | El firmware de fábrica reproduce en el arranque un AVI generado por este SDK | **CONDITIONAL_PASS** — observado en pantalla por el operador el 2026-11-06; sin captura de cámara, no sube a PASS |
| 6 | El PCM mono instalado (`boot-chime.wav` → `e7b85961`) suena en el arranque | NOT_DEMONSTRATED |
| 7 | El slot del playlist (`video/Blink.avi` = `541c29e4`) se reproduce | NOT_DEMONSTRATED — su disparo físico es desconocido (MOCHI-REA-03) |
| 8 | `deploy.apply` conserva un backup util por escritura cuando dos escrituras apuntan al mismo destino con el mismo `backup_root` | **FAIL** — `journal-boot` quedó apuntando a `86f15586` cuando su `sha_previo` es `dbd65d1f` |
| 9 | Tras el fix, dos escrituras al mismo destino conservan backups distinguibles y el rollback de la primera restaura el estado original; con un backup adulterado, `rollback` se niega **antes** de escribir | PASS — `test_dos_escrituras_al_mismo_destino_no_chocan_en_el_backup` y `test_rollback_rechaza_un_backup_adulterado`, en volumen falso de `/tmp` |

## ALCANCE DEMOSTRADO

H1 aceptada de forma condicional para **el slot de arranque**: un AVI propio, con
audio PCM mono, se reproduce. La identidad de bytes y el determinismo de la cadena
están demostrados sin condición. El fallo 8 está demostrado con números del propio
dispositivo y su reparación, en volumen falso.

## NO DEMOSTRADO (explícito)

* Que el clip del playlist se muestre alguna vez (desconocido el disparo físico).
* Que el chime se oiga.
* Relectura del volumen en este instante: `grep sda1 /proc/mounts` devuelve rc 1, el
  volumen no está montado, así que no hay prueba *en vivo* de que `startup.avi` siga
  siendo `e7b85961`. Lo que se prueba es la cadena de escrituras sellada.
* Que `dbd65d1f` (el AVI ajeno reparado) pueda recuperarse desde el journal afectado.
  El original de fábrica sí está preservado: `~/megamochi-backup/volume_files/startup.avi`
  = `acb6afb9d8e9494d…`, y la reparación del bug impide que la colisión se repita.

## ROLLBACK — orden real y estado

1. `journal-boot-audio.json` → restaura `86f15586` (backup sano).
2. `journal-video.json` → restaura `087788a2` (backup sano).
3. `journal-boot.json` → **no usable tal cual**: su backup ya no es `dbd65d1f`. Para
   volver al estado de fábrica hay que instalar `volume_files/startup.avi`
   (`acb6afb9…`) con un plan nuevo, no con este journal.

## Notas de proceso

* El hallazgo 8 salió de intentar responder una pregunta inocente ("¿puedo hacer
  rollback de la primera escritura?"), no de un pedido. Se corrigió el código en vez
  de la documentación: `deploy.apply` ahora nombra el backup con
  `destino_relativo__sha_previo[0:8]` y `rollback` verifica el backup **antes** de
  copiarlo. El journal por defecto pasó a `journal-<sello>-<token>[0:12].json` porque
  un único `journal.json` por `backup_root` hacía que la segunda aplicación borrara
  el historial de la primera (eso lo cazó el propio test de colisión).
* La claim 5 no sube a PASS hasta que exista una captura de cámara o una relectura
  del volumen montado; así queda también en `README.md`.
