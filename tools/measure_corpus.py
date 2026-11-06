"""Mide el perfil real del corpus factory del DASAI Mega Mochi.

Corre sobre las copias locales de ~/megamochi-backup/volume_files/video (cero
lecturas del dispositivo) y emite profiles/mochi-factory-v1.json. Ese archivo
es la unica fuente de numeros para las reglas de mochisdk/profile.py: ninguna
regla del validator se escribe sin un valor medido aqui.

Uso:
  python3 tools/measure_corpus.py [--video DIR] [--out profiles/mochi-factory-v1.json]
"""
from __future__ import annotations

import argparse, glob, hashlib, json, os, struct, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mochisdk import container

DEFAULT_VIDEO = os.path.expanduser('~/megamochi-backup/volume_files/video')


def pct(vals, q):
    if not vals:
        return None
    s = sorted(vals)
    i = min(len(s) - 1, int(round(q / 100.0 * (len(s) - 1))))
    return s[i]


def stats(vals):
    if not vals:
        return {'n': 0}
    return {'n': len(vals), 'min': min(vals), 'max': max(vals),
            'mean': round(sum(vals) / len(vals), 3), 'median': pct(vals, 50),
            'p95': pct(vals, 95), 'p99': pct(vals, 99)}


def _be16(b, o):
    """Longitud de segmento JPEG: big-endian. Leerla en LE daba 4096 donde era 16."""
    return struct.unpack_from('>H', b, o)[0]


def jpeg_header(payload):
    """Caminata correcta de segmentos JPEG desde SOI hasta SOS.

    Buscar FF C0/FF C2 a mano da falsos positivos dentro de las tablas DHT y
    de los datos entropy-coded, y leer la longitud en little-endian desincroniza
    el recorrido (ambos errores medidos en esta muestra).
    """
    out = {'soi': payload[:2] == b'\xff\xd8', 'eoi': payload[-2:] == b'\xff\xd9',
           'sof': None, 'sof_dims': None, 'precision': None, 'n_components': None,
           'components': [], 'sos_off': None, 'segments': [], 'app0_jfif': False,
           'comment': None, 'n_dqt': 0, 'n_dht': 0, 'n_sos': 0}
    if not out['soi']:
        return out
    i = 2
    while i + 4 <= len(payload):
        if payload[i] != 0xFF:
            break
        m = payload[i + 1]
        if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
            i += 2
            continue
        if m == 0xDA:
            out['sos_off'] = i
            out['n_sos'] += 1
            break
        seglen = _be16(payload, i + 2)
        out['segments'].append('FF%02X:%d' % (m, seglen))
        if m == 0xE0:
            out['app0_jfif'] = payload[i + 4:i + 8] == b'JFIF'
        elif m == 0xFE:
            out['comment'] = payload[i + 4:i + 2 + seglen].split(b'\x00')[0].decode('latin1')
        elif m == 0xDB:
            out['n_dqt'] += 1
        elif m == 0xC4:
            out['n_dht'] += 1
        elif m in (0xC0, 0xC1, 0xC2, 0xC3):
            out['sof'] = m
            if i + 10 <= len(payload):
                out['precision'] = payload[i + 4]
                out['sof_dims'] = [_be16(payload, i + 7), _be16(payload, i + 5)]
                out['n_components'] = payload[i + 9]
                comps = []
                for c in range(out['n_components'] or 0):
                    o = i + 10 + 3 * c
                    if o + 3 > len(payload):
                        break
                    comps.append([payload[o], payload[o + 1] >> 4, payload[o + 1] & 15, payload[o + 2]])
                out['components'] = comps
        i += 2 + seglen
        if i > len(payload):
            break
    return out


def measure_one(path):
    buf = open(path, 'rb').read()
    a = container.parse_avi(buf, path=path)
    vid, aud = a.video, a.audio
    vframes = [r.size for r in vid]
    achunks = [r.size for r in aud]
    top = container.read_chunks(buf, 12, skip_form=False)
    movi = next((c for c in top if c.fcc == b'LIST' and c.data[:4] == b'movi'), None)
    list_fccs = Counter()
    for c in top:
        list_fccs[c.fcc.decode('latin1') + (':' + c.data[:4].decode('latin1') if c.fcc == b'LIST' else '')] += 1
    strh_sizes = [s.size for s in a.streams]
    junk_lens = [len(j) for j in a.junk]
    dur = a.duration_s
    idx1_matched = sum(1 for r in vid + aud if r.flags)
    interleave = ''.join('v' if r.kind == 'video' else ('a' if r.kind == 'audio' else '?') for r in a.records)[:12]
    tail_after_idx1 = len(buf) - (buf.rfind(b'idx1') + 8 + container._u32(buf, buf.rfind(b'idx1') + 4)) if b'idx1' in buf else None
    odd = [r.size for r in a.records if r.size & 1]
    sof = [jpeg_header(r.data) for r in vid]
    out = {
        'file': os.path.basename(path),
        'sha256': hashlib.sha256(buf).hexdigest(),
        'bytes': len(buf),
        'duration_s': round(dur, 6),
        'avih': {k: a.avih[k] for k in ('microsec_per_frame', 'max_bytes_per_sec', 'padding_granularity',
                                        'flags', 'total_frames', 'streams', 'suggested_buf_size', 'width', 'height')},
        'avih_declared_bps': a.avih['max_bytes_per_sec'],
        'actual_bps': round(len(buf) / dur, 1) if dur else None,
        'top_chunks': dict(list_fccs),
        'strh_sizes': strh_sizes,
        'streams': [{'type': s.fcc_type.decode('latin1'), 'handler': s.fcc_handler.decode('latin1') if s.fcc_type == b'vids' else '0x%04x' % int.from_bytes(s.fcc_handler[:2], 'little'),
                     'flags': s.flags, 'scale': s.scale, 'rate': s.rate, 'fps': s.fps,
                     'start': s.start, 'length': s.length, 'suggested_buf': s.suggested_buf,
                     'quality': s.quality, 'sample_size': s.sample_size, 'rect': list(s.rect)} for s in a.streams],
        'strf': [{'kind': 'BITMAPINFOHEADER' if isinstance(f, container.BitmapInfo) else ('WAVEFORMATEX' if isinstance(f, container.PCMFormat) else str(f)),
                  **({k: (v.decode('latin1') if isinstance(v, bytes) else v) for k, v in f.__dict__.items()}
                     if isinstance(f, (container.BitmapInfo, container.PCMFormat)) else {})} for f in a.strf],
        'junk_lens': junk_lens,
        'records': {'total': len(a.records), 'video': len(vid), 'audio': len(achunks),
                    'other': len(a.records) - len(vid) - len(achunks)},
        'interleave_head': interleave,
        'video_frame_bytes': stats(vframes),
        'audio_chunk_bytes': stats(achunks),
        'audio_chunk_hist': dict(Counter(achunks)),
        'audio_total': a.audio_bytes,
        'video_total': sum(vframes),
        'idx1': {'entries': len(a.idx1), 'ckids': dict(Counter(e[0].decode('latin1') for e in a.idx1)),
                 'flags_hist': dict(Counter(e[1] for e in a.idx1)),
                 'with_flags': idx1_matched, 'records': len(a.records)},
        'odd_size_chunks': len(odd),
        'pad_bytes_present': bool(odd),
        'jpeg_soi_all': all(h['soi'] for h in sof),
        'jpeg_eoi_all': all(h['eoi'] for h in sof),
        'jpeg_sof_all': all(h['sof'] for h in sof),
        'trailing_after_idx1': tail_after_idx1,
        'riff_size_matches': container._u32(buf, 4) == len(buf) - 8,
        'movi_size_declared': next((c.size for c in top if c.fcc == b'LIST' and c.data[:4] == b'movi'), None),
        'movi_size_actual': None,
    }
    out['suggested_buf_eq_max_frame'] = (a.streams[0].suggested_buf == max(vframes)) if vframes else None

    out['blueprint'] = [r for r in blueprint(buf) if not r[0].startswith('RIFF[AVI ]/LIST[movi]/')]
    out['blueprint_shape'] = blueprints_shape(blueprint(buf))
    hdrl_c = next((c for c in top if c.fcc == b'LIST' and c.data[:4] == b'hdrl'), None)
    vprp = [k for c in (hdrl_c.children() if hdrl_c else []) if c.fcc == b'LIST' and c.data[:4] == b'strl'
            for k in c.children() if k.fcc == b'vprp']
    out['vprp'] = [[len(v.data), v.data.hex()] for v in vprp]
    out['junk_tree'] = [[r[0], r[1]] for r in out['blueprint'] if r[0].endswith('/JUNK')]

    # un solo recorrido del movi: tamano real escrito y byte de relleno tras cada chunk impar
    padvals = []
    limit = min(movi.body + movi.size, len(buf)) if movi else 0
    pos = end = a.movi_offset
    while movi is not None and pos + 8 <= limit:
        size = container._u32(buf, pos + 4)
        if pos + 8 + size > limit:
            break
        if size & 1:
            padvals.append(buf[pos + 8 + size])
        pos += 8 + size + (size & 1)
        end = pos
    out['movi_size_actual'] = end - a.movi_offset if movi is not None else None
    out['pad_byte_values'] = dict(Counter(padvals))

    # --- detalles estructurales que el validator va a exigir ---
    info = next((c for c in top if c.fcc == b'LIST' and c.data[:4] == b'INFO'), None)
    out['info_chunks'] = [[c.fcc.decode('latin1'), c.size, c.data[:48].decode('latin1').strip('\x00').strip()]
                          for c in info.children()] if info else []
    sof = [jpeg_header(r.data) for r in vid]
    out['jpeg_sof_dims'] = sorted({tuple(h['sof_dims']) for h in sof if h['sof_dims']})
    out['jpeg_sof_codes'] = sorted({h['sof'] for h in sof if h['sof']})
    out['jpeg_precision'] = sorted({h['precision'] for h in sof if h['precision'] is not None})
    out['jpeg_components'] = sorted({json.dumps(h['components']) for h in sof})
    out['jpeg_header_segments'] = sorted({json.dumps(h['segments']) for h in sof})
    out['jpeg_nframes_without_sos'] = sum(1 for h in sof if h['sos_off'] is None)
    out['jpeg_app0_jfif_all'] = all(h['app0_jfif'] for h in sof)
    out['jpeg_encoder_comment'] = sorted({str(h['comment']) for h in sof})
    out['jpeg_dqt_hist'] = dict(Counter(h['n_dqt'] for h in sof))
    out['jpeg_dht_hist'] = dict(Counter(h['n_dht'] for h in sof))
    out['jpeg_sof_hist'] = dict(Counter(str(h['sof']) for h in sof))
    out['junk_sha256'] = [hashlib.sha256(j).hexdigest()[:16] for j in a.junk]
    out['junk_nonzero_offs'] = sorted({i for j in a.junk for i, b in enumerate(j) if b})[:40]
    out['movi_declared_minus_actual'] = (out['movi_size_declared'] - out['movi_size_actual']) \
        if out['movi_size_declared'] is not None else None
    out['audio_total_eq_3200_x_video'] = a.audio_bytes == 3200 * len(vid)
    out['audio_last_chunk_size'] = aud[-1].size if aud else None
    out['audio_zero_count'] = sum(1 for s in achunks if s == 0)
    out['video_flags_all_keyframe'] = all(r.keyframe for r in vid)
    out['strf_image_size_eq_rgb_raw'] = None
    if out['strf'] and isinstance(a.strf[0], container.BitmapInfo):
        f0 = a.strf[0]
        out['strf_image_size_eq_rgb_raw'] = f0.image_size in (0, f0.width * f0.height * 3)
    return out


def merge_hist(rows, key):
    """Suma los histogramas por archivo en uno solo sobre los 9650 frames."""
    g = Counter()
    for r in rows:
        for k, v in r[key].items():
            g[k] += v
    return dict(g)


def blueprint(buf):
    """Arbol RIFF completo como [(ruta, fcc, tamano, sha256-corto-del-payload)].

    Es lo que el writer tiene que reproducir: si los 62 archivos factory
    comparten el mismo arbol, una sola plantilla basta y el round-trip
    byte-exacto es un control positivo real.
    """
    rows = []
    seen = {}

    def walk(ch, path):
        if ch.fcc in (b'RIFF', b'LIST'):
            form = ch.data[:4].decode('latin1')
            p = '%s/%s[%s]' % (path, ch.fcc.decode('latin1'), form)
            rows.append([p, ch.size, None])
            for k in ch.children():
                walk(k, p)
        else:
            base = '%s/%s' % (path, ch.fcc.decode('latin1'))
            if base.startswith('RIFF[AVI ]/LIST[movi]'):
                rows.append([base, ch.size, None])   # los records varian con N frames
                return
            n = seen[base] = seen.get(base, 0) + 1
            rows.append(['%s#%d' % (base, n), ch.size, hashlib.sha256(ch.data).hexdigest()[:16]])

    top = container.read_chunks(buf, 12, skip_form=False)
    rows.append(['RIFF[AVI ]', container._u32(buf, 4), None])
    for c in top:
        walk(c, 'RIFF[AVI ]')
    return rows


def blueprints_shape(rows):
    """Secuencia de rutas del arbol, con el contenido del movi colapsado en un
    unico nodo: lo que debe ser identico entre archivos es la cabecera."""
    out = []
    for r in rows:
        p = r[0]
        if p.startswith('RIFF[AVI ]/LIST[movi]/') or p == 'RIFF[AVI ]/LIST[movi]':
            if out and out[-1] == 'RIFF[AVI ]/LIST[movi]/*':
                continue
            out.append('RIFF[AVI ]/LIST[movi]/*')
        else:
            out.append(p)
    return json.dumps(out)


def sizes_by_path(rows):
    """Para cada nodo del arbol, los tamanos observados en el corpus.

    Un nodo con un solo tamano es constante: el writer lo copia tal cual.
    Un nodo con varios depende del contenido (movi, idx1, tamano de archivo).
    """
    g = {}
    for r in rows:
        for path, size, _ in r['blueprint']:
            g.setdefault(path, set()).add(size)
    return {k: (sorted(v) if len(v) <= 6 else ['%d tamanos distintos (%d..%d)' % (len(v), min(v), max(v))])
            for k, v in g.items()}


def const_payloads(rows, constante):
    """Nodos cuyo payload es identico en los 62 archivos (constante=True) o no (False).

    Solo mira nodos que aparecen exactamente una vez por archivo: los records
    del movi aparecen N veces y por definicion son variables.
    """
    stats = {}
    for r in rows:
        cnt = Counter()
        for path, size, sha in r['blueprint']:
            if sha is None:
                continue
            cnt[path] += 1
            s = stats.setdefault(path, {'archivos': 0, 'max_por_archivo': 0, 'hashes': set()})
            s['hashes'].add(sha)
        for path, n in cnt.items():
            s = stats[path]
            s['archivos'] += 1
            s['max_por_archivo'] = max(s['max_por_archivo'], n)
    out = {}
    for path, s in stats.items():
        unica = s['archivos'] == len(rows) and s['max_por_archivo'] == 1
        fija = len(s['hashes']) == 1
        if unica and fija == bool(constante):
            out[path] = next(iter(s['hashes'])) if fija else '%d hashes distintos' % len(s['hashes'])
    return out


def header_chunks(path):
    """{ruta_del_blueprint: payload} de todo chunk fuera del movi."""
    buf = open(path, 'rb').read()
    out, seen = {}, {}

    def walk(ch, pfx):
        if ch.fcc in (b'RIFF', b'LIST'):
            p = '%s/%s[%s]' % (pfx, ch.fcc.decode('latin1'), ch.data[:4].decode('latin1'))
            for k in ch.children():
                walk(k, p)
            return
        base = '%s/%s' % (pfx, ch.fcc.decode('latin1'))
        if base.startswith('RIFF[AVI ]/LIST[movi]'):
            return
        n = seen[base] = seen.get(base, 0) + 1
        out['%s#%d' % (base, n)] = ch.data

    for c in container.read_chunks(buf, 12, skip_form=False):
        walk(c, 'RIFF[AVI ]')
    return out


def header_template(path, constantes):
    """Plantilla del writer: cada payload constante verificado contra su sha medido."""
    import base64
    chunks = header_chunks(path)
    blobs = {}
    for ruta, sha in constantes.items():
        data = chunks[ruta]
        if hashlib.sha256(data).hexdigest()[:16] != sha:
            raise AssertionError('payload de %s no coincide con el hash medido' % ruta)
        blobs[ruta] = base64.b64encode(data).decode()
    return {'plantilla': 'mochi-header-v1', 'referencia': os.path.basename(path),
            'referencia_sha256': hashlib.sha256(open(path, 'rb').read()).hexdigest(),
            'nota': 'payloads de chunk identicos en los 62 archivos factory; el writer los copia '
                    'tal cual y solo recalcula avih, strh e idx1',
            'rutas_constantes': constantes, 'blobs_base64': blobs}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--video', default=DEFAULT_VIDEO)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = args.out or os.path.join(root, 'profiles', 'mochi-factory-v1.json')

    files = sorted(glob.glob(os.path.join(args.video, '*.avi')))
    rows = [measure_one(f) for f in files]

    vstats = stats([r['video_frame_bytes']['max'] for r in rows])
    declared = stats([r['avih_declared_bps'] for r in rows])
    actual = stats([r['actual_bps'] for r in rows])
    durations = stats([r['duration_s'] for r in rows])
    frames = stats([r['avih']['total_frames'] for r in rows])
    sizes = stats([r['bytes'] for r in rows])

    def uniq(key):
        return sorted({json.dumps(r[key], sort_keys=True) if isinstance(r[key], (dict, list)) else str(r[key]) for r in rows})

    summary = {
        'n_archivos': len(rows),
        'bytes_corpus': sum(r['bytes'] for r in rows),
        'sha256_lista': hashlib.sha256('\n'.join(r['sha256'] for r in rows).encode()).hexdigest(),
        'fps': sorted({r['streams'][0]['fps'] for r in rows}),
        'dims': sorted({(r['avih']['width'], r['avih']['height']) for r in rows}),
        'handler_video': sorted({r['streams'][0]['handler'] for r in rows}),
        'fourcc_strf_video': sorted({r['strf'][0].get('compression') for r in rows}),
        'audio_format': sorted({json.dumps(r['strf'][1], sort_keys=True) for r in rows if len(r['strf']) > 1}),
        'strh_sizes': sorted({tuple(r['strh_sizes']) for r in rows}),
        'top_chunks': sorted({k for r in rows for k in r['top_chunks']}),
        'interleave_head': dict(Counter(r['interleave_head'] for r in rows)),
        'records_ratio_v_a': [[list(map(str, k)), v] for k, v in Counter((r['records']['video'], r['records']['audio']) for r in rows).items()],
        'audio_chunk_hist_total': dict(Counter(sz for r in rows for sz, c in r['audio_chunk_hist'].items() for _ in range(c))),
        'odd_size_chunks_files': sum(1 for r in rows if r['odd_size_chunks']),
        'pad_files': sum(1 for r in rows if r['pad_bytes_present']),
        'pad_byte_values': dict(Counter(v for r in rows for v in r['pad_byte_values'])),
        'idx1_full_match': sum(1 for r in rows if r['idx1']['with_flags'] == r['idx1']['records']),
        'idx1_ckids': sorted({k for r in rows for k in r['idx1']['ckids']}),
        'idx1_flags': sorted({k for r in rows for e in r['idx1']['flags_hist'] for k in [e]}),
        'jpeg_soi_all': sum(1 for r in rows if r['jpeg_soi_all']),
        'jpeg_eoi_all': sum(1 for r in rows if r['jpeg_eoi_all']),
        'jpeg_sof_all': sum(1 for r in rows if r['jpeg_sof_all']),
        'riff_size_matches': sum(1 for r in rows if r['riff_size_matches']),
        'movi_declared_eq_actual': sum(1 for r in rows if r['movi_size_declared'] == r['movi_size_actual']),
        'trailing_after_idx1': dict(Counter(r['trailing_after_idx1'] for r in rows)),
        'junk_lens': dict(Counter(str(tuple(r['junk_lens'])) for r in rows)),
        'blueprint_unicas': len({r['blueprint_shape'] for r in rows}),
        'blueprint': json.loads(sorted({r['blueprint_shape'] for r in rows})[0]) if rows else [],
        'tamano_por_ruta': sizes_by_path(rows),
        'payloads_constantes': const_payloads(rows, constante=True),
        'payloads_variables': const_payloads(rows, constante=False),
        'vprp_unicas': len({v[1] for r in rows for v in r['vprp']}),
        'vprp_hex': sorted({v[1] for r in rows for v in r['vprp']})[:2],
        'vprp_presencia': dict(Counter(len(r['vprp']) for r in rows)),
        'junk_tree': sorted({json.dumps(r['junk_tree']) for r in rows})[:2],
        'declared_max_bytes_per_sec': declared,
        'actual_bytes_per_sec': actual,
        'max_frame_bytes_across_corpus': vstats,
        'duration_s': durations,
        'total_frames': frames,
        'file_bytes': sizes,
        'suggested_buf_eq_max_frame': dict(Counter(r['suggested_buf_eq_max_frame'] for r in rows)),
        'info_variants': sorted({json.dumps(r['info_chunks']) for r in rows}),
        'junk_variants': sorted({json.dumps(r['junk_sha256']) for r in rows}),
        'junk_nonzero_offsets': sorted({str(o) for r in rows for o in r['junk_nonzero_offs']})[:24],
        'movi_declared_minus_actual': stats([r['movi_declared_minus_actual'] for r in rows]),
        'audio_total_eq_3200_x_video': dict(Counter(r['audio_total_eq_3200_x_video'] for r in rows)),
        'audio_last_chunk_size': dict(Counter(r['audio_last_chunk_size'] for r in rows)),
        'audio_zero_count': dict(Counter(r['audio_zero_count'] for r in rows)),
        'video_flags_all_keyframe': dict(Counter(r['video_flags_all_keyframe'] for r in rows)),
        'jpeg_sof_dims': sorted({tuple(d) for r in rows for d in r['jpeg_sof_dims']}),
        'jpeg_sof_codes': sorted({c for r in rows for c in r['jpeg_sof_codes']}),
        'jpeg_precision': sorted({p for r in rows for p in r['jpeg_precision']}),
        'jpeg_components_variants': sorted({c for r in rows for c in r['jpeg_components']}),
        'jpeg_header_segment_variants': sorted({c for r in rows for c in r['jpeg_header_segments']})[:6],
        'jpeg_nframes_without_sos': sum(r['jpeg_nframes_without_sos'] for r in rows),
        'jpeg_app0_jfif_all': dict(Counter(r['jpeg_app0_jfif_all'] for r in rows)),
        'jpeg_encoder_comment': sorted({c for r in rows for c in r['jpeg_encoder_comment']}),
        'jpeg_sof_hist': merge_hist(rows, 'jpeg_sof_hist'),
        'jpeg_dqt_hist': merge_hist(rows, 'jpeg_dqt_hist'),
        'jpeg_dht_hist': merge_hist(rows, 'jpeg_dht_hist'),
        'strf_image_size_eq_rgb_raw': dict(Counter(r['strf_image_size_eq_rgb_raw'] for r in rows)),
        'avih_streams': dict(Counter(r['avih']['streams'] for r in rows)),
        'avih_total_frames_eq_video': dict(Counter(r['avih']['total_frames'] == r['records']['video'] for r in rows)),
        'padding_granularity': sorted({r['avih']['padding_granularity'] for r in rows}),
        'avih_flags': dict(Counter(r['avih']['flags'] for r in rows)),
        'microsec_per_frame': sorted({r['avih']['microsec_per_frame'] for r in rows}),
    }
    # techo de bitrate observado: el mayor max_bytes_per_sec declarado y el mayor real
    ceiling = {
        'declarado_max': max(r['avih_declared_bps'] for r in rows),
        'declarado_min': min(r['avih_declared_bps'] for r in rows),
        'real_max': max(r['actual_bps'] for r in rows),
        'frame_max_absoluto': max(r['video_frame_bytes']['max'] for r in rows),
        'audio_bytes_por_frame': sorted({k for r in rows for k in r['audio_chunk_hist']}),
        'nota': 'El techo que importa para generar assets nuevos es el maximo de bytes por frame '
                'y el max_bytes_per_sec declarados por los archivos que el firmware ya reproduce.',
    }
    # plantilla de cabecera: los payloads constantes extraidos de un archivo de
    # referencia, verificados contra el histograma de los 62
    template = header_template(os.path.join(args.video, rows[0]['file']),
                               summary['payloads_constantes'])
    template_path = os.path.join(root, 'profiles', 'mochi-header-v1.json')
    with open(template_path, 'w') as fh:
        json.dump(template, fh, indent=1)

    # Sin marca de tiempo: el perfil tiene que ser byte-estable para que su
    # SHA-256 siga siendo verificable. El cuando vive en el manifest del pack.
    doc = {'perfil': 'mochi-factory-v1', 'fuente': args.video,
           'metodo': 'python3 tools/measure_corpus.py', 'herramienta': 'mochisdk/container.py (RIFF puro, sin ffmpeg)',
           'resumen': summary, 'techo_bitrate': ceiling, 'archivos': rows}
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)
    print(json.dumps(summary, indent=1, ensure_ascii=False, default=str))
    print('=== TECHO DE BITRATE ===')
    print(json.dumps(ceiling, indent=1, ensure_ascii=False))
    print('escrito:', out_path, os.path.getsize(out_path), 'bytes')
    print('sha256:', hashlib.sha256(open(out_path, 'rb').read()).hexdigest())


if __name__ == '__main__':
    main()
