"""Controles del validator: positivo con el corpus real, negativo con mutantes.

Regla de metodo: un validator que no rechaza mutantes no esta midiendo nada, y
uno que rechaza un archivo factory esta mal. Aqui se comprueba lo segundo con
los 62 originales y lo primero con 10 mutantes de byte concreto.
"""
import glob
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mochisdk import container, profile, writer

FILES = sorted(glob.glob(os.path.expanduser('~/megamochi-backup/volume_files/video/*.avi')))
pytestmark = pytest.mark.skipif(len(FILES) < 62, reason="falta el backup del corpus factory")


def hard_rules(findings):
    return {f.rule for f in findings if f.severity == 'hard'}


@pytest.fixture(scope='module')
def base():
    path = FILES[0]
    buf = open(path, 'rb').read()
    asset = container.parse_avi(buf, path=path)
    return path, buf, asset


# --------------------------------------------------------------- control positivo
@pytest.mark.parametrize('path', FILES[:20], ids=lambda p: os.path.basename(p))
def test_factory_no_produce_hallazgos_duros(path):
    assert hard_rules(profile.validate_path(path)) == set(), \
        'un asset que el firmware ya reproduce no puede ser rechazado'


def test_mutante_por_debajo_del_techo_no_medido_es_soft(base):
    """Cambiar max_bytes_per_sec solo produce soft: ese campo es placeholder y
    el techo real del dispositivo NO esta medido, asi que no podemos rechazar."""
    _, buf, asset = base
    patched = bytearray(buf)
    off = buf.index(b'avih') + 8 + 4
    patched[off:off + 4] = (50_000_000).to_bytes(4, 'little')
    f = profile.validate(container.parse_avi(bytes(patched)), bytes(patched))
    assert 'avih.max_bytes_per_sec' not in hard_rules(f)
    assert 'avih.max_bytes_per_sec' in {x.rule for x in f if x.severity == 'soft'}


def test_asset_generado_por_el_sdk_pasa(base):
    _, _, asset = base
    generado = writer.build_avi([r.data for r in asset.video], asset.pcm())
    assert hard_rules(profile.validate(container.parse_avi(generado), generado)) == set()


# --------------------------------------------------------------------- mutantes
def _patch(buf, needle, new, occurrence=0):
    out = bytearray(buf)
    i = -1
    for _ in range(occurrence + 1):
        i = buf.index(needle, i + 1)
    out[i:i + len(needle)] = new + b'\x00' * (len(needle) - len(new))
    return bytes(out)


def test_mutante_handler_video(base):
    _, buf, _ = base
    m = _patch(buf, b'MJPG', b'DIB ')
    assert 'strf.video.compression' in hard_rules(profile.validate(container.parse_avi(m), m))


def test_mutante_quantum_audio(base):
    """Un chunk de audio de 3000 B rompe el paso 1:1 medido en 9650/9650 chunks.

    Se parchea por header_off del registro, no buscando b'01wb': el fourcc
    tambien aparece dentro del JUNK de la cabecera (medido: primer match en
    0x11b4, el chunk real esta en 0x3d96).
    """
    _, buf, asset = base
    off = asset.audio[0].header_off + 4
    m = bytearray(buf)
    m[off:off + 4] = (3000).to_bytes(4, 'little')
    m = bytes(m)
    f = profile.validate(container.parse_avi(m), m)
    assert 'audio.quantum' in hard_rules(f) or 'movi.patron' in hard_rules(f), f
    assert hard_rules(f), 'el mutante debe rechazarse'


def test_mutante_intercalado_invertido(base):
    """Poner el chunk de audio antes que el de video del mismo par rompe el paso."""
    _, buf, asset = base
    v, a = asset.video[0], asset.audio[0]
    tam_v = 8 + v.size + (v.size & 1)
    tam_a = 8 + a.size + (a.size & 1)
    assert a.header_off == v.header_off + tam_v, 'supuesto del mutante: pares contiguos'
    m = (buf[:v.header_off] + buf[a.header_off:a.header_off + tam_a]
         + buf[v.header_off:v.header_off + tam_v] + buf[a.header_off + tam_a:])
    assert 'movi.patron' in hard_rules(profile.validate(container.parse_avi(m), m))


def test_mutante_idx1_truncado(base):
    _, buf, _ = base
    i = buf.rindex(b'idx1')
    n = int.from_bytes(buf[i + 4:i + 8], 'little')
    m = buf[:i + 8] + buf[i + 8:i + 8 + n - 16]      # un entry menos
    m = m[:i + 4] + (n - 16).to_bytes(4, 'little') + m[i + 8:]
    assert {'idx1.entries', 'idx1.eof'} & hard_rules(profile.validate(container.parse_avi(m), m))


def test_mutante_sin_byte_de_relleno(base):
    """Los JPEG de tamano impar llevan pad 0x00; quitarlo desfasa todos los offsets."""
    _, buf, asset = base
    impar = next((r for r in asset.records if r.size & 1), None)
    if impar is None:
        pytest.skip('este archivo no tiene chunks impares')
    pos = impar.data_off + impar.size          # el byte de relleno
    assert buf[pos] == 0, 'el pad medido en el corpus es 0x00'
    m = buf[:pos + 1] + buf[pos + 2:]
    assert 'idx1.alineado' in hard_rules(profile.validate(container.parse_avi(m), m))


def test_mutante_suggested_buf(base):
    _, buf, _ = base
    i = buf.index(b'strh') + 8 + 36
    m = bytearray(buf)
    m[i:i + 4] = (9999).to_bytes(4, 'little')
    assert 'strh.video.suggested_buf' in hard_rules(profile.validate(container.parse_avi(bytes(m)), m))


def test_mutante_dimensiones(base):
    _, buf, _ = base
    i = buf.index(b'strf') + 8 + 4
    m = bytearray(buf)
    m[i:i + 8] = (240).to_bytes(4, 'little') + (240).to_bytes(4, 'little')
    assert {'strf.video.dims', 'jpeg.forma'} & hard_rules(profile.validate(container.parse_avi(m), m))


def test_mutante_pcm_sustituido_no_es_hallazgo(base):
    """Suplantar el payload de un chunk de audio por ruido: la cabecera sigue
    cuadrandose, asi que solo el tamano puede delatarlo. Se usa para exigir que
    el validator no confie en el idx1 cuando el movi miente."""
    _, buf, asset = base
    v, a = asset.video[0], asset.audio[0]
    assert a.size == writer.AUDIO_BYTES_PER_FRAME
    m = bytearray(buf)
    m[a.data_off:a.data_off + a.size] = b'\x5a' * a.size
    f = profile.validate(container.parse_avi(bytes(m)), bytes(m))
    assert hard_rules(f) == set(), 'cambiar bytes de PCM no invalida el contenedor'


def test_mutante_pcm_a_estereo(base):
    _, buf, _ = base
    j = buf.rindex(b'strf') + 8          # el strf de audio es el ultimo del hdrl
    m = bytearray(buf)
    m[j + 2:j + 4] = (2).to_bytes(2, 'little')
    assert 'strf.audio.pcm' in hard_rules(profile.validate(container.parse_avi(bytes(m)), m))


def test_mutante_jpeg_444(base):
    """Re-codificar un frame en 4:4:4: el contenedor sigue bien pero la forma
    JPEG deja de ser la medida en el corpus (submuestreo 4:2:0)."""
    pytest.importorskip('PIL')
    from PIL import Image
    import io
    _, _, asset = base
    img = Image.open(io.BytesIO(asset.video[0].data)).convert('RGB')
    y444 = io.BytesIO()
    img.save(y444, 'JPEG', subsampling=0, quality=90)   # 4:4:4: sampling=0 es ignorado por PIL
    frames = [y444.getvalue()] + [r.data for r in asset.video[1:]]
    m = writer.build_avi(frames, asset.pcm())
    assert 'jpeg.forma' in hard_rules(profile.validate(container.parse_avi(m), m))


def test_mutante_avih_total_frames(base):
    _, buf, _ = base
    i = buf.index(b'avih') + 8 + 16
    m = bytearray(buf)
    m[i:i + 4] = (int.from_bytes(buf[i:i + 4], 'little') + 1).to_bytes(4, 'little')
    assert 'avih.total_frames' in hard_rules(profile.validate(container.parse_avi(bytes(m)), m))
