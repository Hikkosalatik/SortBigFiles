

HEADER = ["fio", "birth_date", "phone_type", "phone_number_raw", "blocked"]

FIELD_LABELS = {
    1: "ФИО",
    2: "Дата рождения",
    3: "Тип телефона",
    4: "Номер телефона без маски",
    5: "Заблокирован",
}

def digits_only(value):
    return "".join(ch for ch in str(value) if ch.isdigit())

# преобразует номер телефона
def normalize_phone_key(value):
    digits = digits_only(value)
    stripped = digits.lstrip("0") or "0"
    return len(stripped), stripped

def blocked_to_int(value):
    v = str(value).strip().lower()
    return 1 if v in {"да", "1", "true", "yes", "y", "blocked"} else 0

def column_from_key(key):
    column = abs(int(key))
    if column < 1 or column > 5:
        raise ValueError("Ключ сортировки должен быть от 1 до 5 или от -1 до -5")
    return column

def is_descending_key(key):
    column = column_from_key(key)
    if column == 5:
        return int(key) > 0
    return int(key) < 0

def order_description(key):
    column = column_from_key(key)
    if column == 3:
        return "сначала домашний" if int(key) > 0 else "сначала сотовый"
    if column == 5:
        return "сначала Да" if int(key) > 0 else "сначала Нет"
    return "по убыванию" if int(key) < 0 else "по возрастанию"

def sort_key(row, column):
    index = int(column) - 1
    value = row[index].strip() if index < len(row) else ""
    if column == 4:
        return normalize_phone_key(value)
    if column == 5:
        return blocked_to_int(value)
    return value

# форматирование номера телефона
def mask_phone(phone_type, raw_number):
    digits = digits_only(raw_number)
    phone_type = (phone_type or "").strip().lower()
    if phone_type.startswith("дом"):
        if len(digits) == 8:
            return f"{digits[0]}-{digits[1:4]}-{digits[4:]}"
        if len(digits) == 7:
            return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
        return raw_number
    if len(digits) == 11 and digits.startswith("7"):
        return f"+7-{digits[1:4]}-{digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
    if len(digits) == 10:
        return f"+7-{digits[:3]}-{digits[3:6]}-{digits[6:8]}-{digits[8:10]}"
    return raw_number

def row_to_preview(row):
    values = list(row) + [""] * (5 - len(row))
    fio, birth_date, phone_type, raw_phone, blocked = values[:5]
    return (
        f"{fio} | {birth_date} | {phone_type} | "
        f"хранится: {raw_phone} | отображается: {mask_phone(phone_type, raw_phone)} | "
        f"заблокирован: {blocked}"
    )
