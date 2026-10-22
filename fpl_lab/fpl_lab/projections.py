"""Transparent estimates, not a trained or backtested prediction model."""
import numpy as np
import pandas as pd


def read_projection_csv(source, player_ids) -> pd.DataFrame:
    frame = pd.read_csv(source)
    required = ["player_id", "gameweek", "expected_points"]
    if not set(required).issubset(frame.columns):
        raise ValueError("Projection CSV needs player_id, gameweek, expected_points columns.")
    frame = frame[required].copy()
    for column in required:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if not np.isfinite(frame.to_numpy(dtype=float)).all():
        raise ValueError("Projection values must be finite numbers with no missing cells.")
    for column in ["player_id", "gameweek"]:
        if (frame[column] % 1 != 0).any():
            raise ValueError(f"{column} must be a whole number.")
        frame[column] = frame[column].astype(int)
    if not frame["gameweek"].between(1, 38).all():
        raise ValueError("Gameweeks must be between 1 and 38.")
    if frame.duplicated(["player_id", "gameweek"]).any():
        raise ValueError("Use one projection per player and gameweek; sum double-gameweek fixtures first.")
    unknown = set(frame["player_id"]) - set(player_ids)
    if unknown:
        raise ValueError(f"Unknown player IDs for this season: {sorted(unknown)[:10]}")
    return frame


def cat_frame(payload: dict, player_ids) -> pd.DataFrame:
    """Do not silently apply a provider's next-GW forecast to another week."""
    rows = [{"player_id": p["id"], "gameweek": payload["gameweek"],
             "expected_points": p["xp"]} for p in payload["players"]]
    import io
    return read_projection_csv(io.StringIO(pd.DataFrame(rows).to_csv(index=False)), player_ids)


def build_projections(players: pd.DataFrame, fixtures: list[dict], events: list[dict],
                      gameweeks: list[int], source: str = "Fixture model",
                      overrides: pd.DataFrame | None = None) -> pd.DataFrame:
    teams_by_id = dict(zip(players["team"], players["club"]))
    next_event = next((e["id"] for e in events if e.get("is_next")), None)
    # Status is a current snapshot; it is not a forecast of recovery dates.
    chance = pd.to_numeric(players["chance_of_playing_next_round"], errors="coerce")
    fallback = players["status"].map({"a": 100, "d": 75}).fillna(0)
    availability = chance.fillna(fallback).clip(0, 100) / 100
    availability = availability.where(players["status"].isin(["a", "d"]), 0)
    # A modest minutes discount avoids treating a 10-minute substitute like a starter.
    minutes_per_start = players["minutes"] / players["starts"].clip(lower=1)
    minutes_factor = (minutes_per_start / 75).clip(0.25, 1)
    minutes_factor = minutes_factor.where(players["minutes"] > 0, 0.35)
    baseline = (0.55 * players["points_per_game"] + 0.45 * players["form"]).clip(lower=0)
    rows = []
    override_map = {} if overrides is None else {
        (int(r.player_id), int(r.gameweek)): float(r.expected_points)
        for r in overrides.itertuples(index=False)}
    for gw in gameweeks:
        by_team = {}
        for fixture in fixtures:
            if fixture.get("event") != gw:
                continue
            for side, other in [("h", "a"), ("a", "h")]:
                by_team.setdefault(fixture[f"team_{side}"], []).append({
                    "opponent": teams_by_id.get(fixture[f"team_{other}"], "?"),
                    "home": side == "h",
                    "difficulty": float(fixture.get(f"team_{side}_difficulty", 3) or 3)})
        for pid, player in players.iterrows():
            matches = by_team.get(player["team"], [])
            factor = sum(np.clip(1 + (3 - m["difficulty"]) * 0.12, 0.7, 1.3)
                         * (1.04 if m["home"] else 0.96) for m in matches)
            points = float(baseline.loc[pid] * minutes_factor.loc[pid]
                           * availability.loc[pid] * factor)
            used_source = "Fixture model"
            if source == "FPL estimates" and gw == next_event:
                # ep_next is already a whole-GW estimate, including availability/fixtures.
                points = float(player["ep_next"])
                used_source = "FPL ep_next"
            if (pid, gw) in override_map:
                points = override_map[(pid, gw)]
                used_source = "FPL Cat" if source == "FPL Cat" else "Uploaded CSV"
            # Known blank weeks always score zero, irrespective of the chosen source.
            if not matches:
                points = 0.0
            rows.append({"player_id": int(pid), "gameweek": gw,
                "expected_points": round(points, 4), "fixtures": len(matches),
                "opponents": ", ".join(f"{m['opponent']} ({'H' if m['home'] else 'A'})" for m in matches)
                             or "BLANK", "source": used_source})
    return pd.DataFrame(rows)
