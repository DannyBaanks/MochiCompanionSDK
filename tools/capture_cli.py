"""Captura la superficie del CLI `mochic` sobre un volumen FALSO en /tmp.

Existe por una razon metodologica: GUIA.md exige que cada comando documentado
haya sido ejecutado de verdad. Este script los ejecuta todos en orden, guarda
stdout+stderr y el exit code de cada uno, y escribe el crudo que sella el pack
de evidencia. Nunca abre un dispositivo: el volumen es un arbol de copias en
/tmp, y el backup local solo se lee.

Uso:
  python3 tools/capture_cli.py [--out evidence/cli_v0/stdout.raw.txt]
"""
from __future__ import annotations

import argparse, json, os, re, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUP = os.path.expanduser('~/megamochi-backup/volume_files')
PACK = os.path.expanduser('~/Development/ISyCo Git/Companion/packs/malbolge-cat')
MOCHIC = os.path.join(ROOT, 'mochic')


def build_fake_volume(target: str) -> None:
    sys.path.insert(0, ROOT)
    from mochisdk import playlist
    shutil.rmtree(target, ignore_errors=True)
    os.makedirs(os.path.join(target, 'video'))
    shutil.copy2(os.path.join(BACKUP, 'playlist.lst'), target)
    for n in playlist.load(os.path.join(BACKUP, 'playlist.lst')):
        shutil.copy2(os.path.join(BACKUP, 'video', n), os.path.join(target, 'video', n))


def guard_out(out_path: str, force: bool = False) -> None:
    """Fail closed: nunca pisar un crudo que ya esta sellado por un manifest.

    Motivo real, medido el 2026-11-06: `capture_cli.py` se corro a las 10:59Z
    seis minutos despues de sellar `evidence/cli_v0` a las 10:53Z. El crudo de
    24 bloques fue reemplazado por uno de 26, el manifest quedo apuntando a
    bytes que ya no existian en disco y sin version de control no habia forma
    de recuperarlos. Un capturer que escribe dentro de un pack cerrado tiene
    que negarse, no avisar.
    """
    man = os.path.join(os.path.dirname(os.path.abspath(out_path)), 'manifest.json')
    if force or not (os.path.isfile(out_path) and os.path.isfile(man)):
        return
    import hashlib
    h = hashlib.sha256()
    with open(out_path, 'rb') as fh:
        for blk in iter(lambda: fh.read(1 << 20), b''):
            h.update(blk)
    pack = os.path.basename(os.path.dirname(os.path.abspath(out_path)))
    nxt = (re.sub(r'_v(\d+)$', lambda m: '_v%d' % (int(m.group(1)) + 1), pack)
           if re.search(r'_v\d+$', pack) else pack + '_v0')
    raise SystemExit(
        "REFUSAL: %s ya existe y esta sellado por %s (sha256 disco %s, manifest %s).\n"
        "Re-correar el capturer aqui pisaria evidencia cruda. Abre una version nueva:\n"
        "  python3 tools/%s --out evidence/%s/stdout.raw.txt\n"
        "y sella ese pack; el anterior queda SUPERSEDED, intacto.\n"
        "Si de verdad quieres reescribir dentro de %s (solo si vas a re-sellar con\n"
        "build --force y a documentarlo en CORRECCIONES.md): pasa --fuerza."
        % (out_path, man, h.hexdigest()[:16],
           (json.load(open(man))['stdout'].get('sha256') or '')[:16],
           os.path.basename(__file__), nxt, pack))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'evidence', 'cli_v0', 'stdout.raw.txt'))
    ap.add_argument('--vol', default='/tmp/mochi-fake-vol')
    ap.add_argument('--bridge', default='/tmp/mochi-bridge')
    ap.add_argument('--fuerza', action='store_true',
                    help='reescribir el crudo de un pack ya sellado (exige re-sellar)')
    a = ap.parse_args(argv)

    guard_out(a.out, a.fuerza)
    if not os.path.isdir(BACKUP):
        print('falta la copia local del volumen: %s' % BACKUP, file=sys.stderr)
        return 3
    build_fake_volume(a.vol)
    shutil.rmtree(a.bridge, ignore_errors=True)
    os.makedirs(a.bridge)
    shutil.rmtree(os.path.join(ROOT, 'build'), ignore_errors=True)
    inbox = os.path.join(a.bridge, 'inbox.jsonl')

    seq = [
        ['version'],
        ['profile', '--control'],
        ['inspect', os.path.join(BACKUP, 'video', 'Angry.avi')],
        ['validate', os.path.join(BACKUP, 'video', 'Angry.avi')],
        ['playlist', a.vol],
        ['map', '--mostrar'],
        ['spec', '--pack', PACK, '--animacion', 'thinking', '--slot', 'Squint.avi',
         '--fotogramas', '60', '--id', 'demo-thinking', '-o', 'examples/demo-thinking.json'],
        ['build', 'examples/demo-thinking.json'],
        ['validate', 'build/demo-thinking.avi'],
        ['plan', a.vol, 'examples/demo-thinking.json', '--salida', 'build/plan-demo.json'],
    ]
    blocks = []

    def run(cmd):
        r = subprocess.run([MOCHIC] + cmd, capture_output=True, text=True, cwd=ROOT)
        shown = ' '.join('"%s"' % x if ' ' in x else x for x in cmd)
        blocks.append('$ mochic %s\n[exit %d]\n%s%s' % (shown, r.returncode, r.stdout, r.stderr))
        return r.returncode

    for c in seq:
        run(c)
    token = json.load(open(os.path.join(ROOT, 'build', 'plan-demo.json')))['token']
    run(['apply', 'build/plan-demo.json', '--token', 'TOKEN-MALO'])
    rc = run(['apply', 'build/plan-demo.json', '--token', token, '--copia',
              os.path.join(a.bridge, 'backup'), '--diario', os.path.join(a.bridge, 'journal.json')])
    run(['rollback', os.path.join(a.bridge, 'journal.json')])
    # el plan ya quedo viejo despues del rollback: planear otra vez y no aplicar
    run(['plan', a.vol, 'examples/demo-thinking.json', '--salida', 'build/plan-2.json'])
    run(['plan', a.vol, '--par', 'build/no-existe.avi', 'video/Blink.avi'])

    for t, v in [('state', 'working'), ('state', 'thinking'), ('mood', 'error'),
                 ('move', 'top-right'), ('summon', None), ('say', None)]:
        c = ['emit', t, '--inbox', inbox, '--agente', 'agente-demo']
        if v:
            c += ['--valor', v]
        if t == 'say':
            c += ['--mensaje', 'termine']
        run(c)
    run(['watch', '--inbox', inbox, '--pack', PACK, '--volumen', a.vol,
         '--outbox', os.path.join(a.bridge, 'outbox.jsonl'),
         '--cursor-root', os.path.join(a.bridge, 'cursor'), '--fotogramas', '45'])
    run(['watch', '--inbox', inbox, '--pack', PACK, '--volumen', a.vol,
         '--cursor-root', os.path.join(a.bridge, 'cursor'), '--fotogramas', '45'])
    def interop(vol):
        """Control de interoperabilidad: el inbox lo escribe el VALIDADOR de Companion."""
        comp_src = os.path.expanduser('~/Development/ISyCo Git/Companion/src')
        if not os.path.isdir(comp_src):
            blocks.append('$ interop companion -> mochic\n[NO PROBADO] falta el repo Companion')
            return
        e2e = '/tmp/mochi-e2e'
        shutil.rmtree(e2e, ignore_errors=True)
        os.makedirs(e2e)
        env = dict(os.environ, COMPANION_ROOT=e2e, PYTHONPATH=comp_src)
        line = ('{"version":"companion-event-v1","id":"evt-real-%d","agent":"agente-real",'
                '"created_at":"2026-11-06T10:00:0%dZ","type":"%s","value":"%s"}\n')
        stdin = (line % (1, 4, 'state', 'success') + line % (2, 5, 'mood', 'error')
                 + '{"version":"companion-event-v1","id":"evt-real-3","agent":"agente-real",'
                   '"created_at":"2026-11-06T10:06:00Z","type":"state","value":"imposible"}\n')
        h = subprocess.run([sys.executable, '-c', 'from companion.cli import main; import sys;'
                                             'sys.exit(main())', 'hook'],
                           input=stdin, capture_output=True, text=True,
                           cwd=os.path.dirname(comp_src), env=env)
        blocks.append('$ printf "3 eventos" | COMPANION_ROOT=%s PYTHONPATH=%s '
                      'python3 -c "from companion.cli import main;..." hook\n[exit %d]\n%s%s'
                      % (e2e, comp_src, h.returncode, h.stdout, h.stderr))
        c = ['watch', '--inbox', os.path.join(e2e, 'inbox.jsonl'), '--pack', PACK,
             '--volumen', vol, '--build-dir', os.path.join(e2e, 'build'),
             '--cursor-root', os.path.join(e2e, 'cursor'), '--fotogramas', '30']
        run(c)

    interop(a.vol)

    pytest = subprocess.run([sys.executable, '-m', 'pytest', 'tests/', '-q'],
                            capture_output=True, text=True, cwd=ROOT)
    blocks.append('$ python3 -m pytest tests/ -q\n[exit %d]\n%s'
                  % (pytest.returncode, pytest.stdout[-500:]))

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, 'w') as fh:
        fh.write('\n'.join(blocks) + '\n')
    print('capturados %d bloques en %s' % (len(blocks), a.out))
    print('aplicacion del plan bueno: exit %d' % rc)
    return 0 if rc == 0 and pytest.returncode == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
