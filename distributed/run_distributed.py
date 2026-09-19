# -*- coding: utf-8 -*-
"""
Distributed Storage System - Web Console Runner

Starts the web console for the distributed storage system.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import webbrowser
import time

from distributed.api import app

def main():
    print("\n" + "="*70)
    print("Distributed Storage System - Web Console")
    print("="*70)

    print("\n[1] System Features:")
    print("  - Cluster Overview (nodes, health, hash ring)")
    print("  - Node Management (register, heartbeat, load)")
    print("  - Task Scheduling (scan tasks, progress)")
    print("  - Sharding (consistent hash, routing)")
    print("  - Storage Analytics (dedup stats, ROI)")

    print("\n[2] Starting web server...")
    print("  URL: http://localhost:5001")
    print("  Press Ctrl+C to stop")

    # Open browser after a short delay
    time.sleep(1)
    webbrowser.open('http://localhost:5001')

    # Run Flask app
    app.run(host='0.0.0.0', port=5001, debug=False)


if __name__ == '__main__':
    main()
