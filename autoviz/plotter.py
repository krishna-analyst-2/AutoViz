from datetime import datetime

from matplotlib.ticker import FuncFormatter

TITLE = "AutoViz - Live Marketing Dashboard"


def short_number(n):
    for size, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(n) >= size:
            return f"{n / size:.1f}{suffix}"
    return f"{n:.0f}"


_short_axis = FuncFormatter(lambda v, _: short_number(v))


class PlotManager:
    def __init__(self, title=TITLE):
        self.title = title
        self.fig = None
        self.axes = None
        self._footer = None
        self._legend = None
        self._colors = {}

    def init_plot(self):
        # pyplot is imported here so --snapshot can switch to the Agg backend first
        import matplotlib.pyplot as plt

        self.fig, axes = plt.subplots(2, 2, figsize=(13, 8))
        self.axes = axes.flatten()
        self.fig.canvas.manager.set_window_title("AutoViz")
        self.show_message("Waiting for data...", waiting=True)
        return self.fig

    def _color(self, campaign):
        if campaign not in self._colors:
            import matplotlib.pyplot as plt

            palette = plt.get_cmap("tab10").colors
            self._colors[campaign] = palette[len(self._colors) % len(palette)]
        return self._colors[campaign]

    def _set_footer(self, text):
        if self._footer is not None:
            self._footer.remove()
        self._footer = self.fig.text(0.99, 0.005, text, ha="right", fontsize=8, color="gray")

    def _clear(self):
        for ax in self.axes:
            ax.clear()
            ax.set_axis_off()
        if self._legend is not None:
            self._legend.remove()
            self._legend = None

    def show_message(self, message, waiting=False):
        self._clear()
        self._set_footer(f"last checked {datetime.now():%H:%M:%S}")
        self.axes[0].text(0.5, 0.5, message, transform=self.fig.transFigure,
                          ha="center", va="center", wrap=True,
                          fontsize=14 if waiting else 12,
                          color="dimgray" if waiting else "firebrick")
        self.fig.suptitle(self.title, fontsize=14, fontweight="bold")
        self.fig.canvas.draw_idle()

    def update_plot(self, agg, kpis, source=""):
        if agg.empty:
            self.show_message("No valid rows in the selected window yet.")
            return
        self._clear()
        ax_imp, ax_clk, ax_ctr, ax_conv = self.axes
        campaigns = sorted(agg["campaign"].unique())

        line_charts = [
            (ax_imp, "impressions", "Impressions over time", "Impressions"),
            (ax_clk, "clicks", "Clicks over time", "Clicks"),
            (ax_ctr, "ctr", "Click-through rate (CTR)", "CTR %"),
        ]
        for ax, col, title, ylabel in line_charts:
            ax.set_axis_on()
            for name in campaigns:
                rows = agg[agg["campaign"] == name]
                ax.plot(rows["timestamp"], rows[col], marker="o", markersize=3,
                        linewidth=1.5, label=name, color=self._color(name))
            ax.set_title(title, fontweight="bold")
            ax.set_ylabel(ylabel)
            ax.grid(alpha=0.3)
            ax.tick_params(axis="x", labelrotation=30, labelsize=8)
            if col != "ctr":
                ax.yaxis.set_major_formatter(_short_axis)

        handles, labels = ax_imp.get_legend_handles_labels()
        self._legend = self.fig.legend(handles, labels, loc="upper center", ncol=len(campaigns),
                                       bbox_to_anchor=(0.5, 0.925), fontsize=9, frameon=False)

        totals = agg.groupby("campaign")["conversions"].sum().reindex(campaigns)
        ax_conv.set_axis_on()
        bars = ax_conv.bar(campaigns, totals.values, color=[self._color(c) for c in campaigns])
        ax_conv.bar_label(bars, labels=[short_number(v) for v in totals.values], fontsize=8)
        ax_conv.set_title("Conversions by campaign (window total)", fontweight="bold")
        ax_conv.set_ylabel("Conversions")
        ax_conv.yaxis.set_major_formatter(_short_axis)
        ax_conv.tick_params(axis="x", labelrotation=20, labelsize=8)
        ax_conv.grid(axis="y", alpha=0.3)

        header = (f"Impressions {short_number(kpis['impressions'])}  |  "
                  f"Clicks {short_number(kpis['clicks'])}  |  "
                  f"Conversions {short_number(kpis['conversions'])}  |  "
                  f"CTR {kpis['ctr']:.2f}%  |  Conv. rate {kpis['conv_rate']:.2f}%")
        if "spend" in kpis:
            header += f"  |  Spend {short_number(kpis['spend'])}  |  CPA {kpis['cpa']:.2f}"
        self.fig.suptitle(f"{self.title}\n{header}", fontsize=11, fontweight="bold")

        latest = agg["timestamp"].max()
        self._set_footer(f"{source}  |  data up to {latest:%Y-%m-%d %H:%M}  |  "
                         f"refreshed {datetime.now():%H:%M:%S}")
        self.fig.tight_layout(rect=(0, 0.02, 1, 0.93))
        self.fig.canvas.draw_idle()

    def reset(self):
        self.show_message("Plot error - retrying on next update...")
