

import argparse
import csv
import heapq
import os
import time
from pathlib import Path

from phonebook_utils import FIELD_LABELS, HEADER, column_from_key, is_descending_key, order_description, sort_key

USER_ENCODING = "utf-8-sig"
CHUNK_ENCODING = "utf-8-sig"


#записывает все helps файлы
def _flush_chunk(rows,chunk_index,column,descending,chunk_names):
    if not rows:
        return
    rows.sort(key=lambda r: sort_key(r, column), reverse=descending)
    name = f"hepl{chunk_index + 1}.txt"
    with open(name, "w", encoding=CHUNK_ENCODING, newline="") as f:
        writer = csv.writer(f, delimiter=",")
        writer.writerows(rows)
    chunk_names.append(name)

def _split_and_sort(input_path,column,descending,chunk_limit_bytes):
    chunk_names            = []
    current_rows                  = []
    current_bytes = 0
    chunk_index = 0
    total_data_rows = 0

    with input_path.open("r", encoding=USER_ENCODING, newline="") as f:
        reader = csv.reader(f, delimiter=",")
        try:
            header = next(reader)
        except StopIteration:
            return HEADER[:], [], 0

        for row in reader:
            if not row:
                continue
            row_bytes = sum(len(c.encode("utf-8")) for c in row) + len(row) + 1
            if current_rows and current_bytes + row_bytes > chunk_limit_bytes:
                _flush_chunk(current_rows, chunk_index, column, descending, chunk_names)
                chunk_index += 1
                current_rows = []
                current_bytes = 0
            current_rows.append(row)
            current_bytes += row_bytes
            total_data_rows += 1

    _flush_chunk(current_rows, chunk_index, column, descending, chunk_names)
    return header, chunk_names, total_data_rows

def _merge_chunks(chunk_names,output_path,header,column,descending):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    open_files = [open(name, "r", encoding=CHUNK_ENCODING, newline="") for name in chunk_names]
    readers = [csv.reader(f, delimiter=",") for f in open_files]

    class _Item:
        __slots__ = ("key_val", "row", "idx", "seq")

        def __init__(self, key_val, row, idx, seq):
            self.key_val = key_val
            self.row = row
            self.idx = idx
            self.seq = seq

        def __lt__(self, other):
            if self.key_val == other.key_val:
                return self.seq < other.seq
            return self.key_val > other.key_val if descending else self.key_val < other.key_val

    heap              = []
    sequence = 0

    for idx, reader in enumerate(readers):
        try:
            row = next(reader)
            heapq.heappush(heap, _Item(sort_key(row, column), row, idx, sequence))
            sequence += 1
        except StopIteration:
            pass

    with output_path.open("w", encoding=USER_ENCODING, newline="") as out_f:
        writer = csv.writer(out_f, delimiter=",")
        writer.writerow(header)
        while heap:
            item = heapq.heappop(heap)
            writer.writerow(item.row)
            try:
                row = next(readers[item.idx])
                heapq.heappush(heap, _Item(sort_key(row, column), row, item.idx, sequence))
                sequence += 1
            except StopIteration:
                pass

    for f in open_files:
        f.close()

def external_sort(input_path,output_path = "sorted.txt",key = 1,memory_ratio = 0.09):
    if not 0 < memory_ratio <= 0.10:
        raise ValueError("memory должен быть > 0 и <= 0.10")

    column = column_from_key(key)
    descending = is_descending_key(key)
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Файл не найден: {input_path}")

    original_cwd = os.getcwd()
    work_dir = str(input_path.resolve().parent)
    os.chdir(work_dir)

    file_size = input_path.stat().st_size
    chunk_limit = max(1, int(file_size * memory_ratio))
    chunk_names            = []
    split_started = time.perf_counter()

    try:
        header, chunk_names, total_rows = _split_and_sort(input_path, column, descending, chunk_limit)
        split_finished = time.perf_counter()
        _merge_chunks(chunk_names, output_path, header, column, descending)
        merge_finished = time.perf_counter()
    finally:
        for name in chunk_names:
            try:
                os.remove(name)
            except FileNotFoundError:
                pass
        os.chdir(original_cwd)

    return {
        "input": str(input_path),
        "output": str(output_path),
        "key": int(key),
        "field": FIELD_LABELS[column],
        "order": order_description(key),
        "descending": int(descending),
        "file_size_bytes": int(file_size),
        "chunk_limit_bytes": int(chunk_limit),
        "chunks": int(len(chunk_names)),
        "split_sort_seconds": split_finished - split_started,
        "merge_seconds": merge_finished - split_finished,
        "total_seconds": merge_finished - split_started,
    }

def check_sorted(path,key = 1,max_rows = None):
    column = column_from_key(key)
    descending = is_descending_key(key)
    previous_key      = None
    previous_row_number = 0
    checked = 0

    with Path(path).open("r", encoding=USER_ENCODING, newline="") as f:
        reader = csv.reader(f, delimiter=",")
        try:
            next(reader)
        except StopIteration:
            return True, "Файл пустой или содержит только заголовок."

        for row_number, row in enumerate(reader, start=2):
            current_key = sort_key(row, column)
            if previous_key is not None:
                bad_asc = not descending and previous_key > current_key
                bad_desc = descending and previous_key < current_key
                if bad_asc or bad_desc:
                    return (
                        False,
                        f"Нарушен порядок ({order_description(key)}): "
                        f"строки {previous_row_number} и {row_number}. "
                        f"Ключи: {previous_key!r} -> {current_key!r}",
                    )
            previous_key = current_key
            previous_row_number = row_number
            checked += 1
            if max_rows is not None and checked >= max_rows:
                break

    return True, f"Проверено строк: {checked}. Нарушений сортировки не найдено."

def sort_all(key):
    external_sort("data.csv", "sorted.txt", key=key, memory_ratio=0.09)
    with open("sorted.txt", "r", encoding=USER_ENCODING, newline="") as f:
        return max(0, sum(1 for _ in f) - 1)

def _parse_args():
    parser = argparse.ArgumentParser(description="Внешняя сортировка data.csv для справочника телефонов.")
    parser.add_argument("--input", default="data.csv", help="Входной CSV-файл.")
    parser.add_argument("--output", default="sorted.txt", help="Файл результата.")
    parser.add_argument("--key", type=int, default=1, help="1..5/-1..-5.")
    parser.add_argument("--memory", type=float, default=0.09, help="Memory процент.")
    parser.add_argument("--check", action="store_true", help="Проверить результат после сортировки.")
    return parser.parse_args()

def main():
    args = _parse_args()
    stats = external_sort(args.input, args.output, key=args.key, memory_ratio=args.memory_ratio)
    print("Python external sort finished")
    print(f"Input:       {stats['input']}")
    print(f"Output:      {stats['output']}")
    print(f"Field:       {stats['field']}")
    print(f"Order:       {stats['order']}")
    print(f"File size:   {stats['file_size_bytes'] / 1024 / 1024:.2f} MiB")
    print(f"Chunks:      {stats['chunks']}")
    print(f"Total:       {stats['total_seconds']:.2f} sec")
    if args.check:
        ok, message = check_sorted(args.output, key=args.key)
        print(("OK: " if ok else "ERROR: ") + message)


if __name__ == "__main__":
    main()
