# FPL Dashboard

A small dashboard for exploring and organising data from the Fantasy Premier League (FPL) API. I made this project for practice and to familiarise myself with the data; it is an exploratory project, not a prediction or team-selection service.

## How it came together

The data work started in the Google Colab notebook, [fpl_dashboard.ipynb](./fpl_dashboard.ipynb). It retrieves data from the FPL API with `requests`, then uses `pandas` (and `numpy`) to clean, combine, and explore it. The notebook also uses Plotly and `ipywidgets` for charts and interactive exploration.

That initial analysis was then transferred into a Streamlit dashboard. The dashboard fetches FPL data and organises it for interactive tables and visualisations.

## Dashboard

The dashboard includes sections for:

- **Players:** filter and sort player statistics.
- **Teams:** view a league table and compare goals with expected goals.
- **Fixtures:** browse gameweek matches and fixture difficulty.
- **Transfers:** explore transfer activity and find low-ownership differentials.
- **Gameweek:** review gameweek and live player information.
- **Player detail and Compare:** inspect player history, upcoming fixtures, and compare players.

Data is retrieved from the FPL API and cached by the app for short periods to reduce repeated requests. The dashboard needs an internet connection to load current data.

## Technologies

- **Dashboard:** Python, Streamlit, pandas, NumPy, requests, and Plotly.
- **Initial analysis:** Google Colab / Jupyter notebook, Python, pandas, NumPy, requests, Plotly, and `ipywidgets`.
- **Data source:** Fantasy Premier League API.

## Run locally

Requires Python and an internet connection.

```bash
pip install -r requirements.txt
streamlit run app.py
```

Streamlit prints a local URL in the terminal when the app starts.
