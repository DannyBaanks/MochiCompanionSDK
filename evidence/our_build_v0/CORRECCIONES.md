# CORRECCIONES — our_build_v0

## 2026-11-06 — dos claims cambiaron de estado, este pack NO se reescribió

* Claim 7 ("el firmware reproduce nuestros archivos, arranque y slot Blink") queda
  **sustituida** por `evidence/our_build_v1`, que la separa en dos: el slot de
  arranque pasa a `CONDITIONAL_PASS` (el operador lo vio en pantalla tras el reboot;
  sigue sin haber captura de cámara) y el slot del playlist sigue `NOT_DEMONSTRATED`
  porque se desconoce su disparo físico. El `stdout.raw.txt` y el `VERDICT.md` de
  este pack se conservan tal cual; el crudo no se toca.
* Apareció además un fallo propio que este pack no vio: `deploy.apply` nombraba el
  backup solo por `basename`, así que la escritura `journal-boot-audio` sobrescribió
  el backup al que apunta `journal-boot`. El crudo de `our_build_v1` lo documenta con
  números (`sha_previo dbd65d1f` vs `backup 86f15586`) y `deploy.py` está corregido
  con controles en `tests/test_deploy_playlist.py`. Consecuencia práctica para
  cualquiera que tenga este pack delante: el rollback del arranque con
  `journal-boot.json` **no** restaura `dbd65d1f`; para volver a fábrica hay que
  instalar `~/megamochi-backup/volume_files/startup.avi` (`acb6afb9…`) con un plan
  nuevo.
