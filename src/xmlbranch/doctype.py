"""DocType (код постановления ФССП) → DocType2 (формулировка из разметки)."""

from __future__ import annotations

import logging

log = logging.getLogger("xmlbranch")

DOCTYPE2: dict[str, str] = {
    "O_IP_ACT_END_END": "Постановление об окончании ИП",
    "O_IP_ACT_END_STOP": "Постановление о прекращении ИП",
    "O_IP_ACT_REOPEN_CANCEL": "Постановление об отказе в возбуждении ИП",
    "O_IP_ACT_RETURN": "Постановление об окончании и возвращении ИД",
    "O_IP_RES_REOPEN": "Постановление о возбуждении",
}


def doctype2(code: str) -> str:
    """Неизвестный код — пустая строка и warning (дальше его подхватит UNCLASSIFIED в правилах)."""
    value = DOCTYPE2.get(code.strip(), "")
    if not value:
        log.warning("неизвестный DocType %r — DocType2 пустой", code)
    return value
