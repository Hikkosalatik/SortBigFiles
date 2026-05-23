
import argparse
import csv
import os
import random
import time
from datetime import date, timedelta
from pathlib import Path

from phonebook_utils import HEADER

SURNAMES = [
    "Иванов", "Петров", "Сидоров", "Смирнов", "Кузнецов", "Попов", "Соколов",
    "Лебедев", "Козлов", "Новиков", "Морозов", "Волков", "Соловьев", "Васильев",
    "Зайцев", "Павлов", "Семенов", "Голубев", "Виноградов", "Богданов",
    "Воробьев", "Федоров", "Михайлов", "Беляев", "Тарасов", "Белов", "Комаров",
    "Орлов", "Киселев", "Макаров", "Андреев", "Ковалев", "Ильин", "Гусев",
    "Титов", "Кузьмин", "Кудрявцев", "Баранов", "Куликов", "Алексеев",
    "Степанов", "Яковлев", "Сорокин", "Сергеев", "Романов", "Захаров",
    "Борисов", "Королев", "Герасимов", "Пономарев", "Григорьев", "Лазарев",
    "Медведев", "Ершов", "Никитин", "Соболев", "Рябов", "Поляков", "Цветков",
    "Данилов", "Жуков", "Фролов", "Журавлев", "Николаев", "Крылов", "Максимов",
    "Сидоренко", "Осипов", "Белоусов", "Фомин", "Дорофеев", "Егоров", "Матвеев",
    "Бобров", "Дмитриев", "Калинин", "Анисимов", "Петухов", "Антонов", "Тимофеев",
    "Никифоров", "Веселов", "Филиппов", "Марков", "Большаков", "Суханов",
    "Миронов", "Ширяев", "Александров", "Коновалов", "Шестаков", "Казаков",
    "Ефимов", "Денисов", "Громов", "Фокин", "Блинов", "Лапин", "Прохоров",
    "Зарубин",
]

INITIALS = list("АБВГДЕЖЗИКЛМНОПРСТУФХЭЮЯ")
MOBILE_PREFIXES = ["700", "701", "702", "705", "707", "708", "738", "747", "771", "775", "776", "777", "778"]

def random_fio(rng):
    return f"{rng.choice(SURNAMES)} {rng.choice(INITIALS)}.{rng.choice(INITIALS)}."

def random_birth_date(rng):
    start = date(1950, 1, 1)
    end = date(2007, 12, 31)
    return (start + timedelta(days=rng.randint(0, (end - start).days))).isoformat()


def random_home_phone(rng): #без маски 
    return str(rng.randint(2, 9)) + "".join(str(rng.randint(0, 9)) for _ in range(7))


def random_mobile_phone(rng): #без маски
    return "+7" + rng.choice(MOBILE_PREFIXES) + "".join(str(rng.randint(0, 9)) for _ in range(7))

def random_row(rng):
    phone_type = "сотовый" if rng.random() < 0.65 else "домашний"
    phone = random_mobile_phone(rng) if phone_type == "сотовый" else random_home_phone(rng)
    blocked = "Да" if rng.random() < 0.10 else "Нет"
    return [random_fio(rng), random_birth_date(rng), phone_type, phone, blocked]

def generate_csv(output_path = "data.csv",target_bytes = None,records = None,seed = None,progress_callback = None):
    if target_bytes is None and records is None:
        target_bytes = int(1.1 * 1024 * 1024 * 1024)

    rng = random.Random(seed)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    size_now = 0
    last_progress_time = time.perf_counter()

    with output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=",")
        writer.writerow(HEADER)

        while True:
            if records is not None and count >= records:
                break
            if target_bytes is not None and size_now >= target_bytes:
                break

            writer.writerow(random_row(rng))
            count += 1

            if count % 10000 == 0:
                f.flush()
                size_now = output.stat().st_size
                now = time.perf_counter()
                if progress_callback and now - last_progress_time >= 1.0:
                    progress_callback(count, size_now)
                    last_progress_time = now

        f.flush()
        size_now = output.stat().st_size
        if progress_callback:
            progress_callback(count, size_now)

    return count

def generate(size_gb = 1.1):
    if size_gb <= 0:
        raise ValueError("Размер должен быть больше 0")
    return generate_csv("data.csv", target_bytes=int(size_gb * 1024 * 1024 * 1024))


def _parse_args(): #разбирает аргументы командной строки для запуска генератора напрямую
    parser = argparse.ArgumentParser(description="Генератор data.csv для справочника телефонов.")
    parser.add_argument("--output", default="data.csv", help="Имя выходного CSV-файла.")
    parser.add_argument("--size-gb", type=float, default=1.1, help="Размер файла в ГиБ.")
    parser.add_argument("--size-mb", type=float, default=None, help="Размер файла в МиБ, перекрывает --size-gb.")
    parser.add_argument("--records", type=int, default=None, help="Точное количество строк вместо размера.")
    parser.add_argument("--seed", type=int, default=None, help="Seed для повторяемой генерации.")
    return parser.parse_args()

def main():
    args = _parse_args()
    if args.records is not None:
        target = None
    elif args.size_mb is not None:
        target = int(args.size_mb * 1024 * 1024)
    else:
        target = int(args.size_gb * 1024 * 1024 * 1024)

    def progress(rows, bytes_written):
        print(f"Генерация: {rows:,} строк, {bytes_written / 1024 / 1024:.1f} MiB", end="\r", flush=True)

    started = time.perf_counter()
    rows = generate_csv(args.output, target_bytes=target, records=args.records, seed=args.seed, progress_callback=progress)
    elapsed = time.perf_counter() - started
    size = Path(args.output).stat().st_size / 1024 / 1024
    print()
    print(f"Файл создан: {args.output}")
    print(f"Строк: {rows:,}")
    print(f"Размер: {size:.2f} MiB")
    print(f"Время: {elapsed:.2f} сек")


if __name__ == "__main__":
    main()
