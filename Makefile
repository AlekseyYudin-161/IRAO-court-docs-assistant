# Помощник по судебным документам — единая точка входа. make help — список команд.
.PHONY: help setup check test run-examples run-all score report ui clean

VENV      ?= .venv
PYTHON    ?= python3
VENV_BIN   = $(VENV)/bin
LLM_MODEL ?= qwen3:8b
DOCS      ?= data
PRED      ?= out
ARGS      ?=

ifeq ($(OS),Windows_NT)
	VENV_BIN = $(VENV)/Scripts
	PYTHON   = python
endif

PY  = $(VENV_BIN)/python
PIP = $(VENV_BIN)/pip

help:
	@echo "make setup         - создать $(VENV), поставить зависимости, проверить Tesseract и Ollama"
	@echo "make check         - только проверка окружения (Tesseract rus, Ollama, модель)"
	@echo "make test          - pytest"
	@echo "make run-examples  - прогон на fixtures/ -> out/examples/ (без LLM: ARGS=--no-llm)"
	@echo "make run-all       - прогон на DOCS=$(DOCS) -> out/"
	@echo "make score         - сверка PRED=$(PRED) с разметкой (src/eval)
	@echo "make report        - отчёт ожидаемое vs извлечённое"
	@echo "make ui            - Streamlit"
	@echo "make clean         - удалить $(VENV), out/examples, work/"

setup:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	$(PY) scripts/check_env.py --pull-model $(LLM_MODEL)

check:
	$(PY) scripts/check_env.py

test:
	$(PY) -m pytest -q

run-examples:
	$(PY) run_examples.py --docs fixtures --out out/examples $(ARGS)

run-all:
	$(PY) run_examples.py --docs $(DOCS) --out out $(ARGS)

score:
	$(PY) -m src.eval.score --pred $(PRED) --gold data/courts_anonymized/labels

report:
	$(PY) -m src.eval.report --pred $(PRED) --gold data/courts_anonymized/labels

ui:
	$(PY) -m streamlit run src/ui/app.py

clean:
	$(PY) -c "import shutil; [shutil.rmtree(p, ignore_errors=True) for p in ('$(VENV)', 'out/examples', 'work')]"