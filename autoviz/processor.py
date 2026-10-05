from .loader import NUMERIC_COLUMNS


def _pct(num, den):
    return (100.0 * num / den.where(den != 0)).fillna(0.0)


class DataProcessor:
    def __init__(self, window=30, campaigns=None):
        self.window = window
        self.campaigns = campaigns

    def filter(self, df):
        """Keep selected campaigns and only the latest `window` timestamps."""
        if self.campaigns:
            df = df[df["campaign"].isin(self.campaigns)]
        if self.window and not df.empty:
            recent = df["timestamp"].drop_duplicates().nlargest(self.window)
            df = df[df["timestamp"].isin(recent)]
        return df

    def aggregate(self, df):
        metrics = [c for c in NUMERIC_COLUMNS if c in df.columns]
        out = df.groupby(["timestamp", "campaign"], as_index=False)[metrics].sum()
        out["ctr"] = _pct(out["clicks"], out["impressions"])
        out["conv_rate"] = _pct(out["conversions"], out["clicks"])
        return out.sort_values("timestamp")

    @staticmethod
    def summary(df):
        imp = float(df["impressions"].sum())
        clk = float(df["clicks"].sum())
        conv = float(df["conversions"].sum())
        kpis = {
            "impressions": imp,
            "clicks": clk,
            "conversions": conv,
            "ctr": 100.0 * clk / imp if imp else 0.0,
            "conv_rate": 100.0 * conv / clk if clk else 0.0,
        }
        if "spend" in df.columns:
            kpis["spend"] = float(df["spend"].sum())
            kpis["cpa"] = kpis["spend"] / conv if conv else 0.0
        return kpis
