import pytest

from maat.checkers import run_checker


@pytest.mark.parametrize(
    "checker,answer,trace,ok",
    [
        ({"type": "contains_all", "items": ["Critical"]}, "it is critical", None, True),
        ({"type": "contains_all", "items": ["a", "b"]}, "only a", None, False),
        ({"type": "regex", "pattern": r"\bis 47\b"}, "x is 47.", None, True),
        ({"type": "regex", "pattern": r"\bis 47\b"}, "x is 147.", None, False),
        ({"type": "numeric_close", "expected": 2500}, "Result: 2500 mm", None, True),
        ({"type": "numeric_close", "expected": 2500}, "Result: 2.5 mm", None, False),
        ({"type": "numeric_close", "expected": 1}, "no number", None, False),
        ({"type": "tool_called", "tool": "t"}, "", {"tool_calls": [{"tool": "t"}]}, True),
        ({"type": "tool_called", "tool": "t"}, "", {"tool_calls": []}, False),
        (
            {"type": "checklist_covers", "items": ["a", "b"]},
            "CHECKLIST:\n- a\n- b\n- c",
            None,
            True,
        ),
        ({"type": "checklist_covers", "items": ["a", "b"]}, "CHECKLIST:\n- a", None, False),
        (
            {"type": "fields_present", "fields": ["x"], "values": {"x": "1"}},
            '{"x": "1"}',
            None,
            True,
        ),
        (
            {"type": "fields_present", "fields": ["x"], "values": {"x": "2"}},
            '{"x": "1"}',
            None,
            False,
        ),
        ({"type": "fields_present", "fields": ["x"]}, "not json", None, False),
    ],
)
def test_checkers(checker, answer, trace, ok) -> None:
    assert run_checker(checker, answer, trace) is ok


def test_unknown_checker() -> None:
    with pytest.raises(ValueError):
        run_checker({"type": "nope"}, "")
