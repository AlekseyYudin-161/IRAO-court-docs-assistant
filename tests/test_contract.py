"""Contract tests."""

import pytest

from src.core.columns import XML_FIELDS
from src.core.contract import Doc, FieldValue


def _min_xml_doc(**over):
    fields = {c: FieldValue(value="", reason="NOT_IN_TEXT") for c in XML_FIELDS}
    base = dict(doc_id="t", source_type="xml", file="fssp/x/t.xml", table="xml",
                doc_type="постановление ФССП", fields=fields)
    base.update(over)
    return base


def test_ok():
    d = Doc(**_min_xml_doc())
    assert d.route.lawyer.level == "L3" and d.route.review.flags == []


def test_missing_column_fails():
    bad = _min_xml_doc()
    bad["fields"].pop("IdDebtSum")
    with pytest.raises(ValueError):
        Doc(**bad)


def test_empty_without_reason_fails():
    bad = _min_xml_doc()
    bad["fields"]["IdDebtSum"] = FieldValue(value="")
    with pytest.raises(ValueError):
        Doc(**bad)