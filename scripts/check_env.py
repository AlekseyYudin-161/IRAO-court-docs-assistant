# scripts/check_env.py
"""Проверка окружения перед запуском: Python, Tesseract (rus), Ollama и модель. Одинаково на macOS/Linux/Windows.
Запуск: python scripts/check_env.py [--pull-model qwen3:8b]"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import urllib.request

OK, WARN = "OK  ", "WARN"


def run(cmd: list[str]) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
        return r.returncode, (r.stdout + r.stderr)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pull-model", default=None, help="скачать модель через ollama pull, если Ollama есть")
    a = ap.parse_args()
    problems = 0

    print(f"{OK} Python {sys.version.split()[0]} ({sys.executable})")
    # UP036 — проверяем окружение эксперта намеренно
    if sys.version_info < (3, 10):
        print(f"{WARN} нужен Python >= 3.10")
        problems += 1

    if shutil.which("tesseract"):
        code, out = run(["tesseract", "--list-langs"])
        if code == 0 and "rus" in out.split():
            print(f"{OK} Tesseract с русским языком")
        else:
            print(f"{WARN} Tesseract есть, но нет языка rus: macOS: brew install tesseract-lang; "
                  "Linux: apt install tesseract-ocr-rus; Windows: установщик UB-Mannheim, отметить Russian"); problems += 1
    else:
        print(f"{WARN} Tesseract не найден: macOS: brew install tesseract tesseract-lang; Linux: apt install tesseract-ocr "
              "tesseract-ocr-rus; Windows: https://github.com/UB-Mannheim/tesseract/wiki (+ добавить в PATH)"); problems += 1

    base = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
    model = a.pull_model or os.getenv("LLM_MODEL", "qwen3:8b")
    if shutil.which("ollama"):
        if a.pull_model:
            print(f"...  ollama pull {model} (один раз, ~5 ГБ)")
            code, out = run(["ollama", "pull", model])
            print(f"{OK if code == 0 else WARN} ollama pull: {'готово' if code == 0 else out.strip()[-200:]}")
        try:
            with urllib.request.urlopen(f"{base}/models", timeout=3) as r:
                names = r.read().decode()
            print(f"{OK} Ollama отвечает на {base}; модель {model} {'есть' if model.split(':')[0] in names else 'НЕ скачана: ollama pull ' + model}")
        except Exception:
            print(f"{WARN} Ollama установлена, но сервер не запущен ({base}): откройте приложение Ollama или выполните `ollama serve`. "
                  "Без LLM всё работает в режиме --no-llm")
    else:
        print(f"{WARN} Ollama не найдена — LLM-режим недоступен, используйте --no-llm (XML и электронные PDF считаются полностью)")

    # print("\nИтог:", "всё готово" if problems == 0 else f"предупреждений: {problems}; базовый сценарий (--no-llm) работает при наличии Tesseract")
    print("\nИтог:", "всё готово" if problems == 0
          else f"обязательных проблем: {problems} — без Tesseract не работает OCR; Ollama опциональна (режим --no-llm)"
          )

    return 0  # предупреждения не валят make setup


if __name__ == "__main__":
    sys.exit(main())
