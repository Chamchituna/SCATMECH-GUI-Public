import os
import csv
import datetime
import math
import subprocess
from pathlib import Path
import re
import json
from scatmech_paths import (
    configure_scatmech_path,
    find_solver_executable,
    format_missing_solver_message,
    get_data_dir,
)
from brdfplot import plot_csv as plot_brdf_csv
from scatmech_gratings import (
    CROSS_GRATING_SPECS,
    ONE_D_GRATING_SPECS,
    build_default_cross_grating,
    build_default_one_d_grating,
    coerce_cross_grating,
    coerce_one_d_grating,
    list_cross_grating_models,
    serialize_cross_grating,
    serialize_one_d_grating,
    validate_cross_grating,
    validate_one_d_grating,
)

from PyQt5.QtWidgets import (
    QWidget, QLabel, QLineEdit,
    QVBoxLayout, QHBoxLayout,
    QPushButton, QComboBox,
    QTextEdit, QGroupBox,
    QFormLayout, QFileDialog,
    QSizePolicy
)
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

configure_scatmech_path()


class OneDGratingEditor(QWidget):
    def __init__(self, *, title: str = "1D Grating", parent=None):
        super().__init__(parent)
        self._value_store = {}
        self.param_inputs = {}
        self._current_model = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.group = QGroupBox(title)
        self.group_layout = QFormLayout()
        self.group.setLayout(self.group_layout)
        outer.addWidget(self.group)

        self.model_combo = QComboBox()
        for name in ONE_D_GRATING_SPECS:
            self.model_combo.addItem(name)
        self.group_layout.addRow("Model:", self.model_combo)

        self.fields_container = QWidget()
        self.fields_layout = QFormLayout()
        self.fields_container.setLayout(self.fields_layout)
        self.group_layout.addRow(self.fields_container)

        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        initial_model = self.model_combo.currentText() or next(iter(ONE_D_GRATING_SPECS))
        self._rebuild_fields(initial_model)

    def _clear_fields(self):
        while self.fields_layout.count():
            item = self.fields_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.param_inputs = {}

    def _add_param_row(self, field, value: str):
        name = field["name"]
        line_edit = QLineEdit()
        line_edit.setText(value)
        self.param_inputs[name] = line_edit
        if name == "filename":
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(line_edit)
            browse_btn = QPushButton("Browse...")
            browse_btn.clicked.connect(lambda: self._browse_for_file(name))
            row_layout.addWidget(browse_btn)
            self.fields_layout.addRow(f"{field['label']}:", row_widget)
        else:
            self.fields_layout.addRow(f"{field['label']}:", line_edit)

    def _browse_for_file(self, field_name: str):
        fname, _ = QFileDialog.getOpenFileName(self, "Select grating file", "", "All Files (*)")
        if fname:
            widget = self.param_inputs.get(field_name)
            if widget is not None:
                widget.setText(fname)

    def _store_current_state(self):
        if self._current_model:
            self._value_store[self._current_model] = self.to_node()

    def _rebuild_fields(self, model_name: str, node=None):
        if model_name not in ONE_D_GRATING_SPECS:
            model_name = next(iter(ONE_D_GRATING_SPECS))
        self._clear_fields()
        state = node if node is not None else self._value_store.get(model_name)
        coerced = coerce_one_d_grating(state, default_model=model_name)
        self._current_model = coerced["model"]
        self._value_store[self._current_model] = coerced
        for field in ONE_D_GRATING_SPECS[self._current_model]["fields"]:
            self._add_param_row(field, coerced["params"][field["name"]])

    def _on_model_changed(self, model_name: str):
        self._store_current_state()
        self._rebuild_fields(model_name)

    def to_node(self):
        model = self.model_combo.currentText() or self._current_model or next(iter(ONE_D_GRATING_SPECS))
        params = {}
        for field in ONE_D_GRATING_SPECS[model]["fields"]:
            widget = self.param_inputs.get(field["name"])
            value = widget.text().strip() if widget is not None else field["default"]
            params[field["name"]] = value if value else field["default"]
        return {
            "kind": "grating",
            "model": model,
            "params": params,
        }

    def from_node(self, node):
        coerced = coerce_one_d_grating(node)
        self._value_store[coerced["model"]] = coerced
        idx = self.model_combo.findText(coerced["model"])
        if idx >= 0:
            previous = self.model_combo.blockSignals(True)
            self.model_combo.setCurrentIndex(idx)
            self.model_combo.blockSignals(previous)
        self._rebuild_fields(coerced["model"], node=coerced)


class CrossGratingEditor(QWidget):
    def __init__(self, *, title: str = "Cross Grating", allow_overlay: bool = True, parent=None):
        super().__init__(parent)
        self.allow_overlay = allow_overlay
        self._value_store = {}
        self._current_model = ""
        self.param_inputs = {}
        self.child_editors = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.group = QGroupBox(title)
        self.group_layout = QFormLayout()
        self.group.setLayout(self.group_layout)
        outer.addWidget(self.group)

        self.model_combo = QComboBox()
        for name in list_cross_grating_models(allow_overlay=allow_overlay):
            self.model_combo.addItem(name)
        self.group_layout.addRow("Model:", self.model_combo)

        self.fields_container = QWidget()
        self.fields_layout = QFormLayout()
        self.fields_container.setLayout(self.fields_layout)
        self.group_layout.addRow(self.fields_container)

        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        initial_model = self.model_combo.currentText() or next(iter(CROSS_GRATING_SPECS))
        self._rebuild_fields(initial_model)

    def _clear_fields(self):
        while self.fields_layout.count():
            item = self.fields_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.param_inputs = {}
        self.child_editors = {}

    def _add_param_row(self, field, value: str):
        name = field["name"]
        line_edit = QLineEdit()
        line_edit.setText(value)
        self.param_inputs[name] = line_edit
        if name == "filename":
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(line_edit)
            browse_btn = QPushButton("Browse...")
            browse_btn.clicked.connect(lambda: self._browse_for_file(name))
            row_layout.addWidget(browse_btn)
            self.fields_layout.addRow(f"{field['label']}:", row_widget)
        else:
            self.fields_layout.addRow(f"{field['label']}:", line_edit)

    def _browse_for_file(self, field_name: str):
        fname, _ = QFileDialog.getOpenFileName(self, "Select grating file", "", "All Files (*)")
        if fname:
            widget = self.param_inputs.get(field_name)
            if widget is not None:
                widget.setText(fname)

    def _store_current_state(self):
        if self._current_model:
            self._value_store[self._current_model] = self.to_node()

    def _rebuild_fields(self, model_name: str, node=None):
        choices = list_cross_grating_models(allow_overlay=self.allow_overlay)
        if model_name not in choices:
            model_name = choices[0]
        self._clear_fields()
        state = node if node is not None else self._value_store.get(model_name)
        coerced = coerce_cross_grating(state, allow_overlay=self.allow_overlay, default_model=model_name)
        self._current_model = coerced["model"]
        self._value_store[self._current_model] = coerced
        for field in CROSS_GRATING_SPECS[self._current_model]["fields"]:
            if field["kind"] == "param":
                self._add_param_row(field, coerced["params"][field["name"]])
                continue
            child_name = field["name"]
            child_value = coerced["children"][child_name]
            if field["child_kind"] == "one_d":
                editor = OneDGratingEditor(title=field["label"])
                editor.from_node(child_value)
            else:
                editor = CrossGratingEditor(title=field["label"], allow_overlay=False)
                editor.from_node(child_value)
            self.child_editors[child_name] = editor
            self.fields_layout.addRow(editor)

    def _on_model_changed(self, model_name: str):
        self._store_current_state()
        self._rebuild_fields(model_name)

    def to_node(self):
        choices = list_cross_grating_models(allow_overlay=self.allow_overlay)
        fallback = choices[0] if choices else "OneD_CrossGrating"
        model = self.model_combo.currentText() or self._current_model or fallback
        params = {}
        children = {}
        for field in CROSS_GRATING_SPECS[model]["fields"]:
            if field["kind"] == "param":
                widget = self.param_inputs.get(field["name"])
                value = widget.text().strip() if widget is not None else field["default"]
                params[field["name"]] = value if value else field["default"]
                continue
            editor = self.child_editors.get(field["name"])
            if editor is not None:
                children[field["name"]] = editor.to_node()
        return {
            "kind": "cross",
            "model": model,
            "params": params,
            "children": children,
        }

    def from_node(self, node):
        coerced = coerce_cross_grating(node, allow_overlay=self.allow_overlay)
        self._value_store[coerced["model"]] = coerced
        idx = self.model_combo.findText(coerced["model"])
        if idx >= 0:
            previous = self.model_combo.blockSignals(True)
            self.model_combo.setCurrentIndex(idx)
            self.model_combo.blockSignals(previous)
        self._rebuild_fields(coerced["model"], node=coerced)


class BRDFForm(QWidget):

    DIRECTION_CODES = {
        "Forward Reflection": "0",
        "Forward Transmission": "1",
        "Backward Reflection": "2",
        "Backward Transmission": "3",
    }
    
    def __init__(self):
        super().__init__()

        # ===== Main layout =====
        self.main_layout = QHBoxLayout(self)
        self.setLayout(self.main_layout)

        # Left: form
        self.form_layout = QVBoxLayout()
        form_widget = QWidget()
        form_widget.setLayout(self.form_layout)

        # Right: matplotlib canvas
        self.figure = Figure(figsize=(6, 5), tight_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        plot_layout = QVBoxLayout()
        plot_layout.addWidget(self.canvas, 1)
        plot_widget = QWidget()
        plot_widget.setLayout(plot_layout)

        self.main_layout.addWidget(form_widget, 1)
        self.main_layout.addWidget(plot_widget, 1)

        # ===== Angular parameters =====
        angles_group = QGroupBox("Angular Parameters")
        angle_layout = QFormLayout()
        self.incident_angle = QLineEdit("45")
        self.scatter_start = QLineEdit("45")
        self.scatter_end = QLineEdit("45")
        self.scatter_step = QLineEdit("1")
        self.azimuth_start = QLineEdit("0")
        self.azimuth_end = QLineEdit("180")
        self.azimuth_step = QLineEdit("2")
        angle_layout.addRow("Incident Angle (°):", self.incident_angle)
        angle_layout.addRow("Scattering Start (°):", self.scatter_start)
        angle_layout.addRow("Scattering End (°):", self.scatter_end)
        angle_layout.addRow("Scattering Step (°):", self.scatter_step)
        angle_layout.addRow("Azimuth Start (°):", self.azimuth_start)
        angle_layout.addRow("Azimuth End (°):", self.azimuth_end)
        angle_layout.addRow("Azimuth Step (°):", self.azimuth_step)
        angles_group.setLayout(angle_layout)
        self.form_layout.addWidget(angles_group)

        # ===== Model selection =====
        model_group = QGroupBox("Model Selection")
        model_layout = QFormLayout()
        self.family_selector = QComboBox()
        self.family_selector.addItems([
            "Roughness_BRDF_Model", "Facet_BRDF_Model", "Lambertian_BRDF_Model",
            "Local_BRDF_Model", "Instrument_BRDF_Model", "First_Diffuse_BRDF_Model",
            "Two_Source_BRDF_Model", "Three_Source_BRDF_Model", "Four_Source_BRDF_Model",
            "Transmit_BRDF_Model", "RCW_BRDF_Model",
            "ZernikeExpansion_BRDF_Model", "Polydisperse_Sphere_BRDF_Model",
        ])
        self.subclass_selector = QComboBox()

        self.subclass_selector.currentTextChanged.connect(self._on_model_changed)
        self.family_selector.currentTextChanged.connect(self.update_subclasses)
        model_layout.addRow("Model Family:", self.family_selector)
        model_layout.addRow("Model Type:", self.subclass_selector)
        model_group.setLayout(model_layout)
        self.form_layout.addWidget(model_group)

        # ===== Wavelength & substrate =====
        param_group = QGroupBox("Model Parameters")
        param_layout = QFormLayout()
        self.wavelength = QLineEdit("0.532")
        self.substrate = QLineEdit("(4.05,0.05)")
        self.direction = QComboBox()
        self.direction.addItem("Forward Reflection")

        param_layout.addRow("Wavelength (µm):", self.wavelength)
        param_layout.addRow("Substrate (n or file):", self.substrate)
        param_layout.addRow("Direction:", self.direction)
        param_group.setLayout(param_layout)
        self.form_layout.addWidget(param_group)

        # ===== Auto parameters for selected model =====
        self.model_params_group = QGroupBox("Selected Model Parameters")
        self.model_params_layout = QFormLayout()
        self.model_params_group.setLayout(self.model_params_layout)
        self.form_layout.addWidget(self.model_params_group)
        # Populate once the params UI exists
        self.update_subclasses()
        self.subclass_selector.currentTextChanged.connect(self.populate_model_params)
        self.direction.currentTextChanged.connect(self._on_direction_changed)

        # ===== PSD selector and parameter widgets =====
        self.psd_group = QGroupBox("PSD Function")
        psd_layout = QVBoxLayout()

        self.psd_function = QComboBox()
        self.psd_function.addItems([
            "Unit_PSD_Function", "ABC_PSD_Function", "Fractal_PSD_Function",
            "Gaussian_PSD_Function", "Elliptical_Mesa_PSD_Function",
            "Rectangular_Mesa_PSD_Function", "Triangular_Mesa_PSD_Function",
            "Rectangular_Pyramid_PSD_Function", "Triangular_Pyramid_PSD_Function",
            "Parabolic_Dimple_PSD_Function",
        ])
        self.psd_function.currentTextChanged.connect(self.update_psd_parameters)
        psd_layout.addWidget(self.psd_function)

        # --- Unit (no parameters)
        self.psd_param_unit = QWidget()
        self.psd_param_unit.setLayout(QFormLayout())

        # --- ABC
        self.psd_param_abc = QWidget()
        abc_layout = QFormLayout()
        self.psd_A = QLineEdit("0.01")
        self.psd_B = QLineEdit("362")
        self.psd_C = QLineEdit("2.5")
        abc_layout.addRow("A [µm⁴]:", self.psd_A)
        abc_layout.addRow("B [µm]:", self.psd_B)
        abc_layout.addRow("C [-]:", self.psd_C)
        self.psd_param_abc.setLayout(abc_layout)

        # --- Fractal
        self.psd_param_fractal = QWidget()
        fractal_layout = QFormLayout()
        self.psd_fractalAmp = QLineEdit("0.01")   # A [µm^4]
        self.psd_fractalExp = QLineEdit("2.5")    # exponent γ [-]
        fractal_layout.addRow("Amplitude A [µm⁴]:", self.psd_fractalAmp)
        fractal_layout.addRow("Exponent γ [-]:", self.psd_fractalExp)
        self.psd_param_fractal.setLayout(fractal_layout)

        # --- Gaussian
        self.psd_param_gaussian = QWidget()
        gaussian_layout = QFormLayout()
        self.psd_sigma = QLineEdit("0.05")
        self.psd_lc = QLineEdit("5")
        gaussian_layout.addRow("Std. Dev. σ [µm]:", self.psd_sigma)
        gaussian_layout.addRow("Correlation Lc [µm]:", self.psd_lc)
        self.psd_param_gaussian.setLayout(gaussian_layout)

        # --- Elliptical Mesa
        self.psd_param_elliptical_mesa = QWidget()
        el_layout = QFormLayout()
        self.psd_ellipticalX = QLineEdit("1.5")
        self.psd_ellipticalY = QLineEdit("1.5")
        self.psd_mesaHeight = QLineEdit("0.01")
        self.psd_mesaDensity = QLineEdit("0.01")
        el_layout.addRow("X-axis [µm]:", self.psd_ellipticalX)
        el_layout.addRow("Y-axis [µm]:", self.psd_ellipticalY)
        el_layout.addRow("Height [µm]:", self.psd_mesaHeight)
        el_layout.addRow("Density [µm⁻²]:", self.psd_mesaDensity)
        self.psd_param_elliptical_mesa.setLayout(el_layout)

        # --- Rectangular Mesa
        self.psd_param_rectangular_mesa = QWidget()
        rm_layout = QFormLayout()
        self.psd_rectLenX = QLineEdit("1.5")
        self.psd_rectLenY = QLineEdit("1.5")
        self.psd_rectHeight = QLineEdit("0.01")
        self.psd_rectDensity = QLineEdit("0.01")
        rm_layout.addRow("Length X [µm]:", self.psd_rectLenX)
        rm_layout.addRow("Length Y [µm]:", self.psd_rectLenY)
        rm_layout.addRow("Height [µm]:", self.psd_rectHeight)
        rm_layout.addRow("Density [µm⁻²]:", self.psd_rectDensity)
        self.psd_param_rectangular_mesa.setLayout(rm_layout)

        # --- Triangular Mesa
        self.psd_param_triangular_mesa = QWidget()
        tm_layout = QFormLayout()
        self.psd_triSide = QLineEdit("1.5")
        self.psd_triHeight = QLineEdit("0.01")
        self.psd_triDensity = QLineEdit("0.01")
        tm_layout.addRow("Side [µm]:", self.psd_triSide)
        tm_layout.addRow("Height [µm]:", self.psd_triHeight)
        tm_layout.addRow("Density [µm⁻²]:", self.psd_triDensity)
        self.psd_param_triangular_mesa.setLayout(tm_layout)

        # --- Rectangular Pyramid
        self.psd_param_rectangular_pyramid = QWidget()
        rp_layout = QFormLayout()
        self.psd_pyrLenX = QLineEdit("1.5")
        self.psd_pyrLenY = QLineEdit("1.5")
        self.psd_pyrHeight = QLineEdit("0.01")
        self.psd_pyrDensity = QLineEdit("0.01")
        rp_layout.addRow("Base Length X [µm]:", self.psd_pyrLenX)
        rp_layout.addRow("Base Length Y [µm]:", self.psd_pyrLenY)
        rp_layout.addRow("Height [µm]:", self.psd_pyrHeight)
        rp_layout.addRow("Density [µm⁻²]:", self.psd_pyrDensity)
        self.psd_param_rectangular_pyramid.setLayout(rp_layout)

        # --- Triangular Pyramid
        self.psd_param_triangular_pyramid = QWidget()
        tp_layout = QFormLayout()
        self.psd_tpSide = QLineEdit("1.5")
        self.psd_tpHeight = QLineEdit("0.01")
        self.psd_tpDensity = QLineEdit("0.01")
        tp_layout.addRow("Base Side [µm]:", self.psd_tpSide)
        tp_layout.addRow("Height [µm]:", self.psd_tpHeight)
        tp_layout.addRow("Density [µm⁻²]:", self.psd_tpDensity)
        self.psd_param_triangular_pyramid.setLayout(tp_layout)

        # --- Parabolic Dimple
        self.psd_param_parabolic_dimple = QWidget()
        pd_layout = QFormLayout()
        self.psd_pdAxisX = QLineEdit("1.5")
        self.psd_pdAxisY = QLineEdit("1.5")
        self.psd_pdHeight = QLineEdit("0.01")
        self.psd_pdDensity = QLineEdit("0.01")
        pd_layout.addRow("Axis X [µm]:", self.psd_pdAxisX)
        pd_layout.addRow("Axis Y [µm]:", self.psd_pdAxisY)
        pd_layout.addRow("Height [µm]:", self.psd_pdHeight)
        pd_layout.addRow("Density [µm⁻²]:", self.psd_pdDensity)
        self.psd_param_parabolic_dimple.setLayout(pd_layout)

        # Add all PSD parameter widgets, hidden by default
        for w in [
            self.psd_param_unit, self.psd_param_abc, self.psd_param_fractal,
            self.psd_param_gaussian, self.psd_param_elliptical_mesa,
            self.psd_param_rectangular_mesa, self.psd_param_triangular_mesa,
            self.psd_param_rectangular_pyramid, self.psd_param_triangular_pyramid,
            self.psd_param_parabolic_dimple,
        ]:
            w.hide()
            psd_layout.addWidget(w)

        self.psd_group.setLayout(psd_layout)
        self.form_layout.addWidget(self.psd_group)

        # ===== Controls =====
        ctrl_row = QHBoxLayout()
        self.run_btn = QPushButton("Run BRDFProg")
        self.clear_btn = QPushButton("Clear Plot")
        ctrl_row.addWidget(self.run_btn)
        ctrl_row.addWidget(self.clear_btn)
        self.open_output_btn = QPushButton("Open Last Output")
        self.open_input_btn = QPushButton("Open Last Input")
        ctrl_row.addWidget(self.open_output_btn)
        ctrl_row.addWidget(self.open_input_btn)
        self.form_layout.addLayout(ctrl_row)

        # Output log
        self.output_box = QTextEdit()
        self.output_box.setReadOnly(True)
        self.form_layout.addWidget(QLabel("Log:"))
        self.form_layout.addWidget(self.output_box)

        # Wire signals
        self.run_btn.clicked.connect(self.run_brdfprog)
        self.clear_btn.clicked.connect(self.clear_plot)
        self.open_output_btn.clicked.connect(self.open_last_output)
        self.open_input_btn.clicked.connect(self.open_last_input)
        
        # Keep shared parameter fields 
        self.wavelength.textChanged.connect(
            lambda txt: self._sync_general_to_model("lambda", txt)
        )
        self.substrate.textChanged.connect(
            lambda txt: self._sync_general_to_model("substrate", txt)
        )

        # Initialize selectors
        self.update_subclasses()
        self.update_psd_parameters(self.psd_function.currentText())

        # State for last I/O paths
        self.last_stdout_path = None
        self.last_input_path = None
        self.last_csv_path = None
        self.last_output_meta = None
        self.rcw_grating_editor = None
        self._rcw_grating_state = build_default_one_d_grating()
        self.cross_grating_editor = None
        self._cross_grating_state = build_default_cross_grating()

    # ===== Helpers =====
    def clear_plot(self):
        self.figure.clear()
        self.canvas.draw()
        self.output_box.append("Plot cleared.")

    
    def update_subclasses(self):
        """Populate the 'Model Type' combo based on the selected family,
        matching the NIST SCATMECH class list. When a family has no subclasses
        (i.e., it is itself a concrete model), we show the family name as the
        only selectable entry so downstream code can read a model name either
        from subclass_selector or family_selector consistently.
        All names use underscores instead of spaces.
        """
        subclasses = {
            # --- Roughness models
            "Roughness_BRDF_Model": [
                "Microroughness_BRDF_Model",
                "Correlated_Roughness_BRDF_Model",
                "Two_Face_BRDF_Model",
                "Roughness_Stack_BRDF_Model",
                "Correlated_Roughness_Stack_BRDF_Model",
                "Uncorrelated_Roughness_Stack_BRDF_Model",
                "Growth_Roughness_Stack_BRDF_Model",
            ],
            # --- Facet models
            "Facet_BRDF_Model": [
                "Shadowed_Facet_BRDF_Model",
                "Subsurface_Facet_BRDF_Model",
            ],
            # --- Lambertian
            "Lambertian_BRDF_Model": [
                "Lambertian_BRDF_Model",
                "Diffuse_Subsurface_BRDF_Model",
            ],
            # --- Local particle / defect models
            "Local_BRDF_Model": [
                "Rayleigh_Defect_BRDF_Model",
                "OneLayer_BRDF_Model",
                "Rayleigh_Stack_BRDF_Model",
                "Double_Interaction_BRDF_Model",
                "Bobbert_Vlieger_BRDF_Model",
                "Axisymmetric_Particle_BRDF_Model",
                "Subsurface_Bobbert_Vlieger_BRDF_Model",
                "Subsurface_Axisymmetric_Particle_BRDF_Model",
            ],
            # --- Instrument / measurement models
            "Instrument_BRDF_Model": [
                "Rayleigh_Instrument_BRDF_Model",
                "Finite_Aperture_Instrument_BRDF_Model",
                "Focussed_Beam_Instrument_BRDF_Model",
            ],
        }
        current_family = self.family_selector.currentText()
        items = subclasses.get(current_family, [])
        self.subclass_selector.clear()
        if items:
            self.subclass_selector.addItems(items)
        else:
            # Concrete/standalone model families: set to the family itself
            self.subclass_selector.addItems([current_family])

        # Update parameter form for current selection
        self.populate_model_params()

    # ---- Parameter specifications scraped from NIST docs
    MODEL_PARAM_SPECS = {
        # Roughness family
        "Microroughness_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("psd","PSD_Function_Ptr","ABC_PSD_Function"),
        ],
        "Correlated_Roughness_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("psd","PSD_Function_Ptr","ABC_PSD_Function"),
            ("film","dielectric_function","(1.46,0.05)"),
            ("thickness","double","0.05"),
        ],
        "Two_Face_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("psd","PSD_Function_Ptr","ABC_PSD_Function"),
            ("film","dielectric_function","(1.46,0)"),
            ("thickness","double","0.05"),
            ("face","int","1"),
        ],
        "Roughness_Stack_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("psd","PSD_Function_Ptr","ABC_PSD_Function"),
            ("stack","StackModel_Ptr","No_StackModel"),
            ("this_layer","int","0"),
        ],
        "Correlated_Roughness_Stack_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("psd","PSD_Function_Ptr","ABC_PSD_Function"),
            ("stack","StackModel_Ptr","No_StackModel"),
        ],
        "Uncorrelated_Roughness_Stack_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("psd","PSD_Function_Ptr","ABC_PSD_Function"),
            ("stack","StackModel_Ptr","No_StackModel"),
        ],
        "Growth_Roughness_Stack_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("psd","PSD_Function_Ptr","ABC_PSD_Function"),
            ("stack","StackModel_Ptr","No_StackModel"),
            ("intrinsic","PSD_Function_Ptr","ABC_PSD_Function"),
            ("relaxation","double","0.05"),
            ("exponent","double","2"),
        ],
        # Facet family
        "Shadowed_Facet_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("sdf","Slope_Distribution_Function","Exponential_Slope_Distribution_Function"),
            ("stack","StackModel_Ptr","No_StackModel"),
            ("shadow","Shadow_Function","Torrance_Sparrow_Shadow_Function"),
        ],
        "Subsurface_Facet_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("sdf","Slope_Distribution_Function","Exponential_Slope_Distribution_Function"),
        ],
        # Lambertian
        "Lambertian_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("reflectance","Reflectance","Table_Reflectance(1)"),
        ],
        "Diffuse_Subsurface_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("reflectance","Reflectance","Table_Reflectance(1)"),
            ("stack","StackModel_Ptr","No_StackModel"),
        ],
        # Local / defect
        "Rayleigh_Defect_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("density","double","1"),
            ("stack","StackModel_Ptr","No_StackModel"),
            ("radius","double","0.001"),
            ("distance","double","0"),
            ("defect","dielectric_function","(1.0,0.0)"),
        ],
        "OneLayer_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("density","double","1"),
            ("radius","double","0.01"),
            ("defect","dielectric_function","(1.0,0.0)"),
            ("film","dielectric_function","(1.59,0.0)"),
            ("tau","double","0.05"),
            ("depth","double","0.00"),
        ],
        "Rayleigh_Stack_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("density","double","1"),
            ("stack","StackModel_Ptr","No_StackModel"),
            ("radius","double","0.01"),
            ("sphere","dielectric_function","(1,0)"),
            ("depth","double","0"),
        ],
        "Double_Interaction_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("density","double","1"),
            ("stack","StackModel_Ptr","No_StackModel"),
            ("distance","double","0.05"),
            ("scatterer","Free_Space_Scatterer_Ptr","MieScatterer"),
            ("alpha","double","0"),
            ("beta","double","0"),
        ],
        "Subsurface_Particle_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("density","double","1"),
            ("stack","StackModel_Ptr","No_StackModel"),
            ("depth","double","0"),
            ("scatterer","Free_Space_Scatterer_Ptr","MieScatterer"),
            ("alpha","double","0"),
            ("beta","double","0"),
        ],
        "Bobbert_Vlieger_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("density","double","1"),
            ("sphere","dielectric_function","(1.59,0)"),
            ("radius","double","0.05"),
            ("spherecoat","StackModel_Ptr","No_StackModel"),
            ("stack","StackModel_Ptr","No_StackModel"),
            ("delta","double","0"),
            ("lmax","int","0"),
            ("order","int","-1"),
            ("Norm_Inc_Approx","int","0"),
        ],
        "Axisymmetric_Particle_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("density","double","1"),
            ("Shape","Axisymmetric_Shape","Ellipsoid_Axisymmetric_Shape(npoints=100,vertical=0.05,horizontal=0.05,offset=0)"),
            ("particle","dielectric_function","(1.59,0)"),
            ("stack","StackModel_Ptr","No_StackModel"),
            ("delta","double","0"),
            ("lmax","int","0"),
            ("nmax","int","0"),
            ("order","int","-1"),
            ("Norm_Inc_Approx","int","0"),
            ("improve","int","3"),
        ],
        "Subsurface_Bobbert_Vlieger_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("density","double","1"),
            ("sphere","dielectric_function","(1.59,0)"),
            ("radius","double","0.05"),
            ("spherecoat","StackModel_Ptr","No_StackModel"),
            ("stack","StackModel_Ptr","No_StackModel"),
            ("delta","double","0"),
            ("lmax","int","0"),
            ("order","int","-1"),
            ("Norm_Inc_Approx","int","0"),
            ("improve","int","3"),
        ],
        "Subsurface_Axisymmetric_Particle_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("density","double","1"),
            ("Shape","Axisymmetric_Shape","Ellipsoid_Axisymmetric_Shape(npoints=100,vertical=0.05,horizontal=0.05,offset=0)"),
            ("particle","dielectric_function","(1.59,0)"),
            ("stack","StackModel_Ptr","No_StackModel"),
            ("delta","double","0"),
            ("lmax","int","0"),
            ("nmax","int","0"),
            ("order","int","-1"),
            ("Norm_Inc_Approx","int","0"),
            ("improve","int","3"),
        ],
        # Instrument
        "Rayleigh_Instrument_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("stack","StackModel_Ptr","No_StackModel"),
            ("field_of_view","double","1000"),
            ("air","dielectric_function","(1+2784E-7,0)"),
            ("number_density","double","2.51E-7"),
        ],
        "Finite_Aperture_Instrument_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("alpha","double","0"),
            ("integralmode","int","3"),
            ("model","BRDF_Model_Ptr","Microroughness_BRDF_Model"),
        ],
        "Focussed_Beam_Instrument_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("model","BRDF_Model_Ptr","Microroughness_BRDF_Model"),
            ("alpha","double","0"),
            ("integralmode","int","3"),
            ("focal_point","double","1"),
        ],
        # Utilities
        "First_Diffuse_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("depoll","double","0"),
            ("depolc","double","0"),
            ("phase_function","Polarized_Phase_Function_Ptr","Unpolarized_Phase_Function"),
            ("stack","StackModel_Ptr","No_StackModel"),
        ],
        "Two_Source_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("factor1","double","1"),
            ("source1","BRDF_Model_Ptr","Microroughness_BRDF_Model"),
            ("factor2","double","1"),
            ("source2","BRDF_Model_Ptr","Microroughness_BRDF_Model"),
            ("correlation","double","0"),
        ],
        "Three_Source_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("factor1","double","1"),
            ("source1","BRDF_Model_Ptr","Microroughness_BRDF_Model"),
            ("factor2","double","1"),
            ("source2","BRDF_Model_Ptr","Microroughness_BRDF_Model"),
            ("factor3","double","1"),
            ("source3","BRDF_Model_Ptr","Microroughness_BRDF_Model"),
        ],
        "Four_Source_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("factor1","double","1"),
            ("source1","BRDF_Model_Ptr","Microroughness_BRDF_Model"),
            ("factor2","double","1"),
            ("source2","BRDF_Model_Ptr","Microroughness_BRDF_Model"),
            ("factor3","double","1"),
            ("source3","BRDF_Model_Ptr","Microroughness_BRDF_Model"),
            ("factor4","double","1"),
            ("source4","BRDF_Model_Ptr","Microroughness_BRDF_Model"),
        ],
        "Transmit_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("model","BRDF_Model_Ptr","Microroughness_BRDF_Model"),
            ("films","StackModel_Ptr","No_StackModel"),
        ],
        "RCW_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("alpha","double","0.0175"),
            ("order","int","25"),
            ("grating","Grating_Ptr","Single_Line_Grating"),
        ],
        "CrossRCW_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("alpha","double","0.01"),
            ("order1","int","10"),
            ("order2","int","10"),
            ("grating","CrossGrating_Ptr","OneD_CrossGrating"),
        ],
        "ZernikeExpansion_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("coefficientfile","string",""),
            ("scale","Table","1"),
        ],
        "Polydisperse_Sphere_BRDF_Model": [
            ("lambda","double","0.532"),
            ("type","int","0"),
            ("substrate","dielectric_function","(4.05,0.05)"),
            ("distribution","SurfaceParticleSizeDistribution","SurfaceParticleSizeDistribution"),
            ("stack","StackModel_Ptr","No_StackModel"),
            ("particle","dielectric_function","(1.5,0.0)"),
            ("Dstart","double","0.1"),
            ("Dend","double","100"),
            ("Dstep","double","0.01"),
            ("fractional_coverage","double","0"),
            ("antirainbow","double","0"),
        ],
    }

    def populate_model_params(self):
        """Rebuild parameter widgets when model selection changes."""
        existing_rcw_editor = getattr(self, "rcw_grating_editor", None)
        if existing_rcw_editor is not None:
            try:
                self._rcw_grating_state = existing_rcw_editor.to_node()
            except Exception:
                pass
        self.rcw_grating_editor = None

        existing_editor = getattr(self, "cross_grating_editor", None)
        if existing_editor is not None:
            try:
                self._cross_grating_state = existing_editor.to_node()
            except Exception:
                pass
        self.cross_grating_editor = None

        # Clear existing rows
        while self.model_params_layout.count():
            item = self.model_params_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        model = self.subclass_selector.currentText() or self.family_selector.currentText()
        specs = self.MODEL_PARAM_SPECS.get(model, [])
        self.param_widgets = {}
        for name, dtype, default in specs:
            # Skip PSD pointer here; PSD is configured in the dedicated PSD section
            if name.lower() == "psd" or dtype == "PSD_Function_Ptr":
                continue
            if model == "RCW_BRDF_Model" and dtype == "Grating_Ptr" and name == "grating":
                editor = OneDGratingEditor(title="1D Grating")
                editor.from_node(getattr(self, "_rcw_grating_state", build_default_one_d_grating()))
                self.rcw_grating_editor = editor
                self.model_params_layout.addRow(editor)
                continue
            if model == "CrossRCW_BRDF_Model" and dtype == "CrossGrating_Ptr" and name == "grating":
                editor = CrossGratingEditor(title="Cross Grating")
                editor.from_node(getattr(self, "_cross_grating_state", build_default_cross_grating()))
                self.cross_grating_editor = editor
                self.model_params_layout.addRow(editor)
                continue

            self._add_model_param_row(
                name,
                dtype,
                str(default),
                browse=name in {"coefficientfile"},
            )

            lowered = name.lower()
            if lowered == "lambda":
                self.param_widgets[name].setText(self.wavelength.text())
            elif lowered == "substrate":
                self.param_widgets[name].setText(self.substrate.text())
            elif lowered == "type":
                self.param_widgets[name].setText(self.DIRECTION_CODES.get(self.direction.currentText(), str(default)))

    def _add_model_param_row(self, name: str, dtype: str, value: str, *, browse: bool = False):
        line_edit = QLineEdit()
        line_edit.setText(value)
        self.param_widgets[name] = line_edit
        label = f"{name} ({dtype}):"

        if not browse:
            self.model_params_layout.addRow(label, line_edit)
            return

        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(line_edit)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(lambda: self._browse_for_model_file(name))
        row_layout.addWidget(browse_btn)
        self.model_params_layout.addRow(label, row_widget)

    def _browse_for_model_file(self, field_name: str):
        title = "Select file"
        if field_name == "coefficientfile":
            title = "Select coefficient file"
        fname, _ = QFileDialog.getOpenFileName(self, title, "", "All Files (*)")
        if not fname:
            return
        widget = self.param_widgets.get(field_name)
        if widget is not None:
            widget.setText(fname)

    def update_psd_parameters(self, current: str):
        mapping = {
            "Unit_PSD_Function": self.psd_param_unit,
            "ABC_PSD_Function": self.psd_param_abc,
            "Fractal_PSD_Function": self.psd_param_fractal,
            "Gaussian_PSD_Function": self.psd_param_gaussian,
            "Elliptical_Mesa_PSD_Function": self.psd_param_elliptical_mesa,
            "Rectangular_Mesa_PSD_Function": self.psd_param_rectangular_mesa,
            "Triangular_Mesa_PSD_Function": self.psd_param_triangular_mesa,
            "Rectangular_Pyramid_PSD_Function": self.psd_param_rectangular_pyramid,
            "Triangular_Pyramid_PSD_Function": self.psd_param_triangular_pyramid,
            "Parabolic_Dimple_PSD_Function": self.psd_param_parabolic_dimple,
        }
        for w in mapping.values():
            w.hide()
        widget = mapping.get(current)
        if widget is not None:
            widget.show()
            
    def _sync_general_to_model(self, name: str, text: str):
        widget = getattr(self, "param_widgets", {}).get(name)
        if widget is not None and widget.text() != text:
            widget.setText(text)

    def _on_direction_changed(self, selection: str):
        value = self.DIRECTION_CODES.get(selection)
        if value is None:
            return
        widget = getattr(self, "param_widgets", {}).get("type")
        if widget is not None and widget.text() != value:
            widget.setText(value)

    def _current_model_name(self) -> str:
        return self.subclass_selector.currentText() or self.family_selector.currentText()

    def _current_model_specs(self):
        return self.MODEL_PARAM_SPECS.get(self._current_model_name(), [])

    def _collect_model_params(self) -> dict:
        model = self._current_model_name()
        specs = self.MODEL_PARAM_SPECS.get(model, [])
        params = {}
        for name, dtype, default in specs:
            lowered = name.lower()
            if lowered in {"psd", "lambda", "substrate", "type"}:
                continue
            if model == "RCW_BRDF_Model" and dtype == "Grating_Ptr" and name == "grating":
                continue
            if model == "CrossRCW_BRDF_Model" and dtype == "CrossGrating_Ptr" and name == "grating":
                continue
            widget = self.param_widgets.get(name)
            if widget is None:
                continue
            text = widget.text().strip()
            params[name] = text if text else str(default)
        return params

    def _current_cross_grating_tree(self):
        editor = getattr(self, "cross_grating_editor", None)
        if editor is not None:
            tree = editor.to_node()
            self._cross_grating_state = tree
            return tree
        return getattr(self, "_cross_grating_state", build_default_cross_grating())

    def _current_rcw_grating_tree(self):
        editor = getattr(self, "rcw_grating_editor", None)
        if editor is not None:
            tree = editor.to_node()
            self._rcw_grating_state = tree
            return tree
        return getattr(self, "_rcw_grating_state", build_default_one_d_grating())

    def _append_cross_rcw_input_lines(self, input_lines, *, model_params=None, grating_tree=None):
        params = dict(model_params or {})
        alpha = str(params.get("alpha", "0.01") or "0.01")
        order1 = str(params.get("order1", "10") or "10")
        order2 = str(params.get("order2", "10") or "10")
        tree = grating_tree if grating_tree is not None else self._current_cross_grating_tree()
        errors = validate_cross_grating(tree)
        if errors:
            raise ValueError("Cross grating validation failed:\n- " + "\n- ".join(errors))
        input_lines.extend([alpha, order1, order2])
        input_lines.extend(serialize_cross_grating(tree))
        self._cross_grating_state = tree
            
    # ===== External plot helper =====
    def render_with_external(self, csv_path: str, *, x_col: int = None, y_col: int = None, semilogy: bool = True):
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        meta = getattr(self, "last_output_meta", None)
        if not meta or meta.get("csv_path") != csv_path:
            meta = self._load_output_meta(csv_path)
        if meta:
            self.last_output_meta = meta

        try:
            try:
                plot_brdf_csv(ax, csv_path, x_col=x_col, y_col=y_col, semilogy=semilogy, meta=meta)
            except TypeError:
                plot_brdf_csv(ax, csv_path, x_col=x_col, y_col=y_col, semilogy=semilogy)
            self.canvas.draw()
            self.output_box.append("Plot updated.")
        except Exception as e:
            self.output_box.append(f"brdfplot render error: {e}")
            self.canvas.draw()

    def _split_top_level_args(self, text: str):
        parts = []
        token = []
        depth = 0
        for ch in text:
            if ch == "(":
                depth += 1
                token.append(ch)
            elif ch == ")":
                if depth > 0:
                    depth -= 1
                token.append(ch)
            elif ch == "," and depth == 0:
                item = "".join(token).strip()
                if item:
                    parts.append(item)
                token = []
            else:
                token.append(ch)
        item = "".join(token).strip()
        if item:
            parts.append(item)
        return parts

    def _parse_model_expression(self, text: str):
        raw = (text or "").strip()
        if not raw:
            return "", [], {}

        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*(?:\((.*)\))?\s*$", raw)
        if not m:
            return raw, [], {}

        model_name = m.group(1).strip()
        inner = m.group(2)
        if inner is None:
            return model_name, [], {}

        args = []
        kwargs = {}
        for item in self._split_top_level_args(inner):
            if "=" not in item:
                args.append(item.strip())
                continue
            key, value = item.split("=", 1)
            kwargs[key.strip().lower()] = value.strip()
        return model_name, args, kwargs

    def _raise_unsupported_parameterized_expression(self, dtype: str, value: str):
        raise ValueError(
            f"Parameterized expressions for {dtype} are not supported in the public GUI: {value}"
        )

    def _append_scatterer_input_lines(self, input_lines, value: str, model_name: str):
        scatterer_model, _args, kwargs = self._parse_model_expression(value)
        if not scatterer_model:
            scatterer_model = "MieScatterer"
        input_lines.append(scatterer_model)

        if scatterer_model != "MieScatterer":
            raise ValueError(
                f"Unsupported scatterer '{scatterer_model}'. Only MieScatterer is supported in the public GUI."
            )

        default_lambda = self.wavelength.text().strip() or "0.532"
        if model_name == "Subsurface_Particle_BRDF_Model":
            default_medium = self.substrate.text().strip() or "(1,0)"
        else:
            default_medium = "(1,0)"
        default_radius = "0.05"
        default_sphere = "(1.59,0)"

        input_lines.append(kwargs.get("lambda", default_lambda))
        input_lines.append(kwargs.get("medium", default_medium))
        input_lines.append(kwargs.get("radius", default_radius))
        input_lines.append(kwargs.get("sphere", default_sphere))

    def _append_psd_named_input_lines(self, input_lines, current: str):
        input_lines.append(current)
        if current == "Unit_PSD_Function":
            return
        if current == "ABC_PSD_Function":
            input_lines += [self.psd_A.text(), self.psd_B.text(), self.psd_C.text()]
            return
        if current == "Fractal_PSD_Function":
            input_lines += [self.psd_fractalAmp.text(), self.psd_fractalExp.text()]
            return
        if current == "Gaussian_PSD_Function":
            input_lines += [self.psd_sigma.text(), self.psd_lc.text()]
            return
        if current == "Elliptical_Mesa_PSD_Function":
            input_lines += [
                self.psd_ellipticalX.text(),
                self.psd_ellipticalY.text(),
                self.psd_mesaHeight.text(),
                self.psd_mesaDensity.text(),
            ]
            return
        if current == "Rectangular_Mesa_PSD_Function":
            input_lines += [
                self.psd_rectLenX.text(),
                self.psd_rectLenY.text(),
                self.psd_rectHeight.text(),
                self.psd_rectDensity.text(),
            ]
            return
        if current == "Triangular_Mesa_PSD_Function":
            input_lines += [self.psd_triSide.text(), self.psd_triHeight.text(), self.psd_triDensity.text()]
            return
        if current == "Rectangular_Pyramid_PSD_Function":
            input_lines += [
                self.psd_pyrLenX.text(),
                self.psd_pyrLenY.text(),
                self.psd_pyrHeight.text(),
                self.psd_pyrDensity.text(),
            ]
            return
        if current == "Triangular_Pyramid_PSD_Function":
            input_lines += [self.psd_tpSide.text(), self.psd_tpHeight.text(), self.psd_tpDensity.text()]
            return
        if current == "Parabolic_Dimple_PSD_Function":
            input_lines += [
                self.psd_pdAxisX.text(),
                self.psd_pdAxisY.text(),
                self.psd_pdHeight.text(),
                self.psd_pdDensity.text(),
            ]
            return
        raise ValueError(f"Unsupported PSD function: {current}")

    def _append_psd_input_lines(self, input_lines):
        self._append_psd_named_input_lines(input_lines, self.psd_function.currentText())

    def _append_one_d_grating_input_lines(self, input_lines, value: str = None, *, grating_tree=None):
        tree = grating_tree if grating_tree is not None else self._current_rcw_grating_tree()
        if value:
            model_name, args, kwargs = self._parse_model_expression(value)
            if args or kwargs:
                self._raise_unsupported_parameterized_expression("Grating_Ptr", value)
            if model_name:
                tree = build_default_one_d_grating(model_name)
        errors = validate_one_d_grating(tree)
        if errors:
            raise ValueError("1D grating validation failed:\n- " + "\n- ".join(errors))
        input_lines.extend(serialize_one_d_grating(tree))
        self._rcw_grating_state = tree

    def _append_reflectance_input_lines(self, input_lines, value: str):
        reflectance_model, args, kwargs = self._parse_model_expression(value)
        if not reflectance_model:
            reflectance_model = "Table_Reflectance"
        input_lines.append(reflectance_model)

        if reflectance_model != "Table_Reflectance":
            raise ValueError(
                "Only Table_Reflectance(value_or_filename) is supported in the public GUI."
            )

        reflectance_value = ""
        if args:
            reflectance_value = args[0]
        else:
            reflectance_value = kwargs.get("value") or kwargs.get("table") or "1"
        reflectance_value = str(reflectance_value).strip()
        if not reflectance_value:
            raise ValueError("Table_Reflectance requires a numeric value or filename.")
        input_lines.append(reflectance_value)

    def _append_axisymmetric_shape_input_lines(self, input_lines, value: str):
        shape_model, args, kwargs = self._parse_model_expression(value)
        if not shape_model:
            shape_model = "Ellipsoid_Axisymmetric_Shape"
        if shape_model != "Ellipsoid_Axisymmetric_Shape":
            raise ValueError(
                "Only Ellipsoid_Axisymmetric_Shape(...) is supported in the public GUI."
            )

        defaults = {
            "npoints": "100",
            "vertical": "0.05",
            "horizontal": "0.05",
            "offset": "0",
        }
        positional_names = ["npoints", "vertical", "horizontal", "offset"]
        for name, arg in zip(positional_names, args):
            defaults[name] = arg
        for key in positional_names:
            if key in kwargs:
                defaults[key] = kwargs[key]

        horizontal = self._safe_float(defaults["horizontal"])
        if horizontal is None or horizontal <= 0:
            raise ValueError("Ellipsoid_Axisymmetric_Shape requires a positive horizontal radius.")

        input_lines.append(shape_model)
        input_lines.extend([
            defaults["npoints"],
            defaults["vertical"],
            defaults["horizontal"],
            defaults["offset"],
        ])

    def _append_brdf_model_input_lines(self, input_lines, value: str, *, depth: int = 0):
        nested_model, _args, kwargs = self._parse_model_expression(value)
        if not nested_model:
            nested_model = "Microroughness_BRDF_Model"
        if depth > 4:
            raise ValueError(f"Nested BRDF model recursion is too deep near {nested_model}.")
        if nested_model in {"Subsurface_Particle_BRDF_Model", "CrossRCW_BRDF_Model"}:
            raise ValueError(f"{nested_model} is not supported in the public GUI.")
        if nested_model not in self.MODEL_PARAM_SPECS:
            raise ValueError(f"Unsupported nested BRDF model: {nested_model}")

        specs = self.MODEL_PARAM_SPECS[nested_model]
        defaults = {name.lower(): str(default) for name, _dtype, default in specs}
        input_lines.append(nested_model)
        input_lines.append(kwargs.get("lambda", self.wavelength.text().strip() or defaults.get("lambda", "0.532")))
        input_lines.append(kwargs.get("substrate", self.substrate.text().strip() or defaults.get("substrate", "(4.05,0.05)")))
        input_lines.append(kwargs.get("type", self.DIRECTION_CODES.get(self.direction.currentText(), defaults.get("type", "0"))))

        for name, dtype, default in specs:
            lowered = name.lower()
            if lowered in {"lambda", "substrate", "type"}:
                continue

            if dtype == "PSD_Function_Ptr":
                psd_value = kwargs.get(lowered, "Unit_PSD_Function")
                psd_model, psd_args, psd_kwargs = self._parse_model_expression(psd_value)
                if psd_args or psd_kwargs:
                    self._raise_unsupported_parameterized_expression(dtype, psd_value)
                self._append_psd_named_input_lines(input_lines, psd_model or "Unit_PSD_Function")
                continue

            raw_value = kwargs.get(lowered, str(default))
            self._append_param_value_input_lines(
                input_lines,
                name=name,
                dtype=dtype,
                value=raw_value,
                model_name=nested_model,
                depth=depth + 1,
            )

    def _append_param_value_input_lines(
        self,
        input_lines,
        *,
        name: str,
        dtype: str,
        value: str,
        model_name: str,
        depth: int = 0,
    ):
        if dtype == "Free_Space_Scatterer_Ptr":
            self._append_scatterer_input_lines(input_lines, value, model_name)
            return
        if dtype == "BRDF_Model_Ptr":
            self._append_brdf_model_input_lines(input_lines, value, depth=depth)
            return
        if dtype == "Reflectance":
            self._append_reflectance_input_lines(input_lines, value)
            return
        if dtype == "Axisymmetric_Shape":
            self._append_axisymmetric_shape_input_lines(input_lines, value)
            return
        if dtype == "Grating_Ptr":
            self._append_one_d_grating_input_lines(input_lines, value)
            return

        model_ptr_name, args, kwargs = self._parse_model_expression(value)
        if (args or kwargs) and dtype.endswith("_Ptr"):
            self._raise_unsupported_parameterized_expression(dtype, value)

        if name == "coefficientfile":
            coefficient_path = str(value).strip()
            if not coefficient_path:
                raise ValueError("coefficientfile is required for ZernikeExpansion_BRDF_Model.")
            if not Path(coefficient_path).exists():
                raise ValueError(f"coefficientfile does not exist: {coefficient_path}")

        input_lines.append(str(value))

    def _build_input_lines(self):
        incident = self._safe_float(self.incident_angle.text())
        scatter_step = self._safe_float(self.scatter_step.text())
        azimuth_step = self._safe_float(self.azimuth_step.text())
        if incident is None:
            raise ValueError("Incident angle must be numeric.")
        if scatter_step is None or scatter_step <= 0:
            raise ValueError("Scattering step must be a positive number.")
        if azimuth_step is None or azimuth_step <= 0:
            raise ValueError("Azimuth step must be a positive number.")

        fam = self.family_selector.currentText()
        model = self._current_model_name()
        if model in {"Subsurface_Particle_BRDF_Model", "CrossRCW_BRDF_Model"}:
            raise ValueError(f"{model} is not supported in the public GUI.")

        input_lines = [
            self.incident_angle.text(),
            self.scatter_start.text(),
            self.scatter_end.text(),
            self.scatter_step.text(),
            self.azimuth_start.text(),
            self.azimuth_end.text(),
            self.azimuth_step.text(),
            fam,
        ]
        if model and model != fam:
            input_lines.append(model)

        input_lines += [
            self.wavelength.text(),
            self.substrate.text(),
            self.DIRECTION_CODES.get(self.direction.currentText(), "0"),
        ]

        specs = self._current_model_specs()
        for name, dtype, default in specs:
            lowered = name.lower()
            if lowered in {"lambda", "substrate", "type"}:
                continue

            if model == "RCW_BRDF_Model" and dtype == "Grating_Ptr" and name == "grating":
                self._append_one_d_grating_input_lines(
                    input_lines,
                    grating_tree=self._current_rcw_grating_tree(),
                )
                continue
            if model == "CrossRCW_BRDF_Model" and dtype == "CrossGrating_Ptr" and name == "grating":
                self._append_cross_rcw_input_lines(
                    input_lines,
                    model_params=self._collect_model_params(),
                )
                return input_lines
            if dtype == "PSD_Function_Ptr":
                self._append_psd_input_lines(input_lines)
                continue

            widget = self.param_widgets.get(name)
            value = widget.text().strip() if widget is not None else str(default)
            self._append_param_value_input_lines(
                input_lines,
                name=name,
                dtype=dtype,
                value=value,
                model_name=model,
            )
        return input_lines

    # ===== Run BRDFProg =====
    def run_brdfprog(self):
        self.last_stdout_path = None
        self.last_input_path = None
        self.last_csv_path = None
        self.last_output_meta = None

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
        data_dir = get_data_dir(create=True)
        input_filename = str(data_dir / f"brdf_input_{timestamp}.txt")
        output_filename = str(data_dir / f"brdf_output_{timestamp}.txt")
        csv_filename = str(data_dir / f"brdf_output_{timestamp}.csv")

        try:
            input_lines = self._build_input_lines()
        except ValueError as e:
            self.output_box.setText(f"[Error] {e}")
            return

        try:
            with open(input_filename, "w", encoding="utf-8") as f:
                f.write("\n".join(input_lines) + "\n")

            exe = find_solver_executable("brdfprog")
            if not exe:
                self.output_box.setText(format_missing_solver_message("brdfprog"))
                return

            self.last_input_path = input_filename
            self.output_box.setText(

                f"Saved input deck: {input_filename}\nRunning BRDFProg: {exe}"
            )

            with open(input_filename, "r", encoding="utf-8") as stdin_file:
                try:
                    result = subprocess.run(
                        [exe],
                        stdin=stdin_file,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        check=False,
                    )
                except Exception as e:
                    self.output_box.setText(f"[Error] Could not invoke brdfprog: {e}")
                    return                

            if result.returncode != 0:
                self.output_box.setText(f"[Error] brdfprog failed:\n{result.stderr}" )
                return

            with open(output_filename, "w", encoding="utf-8") as f:
                f.write(result.stdout)
            self.last_stdout_path = output_filename
            self.output_box.append("brdfprog completed. Parsing output table…")

            numeric_rows = []
            finite_numeric_rows = []
            header_tokens = []
            last_text_tokens = []
            splitter = re.compile(r"[\s,]+")
            for raw_line in result.stdout.splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                tokens = [tok for tok in splitter.split(line) if tok]
                if not tokens:
                    continue
                row = []
                numeric = True
                for tok in tokens:
                    cleaned = tok.replace("D", "E").replace("d", "E")
                    try:
                        value = float(cleaned)
                    except ValueError:
                        numeric = False
                        break
                    row.append(value)
                if numeric and row:
                    numeric_rows.append(row)
                    if row and math.isfinite(row[-1]):
                        finite_numeric_rows.append(row)
                    if not header_tokens and last_text_tokens:
                        header_tokens = list(last_text_tokens)
                else:
                    last_text_tokens = list(tokens)

            if not header_tokens and last_text_tokens:
                header_tokens = list(last_text_tokens)
                
            if finite_numeric_rows:
                with open(csv_filename, "w", newline="", encoding="utf-8") as csvfile:
                    writer = csv.writer(csvfile)
                    for row in finite_numeric_rows:
                        writer.writerow(row)
                self.output_box.append(f"Saved CSV: {csv_filename}")
                self.last_csv_path = csv_filename
                dropped_rows = len(numeric_rows) - len(finite_numeric_rows)
                if dropped_rows:
                    self.output_box.append(f"Dropped {dropped_rows} non-finite rows from solver output.")
                column_count = max(len(r) for r in finite_numeric_rows)
                meta = self._build_output_meta(
                    csv_filename=csv_filename,
                    stdout_path=output_filename,
                    input_path=input_filename,
                    timestamp=timestamp,
                    header_tokens=header_tokens,
                    column_count=column_count,
                )
                if meta:
                    meta_path = csv_filename + ".meta.json"
                    try:
                        Path(meta_path).write_text(json.dumps(meta, indent=2), encoding="utf-8")
                        self.output_box.append(f"Saved metadata: {meta_path}")
                    except Exception as e:
                        self.output_box.append(f"[Warn] Could not write metadata: {e}")
                    self.last_output_meta = meta
                if header_tokens:
                    preview = ", ".join(header_tokens[:8])
                    self.output_box.append(f"Detected header tokens: {preview}")
                else:
                    self.output_box.append("No textual header detected; using numeric inference.")
                self.render_with_external(csv_filename)
            else:
                self.output_box.append("No finite numeric data detected in BRDFProg output; graph not updated.")
        except Exception as e:  
            self.output_box.setText(f"[Exception] {e}")

    def _safe_float(self, text):
        if text is None:
            return None
        try:
            return float(str(text).strip())
        except Exception:
            return None

    def _build_output_meta(
        self,
        *,
        csv_filename: str,
        stdout_path: str,
        input_path: str,
        timestamp: str,
        header_tokens,
        column_count: int,
    ) -> dict:
        scatter = {
            "incident": self._safe_float(self.incident_angle.text()),
            "scatter_start": self._safe_float(self.scatter_start.text()),
            "scatter_end": self._safe_float(self.scatter_end.text()),
            "scatter_step": self._safe_float(self.scatter_step.text()),
            "azimuth_start": self._safe_float(self.azimuth_start.text()),
            "azimuth_end": self._safe_float(self.azimuth_end.text()),
            "azimuth_step": self._safe_float(self.azimuth_step.text()),
        }

        meta = {
            "csv_path": csv_filename,
            "stdout_path": stdout_path,
            "input_path": input_path,
            "timestamp": timestamp,
            "column_count": column_count,
            "header_tokens": [str(tok) for tok in header_tokens] if header_tokens else [],
            "scatter": scatter,
            "model_family": self.family_selector.currentText(),
            "model_name": self.subclass_selector.currentText() or self.family_selector.currentText(),
            "psd_function": self.psd_function.currentText(),
            "direction_label": self.direction.currentText(),
        }

        wavelength_val = self._safe_float(self.wavelength.text())
        if wavelength_val is not None:
            meta["wavelength_um"] = wavelength_val
        substrate_text = self.substrate.text().strip() if hasattr(self, "substrate") else ""
        if substrate_text:
            meta["substrate"] = substrate_text
        meta["direction_code"] = self.DIRECTION_CODES.get(self.direction.currentText(), "0")
        return meta

    def _load_output_meta(self, csv_path: str):
        if not csv_path:
            return None
        try:
            meta_path = Path(str(csv_path) + ".meta.json")
            if not meta_path.exists():
                return None
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    # ======= Data API: save/load params =======
    def _get_text(self, name: str, default: str = "") -> str:
        w = getattr(self, name, None)
        return w.text().strip() if w is not None else default

    def _set_text(self, name: str, value):
        w = getattr(self, name, None)
        if w is not None and value is not None:
            w.setText(str(value))

    def to_params(self) -> dict:
        """Collect current settings to a dict."""
        data = {
            "program": "BRDFProg",
            "angles": {
                "incident_deg": self._get_text("incident_angle"),
                "scatter_start_deg": self._get_text("scatter_start"),
                "scatter_end_deg": self._get_text("scatter_end"),
                "scatter_step_deg": self._get_text("scatter_step"),
                "azimuth_start_deg": self._get_text("azimuth_start"),
                "azimuth_end_deg": self._get_text("azimuth_end"),
                "azimuth_step_deg": self._get_text("azimuth_step"),
            },
            "general": {
                "wavelength_um": self._get_text("wavelength"),
                "substrate": self._get_text("substrate"),
                "direction": self.direction.currentText() if hasattr(self, "direction") else "",
            },
            "family": self.family_selector.currentText() if hasattr(self, "family_selector") else "",
            "model": self.subclass_selector.currentText() if hasattr(self, "subclass_selector") else "",
            "psd_active": self.psd_function.currentText() if hasattr(self, "psd_function") else "",
            "psd_all": {},
        }
        data["model_params"] = self._collect_model_params()
        if data["model"] == "RCW_BRDF_Model":
            data["grating_tree"] = self._current_rcw_grating_tree()
        if data["model"] == "CrossRCW_BRDF_Model":
            data["grating_tree"] = self._current_cross_grating_tree()

        # also serialize all PSD panes irrespective of visibility
        data["psd_all"]["ABC_PSD_Function"] = {
            "A_um4": self._get_text("psd_A"),
            "B_um": self._get_text("psd_B"),
            "C": self._get_text("psd_C"),
        }
        data["psd_all"]["Fractal_PSD_Function"] = {
            "A_um4": self._get_text("psd_fractalAmp"),
            "gamma": self._get_text("psd_fractalExp"),
        }
        data["psd_all"]["Gaussian_PSD_Function"] = {
            "sigma_um": self._get_text("psd_sigma"),
            "Lc_um": self._get_text("psd_lc"),
        }
        data["psd_all"]["Elliptical_Mesa_PSD_Function"] = {
            "axisx_um": self._get_text("psd_ellipticalX"),
            "axisy_um": self._get_text("psd_ellipticalY"),
            "height_um": self._get_text("psd_mesaHeight"),
            "density_um^-2": self._get_text("psd_mesaDensity"),
        }
        data["psd_all"]["Rectangular_Mesa_PSD_Function"] = {
            "lengthx_um": self._get_text("psd_rectLenX"),
            "lengthy_um": self._get_text("psd_rectLenY"),
            "height_um": self._get_text("psd_rectHeight"),
            "density_um^-2": self._get_text("psd_rectDensity"),
        }
        data["psd_all"]["Triangular_Mesa_PSD_Function"] = {
            "side_um": self._get_text("psd_triSide"),
            "height_um": self._get_text("psd_triHeight"),
            "density_um^-2": self._get_text("psd_triDensity"),
        }
        data["psd_all"]["Rectangular_Pyramid_PSD_Function"] = {
            "lengthx_um": self._get_text("psd_pyrLenX"),
            "lengthy_um": self._get_text("psd_pyrLenY"),
            "height_um": self._get_text("psd_pyrHeight"),
            "density_um^-2": self._get_text("psd_pyrDensity"),
        }
        data["psd_all"]["Triangular_Pyramid_PSD_Function"] = {
            "side_um": self._get_text("psd_tpSide"),
            "height_um": self._get_text("psd_tpHeight"),
            "density_um^-2": self._get_text("psd_tpDensity"),
        }
        data["psd_all"]["Parabolic_Dimple_PSD_Function"] = {
            "axisx_um": self._get_text("psd_pdAxisX"),
            "axisy_um": self._get_text("psd_pdAxisY"),
            "height_um": self._get_text("psd_pdHeight"),
            "density_um^-2": self._get_text("psd_pdDensity"),
        }
        return data

    def from_params(self, p: dict):
        try:
            angles = p.get("angles", {})
            self._set_text("incident_angle", angles.get("incident_deg"))
            self._set_text("scatter_start", angles.get("scatter_start_deg"))
            self._set_text("scatter_end", angles.get("scatter_end_deg"))
            self._set_text("scatter_step", angles.get("scatter_step_deg"))
            self._set_text("azimuth_start", angles.get("azimuth_start_deg"))
            self._set_text("azimuth_end", angles.get("azimuth_end_deg"))
            self._set_text("azimuth_step", angles.get("azimuth_step_deg"))
        except Exception:
            pass

        try:
            gen = p.get("general", {})
            self._set_text("wavelength", gen.get("wavelength_um"))
            self._set_text("substrate", gen.get("substrate"))
            if "direction" in gen:
                txt = gen.get("direction") or ""
                idx = self.direction.findText(txt)
                if idx >= 0:
                    self.direction.setCurrentIndex(idx)
        except Exception:
            pass

        try:
            fam = p.get("family")
            if fam is not None:
                i = self.family_selector.findText(fam)
                if i >= 0:
                    self.family_selector.setCurrentIndex(i)
        except Exception:
            pass

        try:
            mdl = p.get("model")
            if mdl is not None:
                i = self.subclass_selector.findText(mdl)
                if i >= 0:
                    self.subclass_selector.setCurrentIndex(i)
        except Exception:
            pass

        # Activate PSD
        try:
            psd_func = p.get("psd_active", "ABC_PSD_Function")
            i = self.psd_function.findText(psd_func)
            if i >= 0:
                self.psd_function.setCurrentIndex(i)
                self.update_psd_parameters(psd_func)
        except Exception:
            pass

        # Populate PSD fields if supplied
        try:
            psd_all = p.get("psd_all", {})
            def set_text(name, key, dct):
                if name in self.__dict__ and key in dct and dct[key] is not None:
                    getattr(self, name).setText(str(dct[key]))

            if "ABC_PSD_Function" in psd_all:
                d = psd_all["ABC_PSD_Function"]
                set_text("psd_A", "A_um4", d)
                set_text("psd_B", "B_um", d)
                set_text("psd_C", "C", d)
            if "Fractal_PSD_Function" in psd_all:
                d = psd_all["Fractal_PSD_Function"]
                set_text("psd_fractalAmp", "A_um4", d)
                set_text("psd_fractalExp", "gamma", d)
            if "Gaussian_PSD_Function" in psd_all:
                d = psd_all["Gaussian_PSD_Function"]
                set_text("psd_sigma", "sigma_um", d)
                set_text("psd_lc", "Lc_um", d)
            if "Elliptical_Mesa_PSD_Function" in psd_all:
                d = psd_all["Elliptical_Mesa_PSD_Function"]
                set_text("psd_ellipticalX", "axisx_um", d)
                set_text("psd_ellipticalY", "axisy_um", d)
                set_text("psd_mesaHeight", "height_um", d)
                set_text("psd_mesaDensity", "density_um^-2", d)
            if "Rectangular_Mesa_PSD_Function" in psd_all:
                d = psd_all["Rectangular_Mesa_PSD_Function"]
                set_text("psd_rectLenX", "lengthx_um", d)
                set_text("psd_rectLenY", "lengthy_um", d)
                set_text("psd_rectHeight", "height_um", d)
                set_text("psd_rectDensity", "density_um^-2", d)
            if "Triangular_Mesa_PSD_Function" in psd_all:
                d = psd_all["Triangular_Mesa_PSD_Function"]
                set_text("psd_triSide", "side_um", d)
                set_text("psd_triHeight", "height_um", d)
                set_text("psd_triDensity", "density_um^-2", d)
            if "Rectangular_Pyramid_PSD_Function" in psd_all:
                d = psd_all["Rectangular_Pyramid_PSD_Function"]
                set_text("psd_pyrLenX", "lengthx_um", d)
                set_text("psd_pyrLenY", "lengthy_um", d)
                set_text("psd_pyrHeight", "height_um", d)
                set_text("psd_pyrDensity", "density_um^-2", d)
            if "Triangular_Pyramid_PSD_Function" in psd_all:
                d = psd_all["Triangular_Pyramid_PSD_Function"]
                set_text("psd_tpSide", "side_um", d)
                set_text("psd_tpHeight", "height_um", d)
                set_text("psd_tpDensity", "density_um^-2", d)
            if "Parabolic_Dimple_PSD_Function" in psd_all:
                d = psd_all["Parabolic_Dimple_PSD_Function"]
                set_text("psd_pdAxisX", "axisx_um", d)
                set_text("psd_pdAxisY", "axisy_um", d)
                set_text("psd_pdHeight", "height_um", d)
                set_text("psd_pdDensity", "density_um^-2", d)
        except Exception:
            pass

        try:
            model_params = p.get("model_params", {})
            if isinstance(model_params, dict):
                current_model = self._current_model_name()
                for name, dtype, _default in self._current_model_specs():
                    lowered = name.lower()
                    if lowered in {"psd", "lambda", "substrate", "type"}:
                        continue
                    if current_model == "RCW_BRDF_Model" and dtype == "Grating_Ptr" and name == "grating":
                        continue
                    if current_model == "CrossRCW_BRDF_Model" and dtype == "CrossGrating_Ptr" and name == "grating":
                        continue
                    if name not in model_params:
                        continue
                    widget = self.param_widgets.get(name)
                    if widget is not None:
                        widget.setText(str(model_params[name]))
                if current_model == "RCW_BRDF_Model":
                    tree = p.get("grating_tree")
                    if tree is not None and self.rcw_grating_editor is not None:
                        self.rcw_grating_editor.from_node(tree)
                        self._rcw_grating_state = self.rcw_grating_editor.to_node()
                if current_model == "CrossRCW_BRDF_Model":
                    tree = p.get("grating_tree")
                    if tree is not None and self.cross_grating_editor is not None:
                        self.cross_grating_editor.from_node(tree)
                        self._cross_grating_state = self.cross_grating_editor.to_node()
        except Exception:
            pass

        return True

    # simple JSON helpers
    def save_to_json(self, path: str):
        import json, pathlib
        data = self.to_params()
        data.setdefault("_schema", {"program": "BRDFProg", "version": 2})
        pathlib.Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load_from_json(self, path: str):
        import json, pathlib
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        self.from_params(data)


    def _on_model_changed(self, *_):
        # Ensure parameters reflect newly selected model
        try:
            self.populate_model_params()
        except Exception as e:
            print("Param populate error:", e)

    def open_last_output(self):
        """Open last output using CSV if available (table-only, like Mie)."""
        data_dir = str(get_data_dir())

        # Prefer CSV companion of last stdout path
        csv_path = self.last_csv_path if self.last_csv_path and os.path.exists(self.last_csv_path) else None
        txt_path = getattr(self, "last_stdout_path", None)
        if csv_path is None and txt_path and txt_path.endswith(".txt"):
            guess_csv = txt_path[:-4] + ".csv"
            if os.path.exists(guess_csv):
                csv_path = guess_csv

        # If no CSV yet, pick the most recent brdf_output_*.csv
        if csv_path is None:
            try:
                cand = [os.path.join(data_dir, f) for f in os.listdir(data_dir)
                        if f.startswith("brdf_output_") and f.endswith(".csv")]
                csv_path = max(cand, key=os.path.getmtime) if cand else None
            except Exception:
                csv_path = None

        # If still no CSV, fallback to latest TXT for best effort parsing
        if csv_path is None:
            try:
                cand_txt = [os.path.join(data_dir, f) for f in os.listdir(data_dir)
                            if f.startswith("brdf_output_") and f.endswith(".txt")]
                txt_path = max(cand_txt, key=os.path.getmtime) if cand_txt else None
            except Exception:
                txt_path = None

        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem
        import csv as _csv
        import re as _re

        def _populate_table_from_rows(header, rows):
            dlg = QDialog(self)
            dlg.setWindowTitle(f"Output Table: {os.path.basename(csv_path or txt_path)}")
            layout = QVBoxLayout(dlg)
            table = QTableWidget(dlg)
            if header and rows:
                table.setColumnCount(len(header))
                table.setRowCount(len(rows))
                table.setHorizontalHeaderLabels(header)
                for r_i, r in enumerate(rows):
                    for c_i, val in enumerate(r):
                        table.setItem(r_i, c_i, QTableWidgetItem(val))
            else:
                table.setColumnCount(1)
                table.setRowCount(1)
                table.setHorizontalHeaderLabels(["Info"])
                table.setItem(0, 0, QTableWidgetItem("No tabular data detected."))
            layout.addWidget(table)
            dlg.resize(900, 600)
            dlg.exec_()

        # Try CSV first
        if csv_path and os.path.exists(csv_path):
            self.last_csv_path = csv_path
        meta = self._load_output_meta(csv_path) if csv_path else None

        try:
            with open(csv_path, "r", encoding="utf-8", errors="ignore", newline="") as f:
                reader = _csv.reader(f)
                rows = [row for row in reader if row]
            if rows:
                ncol = max(len(r) for r in rows)
                header = []
                if meta and meta.get("header_tokens"):
                    header = [str(tok) for tok in meta.get("header_tokens", [])][:ncol]
                if len(header) < ncol:
                    header.extend([f"C{i+1}" for i in range(len(header), ncol)])
                norm_rows = [r + [""]*(ncol-len(r)) for r in rows]
                return _populate_table_from_rows(header, norm_rows)
        except Exception as e:
            self.output_box.append(f"CSV read failed, falling back to TXT: {e}")

        # TXT fallback parsing (collect ALL consecutive numeric rows)
        if not txt_path or not os.path.exists(txt_path):
            self.output_box.append("No BRDF output file found in DATA.")
            return
        try:
            content = open(txt_path, "r", encoding="utf-8", errors="ignore").read()
        except Exception as e:
            self.output_box.append(f"Could not open output: {e}")
            return

        lines = content.splitlines()
        header = None
        rows = []

        def _is_num(t: str) -> bool:
            try:
                float(t.replace("D", "E").replace("d", "e"))
                return True
            except Exception:
                return False

        # Strategy: find first header-like line; then collect ALL following numeric lines (until non-numeric chunk)
        start_idx = None
        for i, line in enumerate(lines):
            toks = _re.split(r"\s+", line.strip())
            if not toks or all(not t for t in toks):
                continue
            # header = any token contains alpha
            if any(_re.search(r"[A-Za-z]", t) for t in toks):
                header = toks
                start_idx = i + 1
                break

        if start_idx is None:
            # No header; collect the LONGEST contiguous numeric block in the file
            best_block = []
            current = []
            for line in lines:
                s = line.strip()
                if not s:
                    if current:
                        if len(current) > len(best_block):
                            best_block = current
                        current = []
                    continue
                parts = _re.split(r"\s+", s)
                if parts and all(_is_num(x) for x in parts):
                    current.append(parts)
                else:
                    if current:
                        if len(current) > len(best_block):
                            best_block = current
                        current = []
            if current and len(current) > len(best_block):
                best_block = current
            if best_block:
                ncol = max(len(r) for r in best_block)
                header = [f"C{i+1}" for i in range(ncol)]
                rows = [r + [""]*(ncol-len(r)) for r in best_block]
            return _populate_table_from_rows(header, rows)

        # With header found, collect ALL subsequent numeric lines
        i = start_idx
        while i < len(lines):
            s = lines[i].strip()
            if not s:
                i += 1
                continue
            parts = _re.split(r"\s+", s)
            if parts and all(_is_num(x) for x in parts):
                rows.append(parts)
                i += 1
                continue
            else:
                # stop at first non-numeric line AFTER header
                break

        # Normalize columns
        if rows:
            ncol = max(len(r) for r in rows)
            rows = [r + [""]*(ncol-len(r)) for r in rows]
            if (not header or not any(header)) and meta and meta.get("header_tokens"):
                header = [str(tok) for tok in meta.get("header_tokens", [])][:ncol]
                if len(header) < ncol:
                    header.extend([f"C{i+1}" for i in range(len(header), ncol)])
        return _populate_table_from_rows(header, rows)


    def open_last_input(self):
        """Open last input deck as plain text."""
        data_dir = str(get_data_dir())
        path = getattr(self, "last_input_path", None)
        if not path or not os.path.exists(path):
            try:
                cand = [os.path.join(data_dir, f) for f in os.listdir(data_dir) if f.startswith("brdf_input_") and f.endswith(".txt")]
                path = max(cand, key=os.path.getmtime) if cand else None
            except Exception:
                path = None
        if not path:
            self.output_box.append("No BRDF input file found in DATA.")
            return
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextEdit
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Input: {os.path.basename(path)}")
        layout = QVBoxLayout(dlg)
        txt = QTextEdit(dlg)
        txt.setReadOnly(True)
        txt.setPlainText(open(path, "r", encoding="utf-8", errors="ignore").read())
        layout.addWidget(txt)
        dlg.resize(700, 500)
        dlg.exec_()
