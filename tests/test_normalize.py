"""Symbol/format normalization (SPEC §4 false-positive controls)."""

from pathlib import Path

from comparator.config import Config
from comparator.normalize import Normalizer

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def _norm():
    return Normalizer(Config.load(CONFIG_PATH))


def test_symbol_equivalences_collapse():
    n = _norm()
    assert n.equal("1/2", "½")
    assert n.equal("DIA", "Ø")
    assert n.equal("Ø10", "DIA10")
    assert n.equal("90DEG", "90°")
    assert n.equal("+/-0.1", "±0.1")


def test_trailing_zero_and_decimal_equivalence():
    n = _norm()
    assert n.equal("1.50", "1.5")
    assert n.equal("1.500", "1.5")
    assert n.equal("2.0", "2")
    assert n.equal("1,5", "1.5")


def test_whitespace_collapse():
    n = _norm()
    assert n.equal("SECTION  A-A", "SECTION A-A")


def test_genuinely_different_strings_not_equal():
    n = _norm()
    assert not n.equal("1/2", "1#8")
    assert not n.equal("R5.00", "R6.00")
    assert n.edit_distance_norm("1/2", "1#8") > 0.0
