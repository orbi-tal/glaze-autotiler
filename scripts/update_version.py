#!/usr/bin/env python
"""
Update version numbers in source files.

This script should be run before creating a new release tag.
It updates the version number in main.py and optionally creates
a Git tag for the new version. It can also pin build dependency
versions (pyinstaller, psutil) to what's installed locally.

Usage:
    python scripts/update_version.py [version] [options]

Positional arguments:
    version           Version number to set, format X.Y.Z (e.g. 1.2.3).
                      Optional -- if omitted, the patch version of the
                      latest Git tag is auto-incremented.

Options:
    --tag             Create a Git tag (vX.Y.Z) for the version. Refuses if
                      there are uncommitted changes to tracked files, unless
                      --commit or --force-tag is also given.
    --force-tag       Create the tag even if there are uncommitted changes
                      to tracked files. Has no effect without --tag.
    --commit          Commit version/dependency changes to Git before
                      tagging.
    --pin-deps        Pin requirements.txt (and build.yml's pyinstaller
                      version) to what's currently installed locally.

Examples:
    # Update to version 1.2.3
    python scripts/update_version.py 1.2.3

    # Update to version 1.2.3 and create a tag
    python scripts/update_version.py 1.2.3 --tag

    # Update, commit, and tag in one step
    python scripts/update_version.py 1.2.3 --commit --tag

    # Pin requirements.txt and build.yml to locally installed dep versions
    python scripts/update_version.py 1.2.3 --pin-deps

    # Pin deps, commit them, and tag -- so the tag reflects the pins
    python scripts/update_version.py 1.2.3 --pin-deps --commit --tag

    # Tag anyway despite uncommitted changes (not recommended)
    python scripts/update_version.py 1.2.3 --tag --force-tag
"""

import argparse
import importlib.metadata
import os
import re
import subprocess
import sys

# Dependencies whose installed versions get pinned in requirements.txt
# and (for pyinstaller) in the CI workflow, when --pin-deps is used.
PINNED_DEPENDENCIES = ["pyinstaller", "psutil"]

REQUIREMENTS_FILE = "requirements.txt"
WORKFLOW_FILE = os.path.join(".github", "workflows", "build.yml")

# Files to update version in
VERSION_FILES = [
    "src/main.py",
    "file_version_info.txt",
    "setup.py",
    "manifest.xml",
]

# Regular expressions to match version patterns in different files
VERSION_PATTERNS = {
    "src/main.py": r'APP_VERSION = "[0-9]+\.[0-9]+\.[0-9]+"',
    "setup.py": r'version="[0-9]+\.[0-9]+\.[0-9]+"',
    "file_version_info.txt": [
        r"filevers=\([0-9]+,[0-9]+,[0-9]+,[0-9]+\)",
        r"prodvers=\([0-9]+,[0-9]+,[0-9]+,[0-9]+\)",
        r"StringStruct\(u\'FileVersion\', u\'[0-9]+\.[0-9]+\.[0-9]+\'\)",
        r"StringStruct\(u\'ProductVersion\', u\'[0-9]+\.[0-9]+\.[0-9]+\'\)",
    ],
    "manifest.xml": [
        r'manifestversion="[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+"',
        # Negative lookbehind stops this from also matching the tail of
        # 'manifestversion="..."' (which contains 'version="..."' as a substring).
        r'(?<!manifest)version="[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+"',
    ],
}


def get_latest_tag():
    """Get the latest Git tag."""
    try:
        # Try to get the latest tag
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True,
            text=True,
            check=True,
        )
        tag = result.stdout.strip()

        # Remove 'v' prefix if present
        if tag.startswith("v"):
            tag = tag[1:]

        return tag
    except subprocess.CalledProcessError:
        print("Warning: No Git tags found. Using default version 0.0.0.")
        return "0.0.0"


def validate_version(version):
    """Validate that the version string is in the correct format."""
    if not re.match(r"^[0-9]+\.[0-9]+\.[0-9]+(\.[0-9]+)?$", version):
        print(f"Error: Version {version} does not match the required format X.Y.Z or X.Y.Z.W")
        return False
    return True


def update_version_in_file(file_path, version, relative_path=None):
    """Update version in a specific file.

    `file_path` is the actual filesystem path to read/write. `relative_path`
    is the key used to look up VERSION_PATTERNS and select file-specific
    handling (e.g. "manifest.xml", "src/main.py") -- these must match the
    keys in VERSION_FILES/VERSION_PATTERNS, which are relative, not the
    resolved absolute path. Defaults to file_path if not given (for direct
    callers that already pass a relative path).
    """
    if relative_path is None:
        relative_path = file_path

    if not os.path.exists(file_path):
        print(f"Error: File {file_path} not found.")
        return False

    # Get the appropriate pattern for this file
    patterns = VERSION_PATTERNS.get(relative_path)
    if not patterns:
        print(f"Error: No version pattern defined for {relative_path}.")
        return False

    with open(file_path, "r", encoding="utf-8", newline="") as file:
        content = file.read()

    # Make a copy of the content to check if any changes were made
    original_content = content

    # Prepare Windows-style version (4 parts)
    v_parts = version.split(".")
    while len(v_parts) < 4:
        v_parts.append("0")
    windows_version = ".".join(v_parts)
    v_tuple = ",".join(v_parts)

    # Handle file_version_info.txt specially
    if relative_path == "file_version_info.txt":
        # Process multiple patterns
        for pattern in patterns:
            if "filevers" in pattern or "prodvers" in pattern:
                replacement = f'{pattern.split("=")[0]}=({v_tuple})'
                content = re.sub(pattern, replacement, content)
            elif "FileVersion" in pattern:
                replacement = f"StringStruct(u'FileVersion', u'{version}')"
                content = re.sub(pattern, replacement, content)
            elif "ProductVersion" in pattern:
                replacement = f"StringStruct(u'ProductVersion', u'{version}')"
                content = re.sub(pattern, replacement, content)

    # Handle manifest.xml
    elif relative_path == "manifest.xml":
        # Process multiple patterns with Windows-style version.
        # The XML declaration's version attribute is never touched here.
        for pattern in patterns:
            if "manifestversion=" in pattern:
                replacement = f'manifestversion="{windows_version}"'
                content = re.sub(pattern, replacement, content)
            elif "version=" in pattern:
                replacement = f'version="{windows_version}"'
                content = re.sub(pattern, replacement, content)

    # Handle other files
    elif relative_path == "src/main.py":
        replacement = f'APP_VERSION = "{version}"'
        content = re.sub(patterns, replacement, content)

    elif relative_path == "setup.py":
        replacement = f'version="{version}"'
        content = re.sub(patterns, replacement, content)

    # Check if content was modified
    if content == original_content:
        print(f"No version update needed in {relative_path}")
        return False

    # Write updated content
    with open(file_path, "w", encoding="utf-8", newline="") as file:
        file.write(content)

    print(f"Updated version to {version} in {relative_path}")
    return True


def get_installed_version(package_name):
    """Return the installed version string for package_name, or None if not installed."""
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        print(f"Warning: {package_name} is not installed in this environment; skipping.")
        return None


def pin_requirements_file(root_dir, versions):
    """Rewrite requirements.txt, pinning any line for a package in `versions`
    to an exact `==` version. Comments, blank lines, and unrelated packages
    are left untouched. Packages in `versions` not already present are
    appended at the end. Returns True if the file content changed.
    """
    req_path = os.path.join(root_dir, REQUIREMENTS_FILE)
    existing_lines = []
    line_ending = "\n"
    if os.path.exists(req_path):
        with open(req_path, "r", encoding="utf-8", newline="") as file:
            raw = file.read()
        if "\r\n" in raw:
            line_ending = "\r\n"
        existing_lines = raw.splitlines()

    name_pattern = re.compile(r"^([A-Za-z0-9_.\-]+)\s*(==|>=|<=|~=|>|<)\s*[0-9A-Za-z.\-]+")
    seen = set()
    new_lines = []
    for line in existing_lines:
        stripped = line.strip()
        match = name_pattern.match(stripped) if stripped and not stripped.startswith("#") else None
        pkg_name = match.group(1).lower() if match else None
        if pkg_name in versions:
            new_lines.append(f"{pkg_name}=={versions[pkg_name]}")
            seen.add(pkg_name)
        else:
            new_lines.append(line)

    for pkg_name, version in versions.items():
        if pkg_name not in seen:
            new_lines.append(f"{pkg_name}=={version}")

    new_content = line_ending.join(new_lines) + line_ending
    old_content = line_ending.join(existing_lines) + line_ending if existing_lines else ""

    if new_content == old_content:
        print(f"No changes needed in {REQUIREMENTS_FILE}")
        return False

    with open(req_path, "w", encoding="utf-8", newline="") as file:
        file.write(new_content)
    print(f"Updated {REQUIREMENTS_FILE} with pinned versions: {versions}")
    return True


def pin_workflow_pyinstaller_version(root_dir, pyinstaller_version):
    """Update the `pip install pyinstaller==X.Y.Z ...` line in build.yml.

    Returns True if the file was changed, False if not found/unchanged.
    """
    workflow_path = os.path.join(root_dir, WORKFLOW_FILE)
    if not os.path.exists(workflow_path):
        print(f"Warning: {WORKFLOW_FILE} not found; skipping workflow pin.")
        return False

    with open(workflow_path, "r", encoding="utf-8", newline="") as file:
        content = file.read()

    pattern = r"pyinstaller==[0-9]+(\.[0-9]+)*"
    replacement = f"pyinstaller=={pyinstaller_version}"
    new_content, count = re.subn(pattern, replacement, content)

    if count == 0:
        print(f"Warning: no 'pyinstaller==X.Y.Z' pin found in {WORKFLOW_FILE}; skipping.")
        return False

    if new_content == content:
        print(f"No changes needed in {WORKFLOW_FILE}")
        return False

    with open(workflow_path, "w", encoding="utf-8", newline="") as file:
        file.write(new_content)
    print(f"Updated {WORKFLOW_FILE} to pin pyinstaller=={pyinstaller_version}")
    return True


def pin_dependency_versions(root_dir):
    """Detect installed versions of PINNED_DEPENDENCIES and pin them in
    requirements.txt (all of them) and build.yml (pyinstaller only).

    Returns True if anything was changed.
    """
    versions = {}
    for package_name in PINNED_DEPENDENCIES:
        version = get_installed_version(package_name)
        if version:
            versions[package_name.lower()] = version

    if not versions:
        print("No installed versions found for pinning; nothing to do.")
        return False

    changed = pin_requirements_file(root_dir, versions)

    pyinstaller_version = versions.get("pyinstaller")
    if pyinstaller_version:
        changed = pin_workflow_pyinstaller_version(root_dir, pyinstaller_version) or changed

    return changed


def has_uncommitted_changes():
    """Return True if there are uncommitted changes to tracked files.

    Untracked files are ignored (`git status --porcelain` without `-uall`
    only reports them as a single `??` summary line per file/dir, which we
    filter out here since new/untracked files aren't what a tag needs to
    reflect).
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"Warning: Could not check Git status: {e}")
        return False

    tracked_changes = [line for line in result.stdout.splitlines() if not line.startswith("??")]
    return bool(tracked_changes)


def create_git_tag(version):
    """Create a Git tag for the version."""
    tag_name = f"v{version}"
    try:
        # Check if tag already exists
        result = subprocess.run(
            ["git", "tag", "-l", tag_name],
            capture_output=True,
            text=True,
            check=True,
        )
        if tag_name in result.stdout.splitlines():
            print(f"Error: Tag {tag_name} already exists.")
            return False

        # Create the tag
        subprocess.run(
            ["git", "tag", "-a", tag_name, "-m", f"Release {version}"],
            check=True,
        )
        print(f"Created Git tag: {tag_name}")
        print(f"To push this tag, run: git push origin {tag_name}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error creating Git tag: {e}")
        return False


def main():
    """Main function to update version numbers."""
    parser = argparse.ArgumentParser(description="Update version numbers in source files.")
    parser.add_argument("version", nargs="?", help="Version number to set (format: X.Y.Z)")
    parser.add_argument(
        "--tag",
        action="store_true",
        help="Create a Git tag for the version (refuses if tracked files have "
        "uncommitted changes, unless --commit or --force-tag is also given)",
    )
    parser.add_argument(
        "--force-tag",
        action="store_true",
        help="Create the tag even if there are uncommitted changes to tracked files",
    )
    parser.add_argument("--commit", action="store_true", help="Commit the version changes")
    parser.add_argument(
        "--pin-deps",
        action="store_true",
        help="Pin requirements.txt and build.yml's pyinstaller version to what's installed locally",
    )
    args = parser.parse_args()

    # Get the current directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(script_dir)

    # Change to the root directory
    os.chdir(root_dir)

    if args.version:
        # Use the provided version
        version = args.version
        # Remove 'v' prefix if present
        if version.startswith("v"):
            version = version[1:]

        if not validate_version(version):
            sys.exit(1)
    else:
        # Get the latest tag and increment the patch version
        current_version = get_latest_tag()
        if not current_version:
            sys.exit(1)

        try:
            major, minor, patch = map(int, current_version.split("."))
            patch += 1
            version = f"{major}.{minor}.{patch}"
            print(f"Incrementing patch version from {current_version} to {version}")
        except ValueError:
            print(f"Error parsing version: {current_version}")
            sys.exit(1)

    # Standardize to 3-part version for most files, with special handling for Windows files
    print(f"Setting version to: {version}")

    # For display purposes, show the 4-part version that will be used in Windows files
    v_parts = version.split(".")
    while len(v_parts) < 4:
        v_parts.append("0")
    windows_version = ".".join(v_parts)
    print(f"Windows version will be: {windows_version}")

    # Update version in each file
    updated = False
    for file_path in VERSION_FILES:
        absolute_path = os.path.join(root_dir, file_path)
        if update_version_in_file(absolute_path, version, relative_path=file_path):
            updated = True

    # Optionally pin build dependency versions to what's installed locally
    deps_updated = False
    if args.pin_deps:
        deps_updated = pin_dependency_versions(root_dir)

    if updated or deps_updated:
        print("Version numbers updated successfully." if updated else "Dependency pins updated.")
    else:
        print("No version updates were needed.")

    # Optionally commit the changes
    if args.commit:
        if updated or deps_updated:
            files_to_commit = list(VERSION_FILES)
            if deps_updated:
                files_to_commit += [REQUIREMENTS_FILE, WORKFLOW_FILE]
            try:
                subprocess.run(
                    ["git", "add"] + files_to_commit,
                    check=True,
                )
                commit_msg = (
                    f"Update version to {version}" if updated else "Pin build dependency versions"
                )
                subprocess.run(
                    ["git", "commit", "-m", commit_msg],
                    check=True,
                )
                print("Changes committed.")
            except subprocess.CalledProcessError as e:
                print(f"Warning: Failed to commit changes: {e}")
        else:
            print("--commit had nothing to commit: no version or dependency changes were made.")

    # Optionally create a tag
    if args.tag:
        if has_uncommitted_changes() and not args.force_tag:
            print(
                "Error: Not creating tag -- uncommitted changes to tracked files exist, "
                "so the tag would not reflect them. Use --commit to include them first, "
                "or --force-tag to tag anyway."
            )
        else:
            create_git_tag(version)

    return 0


if __name__ == "__main__":
    sys.exit(main())
