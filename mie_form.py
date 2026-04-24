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
from mieplot import (
    plot_csv as plot_mie_csv,
    set_color_scale as set_mie_color_scale,
    set_metric as set_mie_metric,
)
from PyQt5.QtWidgets import (
    QWidget, QLabel, QLineEdit,
    QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QGroupBox,
    QFormLayout, QDialog, QTableWidget, QTableWidgetItem, QSizePolicy, QComboBox
)

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

configure_scatmech_path()


class MieForm(QWidget):
    def __init__(self):
        super().__init__()

        # Top-level layout
        self.main_layout = QHBoxLayout(self)
        self.setLayout(self.main_layout)

        # Left panel 
        self.form_layout = QVBoxLayout()
        form_widget = QWidget()
        form_widget.setLayout(self.form_layout)

        # Right panel
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

        # Input 
        grp = QGroupBox("Simulation Parameters")
        form = QFormLayout()

        self.step_angle_deg = QLineEdit("1")
        form.addRow("Step Angle (theta, deg):", self.step_angle_deg)

        self.step_phi_deg = QLineEdit("10")
        form.addRow("Step Azimuth (phi, deg):", self.step_phi_deg)

        self.wavelength_um = QLineEdit("0.532")
        form.addRow("Wavelength (µm):", self.wavelength_um)

        self.medium_optics = QLineEdit("(1,0)")
        form.addRow("Optical Properties of Surrounding Medium (n,k):", self.medium_optics)

        self.radius_um = QLineEdit("0.05")
        form.addRow("Radius (µm):", self.radius_um)

        self.sphere_optics = QLineEdit("(1.59,0)")
        form.addRow("Optical Properties of the Sphere (n,k):", self.sphere_optics)

        self.metric_combo = QComboBox()
        self.metric_combo.addItems(["S11", "Pol", "S33", "S34"])
        form.addRow("Metric:", self.metric_combo)

        grp.setLayout(form)
        self.form_layout.addWidget(grp)

        # Controls 
        ctrl = QHBoxLayout()
        self.run_btn = QPushButton("Run MieProg")
        self.clear_btn = QPushButton("Clear Plot")
        self.log_color_btn = QPushButton("Log Color: Off")
        self.log_color_btn.setCheckable(True)
        self.open_output_btn = QPushButton("Open Last Output")
        self.open_input_btn = QPushButton("Open Last Input")
        
        ctrl.setContentsMargins(0, 0, 0, 0)  
        ctrl.setSpacing(12)                 

        ctrl.addWidget(self.run_btn,        1)
        ctrl.addWidget(self.clear_btn,      1)
        ctrl.addWidget(self.log_color_btn,  1)
        ctrl.addWidget(self.open_output_btn,1)
        ctrl.addWidget(self.open_input_btn, 1)
        
        ctrl_wrap = QWidget()
        ctrl_wrap.setLayout(ctrl)
        self.form_layout.addWidget(ctrl_wrap)
        self.form_layout.addWidget(QLabel("Log:"))

        # Log 
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(140)
        self.log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.form_layout.addWidget(self.log)
        self.form_layout.addStretch(1)

        # Signals
        self.run_btn.clicked.connect(self.run_mieprog)
        self.clear_btn.clicked.connect(self.clear_plot)
        self.metric_combo.currentTextChanged.connect(self._on_metric_changed)
        self.log_color_btn.toggled.connect(self.toggle_log_color_scale)
        self.open_output_btn.clicked.connect(self.open_last_output)
        self.open_input_btn.clicked.connect(self.open_last_input)

        # Default intensity function
        self.metric_name = self.metric_combo.currentText()
        self.color_scale = "linear"

        # State
        self.last_stdout_path = None
        self.last_input_path = None
        self.last_csv_path = None
        self.last_rendered_csv_path = None

    # Core actions 
    def clear_plot(self):
        if hasattr(self, 'figure'):
            self.figure.clear()
        if hasattr(self, 'canvas'):
            self.canvas.draw()
        self.log.append("Plot cleared.")

    def run_mieprog(self):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        data_dir = get_data_dir(create=True)
        stdout_txt = str(data_dir / f"mie_output_{timestamp}.txt")
        csv_filename = str(data_dir / f"mie_output_{timestamp}.csv")

        p = self.to_params()

        def _norm_num(s):
            sx = str(s).strip()
            try:
                fx = float(sx)
                return str(int(fx)) if fx.is_integer() else str(fx)
            except Exception:
                return sx

        step_theta = _norm_num(p.get("step_angle_deg", "1"))
        step_phi   = _norm_num(p.get("step_phi_deg", "10"))
        wl_str     = _norm_num(p.get("wavelength_um", "0.532"))
        medium_str = str(p.get("medium_optics", "(1,0)")).strip()
        rad_str    = _norm_num(p.get("radius_um", "0.05"))
        sphere_str = str(p.get("sphere_optics", "(1.59,0)")).strip()

        stdin_payload = f"""{step_theta}
{step_phi}
{wl_str}
{medium_str}
{rad_str}
{sphere_str}
"""

        # Save input 
        input_txt = str(data_dir / f"mie_input_{timestamp}.txt")
        with open(input_txt, "w", encoding="utf-8") as f:
            f.write(stdin_payload)
        self.last_input_path = input_txt
        self.log.append(f"Saved input deck: {input_txt}")

        # Run executable
        exe = find_solver_executable("mieprog")
        if not exe:
            self.log.setText(format_missing_solver_message("mieprog"))
            return

        self.log.append(f"Running MieProg: {exe}")
        try:
            proc = subprocess.run(
                [exe],
                input=stdin_payload,
                capture_output=True, text=True, check=False,
                cwd=os.path.dirname(exe) if os.path.sep in exe else None,
            )
            # Save raw output
            with open(stdout_txt, "w", encoding="utf-8", errors="ignore") as f:
                self.last_stdout_path = stdout_txt
                f.write(proc.stdout or "")
                if proc.stderr:
                    f.write("\n--- STDERR ---\n")
                    f.write(proc.stderr)

            if proc.returncode != 0:
                self.log.append("mieprog returned non-zero exit. See output text for details.")
                return

            out = proc.stdout or ""
            self.log.append("mieprog completed. Parsing output table…")

            # Parse table 
            lines = out.splitlines()
            header_idx = None
            header = None
            for i, line in enumerate(lines):
                s = line.strip()
                if not s:
                    continue
                if s.startswith("Theta") or s.startswith("Angle"):
                    header_idx = i
                    header = re.split(r"\s+", s)
                    break

            if header_idx is None or not header:
                self.log.append("Could not find data header ('Theta Phi ...' or 'Angle ...').")
                return

            data_rows = []
            for line in lines[header_idx+1:]:
                if not line.strip():
                    break
                parts = re.split(r"\s+", line.strip())
                try:
                    float(parts[0]) 
                except Exception:
                    break
                data_rows.append(parts)

            if not data_rows:
                self.log.append("No data rows found in Mie output.")
                return

            # Write CSV 
            with open(csv_filename, "w", newline="") as fcsv:
                w = csv.writer(fcsv)
                w.writerow(header)
                w.writerows(data_rows)
            self.last_csv_path = csv_filename
            self.log.append(f"Saved CSV: {csv_filename}")

            self.render_with_external(csv_filename)

        except FileNotFoundError:
            self.log.append(format_missing_solver_message("mieprog"))
        except Exception as e:
            self.log.append(f"Error running mieprog: {e}")

        # External plot module connection
    def render_with_external(self, csv_path: str):
        if csv_path:
            self.last_rendered_csv_path = csv_path
            self.last_csv_path = csv_path

        def _render(scale: str):
            self.figure.clear()
            ax = self.figure.add_subplot(111, projection="3d")
            set_mie_metric(getattr(self, "metric_name", "S11"))
            set_mie_color_scale(scale)
            plot_mie_csv(ax, csv_path)

        try:
            _render(getattr(self, "color_scale", "linear"))
            self.canvas.draw()
            self.log.append("Plot updated.")
        except Exception as e:
            if self.color_scale == "log":
                previous = self.log_color_btn.blockSignals(True)
                self.log_color_btn.setChecked(False)
                self.log_color_btn.blockSignals(previous)
                self.color_scale = "linear"
                self.log_color_btn.setText("Log Color: Off")
                try:
                    _render("linear")
                    self.canvas.draw()
                    self.log.append(f"mieplot render error: {e}")
                    self.log.append("Log color scale is unavailable for the current metric. Reverted to linear scale.")
                    self.log.append("Plot updated.")
                    return
                except Exception as fallback_exc:
                    self.log.append(f"mieplot render error: {fallback_exc}")
                    self.canvas.draw()
                    return
            self.log.append(f"mieplot render error: {e}")
            self.canvas.draw()

    def toggle_log_color_scale(self, checked: bool):
        self.color_scale = "log" if checked else "linear"
        self.log_color_btn.setText("Log Color: On" if checked else "Log Color: Off")
        if not self._rerender_last_plot():
            view_name = "log" if checked else "normal"
            self.log.append(f"Color scale selected: {view_name}. It will apply after the next MieProg run.")
            return
        if checked and self.color_scale != "log":
            self.log.append("Log color scale is unavailable for the current metric; linear scale remains active.")
            return
        view_name = "log" if checked else "normal"
        self.log.append(f"Color scale selected: {view_name}. Re-rendered current Mie plot.")

    def _on_metric_changed(self, name: str):
        if not name:
            return
        self.metric_name = name
        if self._rerender_last_plot():
            self.log.append(f"Metric selected: {name}. Re-rendered current Mie plot.")
        else:
            self.log.append(f"Metric selected: {name}. It will apply after the next Mie plot is available.")

    def _rerender_last_plot(self) -> bool:
        csv_path = (
            getattr(self, "last_rendered_csv_path", None)
            or getattr(self, "last_csv_path", None)
        )
        if not csv_path or not os.path.exists(csv_path):
            return False
        self.render_with_external(csv_path)
        return True


    # Parameter 
    def to_params(self):
        return {
            "step_angle_deg": self._get_text("step_angle_deg", "1"),
            "step_phi_deg": self._get_text("step_phi_deg", "10"),
            "wavelength_um": self._get_text("wavelength_um", "0.532"),
            "medium_optics": self._get_text("medium_optics", "(1,0)"),
            "radius_um": self._get_text("radius_um", "0.05"),
            "sphere_optics": self._get_text("sphere_optics", "(1.59,0)"),
            "metric": self.metric_combo.currentText(),
            "color_scale": self.color_scale,
        }

    def from_params(self, p: dict):
        self._set_text("step_angle_deg", p.get("step_angle_deg"))
        self._set_text("step_phi_deg", p.get("step_phi_deg"))
        self._set_text("wavelength_um", p.get("wavelength_um"))
        self._set_text("medium_optics", p.get("medium_optics"))
        self._set_text("radius_um", p.get("radius_um"))
        self._set_text("sphere_optics", p.get("sphere_optics"))
        metric = p.get("metric")
        if metric:
            idx = self.metric_combo.findText(str(metric))
            if idx >= 0:
                previous = self.metric_combo.blockSignals(True)
                self.metric_combo.setCurrentIndex(idx)
                self.metric_combo.blockSignals(previous)
                self.metric_name = self.metric_combo.currentText()
        scale = str(p.get("color_scale", "linear") or "linear").lower()
        previous = self.log_color_btn.blockSignals(True)
        self.log_color_btn.setChecked(scale == "log")
        self.log_color_btn.blockSignals(previous)
        self.color_scale = "log" if scale == "log" else "linear"
        self.log_color_btn.setText("Log Color: On" if self.color_scale == "log" else "Log Color: Off")

    # Viewers 
    def _find_latest(self, prefix: str, folder: str):
        try:
            paths = [os.path.join(folder, f) for f in os.listdir(folder) if f.startswith(prefix)]
            if not paths:
                return None
            return max(paths, key=lambda p: os.path.getmtime(p))
        except Exception:
            return None

    def _read_file(self, path: str):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception as e:
            return f"(Could not open file: {e})"

    def open_last_output(self):
        import csv as _csv
        data_dir = str(get_data_dir())
        path = getattr(self, "last_stdout_path", None)
        if not path or not os.path.exists(path):
            path = self._find_latest("mie_output_", data_dir)
        if not path:
            self.log.append("No Mie output file found in DATA.")
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

        _, ext = os.path.splitext(path)
        ext = (ext or "").lower()
        if ext == ".csv":
            try:
                with open(path, newline="") as f:
                    rows = list(_csv.reader(f))
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
                    txt.setPlainText("")
            except Exception as e:
                txt.setPlainText(f"(Failed to open CSV: {e})")
        else:
            text = self._read_file(path)
            lines = text.splitlines()
            header_idx = None
            for i, line in enumerate(lines):
                s = line.strip()
                if s.startswith("Theta") or s.startswith("Angle"):
                    header_idx = i
                    break
            pre = "\n".join(lines[:header_idx]) if header_idx not in (None, 0) else ""
            txt.setPlainText(pre if pre else "(No preamble)")
            if header_idx is not None:
                header = re.split(r"\s+", lines[header_idx].strip())
                data_rows = []
                for line in lines[header_idx+1:]:
                    if not line.strip():
                        break
                    parts = re.split(r"\s+", line.strip())
                    try:
                        float(parts[0])
                    except Exception:
                        break
                    data_rows.append(parts)
                table.setColumnCount(len(header))
                table.setRowCount(len(data_rows))
                table.setHorizontalHeaderLabels(header)
                for r, row in enumerate(data_rows):
                    for c, val in enumerate(row):
                        table.setItem(r, c, QTableWidgetItem(val))
                table.setSortingEnabled(True)
                table.resizeColumnsToContents()
            else:
                txt.setPlainText(text)

        dlg.resize(900, 700)
        dlg.exec_()

    def open_last_input(self):
        data_dir = str(get_data_dir())
        path = getattr(self, "last_input_path", None)
        if not path or not os.path.exists(path):
            path = self._find_latest("mie_input_", data_dir)
        if not path:
            self.log.append("No Mie input deck found in DATA.")
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

    # Helpers
    def _get_text(self, name, default=""):
        try:
            w = getattr(self, name, None)
            return w.text().strip() if w is not None else default
        except Exception:
            return default

    def _set_text(self, name, value):
        try:
            w = getattr(self, name, None)
            if w is not None and value is not None:
                w.setText(str(value))
        except Exception:
            pass
