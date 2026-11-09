"""Inventory management (sample code for DefectScope)."""
from . import pricing
import json


class Item:
    def __init__(self, sku, qty):
        self.sku = sku
        self.qty = qty

    def total(self, price):
        return self.qty * price

    def restock(self, n):
        self.qty += n


class Inventory:
    def __init__(self):
        self.items = {}
        self.log = []

    def add(self, item):
        if item.sku in self.items:
            self.items[item.sku].restock(item.qty)
        else:
            self.items[item.sku] = item
        self.log.append(("add", item.sku))

    def value(self):
        total = 0
        for sku, item in self.items.items():
            total += pricing.price_for(sku, item.qty)
        return total

    def report(self, verbose, fmt, limit, offset, filters, sort_key):
        out = []
        for sku, item in self.items.items():
            if filters and sku not in filters:
                continue
            if verbose:
                if fmt == "json":
                    for k in range(3):
                        if k > 1 and item.qty > 0 and sku:
                            try:
                                out.append(json.dumps({"sku": sku}))
                            except ValueError:
                                out.append("?")
                else:
                    out.append(sku)
            elif item.qty > limit or item.qty < offset:
                out.append(sku)
        return sorted(out, key=sort_key)


def simple(a):
    if a:
        return 1
    return 0
