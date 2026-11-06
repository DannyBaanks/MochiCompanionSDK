"""playlist.lst del Mochi: 62 registros fijos de 128 bytes.

Medido sobre la copia local del volumen (evidence/profile_v0 no cubre este
archivo; la medicion esta en tests/test_playlist.py, que exige round-trip
byte-exacto sobre las 62 entradas reales):
  tameno total 7936 = 62 x 128, sin bytes de sobra al final.
  nombre ASCII en latin1, NUL-padded a 128; 62/62 no vacios; 1:1 con video/.
  largo maximo de nombre observado: 22.
Un registro vacio (todo ceros) existe en el formato por construccion, pero el
firmware nunca se ha visto con menos de 62 entradas: NO esta demostrado que
acepte otra cantidad, y por eso el plan de despliegue no reescribe el numero
de slots.
"""
from __future__ import annotations

import os

RECORD = 128
SLOTS = 62


class PlaylistError(ValueError):
    pass


def parse(data: bytes) -> list[str]:
    if len(data) % RECORD:
        raise PlaylistError("playlist.lst deberia medir un multiplo de %d B, mide %d"
                            % (RECORD, len(data)))
    out = []
    for i in range(len(data) // RECORD):
        rec = data[i * RECORD:(i + 1) * RECORD]
        out.append(rec.split(b'\x00')[0].decode('latin1'))
    return out


def render(names: list[str]) -> bytes:
    out = bytearray()
    for n in names:
        raw = n.encode('latin1')
        if len(raw) >= RECORD:
            raise PlaylistError("nombre demasiado largo para un registro de %d B: %r" % (RECORD, n))
        if '/' in n or '\\' in n:
            raise PlaylistError("el playlist guarda nombres sueltos, no rutas: %r" % n)
        out += raw + b'\x00' * (RECORD - len(raw))
    return bytes(out)


def load(path: str) -> list[str]:
    return parse(open(path, 'rb').read())


def diff(old: list[str], new: list[str]) -> dict:
    return {'anadidos': [n for n in new if n and n not in old],
            'quitados': [n for n in old if n and n not in new],
            'movidos': [i for i, (a, b) in enumerate(zip(old, new)) if a != b]}
