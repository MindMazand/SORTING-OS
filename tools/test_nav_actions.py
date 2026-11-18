#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — no navigation button may be a silent no-op.

WHY THIS EXISTS

`MainWindow.Nav_Click` is one handler for nine nav buttons. The pattern for a
wired button is:

    else if (source == NavReports)
    {
        SelectTool("گزارش‌ها", NavReports);
        OpenReports();                       <-- the actual action
    }

The pattern for an UNWIRED button was:

    else if (source == NavWeigh) { SelectTool("باسکول", NavWeigh); }

which changes a label and does nothing else. To the owner that is indistinguishable
from a working button: it highlights, the screen does not change, and they
conclude the software has no such feature. This project has already shipped one
of those (Reports, until this round) and fixed it only because someone happened
to look.

So this gate reads the nav handler and requires every branch to either call an
action method (Open*) or be listed in PLANNED with a reason. A new silent
no-op fails here.

    python3 tools/test_nav_actions.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CS = os.path.join(ROOT, "src", "Mazandasht.Presentation", "MainWindow.xaml.cs")

# Buttons that intentionally do nothing yet, each with the reason it is not
# built. Emptying this list is the goal; it may never grow silently, because
# adding an entry is a visible edit in a file whose whole purpose is to be
# short.
PLANNED = {
    "NavWeigh": "باسکول — فرم ورود باسکول هنوز ساخته نشده (فاز عملیاتی)",
    "NavSorting": "سورتینگ — فرم ورود سورتینگ هنوز ساخته نشده",
    "NavInvoices": "خرید و فروش — فرم فاکتور هنوز ساخته نشده",
    "NavBank": "بانک و چک — فرم تراکنش بانکی هنوز ساخته نشده",
    "NavParties": "اشخاص — فرم اشخاص هنوز ساخته نشده",
    "NavDashboard": "داشبورد در خود MainWindow است و پنجره جدا ندارد",
}


def source():
    with open(CS, encoding="utf-8") as f:
        return f.read()


def nav_branches(text):
    """
    Return {button: branch body} for every `source == NavX` branch.

    Slice by POSITION, not by re.split. Splitting the text on the branch
    pattern also splits each chunk at its own match, so every body came back
    empty and the gate reported three wired buttons as dead — a false positive
    that would have been "fixed" by weakening the test.
    """
    start = text.index("private void Nav_Click")
    body = text[start:]
    # Cut at the end of the METHOD. Without this the last branch swallows every
    # method defined after it, and NavParties "calls" OpenTools, OpenReports and
    # OpenImport — all three of which belong to other branches. That produced a
    # false "stale PLANNED entry" for a button that is genuinely not wired.
    end_of_method = body.find("\n        private void SelectTool")
    if end_of_method > 0:
        body = body[:end_of_method]
    matches = list(re.finditer(r"source == (Nav\w+)", body))
    branches = {}
    for idx, m in enumerate(matches):
        end_pos = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        branches[m.group(1)] = body[m.end():end_pos]
    return branches


def actions_in(chunk):
    """Method calls that are not SelectTool and look like the real action."""
    return re.findall(r"\b(Open\w+)\s*\(", chunk)


def all_nav_buttons_in_xaml():
    xaml = os.path.join(ROOT, "src", "Mazandasht.Presentation", "MainWindow.xaml")
    with open(xaml, encoding="utf-8") as f:
        text = f.read()
    return re.findall(r'x:Name="(Nav\w+)"[^>]*Click="Nav_Click"', text)


# ---------------------------------------------------------------------------
def t_every_nav_button_has_a_branch():
    """A button with Click="Nav_Click" and no branch falls through silently."""
    text = source()
    branches = nav_branches(text)
    buttons = all_nav_buttons_in_xaml()
    assert buttons, "هیچ دکمه ناوبری پیدا نشد — تست بی‌اثر است"
    missing = [b for b in buttons if b not in branches]
    assert not missing, "دکمه بدون شاخه در Nav_Click: %s" % missing
    print("      %d دکمه ناوبری، %d شاخه" % (len(buttons), len(branches)))


def t_wired_branch_calls_an_action():
    """Reports shipped with a branch that only relabelled itself. Every branch
    not in PLANNED must call an Open* method."""
    branches = nav_branches(source())
    dead = []
    for name, chunk in branches.items():
        if name in PLANNED:
            continue
        if not actions_in(chunk):
            dead.append(name)
    assert not dead, (
        "دکمه‌ای که فقط عنوان را عوض می‌کند و کاری نمی‌کند: %s — "
        "یا Open* را صدا بزنید یا به PLANNED با دلیل اضافه کنید" % dead)


def t_planned_entries_still_exist():
    """A PLANNED entry for a button that has since been wired hides the fix:
    the list would claim a feature is missing after it works."""
    branches = nav_branches(source())
    stale = []
    for name, reason in PLANNED.items():
        if name not in branches:
            stale.append("%s (شاخه وجود ندارد)" % name)
        elif actions_in(branches[name]):
            stale.append("%s (اکنون Open* را صدا می‌زند)" % name)
    assert not stale, "مدخل کهنه در PLANNED: %s" % stale


def t_planned_entries_have_a_reason():
    for name, reason in PLANNED.items():
        assert reason and len(reason.strip()) >= 5, \
            "%s دلیل ندارد؛ «بعداً» دلیل نیست" % name


def t_reports_is_actually_wired():
    """The specific regression this gate was written for."""
    branches = nav_branches(source())
    assert "NavReports" in branches, "شاخه گزارش‌ها نیست"
    assert "OpenReports" in branches["NavReports"], \
        "دکمه گزارش‌ها دوباره فقط عنوان را عوض می‌کند"
    assert "NavReports" not in PLANNED, \
        "گزارش‌ها نباید در PLANNED باشد؛ ساخته شده است"


def t_every_open_method_exists():
    """OpenX() must have a definition, or the branch throws at click time."""
    text = source()
    branches = nav_branches(text)
    called = set()
    for chunk in branches.values():
        called.update(actions_in(chunk))
    defined = set(re.findall(r"private void (Open\w+)\s*\(", text))
    missing = called - defined
    assert not missing, "متد صدا زده‌شده ولی تعریف‌نشده: %s" % missing


TESTS = [
    ("هر دکمه ناوبری شاخه دارد", t_every_nav_button_has_a_branch),
    ("هر شاخه وصل‌شده یک اقدام صدا می‌زند", t_wired_branch_calls_an_action),
    ("PLANNED هیچ مدخل کهنه‌ای ندارد", t_planned_entries_still_exist),
    ("هر مدخل PLANNED دلیل دارد", t_planned_entries_have_a_reason),
    ("دکمه گزارش‌ها واقعاً وصل است", t_reports_is_actually_wired),
    ("هر Open* تعریف شده است", t_every_open_method_exists),
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
