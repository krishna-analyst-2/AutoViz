import logging
import os
import time

log = logging.getLogger(__name__)

POLL_SECONDS = 0.5


class AutoVizController:
    def __init__(self, csv_path, refresh, loader, processor, plotter, watch=True):
        self.csv_path = csv_path
        self.refresh = refresh
        self.loader = loader
        self.processor = processor
        self.plotter = plotter
        self.watch = watch
        self._last_sig = None
        self._last_update = 0.0
        self._last_error = None

    def _file_signature(self):
        try:
            st = os.stat(self.csv_path)
            return (st.st_mtime, st.st_size)
        except OSError:
            return None

    def update_once(self):
        """Load, process and redraw. Returns True if something was plotted."""
        self._last_sig = self._file_signature()
        self._last_update = time.monotonic()

        df = self.loader.load_data(self.csv_path)
        if df is None:
            msg = self.loader.last_error or "Unknown error loading CSV"
            if self.loader.waiting:
                self._report(f"Waiting for data - {msg}", level=logging.INFO)
                self.plotter.show_message(f"Waiting for data...\n\n{msg}", waiting=True)
            else:
                self._report(msg)
                self.plotter.show_message(msg)
            return False
        try:
            window_df = self.processor.filter(df)
            agg = self.processor.aggregate(window_df)
            kpis = self.processor.summary(window_df)
        except Exception as exc:
            self._report(f"Data processing error: {exc}")
            return False
        try:
            self.plotter.update_plot(agg, kpis, source=os.path.basename(self.csv_path))
        except Exception as exc:
            self._report(f"Plot rendering error: {exc}")
            self.plotter.reset()
            return False

        if self._last_error:
            log.info("Recovered - plotting %d rows", len(df))
        self._last_error = None
        log.debug("Updated plot with %d rows (%d in window)", len(df), len(window_df))
        return not agg.empty

    def _report(self, message, level=logging.ERROR):
        # only log a message the first time it shows up, not on every tick
        if message != self._last_error:
            log.log(level, message)
        self._last_error = message

    def schedule_update(self):
        due = time.monotonic() - self._last_update >= self.refresh
        changed = self.watch and self._file_signature() != self._last_sig
        if due or changed:
            self.update_once()

    def run(self):
        import matplotlib.pyplot as plt

        fig = self.plotter.init_plot()
        self.update_once()

        interval = min(self.refresh, POLL_SECONDS) if self.watch else self.refresh
        timer = fig.canvas.new_timer(interval=int(interval * 1000))
        timer.add_callback(self.schedule_update)
        timer.start()
        log.info("Watching %s (refresh every %ss%s). Close the window or press Ctrl+C to stop.",
                 self.csv_path, self.refresh, ", instant on change" if self.watch else "")
        try:
            plt.show()
        except KeyboardInterrupt:
            pass
        finally:
            timer.stop()
