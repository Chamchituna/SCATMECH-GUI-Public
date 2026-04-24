# SCATMECH GUI

Minimal public-facing GUI source for running the SCATMECH command-line solvers from a desktop app.

## Requirements

- Python 3.10 or newer
- A separate SCATMECH installation that provides `brdfprog`, `mieprog`, `reflectprog`, and `rcwprog`
- The Python packages listed in `requirements.txt`

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configure SCATMECH

If the SCATMECH executables are not already on your `PATH`, set `SCATMECH_BIN` to the directory that contains them.

```bash
export SCATMECH_BIN=/path/to/scatmech/bin
```

## Launch

```bash
python run_gui.py
```

The GUI writes generated input and output files to the local `DATA/` directory, which is ignored by git.

## Not Included

- SCATMECH binaries
- datasets, plots, and result artifacts
- batch automation scripts, sample job configs, and test assets

## Author

Woojun Lee
