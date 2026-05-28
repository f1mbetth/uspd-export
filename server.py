#!/usr/bin/env python3
"""
УСПД Export Tool — Flask-сервер.
Запуск: python server.py
Откроет http://localhost:5000 в браузере автоматически.
"""

import io, json, os, sys, threading, webbrowser
from collections import Counter
import pandas as pd
from flask import Flask, request, jsonify, send_file, send_from_directory

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from config.settings  import load_settings, save_settings, DEFAULT_SETTINGS
from config.profiles  import DEFAULT_DEVICE_TYPES
from config.tag_types import DEFAULT_TAG_TYPES, DEFAULT_TAG_PRESETS
from core.parsers     import detect_file_type, PARSERS, FILE_TYPE_LABELS, merge_formula_overrides
from core.export_gen  import generate_devices_export
from core.tags_gen    import generate_tags, get_ids_col

app = Flask(__name__, static_folder=_ROOT, static_url_path='')

_settings = load_settings()

# ─── Статика ──────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory(_ROOT, 'index.html')

# ─── Настройки ────────────────────────────────────────────────────────────────

@app.route('/api/settings', methods=['GET'])
def api_settings_get():
    result = dict(_settings)
    result['tag_presets'] = DEFAULT_TAG_PRESETS      # пресеты только для чтения
    return jsonify(result)

@app.route('/api/settings', methods=['POST'])
def api_settings_post():
    global _settings
    data = request.get_json(force=True)
    _settings.update(data)
    save_settings(_settings)
    return jsonify({'ok': True})

@app.route('/api/defaults', methods=['GET'])
def api_defaults():
    result = dict(DEFAULT_SETTINGS)
    result['tag_presets'] = DEFAULT_TAG_PRESETS
    return jsonify(result)

# ─── Разбор файла (без генерации) ─────────────────────────────────────────────

@app.route('/api/parse', methods=['POST'])
def api_parse():
    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'Файл не передан'}), 400

    fb    = f.read()
    ftype = detect_file_type(f.filename, fb)

    if ftype == 'UNKNOWN':
        return jsonify({'error': f'Неизвестный формат: {f.filename}'}), 422

    device_types = _settings.get('device_types', DEFAULT_DEVICE_TYPES)
    try:
        rows = PARSERS[ftype](fb, device_types)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    # Типы приборов с интерфейсом, диапазоном адресов, комментариями и количеством
    from collections import defaultdict
    groups: dict = defaultdict(lambda: {
        'count': 0, 'with_comments': 0,
        'addr_min': None, 'addr_max': None,
    })
    for r in rows:
        if not r['kind_name']:
            continue
        key = (r.get('interface') or '—', r['kind_name'])
        g = groups[key]
        g['count'] += 1
        if r.get('comment', '').strip():
            g['with_comments'] += 1
        addr = r.get('network_addr', '').strip()
        if addr:
            try:
                n = int(addr)
                if g['addr_min'] is None or n < g['addr_min']:
                    g['addr_min'] = n
                if g['addr_max'] is None or n > g['addr_max']:
                    g['addr_max'] = n
            except (ValueError, TypeError):
                if g['addr_min'] is None or addr < str(g['addr_min']):
                    g['addr_min'] = addr
                if g['addr_max'] is None or addr > str(g['addr_max']):
                    g['addr_max'] = addr
    type_counts = [
        {'interface': iface, 'name': name,
         'count': g['count'], 'with_comments': g['with_comments'],
         'addr_min': g['addr_min'], 'addr_max': g['addr_max']}
        for (iface, name), g in sorted(groups.items())
    ]

    return jsonify({
        'filename':     f.filename,
        'file_type':    ftype,
        'label':        FILE_TYPE_LABELS.get(ftype, ftype),
        'count_kv':     sum(1 for r in rows if not r['is_vru']),
        'count_vru':    sum(1 for r in rows if r['is_vru']),
        'count_no_sn':  sum(1 for r in rows if r['serial'] == '-'),
        'total':        len(rows),
        'type_counts':  type_counts,
    })

# ─── Генерация export.xlsx ────────────────────────────────────────────────────

@app.route('/api/export', methods=['POST'])
def api_export():
    try:
        meta = json.loads(request.form.get('meta', '[]'))
    except Exception:
        return jsonify({'error': 'Некорректный JSON в meta'}), 400

    device_types  = _settings.get('device_types', DEFAULT_DEVICE_TYPES)
    files_by_name = {f.filename: f for f in request.files.getlist('files')}

    files_data = []
    for m in meta:
        fname = m.get('filename', '')
        uf    = files_by_name.get(fname)
        if not uf:
            return jsonify({'error': f'Файл не найден: {fname}'}), 400
        fb    = uf.read()
        ftype = detect_file_type(fname, fb)
        formula_overrides = m.get('formula_overrides', {})
        dt_for_file = merge_formula_overrides(device_types, formula_overrides) \
                      if formula_overrides else device_types
        try:
            rows = PARSERS[ftype](fb, dt_for_file)
        except Exception as e:
            return jsonify({'error': f'{fname}: {e}'}), 500

        files_data.append({
            'rows':        rows,
            'object_name': m.get('object_name', ''),
            'parent_id':   m.get('parent_id', ''),
        })

    out = generate_devices_export(files_data)
    return send_file(
        out,
        download_name='export.xlsx',
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )

# ─── Инфо об ids.xlsx (без генерации) ────────────────────────────────────────

@app.route('/api/ids-info', methods=['POST'])
def api_ids_info():
    f = request.files.get('ids')
    if not f:
        return jsonify({'error': 'Файл не передан'}), 400
    ids_bytes = f.read()
    try:
        xl      = pd.ExcelFile(io.BytesIO(ids_bytes))
        ld_list = get_ids_col(xl, 'LogicDevices', 'A')
        d_list  = get_ids_col(xl, 'Devices',      'A')
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify({
        'count':    len(ld_list),
        'd_count':  len(d_list),
        'mismatch': len(ld_list) != len(d_list),
    })

# ─── Тест формулы адресации ───────────────────────────────────────────────────

@app.route('/api/test-formula', methods=['POST'])
def api_test_formula():
    data    = request.get_json(force=True)
    formula = data.get('formula', 'ad')
    ad_raw  = data.get('ad', '0')
    try:
        from core.parsers import apply_formula
        result = apply_formula(formula, str(ad_raw))
        return jsonify({'result': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# ─── Генерация tags_to_load.xlsx ─────────────────────────────────────────────

@app.route('/api/tags', methods=['POST'])
def api_tags():
    f    = request.files.get('ids')
    tags = json.loads(request.form.get('tags', '[]'))

    if not f:
        return jsonify({'error': 'Файл ids.xlsx не передан'}), 400
    if not tags:
        return jsonify({'error': 'Не выбраны теги'}), 400

    ids_bytes = f.read()
    try:
        out = generate_tags(ids_bytes, tags)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    return send_file(
        out,
        download_name='tags_to_load.xlsx',
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )

# ─── Перезапуск ───────────────────────────────────────────────────────────────

@app.route('/api/restart', methods=['POST'])
def api_restart():
    def do_restart():
        import time
        time.sleep(0.4)
        os.execv(sys.executable, [sys.executable] + sys.argv)
    threading.Thread(target=do_restart, daemon=True).start()
    return jsonify({'ok': True})

# ─── Запуск ───────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    from waitress import serve
    port = int(os.environ.get('PORT', 5000))
    # Локальный запуск: открываем браузер автоматически
    if port == 5000:
        url = f'http://localhost:{port}'
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
        print(f'\n  УСПД Export Tool\n  → {url}\n')
        serve(app, host='127.0.0.1', port=port, threads=4)
    else:
        # Облачный запуск (Railway / Render): слушаем на 0.0.0.0
        print(f'\n  УСПД Export Tool  [cloud mode]\n  PORT={port}\n')
        serve(app, host='0.0.0.0', port=port, threads=4)
