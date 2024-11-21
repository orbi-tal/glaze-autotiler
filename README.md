# <img src="assets/icon_@128px.png" alt="Glaze Autotiler Logo" height="28px"/> Glaze Autotiler

[![Build](https://github.com/orbi-tal/glaze-autotiler/actions/workflows/build.yml/badge.svg)](https://github.com/orbi-tal/glaze-autotiler/actions/workflows/build.yml)
[![Latest Release](https://img.shields.io/github/v/release/orbi-tal/glaze-autotiler?include_prereleases&label=Latest+Release)](https://github.com/orbi-tal/glaze-autotiler/releases)

An auto-tiling tray application for GlazeWM, provides Master-Stack and Dwindle layouts by default and is extensible with python!

## Features

### Autotiling

![Automatic Window Tiling](assets/autotiling.mp4)

### Custom Layouts

![Custom Layouts](assets/custom-layouts.mp4)

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


### Using Pre-built Executable
Download the latest release from the [releases page](https://github.com/orbi-tal/glaze-autotiler/releases).


## Building the Executable

1. Install PyInstaller:
```bash
pip install pyinstaller
```

2. Build the executable:
```bash
pyinstaller build.spec
```

The executable will be created in the `dist` directory.


## Usage

Run the executable or use Python:
```bash
glaze-autotiler
# or
python src/autotile/main.py
```

Use --log to enable verbose logging:
```bash
glaze-autotiler --log
# or
python src/autotile/main.py --log
```

You can select which layout to use from the tray icon menu.


## Configuration

Configuration files and default tiling scripts are stored in `%USERPROFILE%\.config\glaze-autotiler\`.

To add a custom layout you can add to the config.json file:
```json
{
  "custom_layout": {
      "display_name": "My Custom Layout",
      "enabled": true
  }
}
```
You can also add a custom script path in:
```json
  "script_paths": [
      "C:\\Users\\YourUsername\\.config\\glaze-autotiler\\scripts",
      "C:\\Custom\\Script\\Path"
  ]
```

## Development

### Setup Linting

This project uses several linting and formatting tools:
- `black` for code formatting
- `isort` for import sorting
- `flake8` for style guide enforcement
- `pylint` for code analysis

To set up the development environment:

```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install development dependencies
pip install -r requirements-dev.txt

# Install pre-commit hooks
pip install pre-commit
pre-commit install
```

### Running Linters

```bash
# Run all linters
python scripts/lint.py

# Format code
black .
isort .

# Check code without formatting
black --check .
isort --check-only .
flake8
pylint src
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgements
lars-berger for [GlazeWM](https://github.com/glzr-io/glazewm).\
ParasiteDelta for the [inspiration](https://github.com/ParasiteDelta/GAT-GWM).\
burgr033 for the original [autotiler script](https://github.com/burgr033/GlazeWM-autotiling-python).\
Opposite34 for the [Dwindle script](https://gist.github.com/Opposite34/f3a487d940e9fb968d01f7e30969fbd1).
