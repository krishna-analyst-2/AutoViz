"""Replays the prepared history into a live CSV one day at a time, so the
dashboard has something to react to.

    python scripts/simulate_stream.py --interval 2 --prefill 10
"""
import argparse
import os
import random
import sys
import time

import pandas as pd


def append_rows(path, rows, write_header):
    rows.to_csv(path, mode="w" if write_header else "a", header=write_header, index=False)


def main(argv=None):
    p = argparse.ArgumentParser(description="Stream campaign history into a live CSV.")
    p.add_argument("--source", default="data/campaign_history.csv",
                   help="prepared history CSV (from scripts/prepare_data.py)")
    p.add_argument("--out", default="data/live_campaigns.csv", help="live CSV to append to")
    p.add_argument("--interval", type=float, default=2.0,
                   help="seconds between new data batches (default: 2)")
    p.add_argument("--prefill", type=int, default=5,
                   help="timestamps to write immediately so the chart isn't empty (default: 5)")
    p.add_argument("--bad-rows", type=float, default=0.0, metavar="P",
                   help="chance of also writing a broken row each tick, to test error handling")
    p.add_argument("--loop", action="store_true", help="start over when the history runs out")
    args = p.parse_args(argv)

    if not os.path.exists(args.source):
        sys.exit(f"{args.source} not found. Run: python scripts/prepare_data.py")
    history = pd.read_csv(args.source)
    batches = [g for _, g in history.groupby("timestamp", sort=True)]
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)

    print(f"Streaming {len(batches)} timestamps from {args.source} -> {args.out} "
          f"every {args.interval}s (Ctrl+C to stop)")
    first, i = True, 0
    try:
        while True:
            if i >= len(batches):
                if not args.loop:
                    print("History exhausted - done.")
                    return 0
                i, first = 0, True
            append_rows(args.out, batches[i], write_header=first)
            first = False
            if args.bad_rows and random.random() < args.bad_rows:
                with open(args.out, "a", encoding="utf-8") as f:
                    f.write(random.choice(["garbage,row\n", "2021-13-45,Email,abc,-5,x,1\n",
                                           ",,,,\n"]))
            print(f"[{time.strftime('%H:%M:%S')}] +{len(batches[i])} rows "
                  f"for {batches[i]['timestamp'].iloc[0]}")
            i += 1
            if i > args.prefill:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
