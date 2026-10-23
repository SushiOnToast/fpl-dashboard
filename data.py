import numpy as np
import pandas as pd
import requests
import streamlit as st

BASE = "https://fantasy.premierleague.com/api"
PHOTO_URL = "https://resources.premierleague.com/premierleague/photos/players/110x140/p{code}.png"


KEEP = [
    # identity
    "id", "code", "web_name", "first_name", "second_name", "team", "team_code", "element_type",
    # price and value
    "now_cost", "cost_change_start", "value_form", "value_season",
    # performance
    "total_points", "points_per_game", "form", "event_points",
    "minutes", "starts", "goals_scored", "assists", "clean_sheets",
    "goals_conceded", "saves", "bonus", "bps",
    "yellow_cards", "red_cards", "own_goals",
    "penalties_saved", "penalties_missed", "defensive_contribution",
    # underlying stats
    "expected_goals", "expected_assists", "expected_goal_involvements",
    "expected_goals_conceded", "influence", "creativity", "threat", "ict_index",
    # ownership and transfers
    "selected_by_percent", "transfers_in", "transfers_out",
    "transfers_in_event", "transfers_out_event",
    # availability
    "status", "news", "news_added",
    "chance_of_playing_this_round", "chance_of_playing_next_round",
    # set pieces
    "penalties_order", "corners_and_indirect_freekicks_order", "direct_freekicks_order",
    # FPL's own predictions
    "ep_this", "ep_next",
]

NUMERIC_COLS = [
    "value_form", "value_season", "points_per_game", "form",
    "expected_goals", "expected_assists", "expected_goal_involvements",
    "expected_goals_conceded", "influence", "creativity", "threat", "ict_index",
    "selected_by_percent", "ep_this", "ep_next",
]

@st.cache_data(ttl=86400)
def photo_exists(url):
    try:
        return requests.head(url, timeout=5).status_code == 200
    except Exception:
        return False

@st.cache_data(ttl=600)  # reuse the result for 10 minutes
def load_raw():
    bootstrap = requests.get(f"{BASE}/bootstrap-static/", timeout=30).json()
    fixtures = requests.get(f"{BASE}/fixtures/", timeout=30).json()
    return bootstrap, fixtures


@st.cache_data(ttl=600)
def load_players():
    bootstrap, _ = load_raw()
    players = pd.DataFrame(bootstrap["elements"])[KEEP].copy()

    # --- types and units ---
    players["price"] = players["now_cost"] / 10
    for col in NUMERIC_COLS:
        players[col] = pd.to_numeric(players[col])
    players["news_added"] = pd.to_datetime(players["news_added"])
    players["news"] = players["news"].fillna("")

    # --- team and position names (keep the ID columns) ---
    teams = pd.DataFrame(bootstrap["teams"])[["id", "name", "short_name"]]
    positions = pd.DataFrame(bootstrap["element_types"])[["id", "singular_name", "singular_name_short"]]

    players = players.merge(teams, left_on="team", right_on="id", how="left", suffixes=("", "_team"))
    players = players.merge(positions, left_on="element_type", right_on="id", how="left", suffixes=("", "_type"))
    players = players.drop(columns=["id_team", "id_type"]).rename(columns={
        "name": "team_name",
        "short_name": "team_name_short",
        "singular_name": "position",
        "singular_name_short": "position_short",
    })

    # --- missing values: NaN means "no concern" only for available players ---
    avail = players["status"] == "a"
    for col in ["chance_of_playing_this_round", "chance_of_playing_next_round"]:
        players.loc[avail, col] = players.loc[avail, col].fillna(100)

    # --- derived columns ---
    players["points_per_million"] = players["total_points"] / players["price"]
    players["xg_diff"] = players["goals_scored"] - players["expected_goals"]

    players["nineties"] = players["minutes"] / 90
    n = players["nineties"].replace(0, np.nan)   # 0 minutes -> NaN, not inf
    players["tp_per90"] = players["total_points"] / n
    players["xgi_per90"] = players["expected_goal_involvements"] / n
    players["gi_per90"] = (players["goals_scored"] + players["assists"]) / n
    players["gi_diff_per90"] = players["gi_per90"] - players["xgi_per90"]
    players["defcon_per90"] = players["defensive_contribution"] / n
    players["xgc_per90"] = players["expected_goals_conceded"] / n

    players["net_transfers_event"] = players["transfers_in_event"] - players["transfers_out_event"]
    players["net_transfers"] = players["transfers_in"] - players["transfers_out"]
    players["price_change"] = players["cost_change_start"] / 10      # tenths of £m -> £m
    players["reason"] = np.where(players["news"] != "", "injury/news", "form/other")

    players["photo_url"] = players["code"].map(lambda c: PHOTO_URL.format(code=c))

    return players

@st.cache_data(ttl=600)
def load_teams():
    bootstrap, _ = load_raw()
    return pd.DataFrame(bootstrap["teams"])


@st.cache_data(ttl=600)
def load_fixtures():
    _, fixtures = load_raw()
    return pd.DataFrame(fixtures)


def team_lookup(column="name"):
    """Series mapping team ID -> name (or short_name). Reused by every tab."""
    return load_teams().set_index("id")[column]


@st.cache_data(ttl=600)
def build_league_table():
    fixtures = load_fixtures()
    players = load_players()

    played = fixtures[fixtures["finished"]].copy()
    if played.empty:
        return pd.DataFrame()

    # one row per team per match: the home view, then the away view
    home = pd.DataFrame({
        "team": played["team_h"],
        "gf": played["team_h_score"].astype(int),
        "ga": played["team_a_score"].astype(int),
    })
    away = pd.DataFrame({
        "team": played["team_a"],
        "gf": played["team_a_score"].astype(int),
        "ga": played["team_h_score"].astype(int),
    })
    results = pd.concat([home, away], ignore_index=True)

    results["won"] = results["gf"] > results["ga"]
    results["drawn"] = results["gf"] == results["ga"]
    results["lost"] = results["gf"] < results["ga"]

    table = results.groupby("team").agg(
        played=("team", "size"),
        won=("won", "sum"),
        drawn=("drawn", "sum"),
        lost=("lost", "sum"),
        gf=("gf", "sum"),
        ga=("ga", "sum"),
    )
    table["points"] = table["won"] * 3 + table["drawn"]
    table["gd"] = table["gf"] - table["ga"]
    table["gf_per_game"] = table["gf"] / table["played"]
    table["ga_per_game"] = table["ga"] / table["played"]

    # xG only exists per player, so sum it by team ID
    xg = players.groupby("team")["expected_goals"].sum()
    table["xg"] = table.index.map(xg)
    table["gf_minus_xg"] = table["gf"] - table["xg"]

    table["team_name"] = table.index.map(team_lookup("name"))

    # PL tiebreakers: points, then goal difference, then goals scored
    table = table.sort_values(["points", "gd", "gf"], ascending=False).reset_index()
    table.insert(0, "rank", range(1, len(table) + 1))
    return table

@st.cache_data(ttl=600)
def build_match_list():
    """One row per match, with names, score text, kickoff and both difficulties."""
    fx = load_fixtures()
    fx = fx[fx["event"].notna()].copy()          # drop unscheduled matches
    fx["event"] = fx["event"].astype(int)

    names = team_lookup("name")
    fx["home"] = fx["team_h"].map(names)
    fx["away"] = fx["team_a"].map(names)

    h = fx["team_h_score"].astype("Int64").astype(str)
    a = fx["team_a_score"].astype("Int64").astype(str)
    fx["score"] = np.where(fx["started"], h + " - " + a, "v")

    fx["kickoff"] = pd.to_datetime(fx["kickoff_time"], utc=True).dt.tz_convert("Asia/Kolkata")
    fx["kickoff_text"] = fx["kickoff"].dt.strftime("%a %d %b, %H:%M").fillna("TBC")

    return fx.rename(columns={"team_h_difficulty": "home_diff", "team_a_difficulty": "away_diff"})


def default_gameweek(matches):
    """First gameweek with an unfinished match, or the last one if the season is over."""
    unfinished = matches.loc[~matches["finished"], "event"]
    return int(unfinished.min()) if not unfinished.empty else int(matches["event"].max())


@st.cache_data(ttl=600)
def build_fixture_grids():
    """Team-by-gameweek grids: difficulty (colour), cell text, and hover text."""
    fx = load_fixtures()
    fx = fx[fx["event"].notna()].copy()
    fx["event"] = fx["event"].astype(int)

    def side(team, opp, diff, gf, ga, venue):
        return pd.DataFrame({
            "team": fx[team], "opp": fx[opp], "event": fx["event"],
            "finished": fx["finished"], "difficulty": fx[diff],
            "gf": fx[gf], "ga": fx[ga], "venue": venue,
        })

    long = pd.concat([
        side("team_h", "team_a", "team_h_difficulty", "team_h_score", "team_a_score", "H"),
        side("team_a", "team_h", "team_a_difficulty", "team_a_score", "team_h_score", "A"),
    ], ignore_index=True)

    names, shorts = team_lookup("name"), team_lookup("short_name")
    long["team_name"] = long["team"].map(names)
    opp_short = long["opp"].map(shorts)
    opp_name = long["opp"].map(names)
    score = long["gf"].astype("Int64").astype(str) + "-" + long["ga"].astype("Int64").astype(str)
    v = " (" + long["venue"] + ")"

    long["cell_text"] = np.where(long["finished"], opp_short + " " + score + v, opp_short + v)
    long["hover_text"] = np.where(long["finished"], opp_name + " " + score + v, opp_name + v)

    long["done"] = long["finished"].astype(int)

    # pivot_table (not pivot) so a double gameweek doesn't raise a duplicate error
    def grid(col, agg):
        return long.pivot_table(index="team_name", columns="event", values=col, aggfunc=agg)

    return (grid("difficulty", "mean"), grid("cell_text", " + ".join),
        grid("hover_text", " + ".join), grid("done", "min"))

PLAYER_EVENT_COLS = ["most_selected", "most_captained", "most_vice_captained",
                     "most_transferred_in", "top_element"]


@st.cache_data(ttl=600)
def build_events():
    """One row per finished gameweek, with player IDs also mapped to names."""
    bootstrap, _ = load_raw()
    players = load_players()

    events = pd.DataFrame(bootstrap["events"])
    events = events[events["finished"]].copy()
    names = players.set_index("id")["web_name"]

    for col in PLAYER_EVENT_COLS:
        ids = pd.to_numeric(events[col]).astype("Int64")
        events[f"{col}_id"] = ids
        events[f"{col}_name"] = ids.map(names)

    events["top_points"] = events["top_element_info"].apply(
        lambda d: d["points"] if isinstance(d, dict) else np.nan)

    keep = ["id", "name", "average_entry_score", "highest_score", "transfers_made", "top_points"]
    keep += [f"{c}_{s}" for c in PLAYER_EVENT_COLS for s in ("id", "name")]
    return events[keep].sort_values("id").reset_index(drop=True)


@st.cache_data(ttl=3600)   # a finished gameweek never changes
def load_live(gw):
    url = f"{BASE}/event/{gw}/live/"
    elements = requests.get(url, timeout=30).json()["elements"]
    live = pd.DataFrame(elements)
    stats = pd.json_normalize(live["stats"])
    out = pd.concat([live[["id"]], stats], axis=1)
    players = load_players()
    return out.merge(players[["id", "web_name", "team_name", "position"]], on="id", how="left")

HIST_KEEP = [
    "round", "opponent_team", "was_home", "kickoff_time", "team_h_score", "team_a_score",
    "minutes", "starts",
    "total_points", "goals_scored", "assists", "clean_sheets", "goals_conceded", "saves", "bonus", "bps",
    "expected_goals", "expected_assists", "expected_goal_involvements", "expected_goals_conceded",
    "defensive_contribution", "clearances_blocks_interceptions", "tackles", "recoveries",
    "value", "selected", "transfers_balance",
]


def _local(series):
    return pd.to_datetime(series, utc=True).dt.tz_convert("Asia/Kolkata")


@st.cache_data(ttl=600)
def load_player_detail(pid):
    data = requests.get(f"{BASE}/element-summary/{pid}/", timeout=30).json()
    names = team_lookup("name")

    hist = pd.DataFrame(data["history"])
    if not hist.empty:
        hist = hist[HIST_KEEP].copy()
        hist["price"] = hist["value"] / 10
        for col in ["expected_goals", "expected_assists",
                    "expected_goal_involvements", "expected_goals_conceded"]:
            hist[col] = pd.to_numeric(hist[col])
        hist["opponent_team"] = hist["opponent_team"].map(names)
        hist["kickoff_text"] = _local(hist["kickoff_time"]).dt.strftime("%a %d %b, %H:%M")
        hist["venue"] = np.where(hist["was_home"], "H", "A")

    fixtures = pd.DataFrame(data["fixtures"])
    if not fixtures.empty:
        opp_id = fixtures["team_a"].where(fixtures["is_home"], fixtures["team_h"])
        fixtures["opponent"] = opp_id.map(names)
        fixtures["venue"] = np.where(fixtures["is_home"], "H", "A")
        fixtures["kickoff_text"] = _local(fixtures["kickoff_time"]).dt.strftime("%a %d %b, %H:%M").fillna("TBC")
        fixtures = (fixtures[["event_name", "kickoff_text", "opponent", "venue", "difficulty"]]
                    .rename(columns={"event_name": "gameweek"}))

    return hist, fixtures