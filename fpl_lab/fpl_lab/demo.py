"""Deterministic SYNTHETIC data for offline exploration and reproducible tests."""
from datetime import datetime, timedelta, timezone


def load_demo_data() -> dict:
    now = datetime.now(timezone.utc)
    teams = [{"id": i, "name": f"Demo Club {i:02}", "short_name": f"D{i:02}"}
             for i in range(1, 21)]
    events = [{"id": gw, "name": f"Gameweek {gw}",
               "deadline_time": (now + timedelta(days=(gw - 8) * 7 + 3)).isoformat(),
               "is_next": gw == 8, "is_current": gw == 7, "finished": gw < 7}
              for gw in range(1, 39)]
    elements, fixtures = [], []
    player_id = 0
    for team in teams:
        for position, count in [(1, 2), (2, 5), (3, 5), (4, 3)]:
            for slot in range(count):
                player_id += 1
                quality = ((team["id"] * 7 + position * 3 + slot * 11) % 21) / 20
                minutes = 580 if slot < count - 1 else 120
                cost = int(40 + quality * (65 if position in [3, 4] else 25))
                elements.append({"id": player_id, "web_name": f"Player {player_id:03}",
                    "first_name": "Demo", "second_name": f"Player {player_id:03}",
                    "team": team["id"], "element_type": position, "now_cost": cost,
                    "total_points": int(15 + quality * 40), "form": round(2 + quality * 4, 1),
                    "points_per_game": round(2 + quality * 4, 1), "minutes": minutes,
                    "starts": 6 if minutes > 500 else 1, "selected_by_percent": quality * 30,
                    "expected_goals": quality * 3, "expected_assists": quality * 2,
                    "goals_scored": int(quality * 4), "assists": int(quality * 3),
                    "clean_sheets": int(quality * 3), "status": "a", "news": "",
                    "chance_of_playing_next_round": None, "ep_next": round(2 + quality * 4, 1)})
    fixture_id = 0
    for gw in range(1, 39):
        rotation = (gw - 1) % 19
        ring = [20] + [((i + rotation) % 19) + 1 for i in range(19)]
        for index in range(10):
            fixture_id += 1
            home, away = ring[index], ring[-index - 1]
            fixtures.append({"id": fixture_id, "event": gw, "team_h": home, "team_a": away,
                "team_h_difficulty": 2 + away % 3, "team_a_difficulty": 2 + home % 3,
                "finished": gw < 7,
                "kickoff_time": (now + timedelta(days=(gw - 8) * 7 + 4)).isoformat()})
    return {"bootstrap": {"elements": elements, "teams": teams, "events": events},
            "fixtures": fixtures, "demo": True, "fetched_at": now.isoformat()}
