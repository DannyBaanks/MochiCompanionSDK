"""`mochic` — la superficie de línea de comandos del SDK.

Contrato estable, pensado para que lo invoque un agente y decida por el código
de salida, no por el texto:

    0  OK
    1  hallazgo duro: el AVI no calza con el perfil factory (o el spec es inválido)
    2  error de uso (argumentos)
    3  entrada ilegible o inexistente
    4  puerta de autorización: falta el token del plan o no coincide
    5  operación rehusada porque NO está demostrada (salirse del volumen,
       destinos nuevos en playlist, escritura sin plan)

Todo comando imprime JSON en stdout, salvo `--texto`. Los planes se guardan con
`plan --salida ARCHIVO` y `apply` exige el token que ese plan devolvió.
`mochic` nunca escribe en el dispositivo sin `apply` explícito con token.
"""
from __future__ import annotations

import argparse, dataclasses, hashlib, json, os, sys

from . import __version__, bridge, deploy, playlist, profile, render, spec as specmod, writer
from .container import AviError, load_avi, parse_avi

EXIT_OK, EXIT_HARD, EXIT_USAGE, EXIT_INPUT, EXIT_GATE, EXIT_REFUSED = 0, 1, 2, 3, 4, 5

BACKUP_DEFAULT = os.path.join(os.getcwd(), '.mochisdk-backup')


class UsageError(Exception):
    pass


class InputError(Exception):
    pass


class HardError(Exception):
    pass


class GateError(Exception):
    pass


class RefuseError(Exception):
    pass


# Orden relevante: el primero que calza por isinstance decide el codigo.
CODES = [(UsageError, EXIT_USAGE), (GateError, EXIT_GATE), (RefuseError, EXIT_REFUSED),
         (HardError, EXIT_HARD), (InputError, EXIT_INPUT),
         (playlist.PlaylistError, EXIT_INPUT), (bridge.BridgeError, EXIT_HARD),
         (AviError, EXIT_HARD), (OSError, EXIT_INPUT), (ValueError, EXIT_HARD)]


def code_for(exc: BaseException) -> int:
    for cls, code in CODES:
        if isinstance(exc, cls):
            return code
    return EXIT_INPUT


def _texto(doc) -> str:
    if isinstance(doc, dict):
        return '\n'.join('%-24s %s' % (k, _texto(v)) for k, v in doc.items())
    if isinstance(doc, list):
        return '\n'.join('  - ' + _texto(v).replace('\n', ' ') for v in doc)
    return str(doc)


def _clean(x):
    """JSON-seguro: los fourcc y payloads binarios salen como texto o hex."""
    if isinstance(x, bytes):
        s = x.decode('latin1')
        return s if s.isascii() and (not s or s.isprintable()) else 'hex:' + x.hex()
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    return x


def _emit(doc, as_json: bool) -> None:
    doc = _clean(doc)
    if as_json:
        json.dump(doc, sys.stdout, indent=1, ensure_ascii=False, sort_keys=True)
        sys.stdout.write('\n')
    else:
        sys.stdout.write(_texto(doc) + '\n')


def _read(path: str) -> bytes:
    try:
        return open(path, 'rb').read()
    except OSError as exc:
        raise InputError("no se puede leer %s: %s" % (path, exc))


def _sha(path: str) -> str:
    return deploy.sha256_file(path)


def _playlist_path(volume: str) -> str:
    p = os.path.join(volume, 'playlist.lst')
    if not os.path.isfile(p):
        raise InputError("no hay playlist.lst en %s" % volume)
    return p


# ------------------------------------------------------------------ comandos

def cmd_version(a) -> int:
    _emit({'sdk': 'mochisdk', 'version': __version__, 'spec': specmod.SPEC_ID,
           'puente': bridge.BRIDGE_ID, 'perfil': profile.PROFILE_PATH,
           'perfil_sha256': _sha(profile.PROFILE_PATH) if os.path.isfile(profile.PROFILE_PATH) else None,
           'codigos_salida': {'0': 'OK', '1': 'hallazgo duro', '2': 'uso',
                              '3': 'entrada ilegible', '4': 'token no coincide',
                              '5': 'operacion no demostrada'}}, a.json)
    return EXIT_OK


def cmd_inspect(a) -> int:
    buf = _read(a.archivo)
    asset = parse_avi(buf, path=a.archivo)
    vids, auds = asset.video, asset.audio
    sizes = [len(r.data) for r in vids]
    _emit({'archivo': a.archivo, 'bytes': len(buf), 'sha256': hashlib.sha256(buf).hexdigest(),
           'avih': {k: v for k, v in asset.avih.items() if not k.startswith('reserved')},
           'streams': [dataclasses.asdict(s) for s in asset.streams],
           'strf': [dataclasses.asdict(f) if dataclasses.is_dataclass(f) else f for f in asset.strf],
           'registros': {'video': len(vids), 'audio': len(auds),
                         'otros': len(asset.records) - len(vids) - len(auds)},
           'duracion_s': round(asset.duration_s, 4),
           'audio_bytes': asset.audio_bytes,
           'audio_cuanto_ok': asset.audio_bytes == writer.AUDIO_BYTES_PER_FRAME * len(vids),
           'frame_bytes': {'min': min(sizes) if sizes else 0, 'max': max(sizes) if sizes else 0,
                           'total': sum(sizes)},
           'idx1_entries': len(asset.idx1),
           'jpeg_forma': profile.jpeg_shape(vids[0].data) if vids else None},
          a.json)
    return EXIT_OK


def cmd_profile(a) -> int:
    d = json.load(open(profile.PROFILE_PATH))
    r = d['resumen']
    res = {'perfil': d['perfil'], 'fuente': d['fuente'],
           'corpus_sha256': r.get('sha256_lista'),
           'metodo': d['metodo'], 'herramienta': d['herramienta'],
           'hechos': {k: r[k] for k in ('n_archivos', 'bytes_corpus', 'fps', 'dims', 'handler_video',
                                        'audio_format', 'interleave_head', 'audio_total_eq_3200_x_video',
                                        'blueprint_unicas', 'payloads_constantes',
                                        'max_frame_bytes_across_corpus', 'actual_bytes_per_sec',
                                        'duration_s', 'suggested_buf_eq_max_frame', 'jpeg_sof_dims',
                                        'jpeg_encoder_comment', 'idx1_full_match')
                      if k in r},
           'techo_bitrate': d['techo_bitrate']}
    code = EXIT_OK
    if a.control:
        cp = profile.control_positivo()
        rechazados = sorted(f for f, h in cp.items() if h)
        res['control_positivo'] = {'archivos': len(cp), 'rechazados': len(rechazados),
                                   'esperado': 0, 'lista_rechazados': rechazados,
                                   'veredicto': 'PASS' if not rechazados else 'FAIL',
                                   'motivo': 'un asset factory rechazado implica regla mala, no asset malo'}
        code = EXIT_OK if not rechazados else EXIT_HARD
    _emit(res, a.json)
    return code


def cmd_validate(a) -> int:
    out, duros = [], 0
    for p in a.archivos:
        f = profile.validate_path(p)
        r = profile.report(f)
        r.update({'archivo': p, 'sha256': _sha(p)})
        duros += r['duros']
        out.append(r)
    _emit({'archivos': len(out), 'invalidos': sum(1 for r in out if not r['valido']),
           'duros': duros, 'reportes': out}, a.json)
    return EXIT_HARD if duros else EXIT_OK


def cmd_spec(a) -> int:
    doc = specmod.ejemplo()
    for attr, key in (('pack', 'pack'), ('animacion', 'animacion'),
                      ('fotogramas', 'fotogramas'), ('budget', 'budget_bytes_por_frame')):
        v = getattr(a, attr)
        if v is not None:
            doc['fuente'][key] = v
    if a.slot:
        doc['destino'].pop('salida', None)
        doc['destino']['nombre_video'] = a.slot
    if a.id:
        doc['destino'].pop('salida', None)
        doc['id'] = a.id
    doc['nombre'] = '%s -> %s' % (doc['fuente']['animacion'], doc['destino']['nombre_video'])
    specmod.normalize(doc)
    if a.salida:
        os.makedirs(os.path.dirname(os.path.abspath(a.salida)), exist_ok=True)
        with open(a.salida, 'w') as fh:
            json.dump(doc, fh, indent=1, ensure_ascii=False)
        _emit({'escrito': os.path.abspath(a.salida), 'spec': doc['id']}, a.json)
    else:
        _emit(doc, True)
    return EXIT_OK


def cmd_build(a) -> int:
    sp = specmod.load(a.spec)
    rep = render.render_spec(sp, out_path=a.salida)
    rep['siguiente_paso'] = 'mochic plan VOLUMEN %s' % a.spec
    _emit(rep, a.json)
    return EXIT_HARD if not rep['validacion']['valido'] else EXIT_OK


def cmd_playlist(a) -> int:
    volume = os.path.abspath(os.path.expanduser(a.volumen))
    pl = _playlist_path(volume)
    names = playlist.load(pl)
    root = os.path.join(volume, 'video')
    rows = []
    for i, n in enumerate(names):
        p = os.path.join(root, n)
        rows.append({'i': i, 'nombre': n, 'existe': os.path.isfile(p),
                     'bytes': os.path.getsize(p) if os.path.isfile(p) else 0})
    huerfanos = sorted(f for f in os.listdir(root) if f.endswith('.avi') and f not in names) \
        if os.path.isdir(root) else []
    _emit({'playlist': pl, 'entradas': len(names), 'bytes': os.path.getsize(pl),
           'sha256': _sha(pl), 'slots': rows, 'avisos': [
               'agregar entradas nuevas no esta demostrado que el firmware lo acepte'],
           'archivos_fuera_de_playlist': huerfanos}, a.json)
    return EXIT_OK


def _items(a) -> list[tuple[str, str]]:
    """(origen_local, destino_dentro_del_volumen) a partir de specs y de --par."""
    items = []
    for s in a.specs or []:
        sp = specmod.load(s)
        items.append((os.path.expanduser(sp['destino']['salida']),
                      'video/' + sp['destino']['nombre_video']))
    for src, dst in a.par or []:
        items.append((os.path.expanduser(src), dst.lstrip('/')))
    if not items:
        raise UsageError("no hay nada que planear: pase un spec o --par ORIGEN DESTINO")
    return items


def cmd_plan(a) -> int:
    volume = os.path.abspath(os.path.expanduser(a.volumen))
    items = _items(a)
    for src, dst in items:
        if not os.path.isfile(os.path.join(volume, dst)):
            raise RefuseError("el destino %r no existe en el volumen: agregar entradas nuevas "
                              "al playlist NO esta demostrado" % dst)
        if not os.path.isfile(src):
            raise InputError("no existe el origen: %s (primero `mochic build`)" % src)
    p = deploy.plan(volume, [{'origen': s, 'destino': d} for s, d in items])
    destino_plan = a.salida or os.path.join('build', 'plan-%s.json' % p['token'])
    os.makedirs(os.path.dirname(os.path.abspath(destino_plan)), exist_ok=True)
    with open(destino_plan, 'w') as fh:
        json.dump(p, fh, indent=1, ensure_ascii=False)
    p['plan_archivo'] = os.path.abspath(destino_plan)
    p['comando_siguiente'] = 'mochic apply %s --token %s' % (p['plan_archivo'], p['token'])
    _emit(p, a.json)
    return EXIT_OK


def cmd_apply(a) -> int:
    if not os.path.isfile(a.plan):
        raise InputError("no existe el plan: %s" % a.plan)
    p = json.load(open(a.plan))
    if not a.token:
        raise GateError("apply exige --token con el token que devolvio `mochic plan`")
    if a.token != p.get('token'):
        raise GateError("el token no coincide con el plan; nada escrito")
    res = deploy.apply(p, a.token, backup_root=a.copia or BACKUP_DEFAULT, journal_path=a.diario)
    res['volumen'] = p['volumen']
    res['avisos'] = ['el firmware no ha sido observado todavia con estos archivos nuevos',
                    'rollback: mochic rollback %s' % res['journal']]
    _emit(res, a.json)
    return EXIT_OK


def cmd_rollback(a) -> int:
    if not os.path.isfile(a.diario):
        raise InputError("no existe el journal: %s" % a.diario)
    _emit(deploy.rollback(a.diario), a.json)
    return EXIT_OK


def cmd_watch(a) -> int:
    inbox = os.path.expanduser(a.inbox or os.path.join(bridge.default_companion_root(), 'inbox.jsonl'))
    if not os.path.isfile(inbox):
        raise InputError("no existe el inbox: %s" % inbox)
    res = bridge.process_inbox(inbox, pack=os.path.expanduser(a.pack), mapping=bridge.load_map(a.mapa),
                               build_dir=a.build_dir, volume=a.volumen, n_frames=a.fotogramas,
                               outbox=a.outbox, cursor_root=a.cursor_root,
                               from_offset=a.desde, track=a.desde is None)
    res['no_demostrado'] = bridge.NOT_DEMONSTRATED
    _emit(res, a.json)
    return EXIT_HARD if any(r.get('valido') is False for r in res['resultados']) else EXIT_OK


def cmd_emit(a) -> int:
    """Crear un companion-event-v1 en un inbox (probar el puente sin Companion)."""
    fields = {}
    if a.valor:
        fields['value'] = a.valor
    if a.mensaje:
        fields['text'] = a.mensaje
    ev = bridge.new_event(a.tipo, agent=a.agente, **fields)
    bridge.append_jsonl(a.inbox, ev)
    _emit({'inbox': os.path.abspath(a.inbox), 'evento': ev,
           'siguiente_paso': 'mochic watch --pack PACK'}, a.json)
    return EXIT_OK


def cmd_map(a) -> int:
    if a.mostrar:
        _emit(bridge.ANIM_A_SLOT, a.json)
        return EXIT_OK
    os.makedirs(os.path.dirname(os.path.abspath(a.salida)) or '.', exist_ok=True)
    with open(a.salida, 'w') as fh:
        json.dump(bridge.load_map(a.desde), fh, indent=1, ensure_ascii=False, sort_keys=True)
    _emit({'escrito': os.path.abspath(a.salida), 'entradas': len(bridge.load_map(a.desde))}, a.json)
    return EXIT_OK


# ------------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    # Parser "padre" solo con los flags globales: permite escribirlos antes o
    # despues del subcomando (mochic --texto build x / mochic build x --texto).
    base = argparse.ArgumentParser(add_help=False)
    base.add_argument('--json', dest='json', action='store_true', default=True,
                      help='salida JSON en stdout (por defecto)')
    base.add_argument('--texto', dest='json', action='store_false', help='salida legible en texto')

    pr = argparse.ArgumentParser(prog='mochic', parents=[base],
                                 description='SDK Mochi<->Companion: genera y valida assets del '
                                             'DASAI Mega Mochi. Codigo de salida: 0 OK, 1 hallazgo '
                                             'duro, 2 uso, 3 entrada ilegible, 4 token, 5 no demostrado.')
    sub = pr.add_subparsers(dest='cmd', required=True)

    def add(name, **kw):
        return sub.add_parser(name, parents=[base], **kw)

    p = add('version', help='version del SDK y del perfil medido')
    p.set_defaults(fn=cmd_version)

    p = add('inspect', help='hechos de contenedor de un AVI (solo lectura)')
    p.add_argument('archivo')
    p.set_defaults(fn=cmd_inspect)

    p = add('profile', help='resumen del perfil factory medido')
    p.add_argument('--control', action='store_true',
                   help='correr el control positivo sobre los 62 archivos factory')
    p.set_defaults(fn=cmd_profile)

    p = add('validate', help='hallazgos duros/suaves contra el perfil factory')
    p.add_argument('archivos', nargs='+')
    p.set_defaults(fn=cmd_validate)

    p = add('spec', help='imprimir/generar un spec mochi-anim-v1')
    p.add_argument('--id'); p.add_argument('--pack'); p.add_argument('--animacion')
    p.add_argument('--slot'); p.add_argument('--fotogramas', type=int)
    p.add_argument('--budget', type=int)
    p.add_argument('-o', '--salida')
    p.set_defaults(fn=cmd_spec)

    p = add('build', help='spec -> AVI factory (escribe solo en build/)')
    p.add_argument('spec')
    p.add_argument('-o', '--salida', help='ruta de salida (por defecto la del spec)')
    p.set_defaults(fn=cmd_build)

    p = add('playlist', help='leer playlist.lst y casarlo con video/ (solo lectura)')
    p.add_argument('volumen')
    p.set_defaults(fn=cmd_playlist)

    p = add('plan', help='plan de reemplazo: lectura pura, devuelve token')
    p.add_argument('volumen')
    p.add_argument('specs', nargs='*', help='archivos spec mochi-anim-v1 (JSON o YAML)')
    p.add_argument('--par', action='append', nargs=2, metavar=('ORIGEN', 'DESTINO'),
                   help='repetible: AVI ya generado y destino relativo dentro del volumen')
    p.add_argument('--salida', help='donde guardar el plan JSON')
    p.set_defaults(fn=cmd_plan)

    p = add('apply', help='escribir un plan: exige el token que devolvio plan')
    p.add_argument('plan')
    p.add_argument('--token')
    p.add_argument('--copia', help='directorio de backups, fuera del volumen')
    p.add_argument('--diario', help='ruta del journal de rollback')
    p.set_defaults(fn=cmd_apply)

    p = add('rollback', help='restaurar desde un journal de apply')
    p.add_argument('diario')
    p.set_defaults(fn=cmd_rollback)

    p = add('watch', help='inbox companion-event-v1 -> render -> plan (nunca escribe el volumen)')
    p.add_argument('--inbox', help='por defecto $COMPANION_ROOT/inbox.jsonl o ./.companion/inbox.jsonl')
    p.add_argument('--pack', required=True, help='directorio del pack de Companion')
    p.add_argument('--mapa', help='JSON anim->slot; por defecto la tabla del SDK')
    p.add_argument('--volumen', help='si se da, agrega el token del plan por evento')
    p.add_argument('--build-dir', default='build')
    p.add_argument('--fotogramas', type=int, default=bridge.DEFAULT_FRAMES)
    p.add_argument('--outbox', help='escribir eventos status aqui (local, nunca al dispositivo)')
    p.add_argument('--cursor-root', help='directorio del cursor de consumo')
    p.add_argument('--desde', type=int,
                   help='leer desde este offset en bytes y no avanzar el cursor')
    p.set_defaults(fn=cmd_watch)

    p = add('emit', help='crear un companion-event-v1 en un inbox (pruebas locales)')
    p.add_argument('tipo', choices=sorted(bridge.EVENT_TYPES))
    p.add_argument('--valor', help='value para state/mood/move')
    p.add_argument('--mensaje', help='text para eventos say')
    p.add_argument('--agente', default='mochic')
    p.add_argument('--inbox', required=True)
    p.set_defaults(fn=cmd_emit)

    p = add('map', help='mostrar o exportar la tabla anim->slot del puente')
    p.add_argument('--mostrar', action='store_true')
    p.add_argument('--desde', help='partir de un mapa existente')
    p.add_argument('-o', '--salida', default='build/mapa-anim-slot.json')
    p.set_defaults(fn=cmd_map)
    return pr


def main(argv=None) -> int:
    pr = build_parser()
    try:
        args = pr.parse_args(argv)
        return args.fn(args)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else EXIT_USAGE
    except Exception as exc:
        if isinstance(exc, (UsageError, GateError, RefuseError, InputError)):
            code = code_for(exc)
        elif isinstance(exc, (HardError, bridge.BridgeError, AviError, ValueError)):
            code = EXIT_HARD
        else:
            code = code_for(exc)
        sys.stderr.write(json.dumps({'error': type(exc).__name__, 'mensaje': str(exc),
                                     'codigo_salida': code}, ensure_ascii=False) + '\n')
        return code


if __name__ == '__main__':
    sys.exit(main())
