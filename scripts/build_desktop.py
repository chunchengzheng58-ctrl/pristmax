#!/usr/bin/env python3
"""
Pristmax Desktop Build Script

Usage:
    python scripts/build_desktop.py          # Build for current platform
    python scripts/build_desktop.py --clean # Clean build artifacts
"""

import os
import sys
import shutil
import subprocess
import argparse
from pathlib import Path

# Project root
ROOT = Path(__file__).parent.parent.resolve()
DIST = ROOT / "dist"
BUILD = ROOT / "build"


def run(cmd, cwd=None, shell=False):
    """Run command and print output"""
    print(f"\n>>> {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    result = subprocess.run(
        cmd if shell else " ".join(cmd) if isinstance(cmd, list) else cmd,
        shell=shell,
        cwd=cwd or ROOT,
        capture_output=False
    )
    return result.returncode == 0


def check_dependencies():
    """Check if required dependencies are installed"""
    required = ["pyinstaller"]
    missing = []

    for pkg in required:
        try:
            __import__(pkg.replace("-", "_"))
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"❌ Missing dependencies: {', '.join(missing)}")
        print(f"   Install with: pip install {' '.join(missing)}")
        return False
    return True


def clean():
    """Clean build artifacts"""
    print("\n🧹 Cleaning build artifacts...")

    dirs_to_remove = [DIST, BUILD]
    for d in dirs_to_remove:
        if d.exists():
            shutil.rmtree(d)
            print(f"   Removed: {d}")

    # Remove spec backup if exists
    for f in ROOT.glob("*.spec.bak"):
        f.unlink()
        print(f"   Removed: {f}")

    print("✅ Clean complete")


def build_windows():
    """Build Windows executable"""
    print("\n🪟 Building Windows executable...")

    if not (ROOT / "main.spec").exists():
        print("❌ main.spec not found")
        return False

    # Create dist directory
    DIST.mkdir(exist_ok=True)

    # Build with PyInstaller
    cmd = ["pyinstaller", "main.spec", "--noconfirm"]
    if not run(cmd):
        return False

    # Verify output
    exe_path = DIST / "Pristmax.exe"
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"\n✅ Build complete: {exe_path}")
        print(f"   Size: {size_mb:.1f} MB")
        return True
    else:
        print(f"\n❌ Build failed: {exe_path} not found")
        return False


def build_unix():
    """Build Unix/Linux/macOS executable"""
    print("\n🐧 Building Unix executable...")

    # Create dist directory
    DIST.mkdir(exist_ok=True)

    # Simple Python launcher for Unix
    launcher = DIST / "pristmax"
    with open(launcher, "w") as f:
        f.write(f"""#!/bin/bash
cd "$(dirname "$0")"
python3 -c "
import sys
sys.path.insert(0, '{ROOT}')
from src.pristmax.api.server import app
app.run(host='0.0.0.0', port=5000, debug=False)
"
""")
    launcher.chmod(0o755)
    print(f"✅ Launcher created: {launcher}")
    print("   Run with: ./pristmax")
    return True


def main():
    parser = argparse.ArgumentParser(description="Pristmax Desktop Build Script")
    parser.add_argument("--clean", action="store_true", help="Clean build artifacts")
    parser.add_argument("--platform", choices=["win", "unix", "auto"], default="auto",
                        help="Target platform (default: auto-detect)")
    args = parser.parse_args()

    print("=" * 50)
    print("Pristmax Desktop Build")
    print("=" * 50)

    if args.clean:
        clean()
        return

    if not check_dependencies():
        sys.exit(1)

    # Detect platform
    platform = args.platform
    if platform == "auto":
        if sys.platform == "win32":
            platform = "win"
        else:
            platform = "unix"

    # Build
    if platform == "win":
        success = build_windows()
    else:
        success = build_unix()

    if success:
        print("\n" + "=" * 50)
        print("🎉 Build successful!")
        print("=" * 50)
    else:
        print("\n❌ Build failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
