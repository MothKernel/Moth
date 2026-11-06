"""Native Qt Widgets UI. Calls the Python engine directly; no web server or WebView."""
import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QSettings, QLockFile, QUrl
from PySide6.QtGui import QIcon, QDesktopServices, QPalette, QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QLineEdit, QCheckBox,
    QComboBox, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QStackedWidget,
    QGroupBox, QScrollArea, QSplitter, QTreeWidget, QTreeWidgetItem, QPlainTextEdit,
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QMessageBox, QAbstractItemView, QSizePolicy, QTabWidget, QButtonGroup,
)
from . import __version__, engine, storage, tools, updates
from .config import ROOT, DATA
from .profiles import PROFILES, scope
from .tips import TipDeck
from . import estimates
from .reports import render
from .presentation import describe, error_help, evidence_text, OBSERVATIONS, finding_sort_keys

RESOURCES = ROOT / "resources"
TRANSLATIONS = json.loads((RESOURCES / "translations.json").read_text(encoding="utf-8"))
FINISHED = {"completed", "partial", "failed", "cancelled", "interrupted"}

STYLE = """
QWidget { font-family: 'Segoe UI', 'DejaVu Sans'; font-size: 13px; color: #203c32; }
QMainWindow, QWidget#content, QDialog, QMessageBox { background: #f5f5ef; }
QMessageBox QLabel { color: #203c32; background: transparent; }
QMessageBox QTextEdit { background: white; color: #203c32; border: 1px solid #dce3d4; }
QFrame#tipCard { background: #edf2e6; border: 1px solid #dce3d4; border-radius: 7px; }
QPushButton#tipAction { font-size: 11px; padding: 6px 8px; }
QFrame#sidebar { background: #eaf0e3; border-right: 1px solid #dbe2d3; }
QLabel#brand { font-size: 34px; font-weight: 700; }
QLabel#heading { font-size: 27px; font-weight: 600; }
QLabel#muted { color: #75836c; }
QLabel#resultTitle { font-size: 17px; font-weight: 600; }
QLabel#notice { background: #fff0e8; color: #914b37; padding: 12px; border-radius: 5px; }
QGroupBox { background: white; border: 1px solid #dce3d4; border-radius: 9px;
            margin-top: 15px; padding: 18px 14px 12px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 5px; }
QPushButton { background: #f7f8f2; border: 1px solid #d7dfce; border-radius: 6px;
              padding: 9px 15px; }
QPushButton:hover { background: #e5edda; }
QPushButton:disabled { color: #9aa58f; background: #f0f2eb; }
QPushButton#primary, QPushButton[navActive="true"] { background: #203c32; color: white; border: 1px solid #203c32; }
QPushButton#primary:hover { background: #345844; }
QPushButton#stop { color: #a44632; }
QLineEdit, QComboBox { background: white; border: 1px solid #ccd7c1; border-radius: 5px; padding: 9px; }
QLineEdit:focus { border: 2px solid #8aa666; }
QCheckBox { spacing: 9px; padding: 4px 0; font-weight: 400; }
QCheckBox:disabled { color: #9aa58f; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #75836c; border-radius: 3px; background: white; }
QCheckBox::indicator:hover { border: 1px solid #8aa666; background: #e5edda; }
QCheckBox::indicator:checked { background: #93bd78; border: 1px solid #638a50; image: url("__CHECK_ICON__"); }
QCheckBox::indicator:disabled { background: #f0f2eb; border-color: #d7dfce; }
QCheckBox::indicator:checked:disabled { background: #9aa58f; }
QProgressBar { border: 1px solid #dce3d4; background: white; border-radius: 4px; text-align: center; min-height: 20px; }
QProgressBar::chunk { background: #bfdaa0; border-radius: 3px; }
QTreeWidget, QTableWidget, QPlainTextEdit { background: white; border: 1px solid #dce3d4; border-radius: 5px; selection-background-color: #dcebbf; selection-color: #203c32; }
QTreeWidget, QTableWidget { alternate-background-color: #edf2e6; }
QTreeWidget::item:alternate, QTableWidget::item:alternate { background: #edf2e6; }
QTreeWidget::item:selected, QTableWidget::item:selected { background: #dcebbf; color: #203c32; }
QTreeWidget::item:selected:!active, QTableWidget::item:selected:!active { background: #dcebbf; color: #203c32; }
QTreeWidget::item:focus { border: 0; }
QTabWidget::pane { border: 0; }
QTabBar::tab { background: #edf2e6; color: #203c32; padding: 9px 14px; border: 1px solid #dce3d4; }
QTabBar::tab:selected { background: white; border-bottom: 2px solid #8aa666; }
QHeaderView::section { background: #edf2e6; border: 0; border-bottom: 1px solid #dce3d4; padding: 9px; }
QTreeWidget::item, QTableWidget::item { padding: 7px; }
QScrollArea { border: 0; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: #edf2e6; width: 12px; margin: 0; }
QScrollBar:horizontal { background: #edf2e6; height: 12px; margin: 0; }
QScrollBar::handle:vertical { background: #9aa58f; min-height: 28px; border-radius: 5px; }
QScrollBar::handle:horizontal { background: #9aa58f; min-width: 28px; border-radius: 5px; }
QScrollBar::handle:hover { background: #8aa666; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QSplitter::handle { background: #e2e8d9; border-radius: 2px; }
QStatusBar { background: #eaf0e3; color: #718267; }
QComboBox QAbstractItemView { background: white; color: #203c32; selection-background-color: #dcebbf; selection-color: #203c32; }
QLabel#toolStatus { padding: 5px 10px; border-radius: 5px; font-weight: 600; }
QLabel#toolStatus[state="ready"] { color: #166534; background: #dcfce7; }
QLabel#toolStatus[state="missing"], QLabel#toolStatus[state="manual"], QLabel#toolStatus[state="prerequisite"] { color: #92400e; background: #fef3c7; }
QLabel#toolStatus[state="installing"], QLabel#toolStatus[state="queued"] { color: #1e40af; background: #dbeafe; }
QLabel#toolStatus[state="available"] { color: #92400e; background: #fef3c7; }
QLabel#toolStatus[state="error"] { color: #991b1b; background: #fee2e2; }
"""

STYLE = STYLE.replace("__CHECK_ICON__", (RESOURCES / "check.svg").as_posix())


DARK_COLORS = {
    "#203c32": "#e2eae5", "#f5f5ef": "#141b18", "#eaf0e3": "#1b2620",
    "#dbe2d3": "#33443a", "#75836c": "#a5b7aa", "#fff0e8": "#402a24",
    "#914b37": "#ffb39a", "white": "#202d26", "#dce3d4": "#3c5043",
    "#f7f8f2": "#28382e", "#d7dfce": "#4b6252", "#e5edda": "#354c3d",
    "#9aa58f": "#8a9b90", "#f0f2eb": "#253129", "#345844": "#a6cf8b",
    "#a44632": "#ffad98", "#ccd7c1": "#4b6252", "#8aa666": "#a6cf8b",
    "#bfdaa0": "#638a50", "#dcebbf": "#415f3e", "#edf2e6": "#28382e",
    "#e2e8d9": "#33443a", "#718267": "#a5b7aa",
    "#166534": "#a7f3b8", "#dcfce7": "#1c4930", "#92400e": "#fde095",
    "#fef3c7": "#4b391c", "#1e40af": "#bfdbfe", "#dbeafe": "#243d62",
    "#991b1b": "#fecaca", "#fee2e2": "#592c30",
}


def theme_style(theme):
    if theme == "light":
        return STYLE
    # Replace all colors in one pass so replacements cannot replace each other.
    import re
    style = re.sub(r"#[0-9a-f]{6}\b|\bwhite\b", lambda m: DARK_COLORS.get(m[0], m[0]), STYLE)
    return style + """
QPushButton#primary, QPushButton[navActive="true"] { background: #93bd78; color: #142219; border-color: #93bd78; }
QPushButton#primary:hover { background: #a6cf8b; }
"""


class FindingTreeItem(QTreeWidgetItem):
    sort_key = (0, 0)

    def __lt__(self, other):
        return self.sort_key < other.sort_key


class OptionCheckBox(QCheckBox):
    """Use the entire option row as the click target, including trailing space."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def hitButton(self, position):
        return self.rect().contains(position)


def text_label(text="", name=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    if name:
        widget.setObjectName(name)
    return widget


def scroller(widget):
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(widget)
    return area


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            clear_layout(item.layout())


class MainWindow(QMainWindow):
    def __init__(self, settings=None):
        super().__init__()
        self.settings = settings or QSettings("MothKernel", "Moth")
        self.language = self.settings.value("language", "en")
        if self.language not in TRANSLATIONS:
            self.language = "en"
        self.theme = self.settings.value("theme", "light")
        if self.theme not in ("light", "dark"):
            self.theme = "light"
        self.tip_deck = TipDeck()
        self.current_tip = None
        self._tips_scan_id = None
        self.profile = "low"
        self.current = None
        self._last_scan = None
        self._last_tools = None
        self._last_history = None
        self._rendered_scan_id = None
        self._pending_close = False
        self._closing_install = False
        self._translated = []
        self.tool_checks = {}
        self.tool_rows = []
        self.setWindowTitle(f"Moth {__version__}")
        self.setWindowIcon(QIcon(str(RESOURCES / "moth.png")))
        self.setMinimumSize(1000, 720)
        self.resize(1280, 900)
        self.apply_theme()
        self._build()
        self.translate()
        self.refresh_tools(force=True)
        self.refresh_history(force=True)
        self.tip_timer = QTimer(self)
        self.tip_timer.setInterval(20000)
        self.tip_timer.timeout.connect(self.next_tip)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(500)
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.check_updates)
        if not os.environ.get("MOTH_DISABLE_UPDATE_CHECKS") and "--smoke-test" not in sys.argv:
            QTimer.singleShot(1500, self, self.check_updates)
            self.update_timer.start(60000)

    def tr_text(self, key):
        return TRANSLATIONS[self.language].get(key, TRANSLATIONS["en"].get(key, key))

    def bind(self, widget, key, setter="setText"):
        self._translated.append((widget, key, setter))
        getattr(widget, setter)(self.tr_text(key))
        return widget

    def label(self, key, name=None):
        return self.bind(text_label(name=name), key)

    def button(self, key, slot=None, name=None):
        button = self.bind(QPushButton(), key)
        if name:
            button.setObjectName(name)
        if slot:
            button.clicked.connect(slot)
        return button

    def group(self, key):
        return self.bind(QGroupBox(), key, "setTitle")

    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        row = QHBoxLayout(root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(190)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(20, 30, 20, 24)
        brand = text_label("moth.", "brand")
        brand.setPixmap(QIcon(str(RESOURCES / "moth.png")).pixmap(36, 36))
        brand.setFixedSize(36, 36)
        branding = QHBoxLayout()
        branding.addWidget(brand)
        branding.addWidget(text_label("moth.", "brand"))
        side_layout.addLayout(branding)
        side_layout.addSpacing(35)
        self.nav = []
        for index, key in enumerate(("assessment", "tools", "history")):
            button = self.button(key)
            button.setMinimumHeight(44)
            button.clicked.connect(lambda checked=False, index=index: self.switch_page(index))
            self.nav.append(button)
            side_layout.addWidget(button)
        side_layout.addStretch()
        side_layout.addWidget(text_label(f"MOTH / {__version__}", "muted"))
        row.addWidget(side)
        content = QWidget()
        content.setObjectName("content")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 20, 28, 15)
        header = QHBoxLayout()
        self.heading = text_label(name="heading")
        header.addWidget(self.heading, 1)
        header.addWidget(self.label("theme"))
        self.theme_box = QComboBox()
        self.theme_box.setObjectName("theme")
        self.theme_box.addItem(self.tr_text("theme_light"), "light")
        self.theme_box.addItem(self.tr_text("theme_dark"), "dark")
        self.theme_box.setCurrentIndex(self.theme_box.findData(self.theme))
        self.theme_box.currentIndexChanged.connect(self.change_theme)
        header.addWidget(self.theme_box)
        self.language_box = QComboBox()
        self.language_box.setObjectName("language")
        for label, code in (("English", "en"), ("Română", "ro"), ("Русский", "ru")):
            self.language_box.addItem(label, code)
        self.language_box.setCurrentIndex(self.language_box.findData(self.language))
        self.language_box.currentIndexChanged.connect(self.change_language)
        header.addWidget(self.language_box)
        layout.addLayout(header)
        self.notice = text_label(name="notice")
        self.notice.setObjectName("notice")
        self.notice.hide()
        layout.addWidget(self.notice)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._scan_page())
        self.pages.addWidget(self._tools_page())
        self.pages.addWidget(self._history_page())
        layout.addWidget(self.pages, 1)
        row.addWidget(content, 1)
        self.switch_page(0)

    def _scan_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        profile_row = QHBoxLayout()
        profile_row.addWidget(self.label("scan_level"))
        self.profile_group = QButtonGroup(self)
        self.profile_group.setExclusive(True)
        self.profile_buttons = {}
        for name in PROFILES:
            button = OptionCheckBox(name.title())
            button.setObjectName("profile_" + name)
            button.setProperty("profile", name)
            self.profile_group.addButton(button)
            self.profile_buttons[name] = button
            profile_row.addWidget(button)
        self.profile_buttons[self.profile].setChecked(True)
        self.profile_group.buttonToggled.connect(lambda button, checked: self.change_profile(button.property("profile")) if checked else None)
        profile_row.addStretch()
        profile_row.addWidget(self.button("profile_details", self.show_profile_details))
        layout.addLayout(profile_row)
        self.profile_note = text_label(name="muted")
        layout.addWidget(self.profile_note)
        self.scan_split = QSplitter(Qt.Orientation.Vertical)
        upper = QWidget()
        top = QHBoxLayout(upper)
        top.setContentsMargins(0, 0, 0, 0)
        form = self.group("target")
        form_layout = QVBoxLayout(form)
        form_layout.addWidget(self.label("website"))
        self.target = QLineEdit()
        self.target.setObjectName("target")
        self.target.setPlaceholderText("https://your-website.com")
        self.target.setMaxLength(2048)
        self.target.returnPressed.connect(self.start_scan)
        form_layout.addWidget(self.target)
        self.scope_note = self.label("scope_note", "muted")
        form_layout.addWidget(self.scope_note)
        self.authorized = self.bind(OptionCheckBox(), "authorized")
        self.authorized.setObjectName("authorized")
        self.lab = self.bind(OptionCheckBox(), "lab")
        self.lab.setObjectName("lab")
        self.active_consent = self.bind(OptionCheckBox(), "active_consent")
        self.active_consent.setObjectName("activeConsent")
        self.active_consent.hide()
        form_layout.addWidget(self.active_consent)
        form_layout.addWidget(self.authorized)
        form_layout.addWidget(self.lab)
        self.extra_toggle = self.bind(OptionCheckBox(), "extra_tools")
        self.extra_toggle.setObjectName("extraTools")
        form_layout.addWidget(self.extra_toggle)
        options = QWidget()
        self.options_layout = QGridLayout(options)
        self.options_layout.setContentsMargins(0, 0, 0, 0)
        for index, tool in enumerate(tools.REGISTRY):
            check = OptionCheckBox(tool["name"])
            check.setObjectName("tool_" + tool["id"])
            self.tool_checks[tool["id"]] = check
            self.options_layout.addWidget(check, index // 2, index % 2)
        self.options_scroll = scroller(options)
        self.options_scroll.setMaximumHeight(140)
        self.options_scroll.hide()
        self.extra_toggle.toggled.connect(self.options_scroll.setVisible)
        form_layout.addWidget(self.options_scroll)
        form_layout.addStretch()
        self.start_button = self.button("start", self.start_scan, "primary")
        self.start_button.setMinimumHeight(42)
        form_layout.addWidget(self.start_button)
        top.addWidget(form, 3)
        overview = self.group("overview")
        overview.setMinimumWidth(260)
        overview_layout = QVBoxLayout(overview)
        self.progress_title = text_label(name="resultTitle")
        overview_layout.addWidget(self.progress_title)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        overview_layout.addWidget(self.progress)
        self.stage = text_label(name="muted")
        overview_layout.addWidget(self.stage)
        self.total_time = text_label(name="muted")
        self.current_time = text_label(name="muted")
        overview_layout.addWidget(self.total_time)
        overview_layout.addWidget(self.current_time)
        self.step_text = QPlainTextEdit()
        self.step_text.setReadOnly(True)
        self.step_text.setMaximumHeight(95)
        overview_layout.addWidget(self.step_text)
        self.stop_button = self.button("stop", self.stop_scan, "stop")
        self.stop_button.hide()
        overview_layout.addWidget(self.stop_button)
        overview_layout.addWidget(self.label("coverage_note", "muted"))
        self.tip_card = QFrame()
        self.tip_card.setObjectName("tipCard")
        self.tip_card.setMinimumHeight(164)
        tip_layout = QVBoxLayout(self.tip_card)
        tip_layout.setContentsMargins(12, 10, 12, 10)
        self.tip_heading = text_label(name="muted")
        self.tip_body = text_label()
        self.tip_body.setObjectName("tipText")
        self.tip_body.setMinimumHeight(64)
        self.tip_body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        tip_layout.addWidget(self.tip_heading)
        tip_layout.addWidget(self.tip_body)
        tip_buttons = QHBoxLayout()
        tip_buttons.addWidget(self.button("next_tip", self.next_tip, "tipAction"))
        self.tip_pause = self.button("pause_tips", name="tipAction")
        self.tip_pause.setCheckable(True)
        self.tip_pause.toggled.connect(self.pause_tips)
        tip_buttons.addWidget(self.tip_pause)
        self.tip_source = self.button("tip_source", self.open_tip_source, "tipAction")
        for button in (tip_buttons.itemAt(0).widget(), self.tip_pause, self.tip_source):
            button.setMinimumHeight(28)
        tip_buttons.addWidget(self.tip_source)
        tip_buttons.addStretch()
        tip_layout.addLayout(tip_buttons)
        self.tip_card.hide()
        overview_layout.addWidget(self.tip_card)
        overview_layout.addStretch()
        top.addWidget(overview, 2)
        self.scan_split.addWidget(scroller(upper))
        lower = self.group("results")
        results_layout = QVBoxLayout(lower)
        exports = QHBoxLayout()
        self.summary = text_label(name="muted")
        exports.addWidget(self.summary, 1)
        for extension in ("html", "json"):
            button = QPushButton(extension.upper() + " ↓")
            button.setObjectName("export_" + extension)
            button.clicked.connect(lambda checked=False, fmt=extension: self.export_report(fmt))
            exports.addWidget(button)
        results_layout.addLayout(exports)
        result_split = QSplitter(Qt.Orientation.Horizontal)
        self.findings = QTreeWidget()
        self.findings.setObjectName("findings")
        self.findings.setRootIsDecorated(False)
        self.findings.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.findings.setAlternatingRowColors(True)
        self.findings.setColumnCount(3)
        self.findings.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.findings.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.findings.setColumnWidth(0, 90)
        self.findings.setColumnWidth(2, 85)
        self.findings.currentItemChanged.connect(self.select_finding)
        result_split.addWidget(self.findings)
        details = QWidget()
        detail_layout = QVBoxLayout(details)
        detail_layout.setContentsMargins(14, 0, 0, 0)
        self.result_title = text_label(name="resultTitle")
        detail_layout.addWidget(self.result_title)
        self.explanation = QPlainTextEdit()
        self.explanation.setObjectName("explanation")
        self.explanation.setReadOnly(True)
        detail_layout.addWidget(self.explanation, 1)
        self.technical_toggle = self.bind(OptionCheckBox(), "technical")
        detail_layout.addWidget(self.technical_toggle)
        self.technical = QPlainTextEdit()
        self.technical.setObjectName("technical")
        self.technical.setReadOnly(True)
        self.technical.hide()
        self.technical_toggle.toggled.connect(self.technical.setVisible)
        detail_layout.addWidget(self.technical, 1)
        result_split.addWidget(details)
        result_split.setSizes([500, 500])
        self.result_tabs = QTabWidget()
        self.result_tabs.setObjectName("resultTabs")
        findings_page = QWidget()
        findings_layout = QVBoxLayout(findings_page)
        findings_layout.setContentsMargins(0, 10, 0, 0)
        filters = QHBoxLayout()
        self.finding_search = QLineEdit()
        self.finding_search.setObjectName("findingSearch")
        self.finding_search.setClearButtonEnabled(True)
        self.finding_search.textChanged.connect(self.filter_findings)
        filters.addWidget(self.finding_search, 1)
        self.reset_filters_button = self.button("reset_filters", self.reset_finding_filters)
        filters.addWidget(self.reset_filters_button)
        findings_layout.addLayout(filters)
        filter_row = QHBoxLayout()
        self.severity_filter = QComboBox()
        self.severity_filter.setObjectName("severityFilter")
        for key in ("all_severities", "critical", "high", "medium", "low", "info"):
            self.severity_filter.addItem(self.tr_text(key), key)
        self.tool_filter = QComboBox()
        self.tool_filter.setObjectName("toolFilter")
        self.tool_filter.addItem(self.tr_text("all_tools"), "all_tools")
        self.tool_filter.addItem("moth", "moth")
        for tool in tools.REGISTRY:
            self.tool_filter.addItem(tool["name"], tool["id"])
        self.kind_filter = QComboBox()
        self.kind_filter.setObjectName("kindFilter")
        for key in ("all_types", "configuration", "hardening", "review", "information"):
            self.kind_filter.addItem(self.tr_text(key), key)
        for widget in (self.severity_filter, self.tool_filter, self.kind_filter):
            widget.currentIndexChanged.connect(self.filter_findings)
            filter_row.addWidget(widget)
        self.visible_findings = text_label(name="muted")
        filter_row.addWidget(self.visible_findings, 1)
        findings_layout.addLayout(filter_row)
        sorting = QHBoxLayout()
        sorting.addWidget(self.label("sort_by"))
        self.sort_order = QComboBox()
        self.sort_order.setObjectName("findingSort")
        for key in ("completion_oldest", "completion_newest", "severity_desc", "severity_asc", "tool_az", "title_az"):
            self.sort_order.addItem(self.tr_text(key), key)
        self.sort_order.currentIndexChanged.connect(self.sort_findings)
        sorting.addWidget(self.sort_order)
        sorting.addStretch()
        findings_layout.addLayout(sorting)
        findings_layout.addWidget(result_split, 1)
        self.result_tabs.addTab(findings_page, "")
        error_page = QWidget()
        error_layout = QVBoxLayout(error_page)
        self.error_list = QTreeWidget()
        self.error_list.setObjectName("errorList")
        self.error_list.setRootIsDecorated(False)
        self.error_list.setColumnCount(2)
        self.error_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.error_list.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.error_list.currentItemChanged.connect(self.select_error)
        self.error_details = QPlainTextEdit()
        self.error_details.setReadOnly(True)
        self.error_details.setObjectName("errorDetails")
        error_split = QSplitter(Qt.Orientation.Vertical)
        error_split.addWidget(self.error_list)
        error_split.addWidget(self.error_details)
        error_split.setSizes([150, 300])
        error_layout.addWidget(error_split)
        self.result_tabs.addTab(error_page, "")
        checks_page = QWidget()
        checks_layout = QVBoxLayout(checks_page)
        self.check_list = QTreeWidget()
        self.check_list.setObjectName("checkList")
        self.check_list.setRootIsDecorated(False)
        self.check_list.setColumnCount(3)
        self.check_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.check_list.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        checks_layout.addWidget(self.check_list)
        self.coverage_details = QPlainTextEdit()
        self.coverage_details.setReadOnly(True)
        checks_layout.addWidget(self.coverage_details)
        self.result_tabs.addTab(checks_page, "")
        spider_page = QWidget()
        spider_layout = QVBoxLayout(spider_page)
        self.spider_summary = text_label()
        spider_layout.addWidget(self.spider_summary)
        self.spider_search = QLineEdit()
        self.spider_search.textChanged.connect(self.filter_spider)
        spider_layout.addWidget(self.spider_search)
        self.spider_urls = QTreeWidget()
        self.spider_urls.setObjectName("spiderUrls")
        self.spider_urls.setRootIsDecorated(False)
        self.spider_urls.setColumnCount(4)
        self.spider_urls.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.spider_urls.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        spider_layout.addWidget(self.spider_urls, 1)
        self.result_tabs.addTab(spider_page, "ZAP Spider")
        self.review_errors = self.button("review_errors", lambda: self.result_tabs.setCurrentIndex(1))
        self.review_errors.setObjectName("stop")
        self.review_errors.hide()
        results_layout.addWidget(self.review_errors)
        results_layout.addWidget(self.result_tabs, 1)
        self.scan_split.addWidget(lower)
        self.scan_split.setSizes([500, 360])
        layout.addWidget(self.scan_split)
        return page

    def _tools_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.addWidget(self.label("tools_intro", "muted"), 1)
        row.addWidget(self.button("check_updates", lambda: self.check_updates(force=True)))
        row.addWidget(self.button("refresh", self.refresh_prerequisites))
        layout.addLayout(row)
        holder = QWidget()
        self.tools_layout = QGridLayout(holder)
        self.tools_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroller(holder), 1)
        return page

    def _history_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label("history_intro", "muted"))
        self.history = QTableWidget(0, 4)
        self.history.setObjectName("history")
        self.history.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.history.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.history.verticalHeader().hide()
        self.history.cellDoubleClicked.connect(lambda row, column: self.open_history(row))
        layout.addWidget(self.history, 1)
        open_button = self.button("open_assessment", lambda: self.open_history(self.history.currentRow()))
        layout.addWidget(open_button)
        return page

    def switch_page(self, index):
        self.pages.setCurrentIndex(index)
        self.heading.setText(self.tr_text(("assessment", "tools", "history")[index]))
        for i, button in enumerate(self.nav):
            button.setProperty("navActive", i == index)
            button.style().unpolish(button)
            button.style().polish(button)
        if index == 2:
            self.refresh_history(force=True)

    def change_profile(self, name):
        if self.running():
            return
        self.profile = name
        self.scope_note.setText(self.tr_text("scope_note" if name == "low" else "scope_note_extended"))
        self.active_consent.setChecked(False)
        self.active_consent.setVisible(name in ("high", "ultra"))
        self.profile_note.setText(self.tr_text("profile_" + name + "_note"))
        if name == "ultra":
            self.extra_toggle.setChecked(True)
        self.refresh_tools(force=True)
        self.render_scan()

    def create_profile_dialog(self):
        dialog = QMessageBox(self)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setPalette(self.palette())
        dialog.setStyleSheet(theme_style(self.theme))
        dialog.setWindowTitle(self.tr_text("profile_details"))
        dialog.setText(self.profile.title() + "\n\n" + self.tr_text("profile_" + self.profile + "_note") + "\n\n" + self.tr_text("profile_limits"))
        dialog.setDetailedText("\n\n".join(tool + ": " + scope(tool, self.profile) for tool in ["moth"] + [t["id"] for t in tools.REGISTRY]))
        return dialog

    def show_profile_details(self):
        dialog = self.create_profile_dialog()
        dialog.exec()
        dialog.deleteLater()

    def apply_theme(self):
        self.setStyleSheet(theme_style(self.theme))
        palette = QPalette()
        dark = self.theme == "dark"
        for role, light, night in (
            (QPalette.ColorRole.Window, "#f5f5ef", "#141b18"),
            (QPalette.ColorRole.WindowText, "#203c32", "#e2eae5"),
            (QPalette.ColorRole.Base, "#ffffff", "#202d26"),
            (QPalette.ColorRole.AlternateBase, "#edf2e6", "#28382e"),
            (QPalette.ColorRole.Text, "#203c32", "#e2eae5"),
            (QPalette.ColorRole.Button, "#f7f8f2", "#28382e"),
            (QPalette.ColorRole.ButtonText, "#203c32", "#e2eae5"),
            (QPalette.ColorRole.Highlight, "#dcebbf", "#415f3e"),
            (QPalette.ColorRole.HighlightedText, "#203c32", "#e2eae5"),
            (QPalette.ColorRole.ToolTipBase, "#ffffff", "#28382e"),
            (QPalette.ColorRole.ToolTipText, "#203c32", "#e2eae5"),
        ):
            palette.setColor(role, QColor(night if dark else light))
        self.setPalette(palette)
        QApplication.instance().setPalette(palette)

    def change_theme(self, index):
        self.theme = self.theme_box.itemData(index)
        self.settings.setValue("theme", self.theme)
        self.apply_theme()

    def change_language(self, index):
        self.language = self.language_box.itemData(index)
        self.settings.setValue("language", self.language)
        self.translate()

    def translate(self):
        self.profile_note.setText(self.tr_text("profile_" + self.profile + "_note"))
        self.theme_box.setItemText(0, self.tr_text("theme_light"))
        self.theme_box.setItemText(1, self.tr_text("theme_dark"))
        for widget, key, setter in self._translated:
            getattr(widget, setter)(self.tr_text(key))
        self.scope_note.setText(self.tr_text("scope_note" if self.profile == "low" else "scope_note_extended"))
        self.heading.setText(self.tr_text(("assessment", "tools", "history")[self.pages.currentIndex()]))
        self.finding_search.setPlaceholderText(self.tr_text("search_findings"))
        for widget in (self.severity_filter, self.kind_filter, self.sort_order):
            for index in range(widget.count()):
                widget.setItemText(index, self.tr_text(widget.itemData(index)))
        self.tool_filter.setItemText(0, self.tr_text("all_tools"))
        self.severity_filter.setToolTip(self.tr_text("severity"))
        self.tool_filter.setToolTip(self.tr_text("tools"))
        self.kind_filter.setToolTip(self.tr_text("result_type"))
        self.sort_order.setToolTip(self.tr_text("completion_order_note"))
        self.spider_urls.setHeaderLabels([self.tr_text("website"), "HTTP", self.tr_text("content_type"), self.tr_text("visited")])
        self.spider_search.setPlaceholderText(self.tr_text("search_spider"))
        self.error_list.setHeaderLabels([self.tr_text("tools"), self.tr_text("error_reason")])
        self.check_list.setHeaderLabels([self.tr_text("tools"), self.tr_text("status"), self.tr_text("check_scope")])
        self.update_result_tabs()
        self.findings.setHeaderLabels([self.tr_text("severity"), self.tr_text("results"), self.tr_text("tools")])
        self.history.setHorizontalHeaderLabels([self.tr_text("website"), self.tr_text("created"), self.tr_text("status"), self.tr_text("results")])
        self._last_scan = None
        self.refresh_tools(force=True)
        self.refresh_history(force=True)
        self.render_scan()
        self.render_tip()

    def show_notice(self, message):
        self.notice.setText(message)
        self.notice.setVisible(bool(message))

    def running(self):
        return self.current and self.current["status"] not in FINISHED

    def start_scan(self):
        try:
            selected = [tool for tool, check in self.tool_checks.items() if check.isChecked()]
            identifier = engine.start(self.target.text(), selected, self.authorized.isChecked(), self.lab.isChecked(), profile=self.profile, active_authorized=self.active_consent.isChecked())
            self.current = storage.get(identifier)
            self._last_scan = None
            self.show_notice("")
            self.render_scan()
        except Exception as exc:
            self.show_notice(str(exc))

    def stop_scan(self):
        if self.current:
            engine.stop(self.current["id"])
            self.stop_button.setText(self.tr_text("stopping"))

    def poll(self):
        try:
            if self.current and self.running():
                self.current = storage.get(self.current["id"]) or self.current
                self.render_scan()
            self.refresh_tools()
            if self.pages.currentIndex() == 2:
                self.refresh_history()
            if self._pending_close and not engine.ACTIVE:
                self.close()
        except Exception as exc:
            self.show_notice(str(exc))

    def next_tip(self):
        self.current_tip = self.tip_deck.next()
        self.render_tip()
        if hasattr(self, "tip_timer") and self.tip_timer.isActive():
            self.tip_timer.start()

    def render_tip(self):
        if self.current_tip is None:
            return
        self.tip_heading.setText(self.tr_text("while_scanning") + " · " + self.tr_text("tip_" + self.current_tip["category"]))
        self.tip_body.setText(self.current_tip["text"][self.language])
        self.tip_pause.setText(self.tr_text("resume_tips" if self.tip_pause.isChecked() else "pause_tips"))
        self.tip_source.setVisible(bool(self.current_tip["source"]))

    def pause_tips(self, paused):
        if paused:
            self.tip_timer.stop()
        elif self.running():
            self.tip_timer.start()
        self.render_tip()

    def open_tip_source(self):
        if self.current_tip and self.current_tip["source"]:
            QDesktopServices.openUrl(QUrl(self.current_tip["source"]))

    def sync_tips(self, running):
        self.tip_card.setVisible(running)
        if not running:
            if hasattr(self, "tip_timer"):
                self.tip_timer.stop()
            self._tips_scan_id = None
            return
        if self._tips_scan_id != self.current["id"]:
            self._tips_scan_id = self.current["id"]
            self.tip_pause.setChecked(False)
            self.next_tip()
            self.tip_timer.start()

    def render_scan(self):
        running = bool(self.running())
        self.sync_tips(running)
        self.render_estimates()
        self.start_button.setEnabled(not running)
        self.target.setEnabled(not running)
        self.authorized.setEnabled(not running)
        self.lab.setEnabled(not running)
        self.active_consent.setEnabled(not running)
        for button in self.profile_buttons.values():
            button.setEnabled(not running)
        self.stop_button.setVisible(running)
        for row in self.tool_rows:
            self.tool_checks[row["id"]].setEnabled(row["status"] == "ready" and not running and self.profile != "ultra")
        if self.current is None:
            self.progress_title.setText(self.tr_text("idle_title"))
            self.stage.setText(self.tr_text("idle_description"))
            self.result_title.setText(self.tr_text("select_finding"))
            return
        scan = self.current
        signature = json.dumps(scan, ensure_ascii=False) + self.language
        if signature == self._last_scan:
            return
        self._last_scan = signature
        status_key = "running_title" if running else "finished_title" if scan["status"] == "completed" else "cancelled_title" if scan["status"] in ("cancelled", "interrupted") else "failed_title"
        self.progress_title.setText(self.tr_text(status_key))
        self.progress.setValue(scan["progress"])
        self.stage.setText(scan["target"] + "\n" + self.tr_text(scan["status"]) + " · " + scan["stage"])
        self.step_text.setPlainText("\n".join(step["tool"] + " — " + self.tr_text(step["status"]) for step in scan["steps"]))
        completed = sum(step["status"] == "completed" for step in scan["steps"])
        self.summary.setText(self.tr_text("assessment_summary").format(findings=len(scan["findings"]), errors=len(scan["errors"]), completed=completed, skipped=sum(step["status"] == "skipped" for step in scan["steps"]), total=len(scan.get("tools", []))+1))
        self.render_diagnostics()
        self.review_errors.setVisible(bool(scan["errors"]))
        new_scan = self._rendered_scan_id != scan["id"]
        self._rendered_scan_id = scan["id"]
        if new_scan:
            self.result_tabs.setCurrentIndex(1 if scan["errors"] and not scan["findings"] else 0)
        selected = self.findings.currentItem()
        selected_id = selected.data(0, Qt.ItemDataRole.UserRole) if selected else None
        self.findings.clear()
        selected_item = None
        for finding in scan["findings"]:
            title = describe(finding, self.language)[0]
            item = FindingTreeItem([self.tr_text(finding["severity"]), title, finding["tool"]])
            item.setData(0, Qt.ItemDataRole.UserRole, finding["id"])
            for column in range(3):
                item.setToolTip(column, title + "\n" + finding["tool"])

            self.findings.addTopLevelItem(item)
            if finding["id"] == selected_id:
                selected_item = item
        if self.findings.topLevelItemCount():
            self.findings.setCurrentItem(selected_item or self.findings.topLevelItem(0))
        else:
            self.result_title.setText(self.tr_text("results"))
            self.explanation.setPlainText(self.tr_text("running_description") if running else self.tr_text("no_completed_results") if scan["errors"] else self.tr_text("no_findings"))
            self.technical.clear()
        self.sort_findings()
        self.filter_findings()

    def render_estimates(self):
        scan = self.current
        if scan is None:
            self.total_time.setText(self.tr_text("estimate_idle"))
            self.current_time.clear()
            return
        data = estimates.remaining(scan)
        if not self.running():
            value = estimates.recorded_time(scan)
            self.total_time.setText(self.tr_text("total_elapsed").format(elapsed=estimates.duration(value) if value is not None else self.tr_text("estimate_unknown")))
            self.current_time.clear()
            return
        remaining = self.tr_text("estimate_unknown") if data["unknown"] else estimates.duration(data["low"]) + " – " + estimates.duration(data["high"])
        self.total_time.setText(self.tr_text("total_estimate").format(elapsed=estimates.duration(data["elapsed"]), remaining=remaining))
        current = data["current"]
        if current:
            remaining = self.tr_text("estimate_overdue") if current["unknown"] else estimates.duration(current["low"]) + " – " + estimates.duration(current["high"])
            phase = next((s.get("details", {}).get("phase", "") for s in scan.get("steps", []) if s["tool"] == current["tool"]), "")
            tool = current["tool"] + (" / " + phase if phase else "")
            self.current_time.setText(self.tr_text("tool_estimate").format(tool=tool, elapsed=estimates.duration(current["elapsed"]), remaining=remaining))
        else:
            self.current_time.setText(self.tr_text("estimate_unknown"))

    def render_spider(self):
        data = self.current.get("spider") if self.current else None
        self.spider_urls.clear()
        if data is None:
            self.spider_summary.setText(self.tr_text("spider_unrecorded"))
            return
        html = data.get("html_pages")
        pages = self.tr_text("estimate_unknown") if html is None else str(html)
        if html is not None and not data.get("html_count_complete"):
            pages = self.tr_text("at_least").format(count=html)
        self.spider_summary.setText(self.tr_text("spider_summary").format(status=self.tr_text(data.get("status", "unavailable")), pages=pages, visited=data.get("visited_urls", 0) if data.get("counts_known", bool(data.get("urls"))) else self.tr_text("estimate_unknown"), discovered=data.get("discovered_urls", 0) if data.get("counts_known", bool(data.get("urls"))) else self.tr_text("estimate_unknown")) + "\n" + self.tr_text("spider_counts_note"))
        for row in data.get("urls", []):
            item = QTreeWidgetItem([row["url"], str(row.get("status_code", "")), row.get("content_type", ""), self.tr_text("yes" if row.get("processed") else "no")])
            item.setToolTip(0, row["url"])
            self.spider_urls.addTopLevelItem(item)
        self.filter_spider()

    def filter_spider(self, *args):
        query = self.spider_search.text().strip().casefold()
        for index in range(self.spider_urls.topLevelItemCount()):
            item = self.spider_urls.topLevelItem(index)
            item.setHidden(query not in " ".join(item.text(i) for i in range(4)).casefold())

    def select_finding(self, item, previous=None):
        if not item or not self.current:
            return
        identifier = item.data(0, Qt.ItemDataRole.UserRole)
        finding = next((f for f in self.current["findings"] if f["id"] == identifier), None)
        if finding is None:
            return
        title, explanation, recommendation = describe(finding, self.language)
        self.result_title.setText(title)
        body = self.tr_text("finding_metadata").format(severity=self.tr_text(finding["severity"]), tool=finding["tool"], target=finding["target"])
        body += "\n\n" + self.tr_text("what_it_means") + "\n" + explanation
        body += "\n\n" + self.tr_text("observed_evidence") + "\n" + (evidence_text(finding.get("evidence", "")) or self.tr_text("no_evidence"))
        body += "\n\n" + self.tr_text("recommendation") + "\n" + recommendation
        if finding.get("source_language") == "en" and self.language != "en" and finding.get("code") not in OBSERVATIONS:
            original = finding["text"]["en"]
            body += "\n\n" + self.tr_text("english_source") + "\n" + "\n\n".join(original)
        self.explanation.setPlainText(body)
        self.technical.setPlainText("\n\n".join([finding["target"], finding["tool"] + " · " + self.tr_text(finding["confidence"]), finding["evidence"], finding.get("technical", "")]))

    def sort_findings(self, *args):
        if self.current is None:
            return
        keys = finding_sort_keys(self.current, self.sort_order.currentData(), self.language)
        selected = self.findings.currentItem()
        for index in range(self.findings.topLevelItemCount()):
            item = self.findings.topLevelItem(index)
            item.sort_key = keys[item.data(0, Qt.ItemDataRole.UserRole)]
        self.findings.sortItems(0, Qt.SortOrder.AscendingOrder)
        if selected:
            self.findings.setCurrentItem(selected)

    def reset_finding_filters(self):
        for widget in (self.finding_search, self.severity_filter, self.tool_filter, self.kind_filter, self.sort_order):
            widget.blockSignals(True)
        self.finding_search.clear()
        for widget in (self.severity_filter, self.tool_filter, self.kind_filter, self.sort_order):
            widget.setCurrentIndex(0)
        for widget in (self.finding_search, self.severity_filter, self.tool_filter, self.kind_filter, self.sort_order):
            widget.blockSignals(False)
        self.sort_findings()
        self.filter_findings()

    def filter_findings(self, *args):
        query = self.finding_search.text().strip().casefold()
        severity = self.severity_filter.currentData()
        tool = self.tool_filter.currentData()
        kind = self.kind_filter.currentData()
        visible_count = 0
        records = {f["id"]: f for f in self.current["findings"]} if self.current else {}
        for index in range(self.findings.topLevelItemCount()):
            item = self.findings.topLevelItem(index)
            record = records.get(item.data(0, Qt.ItemDataRole.UserRole), {})
            text = " ".join(item.text(column) for column in range(3)) + " " + record.get("evidence", "")
            hidden = ((bool(query) and query not in text.casefold())
                      or (severity != "all_severities" and record.get("severity") != severity)
                      or (tool != "all_tools" and record.get("tool") != tool)
                      or (kind != "all_types" and record.get("kind") != kind))
            item.setHidden(hidden)
            visible_count += not hidden
        self.visible_findings.setText(self.tr_text("visible_results").format(visible=visible_count, total=len(records)))
        selected = self.findings.currentItem()
        if selected and selected.isHidden():
            visible = next((self.findings.topLevelItem(i) for i in range(self.findings.topLevelItemCount()) if not self.findings.topLevelItem(i).isHidden()), None)
            self.findings.setCurrentItem(visible)
            if visible is None:
                self.result_title.setText(self.tr_text("no_filter_matches"))
                self.explanation.clear()
                self.technical.clear()
        elif selected is None:
            visible = next((self.findings.topLevelItem(i) for i in range(self.findings.topLevelItemCount()) if not self.findings.topLevelItem(i).isHidden()), None)
            if visible:
                self.findings.setCurrentItem(visible)

    def update_result_tabs(self):
        scan = self.current or {}
        self.result_tabs.setTabText(0, self.tr_text("results") + f" ({len(scan.get('findings', []))})")
        self.result_tabs.setTabText(1, self.tr_text("errors_tab") + f" ({len(scan.get('errors', []))})")
        self.result_tabs.setTabText(2, self.tr_text("checks_tab") + f" ({len(scan.get('tools', []))+1 if scan else 0})")

    def render_diagnostics(self):
        self.update_result_tabs()
        self.render_spider()
        selected = self.error_list.currentItem()
        previous = selected.data(0, Qt.ItemDataRole.UserRole) if selected else 0
        self.error_list.clear()
        for index, error in enumerate(self.current["errors"]):
            title = error_help(error["message"], self.language)[0]
            item = QTreeWidgetItem([error["tool"], title])
            item.setToolTip(1, title)
            item.setData(0, Qt.ItemDataRole.UserRole, index)
            self.error_list.addTopLevelItem(item)
        if self.error_list.topLevelItemCount():
            self.error_list.setCurrentItem(self.error_list.topLevelItem(min(previous or 0, self.error_list.topLevelItemCount()-1)))
        else:
            self.error_details.setPlainText(self.tr_text("no_errors"))
        self.check_list.clear()
        steps = {step["tool"]: step["status"] for step in self.current["steps"]}
        reasons = {step["tool"]: step.get("reason", "") for step in self.current["steps"]}
        for tool in ["moth"] + self.current.get("tools", []):
            check_scope = self.current.get("tool_scope", {}).get(tool) or self.tr_text("basic_scope" if tool == "moth" else "tool_" + tool)
            if reasons.get(tool):
                check_scope = reasons[tool]
            status = steps.get(tool, "not_run")
            self.check_list.addTopLevelItem(QTreeWidgetItem([tool, self.tr_text(status), check_scope]))
        coverage = evidence_text(json.dumps(self.current.get("coverage", {}), ensure_ascii=False))
        self.coverage_details.setPlainText(self.tr_text("scan_level") + ": " + self.current.get("profile", "low").title() + "\n" + self.tr_text("profile_limits") + "\n\n" + self.tr_text("coverage_details") + "\n\n" + (coverage or self.tr_text("no_coverage")) + "\n\n" + self.tr_text("coverage_note"))

    def select_error(self, item, previous=None):
        if item is None or self.current is None:
            return
        index = item.data(0, Qt.ItemDataRole.UserRole)
        error = self.current["errors"][index]
        title, explanation, action = error_help(error["message"], self.language)
        self.error_details.setPlainText(error["tool"] + " · " + title + "\n\n" + self.tr_text("what_it_means") + "\n" + explanation + "\n\n" + self.tr_text("recommendation") + "\n" + action + "\n\n" + self.tr_text("original_error") + "\n" + error["message"])

    def refresh_tools(self, force=False):
        rows = tools.catalog()
        signature = json.dumps(rows, ensure_ascii=False) + self.language + str(bool(self.running()))
        if not force and signature == self._last_tools:
            return
        self._last_tools = signature
        self.tool_rows = rows
        clear_layout(self.tools_layout)
        for index, row in enumerate(rows):
            card = QGroupBox(row["name"])
            card.setMinimumWidth(280)
            content = QVBoxLayout(card)
            available = row.get("update_status") == "available" and row["status"] == "ready"
            badge = text_label(self.tr_text("update_available" if available else row["status"]), "toolStatus")
            badge.setProperty("state", "available" if available else row["status"])
            badge.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            content.addWidget(badge, 0, Qt.AlignmentFlag.AlignLeft)
            content.addWidget(text_label(self.tr_text("tool_" + row["id"])))
            if row.get("source"):
                content.addWidget(text_label(self.tr_text("source_" + row["source"]), "muted"))
            if row.get("location"):
                location = text_label(row["location"], "muted")
                location.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                content.addWidget(location)
            message = (self.tr_text("queue_position").format(position=row["queue_position"])
                       if row["status"] == "queued" else row["message"])
            if row["status"] == "prerequisite" and row["id"] == "zap":
                message = self.tr_text("zap_requirement")
            if row["id"] == "nmap" and row["status"] != "ready":
                message = self.tr_text("nmap_requirement")
            if message:
                content.addWidget(text_label(message[-900:], "muted"))
            if row.get("version"):
                content.addWidget(text_label(row["version"][:70], "muted"))
            update_status = row.get("update_status")
            if row["status"] == "ready" and update_status:
                if update_status == "available":
                    current = row.get("installed_version", "")
                    latest = row.get("latest_version", "")
                    if row.get("source") == "docker":
                        current, latest = current.split("@")[-1][:19], latest.split("@")[-1][:19]
                    content.addWidget(text_label(self.tr_text("update_versions").format(current=current, latest=latest)))
                    if row.get("source") == "system":
                        content.addWidget(text_label(self.tr_text("system_update_note"), "muted"))
                elif update_status == "current":
                    content.addWidget(text_label(self.tr_text("up_to_date") + " · " + row.get("installed_version", "")[:70], "muted"))
                else:
                    label = text_label(self.tr_text("updates_checking" if update_status == "checking" else "updates_error"), "muted")
                    label.setToolTip(row.get("update_error", ""))
                    content.addWidget(label)
            buttons = QHBoxLayout()
            if available:
                managed = row.get("source") in ("moth", "docker")
                update_button = QPushButton(self.tr_text("update" if managed else "update_instructions"))
                update_button.setObjectName("update_" + row["id"])
                update_button.setEnabled(not self.running())
                update_button.clicked.connect(lambda checked=False, tool=row["id"], managed=managed: self.update_tool(tool, managed))
                buttons.addWidget(update_button)
            elif row["id"] != "nmap":
                key = "ready" if row["status"] == "ready" else "installing" if row["status"] == "installing" else "queued" if row["status"] == "queued" else "retry" if row["status"] == "error" else "install"
                install = QPushButton(self.tr_text(key))
                install.setObjectName("install_" + row["id"])
                install.setEnabled(row["status"] not in ("ready", "installing", "queued", "prerequisite") and not self.running())
                install.clicked.connect(lambda checked=False, tool=row["id"]: self.install_tool(tool))
                buttons.addWidget(install)
            official = QPushButton(self.tr_text("upstream"))
            official.clicked.connect(lambda checked=False, url=row["url"]: QDesktopServices.openUrl(QUrl(url)))
            buttons.addWidget(official)
            buttons.addStretch()
            content.addLayout(buttons)
            self.tools_layout.addWidget(card, index // 2, index % 2)
            check = self.tool_checks[row["id"]]
            if self.profile == "ultra":
                check.setChecked(True)
            check.setEnabled(row["status"] == "ready" and not self.running() and self.profile != "ultra")
            check.setToolTip(self.tr_text("tool_" + row["id"]))
        self.tools_layout.setRowStretch((len(rows) + 1) // 2, 1)

    def install_tool(self, identifier):
        try:
            tools.start_install(identifier)
            self.show_notice("")
            self.refresh_tools(force=True)
        except Exception as exc:
            self.show_notice(str(exc))

    def check_updates(self, force=False):
        updates.request_check(tools.catalog(), force=force)
        self.refresh_tools(force=True)

    def update_tool(self, identifier, managed=True):
        if not managed:
            QMessageBox.information(self, self.tr_text("update_instructions"), self.tr_text("system_update_note"))
            return
        if self.running():
            return
        try:
            tools.start_install(identifier, update=True)
            self.show_notice("")
            self.refresh_tools(force=True)
        except Exception as exc:
            self.show_notice(str(exc))

    def refresh_prerequisites(self):
        tools._is_pd_httpx.cache_clear()
        if hasattr(tools.catalog, "python_available"):
            del tools.catalog.python_available
        self.refresh_tools(force=True)

    def refresh_history(self, force=False):
        rows = storage.recent()
        signature = [(s["id"], s["status"], len(s.get("findings", []))) for s in rows]
        signature = str(signature) + self.language
        if not force and self._last_history == signature:
            return
        self._last_history = signature
        self.history.setRowCount(len(rows))
        for index, scan in enumerate(rows):
            values = [scan["target"], scan["created"][:19].replace("T", " "), self.tr_text(scan["status"]), str(len(scan.get("findings", [])))]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, scan["id"])
                self.history.setItem(index, column, item)
        self.history.resizeColumnsToContents()
        self.history.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

    def open_history(self, row):
        if row < 0:
            return
        if self.running():
            self.show_notice(self.tr_text("scan_in_progress"))
            return
        item = self.history.item(row, 0)
        if item:
            self.current = storage.get(item.data(Qt.ItemDataRole.UserRole))
            self._last_scan = None
            self.render_scan()
            self.switch_page(0)

    def export_report(self, extension):
        if self.current is None:
            self.show_notice(self.tr_text("no_assessment"))
            return
        filename, _ = QFileDialog.getSaveFileName(self, self.tr_text("save_report"), str(Path.home() / f"moth-{self.current['id']}.{extension}"), f"{extension.upper()} (*.{extension})")
        if filename:
            try:
                path = Path(filename)
                if not path.suffix:
                    path = path.with_suffix("." + extension)
                content = render(self.current, self.language) if extension == "html" else json.dumps(self.current, ensure_ascii=False, indent=2)
                path.write_text(content, encoding="utf-8")
                self.statusBar().showMessage(self.tr_text("report_saved") + ": " + str(path), 10000)
                self.show_notice("")
            except OSError as exc:
                self.show_notice(str(exc))

    def closeEvent(self, event):
        with engine.LOCK:
            active = list(engine.ACTIVE.values())
        if active:
            if not self._pending_close:
                choice = QMessageBox.question(self, "Moth", self.tr_text("stop_close"))
                if choice != QMessageBox.StandardButton.Yes:
                    event.ignore()
                    return
                self._pending_close = True
                for cancel in active:
                    cancel.set()
                self.show_notice(self.tr_text("stopping"))
                self.start_button.setEnabled(False)
            event.ignore()
            return
        with tools.LOCK:
            installing = any(row.get("status") in ("installing", "queued") for row in tools.STATE.values())
        if installing and not self._closing_install:
            if QMessageBox.question(self, "Moth", self.tr_text("install_close")) != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._closing_install = True
        self.timer.stop()
        self.tip_timer.stop()
        self.update_timer.stop()
        self.settings.sync()
        event.accept()


def run():
    app = QApplication(sys.argv)
    app.setApplicationName("Moth")
    app.setOrganizationName("MothKernel")
    app.setDesktopFileName("moth")
    app.setStyle("Fusion")
    lock = QLockFile(str(DATA / "desktop.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        QMessageBox.information(None, "Moth", "Moth is already running. Open its window from the taskbar.")
        return 0
    storage.recover()
    window = MainWindow()
    window.show()
    if "--smoke-test" in sys.argv:
        QTimer.singleShot(1000, app.quit)
    result = app.exec()
    lock.unlock()
    return result
