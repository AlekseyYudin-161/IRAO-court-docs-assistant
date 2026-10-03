"""dev-set / holdout-set и срезы по типу документа. Тип берётся из пути в РАЗМЕТКЕ, не из предсказания."""

from __future__ import annotations

from pathlib import Path

HOLDOUT_FILE = Path("data/courts_anonymized/holdout.txt")

SLICES = ("XML ФССП", "PDF электронные", "PDF сканы")


def load_holdout(path: Path | str = HOLDOUT_FILE) -> set[str]:
    """Множество stem-ов (ocr_004, fssp_009 …). Строки с # и пустые — пропускаются."""
    p = Path(path)
    if not p.exists():
        return set()
    return {Path(s.strip()).stem for s in p.read_text(encoding="utf-8").splitlines()
            if s.strip() and not s.lstrip().startswith("#")}


def stem(file: str) -> str:
    return Path(str(file).replace("\\", "/")).stem


def slice_of(file: str) -> str:
    f = str(file).replace("\\", "/")
    if f.startswith("fssp/") or "/fssp/" in f or f.endswith(".xml"):
        return "XML ФССП"
    if "_scan/" in f:
        return "PDF сканы"
    if "_electronic/" in f:
        return "PDF электронные"
    return "прочее"


def filter_paths(paths, holdout: bool, holdout_file: Path | str = HOLDOUT_FILE) -> list[Path]:
    """Для run_examples --holdout: только файлы из списка. Без флага — все (dev-set + holdout-set)."""
    paths = [Path(p) for p in paths]
    if not holdout:
        return paths
    keep = load_holdout(holdout_file)
    return [p for p in paths if p.stem in keep]
