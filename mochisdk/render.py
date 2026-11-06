"""Renderiza arte de Companion a un AVI que el Mochi ya sabe reproducir.

Las unicas restricciones duras vienen de la medida del corpus factory
(profiles/mochi-factory-v1.json):

  480x480, 30 fps exactos, JPEG baseline 8 bits submuestreo 4:2:0,
  3200 B de PCM 16-bit 48 kHz mono por frame, intercalado estricto.

Todo lo demas es decision de diseno y se puede cambiar: como se compone el
alfa, como se escala y que calidad JPEG se apunta. La calidad se busca por
biseccion para respetar el techo de bytes por frame que se pasa por argumento;
ese techo es una politica, no un limite demostrado del dispositivo (el maximo
observado en factory es 31893 B y el techo real NO se midio).
"""
from __future__ import annotations

import hashlib, io, json, os, wave

import numpy as np
from PIL import Image

from . import profile
from .container import AviError, parse_avi
from .writer import AUDIO_BYTES_PER_FRAME, AUDIO_SAMPLES_PER_FRAME, AUDIO_RATE, build_avi

WIDTH = HEIGHT = 480
FPS = 30
FRAME_MS = 1000 // FPS
MAX_FRAME_BYTES_POLICY = 31893        # el mayor frame que el firmware ya reproduce


def gif_frames(path: str, background=(0, 0, 0)) -> tuple[list[Image.Image], list[int]]:
    """Frames RGBA compuestos sobre `background` + duraciones por frame en ms."""
    im = Image.open(path)
    frames, durs = [], []
    bg = Image.new('RGB', im.size, background)
    for i in range(getattr(im, 'n_frames', 1)):
        im.seek(i)
        cur = im.convert('RGBA') if im.mode != 'RGBA' else im
        canvas = bg.convert('RGBA').copy()
        canvas.alpha_composite(cur)
        frames.append(canvas.convert('RGB'))
        durs.append(int(im.info.get('duration', FRAME_MS) or FRAME_MS))
    return frames, durs


def sheet_frames(sheet_path: str, cell_w: int, cell_h: int, columns: int,
                 count: int | None = None, background=(0, 0, 0)) -> list[Image.Image]:
    """Recorta una sprite-sheet (formato spriteSheet de los packs de Companion)."""
    im = Image.open(sheet_path).convert('RGBA')
    total = (im.width // cell_w) * (im.height // cell_h)
    n = count or total
    bg = Image.new('RGBA', (cell_w, cell_h), tuple(background) + (255,))
    out = []
    for i in range(n):
        col, row = i % columns, i // columns
        tile = im.crop((col * cell_w, row * cell_h, (col + 1) * cell_w, (row + 1) * cell_h))
        canvas = bg.copy()
        canvas.alpha_composite(tile)
        out.append(canvas.convert('RGB'))
    return out


def resample_to_30(frames: list[Image.Image], durs_ms: list[int], n_out: int,
                   loop: bool = True) -> list[Image.Image]:
    """Redistribuye una linea de tiempo arbitraria sobre n_out slots de 1/30 s.

    Se muestrea por tiempo absoluto, no por indice: un GIF con frames de 140 y
    280 ms no se convierte en una secuencia uniforme si se indexa a ciegas.
    """
    if not frames:
        raise AviError("sin frames de entrada")
    total = float(sum(durs_ms))
    if not total:
        total = float(FRAME_MS) * len(frames)
    if n_out <= len(frames) and not loop:
        idx = [round(i * (len(frames) - 1) / max(1, n_out - 1)) for i in range(n_out)]
        return [frames[i] for i in idx]
    out = []
    starts = np.cumsum([0] + [float(d) for d in durs_ms])   # bordes en milisegundos
    for i in range(n_out):
        t_ms = (i * FRAME_MS) % total if loop else min(i * FRAME_MS, total - 1)
        k = int(np.searchsorted(starts, t_ms, side='right') - 1)
        out.append(frames[max(0, min(len(frames) - 1, k))])
    return out


def _resample(v):
    """Acepta el nombre del spec ('lanczos') o la constante de PIL."""
    if isinstance(v, str):
        return getattr(Image.Resampling, v.upper())
    return v


def fit(img: Image.Image, size=(WIDTH, HEIGHT), resample=Image.LANCZOS,
        pad=(0, 0, 0)) -> Image.Image:
    """Contiene el dibujo en 480x480 conservando aspect y centrado sobre `pad`."""
    canvas = Image.new('RGB', size, pad)
    k = min(size[0] / img.width, size[1] / img.height)
    w, h = max(1, round(img.width * k)), max(1, round(img.height * k))
    small = img.resize((w, h), _resample(resample))
    canvas.paste(small, ((size[0] - w) // 2, (size[1] - h) // 2))
    return canvas


def encode_jpeg(img: Image.Image, max_bytes: int = MAX_FRAME_BYTES_POLICY,
                quality_max: int = 95) -> tuple[bytes, int]:
    """JPEG baseline 4:2:0 el mayor quality que quepa en max_bytes.

    El submuestreo se fija en 2 (4:2:0) porque es lo unico que aparece en los
    9650 frames del corpus; cambiarlo produciria un asset rechazado por
    profile.validate.
    """
    lo, hi, best, bestq = 1, quality_max, None, None
    while lo <= hi:
        mid = (lo + hi) // 2
        buf = io.BytesIO()
        img.save(buf, 'JPEG', quality=mid, subsampling=2, optimize=True, progressive=False)
        data = buf.getvalue()
        if len(data) <= max_bytes:
            best, bestq, lo = data, mid, mid + 1
        else:
            hi = mid - 1
    if best is None:
        buf = io.BytesIO()
        img.save(buf, 'JPEG', quality=1, subsampling=2, optimize=True, progressive=False)
        return buf.getvalue(), 1
    return best, bestq


def silence_pcm(n_frames: int) -> bytes:
    return b'\x00' * (AUDIO_BYTES_PER_FRAME * n_frames)


def load_pcm(wav_path: str, n_frames: int) -> bytes:
    """WAV PCM 16-bit mono 48 kHz recortado/alargado al quantum exacto del frame."""
    with wave.open(wav_path) as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2 or w.getframerate() != AUDIO_RATE:
            raise AviError("el audio debe ser PCM 16-bit mono 48000 Hz (medido en factory): %s"
                           % (w.getparams(),))
        data = w.readframes(w.getnframes())
    need = AUDIO_BYTES_PER_FRAME * n_frames
    if len(data) < need:
        raise AviError("el wav tiene %d B y hacen falta %d B" % (len(data), need))
    return data[:need]


def render_gif(path: str, n_frames: int = 60, *, out_path: str | None = None,
               background=(0, 0, 0), max_frame_bytes: int = MAX_FRAME_BYTES_POLICY,
               audio_wav: str | None = None, resample=Image.LANCZOS) -> dict:
    src, durs = gif_frames(path, background)
    return _mux(src, durs, n_frames, out_path=out_path, background=background,
                max_frame_bytes=max_frame_bytes, audio_wav=audio_wav, resample=resample,
                origen=path, animacion=os.path.basename(path))


def render_companion_pack(pack_dir: str, animation: str = 'idle', n_frames: int = 60,
                          *, out_path: str | None = None, background=(0, 0, 0),
                          max_frame_bytes: int = MAX_FRAME_BYTES_POLICY,
                          audio_wav: str | None = None, resample=Image.LANCZOS) -> dict:
    """Pack de Companion -> AVI factory. Devuelve el informe de render + validacion."""
    manifest = json.load(open(os.path.join(pack_dir, 'manifest.json')))
    src: list[Image.Image]
    durs: list[int]
    used = None
    anims = manifest.get('animations', {})
    if animation in anims and os.path.exists(os.path.join(pack_dir, anims[animation])):
        src, durs = gif_frames(os.path.join(pack_dir, anims[animation]), background)
        used = os.path.join(pack_dir, anims[animation])
    elif animation in anims and anims[animation].endswith('.gif') and os.path.exists(
            os.path.join(pack_dir, 'codex-pet', anims[animation])):
        p = os.path.join(pack_dir, 'codex-pet', anims[animation])
        src, durs = gif_frames(p, background)
        used = p
    else:
        sh = manifest['spriteSheet']
        src = sheet_frames(os.path.join(pack_dir, sh['path']), sh['cellWidth'], sh['cellHeight'],
                           sh['columns'], background=background)
        durs = [FRAME_MS] * len(src)
        used = os.path.join(pack_dir, sh['path'])

    return _mux(src, durs, n_frames, out_path=out_path, background=background,
                max_frame_bytes=max_frame_bytes, audio_wav=audio_wav, resample=resample,
                origen=used, animacion=animation)


def _mux(src, durs, n_frames, *, out_path, background, max_frame_bytes, audio_wav,
         resample, origen, animacion) -> dict:
    seq = resample_to_30(src, durs, n_frames)
    fitted = [fit(f, pad=background, resample=resample) for f in seq]
    payloads, qualities = [], []
    for img in fitted:
        data, q = encode_jpeg(img, max_frame_bytes)
        payloads.append(data)
        qualities.append(q)
    pcm = load_pcm(audio_wav, len(payloads)) if audio_wav else silence_pcm(len(payloads))
    avi = build_avi(payloads, pcm)
    findings = profile.validate(parse_avi(avi), avi)
    report = {
        'origen': origen,
        'animacion': animacion,
        'frames': len(payloads),
        'duracion_s': round(len(payloads) / FPS, 3),
        'jpeg_quality': {'min': min(qualities), 'max': max(qualities),
                         'mediana': sorted(qualities)[len(qualities) // 2]},
        'frame_bytes': {'min': min(map(len, payloads)), 'max': max(map(len, payloads)),
                        'total': sum(map(len, payloads))},
        'bytes_avi': len(avi),
        'budget_por_frame': max_frame_bytes,
        'validacion': profile.report(findings),
    }
    if out_path:
        with open(out_path, 'wb') as fh:
            fh.write(avi)
        report['ruta'] = out_path
        report['sha256'] = hashlib.sha256(avi).hexdigest()
    return report


def render_spec(spec: dict, out_path: str | None = None) -> dict:
    """Spec `mochi-anim-v1` -> AVI. El destino del spec manda donde se escribe."""
    from . import spec as specmod
    spec = specmod.normalize(spec) if 'spec' in spec else spec
    kw = specmod.to_render_kwargs(spec)
    dest = out_path or os.path.expanduser(spec['destino']['salida'])
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    f = spec['fuente']
    if f['tipo'] == 'gif':
        r = render_gif(os.path.expanduser(f['archivo']), out_path=dest, **kw)
    else:
        r = render_companion_pack(os.path.expanduser(f['pack']), out_path=dest, **kw)
    r['spec_id'] = spec['id']
    r['nombre_video_destino'] = spec['destino']['nombre_video']
    return r
