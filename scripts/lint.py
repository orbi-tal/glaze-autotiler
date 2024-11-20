"""Execute linting checks for the project."""

import subprocess
import sys
from typing import List, Tuple


def run_command(command: List[str]) -> Tuple[int, str]:
    """Execute a command and return its exit code and output.

    Args:
        command: Command to run as list of strings

    Returns:
        Tuple of (exit_code, output)
    """
    try:
        output = subprocess.check_output(command, stderr=subprocess.STDOUT)
        return 0, output.decode()
    except subprocess.CalledProcessError as e:
        return e.returncode, e.output.decode()


def main():
    """Execute all linting commands."""
    commands = [["black", "."], ["isort", "."], ["flake8"], ["pylint", "src"]]

    exit_code = 0
    for command in commands:
        print(f"\nRunning {' '.join(command)}...")
        code, output = run_command(command)
        if code != 0:
            exit_code = code
        if output:
            print(output)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
