"""
Загрузка и сохранение настроек приложения (settings.json).
"""

import json
import os

from config.profiles  import DEFAULT_DEVICE_TYPES
from config.tag_types import DEFAULT_TAG_TYPES

# settings.json лежит рядом с app.py (на уровень выше этого файла)
_HERE         = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.normpath(os.path.join(_HERE, "..", "settings.json"))

DEFAULT_SETTINGS: dict = {
    "device_types": DEFAULT_DEVICE_TYPES,
    "tag_types":    DEFAULT_TAG_TYPES,
}


def load_settings() -> dict:
    """Читает settings.json; если файл отсутствует — возвращает умолчания."""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            # Добиваем отсутствующие ключи значениями по умолчанию
            for key, val in DEFAULT_SETTINGS.items():
                if key not in data:
                    data[key] = val
            return data
        except Exception:
            pass
    # Возвращаем deep-copy умолчаний
    return {k: list(v) if isinstance(v, list) else v
            for k, v in DEFAULT_SETTINGS.items()}


def save_settings(settings: dict) -> None:
    """Сохраняет настройки в settings.json."""
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
