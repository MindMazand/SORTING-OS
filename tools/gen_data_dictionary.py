#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — Data dictionary generator (dev tool, NOT part of the product).

Builds a database from schema_v001 + seed_v001 + migrations, then writes
docs/DATA_DICTIONARY_FA.md straight from the live schema. Nothing in the
document is hand-typed, so it cannot drift from the shipped SQL.

Usage:  python3 tools/gen_data_dictionary.py
"""
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_database as v  # noqa: E402

OUT = os.path.join(v.ROOT, "docs", "DATA_DICTIONARY_FA.md")


def main():
    tmp = tempfile.mkdtemp(prefix="mazandasht_dict_")
    con = v.build_db(os.path.join(tmp, "dict.db"))

    version = con.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    views = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='view' ORDER BY name")]
    triggers = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name")]
    indexes = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='index' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    notes = {}
    for t, c, st, nt in con.execute(
            "SELECT table_name, column_name, status, note FROM schema_field_notes"):
        notes[(t, c)] = (st, nt)
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}

    L = []
    a = L.append
    a("# فرهنگ داده — مازندشت (تولیدشده خودکار)")
    a("")
    a("> این فایل **دستی نوشته نشده** است. با `python3 tools/gen_data_dictionary.py`")
    a("> از اسکیمای واقعی تولید می‌شود؛ اگر با کد اختلاف داشت، کد درست است و این فایل")
    a("> باید دوباره تولید شود. مبنای فصل ۱۸ سند اصلی (Data Dictionary).")
    a("")
    a(f"- نسخه اسکیما: **v{version}**")
    a(f"- تعداد جدول: **{len(tables)}** · ویو: **{len(views)}** · تریگر: **{len(triggers)}** · ایندکس: **{len(indexes)}**")
    a("")
    a("## قواعد ثابت (روی همه جدول‌ها)")
    a("")
    a("| قاعده | معنا |")
    a("|---|---|")
    a("| پول | همیشه `INTEGER` ریال. هیچ `REAL` برای پول. تومان فقط برای نمایش (`/10`). |")
    a("| وزن | همیشه `INTEGER` گرم. حداکثر ۳ رقم اعشار کیلوگرم در ورودی. |")
    a("| خالی ≠ صفر | مقدار ثبت‌نشده با پرچم `*_known` یا `NULL` بیان می‌شود، نه `0`. |")
    a("| شماره نمایشی ≠ شناسه | `code` پایدار و تغییرناپذیر است؛ `doc_number` قابل‌ویرایش. |")
    a("| سند تأییدشده | با تریگر قابل UPDATE/DELETE نیست؛ اصلاح فقط با سند معکوس. |")
    a("| موجودی و مانده | هرگز ستون ذخیره‌شده نیست؛ از لجر مشتق می‌شود. |")
    a("")
    a("## ویوهای مشتق‌شده")
    a("")
    for x in views:
        a(f"- `{x}`")
    a("")
    a("## تریگرهای محافظ")
    a("")
    for x in triggers:
        a(f"- `{x}`")
    a("")
    a("## جدول‌ها")
    a("")
    for t in tables:
        a(f"### `{t}`  — {counts[t]} ردیف در دیتابیس تازه")
        a("")
        a("| ستون | نوع | الزام | پیش‌فرض | یادداشت |")
        a("|---|---|---|---|---|")
        for cid, name, ctype, notnull, dflt, pk in con.execute(
                f"PRAGMA table_info({t})"):
            req = "PK" if pk else ("الزامی" if notnull else "اختیاری")
            note = ""
            if (t, name) in notes:
                st, nt = notes[(t, name)]
                note = f"**{st}** — {nt}"
            a(f"| `{name}` | {ctype or '—'} | {req} | "
              f"{'' if dflt is None else '`' + str(dflt) + '`'} | {note} |")
        fks = con.execute(f"PRAGMA foreign_key_list({t})").fetchall()
        if fks:
            a("")
            a("کلیدهای خارجی: " + " · ".join(
                f"`{r[3]}` → `{r[2]}.{r[4]}`" for r in fks))
        a("")
    a("## ایندکس‌ها")
    a("")
    for x in indexes:
        a(f"- `{x}`")
    a("")

    text = "\n".join(L)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    con.close()
    print(f"wrote {OUT} ({len(text.splitlines())} lines, schema v{version}, "
          f"{len(tables)} tables)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
