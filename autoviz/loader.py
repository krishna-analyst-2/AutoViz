import logging
import os

import pandas as pd

log = logging.getLogger(__name__)

REQUIRED_COLUMNS = ["timestamp", "campaign", "impressions", "clicks", "conversions"]
NUMERIC_COLUMNS = ["impressions", "clicks", "conversions", "spend"]


class CSVDataLoader:
    """Loads campaign data from a CSV file and drops rows that can't be used."""

    def __init__(self, max_rows=5000):
        self.max_rows = max_rows
        self.last_error = None

    def load_data(self, filepath):
        self.last_error = None
        if not os.path.exists(filepath):
            self.last_error = f"CSV file not found: {filepath}"
            return None
        try:
            # skip lines with the wrong field count (e.g. a line still being written)
            df = pd.read_csv(filepath, on_bad_lines="skip", skipinitialspace=True)
        except pd.errors.EmptyDataError:
            self.last_error = "CSV file is empty - waiting for data"
            return None
        except (OSError, pd.errors.ParserError, UnicodeDecodeError) as exc:
            self.last_error = f"Could not read CSV: {exc}"
            return None

        df.columns = [str(c).strip().lower() for c in df.columns]
        if not self.validate(df):
            return None
        return self._clean(df)

    def validate(self, df):
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            self.last_error = (
                f"CSV is missing required column(s): {', '.join(missing)}. "
                f"Expected: {', '.join(REQUIRED_COLUMNS)} [, spend]"
            )
            return False
        return True

    def _clean(self, df):
        cols = REQUIRED_COLUMNS + (["spend"] if "spend" in df.columns else [])
        df = df[cols].copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df["campaign"] = df["campaign"].astype(str).str.strip()
        numeric = [c for c in NUMERIC_COLUMNS if c in df.columns]
        for col in numeric:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        bad = df[REQUIRED_COLUMNS].isna().any(axis=1) | df["campaign"].isin(["", "nan"])
        bad |= (df[numeric] < 0).any(axis=1)
        if bad.any():
            log.warning("Skipped %d malformed row(s)", int(bad.sum()))
        df = df[~bad]
        if "spend" in df.columns:
            df["spend"] = df["spend"].fillna(0.0)
        return df.sort_values("timestamp").tail(self.max_rows).reset_index(drop=True)
