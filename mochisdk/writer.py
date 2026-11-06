"""Muxer RIFF-AVI del flavor del DASAI Mega Mochi.

No es un AVI generico: reproduce el blueprint medido en los 62 archivos factory
(profiles/mochi-factory-v1.json), que es lo unico que se sabe que el firmware
acepta. Su control positivo es byte-exacto: con los frames y el PCM de un
archivo factory, build_avi() devuelve exactamente los mismos bytes.

Reglas medidas (valor unico en 62/62 archivos, ver el profile):
  480x480 @ 30 fps, MJPEG baseline 8 bits 4:2:0, PCM 16-bit 48 kHz mono.
  intercalado estricto video,audio,video,audio...
  audio: 3200 B por frame de video + un chunk 01wb final de tamano 0.
  avih: microsec 33333, max_bytes_per_sec 121000 (placeholder constante, no es
        un techo: lo real llega a 745702 B/s), padding 0, flags 2320,
        suggested_buf_size 1048576.
  strh de 56 bytes: 48 B de campos + rcFrame como 4 x int16 (el estandar de 64
        usa LONGs; el muxer factory no).
  strh video: suggested_buf = tamano del frame JPEG mayor.
  strh audio: rate 48000, dwLength en muestras (1600 por frame), sample_size 2.
  JUNK: 4120 por strl, 260 en hdrl, 1016 en raiz; payloads constantes.
  vprp de 68 bytes constante. INFO/ISFT = "Lavf61.7.100" (ffmpeg 7.0).
  idx1 al final del archivo, sin bytes de sobra; offset 0 relativo a la
        etiqueta 'movi', por eso el primer registro figura en offset 4.
"""
from __future__ import annotations

import base64, json, os

from .container import AVIIF_KEYFRAME, AviError

AUDIO_BYTES_PER_FRAME = 3200          # 1600 muestras x 2 B = 1/30 s a 48 kHz
AUDIO_SAMPLES_PER_FRAME = 1600
MICROSEC_PER_FRAME = 33333
AVIH_MAX_BPS = 121000                 # placeholder: identico en los 62 archivos
AVIH_FLAGS = 2320
AVIH_SUGGESTED_BUF = 1048576
VIDEO_SCALE, VIDEO_RATE = 1, 30
AUDIO_RATE = 48000
DEFAULT_TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'profiles', 'mochi-header-v1.json')


def load_template(path: str | None = None) -> dict:
    with open(path or DEFAULT_TEMPLATE) as fh:
        t = json.load(fh)
    t['blobs'] = {k: base64.b64decode(v) for k, v in t['blobs_base64'].items()}
    return t


def _chunk(fcc: bytes, data: bytes) -> bytes:
    pad = b"\x00" if len(data) & 1 else b""
    return fcc + len(data).to_bytes(4, 'little') + data + pad


def _list(fcc4: bytes, body: bytes) -> bytes:
    return b"LIST" + (4 + len(body)).to_bytes(4, 'little') + fcc4 + body


def _avih(n_frames: int, width: int, height: int) -> bytes:
    vals = [MICROSEC_PER_FRAME, AVIH_MAX_BPS, 0, AVIH_FLAGS, n_frames, 0, 2, AVIH_SUGGESTED_BUF,
            width, height, 0, 0, 0, 0]
    return b"".join(int(v).to_bytes(4, 'little') for v in vals)


def _strh(fcc_type: bytes, handler: bytes, length: int, suggested_buf: int,
          rect, rate: int, sample_size: int) -> bytes:
    """strh de 56 bytes con rcFrame en int16. dwScale=1, dwStart=0, dwQuality=-1."""
    d = bytearray(56)
    d[0:4] = fcc_type
    d[4:8] = handler
    d[20:24] = int(VIDEO_SCALE).to_bytes(4, 'little')
    d[24:28] = int(rate).to_bytes(4, 'little')
    d[32:36] = int(length).to_bytes(4, 'little')
    d[36:40] = int(suggested_buf).to_bytes(4, 'little')
    d[40:44] = (-1).to_bytes(4, 'little', signed=True)
    d[44:48] = int(sample_size).to_bytes(4, 'little')
    for i, v in enumerate(rect):
        d[48 + 2 * i:50 + 2 * i] = (int(v) & 0xFFFF).to_bytes(2, 'little')
    return bytes(d)


def build_avi(jpeg_frames: list[bytes], pcm: bytes, *, width: int = 480, height: int = 480,
              template: dict | None = None) -> bytes:
    """Muxa frames MJPEG + PCM segun el blueprint factory. pcm=b'' solo si n=0 no aplica.

    Exige exactamente AUDIO_BYTES_PER_FRAME bytes de audio por frame: el corpus
    no tiene ni un solo archivo con otra relacion, y el firmware se alimenta de
    esa relacion para mantener audio y video en paso.
    """
    tpl = template or load_template()
    blobs = tpl['blobs']
    n = len(jpeg_frames)
    if n == 0:
        raise AviError("sin frames de video")
    if len(pcm) != AUDIO_BYTES_PER_FRAME * n:
        raise AviError("audio %d B no cuadra con %d frames x %d B/frame"
                       % (len(pcm), n, AUDIO_BYTES_PER_FRAME))

    strl_video = _list(b"strl",
                       _chunk(b"strh", _strh(b"vids", b"MJPG", n, max(len(f) for f in jpeg_frames),
                                             (0, 0, width, height), VIDEO_RATE, 0))
                       + _chunk(b"strf", blobs['RIFF[AVI ]/LIST[hdrl]/LIST[strl]/strf#1'])
                       + _chunk(b"JUNK", blobs['RIFF[AVI ]/LIST[hdrl]/LIST[strl]/JUNK#1'])
                       + _chunk(b"vprp", blobs['RIFF[AVI ]/LIST[hdrl]/LIST[strl]/vprp#1']))
    strl_audio = _list(b"strl",
                       _chunk(b"strh", _strh(b"auds", b"\x01\x00\x00\x00", n * AUDIO_SAMPLES_PER_FRAME,
                                             AUDIO_BYTES_PER_FRAME, (0, 0, 0, 0), AUDIO_RATE, 2))
                       + _chunk(b"strf", blobs['RIFF[AVI ]/LIST[hdrl]/LIST[strl]/strf#2'])
                       + _chunk(b"JUNK", blobs['RIFF[AVI ]/LIST[hdrl]/LIST[strl]/JUNK#2']))
    hdrl = _list(b"hdrl", _chunk(b"avih", _avih(n, width, height)) + strl_video + strl_audio
                 + _chunk(b"JUNK", blobs['RIFF[AVI ]/LIST[hdrl]/JUNK#1']))

    movi = b""
    idx = []
    for i, frame in enumerate(jpeg_frames):
        idx.append((b"00dc", AVIIF_KEYFRAME, len(movi) + 4, len(frame)))
        movi += _chunk(b"00dc", frame)
        chunk = pcm[i * AUDIO_BYTES_PER_FRAME:(i + 1) * AUDIO_BYTES_PER_FRAME]
        idx.append((b"01wb", AVIIF_KEYFRAME, len(movi) + 4, len(chunk)))
        movi += _chunk(b"01wb", chunk)
    idx.append((b"01wb", AVIIF_KEYFRAME, len(movi) + 4, 0))   # chunk de audio vacio final
    movi += _chunk(b"01wb", b"")
    movi_list = _list(b"movi", movi)

    idx1 = b"idx1" + (16 * len(idx)).to_bytes(4, 'little')
    for ckid, flags, off, size in idx:
        idx1 += ckid + flags.to_bytes(4, 'little') + off.to_bytes(4, 'little') + size.to_bytes(4, 'little')

    info = _list(b"INFO", _chunk(b"ISFT", blobs['RIFF[AVI ]/LIST[INFO]/ISFT#1']))
    body = hdrl + info + _chunk(b"JUNK", blobs['RIFF[AVI ]/JUNK#1']) + movi_list + idx1
    return b"RIFF" + (4 + len(body)).to_bytes(4, 'little') + b"AVI " + body
