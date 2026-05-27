"""
Парсеры входных файлов выгрузок УСПД.

Поддерживаемые форматы:
  RTU          — УМ-31 RTU / Smart rev.1 (.xls, лист ReportUm40RtuData)
  REV2_DAILY   — Smart rev.2, суточный (.xlsx, лист «На начало суток»)
  REV2_CURRENT — Smart rev.2, текущий (.xlsx, лист «Показания энергии»)
  REV3         — Smart rev.3 (.xlsx, лист Data)

Каждый парсер возвращает list[dict] с ключами:
  serial, kind_name, interface, network_addr, apt_num, is_vru, comment
"""

import io
import warnings
import xlrd
import pandas as pd

from config.profiles import rule_to_formula


# ─── Вспомогательные функции ──────────────────────────────────────────────────

def fmt_serial(raw) -> str:
    """NaN / пустое → '-', иначе строка минимум 8 символов с ведущими нулями."""
    if raw is None:
        return "-"
    s = str(raw).strip()
    if not s or s in ("nan", "None", ""):
        return "-"
    try:
        return str(int(float(s))).zfill(8)
    except Exception:
        return s


def fmt_comment(raw) -> str:
    """Возвращает строку комментария или пустую строку."""
    if raw is None:
        return ""
    s = str(raw).strip()
    return "" if s in ("nan", "None", "") else s


def detect_file_type(filename: str, file_bytes: bytes) -> str:
    """RTU | REV2_DAILY | REV2_CURRENT | REV3 | UNKNOWN"""
    if filename.lower().endswith(".xls"):
        return "RTU"
    try:
        xl     = pd.ExcelFile(io.BytesIO(file_bytes))
        sheets = xl.sheet_names
        if "На начало суток"   in sheets: return "REV2_DAILY"
        if "Показания энергии" in sheets: return "REV2_CURRENT"
        if "Data"              in sheets: return "REV3"
    except Exception:
        pass
    return "UNKNOWN"


def lookup_device(type_name: str, device_types: list) -> dict | None:
    """
    Ищет запись в реестре типов приборов по вхождению подстроки.
    Возвращает первое совпадение или None.
    """
    for dt in device_types:
        reg = dt.get("type_name", "").strip()
        if reg and (reg == type_name or reg in type_name or type_name in reg):
            return dt
    return None


def get_formula(dt: dict) -> str:
    """
    Возвращает формулу из записи реестра.
    Поддерживает старый формат (addr_rule) для обратной совместимости.
    """
    if "formula" in dt and dt["formula"]:
        return dt["formula"]
    if "addr_rule" in dt:
        return rule_to_formula(dt["addr_rule"])
    return "ad"


def apply_formula(formula: str, ad_raw) -> str:
    """
    Вычисляет номер квартиры по формуле.

    Переменная ad в формуле — это сетевой адрес:
      - целое число, если адрес числовой (2001, 4194304011, ...)
      - строка, если адрес содержит буквы (kv1, kv42, ...)

    Специальные значения:
      __comment__  → номер квартиры берётся из поля Комментарий (обрабатывается в export_gen)

    Примеры формул:
      ad                          → копировать адрес как есть
      ad - 2000                   → СПОДЭС (2001 → 1)
      ad.replace("kv", "")        → Меркурий 200 (kv1 → 1)
      (ad - 4194304011) // 8 + 1  → Меркурий 206
    """
    if formula.strip() == '__comment__':
        return ''   # номер квартиры будет взят из comment в export_gen

    ad_str = str(ad_raw).strip()
    # Пробуем преобразовать в целое
    try:
        ad = int(ad_str)
    except (ValueError, TypeError):
        ad = ad_str

    try:
        result = eval(formula.strip(), {"__builtins__": {}}, {"ad": ad})
        # Убираем дробную часть если она нулевая
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return str(result).strip()
    except Exception:
        return ad_str   # fallback: копируем адрес в квартиру


def _row(serial, kind_name, interface, network_addr,
         apt_num, is_vru, comment="") -> dict:
    return {
        "serial":       serial,
        "kind_name":    kind_name,
        "interface":    interface,
        "network_addr": network_addr,
        "apt_num":      apt_num,
        "is_vru":       is_vru,
        "comment":      comment,
    }


# ─── Парсеры ──────────────────────────────────────────────────────────────────

_FALLBACK_3PH = ["3ф", "3Ф", "Меркурий 230"]


def parse_rtu(file_bytes: bytes, device_types: list) -> list:
    """
    RTU / Smart rev.1 (.xls)
    Лист: ReportUm40RtuData
    Строки: 0=пусто, 1=заголовки, 2+=данные
    Столбцы (индексы): 2=Модель, 3=Интерфейс, 4=Адрес, 5=Сер.номер
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = xlrd.open_workbook(file_contents=file_bytes)
    sh   = wb.sheet_by_name("ReportUm40RtuData")
    rows = []
    for r in range(2, sh.nrows):
        v         = [sh.cell_value(r, c) for c in range(sh.ncols)]
        serial    = fmt_serial(v[5])
        model     = str(v[2]).strip()
        interface = str(v[3]).strip()
        addr      = str(v[4]).strip()

        dt = lookup_device(model, device_types)
        if dt:
            is_vru = dt["is_vru"]
            if is_vru:
                apt = None
            else:
                apt = apply_formula(get_formula(dt), addr)
        else:
            # Fallback: kv-префикс = квартира, иначе ВРУ
            if addr.lower().startswith("kv"):
                apt, is_vru = apply_formula('ad.replace("kv", "")', addr), False
            else:
                apt, is_vru = None, True

        rows.append(_row(serial, model, interface, addr, apt, is_vru))
    return rows


def parse_rev2_daily(file_bytes: bytes, device_types: list) -> list:
    """
    Smart rev.2 — суточный (лист «На начало суток»)
    Колонки: ID | Шаблон | Тип прибора учета | Сетевой адрес |
             Интерфейс | Комментарий | Серийный номер | ...
    """
    df   = pd.read_excel(io.BytesIO(file_bytes), sheet_name="На начало суток", header=0)
    rows = []
    for _, row in df.iterrows():
        serial    = fmt_serial(row.get("Серийный номер"))
        type_name = str(row.get("Тип прибора учета", "")).strip()
        interface = str(row.get("Интерфейс", "")).strip()
        comment   = fmt_comment(row.get("Комментарий"))
        addr_raw  = row.get("Сетевой адрес")
        try:    addr_int = int(float(addr_raw))
        except: continue

        dt = lookup_device(type_name, device_types)
        if dt:
            is_vru = dt["is_vru"]
            apt    = None if is_vru else apply_formula(get_formula(dt), addr_int)
        else:
            is_vru = any(p in type_name for p in _FALLBACK_3PH)
            apt    = None if is_vru else str(addr_int)

        rows.append(_row(serial, type_name, interface, str(addr_int), apt, is_vru, comment))
    return rows


def parse_rev2_current(file_bytes: bytes, device_types: list) -> list:
    """
    Smart rev.2 — текущий (лист «Показания энергии»)
    Колонки: ID | Статус | Шаблон | Тип прибора учета | Сетевой адрес |
             Интерфейс | Комментарий | Серийный номер | ...
    """
    df   = pd.read_excel(io.BytesIO(file_bytes), sheet_name="Показания энергии", header=0)
    rows = []
    for _, row in df.iterrows():
        serial    = fmt_serial(row.get("Серийный номер"))
        type_name = str(row.get("Тип прибора учета", "")).strip()
        interface = str(row.get("Интерфейс", "")).strip()
        comment   = fmt_comment(row.get("Комментарий"))
        addr_raw  = row.get("Сетевой адрес")
        try:    addr_int = int(float(addr_raw))
        except: continue

        dt = lookup_device(type_name, device_types)
        if dt:
            is_vru = dt["is_vru"]
            apt    = None if is_vru else apply_formula(get_formula(dt), addr_int)
        else:
            # Неизвестный прибор → копируем адрес
            is_vru = False
            apt    = str(addr_int)

        rows.append(_row(serial, type_name, interface, str(addr_int), apt, is_vru, comment))
    return rows


def parse_rev3(file_bytes: bytes, device_types: list) -> list:
    """
    Smart rev.3 (.xlsx, лист Data)
    Колонки: ID | Тип прибора учёта | Сетевой адрес | Интерфейс |
             Серийный номер | Метка времени | ... | Комментарий
    """
    df = pd.read_excel(io.BytesIO(file_bytes), sheet_name="Data", header=0)

    def find(kws):
        for c in df.columns:
            if any(k.lower() in c.lower() for k in kws):
                return c
        return None

    type_col    = find(["тип прибора"])
    addr_col    = find(["сетевой адрес"])
    iface_col   = find(["интерфейс"])
    serial_col  = find(["серийный номер"])
    comment_col = find(["комментарий"])
    if not all([type_col, addr_col, iface_col, serial_col]):
        raise ValueError("Не найдены обязательные столбцы в листе Data")

    rows = []
    for _, row in df.iterrows():
        serial    = fmt_serial(row.get(serial_col))
        type_name = str(row.get(type_col, "")).strip()
        interface = str(row.get(iface_col, "")).strip()
        comment   = fmt_comment(row.get(comment_col)) if comment_col else ""
        addr_raw  = row.get(addr_col)
        try:    addr_int = int(float(addr_raw))
        except: continue

        dt = lookup_device(type_name, device_types)
        if dt:
            is_vru = dt["is_vru"]
            apt    = None if is_vru else apply_formula(get_formula(dt), addr_int)
        else:
            is_vru = any(p in type_name for p in ["3Ф", "3ф"])
            apt    = None if is_vru else str(addr_int)

        rows.append(_row(serial, type_name, interface, str(addr_int), apt, is_vru, comment))
    return rows


def merge_formula_overrides(device_types: list, overrides: dict) -> list:
    """
    Применяет пользовательские формулы (из вкладки Экспорт) к реестру приборов.
    overrides: {type_name: formula}
    Не изменяет оригинальный список — возвращает новый.
    """
    result = [dict(dt) for dt in device_types]
    for type_name, formula in overrides.items():
        dt = next(
            (d for d in result if
             d["type_name"] == type_name or
             d["type_name"] in type_name or
             type_name in d["type_name"]),
            None,
        )
        if dt:
            dt["formula"] = formula
        else:
            result.append({
                "type_name": type_name,
                "is_vru":    False,
                "formula":   formula,
                "notes":     "",
            })
    return result


FILE_TYPE_LABELS: dict[str, str] = {
    "RTU":          "УМ-31 RTU / Smart rev.1",
    "REV2_DAILY":   "Smart rev.2 (суточный)",
    "REV2_CURRENT": "Smart rev.2 (текущий)",
    "REV3":         "Smart rev.3",
    "UNKNOWN":      "Неизвестный формат",
}

PARSERS: dict = {
    "RTU":          parse_rtu,
    "REV2_DAILY":   parse_rev2_daily,
    "REV2_CURRENT": parse_rev2_current,
    "REV3":         parse_rev3,
}
