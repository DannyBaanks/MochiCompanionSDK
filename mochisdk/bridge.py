"""Puente Companion -> Mochi: eventos del agente se vuelven specs y planes.

Dirección de datos (nunca al revés): el agente emite `companion-event-v1`, el
puente elige una animación del pack, la renderiza a AVI factory y arma un plan
de despliegue. **Ninguna función de este módulo escribe en el volumen del
Mochi**: el plan devuelve un token y `mochic apply` lo consume. Eso es
deliberado — el brief pide DENY por defecto para cualquier escritura, y un
evento de agente no es autorización.

Lo que SI está demostrado: el formato del evento (`Companion/src/companion/protocol.py`),
el camino del inbox (`$COMPANION_ROOT` o `./.companion`, archivo `inbox.jsonl`)
y que el AVI producido pasa `profile.validate`.

Lo que NO está demostrado y por eso va escrito en cada resultado:
  * qué dispara cada una de las 62 animaciones en el firmware (MOCHI-REA-03);
  * que reemplazar el slot X haga visible el cambio en el momento esperado;
  * que el firmware acepte un número de entradas distinto de 62.

La tabla ANIM_A_SLOT es política de nombramiento, no medida. Se puede editar
con un mapa JSON propio (`--mapa`) sin tocar el código.
"""
from __future__ import annotations

import json, os, time, uuid

from . import render, spec as specmod
from .container import AviError

BRIDGE_ID = 'mochi-bridge-v1'
DEFAULT_FRAMES = 60

# Espejo de Companion/src/companion/protocol.py:9-13. Se duplica a proposito:
# el SDK no importa el paquete companion, para que un cambio de version del
# otro repo no rompa este contrato en silencio.
EVENT_TYPES = {"say", "state", "mood", "move", "summon", "hide", "status"}
STATES = {"idle", "thinking", "working", "success", "error", "waiting", "hidden"}
POSITIONS = {"top-left", "top-right", "bottom-left", "bottom-right", "dock", "free"}

# animacion del pack -> archivo del playlist factory que pasa a contenerla
ANIM_A_SLOT = {
    'idle': 'Blink.avi',
    'thinking': 'Squint.avi',
    'working': 'Revs.avi',
    'success': 'Smile.avi',
    'error': 'Crying.avi',
    'waiting': 'Sleepy.avi',
    'running-right': 'Look Right.avi',
    'running-left': 'Look Left.avi',
    'drag': 'UpsideDown.avi',
}

NOT_DEMONSTRATED = [
    "el firmware reproduce el slot reemplazado ante el estimulo que se esperaba",
    "el numero de entradas de playlist.lst puede ser distinto de 62",
    "el firmware relee el volumen sin quitar el cable",
]


class BridgeError(AviError):
    pass


# ---------------------------------------------------------------- eventos

def validate_event(ev) -> dict:
    """Valida el wrapper companion-event-v1 (mismo contrato que Companion)."""
    if not isinstance(ev, dict):
        raise BridgeError("el evento debe ser un objeto JSON")
    if ev.get('version') != 'companion-event-v1':
        raise BridgeError("version debe ser companion-event-v1")
    for k in ('id', 'agent', 'type'):
        v = ev.get(k)
        if not isinstance(v, str) or not v.strip():
            raise BridgeError("%r debe ser una cadena no vacia" % k)
    if ev['type'] not in EVENT_TYPES:
        raise BridgeError("tipo de evento no soportado: %r" % ev['type'])
    created = ev.get('created_at')
    if not isinstance(created, str) or not created.strip():
        raise BridgeError("created_at debe ser ISO-8601")
    try:
        time.strptime(created.replace('Z', '+00:00'), '%Y-%m-%dT%H:%M:%S%z')
    except ValueError:
        raise BridgeError("created_at debe ser ISO-8601: %r" % created)
    if ev['type'] == 'say' and not (isinstance(ev.get('text'), str) and ev['text'].strip()):
        raise BridgeError("los eventos say exigen text no vacio")
    if ev['type'] in ('state', 'mood'):
        if ev.get('value') not in STATES:
            raise BridgeError("value debe estar en %s" % sorted(STATES))
    if ev['type'] == 'move':
        if ev.get('value') not in POSITIONS:
            raise BridgeError("value debe estar en %s" % sorted(POSITIONS))
    ttl = ev.get('ttl')
    if ttl is not None and (isinstance(ttl, bool) or not isinstance(ttl, (int, float)) or ttl < 0):
        raise BridgeError("ttl debe ser un numero >= 0")
    return ev


def new_event(event_type: str, *, agent: str = 'mochic', **fields) -> dict:
    # id aleatorio, no derivado del reloj: dos eventos en el mismo segundo
    # tienen que seguir siendo distinguibles en el inbox.
    ev = {'version': 'companion-event-v1',
          'id': 'mochi-%s-%s' % (event_type, uuid.uuid4().hex[:12]),
          'agent': agent,
          'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
          'type': event_type, **fields}
    return validate_event(ev)


def default_companion_root() -> str:
    return os.environ.get('COMPANION_ROOT') or os.path.join(os.getcwd(), '.companion')


def read_events(path: str, offset: int = 0) -> tuple[list[dict], int]:
    """Lee eventos nuevos desde `offset` (bytes) y devuelve (eventos, offset_final).

    El cursor por bytes permite reler el inbox varias veces sin duplicar
    trabajo aunque nadie trunque el archivo.
    """
    if not os.path.isfile(path):
        return [], offset
    out = []
    with open(path, 'rb') as fh:
        fh.seek(offset)
        for raw in fh:
            if not raw.strip():
                continue
            try:
                out.append(validate_event(json.loads(raw.decode('utf-8'))))
            except (ValueError, BridgeError) as exc:
                raise BridgeError("linea de inbox malformada: %s" % exc)
        new_off = fh.tell()
    return out, new_off


def append_jsonl(path: str, event: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or '.', exist_ok=True)
    with open(path, 'a', encoding='utf-8') as fh:
        fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + '\n')


# ------------------------------------------------------------------ mapeo

def load_map(path: str | None) -> dict:
    """Mapa anim->slot; sin archivo se usa ANIM_A_SLOT."""
    if not path:
        return dict(ANIM_A_SLOT)
    m = json.load(open(path))
    unknown = [k for k, v in m.items() if not isinstance(v, str)]
    if unknown:
        raise BridgeError("mapa con valores no de texto: %s" % unknown)
    return m


def anim_of(event: dict) -> str | None:
    """Que animacion del pack representa un evento; None si es un no-op."""
    t, v = event['type'], event.get('value')
    if t in ('state', 'mood'):
        return None if v == 'hidden' else v
    if t == 'summon':
        return 'idle'
    if t == 'hide':
        return None
    if t == 'move':
        return {'top-left': 'running-left', 'top-right': 'running-right',
                'bottom-left': 'running-left', 'bottom-right': 'running-right',
                'dock': 'drag', 'free': 'idle'}.get(v)
    return None


def spec_for_event(event: dict, *, pack: str, mapping: dict, n_frames: int = DEFAULT_FRAMES,
                   build_dir: str = 'build', fondo=(0, 0, 0)) -> dict | None:
    """Evento -> spec mochi-anim-v1 (o None si el evento no pide animacion)."""
    anim = anim_of(event)
    if anim is None:
        return None
    slot = mapping.get(anim)
    if slot is None:
        raise BridgeError("el mapa no define la animacion %r" % anim)
    return specmod.normalize({
        'spec': specmod.SPEC_ID,
        'id': 'bridge-%s' % event['id'],
        'nombre': '%s -> %s (evento %s de %s)' % (anim, slot, event['type'], event['agent']),
        'fuente': {'tipo': 'companion_pack', 'pack': pack, 'animacion': anim,
                   'fotogramas': n_frames, 'fondo': list(fondo)},
        'destino': {'nombre_video': slot,
                    'salida': os.path.join(build_dir, '%s.avi' % anim)},
        'puente': {'origen_evento': event['id'], 'agente': event['agent'],
                   'creado_utc': event['created_at']},
    })


# ---------------------------------------------------------------- proceso

def handle(event: dict, *, pack: str, mapping: dict, n_frames: int = DEFAULT_FRAMES,
           build_dir: str = 'build', volume: str | None = None, fondo=(0, 0, 0),
           write_audio: str | None = None) -> dict:
    """Evento -> render -> validacion -> (plan). No escribe en el volumen."""
    sp = spec_for_event(event, pack=pack, mapping=mapping, n_frames=n_frames,
                        build_dir=build_dir, fondo=fondo)
    if sp is None:
        return {'evento': event['id'], 'tipo': event['type'], 'accion': 'ignorada',
                'motivo': 'el evento no pide ninguna animacion'}
    if write_audio:
        sp['fuente']['audio'] = write_audio
    rep = render.render_spec(sp)
    res = {'evento': event['id'], 'tipo': event['type'], 'valor': event.get('value'),
           'animacion': sp['fuente']['animacion'], 'slot': sp['destino']['nombre_video'],
           'salida': rep.get('ruta'), 'sha256': rep.get('sha256'),
           'bytes': rep.get('bytes_avi'), 'frames': rep.get('frames'),
           'valido': rep['validacion']['valido'], 'hallazgos': rep['validacion'],
           'nota': 'El render y la validacion son locales; el volumen no se toco.'}
    if not res['valido']:
        res['plan'] = None
        res['error'] = 'el AVI generado tiene hallazgos duros; no se planea nada'
        return res
    if volume:
        from . import deploy
        p = deploy.plan(volume, [{'origen': sp['destino']['salida'],
                                  'destino': 'video/' + sp['destino']['nombre_video']}])
        res['plan_token'] = p['token']
        res['plan_volumen'] = p['volumen']
        res['no_demostrado'] = NOT_DEMONSTRATED
    return res


def cursor_path(root: str) -> str:
    return os.path.join(root, 'bridge-cursor.json')


def load_cursor(root: str, inbox: str) -> int:
    try:
        c = json.load(open(cursor_path(root)))
        if c.get('inbox') == os.path.abspath(inbox):
            return int(c.get('offset', 0))
    except (OSError, ValueError):
        pass
    return 0


def save_cursor(root: str, inbox: str, offset: int) -> None:
    os.makedirs(root, exist_ok=True)
    with open(cursor_path(root), 'w') as fh:
        json.dump({'inbox': os.path.abspath(inbox), 'offset': offset,
                   'sello_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}, fh, indent=1)


def process_inbox(inbox: str, *, pack: str, mapping: dict, build_dir: str = 'build',
                  volume: str | None = None, n_frames: int = DEFAULT_FRAMES,
                  outbox: str | None = None, cursor_root: str | None = None,
                  from_offset: int | None = None, track: bool = True) -> dict:
    """Consume todo lo no leido del inbox. Si `outbox` se da, escribe eventos status.

    `track=False` deja el cursor donde estaba: sirve para releer el historial
    sin consumir, que es lo que quiere un `--desde 0` explícito.
    """
    inbox = os.path.expanduser(inbox)
    cursor_root = cursor_root or os.path.join(os.getcwd(), '.mochisdk-bridge')
    start = load_cursor(cursor_root, inbox) if from_offset is None else from_offset
    events, end = read_events(inbox, start)
    resultados = [handle(ev, pack=pack, mapping=mapping, build_dir=build_dir,
                         n_frames=n_frames, volume=volume) for ev in events]
    for r in resultados:
        if outbox and r.get('salida'):
            append_jsonl(outbox, new_event('status', text='mochi %s -> %s (%s)'
                                           % (r['animacion'], r['slot'], r['sha256'][:12]),
                                           mochi=r))
    if track:
        save_cursor(cursor_root, inbox, end)
    return {'inbox': inbox, 'desde_bytes': start, 'hasta_bytes': end,
            'eventos': len(events), 'resultados': resultados,
            'escribio_volumen': False}
