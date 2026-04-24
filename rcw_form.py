import os
import re
import csv
import datetime
import subprocess
from scatmech_paths import (
    configure_scatmech_path,
    find_solver_executable,
    format_missing_solver_message,
    get_data_dir,
)
from rcwplot import plot_csv as plot_rcw_csv
from scatmech_gratings import ONE_D_GRATING_SPECS, get_one_d_grating_spec
from PyQt5.QtWidgets import (
    QWidget, QLabel, QLineEdit,
    QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QGroupBox,
    QFormLayout, QFileDialog, QComboBox,
    QSizePolicy, QTableWidget, QTableWidgetItem, QDialog
)

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

configure_scatmech_path()


_TYPE_CHOICES = [
    ("Reflection into incident medium", "0"),
    ("Transmission into incident medium", "1"),
    ("Reflection into transmission medium", "2"),
    ("Transmission into transmission medium", "3"),
]

class RCWForm(QWidget):

    def __init__(self):
        super().__init__()

        self._grating_param_store = {}
        self._current_grating_module = None
        self.grating_param_inputs = {}
        
        self.main_layout = QHBoxLayout(self)
        self.setLayout(self.main_layout)

        self.form_layout = QVBoxLayout()
        form_widget = QWidget()
        form_widget.setLayout(self.form_layout)

        self.figure = Figure(figsize=(6, 5), tight_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        plot_layout = QVBoxLayout()
        plot_layout.addWidget(self.canvas, 1)
        plot_widget = QWidget()
        plot_widget.setLayout(plot_layout)

        self.main_layout.addWidget(form_widget, 1)
        self.main_layout.addWidget(plot_widget, 1)
        self.main_layout.setStretch(0, 1)
        self.main_layout.setStretch(1, 1)

        basic_group = QGroupBox("Simulation Parameters")
        basic_form = QFormLayout()

        self.order = QLineEdit("6")
        basic_form.addRow("Maximum Diffraction Order:", self.order)

        self.type_combo = QComboBox()
        for label, code in _TYPE_CHOICES:
            self.type_combo.addItem(label, code)
        basic_form.addRow("Configuration Type:", self.type_combo)

        self.wavelength_um = QLineEdit("0.532")
        basic_form.addRow("Wavelength (µm):", self.wavelength_um)

        self.theta_inc_deg = QLineEdit("0")
        basic_form.addRow("Incident Polar Angle θᵢ (deg):", self.theta_inc_deg)

        self.rotation_deg = QLineEdit("0")
        basic_form.addRow("Grating Rotation φ (deg):", self.rotation_deg)

        basic_group.setLayout(basic_form)
        self.form_layout.addWidget(basic_group)

        grating_group = QGroupBox("Grating Definition")
        grating_form = QFormLayout()
        
        self.grating_model_combo = QComboBox()
        for model_name in ONE_D_GRATING_SPECS:
            self.grating_model_combo.addItem(model_name)
        grating_form.addRow("Module:", self.grating_model_combo)

        self.grating_param_container = QWidget()
        self.grating_param_layout = QFormLayout()
        self.grating_param_container.setLayout(self.grating_param_layout)
        grating_form.addRow(self.grating_param_container)

        self.browse_grating = None
        grating_group.setLayout(grating_form)
        self.form_layout.addWidget(grating_group)

        ctrl_row = QHBoxLayout()
        self.run_btn = QPushButton("Run RCWProg")
        self.clear_btn = QPushButton("Clear Plot")
        self.open_output_btn = QPushButton("Open Last Output")
        self.open_input_btn = QPushButton("Open Last Input")
        ctrl_row.addWidget(self.run_btn, 1)
        ctrl_row.addWidget(self.clear_btn, 1)
        ctrl_row.addWidget(self.open_input_btn, 1)
        ctrl_row.addWidget(self.open_output_btn, 1)
        ctrl_widget = QWidget()
        ctrl_widget.setLayout(ctrl_row)
        self.form_layout.addWidget(ctrl_widget)

        self.form_layout.addWidget(QLabel("Log:"))
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(140)
        self.log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.form_layout.addWidget(self.log)
        self.form_layout.addStretch(1)

        self.run_btn.clicked.connect(self.run_rcwprog)
        self.clear_btn.clicked.connect(self.clear_plot)
        self.open_output_btn.clicked.connect(self.open_last_output)
        self.open_input_btn.clicked.connect(self.open_last_input)
        self.grating_model_combo.currentTextChanged.connect(self._on_grating_model_changed)
        
        self.last_stdout_path = None
        self.last_input_path = None
        self.last_csv_path = None
        
        self._rebuild_grating_param_form(self.grating_model_combo.currentText())

    def clear_plot(self):
        if hasattr(self, "figure"):
            self.figure.clear()
        if hasattr(self, "canvas"):
            self.canvas.draw()
        self.log.append("Plot cleared.")

    def _browse_for_grating(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Select grating file", "", "All Files (*)")
        if fname:
            widget = self.grating_param_inputs.get("filename")
            if widget is not None:
                widget.setText(fname)
            else:
                self.log.append("Filename field not available for current grating module.")
            
    def _build_input_payload(self):
        order = self.order.text().strip() or "6"
        type_code = self.type_combo.currentData() or "0"
        wavelength = self.wavelength_um.text().strip() or "0.532"
        theta = self.theta_inc_deg.text().strip() or "0"
        rotation = self.rotation_deg.text().strip() or "0"
        module_name = self.grating_model_combo.currentText() or next(iter(ONE_D_GRATING_SPECS))

        lines = [order, type_code, wavelength, theta, rotation, module_name]

        for field in self._get_model_fields(module_name):
            lines.append(self._get_grating_param_value(field["name"], field["default"]))
            
        return "\n".join(lines) + "\n"
    
    def _get_model_fields(self, module_name):
        if module_name not in ONE_D_GRATING_SPECS:
            module_name = next(iter(ONE_D_GRATING_SPECS))
        return get_one_d_grating_spec(module_name)["fields"]

    def _get_grating_param_value(self, name, default):
        widget = self.grating_param_inputs.get(name)
        if widget is None:
            return default
        text = widget.text().strip()
        return text if text else default

    def _store_current_grating_params(self):
        module = getattr(self, "_current_grating_module", None)
        if not module:
            return
        values = {}
        for name, widget in self.grating_param_inputs.items():
            values[name] = widget.text()
        self._grating_param_store[module] = values

    def _rebuild_grating_param_form(self, module_name):
        while self.grating_param_layout.count():
            item = self.grating_param_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.grating_param_inputs = {}
        self.browse_grating = None

        values = self._grating_param_store.get(module_name, {})

        for field in self._get_model_fields(module_name):
            name = field["name"]
            stored_value = values.get(name)
            value = stored_value if stored_value not in (None, "") else field["default"]
            use_browse = module_name == "Generic_Grating" and name == "filename"
            self._add_grating_param_row(name, field["label"], value, browse=use_browse)

        self._current_grating_module = module_name

    def _add_grating_param_row(self, name, label, value, browse=False):
        line_edit = QLineEdit()
        line_edit.setText(value or "")
        self.grating_param_inputs[name] = line_edit

        if browse:
            row_widget = QWidget()
            row_layout = QHBoxLayout()
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(line_edit)
            browse_btn = QPushButton("Browse…")
            browse_btn.clicked.connect(self._browse_for_grating)
            row_layout.addWidget(browse_btn)
            row_widget.setLayout(row_layout)
            self.grating_param_layout.addRow(f"{label}:", row_widget)
            self.browse_grating = browse_btn
        else:
            self.grating_param_layout.addRow(f"{label}:", line_edit)

    def _on_grating_model_changed(self, module_name):
        self._store_current_grating_params()
        self._rebuild_grating_param_form(module_name)

    def run_rcwprog(self):
        payload = self._build_input_payload()
        self.last_csv_path = None        

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        data_dir = get_data_dir(create=True)
        input_txt = str(data_dir / f"rcw_input_{timestamp}.txt")
        output_txt = str(data_dir / f"rcw_stdout_{timestamp}.log")
        csv_filename = str(data_dir / f"rcw_output_{timestamp}.csv")

        try:
            with open(input_txt, "w", encoding="utf-8") as f:
                f.write(payload + "\n")
            self.last_input_path = input_txt
            self.log.append(f"Saved input deck: {input_txt}")
        except Exception as exc:
            self.log.append(f"[Error] Could not write input deck: {exc}")
            return

        exe = find_solver_executable("rcwprog")
        if not exe:
            self.log.append(format_missing_solver_message("rcwprog"))
            return

        self.log.append(f"Running RCWProg: {exe}")
        try:
            proc = subprocess.run(
                [exe],
                input=payload,
                capture_output=True,
                text=True,
                check=False,
                cwd=os.path.dirname(exe) if os.path.sep in exe else None,
            )
        except Exception as exc:
            self.log.append(f"[Error] Could not invoke rcwprog: {exc}")
            return

        try:
            with open(output_txt, "w", encoding="utf-8", errors="ignore") as f:
                f.write(proc.stdout or "")
                if proc.stderr:
                    f.write("\n--- STDERR ---\n")
                    f.write(proc.stderr)
            self.last_stdout_path = output_txt
            self.log.append(f"Saved stdout log: {output_txt}")
        except Exception as exc:
            self.log.append(f"[Warning] Failed to store stdout: {exc}")

        if proc.returncode != 0:
            self.log.append("rcwprog returned non-zero exit code. See output log for details.")
            return

        self.log.append("rcwprog completed. Parsing output table…")

        try:
            header, rows = self._extract_table(proc.stdout)
        except Exception as exc:
            self.log.append(f"[Error] Failed to parse rcwprog output: {exc}")
            return

        if not rows:
            self.log.append("No numeric rows detected in rcwprog output.")
            return

        try:
            with open(csv_filename, "w", newline="", encoding="utf-8") as fcsv:
                writer = csv.writer(fcsv)
                if header:
                    writer.writerow(header)
                writer.writerows(rows)
            self.log.append(f"Saved CSV: {csv_filename}")
            self.last_csv_path = csv_filename
        except Exception as exc:
            self.log.append(f"[Error] Could not write CSV: {exc}")
            return

        self.render_with_external(csv_filename)

    def _extract_table(self, stdout: str):
        if not stdout:
            return [], []
        lines = stdout.splitlines()
        header_idx = None
        header = []
        for i, line in enumerate(lines):
            tokens = re.split(r"\s+", line.strip())
            if not tokens:
                continue
            lowered = [t.lower() for t in tokens]
            if any(key in lowered for key in ("order", "theta", "phi", "rs", "rp", "diff")):
                header_idx = i
                header = tokens
                break
        data_rows = []
        start = header_idx + 1 if header_idx is not None else 0
        for line in lines[start:]:
            s = line.strip()
            if not s:
                if data_rows:
                    break
                continue
            parts = re.split(r"\s+", s)
            if not parts:
                continue
            numeric_prefix = 0
            for token in parts:
                try:
                    float(token)
                    numeric_prefix += 1
                except Exception:
                    break
            if numeric_prefix == 0:
                if data_rows:
                    break
                continue
            data_rows.append(parts[:numeric_prefix])
        if not header and data_rows:
            width = max(len(row) for row in data_rows)
            header = [f"col{i+1}" for i in range(width)]
        if header:
            width = min(len(header), max(len(row) for row in data_rows))
            header = header[:width]
        else:
            width = max(len(row) for row in data_rows)
        trimmed = [row[:width] for row in data_rows]
        return header, trimmed

    def render_with_external(self, csv_path: str):
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        try:
            plot_rcw_csv(ax, csv_path)
            self.canvas.draw()
            self.log.append("Plot updated.")
        except Exception as exc:
            self.log.append(f"rcwplot render error: {exc}")
            self.canvas.draw()

    def open_last_output(self):
        data_dir = str(get_data_dir())
        path = getattr(self, "last_csv_path", None)
        if not path or not os.path.exists(path):
            path = self._find_latest("rcw_output_", data_dir, suffix=".csv")
        if not path:
            self.log.append("No RCW CSV output found in DATA.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Output: {os.path.basename(path)}")
        layout = QVBoxLayout(dlg)

        txt = QTextEdit(dlg)
        txt.setReadOnly(True)
        txt.setMinimumHeight(120)
        layout.addWidget(txt)

        table = QTableWidget(dlg)
        table.setMinimumHeight(320)
        layout.addWidget(table)

        btn_row = QHBoxLayout()
        close_btn = QPushButton("Close", dlg)
        btn_row.addStretch(1)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        close_btn.clicked.connect(dlg.accept)

        try:
            with open(path, newline="") as f:
                rows = list(csv.reader(f))
            if not rows:
                txt.setPlainText("(Empty CSV)")
            else:
                header, data = rows[0], rows[1:]
                table.setColumnCount(len(header))
                table.setRowCount(len(data))
                table.setHorizontalHeaderLabels(header)
                for r, row in enumerate(data):
                    for c, val in enumerate(row):
                        table.setItem(r, c, QTableWidgetItem(val))
                table.setSortingEnabled(True)
                table.resizeColumnsToContents()
                txt_path = getattr(self, "last_stdout_path", None)
                if txt_path and os.path.exists(txt_path):
                    txt.setPlainText(self._read_file(txt_path))
                    
                else:
                    txt.setPlainText("(Stdout log not available)")
        except Exception as exc:
            txt.setPlainText(f"(Failed to open CSV: {exc})")
                    
        dlg.resize(900, 700)
        dlg.exec_()

    def open_last_input(self):
        data_dir = str(get_data_dir())
        path = getattr(self, "last_input_path", None)
        if not path or not os.path.exists(path):
            path = self._find_latest("rcw_input_", data_dir)
        if not path:
            self.log.append("No RCW input deck found in DATA.")
            return
        content = self._read_file(path)
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Input: {os.path.basename(path)}")
        layout = QVBoxLayout(dlg)
        view = QTextEdit(dlg)
        view.setReadOnly(True)
        view.setPlainText(content)
        layout.addWidget(view)
        btn_row = QHBoxLayout()
        close_btn = QPushButton("Close", dlg)
        btn_row.addStretch(1)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        close_btn.clicked.connect(dlg.accept)
        dlg.resize(700, 500)
        dlg.exec_()

    def _find_latest(self, prefix: str, folder: str, suffix: str = ""):
        try:
            paths = [
                os.path.join(folder, f)
                for f in os.listdir(folder)
                if f.startswith(prefix) and f.endswith(suffix)
            ] if suffix else [
                os.path.join(folder, f)
                for f in os.listdir(folder)
                if f.startswith(prefix)
            ]
            if not paths:
                return None
            return max(paths, key=lambda p: os.path.getmtime(p))
        except Exception:
            return None

    def _read_file(self, path: str):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception as exc:
            return f"(Could not open file: {exc})"

    def to_params(self):
        return {
            "order": self.order.text().strip(),
            "type": self.type_combo.currentData(),
            "wavelength_um": self.wavelength_um.text().strip(),
            "theta_inc_deg": self.theta_inc_deg.text().strip(),
            "rotation_deg": self.rotation_deg.text().strip(),
            "grating_module": self.grating_model_combo.currentText(),
            "grating_params": {
                name: widget.text().strip()
                for name, widget in self.grating_param_inputs.items()
            },
        }

    def from_params(self, params: dict):
        if not params:
            return
        self.order.setText(params.get("order", ""))
        type_code = params.get("type")
        if type_code is not None:
            idx = self.type_combo.findData(type_code)
            if idx >= 0:
                self.type_combo.setCurrentIndex(idx)
        self.wavelength_um.setText(params.get("wavelength_um", ""))
        self.theta_inc_deg.setText(params.get("theta_inc_deg", ""))
        self.rotation_deg.setText(params.get("rotation_deg", ""))
        module_name = params.get("grating_module")
        stored_params = params.get("grating_params") or {}

        if module_name:
            self._grating_param_store[module_name] = stored_params
            idx = self.grating_model_combo.findText(module_name)
            if idx >= 0:
                current_idx = self.grating_model_combo.currentIndex()
                self.grating_model_combo.setCurrentIndex(idx)
                if idx == current_idx:
                    self._rebuild_grating_param_form(module_name)
            else:
                self.grating_model_combo.setCurrentIndex(0)
        else:
            current_module = self.grating_model_combo.currentText()
            if stored_params:
                self._grating_param_store[current_module] = stored_params
                self._rebuild_grating_param_form(current_module)
