# <img src="assets/icon_@128px.png" alt="Glaze Autotiler Logo" height="28px"/> Glaze Autotiler

[![Build](https://github.com/orbi-tal/glaze-autotiler/actions/workflows/build.yml/badge.svg)](https://github.com/orbi-tal/glaze-autotiler/actions/workflows/build.yml)
[![Latest Release](https://img.shields.io/github/v/release/orbi-tal/glaze-autotiler?include_prereleases&label=Latest+Release)](https://github.com/orbi-tal/glaze-autotiler/releases)

An auto-tiling tray application for GlazeWM. Includes Dwindle and Master-Stack layouts by default, and is easily extended with Python. The tray icon and menu are built directly on the Win32 API (no GUI toolkit), keeping idle memory usage typically around 5MB.

## Features

### Autotiling

https://github.com/user-attachments/assets/a4f8ab7a-5e58-4986-b013-2ea081f34556

### Custom Layouts

https://github.com/user-attachments/assets/710f9a94-6deb-4700-882e-402a50adeadb


## Installation

### From Source
1. Clone the repository:
```bash
git clone https://github.com/orbi-tal/glaze-autotiler.git
cd glaze-autotiler
```

2. Create a virtual environment and activate it:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

### Using a Pre-built Executable
Download the latest release from the [releases page](https://github.com/orbi-tal/glaze-autotiler/releases).

Two builds are available:
- **glaze-autotiler** — no console window, for daily use
- **glaze-autotiler-console** — console window, for debugging


## Building the Executable

1. Install PyInstaller:
```bash
pip install pyinstaller
```

2. Build the executable:
```bash
pyinstaller build.spec              # console build, for debugging
pyinstaller build-noconsole.spec    # no console window, for regular use
```

The executable is created in the `dist` directory. Both builds automatically link `file_version_info.txt` and `manifest.xml` for Windows properties and High-DPI support. 

If something's not working right, build and run the console version first, its output is much easier to read than digging through log files.


## Usage

Run the executable, or `python src/main.py`.

| Flag | Effect |
|---|---|
| `-l`, `--log` | Enable logging |
| `-d`, `--debug` | Enable more verbose logging than `-l` |
| `-m`, `--monitor-cpu` | Enable CPU usage monitoring |
| `--gc-debug` | Enable garbage collection debug output |

These work the same regardless of how you're running it, and can be combined, e.g.:
```bash
glaze-autotiler-console-[version].exe -d -m
# or
python src/main.py --debug --monitor-cpu
```

With the console build, `-l`/`-d` output prints directly to the console. With the no-console build, it's written instead to a timestamped log file under `%USERPROFILE%\.config\glaze-autotiler\logs\`.

**Note:** without `-l`/`-d`, most log output isn't recorded anywhere. Warnings and errors are the exception — those always get written to `autotiler_errors.log` in the same logs folder, so that's the first place to check if something's misbehaving even with logging off.


## Configuration

Config and the default layout scripts live in `%USERPROFILE%\.config\glaze-autotiler\`. A `config.json` is created there automatically on first run, with `dwindle` and `master_stack` already enabled.

To add a custom layout, add it under `"layouts"` in `config.json`:
```json
{
  "layouts": {
    "custom_layout": {
      "display_name": "My Custom Layout",
      "enabled": true
    }
  }
}
```
A custom layout is any Python file that defines an async `run(cancel_event)` function — see `dwindle.py` or `master_stack.py` in the scripts folder for a working example. By default, scripts are loaded from the scripts folder above; you can add more locations, or point directly at a script elsewhere, via `"script_paths"`:
```json
{
  "script_paths": [
    "C:\\Users\\YourUsername\\.config\\glaze-autotiler\\scripts",
    "C:\\Custom\\Script\\Path"
  ]
}
```


## Development

Tools used: `black` (formatting), `isort` (import sorting), `flake8` (style), `pylint` (analysis), `pytest` (testing). `pyproject.toml` also configures `pyright`/`basedpyright` (`extraPaths = ["src"]`) so editors correctly resolve `main.py`'s sibling import of `tray_win32.py`.

### Setup environment
```bash
# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dev dependencies and pre-commit hooks
pip install -r requirements-dev.txt
pre-commit install
```

### Static Analysis & Formatting
```bash
python scripts/lint.py                                     # run all linters
black . && isort .                                          # format code
black --check . && isort --check-only . && flake8 && pylint src   # check without formatting
```

### Testing
Tests run on Windows, Linux, and macOS. Dynamic mocks inside `tests/conftest.py` intercept native Win32/Websocket API calls so tests don't crash on non-Windows environments.

```bash
python -m pytest -v                     # run all tests
python -m pytest -v -s                  # run tests and print debug console output
```
Use `python -m pytest`, not a bare `pytest` or the `py` launcher — either can silently resolve to a different interpreter than your activated venv, missing the dev dependencies installed there (you'll see `pytest-asyncio` etc. absent from the reported `plugins:` line if this happens).


## Troubleshooting

### High CPU Usage
1. Run the console build with monitoring enabled: `glaze-autotiler-console-[version].exe -d -m`
2. Check the console output for errors
3. Try each layout individually to see if one of them is responsible
4. Confirm GlazeWM itself is running properly
5. Note whether spikes happen only during specific operations (e.g. window creation, focus changes)

### Missing Console Output
1. Confirm you're running the console build (`glaze-autotiler-console-[version].exe`), not the no-console one
2. Add `-d` for maximum verbosity
3. Check the log files under `%USERPROFILE%\.config\glaze-autotiler\logs\` — including `autotiler_errors.log`, which is written even when the console shows nothing


## License

This project is licensed under the MIT License - see the LICENSE file for details.


## Acknowledgements
lars-berger for [GlazeWM](https://github.com/glzr-io/glazewm).\
ParasiteDelta for the [inspiration](https://github.com/ParasiteDelta/GAT-GWM).\
burgr033 for the original [autotiler script](https://github.com/burgr033/GlazeWM-autotiling-python).\
Opposite34 for the [Dwindle script](https://gist.github.com/Opposite34/f3a487d940e9fb968d01f7e30969fbd1).
