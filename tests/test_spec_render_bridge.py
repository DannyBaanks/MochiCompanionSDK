"""Pruebas de spec, render, puente y CLI.

Ningun test toca el dispositivo: los volumenes de prueba se construyen en
/tmp con archivos generados por el propio SDK, y el unico `apply` que corre
escribe en esos directorios falsos.
"""
import json
import os
import sys
import wave

import pytest
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mochisdk import bridge, cli, deploy, playlist, profile, render, spec as specmod
from mochisdk.container import AviError, load_avi


# ------------------------------------------------------------------ fixtures

@pytest.fixture(scope='session')
def pack(tmp_path_factory):
    """Mini-pack de Companion sintetico: no depende del repo Companion."""
    d = tmp_path_factory.mktemp('pack')
    frames = [Image.new('RGBA', (64, 48), (i * 60, 30, 200 - i * 40, 255)) for i in range(4)]
    frames[0].save(d / 't.gif', save_all=True, append_images=frames[1:],
                   duration=[100, 200, 100, 300], loop=0)
    anims = {a: 't.gif' for a in list(bridge.ANIM_A_SLOT)}
    (d / 'manifest.json').write_text(json.dumps({'name': 'sintetico', 'animations': anims}))
    return str(d)


@pytest.fixture(scope='session')
def rendered(pack, tmp_path_factory):
    out = str(tmp_path_factory.mktemp('render') / 'r.avi')
    return render.render_companion_pack(pack, 'idle', 20, out_path=out)


@pytest.fixture
def volumen(rendered, tmp_path):
    """Volumen falso con el playlist y los 9 slots del puente poblados."""
    v = tmp_path / 'vol'
    (v / 'video').mkdir(parents=True)
    names = sorted(set(bridge.ANIM_A_SLOT.values()))
    (v / 'playlist.lst').write_bytes(playlist.render(names))
    body = open(rendered['ruta'], 'rb').read()
    for n in names:
        (v / 'video' / n).write_bytes(body)
    return str(v)


def _spec(pack, anim='idle', slot='Blink.avi', n=20, salida=None):
    return specmod.normalize({
        'spec': specmod.SPEC_ID, 'id': 't-%s' % anim,
        'fuente': {'tipo': 'companion_pack', 'pack': pack, 'animacion': anim,
                   'fotogramas': n},
        'destino': {'nombre_video': slot, 'salida': salida or 'build/t.avi'}})


def _ev(tipo, **kw):
    return bridge.new_event(tipo, agent='test', **kw)


# ---------------------------------------------------------------------- spec

def test_spec_ejemplo_es_valido():
    assert specmod.normalize(specmod.ejemplo())['fuente']['fotogramas'] == 90


@pytest.mark.parametrize('mut', [
    {'spec': 'otro'},
    {'spec': specmod.SPEC_ID},
    {'spec': specmod.SPEC_ID, 'id': 'x'},
    {'spec': specmod.SPEC_ID, 'id': 'x', 'fuente': {'tipo': 'gif', 'archivo': '/tmp/a.gif'}},
    {'spec': specmod.SPEC_ID, 'id': 'x', 'destino': {'nombre_video': 'A.avi'},
     'fuente': {'tipo': 'gif'}},
    {'spec': specmod.SPEC_ID, 'id': 'x', 'destino': {},
     'fuente': {'tipo': 'companion_pack', 'pack': '/tmp'}},
    {'spec': specmod.SPEC_ID, 'id': 'x', 'destino': {'nombre_video': 'A.avi'},
     'fuente': {'tipo': 'raro', 'archivo': '/tmp/a.gif'}},
    {'spec': specmod.SPEC_ID, 'id': 'x', 'destino': {'nombre_video': 'A.avi'},
     'fuente': {'tipo': 'gif', 'archivo': '/tmp/a.gif', 'resample': 'magico'}},
    {'spec': specmod.SPEC_ID, 'id': 'x', 'destino': {'nombre_video': 'A.avi'},
     'fuente': {'tipo': 'gif', 'archivo': '/tmp/a.gif', 'fotogramas': 3}},
])
def test_spec_rechaza_doc_incompletos(mut):
    with pytest.raises(AviError):
        specmod.normalize(mut)


def test_spec_aplica_default_de_presupuesto():
    s = _spec('/p')
    assert s['fuente']['budget_bytes_por_frame'] == specmod.DEFAULTS['budget_bytes_por_frame']


def test_spec_traduce_a_kwargs_de_render():
    kw = specmod.to_render_kwargs(_spec('PACK'))
    assert kw['animation'] == 'idle' and kw['n_frames'] == 20
    assert kw['max_frame_bytes'] == specmod.DEFAULTS['budget_bytes_por_frame']
    assert kw['resample'] == 'lanczos'


def test_spec_guardado_y_relegido_vuelve_igual(pack, tmp_path):
    doc = _spec(pack, 'thinking', 'Squint.avi')
    p = str(tmp_path / 's.json')
    with open(p, 'w') as fh:
        json.dump(doc, fh)
    assert specmod.load(p)['destino']['nombre_video'] == 'Squint.avi'


# -------------------------------------------------------------------- render

def test_gif_frames_trae_duraciones_reales(pack):
    frames, durs = render.gif_frames(os.path.join(pack, 't.gif'))
    assert len(frames) == 4 and durs == [100, 200, 100, 300]


def test_resample_to_30_pesa_cada_frame_segun_su_tiempo():
    seq = [Image.new('RGB', (8, 8), c) for c in ((255, 0, 0), (0, 255, 0),
                                                 (0, 0, 255), (255, 255, 0))]
    out = render.resample_to_30(seq, [100, 200, 100, 300], 22)
    colores = [im.getpixel((4, 4)) for im in out]
    # t = 33*i ms sobre un ciclo de 700 ms: los conteos proporcionan a las duraciones
    assert [colores.count(c) for c in ((255, 0, 0), (0, 255, 0), (0, 0, 255),
                                       (255, 255, 0))] == [4, 6, 3, 9]
    assert len(set(colores)) == 4, 'un resample roto devuelve una imagen fija'


def test_resample_bajo_el_minimo_no_inventa_bucle():
    seq = [Image.new('RGB', (8, 8), (i * 80, 0, 0)) for i in range(3)]
    out = render.resample_to_30(seq, [100, 100, 100], 9)
    colores = [im.getpixel((0, 0)) for im in out]
    # t = 0,33,66,99 | 132,165,198 | 231,264 ms: 4 / 3 / 2
    assert colores == [(0, 0, 0)] * 4 + [(80, 0, 0)] * 3 + [(160, 0, 0)] * 2


def test_fit_conserva_aspect_y_rellena():
    small = Image.new('RGB', (100, 50), (200, 100, 0))
    out = render.fit(small, pad=(1, 2, 3))
    assert out.size == (480, 480)
    assert out.getpixel((0, 0)) == (1, 2, 3)
    assert out.getpixel((240, 240)) == (200, 100, 0)


def test_encode_jpeg_respeta_el_presupuesto_y_el_forma_factory():
    img = Image.new('RGB', (480, 480), (10, 200, 30))
    for budget in (31893, 8000, 2000):
        data, q = render.encode_jpeg(img, budget)
        assert len(data) <= budget, (budget, len(data))
        marker, precision, alto, ancho, sampling = profile.jpeg_shape(data)
        assert marker == 0xC0, 'baseline SOF0, no progresivo'
        assert (precision, alto, ancho) == (8, 480, 480)
        assert sampling == (0x22, 0x11, 0x11), '4:2:0 medido en los 9650 frames factory'


def test_silence_pcm_usa_el_cuantito_medido():
    assert len(render.silence_pcm(7)) == 7 * 3200


def test_load_pcm_exige_48k_mono_16bit(tmp_path):
    p = str(tmp_path / 'a.wav')
    with wave.open(p, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes(b'\x00' * 6400)
    with pytest.raises(AviError):
        render.load_pcm(p, 1)
    with wave.open(p, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(48000)
        w.writeframes(b'\x00' * 9600)
    assert render.load_pcm(p, 2) == b'\x00' * 6400      # recortado al quantum exacto
    assert len(render.load_pcm(p, 3)) == 9600
    with pytest.raises(AviError):
        render.load_pcm(p, 4)                            # no alcanza


def test_render_pack_produce_un_avi_valido_y_no_una_imagen_fija(rendered):
    assert rendered['frames'] == 20
    assert rendered['validacion']['duros'] == 0
    assert rendered['frame_bytes']['max'] <= rendered['budget_por_frame']
    assert os.path.getsize(rendered['ruta']) == rendered['bytes_avi']
    a = load_avi(rendered['ruta'])
    assert a.audio_bytes == 20 * 3200
    assert len({r.data for r in a.video}) > 1, 'todos los frames identicos: resample roto'


def test_render_spec_escribe_en_la_salida_del_spec(pack, tmp_path):
    s = _spec(pack, 'working', 'Revs.avi', 20, salida=str(tmp_path / 'o.avi'))
    rep = render.render_spec(s)
    assert rep['ruta'] == str(tmp_path / 'o.avi') and os.path.isfile(rep['ruta'])
    assert rep['nombre_video_destino'] == 'Revs.avi'


# -------------------------------------------------------------------- puente

@pytest.mark.parametrize('ev,razon', [
    ({'type': 'state'}, 'version'),
    ({'version': 'companion-event-v1', 'id': '', 'agent': 'a', 'type': 'state',
      'created_at': '2026-01-01T00:00:00Z', 'value': 'idle'}, 'id'),
    ({'version': 'companion-event-v1', 'id': 'x', 'agent': 'a', 'type': 'bailar',
      'created_at': '2026-01-01T00:00:00Z'}, 'tipo'),
    ({'version': 'companion-event-v1', 'id': 'x', 'agent': 'a', 'type': 'state',
      'created_at': 'ayer', 'value': 'idle'}, 'fecha'),
    ({'version': 'companion-event-v1', 'id': 'x', 'agent': 'a', 'type': 'state',
      'created_at': '2026-01-01T00:00:00Z', 'value': 'hambriento'}, 'valor'),
    ({'version': 'companion-event-v1', 'id': 'x', 'agent': 'a', 'type': 'move',
      'created_at': '2026-01-01T00:00:00Z', 'value': 'arriba'}, 'posicion'),
    ({'version': 'companion-event-v1', 'id': 'x', 'agent': 'a', 'type': 'say',
      'created_at': '2026-01-01T00:00:00Z'}, 'text'),
    ({'version': 'companion-event-v1', 'id': 'x', 'agent': 'a', 'type': 'status',
      'created_at': '2026-01-01T00:00:00Z', 'ttl': -1}, 'ttl'),
])
def test_validate_event_rechaza_mutantes(ev, razon):
    with pytest.raises(bridge.BridgeError):
        bridge.validate_event(ev)


def test_new_event_ids_unicos_dentro_del_mismo_segundo():
    ids = {_ev('status')['id'] for _ in range(50)}
    assert len(ids) == 50


@pytest.mark.parametrize('tipo,valor,anim', [
    ('state', 'working', 'working'), ('mood', 'error', 'error'),
    ('summon', None, 'idle'), ('hide', None, None), ('state', 'hidden', None),
    ('move', 'top-right', 'running-right'), ('move', 'bottom-left', 'running-left'),
    ('move', 'dock', 'drag'), ('say', None, None), ('status', None, None),
])
def test_anim_of_cubre_todos_los_tipos(tipo, valor, anim):
    ev = _ev('say', text='hola') if tipo == 'say' else _ev(tipo, **({'value': valor} if valor else {}))
    assert bridge.anim_of(ev) == anim


def test_spec_for_event_usa_el_mapa_y_deja_rastro_del_agente():
    ev = _ev('summon')
    s = bridge.spec_for_event(ev, pack='/p', mapping={'idle': 'Blink.avi'})
    assert s['destino']['nombre_video'] == 'Blink.avi'
    assert s['puente']['agente'] == 'test' and s['puente']['origen_evento'] == ev['id']


def test_spec_for_event_exige_que_el_mapa_defina_la_animacion():
    with pytest.raises(bridge.BridgeError):
        bridge.spec_for_event(_ev('state', value='waiting'), pack='/p',
                              mapping={'idle': 'Blink.avi'})


def test_read_events_avanza_por_bytes_y_rechaza_lineas_malas(tmp_path):
    p = str(tmp_path / 'inbox.jsonl')
    bridge.append_jsonl(p, _ev('state', value='idle'))
    evs, off = bridge.read_events(p)
    assert len(evs) == 1 and off > 0
    assert bridge.read_events(p, off)[0] == []
    with open(p, 'a') as fh:
        fh.write('no-es-json\n')
    with pytest.raises(bridge.BridgeError):
        bridge.read_events(p, 0)


def test_handle_renderiza_y_planifica_sin_tocar_el_volumen(pack, volumen):
    destino = os.path.join(volumen, 'video', 'Blink.avi')
    antes = deploy.sha256_file(destino)
    r = bridge.handle(_ev('state', value='idle'), pack=pack, mapping=bridge.load_map(None),
                      n_frames=20, build_dir=os.path.join(volumen, 'build'), volume=volumen)
    assert r['valido'] is True and r['slot'] == 'Blink.avi'
    assert r['plan_token'] and 'no_demostrado' in r
    assert deploy.sha256_file(destino) == antes, 'el puente escribio en el volumen'


def test_handle_ignora_eventos_que_no_piden_animacion(pack, tmp_path):
    r = bridge.handle(_ev('say', text='hola'), pack=pack, mapping=bridge.load_map(None),
                      build_dir=str(tmp_path))
    assert r['accion'] == 'ignorada'


def test_handle_no_planea_si_el_render_trae_hallazgos_duros(pack, volumen, tmp_path):
    """Slot que no existe en el volumen: deploy rehusa y el puente propaga el no."""
    m = bridge.load_map(None)
    m['idle'] = 'Inexistente.avi'
    with pytest.raises(AviError):
        bridge.handle(_ev('state', value='idle'), pack=pack, mapping=m, n_frames=20,
                      build_dir=str(tmp_path / 'b'), volume=volumen)


def test_process_inbox_consume_el_cursor_y_no_escribe_el_volumen(pack, volumen, tmp_path):
    inbox = str(tmp_path / 'inbox.jsonl')
    for v in ('idle', 'thinking'):
        bridge.append_jsonl(inbox, _ev('state', value=v))
    previos = {n: deploy.sha256_file(os.path.join(volumen, 'video', n))
               for n in sorted(os.listdir(os.path.join(volumen, 'video')))}
    b, cur = str(tmp_path / 'b'), str(tmp_path / 'cursor')
    kw = dict(pack=pack, mapping=bridge.load_map(None), n_frames=20, build_dir=b)
    res = bridge.process_inbox(inbox, cursor_root=cur, **kw)
    assert res['eventos'] == 2 and res['escribio_volumen'] is False
    assert bridge.process_inbox(inbox, cursor_root=cur, **kw)['eventos'] == 0
    assert bridge.process_inbox(inbox, cursor_root=cur, from_offset=0,
                                track=False, **kw)['eventos'] == 2
    for n, sha in previos.items():
        assert deploy.sha256_file(os.path.join(volumen, 'video', n)) == sha


def test_process_inbox_emite_eventos_status_leibles_por_companion(pack, tmp_path):
    inbox, outbox = str(tmp_path / 'in.jsonl'), str(tmp_path / 'out.jsonl')
    bridge.append_jsonl(inbox, _ev('state', value='success'))
    res = bridge.process_inbox(inbox, pack=pack, mapping=bridge.load_map(None), n_frames=20,
                               build_dir=str(tmp_path / 'b'), outbox=outbox,
                               cursor_root=str(tmp_path / 'c'))
    assert res['resultados'][0]['valido']
    ecos, off = bridge.read_events(outbox, 0)
    assert len(ecos) == 1 and ecos[0]['agent'] == 'mochic' and ecos[0]['type'] == 'status'


@pytest.mark.parametrize('tipo,valor,acepta', [
    ('state', 'idle', True), ('state', 'no_existe', False), ('move', 'dock', True),
    ('summon', None, True), ('say', None, True)])
def test_control_de_contracto_contra_companion(tipo, valor, acepta):
    """El validator propio debe coincidir con el de Companion cuando esta disponible."""
    comp = os.path.expanduser('~/Development/ISyCo Git/Companion/src')
    if not os.path.isdir(comp):
        pytest.skip('repo Companion no presente')
    sys.path.insert(0, comp)
    try:
        from companion.protocol import ProtocolError, validate_event as vcomp
    except ImportError:
        pytest.skip('companion.protocol no importa')
    fields = {'text': 'hola'} if tipo == 'say' else ({'value': valor} if valor else {})
    ev = {'version': 'companion-event-v1', 'id': 'x', 'agent': 'a',
          'created_at': '2026-01-01T00:00:00Z', 'type': tipo, **fields}
    propio_ok = True
    try:
        bridge.validate_event(dict(ev))
    except bridge.BridgeError:
        propio_ok = False
    comp_ok = True
    try:
        vcomp(ev)
    except ProtocolError:
        comp_ok = False
    assert propio_ok == comp_ok == acepta


# ----------------------------------------------------------------------- cli

def test_cli_version(capsys):
    assert cli.main(['version']) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc['spec'] == specmod.SPEC_ID and doc['codigos_salida']['5']


def test_cli_inspect_y_validate_sobre_asset_valido(capsys, rendered):
    assert cli.main(['inspect', rendered['ruta']]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc['audio_cuanto_ok'] is True and doc['registros']['video'] == 20
    assert cli.main(['validate', rendered['ruta']]) == 0


def test_cli_validate_rechaza_un_mutante(rendered, tmp_path):
    """Mutante por header_off, como la suite del validator: buscar b'01wb' a ciegas
    pega con el JUNK de la cabecera y no cambia nada relevante."""
    p = str(tmp_path / 'm.avi')
    asset = load_avi(rendered['ruta'])
    buf = bytearray(open(rendered['ruta'], 'rb').read())
    off = asset.audio[0].header_off + 4
    buf[off:off + 4] = (3000).to_bytes(4, 'little')
    open(p, 'wb').write(bytes(buf))
    assert cli.main(['validate', p]) == cli.EXIT_HARD


def test_cli_codigos_de_salida_estables(capsys, pack, volumen, tmp_path):
    assert cli.main(['inspect', str(tmp_path / 'no-existe.avi')]) == cli.EXIT_INPUT
    assert cli.main(['plan', volumen]) == cli.EXIT_USAGE
    assert cli.main(['watch', '--inbox', str(tmp_path / 'no.jsonl'), '--pack', pack]) == cli.EXIT_INPUT
    assert cli.main(['playlist', str(tmp_path)]) == cli.EXIT_INPUT
    vacio = str(tmp_path / 'plan.json')
    json.dump({'token': 'abc'}, open(vacio, 'w'))
    assert cli.main(['apply', vacio]) == cli.EXIT_GATE
    assert cli.main(['apply', vacio, '--token', 'otro']) == cli.EXIT_GATE
    assert cli.main(['spec', '--pack', pack, '--fotogramas', '2']) == cli.EXIT_HARD


def test_cli_plan_rehusa_destinos_que_no_existen(capsys, pack, volumen, tmp_path):
    s = str(tmp_path / 'spec.json')
    assert cli.main(['spec', '--pack', pack, '--slot', 'NoEsta.avi', '--id', 'rehusa',
                    '-o', s]) == 0
    assert cli.main(['plan', volumen, s]) == cli.EXIT_REFUSED


def test_cli_spec_build_plan_apply_rollback_end_to_end(capsys, pack, volumen, tmp_path,
                                                       monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = str(tmp_path / 'spec.json')
    assert cli.main(['spec', '--pack', pack, '--animacion', 'idle', '--slot', 'Blink.avi',
                    '--fotogramas', '20', '--id', 'cli-demo', '-o', s]) == 0
    doc = json.load(open(s))
    assert doc['destino']['salida'] == 'build/cli-demo.avi'

    assert cli.main(['build', s]) == 0
    assert os.path.isfile(doc['destino']['salida'])

    plan_out = str(tmp_path / 'plan.json')
    assert cli.main(['plan', volumen, s, '--salida', plan_out]) == 0
    p = json.load(open(plan_out))
    assert p['operaciones'][0]['destino'] == 'video/Blink.avi'

    assert cli.main(['apply', plan_out, '--token', 'no-es-el-token']) == cli.EXIT_GATE
    assert cli.main(['apply', plan_out, '--token', p['token'], '--copia',
                    str(tmp_path / 'bak'), '--diario', str(tmp_path / 'j.json')]) == 0
    dst = os.path.join(volumen, 'video', 'Blink.avi')
    assert deploy.sha256_file(dst) == deploy.sha256_file(doc['destino']['salida'])
    assert cli.main(['rollback', str(tmp_path / 'j.json')]) == 0
    assert deploy.sha256_file(dst) == p['operaciones'][0]['destino_sha256_actual']


def test_cli_plan_con_mapa_arbitrary_sin_spec(capsys, pack, volumen, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli.main(['build', _write_spec(pack, tmp_path)]) == 0
    src = str(tmp_path / 'build' / 't.avi')
    assert cli.main(['plan', volumen, '--par', src, 'video/Squint.avi',
                     '--salida', str(tmp_path / 'p.json')]) == 0


def _write_spec(pack, tmp_path):
    p = str(tmp_path / 'par-spec.json')
    json.dump(_spec(pack, 'thinking', 'Squint.avi', 20,
                    salida=str(tmp_path / 'build' / 't.avi')), open(p, 'w'))
    return p


def test_cli_emit_y_watch_sobre_inbox_local(capsys, pack, volumen, tmp_path):
    inbox = str(tmp_path / 'inbox.jsonl')
    assert cli.main(['emit', 'state', '--valor', 'idle', '--inbox', inbox]) == 0
    capsys.readouterr()
    assert cli.main(['watch', '--inbox', inbox, '--pack', pack, '--volumen', volumen,
                     '--fotogramas', '20', '--build-dir', str(tmp_path / 'b'),
                     '--cursor-root', str(tmp_path / 'c')]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc['eventos'] == 1 and doc['escribio_volumen'] is False
    assert doc['resultados'][0]['slot'] == 'Blink.avi'
    assert doc['no_demostrado'], 'el puente debe declarar lo que no esta demostrado'


def test_cli_map_exporta_y_relee(tmp_path):
    p = str(tmp_path / 'm.json')
    assert cli.main(['map', '-o', p]) == 0
    assert bridge.load_map(p) == bridge.ANIM_A_SLOT


def test_cli_profile_responde_el_perfil_medido(capsys):
    assert cli.main(['profile']) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc['perfil'] == 'mochi-factory-v1'
    assert doc['hechos']['n_archivos'] == 62
    assert doc['techo_bitrate']['frame_max_absoluto'] == 31893


# ------------------------------------------------------------- capturers (evidencia)

def _cargador(nombre):
    import importlib.util
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     'tools', nombre + '.py')
    sp = importlib.util.spec_from_file_location(nombre, p)
    mod = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(mod)
    return mod


def test_guard_out_niega_pisar_un_crudo_sellado(tmp_path):
    """El drift que mató a profile_v0: re-correar un capturer dentro de un pack
    ya sellado reemplaza evidencia cruda. Tiene que negarse por defecto."""
    cc = _cargador('capture_cli')
    raw = tmp_path / 'stdout.raw.txt'
    raw.write_text('crudo original\n')
    json.dump({'stdout': {'sha256': 'deadbeef', 'relative': str(raw)}},
              open(tmp_path / 'manifest.json', 'w'))
    with pytest.raises(SystemExit) as exc:
        cc.guard_out(str(raw))
    msg = str(exc.value)
    assert 'REFUSAL' in msg and '--out' in msg and '--fuerza' in msg
    assert raw.read_text() == 'crudo original\n', 'el crudo no se toco'


def test_guard_out_permite_escribir_sin_manifest_o_con_fuerza(tmp_path):
    cc = _cargador('capture_cli')
    cc.guard_out(str(tmp_path / 'nuevo.raw.txt'))            # no existe el crudo
    raw = tmp_path / 'stdout.raw.txt'
    raw.write_text('x\n')
    cc.guard_out(str(raw))                                   # sin manifest: libre
    json.dump({'stdout': {'sha256': 'abc'}}, open(tmp_path / 'manifest.json', 'w'))
    with pytest.raises(SystemExit):
        cc.guard_out(str(raw))
    cc.guard_out(str(raw), force=True)   # el humano pidio re-sellar
