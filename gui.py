
import csv
import ctypes
import os
import queue
import threading
import time
import traceback
from collections import deque
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from external_sort import USER_ENCODING, check_sorted, external_sort
from generator import generate_csv
from phonebook_utils import FIELD_LABELS, HEADER, order_description, row_to_preview

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data.csv"
SORTED_FILE = BASE_DIR / "sorted.txt"
DLL_FILE = BASE_DIR / "sorter.dll"
LOG_FILE = BASE_DIR / "cpp_sort_log.txt"

os.chdir(BASE_DIR)


class PrintRedirector:
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, text):
        if self.text_widget is not None and text:
            self.text_widget.insert(tk.END, text)
            self.text_widget.see(tk.END)

    def flush(self):
        pass


def load_cpp_dll():
    if not DLL_FILE.exists():
        return None, "sorter.dll не найден"
    try:
        dll = ctypes.CDLL(str(DLL_FILE))
        dll.sort_file.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
        dll.sort_file.restype = ctypes.c_int
        return dll, "DLL загружена успешно."
    except Exception as exc:
        return None, f"sorter.dll найден, но не загрузился: {exc}"

def file_size_text(path):
    if not path.exists():
        return "файл отсутствует"
    size = path.stat().st_size
    if size >= 1024 ** 3:
        return f"{size / 1024 ** 3:.2f} ГБ"
    if size >= 1024 ** 2:
        return f"{size / 1024 ** 2:.2f} МБ"
    return f"{size / 1024:.2f} КБ"

def count_rows(path): #количество строк в файле
    if not path.exists():
        return 0
    with path.open("r", encoding=USER_ENCODING, newline="") as f:
        return max(0, sum(1 for _ in f) - 1)

def read_head_rows(path, rows_count):
    rows                  = []
    with path.open("r", encoding=USER_ENCODING, newline="") as f:
        reader = csv.reader(f, delimiter=",")
        for row in reader:
            rows.append(row)
            if len(rows) >= rows_count:
                break
    return rows
def read_range_rows(path, row_from, row_to):
    rows = []
    with path.open("r", encoding=USER_ENCODING, newline="") as f:
        reader = csv.reader(f, delimiter=",")
        for i, row in enumerate(reader):
            if i == 0:
                rows.append(row)
                continue
            if i >= row_from and i <= row_to:
                rows.append(row)
            if i > row_to:
                break
    return rows
def read_tail_rows(path, rows_count):
    tail                   = deque(maxlen=rows_count)
    with path.open("r", encoding=USER_ENCODING, newline="") as f:
        reader = csv.reader(f, delimiter=",")
        for row in reader:
            tail.append(row)
    return list(tail)

def format_preview(rows):
    if not rows:
        return "Нет строк для вывода."
    lines            = []
    for i, row in enumerate(rows, start=1):
        if row == HEADER:
            lines.append(",".join(row))
        else:
            lines.append(f"{i:>4}: {row_to_preview(row)}")
    return "\n".join(lines)


class PhonebookApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Сортировка — Справочник телефонов")
        self.geometry("1000x850")
        self.minsize(950, 650)

        self.messages                        = queue.Queue()
        self.cpp_dll, self.dll_status = load_cpp_dll()
        self.busy = False

        self._build_ui()
        self._poll_messages()

    def _build_ui(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)

        gen_frame = ttk.LabelFrame(main_frame, text="Генерация CSV файла", padding="10")
        gen_frame.grid(row=0, column=0, columnspan=3, sticky="ew", pady=5)

        self.size_var = tk.DoubleVar(value=0.10)
        self.seed_var = tk.StringVar(value="1")

        ttk.Label(gen_frame, text="Размер файла (ГБ):").pack(side="left", padx=5)
        ttk.Spinbox(gen_frame, from_=0.01, to=10.0, increment=0.10,textvariable=self.size_var, width=10).pack(side="left", padx=5)
        ttk.Label(gen_frame, text="По отчету от 1гб").pack(side="left", padx=5)
        ttk.Label(gen_frame, text="Seed:").pack(side="left", padx=(20, 5))
        ttk.Entry(gen_frame, width=10, textvariable=self.seed_var).pack(side="left", padx=5)

        self.gen_btn = ttk.Button(gen_frame, text="Сгенерировать", command=self.generate_file)
        self.gen_btn.pack(side="right", padx=10)

        sort_frame = ttk.LabelFrame(main_frame, text="Сортировка", padding="10")
        sort_frame.grid(row=1, column=0, columnspan=3, sticky="ew", pady=5)

        ttk.Label(sort_frame, text="Метод:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.method_var = tk.StringVar(value="cpp" if self.cpp_dll is not None else "python")
        ttk.Radiobutton(sort_frame, text="Python", variable=self.method_var, value="python").grid(row=0, column=1, sticky="w")
        self.cpp_k = ttk.Radiobutton(sort_frame, text="C++ (DLL)", variable=self.method_var, value="cpp")
        self.cpp_k.grid(row=0, column=2, sticky="w")
        if self.cpp_dll is None:
            self.cpp_k.state(["disabled"])

        ttk.Label(sort_frame, text="Столбец:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.column_var = tk.IntVar(value=1)
        col_frame = ttk.Frame(sort_frame)
        col_frame.grid(row=1, column=1, columnspan=5, sticky="w")
        for i in range(1, 6):
            ttk.Radiobutton(col_frame,text=f"{i}: {FIELD_LABELS[i]}",variable=self.column_var,value=i,command=self.update_order_controls,).pack(side="left", padx=5)

        ttk.Label(sort_frame, text="Порядок:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.order_frame = ttk.Frame(sort_frame)
        self.order_frame.grid(row=2, column=1, columnspan=5, sticky="w")

        self.order_var = tk.StringVar(value="asc")
        self.phone_type_order_var = tk.StringVar(value="home_first")
        self.blocked_order_var = tk.StringVar(value="yes_first")

        self.asc_k = ttk.Radiobutton(self.order_frame, text="По возрастанию", variable=self.order_var, value="asc")
        self.desc_k = ttk.Radiobutton(self.order_frame, text="По убыванию", variable=self.order_var, value="desc")
        self.home_first_k = ttk.Radiobutton(self.order_frame, text="Сначала Домашний", variable=self.phone_type_order_var, value="home_first")
        self.mobile_first_k = ttk.Radiobutton(self.order_frame, text="Сначала Сотовый", variable=self.phone_type_order_var, value="mobile_first")
        self.yes_first_k = ttk.Radiobutton(self.order_frame, text="Сначала Да", variable=self.blocked_order_var, value="yes_first")
        self.no_first_k = ttk.Radiobutton(self.order_frame, text="Сначала Нет", variable=self.blocked_order_var, value="no_first")
        self.update_order_controls()

        btn_frame = ttk.Frame(sort_frame)
        btn_frame.grid(row=3, column=0, columnspan=6, pady=10)
        self.sort_btn = ttk.Button(btn_frame, text="Сортировать", command=self.sort_file)
        self.sort_btn.pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Проверить сортировку", command=self.check_sorting).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Очистить вывод", command=self.clear_output).pack(side="left", padx=5)
        range_frame = ttk.LabelFrame(sort_frame, text="Диапазон строк", padding="5")
        range_frame.grid(row=4, column=0, columnspan=6, sticky="ew", pady=5)

        ttk.Label(range_frame, text="От:").pack(side="left", padx=5)
        self.range_from = tk.StringVar(value="1")
        ttk.Entry(range_frame, width=10, textvariable=self.range_from).pack(side="left", padx=5)

        ttk.Label(range_frame, text="До:").pack(side="left", padx=5)
        self.range_to = tk.StringVar(value="20")
        ttk.Entry(range_frame, width=10, textvariable=self.range_to).pack(side="left", padx=5)

        ttk.Button(range_frame, text="Показать диапазон data.csv",
                command=lambda: self.show_range(DATA_FILE)).pack(side="left", padx=10)
        ttk.Button(range_frame, text="Показать диапазон sorted.txt",
                command=lambda: self.show_range(SORTED_FILE)).pack(side="left", padx=5)
        self.progress_bar = ttk.Progressbar(main_frame, mode="indeterminate")
        self.progress_bar.grid(row=2, column=0, columnspan=3, sticky="ew", pady=5)

        self.status_label = ttk.Label(main_frame, text="Готов к работе", font=("Arial", 10))
        self.status_label.grid(row=3, column=0, columnspan=3, pady=5)

        result_frame = ttk.LabelFrame(main_frame, text="Вывод", padding="5")
        result_frame.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=5)
        self.result_text = scrolledtext.ScrolledText(result_frame, height=25, font=("Consolas", 9))
        self.result_text.pack(fill="both", expand=True)

        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.columnconfigure(2, weight=1)
        main_frame.rowconfigure(4, weight=1)

        self.log(self.dll_status)
        if DATA_FILE.exists():
            self.sort_btn.config(state="normal")
        else:
            self.sort_btn.config(state="disabled")

    def update_order_controls(self):
        for child in self.order_frame.winfo_children():
            child.pack_forget()
        column = self.column_var.get()
        if column == 3:
            self.home_first_k.pack(side="left", padx=5)
            self.mobile_first_k.pack(side="left", padx=5)
        elif column == 5:
            self.yes_first_k.pack(side="left", padx=5)
            self.no_first_k.pack(side="left", padx=5)
        else:
            self.asc_k.pack(side="left", padx=5)
            self.desc_k.pack(side="left", padx=5)

    def selected_key(self):
        column = self.column_var.get()
        if column == 3:
            return 3 if self.phone_type_order_var.get() == "home_first" else -3
        if column == 5:
            return 5 if self.blocked_order_var.get() == "yes_first" else -5
        return column if self.order_var.get() == "asc" else -column

    def set_busy(self, value, status = None):
        self.busy = value
        state = "disabled" if value else "normal"
        self.gen_btn.config(state=state)
        self.sort_btn.config(state=state)
        if value:
            self.progress_bar.start()
        else:
            self.progress_bar.stop()
        if status:
            self.status_label.config(text=status)

    def log(self, message):
        self.result_text.insert(tk.END, message + "\n")
        self.result_text.see(tk.END)

    def clear_output(self):
        self.result_text.delete("1.0", tk.END)

    def _poll_messages(self):
        try:
            while True:
                item = self.messages.get_nowait()
                if isinstance(item, tuple) and len(item) == 3 and item[0] == "busy":
                    self.set_busy(bool(item[1]), str(item[2]))
                    if not item[1] and DATA_FILE.exists():
                        self.sort_btn.config(state="normal")
                else:
                    self.log(str(item))
        except queue.Empty:
            pass
        self.after(200, self._poll_messages)

    def run_threaded(self, target, start_status):
        if self.busy:
            return
        self.set_busy(True, start_status)
        threading.Thread(target=target, daemon=True).start()

    def generate_file(self):
        try:
            size_gb = float(self.size_var.get())
            if size_gb <= 0:
                raise ValueError("Размер должен быть больше 0")
            seed_text = self.seed_var.get().strip()
            seed = int(seed_text) if seed_text else None
        except Exception as exc:
            messagebox.showerror("Ошибка", str(exc))
            return

        def worker():
            try:
                self.messages.put(f"\n{'=' * 50}")
                self.messages.put(f"Генерация файла {size_gb} ГБ...")

                last_msg_time = 0.0

                def progress(rows, bytes_written):
                    nonlocal last_msg_time
                    now = time.time()
                    if now - last_msg_time >= 1.0:
                        pct = bytes_written / (size_gb * 1024 ** 3) * 100
                        self.messages.put(f"  {pct:.0f}% — {rows:,} строк, {bytes_written / 1024**2:.1f} МБ")
                        last_msg_time = now

                rows = generate_csv(
                    DATA_FILE,
                    target_bytes=int(size_gb * 1024 ** 3),
                    seed=seed,
                    progress_callback=progress,
                )
                size = DATA_FILE.stat().st_size if DATA_FILE.exists() else 0
                self.messages.put("Генерация завершена!")
                self.messages.put(f"Имя: data.csv")
                self.messages.put(f"Размер: {size / 1024**3:.2f} ГБ")
                self.messages.put(f"Строк: {rows:,}")
                self.messages.put(("busy", False, "Генерация завершена!"))
            except Exception:
                self.messages.put("Ошибка генерации:\n" + traceback.format_exc())
                self.messages.put(("busy", False, "Ошибка генерации"))

        self.run_threaded(worker, f"Генерация файла {size_gb} ГБ...")

    def sort_file(self):
        if not DATA_FILE.exists():
            messagebox.showerror("Файл не найден", "data.csv не найден. Сначала сгенерируйте файл.")
            return
        method = self.method_var.get()
        key = self.selected_key()

        def worker():
            try:
                self.messages.put(f"\n{'=' * 50}")
                self.messages.put(f"Сортировка ({('Python' if method == 'python' else 'C++').upper()})")
                self.messages.put(f"{'=' * 50}")
                self.messages.put(f"Столбец: {abs(key)}: {FIELD_LABELS[abs(key)]}")
                self.messages.put(f"Порядок: {order_description(key)}")

                start_time = time.time()

                if method == "python":
                    self.messages.put("Сортировка Python...")
                    stats = external_sort(DATA_FILE, SORTED_FILE, key=key, memory_ratio=0.09)
                    rows = count_rows(SORTED_FILE)
                    elapsed = time.time() - start_time

                    self.messages.put("\nРезультат:")
                    self.messages.put(f"Файл: sorted.txt")
                    self.messages.put(f"Строк: {rows:,}")
                    self.messages.put(f"Время: {elapsed:.2f} сек")
                else:
                    if self.cpp_dll is None:
                        raise RuntimeError("sorter.dll не загружен")
                    self.messages.put("Сортировка C++...")
                    code = self.cpp_dll.sort_file(b"data.csv", b"sorted.txt", int(key))
                    if code != 0:
                        raise RuntimeError(f"C++ DLL вернула код ошибки {code}")
                    rows = count_rows(SORTED_FILE)
                    elapsed = time.time() - start_time

                    self.messages.put("\nРезультат:")
                    self.messages.put(f"Файл: sorted.txt")
                    self.messages.put(f"Строк: {rows:,}")
                    self.messages.put(f"Время: {elapsed:.2f} сек")

                ok, msg = check_sorted(SORTED_FILE, key=key)
                self.messages.put(("\nПроверка OK: " if ok else "\nПроверка ОШИБКА: ") + msg)

                self.messages.put("\nПервые 20 строк:")
                self.messages.put(format_preview(read_head_rows(SORTED_FILE, 21)))
                self.messages.put(("busy", False, f"Сортировка завершена за {elapsed:.2f} сек"))
            except Exception:
                self.messages.put("Ошибка сортировки:\n" + traceback.format_exc())
                self.messages.put(("busy", False, "Ошибка сортировки"))

        self.run_threaded(worker, "Сортировка...")

    def check_sorting(self):
        if not SORTED_FILE.exists():
            messagebox.showerror("Файл не найден", "sorted.txt не найден. Сначала выполните сортировку.")
            return
        key = self.selected_key()

        def worker():
            try:
                self.messages.put(
                    f"\nПроверка sorted.txt  ключ={key}  "
                    f"({FIELD_LABELS[abs(key)]}, {order_description(key)})"
                )
                ok, message = check_sorted(SORTED_FILE, key=key)
                self.messages.put(("OK: " if ok else "ОШИБКА: ") + message)
                self.messages.put(("busy", False, "Проверка завершена"))
            except Exception:
                self.messages.put("Ошибка проверки:\n" + traceback.format_exc())
                self.messages.put(("busy", False, "Ошибка проверки"))

        self.run_threaded(worker, "Проверка sorted.txt...")

    def show_part(self, path, part):
        try:
            if not path.exists():
                messagebox.showerror("Файл не найден", str(path))
                return
            rows = (read_head_rows(path, 21) if part == "head" else read_tail_rows(path, 20))
            title = f"\n--- {path.name}: {'начало' if part == 'head' else 'конец'} ---"
            self.log(title)
            self.log(format_preview(rows))
        except Exception:
            self.log("Ошибка просмотра:\n" + traceback.format_exc())

    def show_range(self, path):
        try:
            if not path.exists():
                messagebox.showerror("Файл не найден", str(path))
                return
            row_from = int(self.range_from.get())
            row_to = int(self.range_to.get())
            if row_from < 1 or row_to < row_from:
                messagebox.showerror("Ошибка", "Некорректный диапазон")
                return
            rows = read_range_rows(path, row_from, row_to)
            title = f"\n--- {path.name}: строки {row_from}–{row_to} ---"
            self.log(title)
            self.log(format_preview(rows))
        except ValueError:
            messagebox.showerror("Ошибка", "Введите целые числа в поля От и До.")
        except Exception:
            self.log("Ошибка просмотра:\n" + traceback.format_exc())
if __name__ == "__main__":
    app = PhonebookApp()
    app.mainloop()
