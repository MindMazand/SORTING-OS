#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — the six financial reports, proven by execution.

Every claim `tools/reports_engine.py` makes is tested here against a real
database built by the real migrations, with real rows inserted:

  1. the six reports build and their columns match the owner's workbook
  2. cheque Status is COMPUTED from paid_date, never read from a column
  3. the baskets balance applies the CUMULATIVE paid total to every row
     (the workbook's "به همه ردیف‌های همان حساب اعمال می‌شود")
  4. a blank amount is None, never 0 — and a total over blanks stays None
  5. the trial balance control is reported, and a broken journal makes it
     non-zero instead of being hidden
  6. the balance sheet separates the three sections and prints the
     cash-basis warning
  7. Financial/Report raises instead of returning an empty table
  8. report 7's absence does not stop reports 1-6 (the "a single blocker must
     not stop the whole review" rule, applied to code)

    python3 tools/test_reports.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import reports_engine as R


def fresh():
    import verify_database as V
    con = V.build_db(os.path.join(tempfile.mkdtemp(prefix="tr_"), "r.db"))
    con.execute("PRAGMA foreign_keys = OFF")
    return con


def add_party(con, code="S004", name="فروشنده سبد"):
    # nature is CHECK-constrained to C/SL/S/E/X/F/L/CAP — not 'PERSON'.
    con.execute(
        "INSERT INTO parties(code, display_name, nature) VALUES(?,?,?)",
        (code, name, "SL"))
    con.commit()
    return con.execute("SELECT id FROM parties WHERE code=?", (code,)).fetchone()[0]


def add_cheque(con, num="24012345", date="1405/07/10", amount=80000000,
               paid=None, party_id=None, direction="ISSUED"):
    # cheques.code is NOT NULL — the ledger needs a stable key per cheque.
    con.execute("""INSERT INTO cheques(code, cheque_number, cheque_date, amount_rial,
                                       paid_date, direction, beneficiary_party_id)
                   VALUES(?,?,?,?,?,?,?)""",
                ("CHQ-" + num, num, date, amount, paid or "", direction, party_id))
    con.commit()


def add_seller_payment(con, party_id, amount):
    """
    A cash payment to the basket seller — `payments`, direction OUT.

    The workbook's basket report subtracts "پرداخت‌های بانکی" (bank payments)
    from green purchases. Those are money movements, and basket_movements
    CHECKs event_type to basket events only. Putting a PAYMENT row into
    basket_movements is impossible by design, and inventing one would have
    meant loosening the schema to fit a test.
    """
    con.execute("""INSERT INTO payments(code, party_id, direction, amount_rial,
                   date_iso) VALUES(?,?,'OUT',?,'2026-11-03')""",
                ("PAY-%d" % amount, party_id, amount))
    con.commit()


def add_basket_move(con, party_id, event_type, amount, date="1405-07-02"):
    # basket_movements.basket_id is NOT NULL, and event_type is CHECKed to
    # RECEIVE/ISSUE/RETURN/PURCHASE/TRANSFER/OPENING. A "payment" is not an
    # event type here — money movement lives in payments/bank_transactions.
    basket = con.execute("SELECT id FROM baskets LIMIT 1").fetchone()
    if basket is None:
        con.execute("INSERT INTO baskets(code, name) VALUES('B1','سبد ۵ کیلویی')")
        con.commit()
        basket = con.execute("SELECT id FROM baskets LIMIT 1").fetchone()
    con.execute("""INSERT INTO basket_movements(basket_id, party_id, event_type,
                   quantity, rate_rial, amount_rial, date_iso)
                   VALUES(?,?,?,?,?,?,?)""",
                (basket[0], party_id, event_type, 100, 45000, amount, date))
    con.commit()


def acc_id(con, code):
    return con.execute("SELECT id FROM accounts WHERE code=?", (code,)).fetchone()[0]


def post_journal(con, lines, status="APPROVED", doc="J-1"):
    con.execute("""INSERT INTO journal_entries(code, doc_number, date_iso, status)
                   VALUES(?,?,?,?)""", (doc, doc, "2026-11-01", status))
    jid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    for code, debit, credit in lines:
        con.execute("""INSERT INTO journal_lines(journal_id, account_id,
                       debit_rial, credit_rial) VALUES(?,?,?,?)""",
                    (jid, acc_id(con, code), debit, credit))
    con.commit()
    return jid


# ---------------------------------------------------------------------------
def t_six_reports_exist_and_one_does_not():
    avail = R.availability()
    assert len(avail) == 7, len(avail)
    ok = [a for a in avail if a["available"]]
    no = [a for a in avail if not a["available"]]
    assert len(ok) == 6, len(ok)
    assert len(no) == 1 and no[0]["id"] == "financial_report"
    assert no[0]["reason"], "ناموجود باید دلیل داشته باشد، نه یک پرچم خالی"


def t_columns_match_the_owner_workbook():
    """Column headers copied from the owner's sheets, checked verbatim.
    If a report silently grows/drops a column, this catches it."""
    con = fresh()
    expected = {
        "cheques_issues": ["شماره", "شماره چک", "تاریخ چک", "مبلغ (ریال)",
                           "ذی‌نفع", "وضعیت (خودکار)", "توضیحات"],
        "cheques_month": ["شماره", "تاریخ چک", "شماره چک", "مبلغ (ریال)",
                          "وضعیت", "تاریخ پاس"],
        "accounting_trial": ["ردیف", "حساب", "کد / کلید", "نوع",
                             "جمع بدهکار (ریال)", "جمع بستانکار (ریال)",
                             "مانده (ریال)", "وضعیت"],
        "accounting_balance": ["بخش", "شرح", "کد طبقه", "مبلغ (ریال)"],
    }
    for rid, cols in expected.items():
        r = R.build(con, rid)
        assert r["columns"] == cols, (rid, r["columns"])
    con.close()


def t_cheque_status_is_computed_from_paid_date():
    """The workbook says the status is automatic and must not be written.
    A stored 'CLEARED' with no paid_date must still read UNCLEARED."""
    con = fresh()
    add_cheque(con, num="1", paid=None)
    add_cheque(con, num="2", paid="1405/07/15")
    # A lying stored status, to prove it is ignored.
    # The schema's own vocabulary is OPEN/PAID/COLLECTED/RETURNED/VOIDED.
    # 'PAID' with an empty paid_date is the lie we want the report to ignore.
    con.execute("UPDATE cheques SET status='PAID' WHERE cheque_number='1'")
    con.commit()

    r = R.cheques_issues(con)
    by_num = {x["cheque_number"]: x["status"] for x in r["rows"]}
    assert by_num["1"] == "UNCLEARED", \
        "وضعیت ذخیره‌شده نباید بر وضعیت محاسبه‌شده غلبه کند"
    assert by_num["2"] == "CLEARED"
    con.close()


def t_cheques_totals_split_cleared_and_uncleared():
    con = fresh()
    add_cheque(con, num="1", amount=100, paid=None)
    add_cheque(con, num="2", amount=250, paid="1405/07/20")
    m = R.cheques_month(con)
    assert m["totals"]["all"] == 350
    assert m["totals"]["cleared"] == 250
    assert m["totals"]["uncleared"] == 100
    u = R.cheques_unpaid(con)
    assert u["totals"]["count"] == 1
    assert u["totals"]["sum"] == 100
    con.close()


def t_baskets_balance_uses_cumulative_paid():
    """
    Two purchases (100 and 50) then one payment of 120.
    Row-wise would give: row1 100-0=100, row2 150-0=150.
    The workbook's all-rows rule gives: row1 100-120=-20, row2 150-120=30.
    """
    con = fresh()
    pid = add_party(con)
    add_basket_move(con, pid, "PURCHASE", 100, "1405-07-01")
    add_basket_move(con, pid, "PURCHASE", 50, "1405-07-02")
    add_seller_payment(con, pid, 120)

    r = R.baskets_report(con, "S004")
    balances = [x["balance"] for x in r["rows"]]
    assert balances[0] == -20, balances
    assert balances[1] == 30, balances
    assert r["totals"]["final_balance"] == 30
    assert r["totals"]["purchase_total"] == 150
    assert r["totals"]["paid_total"] == 120
    # A net credit balance means we owe the seller.
    assert r["totals"]["status"] == "بدهکار", r["totals"]["status"]
    con.close()


def t_blank_is_none_never_zero():
    """A cheque with no amount is unknown, not free. The total over only
    blanks must be None, and over mixed rows must skip the blanks."""
    con = fresh()
    add_cheque(con, num="1", amount=None)
    r = R.cheques_issues(con)
    assert r["rows"][0]["amount_rial"] is None, r["rows"][0]
    assert r["totals"]["amount"] is None, \
        "جمع روی سطرهای خالی باید None باشد نه ۰"

    add_cheque(con, num="2", amount=500)
    r = R.cheques_issues(con)
    assert r["totals"]["amount"] == 500, \
        "جمع باید سطر خالی را نادیده بگیرد، نه صفر حساب کند"
    con.close()


def t_trial_balance_control_is_real():
    """A balanced posting gives difference 0; a broken one does not, and the
    report says so rather than printing a footer nobody reads."""
    con = fresh()
    post_journal(con, [("1010", 1000, 0), ("3000", 0, 1000)])
    r = R.accounting_trial(con)
    assert r["balanced"] is True, r["totals"]
    assert r["totals"]["difference"] == 0

    # Now break it.
    post_journal(con, [("1010", 700, 0), ("4000", 0, 500)], doc="J-2")
    r = R.accounting_trial(con)
    assert r["balanced"] is False, "تراز ناتراز باید ناتراز گزارش شود"
    assert r["totals"]["difference"] == 200, r["totals"]
    con.close()


def t_voided_journal_is_excluded():
    con = fresh()
    post_journal(con, [("1010", 999, 0), ("3000", 0, 999)], status="VOIDED")
    r = R.accounting_trial(con)
    assert r["totals"]["debit"] == 0, r["totals"]
    rows = {x["code"]: x for x in r["rows"]}
    # accounts are always present (11 seeded); the one with only a voided
    # line must show a blank debit, not 0 — "no movement" is unknown.
    assert rows["1010"]["debit"] is None, rows["1010"]
    assert rows["1010"]["balance"] == 0, rows["1010"]
    con.close()


def t_balance_sheet_has_three_sections_and_the_caveat():
    con = fresh()
    post_journal(con, [("1010", 5000, 0), ("3000", 0, 5000)])
    r = R.accounting_balance(con)
    sections = {x["section"] for x in r["rows"]}
    assert sections == {"دارایی", "بدهی", "حقوق صاحبان"}, sections
    assert r["totals"]["assets"] == 5000
    assert "نقدی" in r["basis_note"], \
        "هشدار مبنای نقدی نباید حذف شود — وگرنه سود نقدی با سود واقعی اشتباه می‌شود"
    con.close()


def t_financial_report_raises_not_empty():
    con = fresh()
    try:
        R.build(con, "financial_report")
    except R.ReportUnavailable:
        con.close()
        return
    raise AssertionError(
        "گزارش بی‌ساختار باید خطا بدهد؛ جدول خالی شبیه «داده‌ای نیست» است")


def t_one_missing_report_does_not_stop_the_rest():
    con = fresh()
    built, failed = [], []
    for rid, _ in R.REPORTS:
        try:
            R.build(con, rid, party_code="S004") if rid == "baskets_report" \
                else R.build(con, rid)
            built.append(rid)
        except R.ReportUnavailable:
            failed.append(rid)
    assert len(built) == 6, built
    assert failed == [], "شش گزارش نباید به‌خاطر یک گزارش ناموجود متوقف شوند"
    con.close()


def t_unknown_report_id_is_a_different_failure():
    con = fresh()
    try:
        R.build(con, "no_such_report")
    except KeyError:
        con.close()
        return
    raise AssertionError("شناسه ناشناخته باید KeyError بدهد، نه گزارش خالی")


TESTS = [
    ("شش گزارش موجود و یکی ناموجود، با دلیل", t_six_reports_exist_and_one_does_not),
    ("ستون‌ها عیناً مطابق فایل مالک", t_columns_match_the_owner_workbook),
    ("وضعیت چک از paid_date محاسبه می‌شود", t_cheque_status_is_computed_from_paid_date),
    ("جمع چک‌ها پاس‌شده/نشده را جدا می‌کند", t_cheques_totals_split_cleared_and_uncleared),
    ("مانده سبد با پرداخت تجمعی محاسبه می‌شود", t_baskets_balance_uses_cumulative_paid),
    ("خالی None است نه صفر", t_blank_is_none_never_zero),
    ("کنترل تراز آزمایشی واقعی است", t_trial_balance_control_is_real),
    ("سند ابطال‌شده حذف می‌شود", t_voided_journal_is_excluded),
    ("ترازنامه سه بخش + هشدار مبنای نقدی", t_balance_sheet_has_three_sections_and_the_caveat),
    ("گزارش مالی خطا می‌دهد نه جدول خالی", t_financial_report_raises_not_empty),
    ("یک گزارش ناموجود بقیه را متوقف نمی‌کند", t_one_missing_report_does_not_stop_the_rest),
    ("شناسه ناشناخته KeyError است", t_unknown_report_id_is_a_different_failure),
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
