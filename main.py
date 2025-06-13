#!/usr/bin/env python3
"""
Main entry point for Google Photos Takeout Processor.
This is a wrapper around takeout-processor.py for backwards compatibility.
"""

import sys
from pathlib import Path

# Import the takeout processor
sys.path.insert(0, str(Path(__file__).parent))
from takeout_processor import main

if __name__ == "__main__":
    # Call the takeout processor's main function
    main()