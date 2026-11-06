"""Validador de assets para el DASAI Mega Mochi.

Cada regla es un numero medido en profiles/mochi-factory-v1.json (ver
evidence/profile_v0). Nada aqui es una opinion de formato: si una regla no
puede citar un valor unico en 62/62 archivos factory, es soft y lo dice.

Severidades:
  hard  -> el archivo se rechaza. Cumplida en 62/62 assets que el firmware ya
           reproduce, y violarla cambia el contenedor que el decoder recibe.
  soft  -> advertencia. El corpus no da evidencia suficiente para rechazar.

Uso:
  from mochisdk.profile import validate, validate_path
  findings = validate_path('salida.avi')
"""
from __future__ import annotations

import json, os, re

from .container import (AVIIF_KEYFRAME, AviError, BitmapInfo, PCMFormat, load_avi, parse_avi,
                        read_chunks)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE_PATH = os.path.join(ROOT, 'profiles', 'mochi-factory-v1.json')

WIDTH = HEIGHT = 480
FPS_SCALE, FPS_RATE = 1, 30
MICROSEC = 33333
AUDIO_RATE, AUDIO_BITS, AUDIO_CH, AUDIO_BLOCK, AUDIO_AVG_BPS = 48000, 16, 1, 2, 96000
AUDIO_BYTES_PER_FRAME = 3200
AUDIO_SAMPLES_PER_FRAME = 1600
MAX_FRAME_BYTES_OBSERVED = 31893
MAX_REAL_BPS_OBSERVED = 745702.0
CANONICAL_TREE = ['RIFF[AVI ]', 'RIFF[AVI ]/LIST[hdrl]', 'RIFF[AVI ]/LIST[hdrl]/avih#1',
                  'RIFF[AVI ]/LIST[hdrl]/LIST[strl]', 'RIFF[AVI ]/LIST[hdrl]/LIST[strl]/strh#1',
                  'RIFF[AVI ]/LIST[hdrl]/LIST[strl]/strf#1',
                  'RIFF[AVI ]/LIST[hdrl]/LIST[strl]/JUNK#1',
                  'RIFF[AVI ]/LIST[hdrl]/LIST[strl]/vprp#1',
                  'RIFF[AVI ]/LIST[hdrl]/LIST[strl]', 'RIFF[AVI ]/LIST[hdrl]/LIST[strl]/strh#2',
                  'RIFF[AVI ]/LIST[hdrl]/LIST[strl]/strf#2',
                  'RIFF[AVI ]/LIST[hdrl]/LIST[strl]/JUNK#2', 'RIFF[AVI ]/LIST[hdrl]/JUNK#1',
                  'RIFF[AVI ]/LIST[INFO]', 'RIFF[AVI ]/LIST[INFO]/ISFT#1', 'RIFF[AVI ]/JUNK#1',
                  'RIFF[AVI ]/LIST[movi]', 'RIFF[AVI ]/idx1#1']


class Finding:
    def __init__(self, rule: str, severity: str, message: str, observed=None, expected=None):
        self.rule, self.severity, self.message = rule, severity, message
        self.observed, self.expected = observed, expected

    def __repr__(self):
        return '[%s] %s: %s (observado=%r esperado=%r)' % (
            self.severity.upper(), self.rule, self.message, self.observed, self.expected)

    def as_dict(self):
        return {'regla': self.rule, 'severidad': self.severity, 'mensaje': self.message,
                'observado': self.observed, 'esperado': self.expected}


def _tree(buf):
    """Ruta de cada chunk del arbol, con el mismo indice de hermanos que la medida."""
    out = ['RIFF[AVI ]']
    seen = {}

    def walk(ch, pfx):
        if ch.fcc in (b'RIFF', b'LIST'):
            p = '%s/%s[%s]' % (pfx, ch.fcc.decode('latin1'), ch.data[:4].decode('latin1'))
            out.append(p)
            if p == 'RIFF[AVI ]/LIST[movi]':
                return
            for k in ch.children():
                walk(k, p)
            return
        base = '%s/%s' % (pfx, ch.fcc.decode('latin1'))
        if base.startswith('RIFF[AVI ]/LIST[movi]'):
            return
        n = seen[base] = seen.get(base, 0) + 1
        out.append('%s#%d' % (base, n))

    for c in read_chunks(buf, 12, skip_form=False):
        walk(c, 'RIFF[AVI ]')
    return out


def jpeg_shape(payload):
    """(sof, precision, alto, ancho, submuestreo) caminando segmentos JPEG en big-endian."""
    if payload[:2] != b'\xff\xd8':
        return None
    i = 2
    while i + 4 <= len(payload) and payload[i] == 0xFF:
        m = payload[i + 1]
        if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
            i += 2
            continue
        if m == 0xDA:
            break
        seglen = int.from_bytes(payload[i + 2:i + 4], 'big')
        if m in (0xC0, 0xC1, 0xC2, 0xC3) and i + 11 <= len(payload):
            h = int.from_bytes(payload[i + 5:i + 7], 'big')
            w = int.from_bytes(payload[i + 7:i + 9], 'big')
            ncomp = payload[i + 9]
            sampling = tuple(payload[i + 11 + 3 * c] for c in range(ncomp))
            return (m, payload[i + 4], h, w, sampling)
        i += 2 + seglen
    return None


def validate(asset, buf: bytes | None = None) -> list[Finding]:
    """Lista de hallazgos. Vaciar la hard-list es el criterio de "aceptable para el Mochi"."""
    out: list[Finding] = []
    hard = lambda r, m, o=None, e=None: out.append(Finding(r, 'hard', m, o, e))
    soft = lambda r, m, o=None, e=None: out.append(Finding(r, 'soft', m, o, e))
    n = len(asset.video)
    if n == 0:
        hard('movi.tiene_video', 'ningun registro de video en movi')
        return out

    # -- arbol de cabecera: identidad estructural con los 62 factory --
    if buf is not None:
        t = _tree(buf)
        if t != CANONICAL_TREE:
            hard('header.arbol', 'el arbol RIFF difiere del blueprint factory', t, CANONICAL_TREE)

    # -- avih --
    av = asset.avih
    for k, e in (('microsec_per_frame', MICROSEC), ('streams', 2), ('width', WIDTH),
                 ('height', HEIGHT), ('total_frames', n)):
        if av[k] != e:
            hard('avih.' + k, 'avih.%s no coincide con la medida factory' % k, av[k], e)
    if av['padding_granularity'] != 0:
        soft('avih.padding_granularity', 'el corpus factory usa 0', av['padding_granularity'], 0)
    if av['max_bytes_per_sec'] != 121000:
        soft('avih.max_bytes_per_sec',
             'placeholder constante en factory; no es un limite del dispositivo',
             av['max_bytes_per_sec'], 121000)

    # -- streams --
    if len(asset.streams) != 2:
        hard('streams.numero', 'el factory tiene exactamente 2 streams', len(asset.streams), 2)
        return out
    v, a = asset.streams
    if (v.fcc_type, a.fcc_type) != (b'vids', b'auds'):
        hard('streams.orden', 'stream 0 debe ser vids y 1 auds', (v.fcc_type, a.fcc_type), (b'vids', b'auds'))
    for st, name in ((v, 'strh.video'), (a, 'strh.audio')):
        if st.size != 56:
            hard(name + '.longitud', 'strh debe medir 56 bytes (rcFrame en int16)', st.size, 56)
        if (st.scale, st.rate) != (FPS_SCALE, FPS_RATE) and st is v:
            hard(name + '.fps', 'el factory es 30 fps exacto como (scale=1, rate=30)',
                 (st.scale, st.rate), (FPS_SCALE, FPS_RATE))
        if st.quality != -1:
            soft(name + '.quality', 'dwQuality = -1 en 62/62 factory', st.quality, -1)
        if st.start != 0:
            soft(name + '.start', 'dwStart = 0 en 62/62 factory', st.start, 0)
    if v.fcc_handler != b'MJPG':
        hard('strf.video.compression', 'el handler de video debe ser MJPG', v.fcc_handler, b'MJPG')
    if v.length != n:
        hard('strh.video.length', 'dwLength debe ser el numero de frames de video', v.length, n)
    if v.suggested_buf != max(r.size for r in asset.video):
        hard('strh.video.suggested_buf', 'debe ser el tamano del frame JPEG mayor (63/63 factory)',
             v.suggested_buf, max(r.size for r in asset.video))
    if tuple(v.rect) != (0, 0, WIDTH, HEIGHT):
        hard('strh.video.rect', 'rcFrame debe ser 0,0,480,480', tuple(v.rect), (0, 0, WIDTH, HEIGHT))

    # -- strf --
    sfv, sfa = asset.strf[0], asset.strf[1]
    if isinstance(sfv, BitmapInfo):
        if (sfv.width, sfv.height) != (WIDTH, HEIGHT):
            hard('strf.video.dims', 'los factory son 480x480', (sfv.width, sfv.height), (WIDTH, HEIGHT))
        if sfv.compression not in (b'MJPG', b'DIB '):
            hard('strf.video.fourcc', 'compression del strf de video debe ser MJPG', sfv.compression, b'MJPG')
        if sfv.bitcount != 24:
            hard('strf.video.bitcount', '24 bpp en 62/62 factory', sfv.bitcount, 24)
        if sfv.size != 40:
            hard('strf.video.tamano', 'BITMAPINFOHEADER de 40 bytes', sfv.size, 40)
    else:
        hard('strf.video.tipo', 'el strf de video no es BITMAPINFOHEADER', type(sfv).__name__)
    if isinstance(sfa, PCMFormat):
        # Reglas DERIVADAS, no copiadas: medidas sobre los 63 archivos reales del
        # volumen (62 de video/*.avi + startup.avi), cada relacion calza 63/63.
        # El startup.avi de fabrica es STEREO, asi que "mono exacto" era una
        # constante de 62/63 disfrazada de invariante y rechazaba el activo de
        # arranque que el firmware si reproduce.
        fps_v = (v.rate / v.scale) if v.scale else 0.0
        quantum = round(sfa.avg_bytes_per_sec / fps_v) if fps_v else None
        esperado = (1, sfa.channels, AUDIO_RATE, sfa.channels * AUDIO_AVG_BPS,
                    sfa.channels * AUDIO_BLOCK, AUDIO_BITS)
        medido = (sfa.format_tag, sfa.channels, sfa.samples_per_sec, sfa.avg_bytes_per_sec,
                  sfa.block_align, sfa.bits_per_sample)
        if medido != esperado or sfa.channels not in (AUDIO_CH, 2):
            hard('strf.audio.pcm', 'WAVEFORMATEX: PCM 16-bit 48 kHz y block/avg coherentes con '
                                   'los canales, exacto en 63/63 factory', medido, esperado)
        if sfa.channels != AUDIO_CH:
            soft('strf.audio.canales', 'mono en 62/63 assets; el startup.avi de fabrica es '
                                       'stereo y es el unico caso observado', sfa.channels, AUDIO_CH)
    else:
        hard('strf.audio.tipo', 'el strf de audio no es WAVEFORMATEX', type(sfa).__name__)
        fps_v = (v.rate / v.scale) if v.scale else 0.0
        quantum = None
    muestras = round(sfa.samples_per_sec / fps_v) if isinstance(sfa, PCMFormat) and fps_v else None
    esperado_strh = ((sfa.samples_per_sec, sfa.block_align, quantum) if isinstance(sfa, PCMFormat)
                     else (AUDIO_RATE, AUDIO_BLOCK, AUDIO_BYTES_PER_FRAME))
    if (a.rate, a.sample_size, a.suggested_buf) != esperado_strh:
        hard('strh.audio.campos', 'auds: rate = strf.samples_per_sec, sample_size = block_align, '
                                  'suggested_buf = avg_Bps/fps (63/63 factory)',
             (a.rate, a.sample_size, a.suggested_buf), esperado_strh)
    if muestras is not None and a.length != n * muestras:
        hard('strh.audio.length', 'dwLength de audio en muestras = %.6g por frame' % muestras,
             a.length, n * muestras)
    if tuple(a.rect) != (0, 0, 0, 0):
        soft('strh.audio.rect', 'los factory dejan rcFrame en ceros para audio', tuple(a.rect), (0, 0, 0, 0))

    # -- intercalado y cuantizado de audio --
    if len(asset.records) != 2 * n + 1:
        hard('movi.interleave', 'el factory intercala 1 chunk de video y 1 de audio por frame, '
                                'mas un chunk de audio vacio al final', len(asset.records), 2 * n + 1)
    pattern = ''.join({'video': 'v', 'audio': 'a'}.get(r.kind, '?') for r in asset.records)
    esperado_pat = 'va' * n + 'a'
    if pattern != esperado_pat:
        hard('movi.patron', 'el patron de intercalado debe ser (video,audio)* + audio-vacio',
             pattern[:24], esperado_pat[:24])
    sizes = {r.size for r in asset.audio[:-1]} if len(asset.audio) > n else {r.size for r in asset.audio}
    if quantum is not None and sizes - {quantum}:
        hard('audio.quantum', 'todo chunk de audio (salvo el ultimo) mide avg_Bps/fps bytes en '
                              '9650/9650 frames del corpus: 3200 mono, 6400 stereo',
             sorted(sizes), [quantum])
    if asset.audio and asset.audio[-1].size != 0:
        hard('audio.chunk_final', 'el ultimo chunk de audio mide 0 bytes en 63/63 factory',
             asset.audio[-1].size, 0)

    # -- idx1 --
    if not asset.idx1:
        hard('idx1.presente', 'los 62 factory terminan con un idx1 completo')
    else:
        if len(asset.idx1) != len(asset.records):
            hard('idx1.entries', 'un entry idx1 por registro de movi', len(asset.idx1), len(asset.records))
        if any(e[1] != AVIIF_KEYFRAME for e in asset.idx1):
            hard('idx1.flags', 'todos los entries factory llevan flags 0x10',
                 sorted({e[1] for e in asset.idx1}), hex(AVIIF_KEYFRAME))
        if any(e[0] not in (b'00dc', b'01wb') for e in asset.idx1):
            hard('idx1.ckid', 'los factory solo usan 00dc y 01wb', sorted({e[0] for e in asset.idx1}),
                 [b'00dc', b'01wb'])
        matched = sum(1 for r in asset.records if r.flags)
        if matched != len(asset.records):
            hard('idx1.alineado', 'los offsets de idx1 no calzan con los registros de movi; '
                                  'el idx1 del archivo apunta a otro lado', matched, len(asset.records))
    if buf is not None and b'idx1' in buf:
        p = buf.rfind(b'idx1')
        sobra = len(buf) - (p + 8 + int.from_bytes(buf[p + 4:p + 8], 'little'))
        if sobra != 0:
            hard('idx1.eof', 'el idx1 termina exactamente en EOF en 62/62 factory', sobra, 0)

    # -- payload JPEG por frame --
    for i, r in enumerate(asset.video):
        if not r.keyframe:
            hard('jpeg.keyframe', 'frame %d sin flag AVIIF_KEYFRAME: MJPEG es todo-I' % i, r.flags, AVIIF_KEYFRAME)
            break
    bad = []
    for i, r in enumerate(asset.video):
        sh = jpeg_shape(r.data)
        if sh is None or sh[0] != 0xC0 or sh[1] != 8 or (sh[2], sh[3]) != (HEIGHT, WIDTH) \
                or sh[4] != (0x22, 0x11, 0x11):
            bad.append((i, sh))
            break
    if bad:
        hard('jpeg.forma', 'cada frame debe ser baseline 8-bit 4:2:0 480x480 (medido en 9650/9650)',
             bad[0], (20, 8, (480, 480), (0x22, 0x11, 0x11)))
    if not all(r.data[:2] == b'\xff\xd8' and r.data[-2:] == b'\xff\xd9' for r in asset.video):
        hard('jpeg.soi_eoi', 'SOI al inicio y EOI al final en cada frame factory')

    # -- limites observados: soft, porque el techo real no se midio --
    mx = max(r.size for r in asset.video)
    if mx > MAX_FRAME_BYTES_OBSERVED:
        soft('jpeg.frame_bytes', 'por encima del mayor frame que el firmware se ha visto reproducir; '
                                 'el techo real NO esta medido', mx, MAX_FRAME_BYTES_OBSERVED)
    dur = asset.duration_s
    bps = asset.total_size / dur if dur else 0
    if bps > MAX_REAL_BPS_OBSERVED:
        soft('bitrate.real', 'por encima del mayor bitrate observado en factory (techo real no medido)',
             round(bps, 1), MAX_REAL_BPS_OBSERVED)
    if not (0.5 <= dur <= 16.7):
        soft('duracion.rango', 'fuera del rango observado en el corpus factory', round(dur, 3), '0.5..16.7 s')
    return out


def validate_path(path: str) -> list[Finding]:
    buf = open(path, 'rb').read()
    return validate(parse_avi(buf, path=path), buf)


def report(findings: list[Finding]) -> dict:
    hard = [f for f in findings if f.severity == 'hard']
    return {'valido': not hard, 'duros': len(hard), 'suaves': len(findings) - len(hard),
            'hallazgos': [f.as_dict() for f in findings]}


def control_positivo(profile_path: str = PROFILE_PATH) -> dict:
    """Corre el validator sobre los 62 archivos que el firmware ya reproduce.

    Cero hallazgos duros es la unica aceptacion posible: si una regla rechaza un
    asset factory, la regla esta mal, no el asset.
    """
    d = json.load(open(profile_path))
    src = d['fuente']
    res = {}
    for row in d['archivos']:
        p = os.path.join(src, row['file'])
        f = validate_path(p)
        res[row['file']] = [x.as_dict() for x in f if x.severity == 'hard']
    return res
