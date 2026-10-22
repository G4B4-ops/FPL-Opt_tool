"""Normalize FPL's prices (integer tenths of £m) and numeric strings."""
import pandas as pd

POSITIONS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
SQUAD_COUNTS = {1: 2, 2: 5, 3: 5, 4: 3}


def players_frame(bootstrap: dict) -> pd.DataFrame:
    frame = pd.DataFrame(bootstrap["elements"]).copy()
    required = {"id", "team", "element_type", "now_cost", "web_name"}
    if not required.issubset(frame.columns):
        raise ValueError("The FPL player schema changed: missing required player fields.")
    for field in ["total_points", "minutes", "form", "points_per_game", "selected_by_percent",
                  "expected_goals", "expected_assists", "goals_scored", "assists", "clean_sheets",
                  "ep_next", "ep_this", "starts"]:
        if field not in frame:
            frame[field] = 0
        frame[field] = pd.to_numeric(frame[field], errors="coerce").fillna(0)
    for field in ["first_name", "second_name", "news"]:
        if field not in frame:
            frame[field] = ""
    if "status" not in frame:
        frame["status"] = "a"
    if "chance_of_playing_next_round" not in frame:
        frame["chance_of_playing_next_round"] = float("nan")
    teams = {t["id"]: t for t in bootstrap["teams"]}
    frame["club"] = frame["team"].map(lambda t: teams[t]["short_name"])
    frame["position"] = frame["element_type"].map(POSITIONS)
    frame["name"] = frame["web_name"]
    frame["full_name"] = (frame["first_name"] + " " + frame["second_name"]).str.strip()
    frame["price"] = frame["now_cost"] / 10.0
    frame["points_per_million"] = frame["total_points"] / frame["price"].clip(lower=0.1)
    frame["label"] = (frame["name"] + " · " + frame["club"] + " · " + frame["position"]
                      + " · #" + frame["id"].astype(str))
    return frame.set_index("id", drop=False)


def validate_squad(players: pd.DataFrame, ids: list[int]) -> None:
    if len(ids) != 15 or len(set(ids)) != 15:
        raise ValueError("Select exactly 15 different players.")
    unknown = set(ids) - set(players.index)
    if unknown:
        raise ValueError(f"Players absent from this season: {sorted(unknown)}. Edit the squad manually.")
    squad = players.loc[ids]
    if squad["element_type"].value_counts().to_dict() != SQUAD_COUNTS:
        raise ValueError("Your squad must contain 2 GK, 5 DEF, 5 MID and 3 FWD.")
    if squad["team"].value_counts().max() > 3:
        raise ValueError("Your squad has more than three players from a club. Adjust it before optimizing.")


def public_gameweeks(events: list[dict]) -> list[int]:
    """Picks become public after the deadline, including the current week."""
    now = pd.Timestamp.now(tz="UTC")
    return sorted([e["id"] for e in events
                   if pd.to_datetime(e["deadline_time"], utc=True) <= now], reverse=True)


def upcoming_gameweeks(events: list[dict]) -> list[int]:
    now = pd.Timestamp.now(tz="UTC")
    return sorted([e["id"] for e in events
                   if pd.to_datetime(e["deadline_time"], utc=True) > now])
