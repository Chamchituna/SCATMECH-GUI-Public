import os
import csv
import re
import datetime
import subprocess
import importlib, importlib.util, sys
from pathlib import Path
from scatmech_paths import (
    configure_scatmech_path,
    find_solver_executable,
    format_missing_solver_message,
    get_data_dir,
    open_with_default_app,
)
from PyQt5.QtWidgets import (
    QWidget, QLabel, QLineEdit,
    QVBoxLayout, QHBoxLayout,
    QPushButton, QComboBox,
    QTextEdit, QGroupBox,
    QFormLayout,
    QTableWidget, QTableWidgetItem,
    QSizePolicy, QMessageBox
)
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

configure_scatmech_path()

_NK_RE = re.compile(r"^\s*\(?\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*,\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*\)?\s*$")

def _parse_nk(text: str):
    m = _NK_RE.match(text or "")
    if not m:
        raise ValueError("Expected (n,k) pair, e.g. (1.5,0)")
    n = float(m.group(1))
    k = float(m.group(2))
    return n, k

def _is_float(s: str) -> bool:
    try:
        float(s)
        return True
    except Exception:
        return False


class ReflectForm(QWidget):

    def __init__(self):
        super().__init__()

        self.main_layout = QHBoxLayout(self)
        self.setLayout(self.main_layout)

        # Left
        self.form_layout = QVBoxLayout()
        form_widget = QWidget()
        form_widget.setLayout(self.form_layout)

        # Right
        self.figure = Figure(figsize=(5.6, 3.4), tight_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.main_layout.addWidget(form_widget, 0)
        self.main_layout.addWidget(self.canvas, 1)

        # Wavelength
        wl_group = QGroupBox("Wavelength [µm]")
        wl_form = QFormLayout()
        self.wavelength = QLineEdit("0.633")  # default matches ReflectProg example
        wl_form.addRow("λ (µm):", self.wavelength)
        wl_group.setLayout(wl_form)

        # Substrate
        sub_group = QGroupBox("Substrate dielectric (n,k)")
        sub_form = QFormLayout()
        self.sub_n = QLineEdit("1.50")
        self.sub_k = QLineEdit("0.00")
        row_subnk = QHBoxLayout()
        row_subnk.addWidget(QLabel("n:"))
        row_subnk.addWidget(self.sub_n)
        row_subnk.addWidget(QLabel("k:"))
        row_subnk.addWidget(self.sub_k)
        sub_form.addRow("Substrate (n,k):", row_subnk)
        sub_group.setLayout(sub_form)

        # Film stack
        stack_group = QGroupBox("Film Stack (bottom → top)")
        stack_v = QVBoxLayout()

        tool_row = QHBoxLayout()
        self.btn_add = QPushButton("Add Layer")
        self.btn_remove = QPushButton("Remove Selected")
        self.btn_up = QPushButton("Move Up")
        self.btn_down = QPushButton("Move Down")
        for b in (self.btn_add, self.btn_remove, self.btn_up, self.btn_down):
            tool_row.addWidget(b)
        tool_row.addStretch(1)
        stack_v.addLayout(tool_row)

        self.tbl = QTableWidget(0, 2)
        self.tbl.setHorizontalHeaderLabels(["Material (n,k)", "Thickness [µm]"])
        self.tbl.horizontalHeader().setStretchLastSection(True)
        stack_v.addWidget(self.tbl)

        stack_group.setLayout(stack_v)

        # Plot selection 
        plot_group = QGroupBox("Plot")
        plot_form = QFormLayout()
        self.plot_column = QComboBox()
        self.plot_column.addItems(["R_p (p-pol)", "R_s (s-pol)"])
        plot_form.addRow("Y-axis:", self.plot_column)
        plot_group.setLayout(plot_form)

        # Output / actions
        action_row = QHBoxLayout()
        self.run_btn = QPushButton("Run reflectprog")
        self.clear_btn = QPushButton("Clear Plot")
        self.open_output_btn = QPushButton("Open Last Output")
        self.open_input_btn = QPushButton("Open Last Input")
        action_row.addWidget(self.run_btn, 1)
        action_row.addWidget(self.clear_btn, 1)
        action_row.addWidget(self.open_input_btn, 1)
        action_row.addWidget(self.open_output_btn, 1)

        # Output box 
        self.output_box = QTextEdit()
        self.output_box.setReadOnly(True)
        self.output_box.setMinimumHeight(120)

        # Assemble left form
        self.form_layout.addWidget(wl_group)
        self.form_layout.addWidget(sub_group)
        self.form_layout.addWidget(stack_group)
        self.form_layout.addWidget(plot_group)
        self.form_layout.addLayout(action_row)
        self.form_layout.addWidget(QLabel("Log:"))
        self.form_layout.addWidget(self.output_box)
        self.form_layout.addStretch(1)

        # Signals
        self.btn_add.clicked.connect(self._add_layer)
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_up.clicked.connect(lambda: self._move_selected(-1))
        self.btn_down.clicked.connect(lambda: self._move_selected(+1))

        self.run_btn.clicked.connect(self.run_reflectprog)
        self.clear_btn.clicked.connect(self.clear_plot)
        self.open_output_btn.clicked.connect(self.open_last_output)
        self.open_input_btn.clicked.connect(self.open_last_input)

        # State
        self.last_stdout_path = None
        self.last_input_path = None

        # Demo layer
        self._add_layer(default_material="(1.50,0.00)", default_thickness="0.100000")


    # Stack table
    def _add_layer(self, default_material=None, default_thickness=None):
        r = self.tbl.rowCount()
        self.tbl.insertRow(r)
        mat = QTableWidgetItem(default_material or "(1.50,0.00)")
        thk = QTableWidgetItem(default_thickness or "0.100000")
        self.tbl.setItem(r, 0, mat)
        self.tbl.setItem(r, 1, thk)

    def _remove_selected(self):
        rows = {idx.row() for idx in self.tbl.selectedIndexes()}
        for r in sorted(rows, reverse=True):
            self.tbl.removeRow(r)

    def _move_selected(self, direction: int):
        r = self.tbl.currentRow()
        if r < 0:
            return
        new_r = r + direction
        if not (0 <= new_r < self.tbl.rowCount()):
            return
        row_vals = [self.tbl.item(r, c).text() if self.tbl.item(r, c) else "" for c in range(2)]
        self.tbl.removeRow(r)
        self.tbl.insertRow(new_r)
        self.tbl.setItem(new_r, 0, QTableWidgetItem(row_vals[0]))
        self.tbl.setItem(new_r, 1, QTableWidgetItem(row_vals[1]))
        self.tbl.selectRow(new_r)

    # Basic actions 
    def clear_plot(self):
        self.figure.clear()
        self.canvas.draw()

    def open_last_output(self):
        if self.last_stdout_path and os.path.exists(self.last_stdout_path):
            try:
                open_with_default_app(self.last_stdout_path)
            except Exception as exc:
                self.output_box.append(f"Could not open output file: {exc}")
        else:
            self.output_box.append("No output to open.")

    def open_last_input(self):
        if self.last_input_path and os.path.exists(self.last_input_path):
            try:
                open_with_default_app(self.last_input_path)
            except Exception as exc:
                self.output_box.append(f"Could not open input file: {exc}")
        else:
            self.output_box.append("No input file to open.")

    # Build console session for reflectprog 
    def _build_input_lines(self):
        # Validate wavelength
        wl_txt = self.wavelength.text().strip()
        if not _is_float(wl_txt):
            raise ValueError("Wavelength must be a number in µm, e.g. 0.633")

        # Substrate (n,k) 
        n, k = _parse_nk(f"({self.sub_n.text().strip()},{self.sub_k.text().strip()})")

        # Build layer list
        layer_pairs = []
        for r in range(self.tbl.rowCount()):
            mat_txt = (self.tbl.item(r, 0).text() if self.tbl.item(r, 0) else "").strip()
            thk_txt = (self.tbl.item(r, 1).text() if self.tbl.item(r, 1) else "").strip()
            if not mat_txt and not thk_txt:
                continue
            _parse_nk(mat_txt)  # validates (n,k)
            if not _is_float(thk_txt):
                raise ValueError(f"Thickness must be numeric at row {r+1}.")
            layer_pairs.extend([mat_txt, thk_txt])

        lines = []
        lines.append(wl_txt)              # wavelength
        lines.append(f"({n},{k})")       # substrate (n,k)
        lines.append(" ".join(layer_pairs) if layer_pairs else "")  # stack
        lines.append("")                  # end of stack
        return lines

    # External plot 
    def render_with_external(self, csv_path: str, y_idx: int):
        self.figure.clear()
        ax = self.figure.gca()

        here = Path(__file__).resolve().parent
        cwd = Path(os.getcwd())
        csv_dir = Path(csv_path).resolve().parent if csv_path else None

        tried = []
        mod = None
        how = None

        def _try_import(name):
            nonlocal mod, how
            try:
                mod = importlib.import_module(name)
                how = f"import {name}"
                return True
            except Exception as e:
                tried.append(f"import {name}: {e}")
                return False

        def _try_path(path):
            nonlocal mod, how
            try:
                if path and path.exists():
                    spec = importlib.util.spec_from_file_location("reflectplot", str(path))
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        sys.modules["reflectplot"] = mod
                        spec.loader.exec_module(mod)
                        how = f"spec_from_file_location({path})"
                        return True
            except Exception as e:
                tried.append(f"load {path}: {e}")
            return False

        if not _try_import("reflectplot"):
            if not _try_path(here / "reflectplot.py"):
                if not _try_path(cwd / "reflectplot.py") and csv_dir:
                    _try_path(csv_dir / "reflectplot.py")

        if mod is None:
            self.output_box.append("Could not import reflectplot.py: " + " | ".join(tried))
            self.canvas.draw()
            return
        else:
            self.output_box.append(f"reflectplot resolved via: {how}")

        fn = getattr(mod, "plot_csv", None)
        if not callable(fn):
            self.output_box.append("reflectplot.py found, but it must define plot_csv(ax, csv_path, ...).")
            self.canvas.draw()
            return

        try:
            label = "Rp" if y_idx == 1 else ("Rs" if y_idx == 2 else None)
            fn(ax, csv_path, x_col=0, y_col=y_idx, semilogy=False, label=label)
            self.canvas.draw()
            self.output_box.append("Plot updated via reflectplot.plot_csv")
        except Exception as e:
            self.output_box.append(f"reflectplot render error: {e}")
            self.canvas.draw()

    # Run reflectprog, save outputs, and plot
    def run_reflectprog(self):
        try:
            input_lines = self._build_input_lines()
        except Exception as e:
            QMessageBox.critical(self, "Invalid input", str(e))
            return

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        data_dir = get_data_dir(create=True)
        input_filename = str(data_dir / f"reflect_input_{timestamp}.txt")
        output_filename = str(data_dir / f"reflect_output_{timestamp}.txt")
        csv_filename = str(data_dir / f"reflect_output_{timestamp}.csv")

        with open(input_filename, "w", encoding="utf-8") as f:
            for ln in input_lines:
                f.write(ln + "\n")
        self.last_input_path = input_filename

        exe = find_solver_executable("reflectprog")
        if not exe:
            self.output_box.setText(format_missing_solver_message("reflectprog"))
            return

        try:
            result = subprocess.run(
                [exe],
                input="\n".join(input_lines),
                text=True,
                capture_output=True,
                check=False
            )
        except Exception as e:
            self.output_box.setText(f"[Error] Could not invoke reflectprog: {e}")
            return

        if result.returncode != 0:
            self.output_box.setText(f"[Error] reflectprog failed:\n{result.stderr}")
            return

        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(result.stdout)
        self.last_stdout_path = output_filename
        self.output_box.append("reflectprog completed. Parsing output table…")

        # Parse numeric lines to CSV
        lines = result.stdout.strip().split("\n")
        data_lines = [ln for ln in lines if ln and all(c in "0123456789.eE+- \t" for c in ln)]
        if data_lines:
            with open(csv_filename, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)
                for ln in data_lines:
                    writer.writerow(ln.split())
            self.output_box.append(f"Saved CSV: {csv_filename}")

            y_idx = 1 if self.plot_column.currentText().startswith("R_p") else 2
            self.render_with_external(csv_filename, y_idx)
        else:
            self.output_box.append("[Warn] No numeric data lines found in stdout.")
            self.clear_plot()
