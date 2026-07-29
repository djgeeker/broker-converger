"""Leak scanner: does anything in this repo reveal the private system?

Run before every push:

    python3 tools/leak_scan.py

Deny-list driven, not eyeball driven. Three passes:
  1. strategy parameters and result numbers
  2. internal document / repository / leg names
  3. account identifiers, absolute paths, and stray non-English in code
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCAN_SUFFIXES = {".py", ".md", ".toml", ".txt", ".cfg", ".yml", ".yaml"}
SKIP_DIRS = {".git", "__pycache__", ".venv", "dist", "build", ".pytest_cache"}

# --- pass 1: strategy parameters and published result numbers ---------------
# Word-boundary regexes so 0.25 as a tick size does not trip on "2.5".
PARAMETERS = [
    (r"\b(29131|29229\.25|29220\.55|29200\.25|28014|30599|28408)\b", "real market prices"),
    (r"\b(1269|6801138\.63|59\.36|1963|2086|5221|63\.82|44\.68|65\.94|46\.46)\b", "backtest result numbers"),
    (r"\b(0\.0075|0\.015)\b", "protective stop rates"),
    (r"\b1\.005\b", "trend filter multiplier"),
    (r"\b(SMA\s?200|sma300|SMA300)\b", "moving-average parameters"),
    (r"\b(0\.25,\s*0\.15,\s*0\.05|1\.0,\s*1\.3,\s*1\.6)\b", "tranche fractions/multipliers"),
    (r"\b1[56]:[0-9]{2}\b", "signal clock times"),
    # datetime(y, m, d, 16, 29, ...) — clock times hide in positional args too.
    (r"datetime\([^)]*,\s*1[4-6]\s*,\s*(29|30|59|0)\s*[,)]", "signal clock in datetime()"),
    (r"\bentry_hour\b|\bexit_hour\b|\bentry_minute\b", "signal clock field names"),
    (r"\b(volume_ratio|lookback\s*=\s*96|trail_atr|initial_stop_atr)\b", "leg parameter names"),
]

# --- pass 2: internal names -------------------------------------------------
INTERNAL = [
    (r"\b(fvg|FVG|closemom|volbreak|afterhours)\b", "private leg names"),
    (r"(quant_core_rs|quant_backtest|naked-k-dashboard|quant_runtime)", "private repo/module names"),
    (r"(股票交易系统|量化策略知识库|研究报告时间线|同步登记表|工程待办|权威参数总表)", "internal document names"),
    (r"补[一二三四五六七八九十百]+", "internal document section ids"),
]

# --- pass 3: identifiers, paths, stray non-English --------------------------
IDENTIFIERS = [
    (r"\bDUP?[0-9]{6,}\b", "account numbers"),
    (r"/Users/[A-Za-z0-9_]+/", "absolute home paths"),
    (r"\b(MNQ|ES|GC)\b", "instrument symbols"),
]
CJK = re.compile(r"[一-鿿]")


def files():
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name == "leak_scan.py":       # the deny-list itself
            continue
        yield path


def scan(rules, label):
    hits = []
    for path in files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern, why in rules:
            for m in re.finditer(pattern, text):
                line = text[: m.start()].count("\n") + 1
                hits.append((path.relative_to(ROOT), line, why, m.group(0)))
    print(f"\n=== pass: {label} === {len(hits)} hit(s)")
    for path, line, why, text in hits[:40]:
        print(f"  {path}:{line}  [{why}] {text!r}")
    return hits


def scan_cjk():
    """Chinese is fine in README (bilingual by design), not in code."""
    hits = []
    for path in files():
        if path.name == "README.md":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in CJK.finditer(text):
            line = text[: m.start()].count("\n") + 1
            hits.append((path.relative_to(ROOT), line, "CJK outside README", m.group(0)))
            break                              # one report per file is enough
    print(f"\n=== pass: non-English in code === {len(hits)} hit(s)")
    for path, line, why, text in hits:
        print(f"  {path}:{line}  [{why}] {text!r}")
    return hits


def main() -> int:
    total = 0
    total += len(scan(PARAMETERS, "strategy parameters / results"))
    total += len(scan(INTERNAL, "internal names"))
    total += len(scan(IDENTIFIERS, "identifiers & paths"))
    total += len(scan_cjk())
    print()
    if total:
        print(f"BLOCKED: {total} potential leak(s). Fix before pushing.")
        return 1
    print("CLEAN: nothing on the deny-list appears in this repo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
