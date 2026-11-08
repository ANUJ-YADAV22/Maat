import pytest

from maat.agent.tools import calculator


@pytest.mark.parametrize(
    "expr,val", [("12*4", 48), ("3.5*8+2", 30), ("(1+2)**2", 9), ("-4+10/4", -1.5)]
)
def test_calculator(expr: str, val: float) -> None:
    assert calculator(expr) == val


@pytest.mark.parametrize("expr", ["__import__('os')", "1; 2", "abs(3)", "2**99", "a+1", "1/0"])
def test_calculator_rejects_unsafe(expr: str) -> None:
    with pytest.raises((ValueError, SyntaxError, ZeroDivisionError)):
        calculator(expr)
