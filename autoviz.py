"""Entry point so the tool can be started with `python autoviz.py --csv data.csv --refresh 5`."""
import sys

from autoviz.cli import main

if __name__ == "__main__":
    sys.exit(main())
