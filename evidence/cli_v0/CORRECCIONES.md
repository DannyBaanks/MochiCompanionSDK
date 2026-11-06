# CORRECCIONES — `evidence/cli_v0` (append-only; el crudo nunca se editó a mano)

## 2026-11-06 ~11:55Z — drift descubierto al re-sellar: el crudo fue reescrito DESPUÉS del sello

**El hecho, medido en disco.** El `manifest.json` original se creó a las
`2026-11-06T10:53:29Z` y registro como stdout el sha256
`845ebc4820386a14cb7ca2405d08b2ab85fa4b40e99af6c668ea973472f40824`. El archivo
`stdout.raw.txt` que está en disco ahora tiene mtime **10:59:25Z** — seis
minutos después de ese sello — y sha256
`59dbff2aede581a685e617e3f2b5517f700c4bd4fec2be054e46815f1849dca6`.

**Qué pasó.** A las 10:59Z se volvió a correr `python3 tools/capture_cli.py`
para añadir los dos bloques de interoperabilidad con Companion (la §3.11 de
GUIA). Ese re-run pisó su propio crudo: de 24 bloques pasó a 26. El documento
nunca se re-verificó contra el sello anterior, así que el pack quedó con un
hash de stdout que ya no existía. Es la misma clase de fallo que mató a
`evidence/profile_v0`, y por eso se registra aparte en vez de corregir el
manifest viejo.

**Qué NO se perdió.** El crudo anterior (24 bloques, `845ebc48…`) ya no está en
disco: no se puede volver a hashear ni comparar. Queda aqui su identificador.
Ningún byte del crudo actual fue editado a mano; es salida textual de
subprocess. Los hashes de los AVI citados dentro del crudo coinciden con los
artefactos sellados (`demo-thinking.generated.avi` = `77a9df099345f584…`), así
que la corrida de las 10:59Z reprodujo el mismo archivo: el claim de
determinismo sigue en pie y ahora tiene un segundo punto de apoyo.

**Claims corregidos en el re-sello.**

1. Claim 1 decía "Los 24 comandos documentados en GUIA.md". El crudo actual
   tiene 26 bloques con su exit code: 24× `exit 0`, un `exit 4` (token
   incorrecto) y un `exit 3` (origen inexistente). Corregido, con el desglose.
2. Claim 4 atribuía a este crudo el `exit 5` del rechazo. Falso:
   `grep -c "exit 5" evidence/cli_v0/stdout.raw.txt` = **0**. El código 5 sí
   existe y sí se observó, pero en otro experimento creado para la ocasión:
   `evidence/refusals_v0` (`python3 tools/capture_refusals.py`), donde aparece
   dos veces — por spec y por `--par` — con su control positivo al lado. El
   claim 4 queda solo con el 3, y se añadió el claim 11 declarando el hueco en
   lugar de taparlo.
3. Los documentos hasheados (`GUIA.md`, `README.md`, `AGENTS.md`,
   `tools/capture_cli.py` y los módulos) cambiaron de contenido después del
   sello original; `build --force` actualizó sus hashes. Este archivo también
   queda sellado como artefacto.

**Nada de esto cambia un resultado experimental.** Los exit codes, los sha256
de los AVI, el token `4cce25869afb`, los 62 round-trips, los 180 tests y la
interoperabilidad con el validador de Companion son los mismos bytes y los
mismos números. Lo corregido es la prosa que los describía y el hecho de que el
sello anterior apuntaba a un crudo superado.

## 2026-11-06 ~12:00Z — el guard que existe porque este pack perdió un crudo

Para que el incidente de arriba no se repita, `tools/capture_cli.py` y
`tools/capture_refusals.py` ahora llaman a `guard_out()` antes de escribir: si
el `stdout.raw.txt` destino existe **y** hay un `manifest.json` en su carpeta,
el script se niega (`SystemExit`, mensaje con la ruta nueva sugerida
`evidence/<slug>_v1/stdout.raw.txt`) y no toca un byte. `--fuerza` es la única
salida, para el caso en que el operador quiere re-sellar el mismo pack — es
decir, exactamente lo que se hizo aquí.

Lo cubren dos pruebas nuevas en `tests/test_spec_render_bridge.py`:
`test_guard_out_niega_pisar_un_crudo_sellado` (exige `REFUSAL`, `--out` y
`--fuerza` en el mensaje y comprueba que el crudo sigue igual) y
`test_guard_out_permite_escribir_sin_manifest_o_con_fuerza`. La suite pasó de
180 a **182**.

**Lineage del número de pruebas, para que nadie lo lea como contradicción.**
El claim 6 del manifest dice 180 porque eso es lo que imprime el crudo sellado
(`stdout.raw.txt`, bloque 26: `180 passed in 2.99s`). El artefacto
`tests/test_spec_render_bridge.py` que hashea ese mismo manifest es la versión
de 182. No hay una corrida con 182 dentro de este crudo; la prueba del guard se
agregó después de la captura y **no** se re-capturó, porque re-capturar es lo
que destruyó el crudo de 24 bloques. GUIA §3.13 repite esta misma distinción.

**Lo que NO cambia:** ningún exit code, ningún sha256 de AVI, ningún token,
ninguna claim PASS/NOT_DEMONSTRATED de la tabla. Solo se sumó protección y se
explicitó de dónde sale cada número.

---

## Re-sellado 2026-11-06T12:29Z — motivo: `mochisdk/profile.py` cambió

Este pack se volvió a sellar (`evidence_tool.py build --force`) **solo** porque
el manifest hashea `mochisdk/profile.py` y ese archivo cambió despues del sellado
original. Los salidas crudas y los demas artefactos no se tocaron: el `stdout`
verificado sigue siendo el mismo bytes que en el sellado anterior.

Que cambió en el codigo y por que: las reglas de audio `strf.audio.pcm`,
`strh.audio.campos` y `audio.quantum` dejaron de comparar contra la constante
"mono / 3200 B" y pasaron a comparar contra **relaciones derivadas** medidas en
los 63 archivos reales del volumen (62 de `video/*.avi` + `startup.avi`):
`block_align == canales·bits/8`, `avg_Bps == rate·block_align`,
`strh.sample_size == block_align`, `quantum == avg_Bps/fps ==
strh.auds.suggested_buf`, `dwLength == muestras/frame·n`. "Mono" quedó en 62/63,
o sea soft; era un falso positivo rechazar el `startup.avi` de fábrica, que es
estéreo. Evidencia completa: `evidence/foreign_startup_v0/CORRECCIONES.md` y
`evidence/startup_write_v0/`.

Regresión medida despues del cambio: `python3 -m pytest tests/ -q` → 182 passed;
`./mochic profile --control` → 62 archivos, 0 rechazos, veredicto PASS;
`python3 -m pytest tests/test_profile_validate.py -q -k "mutante or rechazo"` →
12 passed. Un mutante de tamano de chunk sigue produciendo 5 hallazgos duros.

## 2026-11-06 (tarde) — README.md reescrito como documento de producto y `deploy.py` endurecido

Dos artefactos de este manifest cambiaron de bytes sin que cambie nada de lo que
afirma el crudo (que sigue intacto, `guard_out` mediante):

1. `README.md` pasó de formato de investigación a documento de producto. Los
   números que muestra son los mismos y salen de los packs que ya estaban sellados;
   lo que cambió fue la prosa y la tabla de claims.
2. `mochisdk/deploy.py` tenía un defecto real que se encontró al querer hacer
   rollback de la primera escritura al slot de arranque: el backup se nombraba por
   `basename(dst)`, así que la segunda escritura al mismo destino pisó el archivo al
   que apunta el primer journal (`sha_previo dbd65d1f…` con un backup que hoy vale
   `86f15586…`). Medido en `evidence/our_build_v1/stdout.raw.txt`. Además, el
   journal por defecto era un único `journal.json` por `backup_root`, y la segunda
   `apply` borraba el historial de la primera — lo cazó el test de colisión.
   Hoy: backup `destino_relativo__sha_previo[0:8]`, journal
   `journal-<sello>-<token>[0:12].json`, y `rollback` verifica el backup **antes**
   de copiarlo. La suite pasó de 182 a **184** con los dos controles nuevos
   (`test_dos_escrituras_al_mismo_destino_no_chocan_en_el_backup`,
   `test_rollback_rechaza_un_backup_adulterado`), ambos en volumen falso de `/tmp`.

Ningún bloque del crudo de este pack describe el comportamiento de backup o de
nombre de journal, así que ninguna claim existente queda falsa por el cambio. La
claim "el firmware reproduce un AVI generado por este SDK" sigue
`NOT_DEMONSTRATED` **dentro del alcance de este pack** (aquí no se miró el
dispositivo); se resolvió aparte en `evidence/our_build_v1` como
`CONDITIONAL_PASS` para el slot de arranque. Se re-selló con
`evidence_tool.py build --force`: mismos command/exit/stdout/claims, hashes
actualizados y las dos claims nuevas que se ven en el manifest.

Segundo re-sello el mismo día, por tres ediciones de documentación que no cambian
ningún número: el bloque de arranque del `README.md` ahora muestra el comando real
(`mochic plan VOLUMEN examples/demo-thinking.json`, con el destino `video/…` que
sale del spec) en lugar de un `--par ...` abreviado; se quitó un enlace de GitHub
que no estaba verificado; y en `GUIA.md` trampa 12 se tachó el número de serie del
disco de la workstation (`gio mount -l`), que no es dato del experimento. El crudo
de este pack no contiene ninguna de esas cadenas.


