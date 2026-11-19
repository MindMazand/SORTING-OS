#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAZANDASHT — static XAML checker.

WHY THIS EXISTS

There is no C# toolchain in this environment and the target is WPF on
.NET Framework 4.8, which cannot build or run on Linux at all (see
reports/CSHARP_BUILD_ATTEMPT_FA.md). That means every XAML file written here is
unverified by the compiler.

Unverified XAML is not harmless. The failures it can hide are exactly the ones
that would crash the app on the owner's machine, at startup, with a dialog:

  * a StaticResource pointing at a key that does not exist  -> XamlParseException
  * a BasedOn referencing a Style of the wrong TargetType    -> invalid cast
  * an event handler in XAML with no matching method in .cs  -> exception at load
  * a x:Class with no code-behind file, or a mismatch         -> build error
  * duplicate x:Key in one dictionary                        -> last one wins, silently

This tool checks those five things without a compiler. It is a linter, not a
build: it cannot tell you a layout looks right. It can tell you the app will
not explode on load.

    python3 tools/check_xaml.py            # check src/
    python3 tools/check_xaml.py --strict   # also enforce the no-hex-in-pages rule
"""
import os
import re
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")

XAML_NS = "http://schemas.microsoft.com/winfx/2006/xaml"
THEME_FILES = {"theme.xaml", "theme.v2.xaml", "tokens.xaml"}

# WPF types whose TargetType-based styles we can sanity-check cheaply.
KNOWN_CONTROL_TYPES = {
    "Button", "ToggleButton", "RadioButton", "CheckBox", "TextBlock", "TextBox",
    "Border", "DataGrid", "DataGridColumnHeader", "DataGridCell", "DataGridRow",
    "ListBox", "ListBoxItem", "ComboBox", "ComboBoxItem", "Window", "Grid",
    "StackPanel", "DockPanel", "WrapPanel", "UniformGrid", "ItemsControl",
    "ContentControl", "ScrollViewer", "ScrollBar", "Slider", "ProgressBar",
    "TabControl", "TabItem", "MenuItem", "ContextMenu", "ToolTip", "Separator",
    "Expander", "GroupBox", "Label", "Hyperlink", "Path", "Ellipse",
    "Rectangle", "Canvas", "Viewbox", "StatusBar", "ToolBar", "TreeView",
    "TreeViewItem", "ListView", "ListViewItem", "PasswordBox", "RichTextBox",
    "DatePicker", "Calendar", "Popup", "Thumb", "RepeatButton", "ToggleMenuButton",
}

# Attributes that are XAML infrastructure, not event handlers.
NON_EVENT_ATTRS = {
    "Name", "Key", "Class", "Uid", "Title", "Tag", "Text", "Content", "Header",
    "Style", "BasedOn", "TargetType", "DataType", "Source", "Mode", "Path",
    "Binding", "Converter", "ElementName", "RelativeSource", "StaticResource",
    "DynamicResource", "Template", "ItemsSource", "Margin", "Padding", "Width",
    "Height", "Background", "Foreground", "FontSize", "FontFamily", "FontWeight",
    "FlowDirection", "Visibility", "HorizontalAlignment", "VerticalAlignment",
    "Grid.Row", "Grid.Column", "Grid.RowSpan", "Grid.ColumnSpan", "TextAlignment",
    "CornerRadius", "BorderThickness", "BorderBrush", "Opacity", "IsEnabled",
    "IsChecked", "IsReadOnly", "AutoGenerateColumns", "CanUserAddRows",
    "CanUserDeleteRows", "SelectionMode", "RowHeight", "GridLinesVisibility",
    "HeadersVisibility", "AlternatingRowBackground", "RowBackground", "Effect",
    "SnapsToDevicePixels", "Cursor", "WindowStartupLocation", "MaxWidth",
    "MinWidth", "MaxHeight", "MinHeight", "ToolTip", "Value", "Property",
    "TargetName", "Orientation", "Columns", "Rows", "ColumnDefinitions",
    "RowDefinitions", "PlacementTarget", "Placement", "From", "To", "Duration",
    "Storyboard.TargetProperty", "Storyboard.TargetName", "EasingMode",
    "TextTrimming", "TextWrapping", "x", "xmlns", "d", "mc",
}


class Finding(object):
    def __init__(self, level, path, line, message):
        self.level = level          # ERROR / WARN
        self.path = path
        self.line = line
        self.message = message

    def __str__(self):
        name = os.path.relpath(self.path, ROOT)
        return "%-5s %s:%s  %s" % (self.level, name, self.line, self.message)


def _local(tag):
    return tag.split("}", 1)[1] if "}" in tag else tag


def _line_of(text, needle, start=0):
    idx = text.find(needle, start)
    if idx < 0:
        return 0
    return text.count("\n", 0, idx) + 1


def find_xaml():
    out = []
    for base, _dirs, files in os.walk(SRC):
        for f in files:
            if f.lower().endswith(".xaml"):
                out.append(os.path.join(base, f))
    return sorted(out)


# ---------------------------------------------------------------------------
# 1. Collect every defined key, and detect duplicates within a dictionary.
# ---------------------------------------------------------------------------
def collect_keys(path, text):
    """Returns (keys, duplicates). Only top-level ResourceDictionary entries and
    resource defs are considered — a nested Key is still a key in scope."""
    keys = []
    dups = []
    try:
        root = ET.fromstring(text.encode("utf-8"))
    except ET.ParseError as e:
        return keys, dups, "XML parse error: %s" % e

    seen = {}

    def walk(el):
        for k, v in el.attrib.items():
            if _local(k) == "Key":
                keys.append(v)
                if v in seen:
                    dups.append(v)
                seen[v] = True
        for child in el:
            walk(child)

    walk(root)
    return keys, dups, None


def collect_references(text):
    """Every {StaticResource X} and {DynamicResource X} in the file."""
    refs = []
    for m in re.finditer(r"\{(?:Static|Dynamic)Resource\s+([^\s,}]+)", text):
        refs.append((m.group(1), text.count("\n", 0, m.start()) + 1))
    return refs


# ---------------------------------------------------------------------------
# 2. Event handlers written in XAML must exist in the code-behind.
# ---------------------------------------------------------------------------
def collect_handlers(root, text):
    handlers = []
    for m in re.finditer(r'\b(\w+)="([A-Za-z_]\w*)"', text):
        attr, value = m.group(1), m.group(2)
        if attr in NON_EVENT_ATTRS or "." in attr:
            continue
        # A handler attribute is one whose value looks like a method name and
        # whose name is not a known property. WPF event names are verbs.
        if attr[0].islower():
            continue
        if not re.match(r"^[A-Z][A-Za-z0-9]*$", attr):
            continue
        # Require the conventional event suffix to avoid false positives on
        # custom attached properties.
        if not re.search(r"(Click|Changed|Loaded|Closing|Closed|KeyDown|KeyUp|"
                         r"MouseDown|MouseUp|MouseMove|MouseWheel|SelectionChanged|"
                         r"Opened|DoubleClick|GotFocus|LostFocus|SizeChanged|"
                         r"TextChanged|Checked|Unchecked|Drop|DragOver|Enter|"
                         r"Leave|Command)$", attr):
            continue
        handlers.append((attr, value, text.count("\n", 0, m.start()) + 1))
    return handlers


def code_behind_for(xaml_path):
    for ext in (".xaml.cs", ".xaml.vb"):
        candidate = xaml_path + ext if ext == ".xaml.cs" else xaml_path[:-5] + ext
        if os.path.exists(candidate):
            return candidate
    # MainWindow.xaml -> MainWindow.xaml.cs
    if os.path.exists(xaml_path + ".cs"):
        return xaml_path + ".cs"
    return None


# ---------------------------------------------------------------------------
# 3. Style TargetType / BasedOn agreement.
# ---------------------------------------------------------------------------
def collect_styles(root):
    """(style_key, target_type, based_on, line_guess) for each Style."""
    styles = []

    def walk(el):
        if _local(el.tag) == "Style":
            key = el.get("{%s}Key" % XAML_NS) or el.get("x:Key")
            target = el.get("TargetType", "")
            based = el.get("BasedOn", "")
            m = re.match(r"\{StaticResource\s+([^\s,}]+)", based or "")
            styles.append((key, target, m.group(1) if m else None))
        for child in el:
            walk(child)

    walk(root)
    return styles


STYLE_TARGETS = {}


def check_style_targets(path, text):
    """A Style applied to an element of a different type throws XamlParseException
    at load time with a message that names neither the file's real problem nor
    the fix. Catching it statically is cheap."""
    findings = []
    for m in re.finditer(r'<(\w+)\b([^>]*?)Style="\{StaticResource\s+([^\s,}]+)\}"', text, re.S):
        element, _attrs, style_key = m.group(1), m.group(2), m.group(3)
        line = text.count("\n", 0, m.start()) + 1
        expected = STYLE_TARGETS.get(style_key)
        if expected is None:
            continue
        name = expected.split(":")[-1]
        if name and name != element:
            findings.append(Finding(
                "ERROR", path, line,
                'استایل «%s» از نوع %s است ولی روی %s اعمال شده'
                % (style_key, name, element)))
    return findings


def main(argv):
    strict = "--strict" in argv
    files = find_xaml()
    if not files:
        print("NOTE  هیچ فایل XAML پیدا نشد.")
        return 0

    findings = []
    global_keys = {}
    all_styles = {}

    parsed = []
    for path in files:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        keys, dups, err = collect_keys(path, text)
        if err:
            findings.append(Finding("ERROR", path, _line_of(text, "<"), err))
            continue
        parsed.append((path, text, keys))
        for k in keys:
            global_keys.setdefault(k, []).append(os.path.relpath(path, ROOT))

    # Duplicate keys are only a defect within the same file; across files the
    # last merged dictionary legitimately wins, which is a design decision.
    for path, text, keys in parsed:
        seen = set()
        dups = [k for k in keys if k in seen or seen.add(k)]
        for d in sorted(set(dups)):
            findings.append(Finding(
                "ERROR", path, _line_of(text, 'Key="%s"' % d),
                'کلید تکراری «%s» در یک دیکشنری؛ مقدار اول بی‌صدا نادیده گرفته می‌شود' % d))

    # Unresolved resource references.
    for path, text, keys in parsed:
        for ref, line in collect_references(text):
            if ref not in global_keys:
                findings.append(Finding(
                    "ERROR", path, line,
                    'منبع «%s» تعریف نشده است؛ در زمان اجرا XamlParseException می‌دهد' % ref))

    # TargetType / BasedOn agreement.
    for path, text, keys in parsed:
        try:
            root = ET.fromstring(text.encode("utf-8"))
        except ET.ParseError:
            continue
        for key, target, based in collect_styles(root):
            if target:
                t = re.sub(r"^\{x:Type\s*", "", target).rstrip("}")
                if t and t not in KNOWN_CONTROL_TYPES and not t.startswith("local:"):
                    findings.append(Finding(
                        "WARN", path, 0, 'TargetType ناشناخته «%s»' % t))
                    all_styles.setdefault(key or "?", t)
                else:
                    all_styles.setdefault(key or "?", t)
            if based and based not in global_keys:
                findings.append(Finding(
                    "ERROR", path, 0,
                    'BasedOn به «%s» اشاره می‌کند که تعریف نشده' % based))
            elif based and key:
                base_t = all_styles.get(based)
                if base_t and t and base_t != t:
                    findings.append(Finding(
                        "ERROR", path, 0,
                        'BasedOn: TargetType «%s» با پایه «%s» از نوع «%s» نمی‌خواند'
                        % (t, based, base_t)))

    # Code-behind existence and handler methods.
    for path in files:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        if 'x:Class="' not in text:
            continue
        cb = code_behind_for(path)
        if cb is None:
            findings.append(Finding(
                "ERROR", path, _line_of(text, 'x:Class='),
                "x:Class دارد ولی فایل code-behind نیست"))
            continue
        with open(cb, encoding="utf-8") as fh:
            cs = fh.read()
        for attr, handler, line in collect_handlers(None, text):
            if not re.search(r"\b%s\s*\(" % re.escape(handler), cs):
                findings.append(Finding(
                    "ERROR", path, line,
                    'رویداد %s به «%s» وصل است که در %s نیست'
                    % (attr, handler, os.path.basename(cb))))

    # Style target-type agreement needs the styles collected first, so it runs
    # as its own pass after all dictionaries are read.
    for key, target in all_styles.items():
        STYLE_TARGETS[key] = target
    for path, text, keys in parsed:
        findings.extend(check_style_targets(path, text))

    # Design rule: no hex colours in page files.
    if strict:
        for path, text, keys in parsed:
            if os.path.basename(path).lower() in THEME_FILES:
                continue
            for m in re.finditer(r"#[0-9A-Fa-f]{6,8}\b", text):
                findings.append(Finding(
                    "ERROR", path, text.count("\n", 0, m.start()) + 1,
                    "رنگ خام %s در صفحه؛ باید توکن تم باشد" % m.group(0)))

    errors = [f for f in findings if f.level == "ERROR"]
    warns = [f for f in findings if f.level == "WARN"]
    for f in findings:
        print(f)

    print()
    print("فایل‌های XAML: %d · کلید منابع: %d · خطا: %d · هشدار: %d"
          % (len(files), len(global_keys), len(errors), len(warns)))
    if errors:
        print("FAIL  XAML از نظر مراجع/رویدادها سالم نیست")
        return 1
    print("PASS  همه مراجع منابع و رویدادهای XAML حل شدند")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
