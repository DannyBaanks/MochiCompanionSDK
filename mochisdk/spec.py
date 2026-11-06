"""Spec `mochi-anim-v1`: la descripcion declarativa de una animacion.

Un spec no es un guion de pixel: declara arte de origen, cuantos frames a 30
fps, y que nombre de archivo del volumen debe quedar reemplazado. Con eso el
CLI puede renderizar, validar y planear sin que nadie tenga que recordar los
numeros medidos (esos viven en profiles/mochi-factory-v1.json).

Formato aceptado: JSON o YAML con la clave `spec: mochi-anim-v1`.
"""
from __future__ import annotations

import json, os

from .container import AviError

SPEC_ID = 'mochi-anim-v1'
DEFAULTS = {
    'fotogramas': 60,
    'fondo': [0, 0, 0],
    'budget_bytes_por_frame': 31893,
    'audio': None,
    'resample': 'lanczos',
}
RESAMPLES = ('lanczos', 'nearest', 'bilinear', 'box', 'hamming')


def load(path: str) -> dict:
    raw = open(path).read()
    if path.endswith(('.yaml', '.yml')):
        import yaml
        doc = yaml.safe_load(raw)
    else:
        doc = json.loads(raw)
    return normalize(doc, origen=path)


def normalize(doc: dict, origen: str | None = None) -> dict:
    if not isinstance(doc, dict):
        raise AviError("%s: el spec debe ser un objeto" % (origen or 'spec'))
    if doc.get('spec') != SPEC_ID:
        raise AviError("%s: spec=%r, se espera %r" % (origen or 'spec', doc.get('spec'), SPEC_ID))
    for k in ('id', 'fuente', 'destino'):
        if k not in doc:
            raise AviError("%s: falta el campo obligatorio %r" % (origen or 'spec', k))
    f, d = doc['fuente'], doc['destino']
    if f.get('tipo') not in ('companion_pack', 'gif'):
        raise AviError("fuente.tipo=%r no soportado (companion_pack | gif)" % f.get('tipo'))
    if f.get('tipo') == 'companion_pack' and 'pack' not in f:
        raise AviError("fuente.pack es obligatorio para companion_pack")
    if f['tipo'] == 'gif' and 'archivo' not in f:
        raise AviError("fuente.archivo es obligatorio para gif")
    if 'nombre_video' not in d:
        raise AviError("destino.nombre_video es obligatorio: debe ser un nombre que ya exista "
                       "en playlist.lst; anadir entradas nuevas no esta demostrado")
    out = dict(doc)
    out['fuente'] = {**DEFAULTS, **f}
    out['destino'].setdefault('salida', 'build/%s.avi' % out['id'])
    if out['fuente']['resample'] not in RESAMPLES:
        raise AviError("fuente.resample=%r no soportado" % out['fuente']['resample'])
    n = int(out['fuente']['fotogramas'])
    if not (15 <= n <= 2000):
        raise AviError("fotogramas=%d fuera de 15..2000 (el corpus factory va de 15 a 501; "
                       "el tope alto es politica, no medida)" % n)
    out['fuente']['fotogramas'] = n
    return out


def to_render_kwargs(spec: dict) -> dict:
    """Traduce el spec a los argumentos de render.render_companion_pack / render_gif."""
    f = spec['fuente']
    return {
        'animation': f.get('animacion', 'idle'),
        'n_frames': f['fotogramas'],
        'background': tuple(f['fondo']),
        'max_frame_bytes': f['budget_bytes_por_frame'],
        'audio_wav': f.get('audio'),
        'resample': f['resample'],
    }


def ejemplo() -> dict:
    return {
        'spec': SPEC_ID,
        'id': 'malbolgato-thinking',
        'nombre': 'Malbolgato pensando, reemplaza la animacion Angry',
        'fuente': {'tipo': 'companion_pack',
                   'pack': '~/Development/ISyCo Git/Companion/packs/malbolge-cat',
                   'animacion': 'thinking', 'fotogramas': 90, 'fondo': [8, 6, 14],
                   'budget_bytes_por_frame': 24000, 'resample': 'lanczos', 'audio': None},
        'destino': {'nombre_video': 'Angry.avi'},
    }


if __name__ == '__main__':
    print(json.dumps(ejemplo(), indent=1))
