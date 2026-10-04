"""Помощник по судебным документам — интерфейс (карточка E).

    make ui            # = streamlit run src/ui/app.py
    UI_FIXTURES=1 make ui   # демо без веток: показывать fixtures/ и предрасчитанный out/

Работает без Ollama: индикатор покажет «работаем на правилах», а для документов, ветки которых
ещё не подключены, откроется готовый результат из out/ или fixtures/ с явной пометкой.
"""

from __future__ import annotations

import html
import inspect
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:                      # streamlit кладёт в sys.path только src/ui/
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)                                      # пути data/, out/, fixtures/ — от корня репо

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from src.core.contract import load  # noqa: E402
from src.eval.normalize import KEY_COLUMNS  # noqa: E402
from src.export import mailer  # noqa: E402
from src.llm import client as llm_client  # noqa: E402
from src.ui import components as C  # noqa: E402

st.set_page_config(page_title="Судебные документы — помощник", page_icon="⚖️", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1280px;}
.route-card {border-radius: 10px; padding: 16px 20px; margin: 4px 0 12px 0; border-left: 6px solid;}
.route-card h3 {margin: 0 0 6px 0; font-size: 1.15rem;}
.route-card .meta {color: #344054; font-size: .92rem; margin: 2px 0;}
.route-card blockquote {margin: 10px 0 0 0; padding: 8px 12px; background: rgba(255,255,255,.7);
  border-left: 3px solid #98a2b3; font-size: .9rem; color: #1d2939;}
.chip {display:inline-block; padding: 2px 9px; margin: 2px 4px 2px 0; border-radius: 12px;
  font-size: .82rem; background:#eef2f6; color:#1d2939; border:1px solid #d0d5dd;}
.chip.warn {background:#fff4ed; border-color:#f9dbaf; color:#93370d;}
.mail {border:1px solid #d0d5dd; border-radius:8px; padding:14px 16px; background:#fcfcfd;
  white-space: pre-line; font-size:.92rem; line-height:1.5;}
.mail .subj {font-weight:600; margin-bottom:8px; white-space: normal;}
</style>
""", unsafe_allow_html=True)

UI_FIXTURES = os.getenv("UI_FIXTURES", "0") == "1"


# =================================================================== сайдбар: режим работы
@st.cache_data(ttl=15, show_spinner=False)
def _ping(base_url: str):
    return C.ping_models(base_url)


with st.sidebar:
    st.subheader("Режим")
    info = llm_client.info()
    ok, models, err = _ping(info["base_url"])
    if ok and models:
        current = os.getenv("LLM_MODEL", info["model"])
        idx = models.index(current) if current in models else 0
        chosen = st.selectbox("Модель LLM", models, index=idx,
                              help="Список с сервера Ollama. Смена модели — без правки кода: меняется LLM_MODEL.")
        os.environ["LLM_MODEL"] = chosen
        no_llm = st.toggle("Без LLM (только правила)", value=False)
        if no_llm:
            st.info("LLM выключена вручную: поля сканов, которые не нашли правила, останутся пустыми "
                    "с причиной «нужна LLM, она выключена».")
        else:
            st.success(f"LLM подключена: {chosen}")
    else:
        no_llm = True
        st.warning("LLM недоступна — работаем на правилах. XML и электронные PDF обрабатываются полностью; "
                   "для сканов показан предрасчитанный результат из out/, если он есть.")
        st.caption(f"{info['base_url']} · {err or 'нет моделей'}")
    C.set_llm(not no_llm)

    st.divider()
    st.subheader("Результаты и письма")
    out_dir = Path(st.text_input("Папка результатов", value="out",
                                 help="Отсюда читаются реестр, метрики и предрасчитанные doc.json."))
    lawyer = st.text_input("Ответственный сотрудник (e-mail)", value=os.getenv("LAWYER_EMAIL", "lawyer@example.local"))
    os.environ["LAWYER_EMAIL"] = lawyer
    smtp_ready = bool(os.getenv("SMTP_HOST"))
    send_real = st.toggle("Отправлять по SMTP", value=False, disabled=not smtp_ready,
                          help=None if smtp_ready else "SMTP не настроен в .env — письма сохраняются файлом .eml.")
    if UI_FIXTURES:
        st.caption("Демо-режим UI_FIXTURES=1: документы открываются из fixtures/ и out/.")


# =================================================================== обработка
def process(path: Path) -> tuple[object | None, str]:
    """(doc, откуда результат). Сначала живой конвейер; если ветка не подключена — готовый результат по stem."""
    stem = path.stem.removeprefix("doc_")
    if not UI_FIXTURES or path.suffix.lower() == ".json":
        try:
            from run_examples import run_one  # pylint: disable=import-outside-toplevel
            t0 = time.time()
            doc = run_one(path, no_llm=no_llm)
            doc.timings_ms.setdefault("total", int((time.time() - t0) * 1000))
            if path.suffix.lower() == ".json":
                return doc, "готовый doc.json, маршрут пересчитан правилами"
            return doc, "обработан сейчас" + (" (без LLM)" if no_llm else f" ({os.getenv('LLM_MODEL')})")
        except NotImplementedError:
            failure = "ветка для этого типа документа ещё не подключена"
        except Exception as e:  # pylint: disable=broad-except  # UI не должен падать на одном документе
            failure = f"ошибка обработки: {type(e).__name__}: {e}"
        else:
            failure = ""
    else:
        failure = "демо-режим UI_FIXTURES=1"
    fb = C.fallback_json(stem, out_dir)
    if fb:
        where = "fixtures/" if "fixtures" in fb.parts else f"{out_dir}/"
        return load(fb), f"предрасчитанный результат из {where} ({failure})"
    return None, f"{failure}; готового результата нет"


def route_card(doc) -> None:
    L, R = doc.route.lawyer, doc.route.review
    fg, bg, title, explain = C.LEVEL_INFO.get(L.level, C.LEVEL_INFO["L3"])
    codes = C.code_texts()
    chips = "".join(f'<span class="chip" title="{html.escape(codes.get(c, ""))}">{html.escape(c)}</span>'
                    for c in L.reason_codes)
    action = "; ".join(doc.extra.get("actions") or [codes[c] for c in L.reason_codes if c in codes])
    parts = [f'<div class="route-card" style="background:{bg}; border-color:{fg};">',
             f'<h3 style="color:{fg};">{L.level} · {title}</h3>',
             f'<div class="meta">{html.escape(explain)}</div>']
    if chips:
        parts.append(f'<div class="meta">{chips}</div>')
    if action:
        parts.append(f'<div class="meta"><b>Что сделать:</b> {html.escape(action)}</div>')
    if L.basis or L.deadline:
        parts.append(f'<div class="meta"><b>Основание:</b> {html.escape(L.basis or "—")}'
                     f'{" · <b>срок до</b> " + html.escape(L.deadline) if L.deadline else ""}</div>')
    if L.evidence:
        parts.append(f"<blockquote>{html.escape(L.evidence)}</blockquote>")
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)
    if R.flags:
        rt = C.review_texts()
        items = []
        for i, f in enumerate(R.flags):
            ev = R.evidence[i] if i < len(R.evidence) else ""
            items.append(f'<span class="chip warn" title="{html.escape(ev)}">{html.escape(rt.get(f, f))}</span>')
        st.markdown("**Ручная проверка реквизитов:** " + "".join(items), unsafe_allow_html=True)


def fields_table(doc) -> None:
    rows = C.field_rows(doc, KEY_COLUMNS)
    df = pd.DataFrame(rows)
    flags = df[["_key", "_llm"]].copy()
    df = df.drop(columns=["_key", "_llm"])

    def paint(row):
        i = row.name
        if not row["значение"]:
            return ["color: #98a2b3; background-color: #f9fafb"] * len(row)
        if flags.loc[i, "_llm"]:
            return ["background-color: #fffaeb"] * len(row)
        return [""] * len(row)

    def bold_key(col):
        return ["font-weight: 600" if flags.loc[i, "_key"] else "" for i in col.index]

    st.dataframe(df.style.apply(paint, axis=1).apply(bold_key, subset=["поле"]),
                 hide_index=True, width="stretch", height=min(38 * (len(df) + 1), 760),
                 column_config={"поле": st.column_config.TextColumn(width="small"),
                                "значение": st.column_config.TextColumn(width="medium"),
                                "уверенность": st.column_config.NumberColumn(format="%.2f", width="small"),
                                "метод": st.column_config.TextColumn(width="small"),
                                "причина пустого": st.column_config.TextColumn(width="small"),
                                "цитата": st.column_config.TextColumn(width="large")})
    st.caption("Жирным — ключевые реквизиты (суммы, даты, ФИО, номера). Серым — не извлечено, причина в столбце. "
               "Жёлтым — значение от LLM, подтверждённое цитатой.")


def _to(fn, *args):
    """mailer.render / send_for_doc с явным адресом из поля «Ответственный сотрудник» (to_addr — с 04.10)."""
    if "to_addr" in inspect.signature(fn).parameters:
        return fn(*args, to_addr=lawyer)
    return fn(*args)


def mail_block(doc) -> None:
    if not mailer.needs_letter(doc):
        st.caption("Письмо не требуется: уровень L3 и нет флагов ручной проверки — документ только в реестре.")
        return
    subj, body = _to(mailer.render, doc)
    st.markdown(f'<div class="mail"><div class="subj">Кому: {html.escape(lawyer)}<br>Тема: {html.escape(subj)}</div>'
                f'{html.escape(body)}</div>', unsafe_allow_html=True)
    att = mailer._attachment(doc)  # pylint: disable=protected-access
    st.caption("Вложения: " + ", ".join(filter(None, [att.name if att else None, f"{doc.doc_id}_row.csv"])))
    msg = mailer.build_message(doc, lawyer, os.getenv("MAIL_FROM", "doc-assistant@example.local"))
    c1, c2 = st.columns(2)
    c1.download_button("Скачать письмо .eml", msg.as_bytes(), file_name=f"{doc.doc_id}.eml",
                       mime="message/rfc822", width="stretch")
    label = "Отправить ответственному" if send_real else "Сохранить письмо в out/ui/mail"
    if c2.button(label, width="stretch", key=f"send_{doc.doc_id}"):
        host = None if send_real else os.environ.pop("SMTP_HOST", None)   # без отправки: только .eml
        try:
            status = _to(mailer.send_for_doc, doc, out_dir / "ui" / "mail")
        finally:
            if host:
                os.environ["SMTP_HOST"] = host
        doc.extra["mail"] = status
        try:
            from src.export.registry import update_registry  # pylint: disable=import-outside-toplevel
            update_registry([doc], out_dir)
        except ImportError:
            pass
        if status.get("sent"):
            st.success(f"Отправлено на {status['to']}. Запись в реестре обновлена.")
        elif status.get("error"):
            st.error(f"SMTP не сработал: {status['error']}. Письмо сохранено: {status['eml']}")
        else:
            st.info(f"Письмо сохранено: {status['eml']}")


def show_doc(doc, source: str) -> None:
    filled, total = C.fill_stats(doc)
    ms = doc.timings_ms.get("total")
    c = st.columns(4)
    c[0].metric("Тип документа", doc.doc_type)
    c[1].metric("Извлечено полей", f"{filled} из {total}")
    c[2].metric("Время обработки", f"{ms / 1000:.1f} с" if ms else "—")
    c[3].metric("Источник результата", "живой" if source.startswith("обработан") else "готовый")
    st.caption(f"Файл `{doc.file}` · {source}")
    if source.startswith("предрасчитанный"):
        st.info(f"Показан {source}: для этого типа документа живая обработка недоступна "
                "в текущем режиме (ветка не подключена или LLM выключена).")

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown("#### Извлечённые сведения")
        fields_table(doc)
    with right:
        st.markdown("#### Маршрут")
        route_card(doc)
        st.markdown("#### Письмо ответственному")
        mail_block(doc)

    st.markdown("#### Выгрузка")
    row = C.table_row(doc)
    d = st.columns(3)
    d[0].download_button("Строка таблицы, CSV", C.rows_to_csv([row]), f"{doc.doc_id}.csv", "text/csv",
                         width="stretch")
    d[1].download_button("Строка таблицы, XLSX", C.rows_to_xlsx([row]), f"{doc.doc_id}.xlsx",
                         width="stretch")
    d[2].download_button("Полный результат, doc.json", C.doc_json_bytes(doc), f"doc_{doc.doc_id}.json",
                         "application/json", width="stretch")


# =================================================================== вкладки
st.title("Помощник по судебным документам")
st.caption("Судебные приказы, исполнительные листы, постановления ФССП и судебные акты → таблица реквизитов, "
           "решение «нужен ли юрист» с основанием и сроком, письмо ответственному сотруднику.")

tab_doc, tab_batch, tab_reg, tab_q = st.tabs(["Документ", "Папка документов", "Реестр", "Качество"])

with tab_doc:
    src = st.radio("Источник", ["Пример из набора", "Загрузить файл", "Предрасчитанный результат"],
                   horizontal=True, label_visibility="collapsed")
    path: Path | None = None
    if src == "Пример из набора":
        groups = C.list_examples()
        if not groups:
            st.warning("В data/ и fixtures/ нет документов.")
        else:
            g = st.selectbox("Набор", list(groups))
            path = st.selectbox("Документ", groups[g], format_func=lambda p: p.name)
    elif src == "Загрузить файл":
        up = st.file_uploader("PDF или XML (до 50 МБ)", type=["pdf", "xml", "json"])
        if up:
            tmp = out_dir / "ui" / "uploads"
            tmp.mkdir(parents=True, exist_ok=True)
            path = tmp / up.name
            path.write_bytes(up.getvalue())
    else:
        pre = C.precomputed_docs(out_dir)
        if not pre:
            st.info(f"В {out_dir}/ пока нет doc_*.json — они появятся после полного прогона (make run-all).")
        else:
            path = st.selectbox("Документ", pre, format_func=lambda p: str(p.relative_to(out_dir)))

    if path and st.button("Обработать", type="primary"):
        with st.spinner("Обрабатываю документ…"):
            st.session_state["doc"], st.session_state["source"] = process(Path(path))
    if "doc" in st.session_state:
        if st.session_state["doc"] is None:
            st.warning(st.session_state["source"])
        else:
            show_doc(st.session_state["doc"], st.session_state["source"])

with tab_batch:
    st.markdown("Обработать все документы из папки и выгрузить таблицы по шаблонам заказчика.")
    folder = st.text_input("Папка", value="data/courts_anonymized",
                           help="Путь от корня репозитория: data/courts_anonymized, data/acts, fixtures, out")
    kinds = st.multiselect("Типы файлов", [".xml", ".pdf", ".json"], default=[".xml", ".pdf", ".json"],
                           help=".json — готовые doc.json (fixtures/, out/)")
    limit = st.number_input("Не больше файлов", 1, 500, 20)
    if st.button("Обработать папку"):
        root = Path(folder)
        files = sorted(p for p in root.rglob("*") if p.suffix.lower() in kinds and "labels" not in p.parts
                       and not (p.suffix.lower() == ".json" and not p.name.startswith("doc_")))
        files = files[: int(limit)]
        _ = st.session_state.pop("batch", None)
        if not root.is_dir():
            st.error(f"Папка «{folder}» не найдена. Путь указывается от корня репозитория, например "
                     "`fixtures` или `data/courts_anonymized`.")
        elif not files:
            st.warning(f"В «{folder}» нет файлов выбранных типов ({', '.join(kinds) or 'типы не выбраны'}).")
        docs, misses = [], []
        bar = st.progress(0.0, text="Начинаю…") if files else None
        for i, p in enumerate(files, 1):
            bar.progress(i / max(len(files), 1), text=f"{i}/{len(files)}: {p.name}")
            d, source = process(p)
            if d:
                docs.append((d, source))
            else:
                misses.append((p.name, source))
        if bar:
            bar.empty()
        if files:
            st.session_state["batch"] = (docs, misses)
    if "batch" in st.session_state:
        docs, misses = st.session_state["batch"]
        if docs:
            summary = [{"документ": d.doc_id, "тип": d.doc_type, "уровень": d.route.lawyer.level,
                        "коды": ", ".join(d.route.lawyer.reason_codes), "ручная проверка": ", ".join(d.route.review.flags),
                        "заполнено": "{} из {}".format(*C.fill_stats(d)), "результат": s} for d, s in docs]
            st.dataframe(pd.DataFrame(summary), hide_index=True, width="stretch")
            b = st.columns(4)
            for col, table in zip(b, ("ocr", "xml")):
                rows = [{k: v for k, v in C.table_row(d).items() if not k.startswith(("route_", "review_"))}
                        for d, _ in docs if d.table == table]
                col.download_button(f"{table}.csv ({len(rows)})", C.rows_to_csv(rows), f"{table}.csv", "text/csv",
                                    disabled=not rows, width="stretch")
                col.download_button(f"{table}.xlsx", C.rows_to_xlsx(rows, table), f"{table}.xlsx",
                                    disabled=not rows, width="stretch")
            routing = [C.table_row(d) | {"doc_id": d.doc_id} for d, _ in docs]
            b[2].download_button("Маршруты, CSV", C.rows_to_csv(
                [{k: r[k] for k in ("doc_id", "route_level", "route_codes", "review_flags")} for r in routing]),
                "routing.csv", "text/csv", width="stretch")
        if misses:
            with st.expander(f"Не обработано: {len(misses)}"):
                st.dataframe(pd.DataFrame(misses, columns=["файл", "почему"]), hide_index=True,
                             width="stretch")

with tab_reg:
    rows, source = C.registry_rows(out_dir)
    if not rows:
        st.info(f"В {out_dir}/ ещё нет registry.csv и routing.csv — запустите make run-all.")
    else:
        df = pd.DataFrame(rows)
        st.caption(f"Источник: `{out_dir}/{source}` — что обработано, куда направлено и ушло ли письмо.")
        m = st.columns(4)
        lv = df["route_level"].value_counts()
        m[0].metric("L1 · срочно", int(lv.get("L1", 0)))
        m[1].metric("L2 · нужно действие", int(lv.get("L2", 0)))
        m[2].metric("L3 · в реестр", int(lv.get("L3", 0)))
        m[3].metric("На ручную проверку", int((df.get("review_flags", pd.Series(dtype=str)).fillna("") != "").sum()))
        f1, f2, f3 = st.columns(3)
        levels = f1.multiselect("Уровень", ["L1", "L2", "L3"], default=["L1", "L2", "L3"])
        all_flags = sorted({f for s in df.get("review_flags", pd.Series(dtype=str)).fillna("") for f in s.split(";") if f})
        flags = f2.multiselect("Флаг проверки", all_flags)
        mail_states = sorted(df["mail_sent"].dropna().unique()) if "mail_sent" in df else []
        mails = f3.multiselect("Письмо", mail_states, default=mail_states)
        view = df[df["route_level"].isin(levels)]
        if flags:
            view = view[view["review_flags"].fillna("").apply(lambda s: any(f in s.split(";") for f in flags))]
        if mails:
            view = view[view["mail_sent"].isin(mails)]
        st.dataframe(view, hide_index=True, width="stretch")
        st.download_button("Скачать реестр, CSV", C.rows_to_csv(view.to_dict("records")), source, "text/csv")

with tab_q:
    metrics_md, report_md = out_dir / "metrics.md", out_dir / "report.md"
    hist = out_dir / "metrics_history.csv"
    if hist.exists():
        h = pd.read_csv(hist, encoding="utf-8-sig")
        h = h[h["slice"].isin(["все", "XML ФССП", "PDF электронные", "PDF сканы", "holdout-set"])]
        if not h.empty:
            import altair as alt  # pylint: disable=import-outside-toplevel  # ставится вместе со streamlit
            st.markdown("#### Точность ключевых реквизитов по прогонам")
            h = h.assign(key=h["key_strict"] * 100,
                         прогон=pd.to_datetime(h["run_at"]).dt.strftime("%d.%m %H:%M"))
            chart = (alt.Chart(h).mark_line(point=alt.OverlayMarkDef(size=70))
                     .encode(x=alt.X("прогон:N", sort=None, title=None, axis=alt.Axis(labelAngle=0)),
                             y=alt.Y("key:Q", title="KEY strict, %", scale=alt.Scale(domain=[0, 100])),
                             color=alt.Color("slice:N", title="срез"),
                             tooltip=["прогон", "slice", alt.Tooltip("key:Q", format=".1f"), "commit", "llm_mode"])
                     .properties(height=260))
            st.altair_chart(chart)
            if h["прогон"].nunique() == 1:
                st.caption("Пока один прогон — линия появится со вторым. Каждый make score добавляет точку.")
    def _demote(md: str) -> str:              # заголовки отчётов на ступень ниже вкладки
        return re.sub(r"^(#{1,3}) ", lambda m: "#" * (len(m.group(1)) + 2) + " ", md, flags=re.M)

    if metrics_md.exists():
        st.markdown(_demote(metrics_md.read_text(encoding="utf-8")))
    else:
        st.info("Метрик ещё нет — make score после полного прогона.")
    if report_md.exists():
        with st.expander("Отчёт сверки: ожидаемое vs извлечённое", expanded=False):
            st.markdown(_demote(report_md.read_text(encoding="utf-8")))
    if (out_dir / "diff.xlsx").exists():
        st.download_button("Скачать diff.xlsx (промахи подсвечены)", (out_dir / "diff.xlsx").read_bytes(), "diff.xlsx")
