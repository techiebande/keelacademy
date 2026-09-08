"""Fixture repo for the S0.3 done-when: one passing test, one deliberately failing."""


def add(a: int, b: int) -> int:
    return a + b


def test_add_passes():
    assert add(2, 3) == 5


def test_add_deliberately_failing():
    # Deliberately wrong expectation so the CLI must name this nodeid.
    assert add(2, 2) == 5, "fixture: this test is meant to fail"
