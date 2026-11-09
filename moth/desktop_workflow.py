"""Native scan configuration, diagnostics, comparison and retest controls."""
import queue
import threading
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit, QPlainTextEdit,
    QSpinBox, QComboBox, QDialogButtonBox, QWidget, QTreeWidget, QTreeWidgetItem, QProgressBar, QLabel, QHBoxLayout)
from . import preflight, engine, storage, results, estimates
from .scan_options import validate
from .session import Session
from .presentation import describe


class WorkflowUI:
    def build_workflow_controls(self, form_layout, overview_layout):
        self.scan_options = validate()
        self.pending_session = None
        self.background_results = queue.Queue()
        self.busy_diagnostics = False
        self.workflow_cancel = threading.Event()
        self.advanced_button = self.button('advanced_options', self.configure_scan)
        self.diagnostics_button = self.button('run_diagnostics', self.run_diagnostics)
        controls = QWidget()
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.addWidget(self.advanced_button)
        controls_layout.addWidget(self.diagnostics_button)
        form_layout.insertWidget(2, controls)
        self.scope_summary = self.label('advanced_hint', 'muted')
        form_layout.insertWidget(3, self.scope_summary)
        self.tool_progress = QProgressBar()
        self.tool_progress.setRange(0, 0)
        self.tool_progress.hide()
        self.tool_activity = self.label('progress_unavailable', 'muted')
        overview_layout.insertWidget(5, self.tool_progress)
        overview_layout.insertWidget(6, self.tool_activity)
        self.skip_button = self.button('skip_tool', self.skip_tool)
        self.skip_button.hide()
        overview_layout.insertWidget(9, self.skip_button)

    def build_workflow_tabs(self):
        self.recheck_button = self.button('recheck_finding', self.recheck_finding)
        self.recheck_button.setEnabled(False)
        self.result_tabs.widget(0).layout().addWidget(self.recheck_button)
        page = QWidget()
        layout = QVBoxLayout(page)
        self.priority_summary = QPlainTextEdit()
        self.priority_summary.setReadOnly(True)
        layout.addWidget(self.priority_summary)
        self.result_tabs.addTab(page, self.tr_text('priorities'))
        page = QWidget()
        layout = QVBoxLayout(page)
        self.baseline_box = QComboBox()
        self.baseline_box.currentIndexChanged.connect(self.render_comparison)
        layout.addWidget(self.baseline_box)
        self.comparison_note = self.label('comparison_hint', 'muted')
        layout.addWidget(self.comparison_note)
        self.comparison_tree = QTreeWidget()
        self.comparison_tree.setRootIsDecorated(False)
        self.comparison_tree.setColumnCount(4)
        self.comparison_tree.setHeaderLabels([self.tr_text('status'), self.tr_text('results'), self.tr_text('website'), self.tr_text('tools')])
        layout.addWidget(self.comparison_tree)
        self.result_tabs.addTab(page, self.tr_text('comparison'))
        page = QWidget()
        layout = QVBoxLayout(page)
        self.preflight_text = QPlainTextEdit()
        self.preflight_text.setReadOnly(True)
        layout.addWidget(self.preflight_text)
        layout.addWidget(self.button('prepare_templates', self.prepare_templates))
        self.result_tabs.addTab(page, self.tr_text('diagnostics'))

    def records(self):
        return results.grouped(self.current.get('findings', [])) if self.current else []

    def make_options_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr_text('advanced_options'))
        dialog.setMinimumWidth(580)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        exclusions = QPlainTextEdit('\n'.join(self.scan_options['exclude_paths']))
        exclusions.setMaximumHeight(95)
        form.addRow(self.tr_text('exclude_paths'), exclusions)
        ports = QLineEdit(self.scan_options['ports'])
        ports.setPlaceholderText('80,443,8000-8010')
        form.addRow(self.tr_text('custom_ports'), ports)
        rate, nmap_rate = QSpinBox(), QSpinBox()
        rate.setRange(1, 100); rate.setValue(self.scan_options['rate'])
        nmap_rate.setRange(1, 5000); nmap_rate.setValue(self.scan_options['nmap_rate'])
        form.addRow(self.tr_text('web_rate'), rate)
        form.addRow(self.tr_text('nmap_rate'), nmap_rate)
        auth = QComboBox()
        for key in ('none', 'cookie', 'bearer', 'basic'):
            auth.addItem(self.tr_text('auth_' + key), key)
        fields = {}
        form.addRow(self.tr_text('authentication'), auth)
        for key in ('account_label', 'session_value', 'username', 'password', 'verify_url', 'verify_marker'):
            field = QLineEdit()
            fields[key] = field
            if key in ('session_value', 'password'):
                field.setEchoMode(QLineEdit.EchoMode.Password)
            form.addRow(self.tr_text(key), field)
        def auth_changed():
            mode = auth.currentData()
            for key, field in fields.items():
                enabled = mode != 'none' and (key not in ('username', 'password', 'session_value') or (key == 'session_value' and mode in ('cookie', 'bearer')) or (key in ('username', 'password') and mode == 'basic'))
                field.setEnabled(enabled)
        auth.currentIndexChanged.connect(auth_changed)
        auth_changed()
        layout.addLayout(form)
        note = QLabel(self.tr_text('session_note'))
        note.setWordWrap(True)
        layout.addWidget(note)
        error = QLabel(self.tr_text('advanced_hint'))
        error.setWordWrap(True)
        layout.addWidget(error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)
        def accept():
            try:
                options = validate(dict(exclude_paths=exclusions.toPlainText(), ports=ports.text(), rate=rate.value(), nmap_rate=nmap_rate.value()))
                session = Session(mode=auth.currentData(), value=fields['session_value'].text(), username=fields['username'].text(), password=fields['password'].text(), label=fields['account_label'].text(), verify_url=fields['verify_url'].text(), marker=fields['verify_marker'].text())
                self.scan_options, self.pending_session = options, session
                self.scope_summary.setText(self.tr_text('configured_scope').format(rate=options['rate'], nmap_rate=options['nmap_rate'], ports=options['ports'] or self.tr_text('profile_default'), count=len(options['exclude_paths']), auth=self.tr_text('auth_' + session.mode)))
                dialog.accept()
            except (ValueError, TypeError) as exc:
                error.setText(str(exc))
        buttons.accepted.connect(accept)
        buttons.rejected.connect(dialog.reject)
        # Exposed widget references make validation testable with real native controls.
        dialog.fields, dialog.auth_box, dialog.exclusions = fields, auth, exclusions
        return dialog

    def configure_scan(self):
        if self.running():
            return
        dialog = self.make_options_dialog()
        dialog.exec()
        dialog.deleteLater()

    def selected_tools(self):
        return [tool for tool, check in self.tool_checks.items() if check.isChecked()]

    def background_job(self, callback):
        if self.busy_diagnostics:
            return
        self.busy_diagnostics = True
        self.workflow_cancel.clear()
        self.preflight_text.setPlainText(self.tr_text('diagnostics_running'))
        self.result_tabs.setCurrentIndex(6)
        def work():
            try:
                data = callback()
                self.background_results.put(('ok', data))
            except Exception:
                self.background_results.put(('error', self.tr_text('diagnostics_failed')))
        threading.Thread(target=work, daemon=True).start()

    def run_diagnostics(self):
        from .targets import normalize
        try:
            target = normalize(self.target.text())
            selected, profile, options = self.selected_tools(), self.profile, dict(self.scan_options)
            authenticated = bool(self.pending_session and self.pending_session.headers)
            self.background_job(lambda: preflight.inspect(target, selected, profile, options, authenticated, self.workflow_cancel))
        except ValueError as exc:
            self.show_notice(str(exc))

    def prepare_templates(self):
        if not self.running():
            self.background_job(lambda: (preflight.prepare_templates(self.workflow_cancel), self.tr_text('templates_ready'))[1])

    def poll_workflow(self):
        try:
            status, data = self.background_results.get_nowait()
            self.busy_diagnostics = False
            if isinstance(data, list):
                data = '\n\n'.join(row['tool'] + ' · ' + self.tr_text(row['status']) + '\n' + row['message'] for row in data)
            self.preflight_text.setPlainText(data)
        except queue.Empty:
            pass
        self.diagnostics_button.setEnabled(not self.busy_diagnostics and not self.running())

    def skip_tool(self):
        if self.current and engine.skip_current(self.current['id']):
            self.skip_button.setEnabled(False)

    def render_workflow(self):
        running = bool(self.running())
        self.advanced_button.setEnabled(not running)
        self.skip_button.setVisible(running)
        active = next((s for s in (self.current or {}).get('steps', []) if s['status'] == 'running'), None)
        self.skip_button.setEnabled(bool(active))
        self.tool_progress.setVisible(bool(active))
        if active:
            details = active.get('details', {})
            percent = details.get('percent')
            self.tool_progress.setRange(0, 0 if percent is None else 1000)
            if percent is not None:
                self.tool_progress.setValue(int(percent * 10))
                self.tool_progress.setFormat(f'{percent:.1f}% · ' + str(details.get('phase', '')))
            phase = details.get('phase', 'running')
            translated_phase = self.tr_text('phase_' + phase)
            text = active['tool'] + ' · ' + (phase if translated_phase == 'phase_' + phase else translated_phase)
            if percent is None:
                text += '\n' + self.tr_text('progress_unavailable')
            if details.get('last_activity'):
                text += '\n' + self.tr_text('last_activity').format(elapsed=estimates.duration(estimates.elapsed(details['last_activity'])))
            for key in ('requests', 'alerts', 'queued_records', 'pages_checked', 'scripts_checked', 'output_bytes'):
                if key in details:
                    text += '\n' + self.tr_text('metric_' + key) + ': ' + str(details[key])
            self.tool_activity.setText(text)
        else:
            self.tool_activity.setText(self.tr_text('progress_unavailable') if running else '')
        self.recheck_button.setEnabled(bool(self.findings.currentItem()) and not running)
        if not self.current:
            return
        if self.current.get('preflight'):
            self.preflight_text.setPlainText('\n\n'.join(row['tool'] + ' · ' + self.tr_text(row['status']) + '\n' + row['message'] for row in self.current['preflight']) + ('\n\n' + '\n'.join(self.current['warnings']) if self.current.get('warnings') else ''))

    def render_result_workflow(self):
        if not self.current:
            return
        lines = [self.tr_text('priority_note')]
        if self.current.get('recheck_result'):
            lines.append(self.tr_text('recheck_' + self.current['recheck_result']))
        for index, finding in enumerate(results.priorities(self.current)[:3], 1):
            title, explanation, action = describe(finding, self.language)
            lines.append(f"{index}. {self.tr_text(finding['severity'])} · {title}\n{finding['target']}\n" + self.tr_text(finding['verification']) + '\n' + explanation + '\n' + action + '\n' + self.tr_text('sources') + ': ' + ', '.join(finding['source_tools']) + '\n' + self.tr_text('observed_evidence') + ': ' + finding['evidence'][:1000])
        if self.current.get('errors') or self.current.get('warnings') or any(s['status'] in ('skipped', 'cancelled', 'failed') for s in self.current.get('steps', [])):
            lines.append(self.tr_text('priority_incomplete'))
        self.priority_summary.setPlainText('\n\n'.join(lines))
        baseline = self.baseline_box.currentData()
        self.baseline_box.blockSignals(True)
        self.baseline_box.clear()
        self.baseline_box.addItem(self.tr_text('automatic_baseline'), '')
        for scan in storage.recent():
            if scan['id'] != self.current['id'] and scan['target'] == self.current['target'] and scan['created'] < self.current.get('created', ''):
                self.baseline_box.addItem(scan['created'][:19] + ' · ' + self.tr_text(scan['status']), scan['id'])
        self.baseline_box.setCurrentIndex(max(0, self.baseline_box.findData(baseline)))
        self.baseline_box.blockSignals(False)
        self.render_comparison()

    def render_comparison(self):
        if not self.current:
            return
        baseline = self.baseline_box.currentData()
        data = results.compare(self.current, storage.get(baseline)) if baseline else self.current.get('comparison', dict(rows=[], reason='no_baseline'))
        self.comparison_note.setText(self.tr_text(data['reason']))
        self.comparison_tree.clear()
        for row in data['rows']:
            finding = row['finding']
            self.comparison_tree.addTopLevelItem(QTreeWidgetItem([self.tr_text('change_' + row['status']), describe(finding, self.language)[0], finding['target'], ', '.join(finding.get('source_tools', [finding['tool']]))]))

    def recheck_finding(self):
        item = self.findings.currentItem()
        if not item or self.running():
            return
        finding = next((f for f in self.records() if f['id'] == item.data(0, Qt.ItemDataRole.UserRole)), None)
        if finding is None:
            return
        original = self.current
        selected = [tool for tool in finding['source_tools'] if tool != 'moth']
        try:
            if original.get('profile') in ('high', 'ultra') and not self.active_consent.isChecked():
                self.profile_buttons[original['profile']].click()
                raise ValueError(self.tr_text('active_consent'))
            if original.get('authentication', {}).get('mode', 'none') != 'none' and not (self.pending_session and self.pending_session.headers):
                raise ValueError(self.tr_text('reenter_session'))
            identifier = engine.start(finding['target'], selected, self.authorized.isChecked(), self.lab.isChecked(), profile=original.get('profile', 'low'), active_authorized=self.active_consent.isChecked(), options=original.get('options', self.scan_options), session=self.pending_session, recheck_of=dict(scan=original['id'], finding=finding['id']))
            self.pending_session = None
            self.current = storage.get(identifier)
            self._last_scan = None
            self.render_scan()
        except ValueError as exc:
            self.show_notice(str(exc))
