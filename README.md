# ⚡ doc-craft

[![CI](https://github.com/doc-craft/doc-craft/actions/workflows/ci.yml/badge.svg)](https://github.com/doc-craft/doc-craft/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.9%20%7C%203.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Code Style](https://img.shields.io/badge/docstrings-Google--Style-brightgreen.svg)](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings)

**doc-craft** adalah alat CLI (*Command Line Interface*) sumber terbuka berbasis Python untuk menghasilkan *docstring* fungsi secara otomatis menggunakan analisis Pohon Sintaksis Abstrak (*Abstract Syntax Tree* / AST) sesuai standar **Google Style Python Docstrings**.

---

## 🌟 Fitur Utama

- 🔍 **Pemindaian Berbasis AST**: Menggunakan modul bawaan Python `ast` sehingga cepat, aman, dan tanpa menjalankan (*executing*) berkas target.
- 🎯 **Deteksi Cerdas**:
  - Nama fungsi dan *human-readable summary*.
  - Parameter (posisional, kata kunci, nilai *default*, `*args`, dan `**kwargs`).
  - Anotasi *type hints* lengkap (termasuk tipe kompleks seperti `Optional[T]`, `Union[A, B]`, `dict[K, V]`).
  - Deteksi tipe pengembalian nilai (*return type annotation*).
  - Pengecualian (*Exceptions*) yang dilempar menggunakan pernyataan `raise`.
- 🏛️ **Dukungan Kelas & Metode**:
  - Mengabaikan `self` dan `cls` secara otomatis pada bagian `Args:` sesuai pedoman Google Style.
  - Mendukung fungsi asinkron (`async def`), `@staticmethod`, dan `@classmethod`.
- ✍️ **Mode Fleksibel**:
  - **Pratinjau (*Dry-run*)**: Menampilkan *diff* berwarna di terminal tanpa mengubah berkas.
  - **In-Place Write (`-i`)**: Menyisipkan atau memperbarui *docstring* langsung ke berkas target secara presisi.
  - **CI Check Mode (`-c`)**: Menghasilkan kode keluar `1` jika ada fungsi yang belum terdokumentasi, sangat cocok untuk *pipeline* CI/CD dan *pre-commit hooks*.

---

## 📦 Instalasi

### 1. Instalasi dari Direktori Sumber (Lokal / Mode Pengembang)

```bash
# Clone repositori
git clone https://github.com/doc-craft/doc-craft.git
cd doc-craft

# Instal paket beserta dependensinya
pip install -e .
```

### 2. Menggunakan `pip` dan `requirements.txt`

```bash
pip install -r requirements.txt
```

---

## 🚀 Penggunaan CLI

Setelah instalasi, perintah `doc-craft` tersedia langsung di terminal Anda.

### 1. Pratinjau Perubahan (*Diff Preview*)

Melihat perbandingan sebelum dan sesudah tanpa menulis ke berkas:

```bash
doc-craft generate ./src --diff
```

Atau melihat pratinjau berkas tunggal:

```bash
doc-craft preview path/to/script.py
```

### 2. Menyisipkan Docstring Langsung ke Berkas (*In-Place*)

Menghasilkan dan menyisipkan *docstring* ke semua berkas `.py` dalam sebuah direktori:

```bash
doc-craft generate ./src --in-place
# atau gunakan shortcut flag:
doc-craft generate ./src -i
```

### 3. Menimpa Docstring yang Sudah Ada (*Overwrite*)

Secara bawaan, fungsi yang sudah memiliki *docstring* akan dilewati. Gunakan flag `--overwrite` (`-w`) untuk memperbaruinya:

```bash
doc-craft generate ./src -i --overwrite
```

### 4. Mode Pemeriksaan CI / Pre-Commit (*Check Mode*)

Memeriksa apakah ada berkas yang belum memiliki *docstring*:

```bash
doc-craft generate ./src --check
```
> *Jika ditemukan fungsi tanpa docstring, perintah akan mengembalikan status keluar `1` sehingga membatalkan build CI yang tidak memenuhi standar.*

---

## 📋 Tabel Pilihan Perintah (*Command Options*)

| Opsi | Singkatan | Tipe | Deskripsi |
| :--- | :---: | :---: | :--- |
| `path` | - | `ARG` | Berkas atau direktori target (default: `.`) |
| `--in-place` | `-i` | `FLAG` | Tulis docstring langsung ke berkas target |
| `--overwrite` | `-w` | `FLAG` | Timpa docstring yang sudah ada |
| `--diff` | `-d` | `FLAG` | Tampilkan pratinjau unified diff berwarna di terminal |
| `--check` | `-c` | `FLAG` | Return exit code 1 jika ada fungsi tanpa docstring |
| `--exclude` | `-e` | `TEXT` | Pola direktori/nama yang dikecualikan (dipisah koma) |
| `--quiet` | `-q` | `FLAG` | Hanya tampilkan pesan galat jika ada |
| `--version` | `-v` | `FLAG` | Tampilkan versi aplikasi |

---

## 📝 Format Google Style Docstring

### Contoh Sebelum (*Input Source*):

```python
class PaymentGateway:
    def process_transaction(
        self,
        account_id: str,
        amount: float,
        currency: str = "USD",
        *tags: str,
        notify_user: bool = True,
        **metadata: str,
    ) -> bool:
        if amount <= 0:
            raise ValueError("Amount must be positive")
        return True
```

### Contoh Sesudah (*Generated Output*):

```python
class PaymentGateway:
    def process_transaction(
        self,
        account_id: str,
        amount: float,
        currency: str = "USD",
        *tags: str,
        notify_user: bool = True,
        **metadata: str,
    ) -> bool:
        """Process transaction.

        Args:
            account_id (str): The account id value.
            amount (float): The amount value.
            currency (str): The currency value. Defaults to "USD".
            *tags: Variable length argument list of tags.
            notify_user (bool): The notify user value. Defaults to True.
            **metadata: Arbitrary keyword arguments for metadata.

        Returns:
            bool: The return value of process transaction.

        Raises:
            ValueError: If an error occurs during execution.
        """
        if amount <= 0:
            raise ValueError("Amount must be positive")
        return True
```

---

## 🧪 Menjalankan Pengujian (Testing)

Proyek ini dilengkapi dengan rangkaian pengujian komprehensif menggunakan `pytest`:

```bash
# Menjalankan seluruh pengujian
pytest -v

# Menjalankan pengujian dengan laporan cakupan (coverage)
pytest --cov=doc_craft tests/
```

---

## 🛠️ Integrasi CI dengan GitHub Actions

Berkas `.github/workflows/ci.yml` sudah dikonfigurasi untuk menjalankan pengujian otomatis pada setiap *push* dan *pull request* di multi-OS (Linux, Windows, macOS) serta multi-versi Python (3.9 - 3.13).

```yaml
name: CI
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.9", "3.10", "3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -r requirements.txt
      - run: pytest -v
```

---

## 🪝 Integrasi Pre-Commit Hook

Anda dapat menggunakan `doc-craft` sebagai *hook* otomatis dalam alur kerja git Anda dengan menambahkan konfigurasi berikut ke `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/doc-craft/doc-craft
    rev: v0.1.0
    hooks:
      # Mode otomatis menambahkan docstring:
      - id: doc-craft
      # Atau mode validasi / CI check:
      # - id: doc-craft-check
```

---

## 📄 Lisensi

Didistribusikan di bawah lisensi resmi [MIT License](LICENSE). Hak Cipta (c) 2026 DocCraft Contributors.
