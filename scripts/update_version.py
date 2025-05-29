#!/usr/bin/env python
"""
Update version numbers in source files.

This script should be run before creating a new release tag.
It updates the version number in main.py and optionally creates
a Git tag for the new version.

Usage:
    python scripts/update_version.py [version]
    
Examples:
    # Update to version 1.2.3
    python scripts/update_version.py 1.2.3
    
    # Update to version 1.2.3 and create a tag
    python scripts/update_version.py 1.2.3 --tag
"""

import argparse
import os
import re
import subprocess
import sys

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
        r'filevers=\([0-9]+,[0-9]+,[0-9]+,[0-9]+\)',
        r'prodvers=\([0-9]+,[0-9]+,[0-9]+,[0-9]+\)',
        r'StringStruct\(u\'FileVersion\', u\'[0-9]+\.[0-9]+\.[0-9]+\'\)',
        r'StringStruct\(u\'ProductVersion\', u\'[0-9]+\.[0-9]+\.[0-9]+\'\)'
    ],
    "manifest.xml": [
        r'<\?xml version="[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+"',
        r'manifestversion="[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+"',
        r'version="[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+"'
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
        if tag.startswith('v'):
            tag = tag[1:]
            
        return tag
    except subprocess.CalledProcessError:
        print("Warning: No Git tags found. Using default version 0.0.0.")
        return "0.0.0"

def validate_version(version):
    """Validate that the version string is in the correct format."""
    if not re.match(r'^[0-9]+\.[0-9]+\.[0-9]+(\.[0-9]+)?$', version):
        print(f"Error: Version {version} does not match the required format X.Y.Z or X.Y.Z.W")
        return False
    return True

def update_version_in_file(file_path, version):
    """Update version in a specific file."""
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} not found.")
        return False
    
    # Get the appropriate pattern for this file
    patterns = VERSION_PATTERNS.get(file_path)
    if not patterns:
        print(f"Error: No version pattern defined for {file_path}.")
        return False
    
    with open(file_path, 'r') as file:
        content = file.read()
    
    # Make a copy of the content to check if any changes were made
    original_content = content
    
    # Prepare Windows-style version (4 parts)
    v_parts = version.split('.')
    while len(v_parts) < 4:
        v_parts.append('0')
    windows_version = '.'.join(v_parts)
    v_tuple = ','.join(v_parts)
    
    # Handle file_version_info.txt specially
    if file_path == "file_version_info.txt":
        # Process multiple patterns
        for pattern in patterns:
            if 'filevers' in pattern or 'prodvers' in pattern:
                replacement = f'{pattern.split("=")[0]}=({v_tuple})'
                content = re.sub(pattern, replacement, content)
            elif 'FileVersion' in pattern:
                replacement = f'StringStruct(u\'FileVersion\', u\'{version}\')'
                content = re.sub(pattern, replacement, content)
            elif 'ProductVersion' in pattern:
                replacement = f'StringStruct(u\'ProductVersion\', u\'{version}\')'
                content = re.sub(pattern, replacement, content)
    
    # Handle manifest.xml
    elif file_path == "manifest.xml":
        # Process multiple patterns with Windows-style version
        for pattern in patterns:
            if 'xml version=' in pattern:
                replacement = f'<?xml version="{windows_version}"'
                content = re.sub(pattern, replacement, content)
            elif 'manifestversion=' in pattern:
                replacement = f'manifestversion="{windows_version}"'
                content = re.sub(pattern, replacement, content)
            elif 'version=' in pattern:
                replacement = f'version="{windows_version}"'
                content = re.sub(pattern, replacement, content)
    
    # Handle other files
    elif file_path == "src/main.py":
        replacement = f'APP_VERSION = "{version}"'
        content = re.sub(patterns, replacement, content)
    
    elif file_path == "setup.py":
        replacement = f'version="{version}"'
        content = re.sub(patterns, replacement, content)
    
    # Check if content was modified
    if content == original_content:
        print(f"No version update needed in {file_path}")
        return False
    
    # Write updated content
    with open(file_path, 'w') as file:
        file.write(content)
    
    print(f"Updated version to {version} in {file_path}")
    return True

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
    parser = argparse.ArgumentParser(description='Update version numbers in source files.')
    parser.add_argument('version', nargs='?', help='Version number to set (format: X.Y.Z)')
    parser.add_argument('--tag', action='store_true', help='Create a Git tag for the version')
    parser.add_argument('--commit', action='store_true', help='Commit the version changes')
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
        if version.startswith('v'):
            version = version[1:]
        
        if not validate_version(version):
            sys.exit(1)
    else:
        # Get the latest tag and increment the patch version
        current_version = get_latest_tag()
        if not current_version:
            sys.exit(1)
        
        try:
            major, minor, patch = map(int, current_version.split('.'))
            patch += 1
            version = f"{major}.{minor}.{patch}"
            print(f"Incrementing patch version from {current_version} to {version}")
        except ValueError:
            print(f"Error parsing version: {current_version}")
            sys.exit(1)
    
    # Standardize to 3-part version for most files, with special handling for Windows files
    print(f"Setting version to: {version}")
    
    # For display purposes, show the 4-part version that will be used in Windows files
    v_parts = version.split('.')
    while len(v_parts) < 4:
        v_parts.append('0')
    windows_version = '.'.join(v_parts)
    print(f"Windows version will be: {windows_version}")
    
    # Update version in each file
    updated = False
    for file_path in VERSION_FILES:
        if update_version_in_file(os.path.join(root_dir, file_path), version):
            updated = True
    
    if updated:
        print("Version numbers updated successfully.")
        
        # Optionally commit the changes
        if args.commit:
            try:
                subprocess.run(
                    ["git", "add"] + VERSION_FILES,
                    check=True,
                )
                subprocess.run(
                    ["git", "commit", "-m", f"Update version to {version}"],
                    check=True,
                )
                print("Changes committed.")
            except subprocess.CalledProcessError as e:
                print(f"Warning: Failed to commit changes: {e}")
                
        # Optionally create a tag
        if args.tag:
            create_git_tag(version)
    else:
        print("No version updates were needed.")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())