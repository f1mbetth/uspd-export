"""
Реестр типов приборов учёта.
Правило адресации задаётся формулой: ad → k (номер квартиры).
  ad — сетевой адрес из файла выгрузки (int или str)
  k  — результат формулы (номер квартиры)
"""

# Типы приборов по умолчанию
DEFAULT_DEVICE_TYPES: list[dict] = [
    {
        "type_name": "Меркурий 200",
        "is_vru":    False,
        "formula":   'ad.replace("kv", "")',
        "notes":     "RTU / Smart rev.1, однофазный",
    },
    {
        "type_name": "Меркурий 230",
        "is_vru":    True,
        "formula":   'ad',
        "notes":     "RTU / Smart rev.1, трёхфазный ВРУ",
    },
    {
        "type_name": "Пульсар 1ф4т",
        "is_vru":    False,
        "formula":   'ad',
        "notes":     "Smart rev.2, однофазный",
    },
    {
        "type_name": "Пульсар 3ф4т",
        "is_vru":    True,
        "formula":   'ad',
        "notes":     "Smart rev.2, трёхфазный ВРУ",
    },
    {
        "type_name": "Э/сч Пульсар 1Ф",
        "is_vru":    False,
        "formula":   'ad',
        "notes":     "Smart rev.3, однофазный",
    },
    {
        "type_name": "Э/сч Пульсар 3Ф",
        "is_vru":    True,
        "formula":   'ad',
        "notes":     "Smart rev.3, трёхфазный ВРУ",
    },
    {
        "type_name": "Счетчики СПОДЭС",
        "is_vru":    False,
        "formula":   'ad - 2000',
        "notes":     "Smart rev.2 текущий, DLMS/СПОДЭС",
    },
    {
        "type_name": "Меркурий 206",
        "is_vru":    False,
        "formula":   '(ad - 4194304011) // 8 + 1',
        "notes":     "DLMS, специальная адресация",
    },
]


# ─── Обратная совместимость: старый addr_rule → формула ──────────────────────

_RULE_TO_FORMULA: dict[str, str] = {
    "kv":        'ad.replace("kv", "")',
    "direct":    'ad',
    "auto_base": 'ad - 2000',
}

def rule_to_formula(rule: str) -> str:
    """Конвертирует старый addr_rule в формулу (для существующих settings.json)."""
    return _RULE_TO_FORMULA.get(rule, 'ad')
