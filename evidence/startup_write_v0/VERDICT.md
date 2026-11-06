# VERDICT — `startup_write_v0` (primera escritura autorizada al slot de arranque)

## QUESTION

Danny autorizó explícitamente pasar el `startup.avi` de `~/Descargas` al Mochi
(«intenta pasar el startup.avi de descargas al del mochi para ver como sirve»).
Dos incertidumbres: (1) ¿falla la escritura por el dispositivo o por el
explorador gráfico? (2) ¿qué hay que corregir en el SDK para que el slot de
arranque sea operable?

## PRIOR_EVIDENCE

* `evidence/foreign_startup_v0/` — el activo de arranque de fábrica es **stéreo**
  y el validator lo rechazaba con 3 duros (falso positivo del perfil de playlist).
* Journal de kernel 06:19:35 — el dispositivo se re-enumeró otra vez; la ventana
  de Nautilus seguía apuntando al GMount muerto.

## HYPOTHESIS

* H1 — el bloqueo «los permisos no permiten pegar» es del explorador (montaje
  caducado), no del volumen: una escritura por ruta de sistema debe completar.
* Falsación: `apply` falla con EPERM/EROFS/EIO sobre el mismo montaje.

## EXPERIMENTO

Cuatro pasos, todos con salida cruda en `stdout.raw.txt`:

1. `deploy.plan` sobre el archivo **tal cual** → rechazo, cero escrituras.
2. `tools/fix_suggested_buf.py` → copia reparada, 2 bytes, origen intacto.
3. `mochic plan … --par <reparado> startup.avi` → 0 duros, 2 suaves, token.
4. `mochic apply --token 47e45cafa60e --copia ~/megamochi-backup/deploy_2026-11-06_bootslot`
   → `sync` → `sha256sum` del dispositivo.

Corrección de fondo hecha en el mismo experimento: `mochisdk/profile.py` dejó de
exigir «mono exacto» y ahora verifica **relaciones derivadas** medidas en los 63
archivos reales del volumen: `block_align == canales·bits/8`,
`avg_Bps == samples_per_sec·block_align`, `strh.sample_size == block_align`,
`quantum == avg_Bps/fps == strh.auds.suggested_buf`, `dwLength == muestras/frame·n`.
El invariante `strh.vids.suggested_buf == mayor JPEG` sigue siendo duro (63/63).

## CONTROLES

* **Positivo:** el respaldo del contenido previo se verificó byte a byte antes de
  escribir (`4f7d6b43…`, idéntico al congelado de `foreign_startup_v0`) y el
  post-check de `apply` comparó el sha del destino contra el del origen.
* **Negativo:** el propio portón rechazó el archivo sin reparar (`AviError:
  strh.video.suggested_buf`, exit 1) y no tocó el volumen — la puerta sigue
  cerrada para lo no conforme; la reparación no es una vía de escape porque
  `fix_suggested_buf.py` refusaría cualquier otro hallazgo duro.
* **Regresión:** `python3 -m pytest tests/ -q` → 182 passed; el mutante de audio
  en bloques (`startupEJEMPLO`) sigue con 6 duros, ahora incluido
  `audio.quantum` derivado (16384 ≠ 6400).

## CLAIMS

| # | claim | estado |
|---|---|---|
| 1 | La ruta de escritura funciona desde el sistema de archivos: `apply` escribió 1 443 076 B, `sha256sum /media/danny/MEGAMOCHI/startup.avi` = `dbd65d1f…` igual al origen, sin EIO/EROFS y sin «Remounting read-only» en el journal | PASS |
| 2 | El «los permisos no permiten pegar» es del explorador con GMount caducado (Nautilus del 5-nov 22:52, `gio mount -l` sin Mount), no del Mochi | PASS |
| 3 | `deploy.plan` rechaza un origen con hallazgos duros sin escribir nada | PASS |
| 4 | La reparación son 2 bytes en el offset 144 (12132 → 7737); el resto del contenedor bit a bit igual; la copia pasa con 0 duros | PASS |
| 5 | Con las reglas derivadas el `startup.avi` de fábrica deja de ser falso positivo (0 duros, 2 suaves) y los 62 del playlist siguen en 0 duros | PASS |
| 6 | Qué se ve y se oye en el dispositivo con este archivo | NOT_DEMONSTRATED (requiere reiniciar el Mochi, acción física de Danny) |

## ROLLBACK

`./mochic rollback ~/megamochi-backup/deploy_2026-11-06_bootslot/journal.json`
devuelve el contenido previo (`4f7d6b43…`). El original de fábrica sigue en
`~/megamochi-backup/volume_files/startup.avi` (`acb6afb9…`) y restaurar
directamente ese archivo también es posible con `mochic plan --par`.

## ALCANCE

Una escritura, un destino, un parámetro reparado. No se tocó `ui.bin`,
`playlist.lst`, `video/` ni firmware. Nada de este pack prueba comportamiento del
reproductor: eso lo decide el reinicio físico.
