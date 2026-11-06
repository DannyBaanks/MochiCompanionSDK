"""Captura el crudo del experimento `foreign_startup_v0` y lo deja listo para sellar.

Existe porque el 2026-11-06 06:01 Danny reemplazo `startup.avi` del volumen por
un AVI generado por otro modelo y el Mochi respondio con audio si y pantalla en
blanco. Convertir eso en informacion exige una tabla campo por campo contra el
archivo de fabrica, y esa tabla tiene que ser reproducible.

No toca el dispositivo salvo para LEER: el unico acceso de escritura que aparece
aca es `sha256sum` del archivo que hoy esta en el volumen, que es una lectura.
El crudo se protege con el mismo `guard_out` de capture_cli: si el pack ya esta
sellado, niega pisarlo y manda abrir una version nueva.

Uso:
  python3 tools/capture_foreign.py                      # escribe el crudo
  python3 tools/capture_foreign.py --out evidence/foreign_startup_v1/stdout.raw.txt
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = '/tmp/mochi-foreign'
INPUTS = os.path.join(ROOT, 'evidence', 'foreign_startup_v0', 'input')
VOLUME_FILE = '/media/danny/MEGAMOCHI/startup.avi'


def _guard():
    spec = importlib.util.spec_from_file_location(
        'capcli', os.path.join(ROOT, 'tools', 'capture_cli.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(cmd, blocks):
    """Ejecuta `cmd` (lista de argumentos, sin shell) y agrega su bloque literal."""
    p = subprocess.run(list(cmd), cwd=ROOT, capture_output=True, text=True)
    shown = ' '.join(cmd)
    out = p.stdout + p.stderr
    blocks.append('$ %s\n[exit %d]\n%s' % (shown, p.returncode, out.rstrip('\n')))
    print('[%3d] %s' % (p.returncode, shown[:96]), file=sys.stderr)
    return p.returncode


def main(argv=None) -> int:
    a = _ap().parse_args(sys.argv[1:] if argv is None else argv)
    _guard().guard_out(a.out, a.fuerza)
    os.makedirs(WORK, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    todos = sorted(os.path.join(INPUTS, f) for f in os.listdir(INPUTS) if f.endswith('.avi'))
    if len(todos) != 3:
        raise SystemExit('REFUSAL: se esperaban 3 entradas congeladas, hay %d' % len(todos))

    blocks = []
    run(['sha256sum'] + todos, blocks)
    if os.path.isfile(VOLUME_FILE):
        rc = run(['sha256sum', VOLUME_FILE], blocks)
        blocks[-1] += '\n(esta linea es una LECTURA del volumen; no se escribio nada)'
        if rc == 0:
            disk = open(VOLUME_FILE, 'rb').read()
            igual = [os.path.basename(p) for p in todos
                     if open(p, 'rb').read() == disk]
            blocks.append('$ # identificacion del archivo que hoy esta en el volumen\n'
                          'coincide byte a byte con: %s' % (igual or 'ninguna entrada congelada'))
    else:
        blocks.append('$ sha256sum %s\n[exit 3]\n(no existe: el volumen no esta montado '
                      'en este momento, esta seccion NO_DEMONSTRATED)' % VOLUME_FILE)
    run(['python3', 'tools/diagnose_foreign.py', '--junit'] + todos, blocks)
    for p in todos:
        run(['./mochic', 'validate', p], blocks)
    for p in todos:
        run(['./mochic', 'inspect', p], blocks)

    texto = '\n\n'.join(blocks) + '\n'
    with open(a.out, 'w', encoding='utf-8') as fh:
        fh.write(texto)
    print('crudo: %s (%d bytes, %d bloques)' % (a.out, len(texto.encode()), len(blocks)),
          file=sys.stderr)
    return 0


def _ap():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', default='evidence/foreign_startup_v0/stdout.raw.txt')
    ap.add_argument('--fuerza', action='store_true',
                    help='pisar aunque el crudo este sellado por un manifest')
    return ap


if __name__ == '__main__':
    sys.exit(main())
