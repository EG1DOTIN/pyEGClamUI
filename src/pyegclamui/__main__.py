"""
Direct module execution support: `python -m pyegclamui`
"""

import sys
from pyegclamui.gui.app import main

if __name__ == "__main__":
    sys.exit(main())
