"""Diagnostico comparativo de AVI ajenos contra el perfil medido del Mochi.

Existe porque el 2026-11-06 Danny reemplazo `startup.avi` del volumen por un
archivo generado por otro modelo: el dispositivo sonoro el audio nuevo, pero
la pantalla se puso en blanco y luego volvio al Mochi normal. Para convertir
eso en informacion hace falta una tabla que compare, campo por campo, el
archivo ajeno contra el original de fabrica que si funciona.

No toca el dispositivo: recibe rutas locales. El exit code es 0 si todos los
archivos se poden parsear; 1 si alguno ni siquiera es un AVI legible.

Uso:
  python3 tools/diagnose_foreign.py A.avi [B.avi ...]
  python3 tools/diagnose_foreign.py --junit   # tabla compacta, para el crudo
"""
from __future__ import annotations

import io, os, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from PIL import Image

from mochisdk import load_avi, profile
from mochisdk.container import AviError


def jpeg_shape(payload: bytes) -> dict:
    """Marcos SOF, precision, dimensiones y submuestreo del JPEG baseline."""
    out = {'sof': None, 'precision': None, 'dims': None, 'sampling': None,
           'progressive': False}
    i = 0
    while i + 4 <= len(payload):
        if payload[i] != 0xFF:
            i += 1
            continue
        marker = payload[i + 1]
        if marker in (0xD8, 0xD9, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        seglen = int.from_bytes(payload[i + 2:i + 4], 'big')
        if marker == 0xC2:
            out['progressive'] = True
        if marker in (0xC0, 0xC1, 0xC2):
            precision = payload[i + 4]
            alto = int.from_bytes(payload[i + 5:i + 7], 'big')
            ancho = int.from_bytes(payload[i + 7:i + 9], 'big')
            ncomp = payload[i + 9]
            sampling = tuple(payload[i + 11 + 3 * k] for k in range(ncomp))
            out.update(sof='FF%02X' % marker, precision=precision, dims=(alto, ancho),
                       sampling=sampling)
        i += 2 + seglen
    return out


def frame_stats(payload: bytes, step: int = 53) -> dict:
    im = Image.open(io.BytesIO(payload)).convert('RGB')
    arr = np.asarray(im, dtype=float).reshape(-1, 3)
    sample = arr[::step]
    return {'w': im.width, 'h': im.height, 'mean': arr.mean(0).round(1).tolist(),
            'std': round(float(arr.std()), 1), 'brutto': int(sample.sum(1).max())}


def describe(path: str) -> dict:
    a = load_avi(path)
    vrecs, arecs = a.video, a.audio
    decl_mismatch = sum(1 for r in a.records if len(r.data) != r.size)
    pat = ''.join('v' if r.kind == 'video' else 'a' for r in a.records[:12])
    js = jpeg_shape(vrecs[0].data) if vrecs else {}
    fs = frame_stats(vrecs[len(vrecs) // 2].data) if vrecs else {}
    st = [s for s in a.strf if getattr(s, 'bitcount', None) is not None]
    pcm = [s for s in a.strf if type(s).__name__ == 'PCMFormat']
    vsh = next((s for s in a.streams if s.fcc_type == b'vids'), None)
    findings = profile.validate(a, open(path, 'rb').read())
    return {
        'ruta': path, 'bytes': a.total_size,
        'frames_video': len(vrecs), 'chunks_audio': len(arecs),
        'trailing_audio_0': bool(arecs and len(arecs[-1].data) == 0),
        'audio_declarados': dict(Counter(r.size for r in arecs).most_common(3)),
        'idx1_entries': len(a.idx1),
        'idx1_alineado': len(a.idx1) == len(a.records),
        'declaro_difiere_real': decl_mismatch,
        'patron_12': pat,
        'avih': {'w': a.avih.get('width'), 'h': a.avih.get('height'),
                 # el fps real vive en strh (rate/scale); avih de estos archivos no trae scale
                 'fps': round(vsh.rate / vsh.scale, 3) if vsh and vsh.scale else None,
                 'total_frames': vsh.length if vsh else a.avih.get('total_frames'),
                 'max_bytes_per_sec': a.avih.get('max_bytes_per_sec'),
                 'flags': a.avih.get('flags'),
                 'suggested_buf': a.avih.get('suggested_buf_size')},
        'strh_vids': {'sugg': vsh.suggested_buf if vsh else None,
                      'frame_max': max((r.size for r in vrecs), default=None),
                      'rate': vsh.rate if vsh else None, 'scale': vsh.scale if vsh else None,
                      'handler': vsh.fcc_handler if vsh else None},
        'strf_video': [{'compression': getattr(s, 'compression', None),
                        'bitcount': getattr(s, 'bitcount', None)} for s in st],
        'strf_audio': [{'format_tag': p.format_tag, 'channels': p.channels,
                        'hz': p.samples_per_sec, 'avg_Bps': p.avg_bytes_per_sec,
                        'block_align': p.block_align, 'bits': p.bits_per_sample} for p in pcm],
        'jpeg': js, 'frame_medio': fs,
        'duros': ['%s obs=%r exp=%r' % (f.rule, f.observed, f.expected)
                  for f in findings if f.severity == 'hard'],
        'suaves': ['%s obs=%r exp=%r' % (f.rule, f.observed, f.expected)
                   for f in findings if f.severity == 'soft'],
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    compact = '--junit' in argv
    paths = [p for p in argv if not p.startswith('-')]
    if not paths:
        print('uso: python3 tools/diagnose_foreign.py A.avi [B.avi ...]', file=sys.stderr)
        return 2
    ok = True
    for p in paths:
        try:
            d = describe(p)
        except (AviError, Exception) as exc:
            print('%s  NO PARSEABLE: %r' % (p, exc))
            ok = False
            continue
        if compact:
            print('| %-22s | %8d B | v%d/a%d | %sx%s fps %s | audio %s ch %s %sHz %sB/frame | jpeg %s prec %s sub %s | strh vids sugg %s / frame_max %s | duros %s |'
                  % (os.path.basename(p)[:22], d['bytes'], d['frames_video'], d['chunks_audio'],
                     d['avih']['w'], d['avih']['h'], d['avih']['fps'],
                     d['strf_audio'][0]['format_tag'] if d['strf_audio'] else '?',
                     d['strf_audio'][0]['channels'] if d['strf_audio'] else '?',
                     d['strf_audio'][0]['hz'] if d['strf_audio'] else '?',
                     list(d['audio_declarados'].keys())[0] if d['audio_declarados'] else '?',
                     d['jpeg'].get('sof'), d['jpeg'].get('precision'),
                     d['jpeg'].get('sampling'),
                     d['strh_vids']['sugg'], d['strh_vids']['frame_max'],
                     ','.join(x.split()[0] for x in d['duros']) or '0'))
            continue
        import json
        print(json.dumps(d, indent=1, ensure_ascii=False, default=str))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
