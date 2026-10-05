import argparse
import logging
import os

from .controller import AutoVizController
from .loader import CSVDataLoader
from .plotter import PlotManager
from .processor import DataProcessor

log = logging.getLogger("autoviz")


def positive_float(value):
    try:
        f = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{value}' is not a number")
    if f <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return f


def positive_int(value):
    try:
        i = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{value}' is not a whole number")
    if i <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return i


def build_parser():
    p = argparse.ArgumentParser(
        prog="autoviz",
        description="Real-time marketing dashboard for a CSV file.",
        epilog="CSV columns: timestamp, campaign, impressions, clicks, conversions [, spend]\n"
               "Example: python -m autoviz --csv data/live_campaigns.csv --refresh 5",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--csv", required=True, help="path to the marketing CSV file")
    p.add_argument("--refresh", type=positive_float, default=5.0,
                   help="refresh interval in seconds (default: 5)")
    p.add_argument("--window", type=positive_int, default=30,
                   help="number of most recent timestamps to plot (default: 30)")
    p.add_argument("--max-rows", type=positive_int, default=5000,
                   help="only keep the last N rows of the CSV in memory (default: 5000)")
    p.add_argument("--campaigns", nargs="+", metavar="NAME", help="only plot these campaigns")
    p.add_argument("--no-watch", action="store_true",
                   help="only reload on the refresh interval, not as soon as the file changes")
    p.add_argument("--snapshot", metavar="PNG",
                   help="render the dashboard once to an image file and exit")
    p.add_argument("-v", "--verbose", action="store_true", help="show debug logging")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("matplotlib").setLevel(logging.WARNING)

    if args.snapshot:
        import matplotlib
        matplotlib.use("Agg")
    if not os.path.exists(args.csv):
        log.warning("%s does not exist yet - waiting for it to appear", args.csv)

    controller = AutoVizController(
        csv_path=args.csv,
        refresh=args.refresh,
        loader=CSVDataLoader(max_rows=args.max_rows),
        processor=DataProcessor(window=args.window, campaigns=args.campaigns),
        plotter=PlotManager(),
        watch=not args.no_watch,
    )

    if args.snapshot:
        controller.plotter.init_plot()
        ok = controller.update_once()
        os.makedirs(os.path.dirname(os.path.abspath(args.snapshot)), exist_ok=True)
        controller.plotter.fig.savefig(args.snapshot, dpi=110)
        log.info("Saved snapshot to %s", args.snapshot)
        return 0 if ok else 1

    controller.run()
    return 0
