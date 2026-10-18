"""Tiny math utilities. Contains seeded bugs for the dark-factory demo."""


def sum_range(n):
    # BUG A (trivial): off-by-one — should be range(1, n+1)
    total = 0
    if n <= 0:
        return 0
    for i in range(1, n + 1):
        total += i
    return total


def is_even(x):
    # BUG B (trivial): wrong operator — should be == 0
    return x % 2 == 1


def safe_len(xs):
    # BUG C (trivial): missing None guard
    return len(xs)


def discount_price(price, percent):
    # BUG D (nasty): compounding instead of flat, plus unclear negative-input policy.
    # Not auto-fixable with a small localized diff; needs human judgement.
    result = price
    for _ in range(int(percent)):
        result = result - result * 0.01
    return round(result, 2)
