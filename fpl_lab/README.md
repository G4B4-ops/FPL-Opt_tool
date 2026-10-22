# FPL Lab

A local Streamlit app for comparing FPL players by points and price, generating squads for upcoming gameweeks, and suggesting transfers for a current team.

## Start on Windows

Your complete project folder is `C:\Users\gabri\OneDrive\Dokumente\fpl_lab`.
Open this folder, or its `fpl-lab.code-workspace` file, in VS Code.
The local `.venv` already has the app's dependencies installed. To start the app,
press **F5** and select **FPL Lab: Streamlit**, or run this in the VS Code terminal:

```powershell
.\.venv\Scripts\python.exe -m streamlit run appfantasy.py
```

You can also use **Terminal > Run Task > FPL Lab: Start app**.
Keep `appfantasy.py`, the nested `fpl_lab` package, and the support files together
in this project folder. Open the outer folder containing `appfantasy.py`.

For a fresh setup on another computer:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run appfantasy.py
```

Python 3.11 or newer is required. If `python` opens the Microsoft Store, use `py` instead, or choose your installed Python executable in VS Code. You do not need to activate the environment.

Alternatively, run `start.ps1` from this folder. It creates the environment if needed, installs dependencies, and starts Streamlit. VS Code's **Run and Debug → FPL Lab: Streamlit** configuration also starts the app once dependencies are installed. Open the local URL printed by Streamlit, usually http://localhost:8501.

No API key or FPL password is needed. Internet access is needed for live data. Turn on **Use synthetic demo data** in the sidebar to explore offline. Demo players and recommendations are fictional.

## What you can do

- Choose a workspace from the large home-page cards; an imported public team is shown as a projected lineup before transfer suggestions.
- **Compare players:** filter by position, club, price, minutes, or name; explore points versus price in an interactive chart; compare up to four players; load gameweek points histories; export a CSV.
- **Build a squad:** choose any upcoming gameweek, a budget, players to include/exclude, and a forecast. Generate a legal 15-player squad, starting XI, captain, vice captain, and substitutes. Optionally optimize one fixed squad over up to six weeks with separate lineups each week. Download the plan.
- **Improve my team:** import a public post-deadline squad using the numeric FPL team ID, or select 15 players manually. Verify the squad, actual selling prices, money in the bank and remaining free transfers. Compare transfer packages with the best unchanged lineup, including captaincy and four-point hits.
- **Data & methodology:** see how forecasts and constraints work, and read the API research.

The team ID is the number after `/entry/` in your FPL points-page URL. A league ID is different. Imported picks reflect the chosen deadline, including any chip active then; edit the squad if you have since made transfers or used a Free Hit.

## Forecast options

1. **Fixture model:** a transparent, untrained heuristic using form, points per game, minutes, current availability, fixture difficulty and home/away. It handles blank and double gameweeks. It has not been backtested.
2. **FPL estimates:** uses the `ep_next` field for the API's next gameweek only. Later weeks use the fixture model. It does not multiply a whole-gameweek estimate by fixture count again.
3. **FPL Cat:** optional, next-gameweek-only feed from https://fplcat.com/developers. The app checks its gameweek and displays its computed timestamp; uncovered forecasts use the fixture model. Attribution is shown in the UI. Check its usage terms before commercial redistribution.
4. **Upload CSV:** supply your own whole-gameweek expected points. Any missing player/week falls back to the fixture model and the source is identified. The table below is a format illustration; IDs must match the current season.

```csv
player_id,gameweek,expected_points
12,8,6.35
411,8,6.19
```

The upload must contain exactly one row per player/gameweek combination, valid current-season player IDs, gameweeks 1–38 and finite numeric points. Sum individual fixture forecasts for a double gameweek before uploading. Known blank weeks are always zero, even with an uploaded estimate. Export the player comparison table to find IDs. `examples/projections_template.csv` contains headers only.

## What “best” means

SciPy's HiGHS mixed-integer solver maximizes projected starting-XI points plus the captain's extra score. Fresh squad generation also gives a configurable weight to bench points (default 0.05); setting this to zero optimizes XI and captain alone. Displayed projected points exclude the bench. Transfer suggestions use a zero bench weight to compare net scoring gains directly.

The constraints enforce 2 goalkeepers, 5 defenders, 5 midfielders and 3 forwards; at most three players per club; and the selected budget. Each XI has one goalkeeper, at least three defenders, at least two midfielders and at least one forward. Only available/doubtful players can be newly bought; unavailable players can be retained.

Each solve has a 25-second limit. An optimal solution is labeled as such within numerical tolerance. A timeout incumbent is checked for integrality and feasibility, and labeled as having unproven optimality. No feasible solution produces an actionable error. Forecast uncertainty remains even when the mathematical solution is optimal.

Transfer budgeting uses your actual selling prices for retained players and current market prices for new purchases. This accounts for money tied up in players whose sale value is below their current market price. Public picks do not provide exact selling prices, current bank or remaining free transfers: you must enter these yourself.

This version plans one set of transfers now and holds that squad for the chosen horizon. It does not model future transfers, free-transfer rollover value, future price changes, chips, automatic substitutions, or vice-captain fallback. Bench order is based on forecast points; it does not model substitution probabilities. Current fitness status is held constant across future weeks, so a player expected to recover may be undervalued. Historical player points use current season data and are descriptive, not a historical backtest.

## Data access and resilience

The read-only FPL client uses HTTPS, timeouts and bounded retries. Streamlit caches public datasets, imported picks and optional forecasts for 15 minutes; player histories for one hour. **Refresh data** clears this cache and previous generated results. Live failures show an error and offer explicit demo mode; live data is never silently replaced by fictional data. The app does not submit transfers or ask for account credentials.

See [API_RESEARCH.md](API_RESEARCH.md) for the sources examined on 19 October 2026. These are the website's own endpoints, not a supported developer API with an uptime guarantee. Review provider terms before publishing or redistributing data.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests run offline with synthetic data. They cover budget and formation constraints, captain scoring, blank/double gameweeks, price handling, transfer hits and limits, uploaded forecast validation, infeasible inputs, and the actual Streamlit app flows. A small exhaustive enumeration independently checks the optimizer's result. HTTP failures are mocked; live upstream availability requires a separate online check.

## Files

```text
appfantasy.py                    Streamlit screens and cached data loading
fpl_lab/api.py            Read-only FPL and optional forecast clients
fpl_lab/data.py           Price normalization and squad validation
fpl_lab/projections.py    Fixture model, forecast imports, source labels
fpl_lab/optimizer.py      Squad/lineup/captain MILP and transfer comparison
fpl_lab/ui.py             Charts, pitch and exports
fpl_lab/demo.py           Clearly marked synthetic offline dataset
tests/                   Core regression tests and Streamlit AppTest
API_RESEARCH.md           API recommendation, comparison and source links
requirements.txt         Runtime dependencies
.streamlit/config.toml   Theme and local server settings
.vscode/                 Interpreter, debugger and test discovery settings
start.ps1                Windows setup/launch helper
```
