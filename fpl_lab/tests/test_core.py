import io
import itertools
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from fpl_lab.api import APIError, load_live_data
from fpl_lab.data import players_frame, validate_squad
from fpl_lab.demo import load_demo_data
from fpl_lab.optimizer import OptimizationError, recommend_transfers, solve_squad
from fpl_lab.projections import build_projections, cat_frame, read_projection_csv


class DataTests(unittest.TestCase):
    def setUp(self):
        self.data = load_demo_data()
        self.players = players_frame(self.data["bootstrap"])

    def test_price_normalization(self):
        self.assertTrue((self.players["price"] * 10 == self.players["now_cost"]).all())

    def test_blank_and_double_gameweeks(self):
        fixtures = [{"event": 8, "team_h": 1, "team_a": 2, "team_h_difficulty": 3, "team_a_difficulty": 3},
                    {"event": 8, "team_h": 1, "team_a": 4, "team_h_difficulty": 3, "team_a_difficulty": 3}]
        forecast = build_projections(self.players, fixtures, self.data["bootstrap"]["events"], [8, 9])
        doubles = forecast.loc[(forecast["gameweek"] == 8) & forecast["player_id"].isin(self.players.loc[self.players.team == 1].index)]
        self.assertTrue((doubles.fixtures == 2).all())
        self.assertTrue((doubles.expected_points > 0).all())
        blanks = forecast.loc[forecast.gameweek == 9]
        self.assertTrue((blanks.expected_points == 0).all())
        self.assertTrue((blanks.opponents == "BLANK").all())

    def test_injury_reduces_fixture_model_to_zero(self):
        self.players.loc[1, "status"] = "i"
        forecast = build_projections(self.players, self.data["fixtures"], self.data["bootstrap"]["events"], [8])
        self.assertEqual(forecast.loc[forecast.player_id == 1, "expected_points"].item(), 0)

    def test_ep_next_is_not_multiplied_and_not_reused_for_later_week(self):
        self.players.loc[1, "ep_next"] = 17
        forecast = build_projections(self.players, self.data["fixtures"], self.data["bootstrap"]["events"], [8, 9], "FPL estimates")
        rows = forecast.loc[forecast.player_id == 1].set_index("gameweek")
        self.assertEqual(rows.loc[8, "expected_points"], 17)
        self.assertEqual(rows.loc[9, "source"], "Fixture model")

    def test_csv_validation(self):
        invalid = ["id,xp\n1,5", "player_id,gameweek,expected_points\n1,8,NaN",
                   "player_id,gameweek,expected_points\n1,8,inf",
                   "player_id,gameweek,expected_points\n1,8.5,5",
                   "player_id,gameweek,expected_points\n1,39,5",
                   "player_id,gameweek,expected_points\n999999,8,5",
                   "player_id,gameweek,expected_points\n1,8,5\n1,8,7"]
        for content in invalid:
            with self.subTest(content=content), self.assertRaises(ValueError):
                read_projection_csv(io.StringIO(content), self.players.index)

    def test_csv_only_overrides_matching_week(self):
        override = read_projection_csv(io.StringIO("player_id,gameweek,expected_points\n1,8,22"), self.players.index)
        forecast = build_projections(self.players, self.data["fixtures"], self.data["bootstrap"]["events"], [8, 9], overrides=override)
        one = forecast.loc[forecast.player_id == 1].set_index("gameweek")
        self.assertEqual(one.loc[8, "expected_points"], 22)
        self.assertEqual(one.loc[9, "source"], "Fixture model")

    def test_cat_projection_schema(self):
        result = cat_frame({"gameweek": 8, "players": [{"id": 1, "xp": 6.2}]}, self.players.index)
        self.assertEqual(result.iloc[0].expected_points, 6.2)

    def test_empty_api_response_is_handled(self):
        with patch("fpl_lab.api.get_json", side_effect=[{}, []]):
            with self.assertRaises(APIError):
                load_live_data()

    def test_duplicate_or_incomplete_squad_rejected(self):
        for ids in [[1] * 15, list(range(1, 15)), list(range(1, 16))]:
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                validate_squad(self.players, ids)


class OptimizerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_demo_data()
        cls.players = players_frame(cls.data["bootstrap"])
        cls.forecast = build_projections(cls.players, cls.data["fixtures"], cls.data["bootstrap"]["events"], [8, 9])
        cls.base = solve_squad(cls.players, cls.forecast, budget=100, time_limit=10)

    def assert_legal(self, plan, players=None):
        players = self.players if players is None else players
        validate_squad(players, plan.squad.id.tolist())
        for view in plan.weekly.values():
            starters = view.loc[view.starter]
            self.assertEqual(len(starters), 11)
            self.assertEqual(int(starters.captain.sum()), 1)
            self.assertEqual(int(starters.vice_captain.sum()), 1)
            counts = starters.element_type.value_counts()
            self.assertEqual(counts.get(1, 0), 1)
            self.assertGreaterEqual(counts.get(2, 0), 3)
            self.assertGreaterEqual(counts.get(3, 0), 2)
            self.assertGreaterEqual(counts.get(4, 0), 1)

    def test_legal_squad_budget_and_captain_score(self):
        self.assert_legal(self.base)
        self.assertLessEqual(self.base.squad.now_cost.sum(), 1000)
        expected = sum(v.loc[v.starter, "expected_points"].sum() + v.loc[v.captain, "expected_points"].sum()
                       for v in self.base.weekly.values())
        self.assertAlmostEqual(self.base.expected_points, expected)

    def test_infeasible_budget(self):
        with self.assertRaises(OptimizationError):
            solve_squad(self.players, self.forecast, budget=1)

    def test_lock_and_exclude(self):
        locked = int(self.base.squad.id.iloc[0])
        excluded = int(self.base.squad.id.iloc[-1])
        plan = solve_squad(self.players, self.forecast, locked=[locked], excluded=[excluded], budget=110)
        self.assertIn(locked, plan.squad.index)
        self.assertNotIn(excluded, plan.squad.index)
        self.assert_legal(plan)
        with self.assertRaises(OptimizationError):
            solve_squad(self.players, self.forecast, locked=[locked], excluded=[locked])

    def test_zero_transfers_preserves_squad_and_reduced_sale_prices_do_not_force_sales(self):
        current = self.base.squad.id.tolist()
        sell = {pid: int(self.players.loc[pid, "now_cost"]) - 3 for pid in current}
        plan = solve_squad(self.players, self.forecast, current_ids=current, bank=0,
                           selling_prices=sell, max_transfers=0)
        self.assertEqual(set(plan.squad.id), set(current))
        self.assertEqual(plan.bank_after, 0)
        self.assertEqual(plan.transfers_in, [])

    def test_transfer_limit_budget_and_hits(self):
        current = self.base.squad.id.tolist()
        sell = {pid: int(self.players.loc[pid, "now_cost"]) - 2 for pid in current}
        plan = solve_squad(self.players, self.forecast, current_ids=current, bank=1,
                           selling_prices=sell, max_transfers=2, free_transfers=0)
        self.assertLessEqual(len(plan.transfers_in), 2)
        self.assertEqual(len(plan.transfers_in), len(plan.transfers_out))
        self.assertEqual(plan.hit_cost, 4 * len(plan.transfers_in))
        cash = 10 + sum(sell[pid] for pid in plan.transfers_out) - sum(int(self.players.loc[pid, "now_cost"]) for pid in plan.transfers_in)
        self.assertEqual(round(plan.bank_after * 10), cash)
        self.assertGreaterEqual(cash, 0)
        self.assert_legal(plan)

    def test_no_gain_recommends_keeping(self):
        current = self.base.squad.id.tolist()
        sell = {pid: int(self.players.loc[pid, "now_cost"]) for pid in current}
        before, after, gain = recommend_transfers(self.players, self.forecast, current,
            bank=0, selling_prices=sell, max_transfers=0)
        self.assertEqual(gain, 0)
        self.assertEqual(set(before.squad.id), set(after.squad.id))

    def test_required_sale_is_respected_even_without_positive_gain(self):
        current = self.base.squad.id.tolist()
        sell = {pid: int(self.players.loc[pid, "now_cost"]) for pid in current}
        before, after, gain = recommend_transfers(self.players, self.forecast, current,
            bank=1, selling_prices=sell, max_transfers=1, free_transfers=0, excluded=[current[0]])
        self.assertNotIn(current[0], after.squad.index)
        self.assertEqual(len(after.transfers_in), 1)
        self.assertAlmostEqual(gain, after.expected_points - after.hit_cost - before.expected_points)

    def test_missing_and_nonfinite_forecasts_rejected(self):
        for value in [float("nan"), float("inf")]:
            forecast = self.forecast.copy()
            forecast.loc[0, "expected_points"] = value
            with self.assertRaises(OptimizationError):
                solve_squad(self.players, forecast)

    def test_optimizer_matches_exhaustive_search_on_small_candidate_pool(self):
        # Three GKs and exactly the required outfield positions. Enumerate every XI and captain.
        base_ids = self.base.squad.id.tolist()
        extra_gk = int(self.players.loc[(self.players.element_type == 1)
                       & ~self.players.id.isin(base_ids), "id"].iloc[0])
        small = self.players.loc[base_ids + [extra_gk]].copy()
        # Club counts cannot accidentally invalidate the extra-GK alternative.
        small["team"] = list(range(1, len(small) + 1))
        small["now_cost"] = 40
        small["price"] = 4.0
        forecast = pd.DataFrame({"player_id": small.id.tolist(), "gameweek": 8,
                                 "expected_points": [(i * 7) % 19 + 1 for i in range(len(small))]})
        xp = forecast.set_index("player_id").expected_points.to_dict()
        best = -float("inf")
        gks = small.loc[small.element_type == 1].index.tolist()
        outfield = small.loc[small.element_type != 1].index.tolist()
        for pair in itertools.combinations(gks, 2):
            for starting_gk in pair:
                for field in itertools.combinations(outfield, 10):
                    ids = [starting_gk] + list(field)
                    counts = small.loc[ids, "element_type"].value_counts()
                    if counts.get(2, 0) < 3 or counts.get(3, 0) < 2 or counts.get(4, 0) < 1:
                        continue
                    best = max(best, sum(xp[pid] for pid in ids) + max(xp[pid] for pid in ids))
        plan = solve_squad(small, forecast, budget=100, bench_weight=0)
        self.assertAlmostEqual(plan.expected_points, best)
        self.assertTrue(plan.optimal)
        self.assert_legal(plan, small)


if __name__ == "__main__":
    unittest.main()
