"""Regression suite. The 'reproducing test' for each bug is injected at runtime
by the harness as test_repro_<bug_id>."""
from calculator import sum_range, is_even, safe_len, discount_price


def test_sum_range_small():
    assert sum_range(3) == 6  # 1+2+3


def test_sum_range_one():
    assert sum_range(1) == 1


def test_is_even_zero():
    assert is_even(0) is True


def test_is_even_odd():
    assert is_even(3) is False


def test_safe_len_list():
    assert safe_len([1, 2, 3]) == 3


def test_safe_len_none():
    assert safe_len(None) == 0


def test_discount_price_zero():
    assert discount_price(100, 0) == 100


def test_discount_price_ten():
    # Business spec: flat 10% off => 90.00
    assert discount_price(100, 10) == 90.00

def test_repro_bug_e():
    from calculator import sum_range
    assert sum_range(0) == 0
