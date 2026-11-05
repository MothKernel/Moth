"""Native Qt Widgets UI. Calls the Python engine directly; no web server or WebView."""
import json
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QSettings, QLockFile, QUrl
from PySide6.QtGui import QIcon, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QLineEdit, QCheckBox,
    QComboBox, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QStackedWidget,
    QGroupBox, QScrollArea, QSplitter, QTreeWidget, QTreeWidgetItem, QPlainTextEdit,
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QMessageBox, QAbstractItemView,
)
from . import __version__, engine, storage, tools
from .config import ROOT, DATA
from .reports import render
from .shortcuts import create_shortcuts

RESOURCES = ROOT / "resources"
TRANSLATIONS = json.loads((RESOURCES / "translations.json").read_text(encoding="utf-8"))
FINISHED = {"completed", "partial", "failed", "cancelled", "interrupted"}

STYLE = """
QWidget { font-family: 'Segoe UI', 'DejaVu Sans'; font-size: 13px; color: #203c32; }
QMainWindow, QWidget#content { background: #f5f5ef; }
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
QPushButton#shortcut { font-size: 11px; padding: 8px; }
QLineEdit, QComboBox { background: white; border: 1px solid #ccd7c1; border-radius: 5px; padding: 9px; }
QLineEdit:focus { border: 2px solid #8aa666; }
QCheckBox { spacing: 9px; padding: 4px 0; font-weight: 400; }
QProgressBar { border: 1px solid #dce3d4; background: white; border-radius: 4px; text-align: center; min-height: 20px; }
QProgressBar::chunk { background: #bfdaa0; border-radius: 3px; }
QTreeWidget, QTableWidget, QPlainTextEdit { background: white; border: 1px solid #dce3d4; border-radius: 5px; selection-background-color: #dcebbf; selection-color: #203c32; }
QHeaderView::section { background: #edf2e6; border: 0; border-bottom: 1px solid #dce3d4; padding: 9px; }
QTreeWidget::item, QTableWidget::item { padding: 7px; }
QScrollArea { border: 0; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QSplitter::handle { background: #e2e8d9; border-radius: 2px; }
QStatusBar { background: #eaf0e3; color: #718267; }
"""


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
        self.current = None
        self._last_scan = None
        self._last_tools = None
        self._last_history = None
        self._pending_close = False
        self._closing_install = False
        self._translated = []
        self.tool_checks = {}
        self.tool_rows = []
        self.setWindowTitle(f"Moth {__version__}")
        self.setWindowIcon(QIcon(str(RESOURCES / "moth.png")))
        self.setMinimumSize(1000, 720)
        self.resize(1280, 900)
        self.setStyleSheet(STYLE)
        self._build()
        self.translate()
        self.refresh_tools(force=True)
        self.refresh_history(force=True)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(500)

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
        side_layout.addWidget(self.label("desktop_local", "muted"))
        side_layout.addWidget(self.button("create_shortcut", self.create_shortcut, "shortcut"))
        side_layout.addSpacing(10)
        side_layout.addWidget(text_label(f"MOTH / {__version__}", "muted"))
        row.addWidget(side)
        content = QWidget()
        content.setObjectName("content")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 20, 28, 15)
        header = QHBoxLayout()
        self.heading = text_label(name="heading")
        header.addWidget(self.heading, 1)
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
        form_layout.addWidget(self.label("scope_note", "muted"))
        self.authorized = self.bind(QCheckBox(), "authorized")
        self.authorized.setObjectName("authorized")
        self.lab = self.bind(QCheckBox(), "lab")
        self.lab.setObjectName("lab")
        form_layout.addWidget(self.authorized)
        form_layout.addWidget(self.lab)
        self.extra_toggle = self.bind(QCheckBox(), "extra_tools")
        self.extra_toggle.setObjectName("extraTools")
        form_layout.addWidget(self.extra_toggle)
        options = QWidget()
        self.options_layout = QGridLayout(options)
        self.options_layout.setContentsMargins(0, 0, 0, 0)
        for index, tool in enumerate(tools.REGISTRY):
            check = QCheckBox(tool["name"])
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
        self.step_text = QPlainTextEdit()
        self.step_text.setReadOnly(True)
        self.step_text.setMaximumHeight(95)
        overview_layout.addWidget(self.step_text)
        self.stop_button = self.button("stop", self.stop_scan, "stop")
        self.stop_button.hide()
        overview_layout.addWidget(self.stop_button)
        overview_layout.addWidget(self.label("coverage_note", "muted"))
        overview_layout.addStretch()
        top.addWidget(overview, 2)
        self.scan_split.addWidget(upper)
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
        self.technical_toggle = self.bind(QCheckBox(), "technical")
        detail_layout.addWidget(self.technical_toggle)
        self.technical = QPlainTextEdit()
        self.technical.setObjectName("technical")
        self.technical.setReadOnly(True)
        self.technical.hide()
        self.technical_toggle.toggled.connect(self.technical.setVisible)
        detail_layout.addWidget(self.technical, 1)
        result_split.addWidget(details)
        result_split.setSizes([500, 500])
        results_layout.addWidget(result_split, 1)
        self.errors = QPlainTextEdit()
        self.errors.setReadOnly(True)
        self.errors.setMaximumHeight(80)
        self.errors.hide()
        results_layout.addWidget(self.errors)
        self.scan_split.addWidget(lower)
        self.scan_split.setSizes([390, 390])
        layout.addWidget(self.scan_split)
        return page

    def _tools_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.addWidget(self.label("tools_intro", "muted"), 1)
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

    def change_language(self, index):
        self.language = self.language_box.itemData(index)
        self.settings.setValue("language", self.language)
        self.translate()

    def translate(self):
        for widget, key, setter in self._translated:
            getattr(widget, setter)(self.tr_text(key))
        self.heading.setText(self.tr_text(("assessment", "tools", "history")[self.pages.currentIndex()]))
        self.findings.setHeaderLabels([self.tr_text("severity"), self.tr_text("results"), self.tr_text("tools")])
        self.history.setHorizontalHeaderLabels([self.tr_text("website"), self.tr_text("created"), self.tr_text("status"), self.tr_text("results")])
        self._last_scan = None
        self.refresh_tools(force=True)
        self.refresh_history(force=True)
        self.render_scan()
        self.statusBar().showMessage(self.tr_text("desktop_local") + f" · Moth {__version__}")

    def show_notice(self, message):
        self.notice.setText(message)
        self.notice.setVisible(bool(message))

    def create_shortcut(self):
        try:
            path = create_shortcuts()
            self.statusBar().showMessage(self.tr_text("shortcut_created") + ": " + path, 15000)
        except Exception as exc:
            self.show_notice(str(exc))

    def running(self):
        return self.current and self.current["status"] not in FINISHED

    def start_scan(self):
        try:
            selected = [tool for tool, check in self.tool_checks.items() if check.isChecked()]
            identifier = engine.start(self.target.text(), selected, self.authorized.isChecked(), self.lab.isChecked())
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

    def render_scan(self):
        running = bool(self.running())
        self.start_button.setEnabled(not running)
        self.target.setEnabled(not running)
        self.authorized.setEnabled(not running)
        self.lab.setEnabled(not running)
        self.stop_button.setVisible(running)
        for row in self.tool_rows:
            self.tool_checks[row["id"]].setEnabled(row["status"] == "ready" and not running)
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
        self.summary.setText(f"{len(scan['findings'])} {self.tr_text('observations')} · {self.tr_text(scan['status'])}")
        self.errors.setPlainText("\n".join(e["tool"] + ": " + e["message"] for e in scan["errors"]))
        self.errors.setVisible(bool(scan["errors"]))
        selected = self.findings.currentItem()
        selected_id = selected.data(0, Qt.ItemDataRole.UserRole) if selected else None
        self.findings.clear()
        selected_item = None
        for finding in scan["findings"]:
            title = finding["text"].get(self.language, finding["text"]["en"])[0]
            item = QTreeWidgetItem([self.tr_text(finding["severity"]), title, finding["tool"]])
            item.setData(0, Qt.ItemDataRole.UserRole, finding["id"])
            self.findings.addTopLevelItem(item)
            if finding["id"] == selected_id:
                selected_item = item
        if self.findings.topLevelItemCount():
            self.findings.setCurrentItem(selected_item or self.findings.topLevelItem(0))
        else:
            self.result_title.setText(self.tr_text("results"))
            self.explanation.setPlainText(self.tr_text("running_description") if running else self.tr_text("no_findings"))
            self.technical.clear()

    def select_finding(self, item, previous=None):
        if not item or not self.current:
            return
        identifier = item.data(0, Qt.ItemDataRole.UserRole)
        finding = next((f for f in self.current["findings"] if f["id"] == identifier), None)
        if finding is None:
            return
        title, explanation, recommendation = finding["text"].get(self.language, finding["text"]["en"])
        self.result_title.setText(title)
        body = explanation + "\n\n" + self.tr_text("recommendation") + "\n" + recommendation
        if finding.get("source_language") == "en" and self.language != "en":
            body += "\n\n" + self.tr_text("english_source")
        self.explanation.setPlainText(body)
        self.technical.setPlainText("\n\n".join([finding["target"], finding["tool"] + " · " + self.tr_text(finding["confidence"]), finding["evidence"], finding.get("technical", "")]))

    def refresh_tools(self, force=False):
        rows = tools.catalog()
        signature = json.dumps(rows, ensure_ascii=False) + self.language + str(bool(self.running()))
        if not force and signature == self._last_tools:
            return
        self._last_tools = signature
        self.tool_rows = rows
        clear_layout(self.tools_layout)
        for index, row in enumerate(rows):
            card = QGroupBox(row["name"] + " · " + self.tr_text(row["status"]))
            card.setMinimumWidth(280)
            content = QVBoxLayout(card)
            content.addWidget(text_label(self.tr_text("tool_" + row["id"])))
            if row.get("source"):
                content.addWidget(text_label(self.tr_text("source_" + row["source"]), "muted"))
            if row.get("location"):
                location = text_label(row["location"], "muted")
                location.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                content.addWidget(location)
            message = row["message"]
            if row["status"] == "prerequisite" and row["id"] == "zap":
                message = self.tr_text("zap_requirement")
            if row["id"] == "nmap" and row["status"] != "ready":
                message = self.tr_text("nmap_requirement")
            if message:
                content.addWidget(text_label(message[-900:], "muted"))
            if row.get("version"):
                content.addWidget(text_label(row["version"][:70], "muted"))
            buttons = QHBoxLayout()
            if row["id"] != "nmap":
                key = "ready" if row["status"] == "ready" else "installing" if row["status"] == "installing" else "retry" if row["status"] == "error" else "install"
                install = QPushButton(self.tr_text(key))
                install.setObjectName("install_" + row["id"])
                install.setEnabled(row["status"] not in ("ready", "installing", "prerequisite") and not self.running())
                install.clicked.connect(lambda checked=False, tool=row["id"]: self.install_tool(tool))
                buttons.addWidget(install)
            official = QPushButton(self.tr_text("upstream"))
            official.clicked.connect(lambda checked=False, url=row["url"]: QDesktopServices.openUrl(QUrl(url)))
            buttons.addWidget(official)
            buttons.addStretch()
            content.addLayout(buttons)
            self.tools_layout.addWidget(card, index // 2, index % 2)
            check = self.tool_checks[row["id"]]
            check.setEnabled(row["status"] == "ready" and not self.running())
            check.setToolTip(self.tr_text("tool_" + row["id"]))
        self.tools_layout.setRowStretch((len(rows) + 1) // 2, 1)

    def install_tool(self, identifier):
        try:
            tools.start_install(identifier)
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
            installing = any(row.get("status") == "installing" for row in tools.STATE.values())
        if installing and not self._closing_install:
            if QMessageBox.question(self, "Moth", self.tr_text("install_close")) != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._closing_install = True
        self.timer.stop()
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
