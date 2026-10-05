import os
import sys
import tempfile
import time
import unittest

import matplotlib

matplotlib.use("Agg")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import autoviz  # noqa: E402
from autoviz.cli import build_parser, main  # noqa: E402

HEADER = "timestamp,campaign,impressions,clicks,conversions,spend\n"
GOOD_ROWS = (
    "2024-06-01 10:00,Launch,1000,50,5,20.0\n"
    "2024-06-01 10:05,Launch,1200,60,6,22.5\n"
    "2024-06-01 10:00,Retarget,800,40,8,15.0\n"
)


class TempCSV:
    def __init__(self, content=""):
        fd, self.path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)

    def append(self, content):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(content)

    def cleanup(self):
        os.remove(self.path)


def make_controller(path, **kw):
    plotter = autoviz.PlotManager()
    plotter.init_plot()
    return autoviz.AutoVizController(path, refresh=kw.get("refresh", 5.0),
                                     loader=autoviz.CSVDataLoader(),
                                     processor=autoviz.DataProcessor(window=30),
                                     plotter=plotter, watch=kw.get("watch", True))


class TestLoader(unittest.TestCase):
    def setUp(self):
        self.loader = autoviz.CSVDataLoader()

    def test_loads_valid_csv(self):  # FR-1
        csv = TempCSV(HEADER + GOOD_ROWS)
        self.addCleanup(csv.cleanup)
        df = self.loader.load_data(csv.path)
        self.assertEqual(len(df), 3)
        self.assertEqual(set(df["campaign"]), {"Launch", "Retarget"})

    def test_spend_is_optional(self):
        csv = TempCSV("timestamp,campaign,impressions,clicks,conversions\n"
                      "2024-06-01 10:00,Launch,1000,50,5\n")
        self.addCleanup(csv.cleanup)
        df = self.loader.load_data(csv.path)
        self.assertEqual(len(df), 1)
        self.assertNotIn("spend", df.columns)

    def test_skips_malformed_rows(self):  # AC-4
        csv = TempCSV(HEADER + GOOD_ROWS
                      + "not-a-date,Launch,1,1,1,1\n"      # bad timestamp
                      + "2024-06-01 10:10,Launch,abc,5,1,1\n"  # non-numeric
                      + "2024-06-01 10:10,Launch,100,-5,1,1\n"  # negative
                      + "2024-06-01 10:10,,100,5,1,1\n"     # missing campaign
                      + "garbage,row\n"                     # too few fields
                      + "2024-06-01 10:1")                  # half-written line
        self.addCleanup(csv.cleanup)
        df = self.loader.load_data(csv.path)
        self.assertEqual(len(df), 3)

    def test_missing_file(self):  # FR-5
        self.assertIsNone(self.loader.load_data("does/not/exist.csv"))
        self.assertIn("not found", self.loader.last_error)

    def test_empty_file(self):
        csv = TempCSV("")
        self.addCleanup(csv.cleanup)
        self.assertIsNone(self.loader.load_data(csv.path))
        self.assertIn("empty", self.loader.last_error)

    def test_missing_columns(self):
        csv = TempCSV("date,name,views\n2024-06-01,Launch,10\n")
        self.addCleanup(csv.cleanup)
        self.assertIsNone(self.loader.load_data(csv.path))
        self.assertIn("missing required column", self.loader.last_error)

    def test_max_rows_keeps_most_recent(self):
        rows = "".join(f"2024-06-01 10:{m:02d},A,100,10,1,1\n" for m in range(50))
        csv = TempCSV(HEADER + rows)
        self.addCleanup(csv.cleanup)
        df = autoviz.CSVDataLoader(max_rows=10).load_data(csv.path)
        self.assertEqual(len(df), 10)
        self.assertEqual(df["timestamp"].max().minute, 49)


class TestProcessor(unittest.TestCase):
    def setUp(self):
        csv = TempCSV(HEADER + GOOD_ROWS + "2024-06-01 10:00,Launch,500,25,2,10\n")
        self.addCleanup(csv.cleanup)
        self.df = autoviz.CSVDataLoader().load_data(csv.path)

    def test_aggregate_and_derived_metrics(self):
        agg = autoviz.DataProcessor().aggregate(self.df)
        launch_10 = agg[(agg["campaign"] == "Launch") & (agg["timestamp"].dt.minute == 0)]
        self.assertEqual(launch_10["impressions"].iloc[0], 1500)
        self.assertAlmostEqual(launch_10["ctr"].iloc[0], 5.0)
        self.assertAlmostEqual(launch_10["conv_rate"].iloc[0], 100 * 7 / 75)

    def test_zero_division_is_safe(self):
        self.df.loc[:, "impressions"] = 0
        agg = autoviz.DataProcessor().aggregate(self.df)
        self.assertTrue((agg["ctr"] == 0).all())

    def test_window_and_campaign_filter(self):
        p = autoviz.DataProcessor(window=1, campaigns=["Launch"])
        out = p.filter(self.df)
        self.assertEqual(set(out["campaign"]), {"Launch"})
        self.assertEqual(out["timestamp"].nunique(), 1)

    def test_summary(self):
        kpis = autoviz.DataProcessor.summary(self.df)
        self.assertEqual(kpis["impressions"], 3500)
        self.assertAlmostEqual(kpis["cpa"], 67.5 / 21)


class TestController(unittest.TestCase):
    def test_updates_when_csv_changes(self):  # AC-1, FR-2
        csv = TempCSV(HEADER + GOOD_ROWS)
        self.addCleanup(csv.cleanup)
        ctrl = make_controller(csv.path)
        self.assertTrue(ctrl.update_once())
        first_title = ctrl.plotter.fig._suptitle.get_text()

        time.sleep(0.05)
        csv.append("2024-06-01 10:10,Launch,90000,9000,900,100\n")
        os.utime(csv.path, None)
        ctrl.schedule_update()
        self.assertNotEqual(ctrl.plotter.fig._suptitle.get_text(), first_title)

    def test_no_update_when_unchanged_and_not_due(self):
        csv = TempCSV(HEADER + GOOD_ROWS)
        self.addCleanup(csv.cleanup)
        ctrl = make_controller(csv.path, refresh=60)
        ctrl.update_once()
        before = ctrl._last_update
        ctrl.schedule_update()
        self.assertEqual(ctrl._last_update, before)

    def test_plots_two_or_more_labelled_metrics(self):  # AC-2, FR-3
        csv = TempCSV(HEADER + GOOD_ROWS)
        self.addCleanup(csv.cleanup)
        ctrl = make_controller(csv.path)
        ctrl.update_once()
        titles = [ax.get_title() for ax in ctrl.plotter.axes]
        self.assertTrue(any("Impressions" in t for t in titles))
        self.assertTrue(any("Clicks" in t for t in titles))
        self.assertTrue(all(ax.get_ylabel() for ax in ctrl.plotter.axes))

    def test_survives_file_deleted_and_recreated(self):  # FR-5
        csv = TempCSV(HEADER + GOOD_ROWS)
        ctrl = make_controller(csv.path)
        self.assertTrue(ctrl.update_once())
        csv.cleanup()
        self.assertFalse(ctrl.update_once())
        with open(csv.path, "w", encoding="utf-8") as f:
            f.write(HEADER + GOOD_ROWS)
        self.addCleanup(csv.cleanup)
        self.assertTrue(ctrl.update_once())


class TestCLI(unittest.TestCase):  # AC-3, NFR-4
    def test_defaults(self):
        args = build_parser().parse_args(["--csv", "x.csv"])
        self.assertEqual(args.refresh, 5.0)

    def test_custom_refresh(self):
        args = build_parser().parse_args(["--csv", "x.csv", "--refresh", "2.5"])
        self.assertEqual(args.refresh, 2.5)

    def test_rejects_bad_refresh(self):
        for bad in ("0", "-1", "fast"):
            with self.assertRaises(SystemExit):
                build_parser().parse_args(["--csv", "x.csv", "--refresh", bad])

    def test_requires_csv(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args([])

    def test_snapshot(self):
        csv = TempCSV(HEADER + GOOD_ROWS)
        self.addCleanup(csv.cleanup)
        out = os.path.join(tempfile.mkdtemp(), "sub", "dash.png")
        self.assertEqual(main(["--csv", csv.path, "--snapshot", out]), 0)
        self.assertGreater(os.path.getsize(out), 10_000)


if __name__ == "__main__":
    unittest.main()
