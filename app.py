import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import pandas as pd
from data import (build_events, build_fixture_grids, build_league_table, build_match_list,
                  default_gameweek, load_live, load_players, load_player_detail, photo_exists)

st.set_page_config(page_title="FPL Dashboard", layout="wide")
st.markdown(
    """
    <style>
    .block-container {padding-top: 2rem;}
    [data-testid="stMetric"] {
        background: #2a0a33; border-radius: 10px; padding: 12px 16px;
    }
    h1 {color: #e0b3ff;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("FPL Dashboard")
_gw = default_gameweek(build_match_list())
st.caption(f"Current gameweek: {_gw}  |  Data refreshes every 10 minutes from the FPL API")

players = load_players()

def player_dataframe(df, config, key):
    """Show a table of players. Clicking a row opens that player's detail page.
    `df` must be indexed by player id."""
    event = st.dataframe(df, column_config=config, hide_index=True, use_container_width=True,
                         on_select="rerun", selection_mode="single-row", key=key)
    rows = event.selection.rows
    if rows:
        st.session_state["goto"] = ("Player detail", int(df.index[rows[0]]))
        st.rerun()
    st.caption("Click a row's left edge to open that player's detail page.")

SORT_OPTIONS = {
    "Total points": "total_points",
    "Points per million": "points_per_million",
    "Ownership %": "selected_by_percent",
    "Price": "price",
    "Points per 90": "tp_per90",
    "xGI per 90": "xgi_per90",
    "xGC per 90 (lower is better)": "xgc_per90",
    "Defensive contribution per 90": "defcon_per90",
}
LOWER_IS_BETTER = {"price", "xgc_per90"}

TABLE_COLS = ["photo_url", "web_name", "team_name", "position", "price", "total_points",
              "points_per_million", "selected_by_percent", "minutes",
              "tp_per90", "xgi_per90", "xgc_per90", "defcon_per90", "news"]

COLUMN_CONFIG = {
    "photo_url": st.column_config.ImageColumn(" ", width="small"),
    "web_name": st.column_config.TextColumn("Player"),
    "team_name": st.column_config.TextColumn("Team"),
    "position": st.column_config.TextColumn("Position"),
    "price": st.column_config.NumberColumn("Price (£m)", format="%.1f"),
    "total_points": st.column_config.NumberColumn("Points"),
    "points_per_million": st.column_config.NumberColumn("Pts / £m", format="%.2f"),
    "selected_by_percent": st.column_config.ProgressColumn(
        "Owned %", format="%.1f%%", min_value=0, max_value=100),
    "minutes": st.column_config.NumberColumn("Minutes"),
    "tp_per90": st.column_config.NumberColumn("Pts / 90", format="%.2f"),
    "xgi_per90": st.column_config.NumberColumn("xGI / 90", format="%.2f"),
    "xgc_per90": st.column_config.NumberColumn("xGC / 90", format="%.2f"),
    "defcon_per90": st.column_config.NumberColumn("DefCon / 90", format="%.2f"),
    "news": st.column_config.TextColumn("News"),
}


def player_table_tab(players):
    teams = ["All"] + sorted(players["team_name"].unique())

    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        position = c1.selectbox("Position", ["All", "Goalkeeper", "Defender", "Midfielder", "Forward"], key="players_position")
        team = c2.selectbox("Team", teams, key="players_team")
        sort_label = c3.selectbox("Sort by", list(SORT_OPTIONS), key="players_sort")

        c4, c5, c6, c7 = st.columns(4)
        max_price = c4.slider("Max price (£m)", 4.0, 16.0, 16.0, 0.5, key="players_max_price")
        min_minutes = c5.slider("Min minutes", 0, 900, 300, 30, key="players_min_minutes")
        max_ownership = c6.slider("Max ownership %", 0, 100, 100, 1, key="players_max_own")
        n_rows = c7.slider("Rows to show", 5, 50, 15, 5, key="players_rows")

    sort_col = SORT_OPTIONS[sort_label]

    mask = (players["price"] <= max_price) & (players["minutes"] >= min_minutes) & (players["selected_by_percent"] <= max_ownership)
    if position != "All":
        mask &= players["position"] == position
    if team != "All":
        mask &= players["team_name"] == team

    df = (players[mask]
        .sort_values(sort_col, ascending=sort_col in LOWER_IS_BETTER)
        .head(n_rows)
        .set_index("id")[TABLE_COLS])

    if df.empty:
        st.info("No players match these filters.")
    else:
        player_dataframe(df, COLUMN_CONFIG, key="players_table")

TEAM_COLUMN_CONFIG = {
    "rank": st.column_config.NumberColumn("#", width="small"),
    "team_name": st.column_config.TextColumn("Team"),
    "played": st.column_config.NumberColumn("P", width="small"),
    "won": st.column_config.NumberColumn("W", width="small"),
    "drawn": st.column_config.NumberColumn("D", width="small"),
    "lost": st.column_config.NumberColumn("L", width="small"),
    "gf": st.column_config.NumberColumn("GF", width="small"),
    "ga": st.column_config.NumberColumn("GA", width="small"),
    "gd": st.column_config.NumberColumn("GD", width="small"),
    "points": st.column_config.NumberColumn("Pts", width="small"),
    "gf_per_game": st.column_config.NumberColumn("GF / game", format="%.2f"),
    "ga_per_game": st.column_config.NumberColumn("GA / game", format="%.2f"),
    "xg": st.column_config.NumberColumn("xG", format="%.1f"),
    "gf_minus_xg": st.column_config.NumberColumn("Goals - xG", format="%+.1f"),
}

TEAM_SORT_OPTIONS = {
    "League position": ("rank", True),
    "Goals per game": ("gf_per_game", False),
    "Goals conceded per game (fewest first)": ("ga_per_game", True),
    "xG": ("xg", False),
    "Goals minus xG": ("gf_minus_xg", False),
}

def teams_tab():
    table = build_league_table()
    if table.empty:
        st.info("No matches have finished yet.")
        return

    st.subheader("League table")
    sort_label = st.selectbox("Sort by", list(TEAM_SORT_OPTIONS), key="teams_sort")
    sort_col, ascending = TEAM_SORT_OPTIONS[sort_label]
    shown = table.sort_values(sort_col, ascending=ascending)

    st.dataframe(
        shown[list(TEAM_COLUMN_CONFIG)],
        column_config=TEAM_COLUMN_CONFIG,
        hide_index=True,
        use_container_width=True,
        height=35 * len(table) + 38,
    )
    st.caption("Only finished matches are counted. A match in progress is not included, "
               "so this can differ slightly from the Premier League site mid-gameweek.")

    st.subheader("Goals vs expected goals")
    left, right = st.columns(2)

    with left:
        # ascending sort puts the biggest overperformer at the top of a horizontal bar chart
        bars = table.sort_values("gf_minus_xg")
        fig = px.bar(
            bars, x="gf_minus_xg", y="team_name", orientation="h",
            color="gf_minus_xg", color_continuous_scale="RdYlGn", color_continuous_midpoint=0,
            labels={"gf_minus_xg": "Goals minus xG", "team_name": ""},
            title="Who is scoring more (or less) than their chances suggest",
        )
        fig.update_layout(coloraxis_showscale=False, height=600)
        st.plotly_chart(fig, use_container_width=True)

    with right:
        fig = px.scatter(
            table, x="xg", y="gf", text="team_name",
            hover_data=["played", "gf_per_game"],
            labels={"xg": "Expected goals (xG)", "gf": "Goals scored"},
            title="Above the line = overperforming, below = underperforming",
        )
        lo = min(table["xg"].min(), table["gf"].min()) - 1
        hi = max(table["xg"].max(), table["gf"].max()) + 1
        fig.add_shape(type="line", x0=lo, y0=lo, x1=hi, y1=hi, line=dict(dash="dash"))
        fig.update_traces(textposition="top center")
        fig.update_layout(height=600)
        st.plotly_chart(fig, use_container_width=True)

def fixtures_tab():
    matches = build_match_list()
    default_gw = default_gameweek(matches)

    # ---- match list for one gameweek ----
    st.subheader("Match list")
    with st.container(border=True):
        c1, c2 = st.columns(2)
        gw = c1.selectbox("Gameweek", list(range(1, 39)), index=default_gw - 1, key="fixtures_gw")
        team = c2.selectbox("Team", ["All"] + sorted(set(matches["home"]) | set(matches["away"])), key="fixtures_team")

    df = matches[matches["event"] == gw]
    if team != "All":
        df = df[(df["home"] == team) | (df["away"] == team)]
    df = df.sort_values("kickoff")[["kickoff_text", "home", "score", "away", "home_diff", "away_diff"]]
    df = df.rename(columns={"kickoff_text": "Kickoff", "home": "Home", "score": "Score",
                            "away": "Away", "home_diff": "Home diff", "away_diff": "Away diff"})

    if df.empty:
        st.info("No matches for this selection.")
    else:
        styled = df.style.background_gradient(
            cmap="RdYlGn_r", subset=["Home diff", "Away diff"], vmin=1, vmax=5)
        st.dataframe(styled, hide_index=True, use_container_width=True)
    st.caption("Difficulty runs from 1 (easy) to 5 (hard), from each side's own point of view.")

    # ---- heatmap ----
    st.subheader("Fixture heatmap")
    diff_grid, text_grid, hover_grid, done_grid = build_fixture_grids()
    with st.container(border=True):
        c3, c4 = st.columns([2, 1])
        start, end = c3.slider("Gameweeks", 1, 38, (default_gw, min(default_gw + 4, 38)), key="fixtures_range")
        team_pick = c4.selectbox("Show", ["All teams"] + list(diff_grid.index), key="fixtures_heatmap_team")

    cols = [c for c in diff_grid.columns if start <= c <= end]
    d, t, hv = diff_grid[cols], text_grid[cols], hover_grid[cols]
    done = done_grid[cols].fillna(0).eq(1)          # True = finished
    if team_pick != "All teams":
        d, t, hv, done = (x.loc[[team_pick]] for x in (d, t, hv, done))
    t, hv = t.fillna(""), hv.fillna("Blank gameweek")

    def layer(show, opacity):
        # draws only the cells where `show` is True; the rest stay empty
        return go.Heatmap(
            z=d.where(show).values,
            x=[f"GW{c}" for c in d.columns],
            y=list(d.index),
            text=t.where(show, "").values,
            texttemplate="%{text}",
            customdata=hv.values,
            hovertemplate="%{y}<br>%{x}: %{customdata}<br>Difficulty %{z}<extra></extra>",
            colorscale=[[0, "green"], [0.5, "yellow"], [1, "red"]],
            zmin=1, zmax=5, xgap=2, ygap=2,
            opacity=opacity, showscale=False, hoverongaps=False,
        )

    fig = go.Figure([layer(~done, 1.0), layer(done, 0.35)])
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(side="top")
    fig.update_layout(height=max(250, 32 * len(d) + 120))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Faded cells are finished matches. Colours run from green (easy) to red (hard).")

TRANSFER_METRICS = {
    "Net transfers this gameweek": "net_transfers_event",
    "Net transfers this season": "net_transfers",
    "Ownership %": "selected_by_percent",
    "Price change since start": "price_change",
}

TRANSFER_COLS = ["web_name", "team_name", "position", "price", "price_change",
                 "selected_by_percent", "net_transfers_event", "net_transfers",
                 "minutes", "xgi_per90", "reason", "news"]

TRANSFER_CONFIG = {
    "web_name": st.column_config.TextColumn("Player"),
    "team_name": st.column_config.TextColumn("Team"),
    "position": st.column_config.TextColumn("Position"),
    "price": st.column_config.NumberColumn("Price (£m)", format="%.1f"),
    "price_change": st.column_config.NumberColumn("Price change", format="%+.1f"),
    "selected_by_percent": st.column_config.ProgressColumn(
        "Owned %", format="%.1f%%", min_value=0, max_value=100),
    "net_transfers_event": st.column_config.NumberColumn("Net transfers (GW)", format="%d"),
    "net_transfers": st.column_config.NumberColumn("Net transfers (season)", format="%d"),
    "minutes": st.column_config.NumberColumn("Minutes"),
    "xgi_per90": st.column_config.NumberColumn("xGI / 90", format="%.2f"),
    "reason": st.column_config.TextColumn("Reason"),
    "news": st.column_config.TextColumn("News"),
}


def transfers_tab(players):
    # ---------- movers ----------
    st.subheader("Movers")
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns(4)
        metric_label = c1.selectbox("Rank by", list(TRANSFER_METRICS), key="transfers_metric")
        direction = c2.selectbox("Direction", ["Highest", "Lowest"], key="transfers_direction")
        position = c3.selectbox("Position", ["All", "Goalkeeper", "Defender", "Midfielder", "Forward"],
                                key="transfers_position")
        team = c4.selectbox("Team", ["All"] + sorted(players["team_name"].unique()), key="transfers_team")

        c5, c6, c7 = st.columns(3)
        reason = c5.selectbox("Reason", ["All", "injury/news", "form/other"], key="transfers_reason")
        min_minutes = c6.slider("Min minutes", 0, 900, 0, 30, key="transfers_min_minutes")
        n = c7.slider("Rows to show", 5, 30, 10, 5, key="transfers_rows")

    metric = TRANSFER_METRICS[metric_label]
    mask = players["minutes"] >= min_minutes
    if position != "All":
        mask &= players["position"] == position
    if team != "All":
        mask &= players["team_name"] == team
    if reason != "All":
        mask &= players["reason"] == reason

    df = players[mask].sort_values(metric, ascending=(direction == "Lowest")).head(n)[TRANSFER_COLS]
    if df.empty:
        st.info("No players match these filters.")
    else:
        st.dataframe(df, column_config=TRANSFER_CONFIG, hide_index=True, use_container_width=True)
    st.caption("'Net transfers (GW)' covers only the current gameweek and resets when the next one starts, "
               "so don't compare it across days without checking which gameweek it belongs to.")

    # ---------- differentials ----------
    st.subheader("Differential finder")
    st.write("Low-owned players whose underlying attacking numbers are strong. "
             "Use the 300+ minute default, because per-90 rates from a few minutes are noise.")

    with st.container(border=True):
        d1, d2, d3 = st.columns(3)
        max_own = d1.slider("Max ownership %", 1, 30, 10, key="diff_max_own")
        diff_minutes = d2.slider("Min minutes", 0, 900, 300, 30, key="diff_min_minutes")
        positions = d3.multiselect("Positions", ["Midfielder", "Forward"],
                               default=["Midfielder", "Forward"], key="diff_positions")

    # position medians come from players with 300+ minutes, so tiny samples don't drag them
    medians = players[players["minutes"] >= 300].groupby("position")["xgi_per90"].median()

    diff = players[
        (players["minutes"] >= diff_minutes)
        & (players["selected_by_percent"] <= max_own)
        & (players["position"].isin(positions))
    ].copy()
    diff["xgi_vs_median"] = diff["xgi_per90"] / diff["position"].map(medians)
    diff = diff.sort_values("xgi_per90", ascending=False).head(15)

    diff_cols = ["web_name", "team_name", "position", "price", "selected_by_percent", "minutes",
                 "xgi_per90", "xgi_vs_median", "tp_per90", "status", "news"]
    diff_config = {
        **TRANSFER_CONFIG,
        "xgi_vs_median": st.column_config.NumberColumn("xGI vs median", format="%.2fx"),
        "tp_per90": st.column_config.NumberColumn("Pts / 90", format="%.2f"),
        "status": st.column_config.TextColumn("Status"),
    }
    if diff.empty:
        st.info("No players match these filters.")
    else:
        st.dataframe(diff[diff_cols], column_config=diff_config, hide_index=True, use_container_width=True)
    st.caption("'xGI vs median' of 1.00x means average for the position. A real differential should be "
               "clearly above that (we used 1.2x as 'clearly'), with fit status and a regular starting place.")

GW_TABLE_COLS = ["web_name", "team_name", "position", "minutes", "goals_scored",
                 "assists", "clean_sheets", "bonus", "total_points"]

GW_CONFIG = {
    "web_name": st.column_config.TextColumn("Player"),
    "team_name": st.column_config.TextColumn("Team"),
    "position": st.column_config.TextColumn("Position"),
    "minutes": st.column_config.NumberColumn("Minutes"),
    "goals_scored": st.column_config.NumberColumn("Goals"),
    "assists": st.column_config.NumberColumn("Assists"),
    "clean_sheets": st.column_config.NumberColumn("Clean sheets"),
    "bonus": st.column_config.NumberColumn("Bonus"),
    "total_points": st.column_config.NumberColumn("Points"),
}


def gameweek_tab():
    events = build_events()
    if events.empty:
        st.info("No gameweeks have finished yet.")
        return

    gw = st.selectbox("Gameweek", list(events["id"]), index=len(events) - 1,
                      format_func=lambda g: f"Gameweek {g}", key="gw_select")
    row = events[events["id"] == gw].iloc[0]
    live = load_live(int(gw))

    # captain's points come from the live data, looked up by ID
    cap_id = row["most_captained_id"]
    cap_pts = live.loc[live["id"] == cap_id, "total_points"]
    cap_pts = int(cap_pts.iloc[0]) if not cap_pts.empty else None
    
    with st.container(border=True):

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Average score", int(row["average_entry_score"]))
        c2.metric("Highest score", int(row["highest_score"]))
        c3.metric("Top scorer", row["top_element_name"], f"{int(row['top_points'])} pts", delta_color="off")
        c4.metric("Most captained", row["most_captained_name"],
                f"{cap_pts} pts (x2 = {cap_pts * 2})" if cap_pts is not None else "n/a",
                delta_color="off")

        c5, c6, c7 = st.columns(3)
        c5.metric("Most selected", row["most_selected_name"])
        c6.metric("Most transferred in", row["most_transferred_in_name"])
        c7.metric("Transfers made", f"{int(row['transfers_made']):,}")
        st.caption("A captain's points count double, so the gap between the captain and the top scorer "
                "is bigger than it looks. Transfers in GW1 show 0 because the first squad is free.")

    with st.container(border=True):

        st.subheader(f"Top scorers: gameweek {gw}")
        t1, t2 = st.columns(2)
        position = t1.selectbox("Position", ["All", "Goalkeeper", "Defender", "Midfielder", "Forward"],
                                key="gw_position")
        n = t2.slider("Rows to show", 5, 30, 10, 5, key="gw_rows")

        df = live if position == "All" else live[live["position"] == position]
        df = df.sort_values("total_points", ascending=False).head(n)[GW_TABLE_COLS]
        st.dataframe(df, column_config=GW_CONFIG, hide_index=True, use_container_width=True)

    with st.container(border=True):

        st.subheader("Season so far")
        trend = events.melt(id_vars="id", value_vars=["average_entry_score", "highest_score"],
                            var_name="measure", value_name="points")
        trend["measure"] = trend["measure"].map({"average_entry_score": "Average", "highest_score": "Highest"})
        fig = px.line(trend, x="id", y="points", color="measure", markers=True,
                    labels={"id": "Gameweek", "points": "Manager score", "measure": ""})
        st.plotly_chart(fig, use_container_width=True)

DETAIL_EXTRA = {
    "Forward":    ["expected_goals", "expected_assists", "expected_goal_involvements"],
    "Midfielder": ["expected_goals", "expected_assists", "expected_goal_involvements"],
    "Defender":   ["expected_goals_conceded", "defensive_contribution",
                   "clearances_blocks_interceptions", "tackles", "recoveries"],
    "Goalkeeper": ["saves", "expected_goals_conceded"],
}
DETAIL_BASE = ["round", "kickoff_text", "opponent_team", "venue", "minutes",
               "total_points", "goals_scored", "assists", "clean_sheets", "bonus", "price"]


def player_detail_tab(players):
    info = players.set_index("id")
    ids = list(players.sort_values("web_name")["id"])

    def label(pid):
        r = info.loc[pid]
        return f"{r['web_name']} ({r['team_name_short']})"

    # searchable: click the box and start typing a name
    pid = st.selectbox("Player", ids, format_func=label, key="detail_pid")
    p = info.loc[pid]

    with st.container(border=True):
        img, text = st.columns([2, 5])
        if photo_exists(p["photo_url"]):
            img.image(p["photo_url"], width=200)
        else:
            img.caption("No photo available")

        with text:
            st.subheader(f"{p['first_name']} {p['second_name']}")
            st.caption(f"{p['team_name']} | {p['position']}")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Price", f"£{p['price']:.1f}m")
            m2.metric("Total points", int(p["total_points"]))
            m3.metric("Owned", f"{p['selected_by_percent']:.1f}%")
            m4.metric("Minutes", int(p["minutes"]))
        if p["news"]:
            st.warning(p["news"])

    hist, fixtures = load_player_detail(int(pid))
    
    with st.container(border=True):

        st.subheader("Season so far")
        if hist.empty:
            st.info("No matches played yet.")
        else:
            # sum over double gameweeks so each round is one point on the line
            per_round = hist.groupby("round", as_index=False)["total_points"].sum()
            fig = px.line(per_round, x="round", y="total_points", markers=True,
                        labels={"round": "Gameweek", "total_points": "Points"})
            st.plotly_chart(fig, use_container_width=True)

            cols = DETAIL_BASE + DETAIL_EXTRA[p["position"]]
            st.dataframe(hist[cols].round(2), hide_index=True, use_container_width=True)

    with st.container(border=True):

        st.subheader("Upcoming fixtures")
        if fixtures.empty:
            st.info("None scheduled.")
        else:
            st.dataframe(
                fixtures.style.background_gradient(cmap="RdYlGn_r", subset=["difficulty"], vmin=1, vmax=5),
                hide_index=True, use_container_width=True)

COMPARE_ROWS = [
    ("Price (£m)", "price", "{:.1f}", True),
    ("Total points", "total_points", "{:.0f}", False),
    ("Points per £m", "points_per_million", "{:.2f}", False),
    ("Points per 90", "tp_per90", "{:.2f}", False),
    ("Minutes", "minutes", "{:.0f}", False),
    ("Goals", "goals_scored", "{:.0f}", False),
    ("Assists", "assists", "{:.0f}", False),
    ("xG", "expected_goals", "{:.2f}", False),
    ("xA", "expected_assists", "{:.2f}", False),
    ("xGI per 90", "xgi_per90", "{:.2f}", False),
    ("xGC per 90", "xgc_per90", "{:.2f}", True),
    ("DefCon per 90", "defcon_per90", "{:.2f}", False),
    ("Bonus", "bonus", "{:.0f}", False),
    ("Clean sheets", "clean_sheets", "{:.0f}", False),
    ("Owned %", "selected_by_percent", "{:.1f}", False),
]


def compare_tab(players):
    info = players.set_index("id")
    ids = list(players.sort_values("web_name")["id"])

    def label(pid):
        r = info.loc[pid]
        return f"{r['web_name']} ({r['team_name_short']})"

    with st.container(border=True):
        c1, c2 = st.columns(2)
        a_id = c1.selectbox("Player A", ids, format_func=label, key="cmp_a")
        b_id = c2.selectbox("Player B", ids, index=1, format_func=label, key="cmp_b")

    if a_id == b_id:
        st.info("Pick two different players.")
        return
    a, b = info.loc[a_id], info.loc[b_id]

    with st.container(border=True):
        col_a, col_b = st.columns(2)
        for col, p in ((col_a, a), (col_b, b)):
            with col:
                st.subheader(p["web_name"])
                st.caption(f"{p['team_name']} | {p['position']}")
                if photo_exists(p["photo_url"]):
                    st.image(p["photo_url"], width=140)
                if p["news"]:
                    st.warning(p["news"])

    # stats table: the better value in each row is marked with a star
    rows = []
    for name, col, fmt, lower_better in COMPARE_ROWS:
        va, vb = a[col], b[col]
        fa = fmt.format(va) if pd.notna(va) else "-"
        fb = fmt.format(vb) if pd.notna(vb) else "-"
        if pd.notna(va) and pd.notna(vb) and va != vb and col not in ("minutes", "selected_by_percent"):
            a_wins = (va < vb) if lower_better else (va > vb)
            fa, fb = (fa + " ★", fb) if a_wins else (fa, fb + " ★")
        rows.append({"Stat": name, a["web_name"]: fa, b["web_name"]: fb})

    with st.container(border=True):
        st.subheader("Side by side")
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        st.caption("★ marks the better value. Minutes and ownership have no star, since more isn't "
                   "'better'. Compare rates per 90 only when both players have 300+ minutes, and "
                   "remember xGI and xGC mean little for goalkeepers and defenders respectively.")

    # points per gameweek overlay
    hist_a, _ = load_player_detail(int(a_id))
    hist_b, _ = load_player_detail(int(b_id))
    frames = []
    for name, h in ((a["web_name"], hist_a), (b["web_name"], hist_b)):
        if not h.empty:
            per_round = h.groupby("round", as_index=False)["total_points"].sum()
            per_round["player"] = name
            frames.append(per_round)

    with st.container(border=True):
        st.subheader("Points per gameweek")
        if frames:
            both = pd.concat(frames)
            fig = px.line(both, x="round", y="total_points", color="player", markers=True,
                          labels={"round": "Gameweek", "total_points": "Points", "player": ""})
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Neither player has played yet.")

SECTIONS = ["Players", "Teams", "Fixtures", "Transfers", "Gameweek", "Player detail", "Compare"]

# a table click leaves a "goto" note; apply it BEFORE the radio is created
if "goto" in st.session_state:
    section, pid = st.session_state.pop("goto")
    st.session_state["nav"] = section
    st.session_state["detail_pid"] = pid

with st.container(border=True):

    section = st.radio("Section", SECTIONS, horizontal=True, key="nav", label_visibility="collapsed")

if section == "Players":
    player_table_tab(players)
elif section == "Teams":
    teams_tab()
elif section == "Fixtures":
    fixtures_tab()
elif section == "Transfers":
    transfers_tab(players)
elif section == "Gameweek":
    gameweek_tab()
elif section == "Player detail":
    player_detail_tab(players)
else:
    compare_tab(players)