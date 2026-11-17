"""Mapping tool rules onto DefectScope's diagnostic categories.

Categories come only from the tool's own rule/CWE identifiers. Rules we do not recognise fall back to
"maintainability" instead of guessing a bug type.
"""
from __future__ import annotations

from typing import Optional

# --- cppcheck: CWE first (most precise), then id prefixes
CWE_CATEGORY = {
    476: "null_pointer", 690: "null_pointer",
    119: "buffer_bounds", 120: "buffer_bounds", 121: "buffer_bounds", 122: "buffer_bounds", 125: "buffer_bounds",
    126: "buffer_bounds", 129: "buffer_bounds", 786: "buffer_bounds", 787: "buffer_bounds", 788: "buffer_bounds",
    401: "resource_management", 404: "resource_management", 459: "resource_management", 772: "resource_management",
    775: "resource_management",
    415: "memory_safety", 416: "memory_safety", 590: "memory_safety", 762: "memory_safety", 825: "memory_safety",
    457: "uninitialized", 908: "uninitialized", 665: "uninitialized",
    561: "control_flow", 570: "suspicious_condition", 571: "suspicious_condition", 398: "suspicious_condition",
    369: "suspicious_condition", 682: "suspicious_condition", 628: "type_problems", 686: "type_problems",
    704: "type_problems", 758: "type_problems", 190: "type_problems", 191: "type_problems", 197: "type_problems",
    134: "security", 78: "security", 327: "security",
}
CPPCHECK_ID_PREFIX = [
    ("nullPointer", "null_pointer"), ("arrayIndex", "buffer_bounds"), ("bufferAccess", "buffer_bounds"),
    ("outOfBounds", "buffer_bounds"), ("negativeIndex", "buffer_bounds"), ("memleak", "resource_management"),
    ("resourceLeak", "resource_management"), ("leak", "resource_management"), ("doubleFree", "memory_safety"),
    ("deallocuse", "memory_safety"), ("deallocDealloc", "memory_safety"), ("mismatchAlloc", "memory_safety"),
    ("danglingLifetime", "memory_safety"), ("returnDanglingLifetime", "memory_safety"),
    ("uninit", "uninitialized"), ("unreachable", "control_flow"), ("unusedStructMember", "maintainability"),
    ("unusedVariable", "maintainability"), ("unusedFunction", "maintainability"), ("unreadVariable", "maintainability"),
    ("duplicate", "suspicious_condition"), ("knownCondition", "suspicious_condition"),
    ("identical", "suspicious_condition"), ("comparison", "suspicious_condition"), ("incorrect", "type_problems"),
    ("invalid", "type_problems"), ("wrongPrintf", "type_problems"), ("invalidPrintf", "type_problems"),
    ("integerOverflow", "type_problems"), ("shiftTooMany", "type_problems"), ("syntaxError", "type_problems"),
    ("zerodiv", "suspicious_condition"), ("va_", "type_problems"),
]


def cppcheck_category(rule: str, cwe: Optional[int]) -> str:
    if cwe in CWE_CATEGORY:
        return CWE_CATEGORY[cwe]
    for prefix, cat in CPPCHECK_ID_PREFIX:
        if rule.startswith(prefix):
            return cat
    return "maintainability"


# --- clang-tidy / clang static analyzer
CLANG_PREFIX = [
    ("clang-analyzer-core.NullDereference", "null_pointer"), ("clang-analyzer-core.CallAndMessage", "null_pointer"),
    ("clang-analyzer-core.uninitialized", "uninitialized"), ("clang-analyzer-core.UndefinedBinaryOperatorResult", "uninitialized"),
    ("clang-analyzer-core.DivideZero", "suspicious_condition"), ("clang-analyzer-core.StackAddressEscape", "memory_safety"),
    ("clang-analyzer-unix.Malloc", "resource_management"), ("clang-analyzer-unix.MismatchedDeallocator", "memory_safety"),
    ("clang-analyzer-cplusplus.NewDelete", "memory_safety"), ("clang-analyzer-cplusplus.NewDeleteLeaks", "resource_management"),
    ("clang-analyzer-unix.cstring", "buffer_bounds"), ("clang-analyzer-security.insecureAPI", "security"),
    ("clang-analyzer-security.ArrayBound", "buffer_bounds"), ("clang-analyzer-alpha.security", "buffer_bounds"),
    ("clang-analyzer-deadcode", "maintainability"), ("clang-analyzer-security", "security"),
    ("bugprone-use-after-move", "memory_safety"), ("bugprone-sizeof", "type_problems"), ("bugprone-signed-char", "type_problems"),
    ("bugprone-integer-division", "type_problems"), ("bugprone-narrowing", "type_problems"),
    ("bugprone-branch-clone", "suspicious_condition"), ("bugprone-infinite-loop", "control_flow"),
    ("bugprone-macro", "suspicious_condition"), ("bugprone-suspicious", "suspicious_condition"),
    ("bugprone-unused-return-value", "suspicious_condition"), ("bugprone-assignment-in-if", "suspicious_condition"),
    ("bugprone-exception-escape", "exception_handling"), ("bugprone-empty-catch", "exception_handling"),
    ("cert-err", "exception_handling"), ("cert-", "security"), ("bugprone-", "suspicious_condition"),
    ("clang-diagnostic-", "type_problems"), ("clang-analyzer-", "suspicious_condition"),
]


def clang_category(check: str) -> str:
    for prefix, cat in CLANG_PREFIX:
        if check.startswith(prefix):
            return cat
    return "maintainability"


# --- Ruff / Pylint / Bandit
def ruff_category(code: str) -> str:
    if code.startswith("S"):
        return "security"
    if code in {"E722", "BLE001", "B012"} or code.startswith(("TRY",)):
        return "exception_handling"
    if code.startswith("E9") or code in {"F821", "F822", "F823", "F632", "F702", "F706", "PLE0101", "PLE1142"}:
        return "type_problems"
    if code in {"F811", "F402", "F601", "F602", "B015", "B018", "B011", "PLW0127", "PLW0129", "F631", "F632"} \
            or code.startswith(("B0", "PLW01")):
        return "suspicious_condition"
    if code.startswith("PLE") or code in {"F5", "F6", "F7"} or code.startswith(("F5", "F6", "F7")):
        return "type_problems"
    if code.startswith(("F4", "F8")) or code in {"E401", "E402", "E701", "E702", "E711", "E712", "E713", "E714", "E731"}:
        return "maintainability"
    return "maintainability"


PYLINT_CATEGORY = {
    "bare-except": "exception_handling", "broad-except": "exception_handling", "broad-exception-caught": "exception_handling",
    "raising-bad-type": "exception_handling", "bad-except-order": "exception_handling", "try-except-raise": "exception_handling",
    "lost-exception": "exception_handling", "return-in-finally": "exception_handling",
    "dangerous-default-value": "suspicious_condition", "comparison-with-itself": "suspicious_condition",
    "self-assigning-variable": "suspicious_condition", "duplicate-key": "suspicious_condition",
    "redundant-keyword-arg": "suspicious_condition", "eval-used": "security", "exec-used": "security",
    "unreachable": "control_flow", "using-constant-test": "suspicious_condition", "unnecessary-pass": "maintainability",
    "undefined-variable": "type_problems", "used-before-assignment": "uninitialized", "unbalanced-tuple-unpacking": "type_problems",
    "no-member": "type_problems", "not-callable": "type_problems", "unsubscriptable-object": "type_problems",
    "too-many-function-args": "type_problems", "no-value-for-parameter": "type_problems", "unexpected-keyword-arg": "type_problems",
    "unused-variable": "maintainability", "unused-import": "maintainability", "unused-argument": "maintainability",
    "arguments-differ": "type_problems", "attribute-defined-outside-init": "maintainability",
    "possibly-used-before-assignment": "uninitialized",
}


def pylint_category(symbol: str, msg_type: str) -> str:
    if symbol in PYLINT_CATEGORY:
        return PYLINT_CATEGORY[symbol]
    return "type_problems" if msg_type in ("error", "fatal") else "maintainability"


def severity_from(label: str) -> str:
    label = label.lower()
    if label in ("error", "high", "fatal"):
        return "high"
    if label in ("warning", "medium"):
        return "warning"
    return "info"
