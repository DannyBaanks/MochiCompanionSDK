"""Crudo reproducible del experimento `our_build_v1`.

Pregunta: ¿el firmware reproduce un AVI generado por ESTE SDK? `our_build_v0`
quedo con esa claim en NOT_DEMONSTRATED porque el 2026-11-06 12:47Z el volumen
desaparecio al rebotar y no se pudo releer. Danny reintentó despues y reporto
que el arranque mostro al Malbolgato, o sea el archivo de `mochic build`. Este
crudo sella lo que si es verificable desde el repo:

  * que los bytes instalados son byte a byte los que produjeron `spec -> build`
    (journal.sha_nuevo == sha256 del input congelado en el pack);
  * que re-corrida la cadena el SDK vuelve a producir exactamente esos bytes;
  * los controles positivos (suit de tests y `profile --control`).

No escribe en el dispositivo: solo lee el estado de montaje y, si esta presente,
el sha256 de `startup.avi`. Si no esta montado, la seccion queda marcada como
NO_DEMONSTRATED en lugar de inventarse una linea.

Uso:
  python3 tools/capture_our_build.py
  python3 tools/capture_our_build.py --out evidence/our_build_v1/stdout.raw.txt
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACK0 = os.path.join(ROOT, 'evidence', 'our_build_v0')
VOLUME = '/media/danny/MEGAMOCHI'

# (journal y spec congelados en ESTE pack, input congelado en our_build_v0)
PARES = [
    ('journal-boot.json', 'spec-boot.json', 'input/startup__nuestro_86f15586.avi'),
    ('journal-video.json', 'spec-video.json', 'input/Blink__nuestro_541c29e4.avi'),
    ('journal-boot-audio.json', 'spec-boot-audio.json',
     'input/startup__nuestro_con_campana_e7b85961.avi'),
]


def _guard():
    spec = importlib.util.spec_from_file_location(
        'capcli', os.path.join(ROOT, 'tools', 'capture_cli.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(cmd, blocks, nota=None):
    p = subprocess.run(list(cmd), cwd=ROOT, capture_output=True, text=True)
    blocks.append('$ %s\n[exit %d]\n%s%s' % (' '.join(cmd), p.returncode,
                                             (p.stdout + p.stderr).rstrip('\n'),
                                             '\n' + nota if nota else ''))
    print('[%3d] %s' % (p.returncode, ' '.join(cmd)[:96]), file=sys.stderr)
    return p.returncode


def main(argv=None) -> int:
    a = _ap().parse_args(sys.argv[1:] if argv is None else argv)
    _guard().guard_out(a.out, a.fuerza)
    pack1 = os.path.dirname(os.path.abspath(a.out))
    os.makedirs(pack1, exist_ok=True)

    blocks = []
    run(['date', '-u', '+%Y-%m-%dT%H:%M:%SZ'], blocks)
    rc = run(['grep', 'sda1', '/proc/mounts'], blocks,
             nota='(rc 1 = el volumen NO esta montado ahora mismo)')
    if rc == 0:
        run(['sha256sum', os.path.join(VOLUME, 'startup.avi')], blocks,
            nota='(lectura del volumen; aqui no se escribe nada)')

    congelados = [os.path.join(PACK0, rel) for _, _, rel in PARES]
    run(['sha256sum'] + congelados, blocks)
    run(['sha256sum', os.path.join(PACK0, 'input', 'boot-chime.wav'),
         'build/boot-chime.wav'], blocks,
        nota='(el re-corrido del spec con audio solo es comparable si estos dos shas calzan)')

    lineas = []
    for jrel, _srel, irel in PARES:
        j = json.load(open(os.path.join(pack1, jrel)))
        e = j['entradas'][0]
        med = subprocess.run(['sha256sum', os.path.join(PACK0, irel)],
                             capture_output=True, text=True).stdout.split()[0]
        lineas.append('%-24s destino %-16s sha_nuevo %s  input_congelado %s  %s'
                      % (jrel, e['destino'], e['sha_nuevo'][:16], med[:16],
                         'IDENTICO' if med == e['sha_nuevo'] else 'DIFIERE'))
    blocks.append('$ # identidad entre lo instalado (journal) y lo congelado (pack)\n'
                  + '\n'.join(lineas))

    lineas = []
    for jrel, _srel, _irel in PARES:
        j = json.load(open(os.path.join(pack1, jrel)))
        e = j['entradas'][0]
        if os.path.isfile(e['backup']):
            med = subprocess.run(['sha256sum', e['backup']],
                                 capture_output=True, text=True).stdout.split()[0]
            estado = 'OK' if med == e['sha_previo'] else 'COLISION: ya no es el estado previo'
            lineas.append('%-24s sha_previo %s  backup %s  %s\n%-24s                 %s'
                          % (jrel, e['sha_previo'][:16], med[:16], estado, '', e['backup']))
        else:
            lineas.append('%-24s backup ausente: %s' % (jrel, e['backup']))
    blocks.append('$ # integridad de los backups referenciados por cada journal '
                  '(fuera del repo; LECTURA)\n' + '\n'.join(lineas))

    for c in congelados:
        run(['./mochic', 'validate', c], blocks)

    for jrel, srel, _irel in PARES:
        run(['./mochic', 'build', os.path.join(pack1, srel)], blocks,
            nota='(re-corrida de %s: el sha256 debe igualar el sha_nuevo de %s)'
                 % (srel, jrel))

    run(['python3', '-m', 'pytest', 'tests/', '-q'], blocks)
    run(['./mochic', 'profile', '--control', '--texto'], blocks)

    texto = '\n\n'.join(blocks) + '\n'
    with open(a.out, 'w', encoding='utf-8') as fh:
        fh.write(texto)
    print('crudo: %s (%d bytes, %d bloques)' % (a.out, len(texto.encode()), len(blocks)),
          file=sys.stderr)
    return 0


def _ap():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', default='evidence/our_build_v1/stdout.raw.txt')
    ap.add_argument('--fuerza', action='store_true',
                    help='pisar aunque el crudo este sellado por un manifest')
    return ap


if __name__ == '__main__':
    sys.exit(main())
