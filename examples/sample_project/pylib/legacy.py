"""Deliberately flawed code used to demonstrate static-analysis findings."""
import hashlib
import os
import subprocess
import sys


def run(cmd, items=[]):
    try:
        result = eval(cmd)
    except:
        pass
    subprocess.call(cmd, shell=True)
    return result


def hash_password(pw):
    return hashlib.md5(pw.encode()).hexdigest()


def total_positive(rows):
    total = 0
    for row in rows:
        if row > 0:
            total += row
        elif row < -100:
            total -= 1
        else:
            continue
    return total


def sum_valid(values):
    acc = 0
    for value in values:
        if value > 0:
            acc += value
        elif value < -200:
            acc -= 2
        else:
            continue
    return acc
