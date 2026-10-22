"""Read-only clients. No account credentials or transfer submissions."""
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://fantasy.premierleague.com/api/"


class APIError(RuntimeError):
    pass


def get_json(url: str):
    retry = Retry(total=2, backoff_factor=0.6, status_forcelist=[429, 500, 502, 503, 504],
                  allowed_methods=["GET"], respect_retry_after_header=False)
    try:
        with requests.Session() as session:
            session.headers.update({"User-Agent": "FPL-Lab/1.0 (personal read-only analytics)",
                                    "Accept": "application/json"})
            session.mount("https://", HTTPAdapter(max_retries=retry))
            response = session.get(url, timeout=(8, 25))
            response.raise_for_status()
            return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise APIError(f"Could not read {url}: {exc}") from exc


def load_live_data() -> dict:
    bootstrap = get_json(BASE_URL + "bootstrap-static/")
    fixtures = get_json(BASE_URL + "fixtures/")
    if (not isinstance(bootstrap, dict) or not bootstrap.get("elements")
            or not bootstrap.get("events") or not bootstrap.get("teams")
            or not isinstance(fixtures, list)):
        raise APIError("FPL returned an unexpected or empty season dataset. Try again later.")
    return {"bootstrap": bootstrap, "fixtures": fixtures, "demo": False,
            "fetched_at": datetime.now(timezone.utc).isoformat()}


def load_entry(entry_id: int, gameweek: int) -> dict:
    if entry_id < 1 or not 1 <= gameweek <= 38:
        raise APIError("Use a positive team ID and a gameweek from 1 to 38.")
    result = get_json(BASE_URL + f"entry/{entry_id}/event/{gameweek}/picks/")
    if not isinstance(result, dict) or len(result.get("picks", [])) != 15:
        raise APIError("No published 15-player squad for this team and gameweek. Try an earlier week.")
    return result


def load_player_history(player_id: int) -> dict:
    return get_json(BASE_URL + f"element-summary/{int(player_id)}/")


def load_cat_projections() -> dict:
    result = get_json("https://fplcat.com/api/v1/projections")
    if not isinstance(result, dict) or not result.get("players") or "gameweek" not in result:
        raise APIError("FPL Cat returned an unexpected projection format.")
    return result
