# src/rules/markers.py
"""Маркеры судебных актов для направления юристу (перечень организаторов от 01.10, 10 фраз).

Как работает (без LLM):
1. operative_part(text) — берём текст ПОСЛЕ последнего заголовка «решил:» / «определил:» / «постановил:»
   (буквы могут быть разрежены пробелами: «О П Р ЕД ЕЛИ Л :»). Фразы ищем только там — README оргов:
   «учитывайте контекст фразы и резолютивную часть». В описательной части «решение … отменить»
   встречается как пересказ жалобы (Акт_08) — это не основание.
2. find_markers(text) — каждая из 10 фраз как регулярка с допусками на «…»; evidence — предложение целиком.
3. appeal_window(operative) — срок обжалования из самого акта («в течение месяца», «пятнадцати дней»,
   «в срок до <дата>») → deadline в днях от даты акта.
4. route_court_act(text, doc_date) — итог для route.lawyer: уровень, коды, норма (если названа в акте), срок, фрагмент.
   Уровень: L1 — срок ≤ 15 дней или в акте назначена дата («в срок до …»); L2 — иначе при наличии маркера; L3 — маркеров нет.
"""

import re
from dataclasses import dataclass, field
from datetime import date, timedelta


def _spaced(word: str) -> str:
    """'решил' -> 'р\\s*е\\s*ш\\s*и\\s*л' — заголовки в актах бывают разрежены пробелами."""
    return r"\s*".join(map(re.escape, word))


HEADER_RE = re.compile(r"(?:" + "|".join(_spaced(w) for w in ("решил", "определил", "постановил")) + r")\s*:", re.IGNORECASE)

# (номер в перечне оргов, код, регулярка, что делать юристу, уровень по умолчанию)
MARKERS: list[tuple[int, str, str, str, str]] = [
    (1, "ACT_PARTIAL_REFUSAL", r"в удовлетворении остальной части.{0,80}?требований отказать",
     "оценить целесообразность обжалования в части отказа", "L2"),
    (2, "ACT_LEFT_WITHOUT_MOTION", r"заявлени\w* оставить без движения",
     "устранить недостатки заявления в срок, указанный в определении", "L1"),
    (3, "ACT_FEE_REFUND", r"возвратить.{0,250}?из федерального бюджета.{0,250}?государственн\w+ пошлин\w+",
     "подать заявление о возврате государственной пошлины (ст. 333.40 НК РФ)", "L2"),
    (4, "ACT_RETURNED", r"заявлени\w* возвратить заявителю",
     "устранить причины возврата и подать заявление повторно либо обжаловать определение", "L2"),
    (5, "ACT_LEFT_WITHOUT_CONSIDERATION", r"оставить.{0,60}?без рассмотрения",
     "устранить причину (например, досудебный порядок) и обратиться повторно либо обжаловать", "L2"),
    (6, "ACT_CLAIM_DENIED", r"в иске отказать",
     "оценить основания для апелляционной жалобы", "L2"),
    (7, "ACT_DECISION_REVERSED", r"решени\w*.{0,400}?отменить",
     "оценить основания для дальнейшего обжалования", "L2"),
    (8, "ACT_NEW_TRIAL", r"направить на новое рассмотрение",
     "подготовить позицию к новому рассмотрению дела", "L2"),
    (9, "ACT_PROCEEDINGS_TERMINATED", r"производство по делу прекратить",
     "проверить основания прекращения, при несогласии — обжаловать", "L2"),
    (10, "ACT_SETTLEMENT_APPROVED", r"утвердить мировое соглашение",
     "поставить на контроль исполнение условий мирового соглашения", "L2"),
]

WINDOW_RE = re.compile(
    r"(?:обжалован\w*|жалоб\w*|обжалования)[^.]{0,160}?"
    r"(?:в течение|не превышающ\w+|в срок, не превышающий)\s+"
    r"(одного месяца|месяца|двух месяцев|пятнадцати дней|десяти дней|(\d{1,2})\s*дней)", re.IGNORECASE)
UNTIL_RE = re.compile(r"в срок до\s*(\[дата\]|\d{2}\.\d{2}\.\d{4})", re.IGNORECASE)
WORDS = {"одного месяца": 30, "месяца": 30, "двух месяцев": 60, "пятнадцати дней": 15, "десяти дней": 10}
ARTICLE_RE = re.compile(r"стать\w+\s+([\d,\s\-–и]+?)\s+(Арбитражного процессуального кодекса|АПК РФ|Гражданского процессуального кодекса|ГПК РФ)", re.IGNORECASE)
L1_MAX_DAYS = 15


@dataclass
class MarkerHit:
    no: int
    code: str
    action: str
    level: str
    evidence: str
    start: int


@dataclass
class ActRoute:
    level: str = "L3"
    reason_codes: list[str] = field(default_factory=list)
    basis: str | None = None
    deadline: str | None = None
    evidence: str | None = None
    actions: list[str] = field(default_factory=list)
    window_days: int | None = None
    hits: list[MarkerHit] = field(default_factory=list)


COURT_ACT_RE = re.compile(r"\b(РЕШЕНИЕ|ОПРЕДЕЛЕНИЕ|ПОСТАНОВЛЕНИЕ)\b|Резолютивная часть (?:решения|определения|постановления)")
FSSP_RE = re.compile(r"Судебный пристав|O_IP_|namespace/order", re.IGNORECASE)


def looks_like_court_act(text: str) -> bool:
    """Классификатор 5-го класса «судебный акт» (решение/определение/постановление суда) по текстовому слою:
    есть шапка суда и вид акта, нет признаков постановления ФССП. Приказ/ИЛ сюда не попадают (там таких слов нет)."""
    head = flatten(text)[:1500]
    return bool(COURT_ACT_RE.search(head)) and ("суд" in head.lower()) and not FSSP_RE.search(head)


def flatten(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def operative_part(text: str) -> tuple[str, int]:
    """Текст после последнего «решил:/определил:/постановил:». Нет заголовка — пустая строка (маркеры не ищем)."""
    flat = flatten(text)
    heads = list(HEADER_RE.finditer(flat))
    if not heads:
        return "", -1
    return flat[heads[-1].end():].strip(), heads[-1].end()


def _sentence(text: str, start: int, end: int, limit: int = 300) -> str:
    i = text.rfind(". ", 0, start)
    left = 0 if i == -1 else i + 2
    right = text.find(". ", end)
    right = len(text) if right == -1 else right + 1
    return text[left:right].strip()[:limit]


def find_markers(text: str) -> list[MarkerHit]:
    op, _ = operative_part(text)
    hits: list[MarkerHit] = []
    for no, code, rx, action, level in MARKERS:
        m = re.search(rx, op, re.IGNORECASE)
        if m:
            hits.append(MarkerHit(no, code, action, level, _sentence(op, m.start(), m.end()), m.start()))
    return sorted(hits, key=lambda h: h.start)


def appeal_window(operative: str) -> tuple[int | None, str | None, str | None]:
    """(дней, явная дата, фрагмент). Явная дата «в срок до …» важнее окна обжалования."""
    m = UNTIL_RE.search(operative)
    if m:
        return None, m.group(1), _sentence(operative, m.start(), m.end())
    m = WINDOW_RE.search(operative)
    if m:
        days = int(m.group(2)) if m.group(2) else WORDS.get(m.group(1).lower())
        return days, None, _sentence(operative, m.start(), m.end())
    return None, None, None


def route_court_act(text: str, doc_date: date | None = None) -> ActRoute:
    """Маршрут судебного акта для юриста по 10 фразам-маркерам оргов.

    Ищет маркеры только в резолютивной части (после последнего «решил:/определил:/постановил:»),
    берёт срок обжалования из текста акта и норму из «Руководствуясь статьями …».
    Возвращает ActRoute: level (L1 — срок ≤ 15 дней или назначена дата; L2 — маркер есть;
    L3 — маркеров нет), reason_codes ACT_*, basis, deadline (если известна doc_date),
    evidence (предложения с маркерами и сроком), actions — что сделать юристу (для письма).
    """
    
    r = ActRoute()
    hits = find_markers(text)
    if not hits:
        return r
    op, _ = operative_part(text)
    r.hits = hits
    r.reason_codes = [h.code for h in hits]
    r.actions = [h.action for h in hits]
    r.evidence = " | ".join(dict.fromkeys(h.evidence for h in hits))
    days, until, win_ev = appeal_window(op)
    r.window_days = days
    if until:
        r.level, r.deadline = "L1", (until if until != "[дата]" else None)
        r.evidence += f" | срок: {win_ev}"
    elif days is not None:
        r.level = "L1" if days <= L1_MAX_DAYS else "L2"
        if doc_date:
            r.deadline = (doc_date + timedelta(days=days)).isoformat()
        r.evidence += f" | срок обжалования: {win_ev}"
    else:
        r.level = "L1" if any(h.level == "L1" for h in hits) else "L2"
    # Норма — из фразы «Руководствуясь статьями … АПК РФ», которая стоит прямо перед заголовком резолютивной части
    flat = flatten(text)
    heads = list(HEADER_RE.finditer(flat))
    before = flat[: heads[-1].start()] if heads else flat
    arts = list(ARTICLE_RE.finditer(before))
    if arts:
        a = arts[-1]
        r.basis = f"ст. {a.group(1).strip(' ,')} {a.group(2)}"
    return r


if __name__ == "__main__":  # отладка: python -m src.rules.markers <pdf|txt>
    import sys
    p = sys.argv[1]
    if p.lower().endswith(".pdf"):
        # локальный импорт: модуль правил не должен зависеть от PDF-библиотеки
        import pymupdf
        txt = " ".join(pg.get_text("text", sort=True) for pg in pymupdf.open(p))
    else:
        with open(p, encoding="utf-8") as f:
            txt = f.read()
    rt = route_court_act(txt)
    print(rt.level, rt.reason_codes, rt.window_days, rt.deadline, "\n", rt.basis, "\n", rt.evidence)
