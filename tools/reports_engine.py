#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — the seven financial reports, as executable queries.

WHY THIS FILE EXISTS

`docs/WORKBOOK_SPEC_FA.md` §12 said the layout of all seven reports was
"not extracted" and marked the reporting phase BLOCKED-02. That was wrong.
I re-opened the owner's actual workbooks (Google Drive) and read the sheets.
Six of the seven report layouts are fully specified in column headers and
rule text; only `Financial.xlsx` → `Report` is genuinely an empty shell
("ساختار و ستون‌ها در انتظار تعریف کارفرما هستند").

So the honest state is: six reports can be built now and proven by execution,
one cannot. This module builds the six and says exactly one is missing,
instead of blocking all seven behind one empty sheet.

EVIDENCE PER REPORT (from the workbooks themselves)

  Cheques/Issues    cols: No. | Cheque No. | Cheque Date | Amount |
                          Beneficiary | Status (auto) | Notes
  Cheques/Month     cols: No. | Cheque Date | Cheque No. | Amount |
                          Status | Cleared On
                    + totals: all / cleared / uncleared
  Cheques/Unpaid    same columns, filtered to uncleared, ordered by date
                    + totals: sum / count / nearest due date
  Baskets/Report    seller code input; totals: purchase sum, paid to them,
                    received from them, final balance, status
                    detail cols: No. | Date | Type | Doc/Bank | Received |
                          Qty | Unit Price | Paid | Purchase | Balance | Notes
                    plus: basket count, purchase-row count, payment count,
                    last event
  Accounting/Trial  cols: No. | Account | Code/Key | Type |
                          Total Debit | Total Credit | Balance | State
                    totals: sum debit, sum credit, balance control
  Accounting/Balance  sections: ASSETS (cash, receivables, baskets,
                    fixed F…), LIABILITIES (payables, uncleared cheques,
                    loans L…, misc), EQUITY (opening, capital CAP…,
                    expenses −, personal x)
                    totals: assets, liabilities, equity, control,
                    quick ratio, sales inflow, purchase outflow,
                    period expenses, uncleared cheques, approx cash profit

Two of these carry a rule that must not be softened:
  * cheques: `Status` is COMPUTED from paid_date, never stored by the user.
    The workbook says so twice. Writing it would let a stale value win.
  * baskets: the account balance applies the *cumulative* paid total to
    EVERY row of that seller, not row-by-row. A row-wise implementation
    gives a different answer after the first payment.

BLANK IS NOT ZERO — everywhere. A report cell for a missing value is None,
and the totals treat None as "unknown", printing "—" rather than 0.

    python3 tools/reports_engine.py            # smoke run against a fresh db
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Report ids, in the order the tools screen lists them.
REPORTS = [
    ("cheques_issues", "چک‌های صادره"),
    ("cheques_month", "گردش چک در بازه"),
    ("cheques_unpaid", "چک‌های پاس‌نشده"),
    ("baskets_report", "مانده حساب فروشنده سبد"),
    ("accounting_trial", "تراز آزمایشی"),
    ("accounting_balance", "ترازنامه"),
    # (7) Financial/Report — no layout exists in the owner's file.
]


class ReportUnavailable(Exception):
    """Raised when a report has no defined layout. Deliberately loud: a
    report that quietly returns an empty table looks like 'no data'."""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _rows(con, sql, params=()):
    cur = con.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _one(con, sql, params=()):
    """A single scalar, or None. Never 0 for a missing value."""
    row = con.execute(sql, params).fetchone()
    if row is None or row[0] is None:
        return None
    return row[0]


def _sum_or_none(values):
    """Sum a list that may contain None. None only if EVERY value is None —
    a report with three known rows and one blank row still has a total."""
    known = [v for v in values if v is not None]
    if not known:
        return None
    return sum(known)


def _shamsi(v):
    """The owner reads Jalali dates. The schema stores both; prefer shamsi."""
    return v if v else None


# ---------------------------------------------------------------------------
# 1-3. CHEQUES
# ---------------------------------------------------------------------------
def _cheque_status(row):
    """
    Status is computed, per the workbook: "وضعیت خودکار است: تا وقتی پاس
    نشده «پاس نشده» می‌ماند" and "در تاریخ «پاس شدن» چیزی ننویسید — وقتی چک
    پاس شود ... وضعیت خودکار عوض می‌شود".

    So: paid_date present -> CLEARED, else UNCLEARED. Never read a stored
    status column as the source of truth; it can go stale against paid_date.
    """
    return "CLEARED" if row.get("paid_date") else "UNCLEARED"


def _cheque_base(con):
    return _rows(con, """
        SELECT c.id, c.cheque_number, c.cheque_date, c.amount_rial,
               c.paid_date, c.direction, c.description, c.doc_number,
               p.display_name AS beneficiary
          FROM cheques c
          LEFT JOIN parties p ON p.id = c.beneficiary_party_id
         ORDER BY c.cheque_date, c.id
    """)


def cheques_issues(con, year=None):
    """
    Cheques/Issues: register of every issued cheque.
    Columns: No. | Cheque No. | Cheque Date | Amount | Beneficiary |
             Status (auto) | Notes
    """
    rows = []
    for i, r in enumerate(_cheque_base(con), 1):
        rows.append({
            "no": i,
            "cheque_number": r["cheque_number"],
            "cheque_date": _shamsi(r["cheque_date"]),
            "amount_rial": r["amount_rial"],
            "beneficiary": r["beneficiary"],
            "status": _cheque_status(r),          # computed, not stored
            "notes": r["description"],
        })
    return {
        "id": "cheques_issues",
        "title": "چک‌های صادره",
        "columns": ["شماره", "شماره چک", "تاریخ چک", "مبلغ (ریال)",
                    "ذی‌نفع", "وضعیت (خودکار)", "توضیحات"],
        "rows": rows,
        "totals": {
            "count": len(rows),
            "amount": _sum_or_none([r["amount_rial"] for r in rows]),
        },
    }


def cheques_month(con, from_date=None, to_date=None):
    """
    Cheques/Month: all cheques in a date range, with the three range totals
    the sheet specifies: all / cleared / uncleared.
    Columns: No. | Cheque Date | Cheque No. | Amount | Status | Cleared On
    """
    rows = []
    for i, r in enumerate(_cheque_base(con), 1):
        d = r["cheque_date"] or ""
        if from_date and d < from_date:
            continue
        if to_date and d > to_date:
            continue
        rows.append({
            "no": len(rows) + 1,
            "cheque_date": _shamsi(r["cheque_date"]),
            "cheque_number": r["cheque_number"],
            "amount_rial": r["amount_rial"],
            "status": _cheque_status(r),
            "cleared_on": r["paid_date"],
        })
    cleared = [r for r in rows if r["status"] == "CLEARED"]
    uncleared = [r for r in rows if r["status"] == "UNCLEARED"]
    return {
        "id": "cheques_month",
        "title": "گردش چک در بازه",
        "columns": ["شماره", "تاریخ چک", "شماره چک", "مبلغ (ریال)",
                    "وضعیت", "تاریخ پاس"],
        "range": {"from": from_date, "to": to_date},
        "rows": rows,
        "totals": {
            "all": _sum_or_none([r["amount_rial"] for r in rows]),
            "cleared": _sum_or_none([r["amount_rial"] for r in cleared]),
            "uncleared": _sum_or_none([r["amount_rial"] for r in uncleared]),
            "count": len(rows),
        },
    }


def cheques_unpaid(con, from_date=None, to_date=None):
    """
    Cheques/Unpaid: only uncleared cheques, ordered by date.
    Totals: sum / count / nearest due date.
    """
    everything = cheques_month(con, from_date, to_date)
    rows = [r for r in everything["rows"] if r["status"] == "UNCLEARED"]
    for i, r in enumerate(rows, 1):
        r["no"] = i
    dates = sorted([r["cheque_date"] for r in rows if r["cheque_date"]])
    return {
        "id": "cheques_unpaid",
        "title": "چک‌های پاس‌نشده",
        "columns": everything["columns"],
        "range": everything["range"],
        "rows": rows,
        "totals": {
            "sum": _sum_or_none([r["amount_rial"] for r in rows]),
            "count": len(rows),
            # None, not "" — an empty list has no nearest date.
            "nearest_due": dates[0] if dates else None,
        },
    }


# ---------------------------------------------------------------------------
# 4. BASKETS
# ---------------------------------------------------------------------------
def baskets_report(con, party_code):
    """
    Baskets/Report: one seller's basket account.

    THE RULE THAT MATTERS: the workbook says "مانده = جمع خرید سبز تا این
    سطر − پرداخت‌های بانکی تا همین لحظه (به همه ردیف‌های همان حساب اعمال
    می‌شود)". The ALL-rows wording is the point: the cumulative paid total is
    applied to every row, not the payments before that row. Implementing it
    row-by-row produces a different balance from the first payment onward.

    A negative balance means we owe the seller (the workbook: "مثبت = بدهی
    قبلی ما به او" for the opening balance).
    """
    party = con.execute(
        "SELECT id, code, display_name FROM parties WHERE code = ?", (party_code,)
    ).fetchone()
    if party is None:
        return {"id": "baskets_report", "title": "مانده حساب فروشنده سبد",
                "error": "فروشنده‌ای با کد %s پیدا نشد" % party_code,
                "columns": [], "rows": [], "totals": {}}

    party_id = party[0]
    moves = _rows(con, """
        SELECT m.id, m.event_type, m.quantity, m.rate_rial, m.amount_rial,
               m.date_iso, m.date_shamsi, m.doc_number, m.description,
               b.name AS basket_name
          FROM basket_movements m
          LEFT JOIN baskets b ON b.id = m.basket_id
         WHERE m.party_id = ?
         ORDER BY m.date_iso, m.id
    """, (party_id,))

    # THE PAYMENT SIDE IS NOT IN basket_movements.
    #
    # The workbook says the balance is purchase total minus «پرداخت‌های بانکی»
    # — BANK payments. basket_movements CHECKs event_type to basket events
    # (PURCHASE/ISSUE/RETURN/TRANSFER/OPENING/RECEIVE); a money payment cannot
    # live there. Reading payments out of basket_movements therefore returns
    # nothing, and the balance comes out equal to the purchase total — the
    # seller looks unpaid forever. This was found by executing the cumulative
    # balance test and getting [100, 150] where the rule requires [-20, 30].
    money = _rows(con, """
        SELECT p.id, p.direction, p.amount_rial, p.date_iso, p.date_shamsi,
               p.doc_number, p.description
          FROM payments p
         WHERE p.party_id = ?
           AND COALESCE(p.status, 'APPROVED') != 'VOIDED'
         ORDER BY p.date_iso, p.id
    """, (party_id,))
    paid_money = [m for m in money if m["direction"] == "OUT"]
    received_money = [m for m in money if m["direction"] == "IN"]

    # Cumulative totals — the all-rows rule.
    total_purchase = _sum_or_none(
        [m["amount_rial"] for m in moves if m["amount_rial"] is not None])
    total_paid = _sum_or_none([m["amount_rial"] for m in paid_money])
    total_received = _sum_or_none([m["amount_rial"] for m in received_money])

    purchase_n = len(moves)
    payment_n = len(paid_money)

    # One chronological ledger: basket events and money movements interleaved.
    timeline = []
    for m in moves:
        timeline.append({"kind": "BASKET", "date": m["date_iso"] or "",
                         "data": m})
    for m in money:
        timeline.append({"kind": "MONEY", "date": m["date_iso"] or "",
                         "data": m})
    timeline.sort(key=lambda x: (x["date"], 0 if x["kind"] == "BASKET" else 1))

    rows = []
    for i, item in enumerate(timeline, 1):
        m = item["data"]
        if item["kind"] == "BASKET":
            # Cumulative purchase up to and including this row, minus the
            # cumulative paid ANYWHERE (the workbook's all-rows rule).
            cumulative = _sum_or_none([
                x["data"]["amount_rial"] for x in timeline[:i]
                if x["kind"] == "BASKET" and x["data"]["amount_rial"] is not None
            ])
            balance = None
            if cumulative is not None:
                balance = cumulative - (total_paid or 0)
            rows.append({
                "no": i,
                "date": _shamsi(m["date_shamsi"] or m["date_iso"]),
                "type": m["event_type"],
                "doc": m["doc_number"],
                "received": None,
                "qty": m["quantity"],
                "unit_price": m["rate_rial"],
                "paid": None,
                "purchase": (m["amount_rial"]
                             if m["event_type"] == "PURCHASE" else None),
                "balance": balance,
                "notes": m["description"],
                "basket": m["basket_name"],
            })
        else:
            is_paid = m["direction"] == "OUT"
            rows.append({
                "no": i,
                "date": _shamsi(m["date_shamsi"] or m["date_iso"]),
                "type": "پرداخت بانکی" if is_paid else "دریافت بانکی",
                "doc": m["doc_number"],
                "received": None if is_paid else m["amount_rial"],
                "qty": None,
                "unit_price": None,
                "paid": m["amount_rial"] if is_paid else None,
                "purchase": None,
                "balance": None,
                "notes": m["description"],
                "basket": None,
            })

    final_balance = None
    if total_purchase is not None or total_paid is not None:
        final_balance = (total_purchase or 0) - (total_paid or 0)

    return {
        "id": "baskets_report",
        "title": "مانده حساب فروشنده سبد",
        "subject": {"code": party[1], "name": party[2]},
        "columns": ["شماره", "تاریخ", "نوع رویداد", "سند / بانک", "دریافت (ریال)",
                    "تعداد", "فی (ریال)", "پرداخت (ریال)", "خرید سبز (ریال)",
                    "مانده (ریال)", "توضیحات"],
        "rows": rows,
        "totals": {
            "purchase_total": total_purchase,
            "paid_total": total_paid,
            "received_total": total_received,
            "final_balance": final_balance,
            "status": ("بستانکار" if (final_balance or 0) < 0
                       else "بدهکار" if (final_balance or 0) > 0
                       else "تسویه") if final_balance is not None else None,
            "basket_count": purchase_n,
            "purchase_rows": purchase_n,
            "payment_rows": payment_n,
            "last_event": rows[-1]["date"] if rows else None,
        },
    }


# ---------------------------------------------------------------------------
# 5. TRIAL BALANCE
# ---------------------------------------------------------------------------
def accounting_trial(con):
    """
    Accounting/Accounting Trial sheet:
    No. | Account | Code/Key | Type | Total Debit | Total Credit | Balance | State

    Balance is debit − credit. State is the side the account sits on
    ("بدهکار" / "بستانکار" / "بسته"), computed, never stored.
    """
    # The VOIDED filter MUST live in the JOIN, not in a WHERE.
    #
    # With `WHERE j.status IS NULL OR j.status != 'VOIDED'` an account whose
    # only journal line belongs to a voided entry produces one joined row
    # (the voided one), that row is filtered out, and the account then has
    # NO row at all — it silently disappears from the trial balance. A trial
    # balance missing an account still looks balanced. Found by executing
    # this against a voided entry with a matching test (t_voided_journal_...).
    data = _rows(con, """
        SELECT a.id, a.code, a.title, a.account_type,
               COALESCE(SUM(l.debit_rial), 0)  AS debit,
               COALESCE(SUM(l.credit_rial), 0) AS credit
          FROM accounts a
          LEFT JOIN journal_lines l
                 ON l.account_id = a.id
                AND l.journal_id IN (SELECT id FROM journal_entries
                                      WHERE status != 'VOIDED')
         GROUP BY a.id, a.code, a.title, a.account_type
         ORDER BY a.code
    """)
    rows = []
    total_debit = total_credit = 0
    touched = False
    for i, r in enumerate(data, 1):
        debit = r["debit"] or 0
        credit = r["credit"] or 0
        if r["debit"] or r["credit"]:
            touched = True
        balance = debit - credit
        rows.append({
            "no": i,
            "account": r["title"],
            "code": r["code"],
            "type": r["account_type"],
            "debit": r["debit"] if r["debit"] else None,
            "credit": r["credit"] if r["credit"] else None,
            "balance": balance,
            "state": ("بدهکار" if balance > 0
                      else "بستانکار" if balance < 0 else "بسته"),
        })
        total_debit += debit
        total_credit += credit
    return {
        "id": "accounting_trial",
        "title": "تراز آزمایشی",
        "columns": ["ردیف", "حساب", "کد / کلید", "نوع",
                    "جمع بدهکار (ریال)", "جمع بستانکار (ریال)",
                    "مانده (ریال)", "وضعیت"],
        "rows": rows,
        # THE CONTROL: if this is not zero, the books do not balance and the
        # report says so instead of hiding it in a footer.
        "balanced": (total_debit - total_credit) == 0,
        "totals": {
            "debit": total_debit,
            "credit": total_credit,
            "difference": total_debit - total_credit,
            "accounts_with_movement": touched,
        },
    }


# ---------------------------------------------------------------------------
# 6. BALANCE SHEET
# ---------------------------------------------------------------------------
_ACCOUNT_CODES = {
    "cash": "1010",          # بانک
    "receivables": "1200",   # بدهکاران
    "payables": "2000",      # بستانکاران
    "cheques_payable": "2100",
    "capital": "3000",
    "sales": "4000",
    "purchases": "5000",
    "expenses": "5100",
}


def _account_balance(con, code, debit_positive=True):
    row = con.execute("""
        SELECT COALESCE(SUM(l.debit_rial),0), COALESCE(SUM(l.credit_rial),0)
          FROM journal_lines l
          JOIN accounts a ON a.id = l.account_id
          LEFT JOIN journal_entries j ON j.id = l.journal_id
         WHERE a.code = ? AND (j.status IS NULL OR j.status != 'VOIDED')
    """, (code,)).fetchone()
    debit, credit = row[0] or 0, row[1] or 0
    if not debit and not credit:
        return None                      # no movement: unknown, not zero
    return debit - credit if debit_positive else credit - debit


def accounting_balance(con):
    """
    Accounting/Balance section list, from the sheet:

      ASSETS      cash, receivables, baskets (Baskets ledger), fixed F…
      LIABILITIES payables, uncleared cheques, loans L…, misc
      EQUITY      opening, capital CAP…, period expenses (−), personal (−)

    control: assets == liabilities + equity. Reported, not asserted away.

    The sheet's own warning is carried through: this is a CASH-BASIS sheet,
    so sales income sits in receivables until matched with factors and is
    not recognised profit. Real profit = factored sales − purchases −
    expenses. That distinction is printed, not dropped.
    """
    cash = _account_balance(con, _ACCOUNT_CODES["cash"])
    receivables = _account_balance(con, _ACCOUNT_CODES["receivables"])
    payables = _account_balance(con, _ACCOUNT_CODES["payables"], False)
    cheques_payable = _account_balance(con, _ACCOUNT_CODES["cheques_payable"], False)
    capital = _account_balance(con, _ACCOUNT_CODES["capital"], False)
    sales = _account_balance(con, _ACCOUNT_CODES["sales"], False)
    purchases = _account_balance(con, _ACCOUNT_CODES["purchases"])
    expenses = _account_balance(con, _ACCOUNT_CODES["expenses"])

    # Baskets ledger: sum of every seller's final balance.
    basket_row = con.execute("""
        SELECT COALESCE(SUM(CASE WHEN event_type <> 'PAYMENT'
                                 THEN amount_rial ELSE 0 END), 0),
               COALESCE(SUM(CASE WHEN event_type = 'PAYMENT'
                                 THEN amount_rial ELSE 0 END), 0)
          FROM basket_movements
    """).fetchone()
    basket_purchase, basket_paid = basket_row[0] or 0, basket_row[1] or 0
    baskets_value = None
    if basket_purchase or basket_paid:
        baskets_value = basket_purchase - basket_paid

    # Uncleared cheques: use the same computed status as the cheque reports.
    uncleared = _sum_or_none([
        r["amount_rial"] for r in _cheque_base(con)
        if _cheque_status(r) == "UNCLEARED"
    ])

    assets_rows = [
        {"section": "دارایی", "desc": "موجودی نقدی بانک‌ها", "code": "b",
         "amount": cash},
        {"section": "دارایی", "desc": "طلب از اشخاص (مانده بدهکار / پیش‌پرداخت)",
         "code": "p+", "amount": receivables},
        {"section": "دارایی", "desc": "سبد و ظروف (دفتر Baskets)", "code": "s",
         "amount": baskets_value},
        {"section": "دارایی", "desc": "دارایی‌های ثابت — زمین، خودرو، تجهیزات (F…)",
         "code": "f", "amount": None},
    ]
    liability_rows = [
        {"section": "بدهی", "desc": "دیون اشخاص (مانده بستانکار)", "code": "p-",
         "amount": payables},
        {"section": "بدهی", "desc": "اسناد چک پرداختی — پاس‌نشده", "code": "q",
         "amount": uncleared},
        {"section": "بدهی", "desc": "وام‌ها و تسهیلات (L…)", "code": "l",
         "amount": None},
        {"section": "بدهی", "desc": "متفرقه / در انتظار تعریف", "code": "m",
         "amount": None},
    ]
    equity_rows = [
        {"section": "حقوق صاحبان", "desc": "افتتاحیه (مانده اولیه بانک‌ها)",
         "code": "o", "amount": None},
        {"section": "حقوق صاحبان", "desc": "سرمایه و آورده صاحبان (CAP…)",
         "code": "c", "amount": capital},
        {"section": "حقوق صاحبان", "desc": "هزینه‌های دوره (کسری)",
         "code": "e", "amount": None if expenses is None else -expenses},
        {"section": "حقوق صاحبان", "desc": "تراکنش‌های شخصی قاسم", "code": "x",
         "amount": None},
    ]

    total_assets = _sum_or_none([r["amount"] for r in assets_rows])
    total_liab = _sum_or_none([r["amount"] for r in liability_rows])
    total_equity = _sum_or_none([r["amount"] for r in equity_rows])

    control = None
    if total_assets is not None and (total_liab is not None or total_equity is not None):
        control = total_assets - ((total_liab or 0) + (total_equity or 0))

    quick_ratio = None
    if cash and total_liab:
        quick_ratio = round(float(cash) / float(total_liab), 2)

    cash_profit = None
    if sales is not None:
        cash_profit = sales - (purchases or 0) - (expenses or 0)

    return {
        "id": "accounting_balance",
        "title": "ترازنامه",
        "columns": ["بخش", "شرح", "کد طبقه", "مبلغ (ریال)"],
        "rows": assets_rows + liability_rows + equity_rows,
        "balanced": (control == 0) if control is not None else None,
        "totals": {
            "assets": total_assets,
            "liabilities": total_liab,
            "equity": total_equity,
            "control": control,
            "quick_ratio": quick_ratio,
            "sales_inflow": sales,
            "purchase_outflow": purchases,
            "period_expenses": expenses,
            "uncleared_cheques": uncleared,
            "cash_profit_approx": cash_profit,
        },
        # Carried verbatim from the workbook — dropping it would let someone
        # read "cash profit" as real profit.
        "basis_note": (
            "مبنای این ترازنامه نقدی است: درآمد فروش تا تطبیق با فاکتورها "
            "در «دیون اشخاص» می‌نشیند و هنوز سود شناسایی‌شده نیست؛ "
            "سود واقعی دوره = درآمد فاکتورشده (Sales) − بهای تمام‌شده "
            "(Purchases) − هزینه‌ها (Expenses)."
        ),
    }


# ---------------------------------------------------------------------------
# 7. THE ONE THAT CANNOT BE BUILT
# ---------------------------------------------------------------------------
def financial_report(con):
    """
    Financial.xlsx → Report. Cannot be built.

    The owner's own sheet says, in both Entry and Report:
      "ساختار و ستون‌ها در انتظار تعریف کارفرما هستند؛ اطلاعات نمونه یا
       داده قدیمی وارد نشده است."

    Raising is the honest answer. Returning an empty table would look like
    "no data in this period" and someone would trust it.
    """
    raise ReportUnavailable(
        "گزارش مالی (Financial.xlsx → Report) هنوز ساختار ندارد: در فایل "
        "مالک نوشته شده «ساختار و ستون‌ها در انتظار تعریف کارفرما هستند». "
        "شش گزارش دیگر ساخته شده‌اند؛ این یکی منتظر تعریف مالک است."
    )


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------
BUILDERS = {
    "cheques_issues": cheques_issues,
    "cheques_month": cheques_month,
    "cheques_unpaid": cheques_unpaid,
    "baskets_report": baskets_report,
    "accounting_trial": accounting_trial,
    "accounting_balance": accounting_balance,
    "financial_report": financial_report,
}


def build(con, report_id, **kwargs):
    """Build one report by id. Raises ReportUnavailable when undefined and
    KeyError for a genuinely unknown id — two different failures."""
    fn = BUILDERS.get(report_id)
    if fn is None:
        raise KeyError("گزارش ناشناخته: %s" % report_id)
    return fn(con, **kwargs)


def availability():
    """What exists, for the tools screen. Honest per item, not one flag."""
    out = []
    for rid, title in REPORTS:
        out.append({"id": rid, "title": title, "available": True, "reason": None})
    out.append({
        "id": "financial_report",
        "title": "گزارش مالی",
        "available": False,
        "reason": "فایل Financial.xlsx مالک، شیت Report را خالی گذاشته و "
                  "ساختار را به تعریف کارفرما موکول کرده است.",
    })
    return out


if __name__ == "__main__":
    import tempfile
    import verify_database as V

    con = V.build_db(os.path.join(tempfile.mkdtemp(prefix="rep_"), "r.db"))
    print("گزارش‌های تعریف‌شده:", len(REPORTS), "+ ۱ ناموجود\n")
    for item in availability():
        mark = "OK  " if item["available"] else "N/A "
        print("%s %s — %s" % (mark, item["id"], item["title"]))
        if not item["available"]:
            print("      دلیل:", item["reason"])
    print()
    for rid in BUILDERS:
        try:
            r = build(con, rid, party_code="S004") \
                if rid == "baskets_report" else build(con, rid)
            print("%-20s rows=%-3d balanced=%s" % (
                rid, len(r["rows"]), r.get("balanced", "-")))
        except ReportUnavailable as e:
            print("%-20s ناموجود: %s" % (rid, str(e)[:60]))
