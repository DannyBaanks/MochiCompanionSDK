
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
