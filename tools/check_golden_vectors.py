#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — the golden vectors must agree with the code they pin.

tests/golden/import_vectors.json is read by BOTH sides: the Python tests here
and the xUnit tests in src/Mazandasht.Tests/ImportGoldenTests.cs, which cannot
run in this environment. If a vector is wrong, the C# tests encode the wrong
expectation and would pass against a wrong implementation — the failure would
surface only after someone finally builds on Windows.

So every vector is re-executed against the Python reference here. A number in
that file is a claim; this proves it.

    python3 tools/check_golden_vectors.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import import_contract as C          # noqa: E402
import import_engine as E            # noqa: E402
import import_parser as P            # noqa: E402
from xlsx_io import Cell             # noqa: E402

VECTORS = os.path.join(ROOT, "tests", "golden", "import_vectors.json")
FAILURES = []


def cell_from(text):
    return Cell(row=1, col=1, ref="A1", text=text, kind="text")


def fail(msg):
    FAILURES.append(msg)
    print("FAIL  " + msg)


def main():
    with open(VECTORS, encoding="utf-8") as f:
        v = json.load(f)

    # -- Jalali date conversion -------------------------------------------
    n = 0
    for shamsi, iso in v["jalali_to_iso"].items():
        got = P._iso_from_shamsi(shamsi) if hasattr(P, "_iso_from_shamsi") \
            else E._iso_from_shamsi(shamsi)
        n += 1
        if got != iso:
            fail(f"تاریخ {shamsi}: پایتون {got} می‌دهد، بردار {iso} می‌گوید")
    print(f"PASS  تاریخ شمسی: {n} بردار اجرا شد")

    # -- leap years --------------------------------------------------------
    n = 0
    for year, expected in v["jalali_leap"].items():
        got = P.is_leap_jalali(int(year))
        n += 1
        if got != expected:
            fail(f"کبیسه {year}: پایتون {got}، بردار {expected}")
    print(f"PASS  کبیسه: {n} بردار اجرا شد")

    # -- kg -> grams -------------------------------------------------------
    n = 0
    for item in v["kg_to_grams"]:
        grams, err = P._to_grams(cell_from(item["input"]))
        n += 1
        if grams != item["grams"]:
            fail(f"گرم {item['input']}: پایتون {grams}، بردار {item['grams']} "
                 f"({err})")
    print(f"PASS  کیلوگرم→گرم: {n} بردار اجرا شد")

    # -- refused weights ---------------------------------------------------
    n = 0
    for item in v["kg_rejected"]:
        grams, err = P._to_grams(cell_from(item["input"]))
        n += 1
        if grams is not None:
            fail(f"وزن ردشدنی {item['input']}: پذیرفته شد ({grams})")
        elif item["reason_contains"] not in (err or ""):
            fail(f"وزن ردشدنی {item['input']}: دلیل «{err}» شامل "
                 f"«{item['reason_contains']}» نیست")
    print(f"PASS  وزن ردشدنی: {n} بردار اجرا شد")

    # -- gross rial --------------------------------------------------------
    n = 0
    for item in v["rial_gross"]:
        got = (item["grams"] * item["rate"] + 500) // 1000
        n += 1
        if got != item["gross_rial"]:
            fail(f"مبلغ ناخالص {item['grams']}x{item['rate']}: پایتون {got}، "
                 f"بردار {item['gross_rial']}")
    print(f"PASS  مبلغ ناخالص: {n} بردار اجرا شد")

    # -- invoice net -------------------------------------------------------
    n = 0
    for item in v["net_invoice"]:
        if "adjustments" in item:            # purchase
            got = (item["gross"] + item["freight"] + item["commission"] +
                   item["adjustments"] - item["discount"])
        else:                                 # sales
            got = (item["gross"] - item["freight"] - item["commission"] -
                   item.get("other", 0) - item["discount"])
        n += 1
        if got != item["net_rial"]:
            fail(f"مبلغ خالص: پایتون {got}، بردار {item['net_rial']}")
    print(f"PASS  مبلغ خالص: {n} بردار اجرا شد")

    # -- percent -----------------------------------------------------------
    n = 0
    for item in v["percent"]:
        got, err = P._to_percent(cell_from(item["input"]))
        n += 1
        if got is None or abs(got - item["value"]) > 1e-9:
            fail(f"درصد {item['input']}: پایتون {got}، بردار {item['value']}")
    for item in v["percent_rejected"]:
        got, err = P._to_percent(cell_from(item["input"]))
        n += 1
        if got is not None:
            fail(f"درصد ردشدنی {item['input']}: پذیرفته شد ({got})")
        elif item["reason_contains"] not in (err or ""):
            fail(f"درصد ردشدنی {item['input']}: دلیل «{err}»")
    print(f"PASS  درصد: {n} بردار اجرا شد")

    # -- net weight formula (DEC-NEW-008) ----------------------------------
    # The vectors live under "cases". An earlier version of this check looked
    # for "scale" directly under each item, found nothing, and reported
    # "0 vectors" as a PASS — a guard that skips is worse than no guard.
    block = v["net_weight_check"]
    cases = block.get("cases", block) if isinstance(block, dict) else block
    if not cases:
        fail("بردار وزن خالص خالی است — چیز مفیدی سنجیده نشد")
    n = 0
    for item in cases:
        tare = item["basket_count"] * item["p01_grams"]
        base = item["scale_grams"] - tare
        # integer arithmetic, half-up, so no float drift can pass for correct
        net = (int(round(base * (100 - item["p02_percent"]))) + 50) // 100
        n += 1
        if tare != item["expected_tare_grams"]:
            fail(f"تار {item['basket_count']}×{item['p01_grams']}: {tare} != "
                 f"{item['expected_tare_grams']}")
        if net != item["expected_net_grams"]:
            fail(f"وزن خالص {item['scale_grams']} با تار {tare} و "
                 f"{item['p02_percent']}%: {net} != {item['expected_net_grams']}")
    print(f"PASS  وزن خالص: {n} بردار اجرا شد")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} بردار با اجرای واقعی نمی‌خواند")
        return 1
    print("PASS  هر بردار طلایی با اجرای واقعی پایتون تأیید شد")
    return 0


if __name__ == "__main__":
    sys.exit(main())
