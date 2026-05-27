"""
Генерация файла экспорта устройств (export.xlsx).
Два листа: LogicDevices и Devices — в формате импорта АСКУЭ.
"""

import io
from openpyxl import Workbook


def generate_devices_export(files_data: list) -> io.BytesIO:
    """
    files_data: list of dicts —
        {"rows": list[dict], "object_name": str, "parent_id": str}

    Каждый row в rows:
        serial, kind_name, interface, network_addr, apt_num, is_vru, comment

    Приоритет имени квартиры:
      1. comment (если заполнен в файле выгрузки)
      2. apt_num (вычисленный по формуле)

    Возвращает BytesIO с готовым .xlsx.
    """
    wb   = Workbook()
    ws_l = wb.active;  ws_l.title = "LogicDevices"
    ws_d = wb.create_sheet("Devices")

    # ── Шапка LogicDevices (2 пустые строки + 3 строки заголовков) ───────────
    ws_l.append([None] * 9)
    ws_l.append([None] * 9)
    ws_l.append(["Name", "Type:Code", "Kind:Name", "Int", "Addr",
                 "CountNo", "ID", "number_kv", "Object:Name"])
    ws_l.append(["Имя", "Тип:Код", "Вид:Имя", "Физический интерфейс",
                 "Сетевой адрес", "Номер счетчика", "Идентификатор прибора",
                 "Номер квартиры", "Объект:Имя"])
    ws_l.append([1, 2, 3, 4, 5, 6, 7, 8, 9])

    # ── Шапка Devices ─────────────────────────────────────────────────────────
    ws_d.append([None] * 7)
    ws_d.append([None] * 7)
    ws_d.append(["Name", "Type:Code", "Type:Name", "SerialNo",
                 "Scid", "Object:Name", "Parent:Id"])
    ws_d.append(["Имя", "Тип:Код", "Тип:Имя", "Серийный номер",
                 "Идентификатор", "Объект:Имя",
                 "Корневое устройство:Идентификатор"])
    ws_d.append([1, 2, 3, 4, 5, 6, 7])

    global_id = 1
    for fd in files_data:
        obj_name  = fd["object_name"]
        parent_id = fd["parent_id"]
        for row in fd["rows"]:
            serial  = row["serial"]
            comment = row.get("comment", "").strip()

            if row["is_vru"]:
                num_kv = "ВРУ"
            elif comment:
                num_kv = comment          # комментарий перекрывает номер квартиры
            elif row["apt_num"]:
                num_kv = row["apt_num"]
            else:
                num_kv = "—"             # шаблон __comment__, но комментарий пуст

            name = f"{num_kv} ({serial})"

            ws_l.append([
                name, "EMeter", row["kind_name"],
                row["interface"], row["network_addr"],
                serial, global_id, num_kv, obj_name,
            ])
            ws_d.append([
                name, "EMeter", "Электросчетчик",
                serial, global_id, obj_name, parent_id,
            ])
            global_id += 1

    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return out
