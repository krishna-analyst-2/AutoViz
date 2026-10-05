"""Download a Kaggle marketing dataset and convert it to the AutoViz CSV format.

    python scripts/prepare_data.py
    python scripts/prepare_data.py --source facebook
    python scripts/prepare_data.py --input marketing_campaign_dataset.csv
"""
import argparse
import glob
import os
import sys

import pandas as pd

SOURCES = {
    "campaigns": "manishabhatt22/marketing-campaign-performance-dataset",
    "facebook": "madislemsalu/facebook-ad-campaign",
}
OUTPUT_COLUMNS = ["timestamp", "campaign", "impressions", "clicks", "conversions", "spend"]


def download(source):
    try:
        import kagglehub
    except ImportError:
        sys.exit("kagglehub is not installed. Run: pip install kagglehub")
    folder = kagglehub.dataset_download(SOURCES[source])
    csvs = glob.glob(os.path.join(folder, "**", "*.csv"), recursive=True)
    if not csvs:
        sys.exit(f"No CSV found in downloaded dataset at {folder}")
    return csvs[0]


def from_campaigns(raw):
    # 200k campaigns over 2021, conversions come from clicks * conversion rate
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(raw["Date"], errors="coerce"),
        "campaign": raw["Campaign_Type"],
        "impressions": pd.to_numeric(raw["Impressions"], errors="coerce"),
        "clicks": pd.to_numeric(raw["Clicks"], errors="coerce"),
        "spend": pd.to_numeric(
            raw["Acquisition_Cost"].astype(str).str.replace(r"[$,]", "", regex=True),
            errors="coerce"),
    })
    df["conversions"] = (df["clicks"] * pd.to_numeric(raw["Conversion_Rate"],
                                                      errors="coerce")).round()
    return df


def from_facebook(raw):
    # ~1.1k ads, Aug 2017. Some rows in this file have shifted columns and get dropped.
    return pd.DataFrame({
        "timestamp": pd.to_datetime(raw["reporting_start"], format="%d/%m/%Y", errors="coerce"),
        "campaign": "Campaign " + raw["campaign_id"].astype(str),
        "impressions": pd.to_numeric(raw["impressions"], errors="coerce"),
        "clicks": pd.to_numeric(raw["clicks"], errors="coerce"),
        "conversions": pd.to_numeric(raw["total_conversion"], errors="coerce"),
        "spend": pd.to_numeric(raw["spent"], errors="coerce"),
    })


def main(argv=None):
    p = argparse.ArgumentParser(description="Prepare a Kaggle marketing dataset for AutoViz.")
    p.add_argument("--source", choices=SOURCES, default="campaigns",
                   help="which Kaggle dataset to use (default: campaigns)")
    p.add_argument("--input", help="path to an already-downloaded Kaggle CSV (skips download)")
    p.add_argument("--out", default="data/campaign_history.csv", help="output CSV path")
    args = p.parse_args(argv)

    path = args.input or download(args.source)
    print(f"Reading {path}")
    raw = pd.read_csv(path)
    df = (from_campaigns if args.source == "campaigns" else from_facebook)(raw)

    before = len(df)
    df = df.dropna()
    print(f"Dropped {before - len(df)} incomplete row(s) of {before}")
    daily = (df.groupby(["timestamp", "campaign"], as_index=False)
               [["impressions", "clicks", "conversions", "spend"]].sum()
               .sort_values(["timestamp", "campaign"]))
    daily["timestamp"] = daily["timestamp"].dt.strftime("%Y-%m-%d %H:%M")
    for col in ("impressions", "clicks", "conversions"):
        daily[col] = daily[col].astype(int)
    daily["spend"] = daily["spend"].round(2)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    daily[OUTPUT_COLUMNS].to_csv(args.out, index=False)
    print(f"Wrote {len(daily)} rows ({daily['timestamp'].nunique()} days, "
          f"{daily['campaign'].nunique()} campaigns) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
