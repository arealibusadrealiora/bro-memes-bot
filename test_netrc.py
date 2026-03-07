#!/usr/bin/env python3
"""Test script to verify .netrc authentication for Instagram"""

import os
import sys
from pathlib import Path

def check_netrc():
    """Check if .netrc file exists and is readable"""
    netrc_path = os.getenv('NETRC_LOCATION', '/app/.netrc')

    print(f"Checking .netrc at: {netrc_path}")

    if not Path(netrc_path).exists():
        print(f"❌ .netrc file not found at {netrc_path}")
        return False

    print(f"✓ .netrc file exists")

    # Check permissions
    stat_info = os.stat(netrc_path)
    mode = oct(stat_info.st_mode)[-3:]
    print(f"  Permissions: {mode}")

    if mode != '600':
        print(f"⚠️  Warning: .netrc should have 600 permissions, but has {mode}")

    # Try to read and parse
    try:
        with open(netrc_path, 'r') as f:
            content = f.read()

        if 'machine instagram' in content:
            # Check if it's commented
            lines = content.split('\n')
            instagram_lines = [l for l in lines if 'machine instagram' in l]

            if all(l.strip().startswith('#') for l in instagram_lines):
                print("❌ Instagram credentials are commented out in .netrc")
                return False
            else:
                print("✓ Instagram credentials found in .netrc")
                # Don't print actual credentials
                return True
        else:
            print("❌ No Instagram credentials in .netrc")
            return False

    except Exception as e:
        print(f"❌ Error reading .netrc: {e}")
        return False

if __name__ == '__main__':
    success = check_netrc()
    sys.exit(0 if success else 1)
