from pylib.inventory import Item


def test_total():
    assert Item("a", 2).total(3) == 6
