#!/usr/bin/env python3
"""
Startup script for Telegram Callback Handler
Runs the handler that listens for inline button presses
"""

import sys
from pathlib import Path

# Add parent directory to path so we can import flathunter
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import and run the callback handler
from flathunter.telegram_callback_handler import main

if __name__ == "__main__":
    main()
