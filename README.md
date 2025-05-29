# <img src="assets/icon_@128px.png" alt="Glaze Autotiler Logo" height="28px"/> Glaze Autotiler

[![Build](https://github.com/orbi-tal/glaze-autotiler/actions/workflows/build.yml/badge.svg)](https://github.com/orbi-tal/glaze-autotiler/actions/workflows/build.yml)
[![Latest Release](https://img.shields.io/github/v/release/orbi-tal/glaze-autotiler?include_prereleases&label=Latest+Release)](https://github.com/orbi-tal/glaze-autotiler/releases)

An auto-tiling tray application for GlazeWM, provides Master-Stack and Dwindle layouts by default and is extensible with python!

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


### Using Pre-built Executable
Download the latest release from the [releases page](https://github.com/orbi-tal/glaze-autotiler/releases).

Two versions are available:
- **glaze-autotiler** - Standard version without console window (recommended for daily use)
- **glaze-autotiler-console** - Version with console window (recommended for debugging)


## Building the Executable

1. Install PyInstaller:
```bash
pip install pyinstaller
```

2. Build the executable:

For a version with console output (better for debugging):
```bash
pyinstaller build.spec
```

For a version without console window (cleaner for regular use):
```bash
pyinstaller build-noconsole.spec
```

The executable will be created in the `dist` directory.

**Note:** The console version is recommended if you're experiencing issues, as it shows debug output directly.

### Console vs. Non-Console Version

- **Console Version** (`glaze-autotiler-console-[version].exe`): Shows debugging information directly in a console window. Use this if you're troubleshooting CPU usage or other issues.
- **Non-Console Version** (`glaze-autotiler-[version].exe`): Runs without a visible console window. More suitable for regular use.

When using the console version, debug arguments (-d, -l, -m) will show output directly in the console window.


## Usage

Run the executable or use Python:
```bash
# Standard version (no console)
glaze-autotiler-[version].exe

# Console version (for debugging)
glaze-autotiler-console-[version].exe

# Or run directly with Python
python src/main.py
```

Use -l or --log to enable verbose logging:
```bash
# With console version
glaze-autotiler-console-[version].exe -l

# With standard version (output goes to log file only)
glaze-autotiler-[version].exe -l

# Or with Python
python src/main.py --log
```

Use -d or --debug for even more detailed logging:
```bash
# With console version (recommended for debugging)
glaze-autotiler-console-[version].exe -d

# With standard version (output goes to log file only)
glaze-autotiler-[version].exe -d
```

Additional command line options:
```bash
# Enable CPU usage monitoring (requires psutil)
glaze-autotiler-console-[version].exe -m
# or
glaze-autotiler-[version].exe --monitor-cpu

# Enable garbage collection debugging
glaze-autotiler-console-[version].exe --gc-debug

# Combine options
glaze-autotiler-console-[version].exe -d -m
# or
glaze-autotiler-[version].exe --debug --monitor-cpu
```

**Note**: These command-line options will work with both Python and the console version of the executable. With the non-console version, debug output won't be visible but will still be written to log files.

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

## Troubleshooting

### High CPU Usage
If you're experiencing high CPU usage:

1. Use the console version with monitoring enabled:
```bash
glaze-autotiler-console-[version].exe -d -m
```

2. Check for error messages in the console output
3. Try each layout to determine if one specific layout is causing high CPU
4. Verify your GlazeWM is running properly
5. Check if CPU usage spikes only during certain operations

### Missing Console Output
If you're not seeing console output:

1. Make sure you're using the console build (`glaze-autotiler-console-[version].exe`)
2. Run with explicit debug flags: `glaze-autotiler-console-[version].exe -d`
3. Check if the log files contain output even when console doesn't

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgements
lars-berger for [GlazeWM](https://github.com/glzr-io/glazewm).\
ParasiteDelta for the [inspiration](https://github.com/ParasiteDelta/GAT-GWM).\
burgr033 for the original [autotiler script](https://github.com/burgr033/GlazeWM-autotiling-python).\
Opposite34 for the [Dwindle script](https://gist.github.com/Opposite34/f3a487d940e9fb968d01f7e30969fbd1).
