from pathlib import Path
from html import escape

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from fpl_lab.api import (APIError, load_cat_projections, load_entry, load_live_data,
                         load_player_history)
from fpl_lab.data import players_frame, public_gameweeks, upcoming_gameweeks, validate_squad
from fpl_lab.demo import load_demo_data
from fpl_lab.optimizer import OptimizationError, recommend_transfers, solve_squad
from fpl_lab.projections import build_projections, cat_frame, read_projection_csv
from fpl_lab.ui import DISPLAY_NAMES, comparison_chart, render_plan, table

st.set_page_config(page_title="FPL Lab", page_icon="⚽", layout="wide")
DEFAULT_HERO_IMAGE_URL = (
    "https://resources.premierleague.com/premierleague/photo/2020/08/11/"
    "55650e57-1935-4a40-b3be-f8d1900598e8/FPL-Statement-Lead.png"
)
st.html("""<style>
.block-container {max-width:1420px;padding-top:1rem;padding-bottom:3rem;}
html, body, [class*="css"] {font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}
h1, h2, h3 {color:#23392c;letter-spacing:-.035em;}
h1 {font-weight:750!important;}
[data-testid="stSidebar"] {background:#e9eee5;border-right:1px solid #d9e1d5;}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {color:#536557;}
[data-testid="stSidebar"], [data-testid="collapsedControl"] {display:none!important;}
[data-testid="stMetric"] {background:#fffdf7;padding:16px;border-radius:18px;border:1px solid #e4e8dc;box-shadow:0 5px 18px rgba(36,59,42,.045);}
[data-testid="stMetricLabel"] {color:#66786a;}
[data-testid="stMetricValue"] {color:#244733;}
.hero {min-height:370px;display:flex;align-items:center;padding:clamp(2rem,6vw,5.5rem);border-radius:26px;overflow:hidden;position:relative;
 background-image:linear-gradient(90deg,rgba(22,43,31,.82) 0%,rgba(22,43,31,.57) 52%,rgba(22,43,31,.12) 100%),var(--hero-image);
 background-size:cover;background-position:center top;background-repeat:no-repeat;box-shadow:0 14px 38px rgba(35,57,44,.14);}
.hero-content {max-width:760px;position:relative;z-index:1;}
.eyebrow {color:#f3eedc;letter-spacing:.16em;font-size:.72rem;font-weight:750;text-transform:uppercase;}
.hero-title {font-size:clamp(2.5rem,5.2vw,4.4rem);line-height:1.02;letter-spacing:-.055em;font-weight:780;color:#fbf5e5;margin:.65rem 0 .7rem;text-wrap:balance;}
.hero-section {display:inline-flex;color:#f6efd9;font-size:.92rem;font-weight:700;letter-spacing:.04em;margin:0 0 .65rem;padding:.4rem .75rem;border-radius:999px;background:rgba(247,245,237,.14);border:1px solid rgba(247,245,237,.26);backdrop-filter:blur(12px);}
.hero-copy {font-size:1.08rem;line-height:1.6;color:#f3eedf;max-width:42rem;}
.workspace-heading {margin:1.5rem 0 .75rem;}
[class*="st-key-workspace-card"] {height:100%;padding:1.1rem 1.1rem .85rem;background:#fffdf7;border:1px solid #e2e8dd;border-radius:18px;box-shadow:0 6px 20px rgba(36,59,42,.05);}
[class*="st-key-workspace-card"] p {min-height:3.2rem;color:#647365;}
[class*="st-key-workspace-card"] button {min-height:3.35rem;border-radius:12px;font-size:.98rem;}
[data-testid="stTextInput"] input, [data-testid="stNumberInput"] input, [data-testid="stSelectbox"] > div,
[data-testid="stMultiSelect"] > div {border-radius:12px;}
[data-testid="stTextInput"] input:focus, [data-testid="stNumberInput"] input:focus {border-color:#63866b;box-shadow:0 0 0 .15rem rgba(88,126,94,.15);}
.stButton > button, [data-testid="stFormSubmitButton"] button, [data-testid="stDownloadButton"] button {border-radius:12px;font-weight:650;transition:transform 120ms ease,box-shadow 160ms ease;}
.stButton > button:hover, [data-testid="stFormSubmitButton"] button:hover, [data-testid="stDownloadButton"] button:hover {box-shadow:0 5px 14px rgba(41,79,51,.12);}
.stButton > button:active, [data-testid="stFormSubmitButton"] button:active, [data-testid="stDownloadButton"] button:active {transform:scale(.985);}
[data-testid="stDataFrame"], [data-testid="stTable"] {border:1px solid #e4e8dc;border-radius:14px;overflow:hidden;}
[data-testid="stExpander"] {border-color:#e1e7dc;border-radius:14px;}
.pitch {border:1px solid #d0dfd0;border-radius:22px;padding:20px 8px;
 background:repeating-linear-gradient(0deg,#e7efe4 0px,#e7efe4 92px,#e1ebde 92px,#e1ebde 184px);}
.pitch-row {display:flex;justify-content:space-evenly;gap:8px;margin:12px 0 24px;}
.player-card {text-align:center;max-width:160px;flex:1;font-size:.86rem;color:#294632;}
.player-card small {display:block;color:#617565;font-size:.75rem;margin-top:4px;}
.shirt {display:grid;place-items:center;margin:0 auto 8px;width:48px;height:46px;
 background:#477454;color:#fffdf7;font-size:.68rem;font-weight:800;border-radius:14px 14px 9px 9px;box-shadow:0 3px 8px rgba(35,57,44,.16);}
@media(max-width:600px){.block-container{padding-top:.5rem}.hero{min-height:330px;padding:1.6rem;background-position:center top;border-radius:20px}.hero-title{font-size:2.65rem}.hero-section{font-size:.8rem}.pitch{padding:5px}.player-card{font-size:.66rem}.player-card small{font-size:.6rem}.shirt{width:32px;height:32px}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;transition:none!important;animation:none!important}}
</style>""")


@st.cache_data(ttl=900, show_spinner=False)
def cached_live():
    return load_live_data()


@st.cache_data(ttl=900, show_spinner=False)
def cached_entry(entry_id, gw):
    return load_entry(entry_id, gw)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_history(pid):
    return load_player_history(pid)


@st.cache_data(ttl=900, show_spinner=False)
def cached_cat():
    return load_cat_projections()


@st.cache_data(ttl=3600, show_spinner=False)
def cached_demo():
    return load_demo_data()


section_titles = {
    "Compare players": "Find the value in the field",
    "Build a squad": "Build for the next deadline",
    "Improve my team": "Make your next move count",
    "Data & methodology": "Know what drives the decision",
}
workspaces = [
    ("Compare players", "Explore player value, form, ownership and fixture history."),
    ("Build a squad", "Create a legal squad and plan lineups for upcoming weeks."),
    ("Improve my team", "Import your team, review its lineup and compare transfer moves."),
    ("Data & methodology", "Understand the forecasts, optimization and data sources."),
]
page = st.session_state.setdefault("workspace", "Compare players")
hero_image_url = escape(DEFAULT_HERO_IMAGE_URL, quote=True)
st.html(
    f'<section class="hero" style="--hero-image:url(&quot;{hero_image_url}&quot;)">'
    '<div class="hero-content">'
    '<div class="eyebrow">FANTASY PREMIER LEAGUE / DECISION DESK</div>'
    '<h1 class="hero-title">Every point has a price.</h1>'
    f'<div class="hero-section">{escape(section_titles[page])}</div>'
    '<div class="hero-copy">Compare your options, build a legal squad, and make your next move with confidence.</div>'
    '</div></section>'
)

control_demo, control_refresh, control_note = st.columns([1.2, .8, 2.4], vertical_alignment="center")
demo_mode = control_demo.toggle("Use synthetic demo data", key="demo_mode")
if control_refresh.button("Refresh data", width="stretch"):
    st.cache_data.clear()
    for key in ["build_result", "transfer_result", "imported_squad", "imported_lineup"]:
        st.session_state.pop(key, None)
    st.rerun()
control_note.caption("Live data is cached for 15 minutes · no account password needed.")

st.markdown("### Choose your workspace", help="Select a workspace to open its tools.")
workspace_columns = st.columns(4)
for index, ((workspace, description), column) in enumerate(zip(workspaces, workspace_columns)):
    with column:
        with st.container(key=f"workspace-card-{index}"):
            st.markdown(f"#### {workspace}")
            st.caption(description)
            if st.button(
                f"Open {workspace}",
                key=f"open-workspace-{index}",
                type="primary" if workspace == page else "secondary",
                width="stretch",
            ):
                st.session_state["workspace"] = workspace
                st.rerun()
page = st.session_state["workspace"]

try:
    with st.spinner("Loading player prices, points and fixtures…"):
        data = cached_demo() if demo_mode else cached_live()
    players = players_frame(data["bootstrap"])
except (APIError, ValueError, KeyError) as exc:
    st.error(str(exc))
    st.info("Enable ‘Use synthetic demo data’ in the sidebar to explore offline. Live data needs internet access.")
    st.stop()

# Clear team/session artifacts when moving between real and synthetic player IDs.
data_identity = (data["demo"], data["fetched_at"])
if st.session_state.get("data_identity") != data_identity:
    for key in ["build_result", "transfer_result", "imported_squad", "manual_squad", "selling_prices",
                "build_locked", "build_excluded", "transfer_locked", "transfer_excluded",
                "confirm_prices", "history_selection", "imported_lineup"]:
        st.session_state.pop(key, None)
    st.session_state["data_identity"] = data_identity
if data["demo"]:
    st.warning("DEMO MODE — all clubs, players, prices and results are synthetic. Do not use these recommendations in FPL.")
st.caption(f"Source: {'synthetic demo' if demo_mode else 'Fantasy Premier League'} · fetched {data['fetched_at'][:19]} UTC")
events = data["bootstrap"]["events"]
upcoming = upcoming_gameweeks(events)
labels = players["label"].to_dict()
options = players.sort_values(["total_points", "now_cost"], ascending=[False, True])["id"].tolist()


def choose_forecasts(key):
    if not upcoming:
        st.info("No future gameweek deadlines in this dataset. Try again after the season refresh.")
        st.stop()
    c1, c2, c3 = st.columns([1, 1, 2])
    first = c1.selectbox("Starting gameweek", upcoming, key=f"{key}_gw")
    horizon = c2.selectbox("Weeks to evaluate", list(range(1, min(6, 39 - first) + 1)), key=f"{key}_horizon")
    sources = ["Fixture model", "FPL estimates", "Upload CSV"] + ([] if demo_mode else ["FPL Cat"])
    source = c3.selectbox("Points forecast", sources, key=f"{key}_source")
    weeks = list(range(first, first + horizon))
    overrides = None
    if source == "Upload CSV":
        upload = st.file_uploader("Projections: player_id, gameweek, expected_points", type="csv", key=f"{key}_upload")
        if upload is None:
            st.info("Upload your forecasts to continue, or choose Fixture model.")
            st.stop()
        try:
            overrides = read_projection_csv(upload, players.index)
        except (ValueError, pd.errors.ParserError) as exc:
            st.error(str(exc))
            st.stop()
    if source == "FPL Cat":
        try:
            payload = cached_cat()
            overrides = cat_frame(payload, players.index)
            if first != int(payload["gameweek"]):
                st.error(f"FPL Cat currently covers GW{payload['gameweek']}. Select that starting gameweek or use another model.")
                st.stop()
            st.caption(f"Projections: [FPL Cat](https://fplcat.com) · computed {payload.get('computed_at', 'unknown')}")
            timestamp = pd.to_datetime(payload.get("computed_at"), utc=True, errors="coerce")
            if pd.isna(timestamp) or pd.Timestamp.now(tz="UTC") - timestamp > pd.Timedelta(hours=48):
                st.warning("Provider forecast timestamp is missing or over 48 hours old. Check freshness before using it.")
        except (APIError, ValueError, KeyError, TypeError) as exc:
            st.error(f"Projection feed unavailable: {exc}. Choose Fixture model or upload a CSV.")
            st.stop()
    projections = build_projections(players, data["fixtures"], events, weeks, source, overrides)
    if source != "Fixture model":
        st.caption("Forecast sources used: " + ", ".join(projections["source"].unique())
                   + ". Uncovered players/weeks use the fixture model; known blank weeks are zero.")
    return projections, weeks


def player_constraints(key):
    c1, c2 = st.columns(2)
    locked = c1.multiselect("Must include / keep", options, format_func=labels.get, key=f"{key}_locked")
    excluded = c2.multiselect("Exclude / sell", options, format_func=labels.get, key=f"{key}_excluded")
    return locked, excluded


if page == "Compare players":
    c1, c2, c3, c4 = st.columns(4)
    positions = c1.multiselect("Positions", ["GK", "DEF", "MID", "FWD"], default=["GK", "DEF", "MID", "FWD"])
    clubs = c2.multiselect("Clubs", sorted(players["club"].unique()))
    price_cap = c3.slider("Maximum price (£m)", 3.0, max(16.0, float(players["price"].max())),
                           max(16.0, float(players["price"].max())), step=0.1)
    min_minutes = c4.number_input("Minimum season minutes", min_value=0, value=0, step=90)
    search = st.text_input("Search player name", placeholder="e.g. a surname")
    view = players.loc[players["position"].isin(positions) & (players["price"] <= price_cap)
                       & (players["minutes"] >= min_minutes)].copy()
    if clubs:
        view = view.loc[view["club"].isin(clubs)]
    if search:
        view = view.loc[(view["name"] + " " + view["full_name"]).str.contains(search, case=False, regex=False)]
    if view.empty:
        st.info("No players match these filters. Broaden your search.")
        st.stop()
    metric = st.selectbox("Compare against price", ["total_points", "points_per_million", "form", "points_per_game"],
                          format_func=lambda m: DISPLAY_NAMES.get(m, m.replace("_", " ").title()))
    comparison_chart(view, metric)
    columns = ["id", "name", "club", "position", "price", "total_points", "points_per_million", "form", "minutes", "selected_by_percent", "news"]
    table(view.sort_values(metric, ascending=False).round(2), columns)
    st.download_button("Export filtered players", view[columns].to_csv(index=False), "fpl-players.csv", "text/csv")
    st.markdown("#### Head-to-head")
    selected = st.multiselect("Choose up to four players", view["id"].tolist(), format_func=labels.get, max_selections=4)
    if selected:
        stats = ["price", "total_points", "points_per_game", "form", "minutes", "expected_goals", "expected_assists"]
        head = players.loc[selected].set_index("label")[stats].T
        head.index = [DISPLAY_NAMES.get(s, s.replace("_", " ").title()) for s in head.index]
        st.dataframe(head.round(2), width="stretch")
        if not demo_mode and st.button("Load gameweek points history"):
            st.session_state["history_selection"] = selected
        if not demo_mode and selected == st.session_state.get("history_selection"):
            try:
                history_rows = []
                for pid in selected:
                    history_rows.extend([{**row, "player": labels[pid]} for row in cached_history(pid).get("history", [])])
                if history_rows:
                    history = pd.DataFrame(history_rows).groupby(["round", "player"], as_index=False)["total_points"].sum()
                    # Sum double-gameweek fixture rows before plotting.
                    chart = alt.Chart(history).mark_line(point=True).encode(
                        x=alt.X("round:O", title="Gameweek"), y=alt.Y("total_points:Q", title="Points"),
                        color="player:N", tooltip=["player", "round", "total_points"])
                    st.altair_chart(chart, width="stretch")
                else:
                    st.info("No played fixtures available for these players yet.")
            except APIError as exc:
                st.error(str(exc))

elif page == "Build a squad":
    st.caption("Choose a gameweek for a fresh squad, or evaluate one fixed squad over up to six weeks. "
               "Lineups and captains can change each week; transfers between those weeks are not modeled.")
    projections, weeks = choose_forecasts("build")
    c1, c2 = st.columns(2)
    budget = c1.number_input("Total squad budget (£m)", min_value=65.0, max_value=150.0, value=100.0, step=0.1)
    bench = c2.slider("Bench importance", 0.0, 0.30, 0.05, 0.01,
                       help="0 optimizes XI plus doubled captain only. A small weight rewards useful substitutes; bench points are excluded from the displayed score.")
    locked, excluded = player_constraints("build")
    fingerprint = (tuple(weeks), budget, bench, tuple(locked), tuple(excluded), projections.to_csv(index=False))
    if st.button("Generate best projected squad", type="primary", width="stretch"):
        try:
            with st.spinner("Solving squad, formations and captains…"):
                plan = solve_squad(players, projections, budget=budget, locked=locked, excluded=excluded, bench_weight=bench)
            st.session_state["build_result"] = (fingerprint, plan)
        except (ValueError, OptimizationError) as exc:
            st.error(str(exc))
    result = st.session_state.get("build_result")
    if result and result[0] == fingerprint:
        render_plan(result[1], "build_plan")
    elif result:
        st.info("Settings changed. Generate a new squad to update the result.")

elif page == "Improve my team":
    st.caption("Import a published squad using its numeric team ID, or select your current 15 players manually.")
    if not demo_mode:
        public = public_gameweeks(events)
        if public:
            with st.form("import_team"):
                c1, c2 = st.columns(2)
                team_id = c1.number_input("FPL team ID", min_value=1, value=1, step=1,
                                          help="From /entry/123456/event/7 in your FPL points-page URL; this is not a league ID.")
                import_gw = c2.selectbox("Published squad gameweek", public)
                submitted = st.form_submit_button("Import published squad")
            if submitted:
                try:
                    entry = cached_entry(int(team_id), import_gw)
                    ids = [int(p["element"]) for p in entry["picks"]]
                    validate_squad(players, ids)
                    st.session_state["manual_squad"] = ids
                    st.session_state["imported_squad"] = (team_id, import_gw)
                    st.session_state.pop("selling_prices", None)
                except (APIError, ValueError, KeyError) as exc:
                    st.error(str(exc))
        else:
            st.info("No squad is public before the first deadline. Select your players manually.")
    if st.session_state.get("imported_squad"):
        entry_id, imported_gw = st.session_state["imported_squad"]
        st.info(f"Imported team {entry_id}, GW{imported_gw}. Public picks exclude transfers made since that deadline. "
                "Check the 15 players, bank, free transfers and selling prices below against your current FPL team.")
    current_ids = st.multiselect("Your current 15 players", options, format_func=labels.get, key="manual_squad")
    if len(current_ids) != 15:
        st.info(f"Selected {len(current_ids)} of 15 players. Complete the squad to evaluate transfers.")
        st.stop()
    try:
        validate_squad(players, current_ids)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()
    st.markdown("#### Verify selling prices")
    st.caption("Public picks do not expose your purchase or current selling prices. Replace these market-price defaults "
               "with the selling prices shown on your FPL Transfers page. Values are in £m.")
    price_frame = players.loc[current_ids, ["id", "label", "price"]].reset_index(drop=True)
    price_frame["selling_price"] = price_frame["price"]
    edited = st.data_editor(price_frame, hide_index=True, disabled=["id", "label", "price"],
        column_config={"id": None, "label": "Player", "price": "Market price (£m)",
                       "selling_price": st.column_config.NumberColumn("Selling price (£m)", min_value=0.0, max_value=20.0, step=0.1, format="%.1f")},
        key="selling_prices", width="stretch")
    confirmed = st.checkbox("I have checked my squad and entered the actual selling prices.", key="confirm_prices")
    c1, c2, c3 = st.columns(3)
    bank = c1.number_input("Money in the bank (£m)", min_value=0.0, max_value=100.0, value=0.0, step=0.1)
    free = c2.number_input("Free transfers available", min_value=0, max_value=5, value=1, step=1)
    maximum = c3.number_input("Maximum transfers to consider", min_value=0, max_value=15, value=2, step=1)
    st.caption("Enter your remaining free transfers if you already made changes this week. "
               "The model charges 4 points per additional transfer; it does not model chips or future free-transfer savings.")
    projections, weeks = choose_forecasts("transfer")
    if st.session_state.get("imported_squad"):
        lineup_fingerprint = (
            tuple(sorted(current_ids)),
            tuple(weeks),
            projections.to_csv(index=False),
        )
        imported_lineup = st.session_state.get("imported_lineup")
        if not imported_lineup or imported_lineup[0] != lineup_fingerprint:
            try:
                with st.spinner("Setting the best lineup for your imported squad…"):
                    plan = solve_squad(
                        players,
                        projections,
                        current_ids=current_ids,
                        bank=0,
                        selling_prices={
                            int(pid): int(players.loc[pid, "now_cost"]) for pid in current_ids
                        },
                        max_transfers=0,
                        free_transfers=0,
                        bench_weight=0,
                    )
                st.session_state["imported_lineup"] = (lineup_fingerprint, plan)
                imported_lineup = st.session_state["imported_lineup"]
            except (ValueError, OptimizationError) as exc:
                st.error(f"Could not build a lineup for the imported team: {exc}")
                imported_lineup = None
        if imported_lineup and imported_lineup[0] == lineup_fingerprint:
            st.markdown("#### Your imported team")
            st.caption(
                f"Lineup optimized for the selected forecast across {len(weeks)} gameweek(s). "
                "The imported squad is a snapshot from the deadline you selected."
            )
            render_plan(imported_lineup[1], "imported_team")
    locked, excluded = player_constraints("transfer")
    prices_valid = (np.isfinite(edited["selling_price"]).all()
                    and (edited["selling_price"] >= 0).all()
                    and (edited["selling_price"] <= edited["price"] + 1e-8).all()
                    and np.allclose(edited["selling_price"] * 10, np.rint(edited["selling_price"] * 10)))
    if not prices_valid:
        st.error("Selling prices must be in £0.1m steps, nonnegative, and no higher than the market price.")
        st.stop()
    selling = dict(zip(edited["id"].astype(int), (edited["selling_price"] * 10).round().astype(int)))
    fingerprint = (tuple(sorted(current_ids)), tuple(sorted(selling.items())), bank, free, maximum,
                   tuple(locked), tuple(excluded), projections.to_csv(index=False))
    if st.button("Suggest transfers", type="primary", disabled=not confirmed, width="stretch"):
        try:
            with st.spinner("Comparing transfers with your best unchanged lineup…"):
                before, after, gain = recommend_transfers(players, projections, current_ids,
                    bank=bank, selling_prices=selling, max_transfers=int(maximum), free_transfers=int(free),
                    locked=locked, excluded=excluded)
            st.session_state["transfer_result"] = (fingerprint, before, after, gain)
        except (ValueError, OptimizationError) as exc:
            st.error(str(exc))
    result = st.session_state.get("transfer_result")
    if result and result[0] == fingerprint:
        _, before, after, gain = result
        if after.transfers_in:
            if gain > 0:
                st.success(f"Projected improvement after hits: +{gain:.2f} points across {len(weeks)} gameweek(s).")
            else:
                st.warning(f"Your required player changes reduce the projection by {abs(gain):.2f} points after hits. "
                           "Relax the include/exclude settings to consider keeping your squad.")
            outs = players.loc[after.transfers_out].sort_values("element_type")
            ins = players.loc[after.transfers_in].sort_values("element_type")
            transfers = pd.DataFrame({"Sell": outs["label"].tolist(), "Sell (£m)": [selling[i] / 10 for i in outs.index],
                                      "Buy": ins["label"].tolist(), "Buy (£m)": ins["price"].tolist()})
            st.dataframe(transfers, hide_index=True, width="stretch")
            st.caption("These moves form one package; an individual row may need funds released by another move.")
        else:
            st.info("Keep your squad: no positive projected gain after hits was found within the chosen settings and solver limit.")
        st.caption(f"Unchanged squad: {before.expected_points:.2f} xP · proposed squad: {after.expected_points:.2f} xP "
                   f"· hit: {after.hit_cost} points. Both scores include optimized lineups and captaincy.")
        render_plan(after, "transfer_plan")
    elif result:
        st.info("Your squad or settings changed. Run suggestions again to update the result.")

else:
    st.markdown("""
**Recommended data source:** the JSON endpoints used by the [FPL website](https://fantasy.premierleague.com/).
They provide FPL prices, points, positions and fixtures directly. Public reads do not need an API key.
The API has no supported public contract; endpoint behavior can change.

**Fixture model:** a simple, untrained heuristic. Per-fixture points start at
`0.55 × points_per_game + 0.45 × form`, with discounts for minutes and current availability,
then adjustments for FPL fixture difficulty and home/away. Fixtures are summed for double gameweeks;
known blanks get zero. Current fitness flags are held constant over the horizon, so check recovery news yourself.
New players with little history may be underestimated. This model has not been backtested.

**Other forecasts:** FPL's `ep_next` is used only for its next gameweek; FPL Cat covers its published gameweek.
An uploaded CSV supplies whole-gameweek expected points by player ID. Uncovered rows use the fixture model.
Forecasts are estimates, not guaranteed scores.

**Optimization:** integer programming chooses a 15-player squad (2 GK, 5 DEF, 5 MID, 3 FWD),
at most three per club, within the available budget. Each week gets 11 starters, one goalkeeper,
at least three defenders, two midfielders and one forward. Captain points count twice.
A fresh-squad objective may reward the bench at the selected weight; displayed xP excludes bench points.
The vice captain is the next highest projected starter. Auto-substitutions and captain fallback are not simulated.

**Transfers:** compares the best unchanged lineup with up to your transfer limit, deducting four points
per transfer beyond your remaining free allowance. Retained players are valued at their selling price
to calculate the funds available. It recommends one set of transfers now and holds that squad across the horizon.
Chips, future transfers, free-transfer rollover value and future price changes are not modeled.
Unavailable players may be retained but cannot be newly bought. Time-limited solutions are labeled.

**Your team:** public picks are snapshots after a deadline. They cannot reveal pending transfers,
current bank, free-transfer allowance or exact selling prices. Verify these manually. The app cannot submit transfers.
""")
    st.markdown("#### API research and setup")
    st.markdown("See the project README and API_RESEARCH.md for the source comparison, endpoint map and limitations.")
    research = Path(__file__).with_name("API_RESEARCH.md")
    if research.exists():
        with st.expander("Read the API comparison"):
            st.markdown(research.read_text(encoding="utf-8"))
    st.markdown("[FPL rules](https://fantasy.premierleague.com/help/rules) · "
                "[FPL Cat API](https://fplcat.com/developers) · "
                "[Sideline Quant feed](https://sidelinequant.com/data)")

st.divider()
st.caption("Independent personal project. Not affiliated with the Premier League. "
           "‘Best’ means highest model objective under your chosen constraints; future performance is uncertain.")
