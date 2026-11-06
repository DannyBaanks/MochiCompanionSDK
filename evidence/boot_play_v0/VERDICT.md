# VERDICT — `boot_play_v0` (arranque real con el asset generado y reparado)

## QUESTION

Despues de `startup_write_v0` (el slot de arranque del Mochi contiene el AVI
`dbd65d1f…`, reparado en 2 bytes y validado con 0 hallazgos duros), la pregunta
pendiente del pack anterior era: ¿reproduce el firmware un AVI que no salio del
muxer de fabrica, y que dice eso de las desviaciones que dieron pantalla en blanco?

## PRIOR_EVIDENCE

* `evidence/startup_write_v0/` — sha del destino despues de `apply` y `sync`:
  `dbd65d1fdf1ceafc360a51bf5590bbcbcdb527daf1ededd5dbf56bf322def3a4`.
* `evidence/foreign_startup_v0/` — el archivo que dio pantalla en blanco
  (`4f7d6b43…`) violaba 4 propiedades estructurales a la vez.

## METRIC

Que el Mochi, al encenderse despues del cambio, muestre **video** ademas del
audio del asset nuevo. Criterio binario, declarado antes del reinicio en la
descripcion de la tarea #11.

## MEASURE

* 06:27 local — `apply` + `sync` + verificacion post-escritura (crudo en
  `startup_write_v0`).
* 06:33 local — Danny apaga y enciende el dispositivo. Reporte textual del
  operador: **«funciono perfecto»**.
* 06:34 local — lectura de estado despues del arranque: el volumen ya **no** esta
  montado y el journal del kernel muestra el bucle de enumeracion `-71`
  (`device not accepting address 3..8, error -71`, `unable to enumerate USB
  device`). Es la firma del MSC atascado despues de un ciclo de energia, no un
  efecto de la escritura.

## CONTROLES

* **Positivo:** el archivo instalado se verifico por sha *despues* del `sync` y
  *antes* del reinicio; ademas `mochic validate` sobre la copia congelada da 0
  duros, asi que lo que se reprodujo es exactamente el asset conforme.
* **Negativo (histórico, del pack anterior):** el contenedor no conforme
  (`4f7d6b43…`) en el mismo slot produjo audio sin video. El par no-conforme /
  conforme en el mismo destino es el contraste que da valor al resultado.

## CLAIMS

| # | claim | estado |
|---|---|---|
| 1 | El Mochi reproduce en el slot de arranque un AVI que no vino del muxer de fabrica, siempre que el contenedor cumpla el perfil | CONDITIONAL_PASS — observado por el operador con el mismo archivo que verificamos por sha; sin grabacion con camara en este pack |
| 2 | La pantalla en blanco del intento anterior se debe a las desviaciones de contenedor (audio en bloques de 16384 B, 155 registros en lugar de 223, sin `vprp`, chunk final de 5888 B), y no a `suggested_buf` | CONDITIONAL_PASS — se descartó `suggested_buf` como unica causa porque el archivo que fallo lo tenia coherente (7719 == 7719) y el que fallo igual |
| 3 | Tras el ciclo de energia el MSC del Mochi dejo de enumerar (`-71` xN, `unable to enumerate`); recuperacion documentada: apagar, desenchufar 60 s, reenchufar, encender con K2 | PASS |
| 4 | Una grabacion de video del arranque sellaria el claim 1 sin depender del testimonio | NOT_DEMONSTRATED |
| 5 | Que el firmware acepte un `startup.avi` **mono** generado por `mochic build` | NOT_DEMONSTRATED |

## ALCANCE

Un destino, un archivo, un ciclo de energia. No se modifico `ui.bin`,
`playlist.lst`, `video/` ni firmware. La observacion del claim 1 es testimonial:
la grabacion con camara sigue pendiente y es lo unico que falta para subirlo a
PASS.
