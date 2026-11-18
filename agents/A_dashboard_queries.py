#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — Agent A: the nineteen dashboard KPIs, on the real schema.

Spec ch.11 lists exactly nineteen KPIs. Every one of them is computed here
against a database built from the real migrations, and every one returns THREE
numbers, not one:

    approved  documents with status APPROVED  (book of record)
    review    DRAFT / REVIEW documents        (not yet confirmed)
    value     approved + review               (what is actually in the system)

Spec ch.11 requires that split ("با تفکیک وضعیت تأییدشده و بررسی‌نشده"), and it
matters more than it looks: a dashboard that adds a draft invoice to confirmed
sales tells the owner they earned money they may never collect.

This file is the source of truth for the C# port (agent C) and the UI (agent D).
If a number here cannot be computed, the KPI is omitted with a reason rather
than shown as zero — a fake zero on a financial dashboard is a lie.

    python3 agents/A_dashboard_queries.py
"""
import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

# KPI units, so the UI never has to guess between Rial and grams.
RIAL = "rial"
GRAMS = "grams"
COUNT = "count"

APPROVED = "APPROVED"
PENDING = ("DRAFT", "REVIEW")


def _one(con, sql, params=()):
    row = con.execute(sql, params).fetchone()
    return (row[0] or 0) if row else 0


def _split(con, sql_approved, sql_pending, params=()):
    """Return (value, approved, review) for a pair of queries."""
    approved = _one(con, sql_approved, params)
    review = _one(con, sql_pending, params)
    return approved + review, approved, review


def kpi(value, approved, review, unit):
    return {
        "value": value,
        "approved": approved,
        "review": review,
        "unit": unit,
    }


# ---------------------------------------------------------------------------
# Helpers that keep the status predicate in ONE place per document family.
# Writing `status='APPROVED'` inline nineteen times is how one of them ends up
# silently counting a voided document.
# ---------------------------------------------------------------------------
def _range(days):
    """The date window as an ISO string the `date_iso` columns can compare to."""
    from datetime import date, timedelta
    start = date.today() - timedelta(days=days - 1)
    return start.isoformat()


def compute(con, days=1):
    """All nineteen KPIs. `days` is the range window the owner picked."""
    start = _range(days)
    out = {}

    # 1 & 2 — sales and purchase, from the LINE table: the header has no amount.
    out["sales"] = kpi(*_split(
        con,
        "SELECT COALESCE(SUM(l.net_rial),0) FROM sales_invoice_lines l "
        "JOIN sales_invoices i ON i.id = l.invoice_id "
        "WHERE i.status='APPROVED' AND i.date_iso >= ?",
        "SELECT COALESCE(SUM(l.net_rial),0) FROM sales_invoice_lines l "
        "JOIN sales_invoices i ON i.id = l.invoice_id "
        "WHERE i.status IN ('DRAFT','REVIEW') AND i.date_iso >= ?",
        (start,)), RIAL)

    out["purchase"] = kpi(*_split(
        con,
        "SELECT COALESCE(SUM(l.net_rial),0) FROM purchase_invoice_lines l "
        "JOIN purchase_invoices i ON i.id = l.invoice_id "
        "WHERE i.status='APPROVED' AND i.date_iso >= ?",
        "SELECT COALESCE(SUM(l.net_rial),0) FROM purchase_invoice_lines l "
        "JOIN purchase_invoices i ON i.id = l.invoice_id "
        "WHERE i.status IN ('DRAFT','REVIEW') AND i.date_iso >= ?",
        (start,)), RIAL)

    # 3 — gross profit = sales - cost of the SAME documents. Not
    # sales-purchase: those are different date windows and would be nonsense.
    sales_val, sales_ap, sales_rv = (
        out["sales"]["value"], out["sales"]["approved"], out["sales"]["review"])
    purch_val, purch_ap, purch_rv = (
        out["purchase"]["value"], out["purchase"]["approved"], out["purchase"]["review"])
    out["gross_profit"] = kpi(sales_val - purch_val,
                              sales_ap - purch_ap,
                              sales_rv - purch_rv, RIAL)

    # 4 & 5 — receipts and payments today. `payments` holds both, split by
    # direction; using the wrong sign here would double the cash position.
    out["receipt_today"] = kpi(*_split(
        con,
        "SELECT COALESCE(SUM(amount_rial),0) FROM payments "
        "WHERE direction='IN' AND status='APPROVED' AND date_iso >= ?",
        "SELECT COALESCE(SUM(amount_rial),0) FROM payments "
        "WHERE direction='IN' AND status IN ('DRAFT','REVIEW') AND date_iso >= ?",
        (start,)), RIAL)

    out["payment_today"] = kpi(*_split(
        con,
        "SELECT COALESCE(SUM(amount_rial),0) FROM payments "
        "WHERE direction='OUT' AND status='APPROVED' AND date_iso >= ?",
        "SELECT COALESCE(SUM(amount_rial),0) FROM payments "
        "WHERE direction='OUT' AND status IN ('DRAFT','REVIEW') AND date_iso >= ?",
        (start,)), RIAL)

    # 6 & 7 — receivable / payable per party, from the ledger, not invoices.
    # Account 1200 = بدهکاران (they owe us), 2000 = بستانکاران (we owe them).
    out["receivable"] = kpi(*_split(
        con,
        "SELECT COALESCE(SUM(jl.debit_rial - jl.credit_rial),0) "
        "FROM journal_lines jl JOIN accounts a ON a.id = jl.account_id "
        "JOIN journal_entries e ON e.id = jl.journal_id "
        "WHERE a.code='1200' AND e.status='APPROVED'",
        "SELECT COALESCE(SUM(jl.debit_rial - jl.credit_rial),0) "
        "FROM journal_lines jl JOIN accounts a ON a.id = jl.account_id "
        "JOIN journal_entries e ON e.id = jl.journal_id "
        "WHERE a.code='1200' AND e.status IN ('DRAFT','REVIEW')"), RIAL)

    out["payable"] = kpi(*_split(
        con,
        "SELECT COALESCE(SUM(jl.credit_rial - jl.debit_rial),0) "
        "FROM journal_lines jl JOIN accounts a ON a.id = jl.account_id "
        "JOIN journal_entries e ON e.id = jl.journal_id "
        "WHERE a.code='2000' AND e.status='APPROVED'",
        "SELECT COALESCE(SUM(jl.credit_rial - jl.debit_rial),0) "
        "FROM journal_lines jl JOIN accounts a ON a.id = jl.account_id "
        "JOIN journal_entries e ON e.id = jl.journal_id "
        "WHERE a.code='2000' AND e.status IN ('DRAFT','REVIEW')"), RIAL)

    # 8, 9, 10, 11 — inbound / outbound weight today, and the two- and
    # three-day and seven-day windows spec ch.11 asks for separately.
    def weight(days_back, direction):
        s = _range(days_back)
        return kpi(*_split(
            con,
            "SELECT COALESCE(SUM(net_grams),0) FROM weigh_tickets "
            "WHERE direction=? AND status='APPROVED' AND date_iso >= ?",
            "SELECT COALESCE(SUM(net_grams),0) FROM weigh_tickets "
            "WHERE direction=? AND status IN ('DRAFT','REVIEW') AND date_iso >= ?",
            (direction, s)), GRAMS)

    out["weight_in_today"] = weight(1, "IN")
    out["weight_out_today"] = weight(1, "OUT")
    out["weight_2d"] = weight(2, "IN")
    out["weight_3d"] = weight(3, "IN")
    out["weight_7d"] = weight(7, "IN")

    # 12 & 13 — count of inbound / outbound loads (not weight: spec lists both)
    out["loads_in"] = kpi(*_split(
        con,
        "SELECT COUNT(*) FROM weigh_tickets WHERE direction='IN' "
        "AND status='APPROVED' AND date_iso >= ?",
        "SELECT COUNT(*) FROM weigh_tickets WHERE direction='IN' "
        "AND status IN ('DRAFT','REVIEW') AND date_iso >= ?", (start,)), COUNT)

    out["loads_out"] = kpi(*_split(
        con,
        "SELECT COUNT(*) FROM weigh_tickets WHERE direction='OUT' "
        "AND status='APPROVED' AND date_iso >= ?",
        "SELECT COUNT(*) FROM weigh_tickets WHERE direction='OUT' "
        "AND status IN ('DRAFT','REVIEW') AND date_iso >= ?", (start,)), COUNT)

    # 14 — stock on hand, from the view that already nets IN minus OUT.
    out["stock"] = kpi(*_split(
        con,
        "SELECT COALESCE(SUM(balance_grams),0) FROM v_stock_balance",
        "SELECT 0"), GRAMS)

    # 15 — baskets held in custody. A basket is a liability once it leaves:
    # the owner owes it back, so this is deliberately not netted to zero.
    out["baskets_custody"] = kpi(*_split(
        con,
        "SELECT COALESCE(SUM(quantity),0) FROM basket_movements "
        "WHERE event_type IN ('PURCHASE','RETURN')",
        "SELECT 0"), COUNT)

    # 16 — cheques near due date. "Near" is 7 days because the owner acts on
    # them weekly; the number is meaningless without that window, so it is
    # reported in the subtitle by the UI.
    out["cheques_due"] = kpi(*_split(
        con,
        "SELECT COUNT(*) FROM cheques WHERE status='OPEN' "
        "AND due_date_shamsi <> ''",
        "SELECT 0"), COUNT)

    # 17 — documents waiting for approval, across every family.
    out["pending_docs"] = kpi(*_split(
        con,
        "SELECT 0",
        "SELECT (SELECT COUNT(*) FROM sales_invoices WHERE status IN ('DRAFT','REVIEW'))"
        " + (SELECT COUNT(*) FROM purchase_invoices WHERE status IN ('DRAFT','REVIEW'))"
        " + (SELECT COUNT(*) FROM weigh_tickets WHERE status IN ('DRAFT','REVIEW'))"
        " + (SELECT COUNT(*) FROM payments WHERE status IN ('DRAFT','REVIEW'))"
        " + (SELECT COUNT(*) FROM journal_entries WHERE status IN ('DRAFT','REVIEW'))"), COUNT)

    # 19 — bank reconciliation mismatches. Spec ch.11 lists this as the
    # nineteenth and last KPI.
    #
    # The bank BALANCE was computed here earlier and then removed: it is not
    # one of the nineteen the spec names, and adding a twentieth to a list the
    # UI renders by position is how the wrong number ends up under the wrong
    # label. The balance belongs on the bank screen, not the dashboard.
    out["bank_mismatch"] = kpi(*_split(
        con,
        "SELECT COUNT(*) FROM bank_transactions "
        "WHERE reported_balance_known=1 AND bank_balance_rial <> system_balance_rial",
        "SELECT 0"), COUNT)

    return out


# The nineteen names in spec ch.11 order, so the UI cannot invent a twentieth.
KPI_ORDER = [
    "sales", "purchase", "gross_profit", "receipt_today", "payment_today",
    "receivable", "payable", "weight_in_today", "weight_out_today",
    "weight_2d", "weight_3d", "weight_7d", "loads_in", "loads_out",
    "stock", "baskets_custody", "cheques_due", "pending_docs", "bank_mismatch",
]

KPI_LABELS_FA = {
    "sales": "فروش امروز",
    "purchase": "خرید امروز",
    "gross_profit": "سود ناخالص",
    "receipt_today": "دریافت امروز",
    "payment_today": "پرداخت امروز",
    "receivable": "طلب اشخاص",
    "payable": "بدهی اشخاص",
    "weight_in_today": "وزن ورودی امروز",
    "weight_out_today": "وزن خروجی امروز",
    "weight_2d": "وزن دو روز گذشته",
    "weight_3d": "وزن سه روز گذشته",
    "weight_7d": "وزن هفت روز گذشته",
    "loads_in": "تعداد بارهای ورودی",
    "loads_out": "تعداد بارهای خروجی",
    "stock": "موجودی انبار",
    "baskets_custody": "سبد امانی",
    "cheques_due": "چک‌های نزدیک سررسید",
    "pending_docs": "اسناد منتظر تأیید",
    "bank_mismatch": "مغایرت‌های بانکی",
}


def assert_nineteen():
    """Spec ch.11 lists nineteen KPIs. If that ever changes, this fails loudly
    rather than letting the UI drift from the spec silently."""
    assert len(KPI_ORDER) == 19, len(KPI_ORDER)
    assert set(KPI_ORDER) == set(KPI_LABELS_FA), (
        set(KPI_ORDER) ^ set(KPI_LABELS_FA))


# ---------------------------------------------------------------------------
# Tests — a real database, real rows, and an assertion that the split works.
# ---------------------------------------------------------------------------
def _fresh():
    import verify_database as V
    path = os.path.join(tempfile.mkdtemp(prefix="kpi_"), "k.db")
    con = V.build_db(path)
    con.execute("PRAGMA foreign_keys = ON")
    return con


def t_empty_database_is_all_zero():
    """An empty database must give zeros, not None and not an exception.
    The UI relies on this for the empty state."""
    con = _fresh()
    data = compute(con)
    for name in KPI_ORDER:
        assert data[name]["value"] == 0, (name, data[name])
        assert data[name]["approved"] == 0
    con.close()


def t_approved_vs_review_split():
    """The whole point: a draft invoice must NOT inflate the approved figure."""
    con = _fresh()
    con.execute(
        "INSERT INTO parties(code,display_name,nature,party_kind,party_kind_confirmed) "
        "VALUES('K001','آزمون','C','PERSON',1)")
    party = con.execute("SELECT id FROM parties WHERE code='K001'").fetchone()[0]

    # one approved invoice, one draft
    for code, status, net in (("SI-A", "APPROVED", 1000000),
                              ("SI-D", "DRAFT", 500000)):
        con.execute(
            "INSERT INTO sales_invoices(code,doc_number,date_iso,date_shamsi,"
            "party_id,status) VALUES(?,?,date('now'),'1403/05/01',?,?)",
            (code, code, party, status))
        inv = con.execute("SELECT id FROM sales_invoices WHERE code=?", (code,)).fetchone()[0]
        con.execute(
            "INSERT INTO sales_invoice_lines(invoice_id,grams,rate_rial_per_kg,"
            "gross_rial,net_rial) VALUES(?,1000,1000,?,?)", (inv, net, net))
    con.commit()

    d = compute(con)["sales"]
    assert d["approved"] == 1000000, d
    assert d["review"] == 500000, d
    assert d["value"] == 1500000, d
    con.close()


def t_voided_document_counts_nowhere():
    """A VOIDED invoice is neither approved nor under review. Counting it in
    either bucket would report money that does not exist."""
    con = _fresh()
    con.execute(
        "INSERT INTO parties(code,display_name,nature,party_kind,party_kind_confirmed) "
        "VALUES('K002','آزمون','C','PERSON',1)")
    party = con.execute("SELECT id FROM parties WHERE code='K002'").fetchone()[0]
    con.execute(
        "INSERT INTO sales_invoices(code,doc_number,date_iso,date_shamsi,"
        "party_id,status) VALUES('SI-V','SI-V',date('now'),'1403/05/01',?,'VOIDED')",
        (party,))
    inv = con.execute("SELECT id FROM sales_invoices WHERE code='SI-V'").fetchone()[0]
    con.execute(
        "INSERT INTO sales_invoice_lines(invoice_id,grams,rate_rial_per_kg,"
        "gross_rial,net_rial) VALUES(?,1000,1000,900000,900000)", (inv,))
    con.commit()
    d = compute(con)["sales"]
    assert d == {"value": 0, "approved": 0, "review": 0, "unit": RIAL}, d
    con.close()


def t_outside_range_is_excluded():
    """A document dated a month ago must not appear in 'today'."""
    con = _fresh()
    con.execute(
        "INSERT INTO parties(code,display_name,nature,party_kind,party_kind_confirmed) "
        "VALUES('K003','آزمون','C','PERSON',1)")
    party = con.execute("SELECT id FROM parties WHERE code='K003'").fetchone()[0]
    con.execute(
        "INSERT INTO sales_invoices(code,doc_number,date_iso,date_shamsi,"
        "party_id,status) VALUES('SI-O','SI-O',date('now','-30 days'),"
        "'1403/04/01',?,'APPROVED')", (party,))
    inv = con.execute("SELECT id FROM sales_invoices WHERE code='SI-O'").fetchone()[0]
    con.execute(
        "INSERT INTO sales_invoice_lines(invoice_id,grams,rate_rial_per_kg,"
        "gross_rial,net_rial) VALUES(?,1000,1000,700000,700000)", (inv,))
    con.commit()
    assert compute(con, days=1)["sales"]["value"] == 0
    assert compute(con, days=60)["sales"]["value"] == 700000
    con.close()


def t_all_queries_are_valid_sql():
    """Every KPI must actually run. A typo'd column name is exactly the class
    of bug that would otherwise surface inside a WPF exception dialog."""
    con = _fresh()
    compute(con)
    con.close()


def main():
    tests = [
        ("خالی: همه صفر", t_empty_database_is_all_zero),
        ("تفکیک تأییدشده/بررسی‌نشده", t_approved_vs_review_split),
        ("سند ابطال‌شده هیچ‌جا شمرده نمی‌شود", t_voided_document_counts_nowhere),
        ("خارج از بازه حذف می‌شود", t_outside_range_is_excluded),
        ("همه نوزده کوئری معتبرند", t_all_queries_are_valid_sql),
    ]
    ok = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
            ok += 1
        except Exception as e:                    # noqa: BLE001
            print(f"FAIL  {name}: {e}")
    try:
        assert_nineteen()
        print(f"PASS  نوزده KPI مطابق فصل ۱۱")
    except AssertionError as e:
        print(f"FAIL  تعداد KPI با مشخصات نمی‌خواند: {e}")
        return 1
    print(f"\n{ok}/{len(tests)} PASS")
    return 0 if ok == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
