"""Controles del playlist y del ciclo plan/apply/rollback.

El volumen de prueba es SIEMPRE un directorio falso en /tmp construido con
copias locales del backup. Ningun test de este archivo puede escribir en el
dispositivo: no abre /dev, no desmonta, no usa un camino de volumen real.
"""
import hashlib
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mochisdk import container, deploy, playlist, profile, writer

BACKUP = os.path.expanduser('~/megamochi-backup/volume_files')
PLIST = os.path.join(BACKUP, 'playlist.lst')
pytestmark = pytest.mark.skipif(not os.path.isdir(BACKUP), reason="falta el backup del volumen")


# --------------------------------------------------------------------- playlist
def test_playlist_roundtrip_byte_exacto():
    data = open(PLIST, 'rb').read()
    names = playlist.parse(data)
    assert len(names) == 62 and all(names)
    assert playlist.render(names) == data


def test_playlist_1a1_con_disco():
    names = set(playlist.parse(open(PLIST, 'rb').read()))
    disk = set(os.listdir(os.path.join(BACKUP, 'video')))
    assert names == disk


def test_playlist_rechaza_rutas_y_nombres_largos():
    with pytest.raises(playlist.PlaylistError):
        playlist.render(['video/Angry.avi'])
    with pytest.raises(playlist.PlaylistError):
        playlist.render(['x' * 130 + '.avi'])


def test_playlist_registro_vacio_es_correcto():
    assert playlist.parse(playlist.render([''])) == ['']


# ------------------------------------------------------------- volumen de prueba
@pytest.fixture()
def fake_volume(tmp_path):
    v = tmp_path / 'volume'
    (v / 'video').mkdir(parents=True)
    shutil.copy2(PLIST, v / 'playlist.lst')
    for name in ('Angry.avi', 'Blink.avi'):
        shutil.copy2(os.path.join(BACKUP, 'video', name), str(v / 'video' / name))
    return str(v)


@pytest.fixture()
def nuevo_avi(tmp_path):
    """Un asset generado por el propio SDK: frames de Blink con otro orden."""
    a = container.load_avi(os.path.join(BACKUP, 'video', 'Blink.avi'))
    frames = [r.data for r in a.video][::-1]
    buf = writer.build_avi(frames, a.pcm())
    p = tmp_path / 'Blink.avi'
    p.write_bytes(buf)
    return str(p)


@pytest.fixture()
def otro_avi(tmp_path):
    """Tercer orden de los mismos frames: otra escritura al mismo slot."""
    a = container.load_avi(os.path.join(BACKUP, 'video', 'Blink.avi'))
    frames = [r.data for r in a.video]
    buf = writer.build_avi(frames[1:] + frames[:1], a.pcm())
    p = tmp_path / 'otro-Blink.avi'
    p.write_bytes(buf)
    return str(p)


def test_plan_no_escribe_nada(fake_volume, nuevo_avi):
    antes = {r: sorted(f for f in fs) for r, fs, _ in os.walk(fake_volume)}
    p = deploy.plan(fake_volume, [{'origen': nuevo_avi, 'destino': 'video/Blink.avi'}])
    assert p['token'] and len(p['operaciones']) == 1
    assert {r: sorted(f for f in fs) for r, fs, _ in os.walk(fake_volume)} == antes
    assert p['operaciones'][0]['destino_sha256_actual'] != p['operaciones'][0]['origen_sha256']


def test_plan_rechaza_asset_invalido(fake_volume, nuevo_avi):
    malo = bytearray(open(nuevo_avi, 'rb').read())
    i = malo.index(b'MJPG')                     # handler del strh de video
    malo[i:i + 4] = b'DIB '
    open(nuevo_avi, 'wb').write(bytes(malo))
    with pytest.raises(Exception) as e:
        deploy.plan(fake_volume, [{'origen': nuevo_avi, 'destino': 'video/Blink.avi'}])
    assert 'validacion' in str(e.value).lower()


def test_apply_con_token_y_rollback(fake_volume, nuevo_avi):
    p = deploy.plan(fake_volume, [{'origen': nuevo_avi, 'destino': 'video/Blink.avi'}])
    original = open(os.path.join(fake_volume, 'video', 'Blink.avi'), 'rb').read()
    r = deploy.apply(p, p['token'], backup_root=os.path.join(fake_volume, '..', 'bak'))
    destino = os.path.join(fake_volume, 'video', 'Blink.avi')
    assert hashlib.sha256(open(destino, 'rb').read()).hexdigest() == p['operaciones'][0]['origen_sha256']
    assert 'mochisdk-tmp' not in os.listdir(os.path.dirname(destino))
    j = deploy.rollback(r['journal'])
    assert hashlib.sha256(open(destino, 'rb').read()).hexdigest() == hashlib.sha256(original).hexdigest()
    assert j['restaurados'][0][1] == 'restaurado'


def test_apply_sin_token_no_toca_nada(fake_volume, nuevo_avi):
    p = deploy.plan(fake_volume, [{'origen': nuevo_avi, 'destino': 'video/Blink.avi'}])
    destino = os.path.join(fake_volume, 'video', 'Blink.avi')
    antes = open(destino, 'rb').read()
    with pytest.raises(container.AviError):
        deploy.apply(p, 'no-el-token')
    assert open(destino, 'rb').read() == antes


def test_apply_aborta_si_el_destino_muto(fake_volume, nuevo_avi):
    p = deploy.plan(fake_volume, [{'origen': nuevo_avi, 'destino': 'video/Blink.avi'}])
    open(os.path.join(fake_volume, 'video', 'Blink.avi'), 'wb').write(b'RF' + b'\x00' * 100)
    with pytest.raises(container.AviError) as e:
        deploy.apply(p, p['token'], backup_root=os.path.join(fake_volume, '..', 'bak2'))
    assert 'cambio desde' in str(e.value)


def test_plan_rechaza_destino_inexistente(fake_volume, nuevo_avi):
    with pytest.raises(container.AviError):
        deploy.plan(fake_volume, [{'origen': nuevo_avi, 'destino': 'video/NUEVO.avi'}])


def test_plan_rechaza_escape_del_volumen(fake_volume, nuevo_avi):
    with pytest.raises(container.AviError):
        deploy.plan(fake_volume, [{'origen': nuevo_avi, 'destino': '../escape.avi'}])


def test_el_asset_reemplazado_vale_validacion(fake_volume, nuevo_avi):
    """Despues de apply, lo que hay en el volumen sigue siendo un factory-AVI."""
    p = deploy.plan(fake_volume, [{'origen': nuevo_avi, 'destino': 'video/Blink.avi'}])
    deploy.apply(p, p['token'], backup_root=os.path.join(fake_volume, '..', 'bak3'))
    destino = os.path.join(fake_volume, 'video', 'Blink.avi')
    assert not [f for f in profile.validate_path(destino) if f.severity == 'hard']


def test_dos_escrituras_al_mismo_destino_no_chocan_en_el_backup(fake_volume, nuevo_avi,
                                                                otro_avi):
    """Control del incidente del 2026-11-06: apply nombraba el backup solo por
    basename, asi que la segunda escritura a `startup.avi` pisó la copia que
    apuntaba el primer journal y lo dejo apuntando a bytes ajenos."""
    bak_root = os.path.join(fake_volume, '..', 'bak-colision')
    destino = os.path.join(fake_volume, 'video', 'Blink.avi')
    original = open(destino, 'rb').read()
    p1 = deploy.plan(fake_volume, [{'origen': nuevo_avi, 'destino': 'video/Blink.avi'}])
    r1 = deploy.apply(p1, p1['token'], backup_root=bak_root)
    intermedio = open(destino, 'rb').read()
    assert intermedio != original
    p2 = deploy.plan(fake_volume, [{'origen': otro_avi, 'destino': 'video/Blink.avi'}])
    r2 = deploy.apply(p2, p2['token'], backup_root=bak_root)
    assert r2['journal'] != r1['journal']
    assert open(destino, 'rb').read() not in (original, intermedio)
    guardadas = [b for b in os.listdir(bak_root) if b.startswith('video_Blink.avi__')]
    assert len(guardadas) == 2
    deploy.rollback(r1['journal'])
    assert open(destino, 'rb').read() == original


def test_rollback_rechaza_un_backup_adulterado(fake_volume, nuevo_avi):
    """El journal-boot real de hoy tiene un backup que fue sobrescrito: rollback
    debe negarse antes de escribir, no instalar bytes que no son el estado previo."""
    import json
    bak_root = os.path.join(fake_volume, '..', 'bak-adulto')
    destino = os.path.join(fake_volume, 'video', 'Blink.avi')
    p = deploy.plan(fake_volume, [{'origen': nuevo_avi, 'destino': 'video/Blink.avi'}])
    r = deploy.apply(p, p['token'], backup_root=bak_root)
    escrito = open(destino, 'rb').read()
    entry = json.load(open(r['journal']))['entradas'][0]
    open(entry['backup'], 'wb').write(b'RF' + b'\x00' * 200)
    with pytest.raises(container.AviError) as e:
        deploy.rollback(r['journal'])
    assert 'backup del journal' in str(e.value)
    assert open(destino, 'rb').read() == escrito
