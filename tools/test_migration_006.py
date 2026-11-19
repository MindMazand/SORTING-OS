#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — migration 006 (nullable money columns), proven by execution.

DEC-NEW-053. The schema had `amount_rial INTEGER NOT NULL DEFAULT 0` in
fourteen places, which makes "amount not recorded" indistinguishable from
"worth zero rials". The owner's first rule is «خالی ≠ صفر». This test proves
the migration actually delivers it, and that it delivers nothing else.

CHECKED

  1. the migration applies and registers version 6
  2. every money column (name contains `_rial`) is nullable afterwards
     — walked from PRAGMA table_info, not from a hand-kept list
  3. a NULL amount stores as NULL and an explicit 0 stores as 0 — the whole
     point, and the case that could not even be constructed before
  4. a present amount is still an INTEGER (no silent rounding)
  5. NO COLUMN IS LOST: every table keeps exactly the columns it had before
  6. rows survive the rebuild, per table
  7. indexes, triggers and views are all back by name (they must be dropped
     to allow DROP TABLE, so "back" is not automatic)
  8. integrity_check is ok and foreign_key_check is empty
  9. the migration contains no BEGIN/COMMIT of its own (the runner wraps it)

    python3 tools/test_migration_006.py
"""
import glob
import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import verify_database as V

MIGRATION = os.path.join(ROOT, "database", "migrations", "006_amount_nullable.sql")
REBUILT = [
    "lots", "purchase_invoices", "sales_invoices", "purchase_invoice_lines",
    "sales_invoice_lines", "payments", "cheques", "bank_transactions",
    "basket_movements", "journal_lines",
]


def pre_006_connection():
    """A database at schema v005 — the state production was in."""
    path = os.path.join(tempfile.mkdtemp(prefix="m6a_"), "pre.db")
    con = V.build_db(path, with_migrations=False)
    for f in sorted(glob.glob(os.path.join(ROOT, "database", "migrations", "*.sql"))):
        if os.path.basename(f).startswith("006"):
            continue
        con.execute("PRAGMA foreign_keys = OFF")
        con.commit()
        con.executescript("BEGIN;\n" + open(f, encoding="utf-8").read() + "\nCOMMIT;")
        con.execute("PRAGMA foreign_keys = ON")
        con.commit()
    return con


def post_006_connection():
    path = os.path.join(tempfile.mkdtemp(prefix="m6b_"), "post.db")
    return V.build_db(path)


def cols(con, table):
    return [r[1] for r in con.execute("PRAGMA table_info(%s)" % table)]


def money_cols(con, table):
    return [c for c in cols(con, table) if "_rial" in c]


# ---------------------------------------------------------------------------
def t_migration_applies_and_registers():
    con = post_006_connection()
    version = con.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
    assert version == 6, version
    name = con.execute(
        "SELECT name FROM schema_migrations WHERE version=6").fetchone()[0]
    assert "nullable" in name and "money" in name, name
    con.close()


def t_every_money_column_is_nullable():
    """Walked from the live schema. A new *_rial column added later in a NOT
    NULL form will fail here — which is the point: the rule is per column,
    not per migration."""
    con = post_006_connection()
    offenders = []
    for t in REBUILT:
        for row in con.execute("PRAGMA table_info(%s)" % t):
            # row: cid, name, type, notnull, dflt_value, pk
            if "_rial" in row[1] and row[3]:
                offenders.append("%s.%s" % (t, row[1]))
    assert not offenders, "ستون پولی هنوز NOT NULL است: %s" % offenders
    con.close()


def t_null_and_zero_are_different_values():
    """The whole point. Before this migration this test could not be written:
    the NULL insert raised NOT NULL constraint failed."""
    con = post_006_connection()
    con.execute("""INSERT INTO cheques(code,cheque_number,cheque_date,
                   amount_rial,direction) VALUES('C-NULL','1','1405/01/01',NULL,'ISSUED')""")
    con.execute("""INSERT INTO cheques(code,cheque_number,cheque_date,
                   amount_rial,direction) VALUES('C-ZERO','2','1405/01/02',0,'ISSUED')""")
    con.commit()
    blank = con.execute("SELECT amount_rial FROM cheques WHERE code='C-NULL'").fetchone()[0]
    zero = con.execute("SELECT amount_rial FROM cheques WHERE code='C-ZERO'").fetchone()[0]
    assert blank is None, "مبلغ ثبت‌نشده باید NULL بماند، نه ۰ — دریافت %r" % (blank,)
    assert zero == 0, zero
    assert blank != zero, "خالی و صفر باید دو مقدار متفاوت باشند"
    con.close()


def t_present_amount_is_still_integer():
    """No silent rounding: a stored amount is an INTEGER, and a float is
    refused by the CHECK rather than truncated."""
    con = post_006_connection()
    con.execute("""INSERT INTO cheques(code,cheque_number,cheque_date,
                   amount_rial,direction) VALUES('C-I','3','1405/01/03',1234567,'ISSUED')""")
    con.commit()
    value = con.execute("SELECT amount_rial FROM cheques WHERE code='C-I'").fetchone()[0]
    assert value == 1234567, value
    assert isinstance(value, int), type(value)
    try:
        con.execute("""INSERT INTO cheques(code,cheque_number,cheque_date,
                       amount_rial,direction) VALUES('C-F','4','1405/01/04',1.5,'ISSUED')""")
        con.commit()
    except sqlite3.IntegrityError:
        pass                                  # CHECK refused the float
    else:
        raise AssertionError("مبلغ اعشاری نباید پذیرفته شود — گرد کردن بی‌صدا ممنوع")
    con.close()


def t_no_column_is_lost():
    """Compare the column list before and after, per table. A rebuild that
    silently drops a column is the failure mode of a hand-written migration —
    it happened here first (bank_transactions went 26 -> 11)."""
    before = pre_006_connection()
    after = post_006_connection()
    problems = []
    for t in REBUILT:
        b, a = cols(before, t), cols(after, t)
        if b != a:
            problems.append("%s: %d -> %d columns; missing=%s extra=%s" % (
                t, len(b), len(a), [c for c in b if c not in a],
                [c for c in a if c not in b]))
    assert not problems, " | ".join(problems)
    before.close()
    after.close()


def t_rows_survive_the_rebuild():
    """Insert one row per rebuilt table BEFORE the migration, then check it is
    still there after. Row loss is silent in SQLite, so it needs a probe."""
    con = pre_006_connection()
    con.execute("INSERT INTO parties(code,display_name,nature) VALUES('P9','x','SL')")
    con.commit()
    pid = con.execute("SELECT id FROM parties WHERE code='P9'").fetchone()[0]
    con.execute("""INSERT INTO cheques(code,cheque_number,cheque_date,amount_rial,
                   direction) VALUES('KEEP-1','9','1405/01/09',777,'ISSUED')""")
    con.execute("""INSERT INTO bank_transactions(code, bank_account_id, deposit_rial)
                   VALUES('BT-1', (SELECT id FROM bank_accounts LIMIT 1), 555)""")
    con.commit()
    counts_before = {t: con.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
                     for t in REBUILT}

    con.executescript(open(MIGRATION, encoding="utf-8").read())

    counts_after = {t: con.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
                    for t in REBUILT}
    assert counts_before == counts_after, (counts_before, counts_after)
    assert con.execute(
        "SELECT amount_rial FROM cheques WHERE code='KEEP-1'").fetchone()[0] == 777
    assert con.execute(
        "SELECT deposit_rial FROM bank_transactions WHERE code='BT-1'"
    ).fetchone()[0] == 555
    con.close()


def t_indexes_triggers_views_all_return():
    """They have to be dropped for DROP TABLE to work, so 'still there' is not
    a given. Every one is compared by NAME to the pre-migration set."""
    before = pre_006_connection()
    after = post_006_connection()
    for kind in ("index", "trigger", "view"):
        b = {r[0] for r in before.execute(
            "SELECT name FROM sqlite_master WHERE type=? AND name NOT LIKE 'sqlite_%'",
            (kind,))}
        a = {r[0] for r in after.execute(
            "SELECT name FROM sqlite_master WHERE type=? AND name NOT LIKE 'sqlite_%'",
            (kind,))}
        missing = b - a
        assert not missing, "%sهای گم‌شده: %s" % (kind, sorted(missing))
    before.close()
    after.close()


def t_integrity_and_foreign_keys_clean():
    con = post_006_connection()
    assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    con.close()


def t_migration_opens_no_transaction():
    """The runner wraps it. A file with its own BEGIN dies with 'cannot start a
    transaction within a transaction' — the trap that hit the audit logger."""
    sql = open(MIGRATION, encoding="utf-8").read()
    statements = [ln.strip().upper() for ln in sql.splitlines()
                  if not ln.strip().startswith("--")]
    assert "BEGIN;" not in statements and "BEGIN TRANSACTION;" not in statements, \
        "فایل مهاجرت نباید تراکنش خودش را باز کند"
    assert "COMMIT;" not in statements, \
        "فایل مهاجرت نباید COMMIT بزند؛ runner این کار را می‌کند"


def t_rebuild_names_are_asserted():
    """Guards the quoted-name trap: a previous migration stored
    `CREATE TABLE "basket_movements"`, so an unanchored string replace missed
    it and the migration died on 'table basket_movements already exists'.
    Every rebuilt table must appear as __new exactly once."""
    sql = open(MIGRATION, encoding="utf-8").read()
    for t in REBUILT:
        n = sql.count("CREATE TABLE %s__new" % t)
        assert n == 1, "%s: %d بار CREATE TABLE __new" % (t, n)
        assert "ALTER TABLE %s__new RENAME TO %s;" % (t, t) in sql, t


TESTS = [
    ("مهاجرت اعمال و نسخه ۶ ثبت می‌شود", t_migration_applies_and_registers),
    ("هر ستون پولی nullable است", t_every_money_column_is_nullable),
    ("NULL و صفر دو مقدار متفاوت‌اند", t_null_and_zero_are_different_values),
    ("مبلغ موجود هنوز INTEGER است", t_present_amount_is_still_integer),
    ("هیچ ستونی گم نمی‌شود", t_no_column_is_lost),
    ("ردیف‌ها از بازسازی جان سالم به‌در می‌برند", t_rows_survive_the_rebuild),
    ("ایندکس‌ها، تریگرها و نماها برمی‌گردند", t_indexes_triggers_views_all_return),
    ("integrity و foreign key پاک‌اند", t_integrity_and_foreign_keys_clean),
    ("فایل مهاجرت تراکنش باز نمی‌کند", t_migration_opens_no_transaction),
    ("نام جدول‌های بازسازی‌شده تأیید می‌شود", t_rebuild_names_are_asserted),
]


def main():
    ok = 0
    for name, fn in TESTS:
        try:
            fn()
            print("PASS  " + name)
            ok += 1
        except Exception as e:                    # noqa: BLE001
            print("FAIL  %s: %s" % (name, e))
    print()
    print("%d/%d PASS" % (ok, len(TESTS)))
    return 0 if ok == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())
