import os
import csv
import re
import datetime
import subprocess
from scatmech_paths import (
    configure_scatmech_path,
    find_solver_executable,
    format_missing_solver_message,
    get_data_dir,
)
from reflectplot import plot_csv as plot_reflect_csv
from PyQt5.QtWidgets import (
    QWidget, QLabel, QLineEdit,
    QVBoxLayout, QHBoxLayout,
    QPushButton, QComboBox,
    QTextEdit, QGroupBox,
    QFormLayout,
    QTableWidget, QTableWidgetItem,
    QSizePolicy, QMessageBox, QDialog
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
        self.run_btn = QPushButton("Run ReflectProg")
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
        self.plot_column.currentTextChanged.connect(self._on_plot_column_changed)

        # State
        self.last_stdout_path = None
        self.last_input_path = None
        self.last_csv_path = None

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
        self.output_box.append("Plot cleared.")

    def open_last_output(self):
        data_dir = str(get_data_dir())
        path = getattr(self, "last_csv_path", None)
        if not path or not os.path.exists(path):
            path = self._find_latest("reflect_output_", data_dir, suffix=".csv")
        if not path:
            self.output_box.append("No Reflect output file found in DATA.")
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
            with open(path, newline="", encoding="utf-8") as handle:
                rows = list(csv.reader(handle))
            if not rows:
                txt.setPlainText("(Empty CSV)")
            else:
                width = max(len(row) for row in rows)
                table.setColumnCount(width)
                table.setRowCount(len(rows))
                table.setHorizontalHeaderLabels([f"C{index + 1}" for index in range(width)])
                for row_index, row in enumerate(rows):
                    for col_index, value in enumerate(row):
                        table.setItem(row_index, col_index, QTableWidgetItem(value))
                table.setSortingEnabled(True)
                table.resizeColumnsToContents()
                stdout_path = getattr(self, "last_stdout_path", None)
                if stdout_path and os.path.exists(stdout_path):
                    txt.setPlainText(self._read_file(stdout_path))
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
            path = self._find_latest("reflect_input_", data_dir)
        if not path:
            self.output_box.append("No Reflect input file found in DATA.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Input: {os.path.basename(path)}")
        layout = QVBoxLayout(dlg)
        view = QTextEdit(dlg)
        view.setReadOnly(True)
        view.setPlainText(self._read_file(path))
        layout.addWidget(view)
        btn_row = QHBoxLayout()
        close_btn = QPushButton("Close", dlg)
        btn_row.addStretch(1)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        close_btn.clicked.connect(dlg.accept)
        dlg.resize(700, 500)
        dlg.exec_()

    def _find_latest(self, prefix: str, folder: str, suffix: str = ".txt"):
        try:
            paths = [
                os.path.join(folder, filename)
                for filename in os.listdir(folder)
                if filename.startswith(prefix) and filename.endswith(suffix)
            ]
            if not paths:
                return None
            return max(paths, key=lambda path: os.path.getmtime(path))
        except Exception:
            return None

    def _read_file(self, path: str):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                return handle.read()
        except Exception as exc:
            return f"(Could not open file: {exc})"

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
        ax = self.figure.add_subplot(111)
        self.last_csv_path = csv_path

        try:
            label = "Rp" if y_idx == 1 else ("Rs" if y_idx == 2 else None)
            plot_reflect_csv(ax, csv_path, x_col=0, y_col=y_idx, semilogy=False, label=label)
            self.canvas.draw()
            self.output_box.append("Plot updated.")
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
            self.last_csv_path = csv_filename
            self.output_box.append(f"Saved CSV: {csv_filename}")

            y_idx = 1 if self.plot_column.currentText().startswith("R_p") else 2
            self.render_with_external(csv_filename, y_idx)
        else:
            self.output_box.append("[Warn] No numeric data lines found in stdout.")
            self.clear_plot()

    def _on_plot_column_changed(self, _text: str):
        csv_path = getattr(self, "last_csv_path", None)
        if not csv_path or not os.path.exists(csv_path):
            return
        y_idx = 1 if self.plot_column.currentText().startswith("R_p") else 2
        self.render_with_external(csv_path, y_idx)

    def to_params(self) -> dict:
        layers = []
        for row in range(self.tbl.rowCount()):
            material = self.tbl.item(row, 0)
            thickness = self.tbl.item(row, 1)
            if material is None or thickness is None:
                continue
            layers.append(
                {
                    "material": material.text().strip(),
                    "thickness_um": thickness.text().strip(),
                }
            )
        return {
            "wavelength_um": self.wavelength.text().strip(),
            "substrate": {
                "n": self.sub_n.text().strip(),
                "k": self.sub_k.text().strip(),
            },
            "layers": layers,
            "plot_y": self.plot_column.currentText(),
        }

    def from_params(self, params: dict):
        if not params:
            return
        self.wavelength.setText(str(params.get("wavelength_um", self.wavelength.text())))
        substrate = params.get("substrate") or {}
        if isinstance(substrate, dict):
            if "n" in substrate:
                self.sub_n.setText(str(substrate["n"]))
            if "k" in substrate:
                self.sub_k.setText(str(substrate["k"]))

        while self.tbl.rowCount() > 0:
            self.tbl.removeRow(0)
        for layer in params.get("layers", []):
            if not isinstance(layer, dict):
                continue
            self._add_layer(
                default_material=str(layer.get("material", "(1.50,0.00)")),
                default_thickness=str(layer.get("thickness_um", "0.100000")),
            )

        plot_y = params.get("plot_y")
        if plot_y:
            index = self.plot_column.findText(str(plot_y))
            if index >= 0:
                self.plot_column.setCurrentIndex(index)
