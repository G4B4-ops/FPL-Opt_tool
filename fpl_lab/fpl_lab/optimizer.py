"""MILP: one squad, independent legal XIs/captains for each horizon week."""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .data import SQUAD_COUNTS, validate_squad


class OptimizationError(ValueError):
    pass


@dataclass
class Plan:
    squad: pd.DataFrame
    weekly: dict[int, pd.DataFrame]
    expected_points: float
    hit_cost: int
    objective: float
    optimal: bool
    gap: float | None
    bank_after: float
    transfers_in: list[int]
    transfers_out: list[int]


def solve_squad(players: pd.DataFrame, projections: pd.DataFrame, *, budget: float = 100,
                current_ids: list[int] | None = None, bank: float = 0,
                selling_prices: dict[int, int] | None = None, max_transfers: int = 15,
                free_transfers: int = 1, locked: list[int] | None = None,
                excluded: list[int] | None = None, bench_weight: float = 0.05,
                time_limit: float = 25) -> Plan:
    # Lazy import lets the app show comparisons/setup help if SciPy isn't installed yet.
    try:
        from scipy.optimize import Bounds, LinearConstraint, milp
        from scipy.sparse import coo_matrix
    except ImportError as exc:
        raise OptimizationError("Install the optimizer: python -m pip install -r requirements.txt") from exc
    current = set(current_ids or [])
    if current_ids is not None:
        validate_squad(players, current_ids)
    locked, excluded = set(locked or []), set(excluded or [])
    if locked & excluded:
        raise OptimizationError("A player cannot be both locked and excluded.")
    if not (locked | excluded).issubset(set(players.index)):
        raise OptimizationError("A locked/excluded player is absent from this dataset.")
    if not 0 <= bench_weight <= 1 or budget < 0 or bank < 0:
        raise OptimizationError("Budgets must be nonnegative; bench weight must be from 0 to 1.")
    if not 0 <= max_transfers <= 15 or not 0 <= free_transfers <= 5:
        raise OptimizationError("Use 0–15 transfers and 0–5 free transfers.")
    eligible = players["status"].isin(["a", "d"]) | players["id"].isin(current)
    candidates = players.loc[eligible & ~players["id"].isin(excluded)].copy()
    if not locked.issubset(set(candidates.index)):
        raise OptimizationError("A locked player is unavailable for new selection. Remove that lock.")
    if len(candidates) < 15:
        raise OptimizationError("Fewer than 15 eligible players remain.")
    ids = candidates["id"].astype(int).tolist()
    lookup = {pid: index for index, pid in enumerate(ids)}
    weeks = sorted(projections["gameweek"].unique().tolist())
    if not weeks or projections.duplicated(["player_id", "gameweek"]).any():
        raise OptimizationError("Provide one forecast per player per gameweek.")
    matrix = projections.pivot(index="player_id", columns="gameweek", values="expected_points")
    matrix = matrix.reindex(index=ids, columns=weeks)
    if matrix.isna().any().any() or not np.isfinite(matrix.to_numpy()).all():
        raise OptimizationError("Every candidate needs a finite forecast for every horizon week.")
    xp = matrix.to_numpy(dtype=float)
    n, k = len(ids), len(weeks)
    # Variables: n squad flags, k*n starter flags, k*n captain flags, hit count.
    size, hit_index = n * (1 + 2 * k) + 1, n * (1 + 2 * k)
    objective = np.zeros(size)
    objective[:n] = -bench_weight * xp.sum(axis=1)
    for week in range(k):
        objective[n + week * n:n + (week + 1) * n] = -(1 - bench_weight) * xp[:, week]
        objective[n + k * n + week * n:n + k * n + (week + 1) * n] = -xp[:, week]
    objective[hit_index] = 4
    row_indices, col_indices, values, lows, highs = [], [], [], [], []

    def constrain(terms, lower=-np.inf, upper=np.inf):
        row = len(lows)
        for index, value in terms:
            row_indices.append(row)
            col_indices.append(index)
            values.append(float(value))
        lows.append(lower)
        highs.append(upper)

    positions = candidates["element_type"].to_numpy()
    for position, count in SQUAD_COUNTS.items():
        constrain([(i, 1) for i in range(n) if positions[i] == position], count, count)
    for club in candidates["team"].unique():
        constrain([(i, 1) for i in range(n) if candidates.iloc[i]["team"] == club], upper=3)
    costs = candidates["now_cost"].to_numpy(dtype=int)
    sell = {}
    if current_ids is not None:
        if selling_prices is None or set(selling_prices) != current:
            raise OptimizationError("Enter a selling price for every current player, in integer tenths of £m.")
        sell = dict(selling_prices)
        for pid, value in sell.items():
            if not np.isfinite(value) or int(value) != value or value < 0 or value > players.loc[pid, "now_cost"]:
                raise OptimizationError("Selling prices must be whole tenths, between zero and the current price.")
        # Retaining a player costs their foregone selling value, not their purchase price.
        costs = np.array([sell[pid] if pid in current else costs[i] for i, pid in enumerate(ids)])
        funds = int(round(bank * 10)) + sum(sell.values())
        incoming = [(i, 1) for i, pid in enumerate(ids) if pid not in current]
        constrain(incoming, upper=max_transfers)
        constrain(incoming + [(hit_index, -1)], upper=free_transfers)
    else:
        funds = int(round(budget * 10))
    constrain(list(enumerate(costs)), upper=funds)
    for pid in locked:
        constrain([(lookup[pid], 1)], 1, 1)
    for week in range(k):
        y, captain = n + week * n, n + k * n + week * n
        constrain([(y + i, 1) for i in range(n)], 11, 11)
        constrain([(captain + i, 1) for i in range(n)], 1, 1)
        for position, (minimum, maximum) in {1: (1, 1), 2: (3, 5), 3: (2, 5), 4: (1, 3)}.items():
            constrain([(y + i, 1) for i in range(n) if positions[i] == position], minimum, maximum)
        for i in range(n):
            constrain([(y + i, 1), (i, -1)], upper=0)
            constrain([(captain + i, 1), (y + i, -1)], upper=0)
    upper_bounds = np.ones(size)
    upper_bounds[hit_index] = 15 if current_ids is not None else 0
    sparse = coo_matrix((values, (row_indices, col_indices)), shape=(len(lows), size)).tocsc()
    result = milp(c=objective, integrality=np.ones(size),
                  bounds=Bounds(np.zeros(size), upper_bounds),
                  constraints=LinearConstraint(sparse, np.array(lows), np.array(highs)),
                  options={"time_limit": time_limit, "mip_rel_gap": 0.00001})
    if result.x is None or result.status not in [0, 1]:
        raise OptimizationError("No feasible squad found. Increase your budget/transfer limit or relax player locks.")
    decision = np.rint(result.x)
    # Never present an unverified incumbent as a legal recommendation after a timeout.
    residual = sparse @ decision
    if (np.max(np.abs(result.x - decision)) > 1e-5
            or (residual < np.array(lows) - 1e-5).any()
            or (residual > np.array(highs) + 1e-5).any()
            or (decision < 0).any() or (decision > upper_bounds).any()):
        raise OptimizationError("The solver stopped before finding a valid integer squad. Run it again.")
    chosen = [pid for i, pid in enumerate(ids) if decision[i] == 1]
    validate_squad(players, chosen)
    squad = players.loc[chosen].copy()
    squad["horizon_xp"] = matrix.loc[chosen].sum(axis=1)
    weekly, total = {}, 0.0
    for week, gw in enumerate(weeks):
        view = squad.copy()
        view["expected_points"] = matrix.loc[chosen, gw]
        view["starter"] = [bool(decision[n + week * n + lookup[pid]]) for pid in chosen]
        view["captain"] = [bool(decision[n + k * n + week * n + lookup[pid]]) for pid in chosen]
        view["vice_captain"] = False
        vice = view.loc[view["starter"] & ~view["captain"], "expected_points"].idxmax()
        view.loc[vice, "vice_captain"] = True
        view = view.sort_values(["starter", "element_type", "expected_points"], ascending=[False, True, False])
        weekly[int(gw)] = view
        total += float(view.loc[view["starter"], "expected_points"].sum()
                       + view.loc[view["captain"], "expected_points"].sum())
    ins, outs = sorted(set(chosen) - current), sorted(current - set(chosen))
    hit_cost = 4 * max(0, len(ins) - free_transfers) if current_ids is not None else 0
    cost_used = sum(int(costs[lookup[pid]]) for pid in chosen)
    return Plan(squad=squad, weekly=weekly, expected_points=total, hit_cost=hit_cost,
                objective=float(-result.fun), optimal=result.status == 0,
                gap=float(result.mip_gap) if getattr(result, "mip_gap", None) is not None else None,
                bank_after=(funds - cost_used) / 10, transfers_in=ins if current_ids is not None else [],
                transfers_out=outs)


def recommend_transfers(players, projections, current_ids, *, bank, selling_prices,
                        max_transfers=2, free_transfers=1, **kwargs):
    """Compare with the best legal lineup of the unchanged squad, including captaincy."""
    before = solve_squad(players, projections, current_ids=current_ids, bank=bank,
                         selling_prices=selling_prices, max_transfers=0,
                         free_transfers=free_transfers, bench_weight=0)
    after = solve_squad(players, projections, current_ids=current_ids, bank=bank,
                        selling_prices=selling_prices, max_transfers=max_transfers,
                        free_transfers=free_transfers, bench_weight=0, **kwargs)
    net_gain = after.expected_points - after.hit_cost - before.expected_points
    forced_change = (not set(kwargs.get("locked") or []).issubset(set(current_ids))
                     or bool(set(kwargs.get("excluded") or []) & set(current_ids)))
    if net_gain <= 0.01 and not forced_change:
        return before, before, 0.0
    return before, after, net_gain
