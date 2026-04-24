from __future__ import annotations

from collections import OrderedDict
from typing import Any, Dict, List, Mapping


FieldSpec = Dict[str, str]
ModelSpec = Dict[str, Any]


def _param(name: str, label: str, default: str) -> FieldSpec:
    return {
        "kind": "param",
        "name": name,
        "label": label,
        "default": default,
    }


def _child(name: str, label: str, child_kind: str, default_model: str) -> FieldSpec:
    return {
        "kind": "child",
        "name": name,
        "label": label,
        "child_kind": child_kind,
        "default_model": default_model,
    }


ONE_D_GRATING_SPECS: "OrderedDict[str, ModelSpec]" = OrderedDict(
    [
        (
            "Single_Line_Grating",
            {
                "fields": [
                    _param("period", "Period of the grating [um]", "1"),
                    _param("medium_i", "Incident medium (n,k)", "(1,0)"),
                    _param("medium_t", "Transmission medium (n,k)", "(4.05,0.05)"),
                    _param("material", "Line material (n,k)", "(4.05,0.05)"),
                    _param("space", "Space between lines (n,k)", "(1,0)"),
                    _param("height", "Height of grating [um]", "0.2"),
                    _param("topwidth", "Top width [um]", "0.2"),
                    _param("bottomwidth", "Bottom width [um]", "0.2"),
                    _param("offset", "Bottom shift relative to top [um]", "0"),
                    _param("nlevels", "Number of levels", "10"),
                ]
            },
        ),
        (
            "Corner_Rounded_Grating",
            {
                "fields": [
                    _param("period", "Period of the grating [um]", "1"),
                    _param("medium_i", "Incident medium (n,k)", "(1,0)"),
                    _param("medium_t", "Transmission medium (n,k)", "(4.05,0.05)"),
                    _param("material", "Line optical properties (n,k)", "(4.05,0.05)"),
                    _param("height", "Height of line [um]", "0.1"),
                    _param("width", "Bottom width [um]", "0.1"),
                    _param("sidewall", "Sidewall angle [deg]", "88"),
                    _param("radiusb", "Bottom radius [um]", "0.010"),
                    _param("radiust", "Top radius [um]", "0.001"),
                    _param("nlevels", "Number of levels", "10"),
                ]
            },
        ),
        (
            "Sinusoidal_Relief_Grating",
            {
                "fields": [
                    _param("period", "Period of the grating [um]", "1"),
                    _param("medium_i", "Incident medium (n,k)", "(1,0)"),
                    _param("medium_t", "Transmission medium (n,k)", "(4.05,0.05)"),
                    _param("material", "Line material (n,k)", "(4.05,0.05)"),
                    _param("amplitude", "Amplitude [um]", "0.4"),
                    _param("base", "Base of sinusoid [um]", "0."),
                    _param("option", "Division option (0=horiz,1=vert)", "0"),
                    _param("nlevels", "Number of levels", "20"),
                ]
            },
        ),
        (
            "Sinusoidal_Volume_Grating",
            {
                "fields": [
                    _param("period", "Period of the grating [um]", "1"),
                    _param("medium_i", "Incident medium (n,k)", "(1,0)"),
                    _param("medium_t", "Transmission medium (n,k)", "(4.05,0.05)"),
                    _param("minimum", "Minimum index (n,k)", "(1.52,0)"),
                    _param("maximum", "Maximum index (n,k)", "(1.50,0)"),
                    _param("thick", "Layer thickness [um]", "0.1"),
                    _param("tilt", "Tilt angle [deg]", "0"),
                    _param("nlevels", "Number of levels", "1"),
                ]
            },
        ),
        (
            "Triangular_Grating",
            {
                "fields": [
                    _param("period", "Period of the grating [um]", "1"),
                    _param("medium_i", "Incident medium (n,k)", "(1,0)"),
                    _param("medium_t", "Transmission medium (n,k)", "(4.05,0.05)"),
                    _param("material", "Triangle medium (n,k)", "(4.05,0.05)"),
                    _param("amplitude", "Amplitude [um]", "0.4"),
                    _param("aspect", "Aspect ratio", "0.5"),
                    _param("nlevels", "Number of levels", "20"),
                ]
            },
        ),
        (
            "Generic_Grating",
            {
                "fields": [
                    _param("period", "Period of the grating [um]", "1"),
                    _param("medium_i", "Incident medium (n,k)", "(1,0)"),
                    _param("medium_t", "Transmission medium (n,k)", "(4.05,0.05)"),
                    _param("filename", "Filename", ""),
                    _param("pstring", "Parameter string", ""),
                    _param("nlayers", "Approximate number of levels", "20"),
                ]
            },
        ),
    ]
)


CROSS_GRATING_SPECS: "OrderedDict[str, ModelSpec]" = OrderedDict(
    [
        (
            "OneD_CrossGrating",
            {
                "fields": [
                    _param("medium_i", "Incident medium (n,k)", "(1,0)"),
                    _param("medium_t", "Transmission medium (n,k)", "(4.05,0.05)"),
                    _param("d2", "Lattice constant #2 [um]", "0.5"),
                    _param("zeta", "Angle of lattice vectors from perpendicular [deg]", "0"),
                    _child("grating", "1D grating", "one_d", "Single_Line_Grating"),
                ]
            },
        ),
        (
            "Overlaid_CrossGrating",
            {
                "fields": [
                    _param("medium_i", "Incident medium (n,k)", "(1,0)"),
                    _param("medium_t", "Transmission medium (n,k)", "(4.05,0.05)"),
                    _child("top", "Top cross grating", "cross", "OneD_CrossGrating"),
                    _child("bottom", "Bottom cross grating", "cross", "OneD_CrossGrating"),
                    _param("overlay1", "Overlay along 1st coordinate [um]", "0"),
                    _param("overlay2", "Overlay along 2nd coordinate [um]", "0"),
                    _param("separation", "Vertical separation between gratings [um]", "0"),
                ]
            },
        ),
        (
            "Overlaid_1D_CrossGrating",
            {
                "fields": [
                    _param("medium_i", "Incident medium (n,k)", "(1,0)"),
                    _param("medium_t", "Transmission medium (n,k)", "(4.05,0.05)"),
                    _child("top", "Top 1D grating", "one_d", "Single_Line_Grating"),
                    _child("bottom", "Bottom 1D grating", "one_d", "Single_Line_Grating"),
                    _param("angle", "Angle between gratings [deg]", "90"),
                    _param("separation", "Vertical separation between gratings [um]", "0"),
                ]
            },
        ),
        (
            "Null_CrossGrating",
            {
                "fields": [
                    _param("medium_i", "Incident medium (n,k)", "(1,0)"),
                    _param("medium_t", "Transmission medium (n,k)", "(4.05,0.05)"),
                    _param("d1", "Lattice constant #1 [um]", "0.5"),
                    _param("d2", "Lattice constant #2 [um]", "0.5"),
                    _param("zeta", "Angle of lattice vectors from perpendicular [deg]", "0"),
                ]
            },
        ),
        (
            "Generic_CrossGrating",
            {
                "fields": [
                    _param("medium_i", "Incident medium (n,k)", "(1,0)"),
                    _param("medium_t", "Transmission medium (n,k)", "(4.05,0.05)"),
                    _param("zeta", "Angle of lattice vectors from perpendicular [deg]", "0"),
                    _param("d1", "Lattice constant #1 [um]", "0.5"),
                    _param("d2", "Lattice constant #2 [um]", "0.5"),
                    _param("grid1", "Grid samples in direction #1", "1024"),
                    _param("grid2", "Grid samples in direction #2", "1024"),
                    _param("filename", "Filename", ""),
                    _param("pstring", "Parameter string", ""),
                    _param("nlayers", "Number of layers", "10"),
                ]
            },
        ),
        (
            "Cylinder_CrossGrating",
            {
                "fields": [
                    _param("medium_i", "Incident medium (n,k)", "(1,0)"),
                    _param("medium_t", "Transmission medium (n,k)", "(4.05,0.05)"),
                    _param("zeta", "Angle of lattice vectors from perpendicular [deg]", "0"),
                    _param("d1", "Lattice constant #1 [um]", "0.5"),
                    _param("d2", "Lattice constant #2 [um]", "0.5"),
                    _param("grid1", "Grid samples in direction #1", "1024"),
                    _param("grid2", "Grid samples in direction #2", "1024"),
                    _param("rtop", "Radius of top of holes [um] as function of angle [deg]", "0.1"),
                    _param("rbottom", "Radius of bottom of holes [um] as function of angle [deg]", "0.1"),
                    _param("thickness", "Thickness of grating [um]", "0.1"),
                    _param("nlevels", "Number of levels in grating", "1"),
                    _param("inside", "Medium inside holes", "(1,0)"),
                    _param("outside", "Medium outside holes", "(1.5,0)"),
                ]
            },
        ),
        (
            "Rectangle_CrossGrating",
            {
                "fields": [
                    _param("medium_i", "Incident medium (n,k)", "(1,0)"),
                    _param("medium_t", "Transmission medium (n,k)", "(4.05,0.05)"),
                    _param("zeta", "Angle of lattice vectors from perpendicular [deg]", "0"),
                    _param("d1", "Lattice constant #1 [um]", "0.5"),
                    _param("d2", "Lattice constant #2 [um]", "0.5"),
                    _param("grid1", "Grid samples in direction #1", "1024"),
                    _param("grid2", "Grid samples in direction #2", "1024"),
                    _param("length1", "Length of rectangle in first direction [um]", "0.1"),
                    _param("length2", "Length of rectangle in second direction [um]", "0.1"),
                    _param("zetaa", "Skew angle of rectangle [deg]", "0"),
                    _param("thickness", "Thickness of grating [um]", "0.1"),
                    _param("inside", "Medium inside rectangles", "(1,0)"),
                    _param("outside", "Medium outside rectangles", "(1.5,0)"),
                ]
            },
        ),
        (
            "Sphere_CrossGrating",
            {
                "fields": [
                    _param("medium_i", "Incident medium (n,k)", "(1,0)"),
                    _param("medium_t", "Transmission medium (n,k)", "(4.05,0.05)"),
                    _param("zeta", "Angle of lattice vectors from perpendicular [deg]", "0"),
                    _param("d1", "Lattice constant #1 [um]", "0.5"),
                    _param("d2", "Lattice constant #2 [um]", "0.5"),
                    _param("grid1", "Grid samples in direction #1", "1024"),
                    _param("grid2", "Grid samples in direction #2", "1024"),
                    _param("diameter", "Diameter of sphere [um]", "0.05"),
                    _param("above", "Distance of sphere from top of layer [um]", "0.05"),
                    _param("below", "Distance of sphere from bottom of layer [um]", "0.05"),
                    _param("nlevels", "Number of levels in structure", "7"),
                    _param("sphere", "Sphere", "(1,0)"),
                    _param("surrounding", "Medium around sphere", "(1.5,0)"),
                ]
            },
        ),
        (
            "Pyramidal_Pit_CrossGrating",
            {
                "fields": [
                    _param("medium_i", "Incident medium (n,k)", "(1,0)"),
                    _param("medium_t", "Transmission medium (n,k)", "(4.05,0.05)"),
                    _param("zeta", "Angle of lattice vectors from perpendicular [deg]", "0"),
                    _param("d1", "Lattice constant #1 [um]", "0.5"),
                    _param("d2", "Lattice constant #2 [um]", "0.5"),
                    _param("grid1", "Grid samples in direction #1", "1024"),
                    _param("grid2", "Grid samples in direction #2", "1024"),
                    _param("side", "Length of side of base of pyramid [um]", "0.05"),
                    _param("depth", "Depth of pit [um]", "0.05"),
                    _param("nlevels", "Number of levels", "10"),
                ]
            },
        ),
    ]
)


def list_one_d_grating_models() -> List[str]:
    return list(ONE_D_GRATING_SPECS.keys())


def list_cross_grating_models(*, allow_overlay: bool = True) -> List[str]:
    names = list(CROSS_GRATING_SPECS.keys())
    if allow_overlay:
        return names
    return [name for name in names if name != "Overlaid_CrossGrating"]


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value)
    return text if text != "" else default


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def get_one_d_grating_spec(model: str) -> ModelSpec:
    return ONE_D_GRATING_SPECS[model]


def get_cross_grating_spec(model: str) -> ModelSpec:
    return CROSS_GRATING_SPECS[model]


def build_default_one_d_grating(model: str = "Single_Line_Grating") -> Dict[str, Any]:
    if model not in ONE_D_GRATING_SPECS:
        model = "Single_Line_Grating"
    spec = ONE_D_GRATING_SPECS[model]
    params = {
        field["name"]: field["default"]
        for field in spec["fields"]
        if field["kind"] == "param"
    }
    return {
        "kind": "grating",
        "model": model,
        "params": params,
    }


def build_default_cross_grating(
    model: str = "OneD_CrossGrating",
    *,
    allow_overlay: bool = True,
) -> Dict[str, Any]:
    if model not in CROSS_GRATING_SPECS or (not allow_overlay and model == "Overlaid_CrossGrating"):
        model = "OneD_CrossGrating"
    spec = CROSS_GRATING_SPECS[model]
    params = {
        field["name"]: field["default"]
        for field in spec["fields"]
        if field["kind"] == "param"
    }
    children: Dict[str, Any] = {}
    for field in spec["fields"]:
        if field["kind"] != "child":
            continue
        name = field["name"]
        default_model = field["default_model"]
        if field["child_kind"] == "one_d":
            children[name] = build_default_one_d_grating(default_model)
        else:
            children[name] = build_default_cross_grating(default_model, allow_overlay=False)
    return {
        "kind": "cross",
        "model": model,
        "params": params,
        "children": children,
    }


def coerce_one_d_grating(node: Any, default_model: str = "Single_Line_Grating") -> Dict[str, Any]:
    raw = _mapping(node)
    model = _text(raw.get("model"), default_model)
    base = build_default_one_d_grating(model)
    params = _mapping(raw.get("params"))
    for key in list(base["params"].keys()):
        if key in params:
            base["params"][key] = _text(params.get(key), base["params"][key])
    return base


def coerce_cross_grating(
    node: Any,
    *,
    allow_overlay: bool = True,
    default_model: str = "OneD_CrossGrating",
) -> Dict[str, Any]:
    raw = _mapping(node)
    model = _text(raw.get("model"), default_model)
    base = build_default_cross_grating(model, allow_overlay=allow_overlay)
    params = _mapping(raw.get("params"))
    for key in list(base["params"].keys()):
        if key in params:
            base["params"][key] = _text(params.get(key), base["params"][key])

    raw_children = _mapping(raw.get("children"))
    for field in CROSS_GRATING_SPECS[base["model"]]["fields"]:
        if field["kind"] != "child":
            continue
        name = field["name"]
        child_value = raw_children.get(name)
        if field["child_kind"] == "one_d":
            base["children"][name] = coerce_one_d_grating(child_value, field["default_model"])
        else:
            base["children"][name] = coerce_cross_grating(
                child_value,
                allow_overlay=False,
                default_model=field["default_model"],
            )
    return base


def serialize_one_d_grating(node: Any) -> List[str]:
    raw = _mapping(node)
    model = _text(raw.get("model"))
    if model not in ONE_D_GRATING_SPECS:
        raise ValueError(f"Unsupported 1D grating model '{model or '<blank>'}'")
    params = _mapping(raw.get("params"))
    spec = ONE_D_GRATING_SPECS[model]
    lines = [model]
    for field in spec["fields"]:
        if field["kind"] != "param":
            continue
        lines.append(_text(params.get(field["name"]), field["default"]))
    return lines


def _serialize_cross_grating(node: Any, *, allow_overlay: bool) -> List[str]:
    raw = _mapping(node)
    model = _text(raw.get("model"))
    if model not in CROSS_GRATING_SPECS:
        raise ValueError(f"Unsupported cross grating model '{model or '<blank>'}'")
    if not allow_overlay and model == "Overlaid_CrossGrating":
        raise ValueError("Nested Overlaid_CrossGrating is not supported")

    params = _mapping(raw.get("params"))
    children = _mapping(raw.get("children"))
    spec = CROSS_GRATING_SPECS[model]

    lines = [model]
    for field in spec["fields"]:
        if field["kind"] == "param":
            lines.append(_text(params.get(field["name"]), field["default"]))
            continue

        child = children.get(field["name"])
        if child is None:
            raise ValueError(f"Missing child grating '{field['name']}' for {model}")
        if field["child_kind"] == "one_d":
            lines.extend(serialize_one_d_grating(child))
        else:
            lines.extend(_serialize_cross_grating(child, allow_overlay=False))
    return lines


def serialize_cross_grating(node: Any) -> List[str]:
    return _serialize_cross_grating(node, allow_overlay=True)


def validate_cross_grating(node: Any) -> List[str]:
    errors: List[str] = []
    _validate_cross_grating(node, errors=errors, path="grating", allow_overlay=True)
    return errors


def _validate_cross_grating(
    node: Any,
    *,
    errors: List[str],
    path: str,
    allow_overlay: bool,
) -> None:
    raw = _mapping(node)
    model = _text(raw.get("model"))
    if model not in CROSS_GRATING_SPECS:
        errors.append(f"{path}: unsupported cross grating model '{model or '<blank>'}'")
        return
    if not allow_overlay and model == "Overlaid_CrossGrating":
        errors.append(f"{path}: nested Overlaid_CrossGrating is not supported")
        return

    params = _mapping(raw.get("params"))
    children = _mapping(raw.get("children"))
    spec = CROSS_GRATING_SPECS[model]

    if model == "Generic_CrossGrating" and not _text(params.get("filename")).strip():
        errors.append(f"{path}.params.filename is required for Generic_CrossGrating")

    if model == "Overlaid_1D_CrossGrating":
        angle = _text(params.get("angle"), "0").strip()
        if angle in {"0", "0.0", "+0", "-0"}:
            errors.append(f"{path}.params.angle must be non-zero for Overlaid_1D_CrossGrating")

    for field in spec["fields"]:
        if field["kind"] != "child":
            continue
        name = field["name"]
        child = children.get(name)
        if child is None:
            errors.append(f"{path}.children.{name} is required for {model}")
            continue
        child_path = f"{path}.children.{name}"
        if field["child_kind"] == "one_d":
            _validate_one_d_grating(child, errors=errors, path=child_path)
        else:
            _validate_cross_grating(child, errors=errors, path=child_path, allow_overlay=False)

    if model == "OneD_CrossGrating":
        child = children.get("grating")
        if child is not None:
            child_params = _mapping(_mapping(child).get("params"))
            parent_medium_i = _text(params.get("medium_i"), "(1,0)")
            parent_medium_t = _text(params.get("medium_t"), "(4.05,0.05)")
            child_medium_i = _text(child_params.get("medium_i"), "(1,0)")
            child_medium_t = _text(child_params.get("medium_t"), "(4.05,0.05)")
            if parent_medium_i != child_medium_i:
                errors.append(
                    f"{path}: medium_i must match child grating.medium_i "
                    f"({parent_medium_i} != {child_medium_i})"
                )
            if parent_medium_t != child_medium_t:
                errors.append(
                    f"{path}: medium_t must match child grating.medium_t "
                    f"({parent_medium_t} != {child_medium_t})"
                )

    if model == "Overlaid_CrossGrating":
        top = children.get("top")
        bottom = children.get("bottom")
        if top is not None and _text(_mapping(top).get("model")) == "Overlaid_CrossGrating":
            errors.append(f"{path}.children.top: nested Overlaid_CrossGrating is not supported")
        if bottom is not None and _text(_mapping(bottom).get("model")) == "Overlaid_CrossGrating":
            errors.append(f"{path}.children.bottom: nested Overlaid_CrossGrating is not supported")

        if top is not None and bottom is not None:
            top_params = _mapping(_mapping(top).get("params"))
            bottom_params = _mapping(_mapping(bottom).get("params"))
            parent_medium_i = _text(params.get("medium_i"), "(1,0)")
            parent_medium_t = _text(params.get("medium_t"), "(4.05,0.05)")
            top_medium_i = _text(top_params.get("medium_i"), "(1,0)")
            top_medium_t = _text(top_params.get("medium_t"), "(4.05,0.05)")
            bottom_medium_i = _text(bottom_params.get("medium_i"), "(1,0)")
            bottom_medium_t = _text(bottom_params.get("medium_t"), "(4.05,0.05)")
            if parent_medium_i != top_medium_i:
                errors.append(
                    f"{path}: medium_i must match top.medium_i "
                    f"({parent_medium_i} != {top_medium_i})"
                )
            if parent_medium_t != bottom_medium_t:
                errors.append(
                    f"{path}: medium_t must match bottom.medium_t "
                    f"({parent_medium_t} != {bottom_medium_t})"
                )
            if top_medium_t != bottom_medium_i:
                errors.append(
                    f"{path}: top.medium_t must match bottom.medium_i "
                    f"({top_medium_t} != {bottom_medium_i})"
                )


def _validate_one_d_grating(node: Any, *, errors: List[str], path: str) -> None:
    raw = _mapping(node)
    model = _text(raw.get("model"))
    if model not in ONE_D_GRATING_SPECS:
        errors.append(f"{path}: unsupported 1D grating model '{model or '<blank>'}'")
        return
    params = _mapping(raw.get("params"))
    if model == "Generic_Grating" and not _text(params.get("filename")).strip():
        errors.append(f"{path}.params.filename is required for Generic_Grating")
