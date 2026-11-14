"""Print the current 6-digit step-up code for a key (testing helper, no phone needed).

Usage:  .venv/bin/python scripts/code.py YOURKEY
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from store import totp  # noqa: E402

if len(sys.argv) != 2:
    sys.exit("Usage: .venv/bin/python scripts/code.py YOURKEY")
print(totp(sys.argv[1].strip().upper()))
