"""Shared views for comparisons, squad plans and the pitch."""
from html import escape

import altair as alt
import pandas as pd
import streamlit as st

DISPLAY_NAMES = {"name": "Player", "club": "Club", "position": "Position", "price": "Price (£m)",
    "total_points": "Points", "form": "Form", "minutes": "Minutes", "selected_by_percent": "Owned (%)",
    "expected_points": "Projected points", "points_per_million": "Points / £m", "opponents": "Fixtures",
    "source": "Forecast source", "gameweek": "Gameweek", "player_id": "Player ID", "news": "News",
    "horizon_xp": "Horizon xP", "captain": "Captain", "vice_captain": "Vice captain", "starter": "Starts"}


def table(frame, columns=None):
    view = frame[columns].copy() if columns else frame.copy()
    st.dataframe(view.rename(columns=DISPLAY_NAMES), hide_index=True, width="stretch")


def pitch(view: pd.DataFrame):
    rows = []
    for position in [1, 2, 3, 4]:
        cards = []
        for _, player in view.loc[view["starter"] & (view["element_type"] == position)].iterrows():
            badge = " · C" if player["captain"] else " · VC" if player["vice_captain"] else ""
            cards.append(f'<div class="player-card"><div class="shirt">{escape(player["club"])}</div>'
                         f'<strong>{escape(player["name"])}</strong><span>{badge}</span>'
                         f'<small>£{player["price"]:.1f}m · {player["expected_points"]:.1f} xP</small></div>')
        rows.append('<div class="pitch-row">' + "".join(cards) + '</div>')
    st.html('<div class="pitch">' + "".join(rows) + '</div>')
    st.caption("Bench: reserve goalkeeper first; outfield substitutes in projected-points order. "
               "Automatic substitutions and vice-captain fallback are not simulated.")
    bench = view.loc[~view["starter"]].sort_values(
        ["element_type", "expected_points"], ascending=[True, False])
    reserve_gk = bench.loc[bench["element_type"] == 1]
    outfield = bench.loc[bench["element_type"] != 1].sort_values("expected_points", ascending=False)
    table(pd.concat([reserve_gk, outfield]), ["name", "club", "position", "price", "expected_points"])


def render_plan(plan, key):
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Projected XI + captain", f"{plan.expected_points:.1f}", help="Sum across selected weeks; bench excluded.")
    col2.metric("Squad market price", f"£{plan.squad['price'].sum():.1f}m")
    col3.metric("Budget remaining", f"£{plan.bank_after:.1f}m")
    col4.metric("Transfer hit", f"−{plan.hit_cost} pts")
    if plan.optimal:
        st.caption("Solver found an optimum within its numerical tolerance for these projections and constraints.")
    else:
        gap = f" · optimality gap {100 * plan.gap:.2f}%" if plan.gap is not None else ""
        st.warning("Time limit reached: showing a validated feasible squad" + gap + ". Global optimality is unproven.")
    gw = st.selectbox("View lineup for", list(plan.weekly), format_func=lambda w: f"Gameweek {w}", key=f"{key}_week")
    view = plan.weekly[gw]
    pitch(view)
    with st.expander("Squad table and export"):
        cols = ["id", "name", "club", "position", "price", "expected_points", "starter", "captain", "vice_captain"]
        table(view, cols)
        export = pd.concat([v.assign(gameweek=w) for w, v in plan.weekly.items()], ignore_index=True)
        st.download_button("Download plan CSV", export[["gameweek"] + cols].to_csv(index=False),
                           f"fpl-plan-gw{gw}.csv", "text/csv", key=f"{key}_export")


def comparison_chart(frame, metric):
    chart = alt.Chart(frame.reset_index(drop=True)).mark_circle(opacity=0.75).encode(
        x=alt.X("price:Q", title="Current price (£m)", scale=alt.Scale(zero=False)),
        y=alt.Y(f"{metric}:Q", title=DISPLAY_NAMES.get(metric, metric)),
        color=alt.Color("position:N", title="Position",
                        scale=alt.Scale(range=["#52785a", "#8a9e6c", "#c48a4b", "#a96e62"])),
        size=alt.Size("selected_by_percent:Q", title="Owned (%)", scale=alt.Scale(range=[40, 450])),
        tooltip=[alt.Tooltip("name:N", title="Player"), "club:N", "position:N",
                 alt.Tooltip("price:Q", format=".1f"), alt.Tooltip(f"{metric}:Q", format=".2f"),
                 alt.Tooltip("selected_by_percent:Q", format=".1f")],
    ).properties(height=390, background="transparent").configure(
        axis=alt.Axis(gridColor="#e5e9df", domainColor="#c8d2c5",
                      labelColor="#596b5d", titleColor="#344d3a"),
        legend=alt.Legend(labelColor="#596b5d", titleColor="#344d3a"),
        view=alt.ViewConfig(stroke=None),
    ).interactive()
    st.altair_chart(chart, width="stretch")
