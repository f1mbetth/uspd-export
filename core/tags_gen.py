"""
Генерация файла тегов (tags_to_load.xlsx).
Читает ids.xlsx (два листа: LogicDevices и Devices),
для каждого устройства создаёт по одной строке на каждый выбранный тег.
"""

import io
import pandas as pd


def get_ids_col(xl, sheet: str, col: str, skip: int = 3) -> list:
    """
    Читает один столбец из Excel-файла.
    skip — сколько строк пропустить в начале после dropna()
           (в ids.xlsx первые 3 строки — заголовочные).
    """
    return (
        pd.read_excel(xl, sheet_name=sheet, usecols=col)
        .squeeze()
        .dropna()
        .tolist()[skip:]
    )


def generate_tags(ids_bytes: bytes, selected_tags: list) -> io.BytesIO:
    """
    ids_bytes     — содержимое ids.xlsx
    selected_tags — список кодов тегов, например ['A+0', 'A+1', 'DA+0']

    Возвращает BytesIO с tags_to_load.xlsx.
    Структура совместима с оригинальными скриптами !Tags*.py.
    """
    xl      = pd.ExcelFile(io.BytesIO(ids_bytes))
    ld_list = get_ids_col(xl, "LogicDevices", "A")
    d_list  = get_ids_col(xl, "Devices",      "A")

    # Заголовочные строки (как в оригинальных скриптах)
    md1 = ["Тег оборудования:Код",       1]
    md2 = ["Тег устройства:Код",          2]
    md3 = ["Подсистема:Имя",              3]
    md4 = ["Оборудование:Идентификатор",  4]
    md5 = ["Устройство:Идентификатор",    5]

    for ld, d in zip(ld_list, d_list):
        for tag in selected_tags:
            md1.append(tag)
            md2.append(tag)
            md3.append("Мониторинг")
            md4.append(ld)
            md5.append(d)

    df = pd.DataFrame({
        "LogicTag:Code":  md1,
        "DeviceTag:Code": md2,
        "SubSystem:Name": md3,
        "LogicDevice:Id": md4,
        "Device:Id":      md5,
    })

    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Tags", index=False, startrow=2)
    out.seek(0)
    return out
