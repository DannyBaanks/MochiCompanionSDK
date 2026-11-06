"""Despliegue en el volumen del Mochi: plan (solo lectura) y apply (escritura).

Ninguna funcion de este modulo abre un dispositivo. `plan` solo lee; `apply`
escribe y exige el token que devolvio `plan`. Eso no es seguridad de perimetro,
es la disciplina que pide el brief: el humano decide el momento exacto en que
la tarjeta cambia.

Garantias comprobables de apply():
  1. cada origen pasa profile.validate sin hallazgos duros antes de planearse;
  2. se guarda una copia local del destino FUERA del volumen y se verifica su
     SHA-256 antes de tocar nada;
  3. la escritura es tmp + os.replace dentro del mismo volumen (nunca un
     truncado in situ);
  4. despues de escribir se re-lee y se compara el SHA-256; si difiere, se
     restaura el backup automaticamente y se reporta el fallo;
  5. queda un journal con el orden exacto para rollback().

Lo que NO esta demostrado: que el firmware acepte un numero de entradas
distinto de 62 en playlist.lst, ni que reprograme al vuelo sin quitar el
cable. Por eso aqui solo se reemplazan archivos existentes.
"""
from __future__ import annotations

import hashlib, json, os, shutil, time

from . import profile
from .container import AviError, parse_avi


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for blk in iter(lambda: fh.read(1 << 20), b''):
            h.update(blk)
    return h.hexdigest()


def _canon(plan: dict) -> bytes:
    return json.dumps({k: v for k, v in plan.items() if k != 'token'},
                      sort_keys=True, ensure_ascii=False).encode()


def plan(volume: str, replacements: list[dict]) -> dict:
    """replacements: [{'origen': path, 'destino': 'video/Nombre.avi'}, ...]

    volume puede ser un directorio cualquiera (una copia de prueba o el
    volumen montado). No se toca nada.
    """
    ops = []
    for r in replacements:
        src, dst_rel = r['origen'], r['destino']
        dst = os.path.normpath(os.path.join(volume, dst_rel))
        if not dst.startswith(os.path.abspath(volume) + os.sep):
            raise AviError("el destino sale del volumen: %r" % dst_rel)
        if not os.path.isfile(dst):
            raise AviError("el destino no existe; agregar entradas nuevas al playlist NO esta "
                           "demostrado que el firmware lo acepte: %r" % dst_rel)
        buf = open(src, 'rb').read()
        findings = profile.validate(parse_avi(buf, path=src), buf)
        hard = [f.as_dict() for f in findings if f.severity == 'hard']
        if hard:
            raise AviError("%s no pasa la validacion: %s" % (src, hard[0]['regla']))
        ops.append({'origen': os.path.abspath(src),
                    'origen_sha256': hashlib.sha256(buf).hexdigest(),
                    'origen_bytes': len(buf),
                    'destino': dst_rel,
                    'destino_absoluto': dst,
                    'destino_sha256_actual': sha256_file(dst),
                    'destino_bytes_actual': os.path.getsize(dst),
                    'suaves': [f.as_dict() for f in findings if f.severity == 'soft']})
    p = {'accion': 'mochi-deploy-v1', 'volumen': os.path.abspath(volume),
         'creado_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
         'operaciones': ops, 'total_bytes': sum(o['origen_bytes'] for o in ops),
         'advertencia': 'Escribir en el volumen cambia el estado del dispositivo. '
                        'Este plan no ha escrito nada.'}
    p['token'] = hashlib.sha256(_canon(p)).hexdigest()[:12]
    return p


def apply(plan_obj: dict, confirm_token: str, *, backup_root: str | None = None,
          journal_path: str | None = None) -> dict:
    if confirm_token != plan_obj.get('token'):
        raise AviError("token de confirmacion no coincide con el plan; nada escrito. "
                       "Ejecute plan y pase su campo 'token'.")
    volume = plan_obj['volumen']
    if not os.path.isdir(volume):
        raise AviError("el volumen del plan no existe: %s" % volume)
    stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    backup_root = backup_root or os.path.join(os.getcwd(), '.mochisdk-rollback', stamp)
    os.makedirs(backup_root, exist_ok=True)

    hechos, journal = [], {'accion': 'mochi-deploy-v1', 'sello': stamp, 'volumen': volume,
                          'token': plan_obj['token'], 'entradas': []}
    for op in plan_obj['operaciones']:
        dst, src = op['destino_absoluto'], op['origen']
        actual = sha256_file(dst)
        if actual != op['destino_sha256_actual']:
            raise AviError("el destino cambio desde que se planifico (%s): aborta sin escribir "
                           "ese archivo; los anteriores ya escritos quedan en el journal"
                           % op['destino'])
        # el nombre lleva el sha PREVIO: dos escrituras al mismo destino en el mismo
        # backup_root chocan por basename (asi perdio su backup original journal-boot
        # el 2026-11-06) y el journal de la primera pasa a apuntar a otros bytes.
        bak = os.path.join(backup_root, '%s__%s' % (op['destino'].replace(os.sep, '_'),
                                                    actual[:8]))
        if os.path.exists(bak) and sha256_file(bak) != actual:
            raise AviError("el backup existente en %s no calza con el estado previo de %s; "
                           "nada escrito" % (bak, op['destino']))
        shutil.copy2(dst, bak)
        if sha256_file(bak) != actual:
            raise AviError("la copia de seguridad no calza con el original: %s" % op['destino'])
        buf = open(src, 'rb').read()
        if hashlib.sha256(buf).hexdigest() != op['origen_sha256']:
            raise AviError("el origen cambio desde el plan: %s" % src)
        tmp = dst + '.mochisdk-tmp'
        with open(tmp, 'wb') as fh:
            fh.write(buf)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, dst)
        if sha256_file(dst) != op['origen_sha256']:
            shutil.copy2(bak, dst)
            raise AviError("verificacion post-escritura fallida en %s; restaurado el backup"
                           % op['destino'])
        journal['entradas'].append({'destino': op['destino'], 'backup': bak,
                                    'sha_previo': actual, 'sha_nuevo': op['origen_sha256']})
        hechos.append(op['destino'])

    # el journal por defecto lleva sello+token: un solo `journal.json` por
    # backup_root hacia que la segunda aplicacion borrara el historico de la
    # primera y su rollback quedara imposibilitado (lo demostro el control de
    # colision en tests/test_deploy_playlist.py).
    journal_path = journal_path or os.path.join(
        backup_root, 'journal-%s-%s.json' % (stamp, plan_obj['token'][:12]))
    with open(journal_path, 'w') as fh:
        json.dump(journal, fh, indent=1)
    return {'escritos': hechos, 'journal': journal_path, 'backup_root': backup_root,
            'total_bytes': sum(op['origen_bytes'] for op in plan_obj['operaciones'])}


def rollback(journal_path: str) -> dict:
    j = json.load(open(journal_path))
    restaurados = []
    for e in reversed(j['entradas']):
        dst = os.path.join(j['volumen'], e['destino'])
        if sha256_file(dst) == e['sha_previo']:
            restaurados.append((e['destino'], 'ya estaba intacto'))
            continue
        if sha256_file(e['backup']) != e['sha_previo']:
            raise AviError("el backup del journal no calza con el estado previo de %s; no se "
                           "escribe nada por esta entrada (journal %s)"
                           % (e['destino'], journal_path))
        shutil.copy2(e['backup'], dst)
        if sha256_file(dst) != e['sha_previo']:
            raise AviError("rollback no pudo restaurar %s" % e['destino'])
        restaurados.append((e['destino'], 'restaurado'))
    return {'restaurados': restaurados, 'journal': journal_path}
