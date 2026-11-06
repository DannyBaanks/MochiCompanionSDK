"""Captura los codigos de salida que GUIA.md promete pero cli_v0 no mostro.

El pack `evidence/cli_v0` dejo crudo solo los codigos 0, 3 y 4. Faltaban los
tres que la tabla de GUIA §4 declara contractuales: 1 (hallazgo duro), 2 (uso)
y 5 (operacion rehusada porque NO esta demostrada). Sin crudo propio esos
codigos quedaban respaldados unicamente por la suite de pruebas.

Metodo: cada refusals se acompana de un control positivo, la misma orden con
argumentos validos, para que el rechazo no pueda ser un falso positivo.
  * codigo 1: un mutante hecho a mano (tamano de un registro 01wb 3200 -> 3000)
    y un valor de estado que el protocolo companion-event-v1 no acepta.
    Control positivo: `validate` del mismo AVI sin mutar devuelve 0.
  * codigo 2: `plan` sin spec ni --par, y `playlist` sin volumen.
    Control positivo: los mismos comandos bien formados devuelven 0.
  * codigo 5: `plan` contra un destino que no existe en playlist.lst.
    Control positivo: el mismo `plan` con un destino que si existe devuelve 0.

Nada de esto abre un dispositivo: el volumen es un arbol de copias en /tmp.

Repetibilidad: el crudo NO es byte-identico entre corridas porque el control
positivo de `plan` imprime `creado_utc` y su `token` derivado. Todo lo demas,
incluidos los codigos de salida que este pack afirma, es estable.

Uso:
  python3 tools/capture_refusals.py [--out evidence/refusals_v0/stdout.raw.txt]
"""
from __future__ import annotations

import argparse, importlib.util, json, os, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
MOCHIC = os.path.join(ROOT, 'mochic')
PACK = os.path.expanduser('~/Development/ISyCo Git/Companion/packs/malbolge-cat')
WORK = '/tmp/mochi-refusals'


def _capture_cli():
    spec = importlib.util.spec_from_file_location('capture_cli',
                                                 os.path.join(ROOT, 'tools', 'capture_cli.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _build_fake_volume(target: str) -> None:
    _capture_cli().build_fake_volume(target)


def run(cmd, blocks, shown=None):
    r = subprocess.run([MOCHIC] + cmd, capture_output=True, text=True, cwd=ROOT)
    label = shown if shown is not None else ' '.join(
        '"%s"' % x if ' ' in x else x for x in cmd)
    blocks.append('$ mochic %s\n[exit %d]\n%s%s' % (label, r.returncode, r.stdout, r.stderr))
    return r.returncode


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'evidence', 'refusals_v0',
                                                  'stdout.raw.txt'))
    ap.add_argument('--vol', default='/tmp/mochi-fake-vol')
    ap.add_argument('--fuerza', action='store_true',
                    help='reescribir el crudo de un pack ya sellado (exige re-sellar)')
    a = ap.parse_args(argv)

    _capture_cli().guard_out(a.out, a.fuerza)

    src = os.path.join(ROOT, 'build', 'demo-thinking.avi')
    if not os.path.isfile(src):
        print('falta %s (primero `./mochic build examples/demo-thinking.json`)' % src,
              file=sys.stderr)
        return 3
    _build_fake_volume(a.vol)
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)

    from mochisdk import deploy, load_avi
    asset = load_avi(src)
    buf = bytearray(open(src, 'rb').read())
    off = asset.audio[0].header_off + 4          # campo dwSize del registro 01wb
    antes = int.from_bytes(buf[off:off + 4], 'little')
    buf[off:off + 4] = (3000).to_bytes(4, 'little')
    mutante = os.path.join(WORK, 'mutante.avi')
    open(mutante, 'wb').write(bytes(buf))

    blocks = []
    blocks.append('# mutante: un registro 01wb declarado de %d B en lugar de %d B'
                  % (3000, antes))
    blocks.append('$ sha256 original / mutante\n%s  %s\n%s  %s'
                  % (deploy.sha256_file(src), os.path.relpath(src, ROOT),
                     deploy.sha256_file(mutante), mutante))

    # --- codigo 1: hallazgo duro ---
    run(['validate', mutante], blocks)
    run(['validate', src], blocks)                       # control positivo
    run(['spec', '--pack', PACK, '--fotogramas', '2', '-o', os.path.join(WORK, 's.json')],
        blocks)
    inb = os.path.join(WORK, 'in.jsonl')
    run(['emit', 'state', '--inbox', inb, '--valor', 'flotante'], blocks)
    probe = ('test -e "%s" && echo EXISTE || echo "NO EXISTE: el evento invalido no se escribio"'
             % inb)
    p = subprocess.run(['bash', '-c', probe], capture_output=True, text=True)
    blocks.append('$ %s\n[exit %d]\n%s' % (probe, p.returncode, p.stdout))
    inbox_intacto = 'NO EXISTE' in p.stdout

    # --- codigo 2: uso ---
    run(['plan', a.vol], blocks)
    run(['playlist'], blocks)
    rc_pl = run(['playlist', a.vol], blocks)             # control positivo
    rc_pl |= run(['map', '--mostrar'], blocks)           # control positivo

    # --- codigo 5: operacion rehusada (NO esta demostrado) ---
    run(['plan', a.vol, '--par', 'build/demo-thinking.avi', 'video/NoExiste.avi'], blocks)
    run(['spec', '--pack', PACK, '--slot', 'NoExiste.avi', '--id', 'rehusa',
         '-o', os.path.join(WORK, 'spec-rehusa.json')], blocks)
    run(['plan', a.vol, os.path.join(WORK, 'spec-rehusa.json')], blocks)
    rc_ok = run(['plan', a.vol, '--par', 'build/demo-thinking.avi', 'video/Squint.avi',
                 '--salida', os.path.join(WORK, 'plan-ok.json')], blocks)
    destino = json.load(open(os.path.join(WORK, 'plan-ok.json')))['operaciones'][0]['destino']

    text = '\n'.join(blocks) + '\n'
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, 'w') as fh:
        fh.write(text)
    print('capturados %d bloques en %s' % (len(blocks), a.out))
    print(' '.join(ln for ln in text.splitlines() if ln.startswith('[exit ')))
    ok = rc_pl == 0 and rc_ok == 0 and inbox_intacto and destino == 'video/Squint.avi'
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
