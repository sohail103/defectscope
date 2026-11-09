from . import inventory


def price_for(sku, qty):
    base = 10 if qty < 100 else 8
    return base * qty


def uses_inventory():
    return inventory.Item("x", 1)
