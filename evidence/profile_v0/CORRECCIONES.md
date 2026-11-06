# Corrección appended 2026-11-06 (no se reescribió nada del pack)

El manifest de este pack quedó **desfasado** respecto de disco: despues de
sellarlo se volvieron a tocar `profiles/mochi-factory-v1.json` (se le sacó la
marca de tiempo para que la medición sea byte-reproducible),
`tools/measure_corpus.py` y `mochisdk/container.py`. `verify` reporta 3 hash
mismatch por ese motivo.

Los números del `stdout.raw.txt` de esta corrida siguen siendo la medida de los
mismos 62 archivos; lo que cambió es la reproducibilidad del artefacto.

Estado: **SUPERSEDED** por `evidence/profile_v1`, que sella la medición
determinista (dos corridas, mismo sha256) y verifica PASS.
