"""Repara la auto-incoherencia de `strh.vids.suggested_buf` y escribe una COPIA.

Existe porque el 2026-11-06 Danny pidio pasar a `startup.avi` un AVI generado por
otro modelo. Ese archivo ya trae la geometria del activo de arranque (223
registros, audio estereo de 6400 B por fotograma, chunk final vacio, `vprp`), pero
declara `strh.vids.suggested_buf = 12132` cuando su fotograma JPEG mayor mide 7737.
El invariante `suggested_buf == mayor frame` se cumple 63/63 en los archivos reales
del volumen y `deploy.plan` lo exige, asi que el porton rechazaba el archivo.

La reparacion es un entero de 4 bytes en el strh de video. Nunca toca el origen y
nunca sirve como via de escape: si el archivo tiene CUALQUIER otro hallazgo duro,
refusa. Salida 0 con el JSON de la reparacion; 1 si refusó; 2 por mal uso.

Uso:
  python3 tools/fix_suggested_buf.py ENTRADA.avi SALIDA.avi
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mochisdk import load_avi, profile
from mochisdk.container import read_chunks

SUGGESTED_BUF_IN_STRH = 36   # offset del campo dentro del cuerpo del strh


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for blk in iter(lambda: fh.read(1 << 20), b''):
            h.update(blk)
    return h.hexdigest()


def strh_video_offset(buf: bytes) -> int:
    """Offset absoluto del primer strh dentro de hdrl/strl (el stream de video)."""
    for top in read_chunks(buf, 12):
        if top.fcc != b'LIST' or top.data[:4] != b'hdrl':
            continue
        for sl in top.children():
            if sl.fcc != b'LIST' or sl.data[:4] != b'strl':
                continue
            for ch in sl.children():
                if ch.fcc == b'strh':
                    if ch.data[0:4] != b'vids':
                        continue
                    return ch.body
    raise SystemExit('REFUSAL: no hay un strh de video bajo hdrl/strl')


def repair(src: str, dst: str) -> dict:
    if os.path.abspath(dst) == os.path.abspath(src):
        raise SystemExit('REFUSAL: la salida no puede ser el origen (%s)' % src)
    buf = bytearray(open(src, 'rb').read())
    original = bytes(buf)
    duras = [f for f in profile.validate(load_avi(src), bytes(buf)) if f.severity == 'hard']
    otras = [f.rule for f in duras if f.rule != 'strh.video.suggested_buf']
    if otras:
        raise SystemExit('REFUSAL: %s tiene otros hallazgos duros %s; esta herramienta solo '
                         'repara la auto-incoherencia de suggested_buf, no contenedores rotos'
                         % (src, otras))
    if not duras:
        raise SystemExit('nada que reparar: %s ya pasa el validador' % src)

    asset = load_avi(src)
    mayor = max(r.size for r in asset.video)
    off = strh_video_offset(bytes(buf)) + SUGGESTED_BUF_IN_STRH
    declarado = struct.unpack_from('<I', buf, off)[0]
    if declarado != duras[0].observed:
        raise SystemExit('REFUSAL: en el offset %d el valor es %d, no el %d del hallazgo'
                         % (off, declarado, duras[0].observed))
    struct.pack_into('<I', buf, off, mayor)
    with open(dst, 'wb') as fh:
        fh.write(bytes(buf))
        fh.flush()
        os.fsync(fh.fileno())

    restante = [f.rule for f in profile.validate(load_avi(dst), open(dst, 'rb').read())
                if f.severity == 'hard']
    if restante:
        os.remove(dst)
        raise SystemExit('REFUSAL: la copia sigue con hallazgos duros %s; se borro la copia'
                         % restante)
    tocados = sum(1 for i, b in enumerate(buf) if b != original[i])
    return {'offset': off, 'declarado': declarado, 'frame_max': mayor,
            'bytes_diferentes': tocados, 'bytes': os.path.getsize(dst),
            'sha_origen': sha256_file(src), 'sha_copia': sha256_file(dst),
            'duros_restantes': restante}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        info = repair(*argv)
    except SystemExit as exc:
        print(json.dumps({'refusal': str(exc)}, indent=1, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps({'origen': argv[0], 'copia': argv[1], **info}, indent=1, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
