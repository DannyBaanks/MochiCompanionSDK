"""Controles del contenedor y del muxer contra los 62 videos factory.

El control positivo no es un fixture inventado: es el corpus real del
dispositivo. build_avi() tiene que devolver exactamente los mismos bytes que
el archivo que el firmware ya reproduce; si eso se cumple, un asset generado
es estructuralmente indistinguible de uno factory.
"""
import glob
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mochisdk import container, writer

VIDEO_DIR = os.path.expanduser('~/megamochi-backup/volume_files/video')
FILES = sorted(glob.glob(os.path.join(VIDEO_DIR, '*.avi')))
pytestmark = pytest.mark.skipif(len(FILES) < 62, reason="falta el backup del corpus factory")


@pytest.mark.parametrize('path', FILES, ids=lambda p: os.path.basename(p))
def test_roundtrip_byte_exacto(path):
    original = open(path, 'rb').read()
    asset = container.load_avi(path)
    rebuilt = writer.build_avi([r.data for r in asset.video], asset.pcm())
    assert rebuilt == original, '%s: %d/%d bytes coinciden' % (
        path, sum(a == b for a, b in zip(rebuilt, original)), len(original))


@pytest.mark.parametrize('path', FILES[:6], ids=lambda p: os.path.basename(p))
def test_lectura_coherente(path):
    asset = container.load_avi(path)
    n = len(asset.video)
    assert n == asset.avih['total_frames'] == asset.streams[0].length
    assert asset.streams[0].fps == 30.0
    assert len(asset.audio) == n + 1                      # chunk de audio vacio al final
    assert asset.audio[-1].size == 0
    assert all(r.size == writer.AUDIO_BYTES_PER_FRAME for r in asset.audio[:-1])
    assert len(asset.idx1) == len(asset.records)
    assert all(r.keyframe for r in asset.video)


def test_idx1_flags_aplicados_desde_idx1():
    asset = container.load_avi(FILES[0])
    assert asset.video[0].flags & container.AVIIF_KEYFRAME
    assert asset.records[1].kind == 'audio'


def test_rechaza_audio_fuera_del_quantum():
    asset = container.load_avi(FILES[0])
    frames = [r.data for r in asset.video]
    with pytest.raises(container.AviError):
        writer.build_avi(frames, asset.pcm()[:-2])
    with pytest.raises(container.AviError):
        writer.build_avi(frames, b'')
    with pytest.raises(container.AviError):
        writer.build_avi([], asset.pcm())


def test_rechaza_no_avi():
    with pytest.raises(container.AviError):
        container.parse_avi(b'GIF89a' + b'\x00' * 64)
