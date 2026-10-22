# FPL API research

Researched on **19 October 2026**. “Best” here means the best fit for a personal app that needs FPL-specific prices, points, fixtures and squad information. This is an engineering assessment of suitability, not a benchmark of forecast accuracy.

## Recommendation

Use the **JSON API behind the FPL website** as the core dataset. It is the direct source for the game's own player IDs and values, and avoids reconciling an unrelated provider's IDs. Public reads work without an API key. It is an undocumented website backend rather than a supported developer product; cache requests and handle failures/schema changes.

Treat predictions as a separate layer. A data API does not establish which players will score most next week. Start with the included explicit heuristic, and compare it against pre-deadline forecasts before relying on it. The app can accept a replacement model through CSV.

## Sources compared

| Source | Fit for this app | Access and tradeoff | Decision |
| --- | --- | --- | --- |
| [FPL website JSON](https://fantasy.premierleague.com/api/bootstrap-static/) | Native FPL prices, points, player IDs and clubs | No key for public reads; no supported public API contract | **Core source used in the app** |
| [FPL Cat API](https://fplcat.com/developers) | Whole-gameweek expected points keyed to FPL player IDs | Advertises free, keyless next-GW JSON/CSV; limited to one published week. Personal/research use; commercial republication needs permission | Optional feed integrated with GW checking, attribution and timestamp display |
| [Sideline Quant feed](https://sidelinequant.com/data) | Forecasts, expected minutes and uncertainty fields | Publisher lists CC BY 4.0, requiring attribution. Rows are per fixture, so sum `xP` across doubles; it keeps only the current feed | Candidate for a future adapter; normalize to the app's CSV format today |
| [vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League) | Season archives and per-gameweek CSVs | Repository data rather than a live API; inspect season coverage and freshness | Useful for future backtesting; not used for live recommendations |
| [Python `fpl` wrapper](https://fpl.readthedocs.io/en/latest/user/quickstart.html) | Convenient Python access to the same underlying data | Adds an asynchronous wrapper; private team access requires authentication | Direct HTTP is simpler for this small read-only app |
| [API-Football](https://www.api-football.com/pricing) | General football statistics, fixtures and injury enrichment | Keyed plans; its pricing page lists 100 requests/day on the free tier with season restrictions | Possible enrichment later; a general football feed does not replace FPL-specific prices/scoring |

No claim is made that one forecasting provider is more accurate than another. Provider documentation establishes advertised fields and access, not predictive quality or service reliability.

## Endpoints used

Base: `https://fantasy.premierleague.com/api/`

| Path | Purpose | App behavior |
| --- | --- | --- |
| [`bootstrap-static/`](https://fantasy.premierleague.com/api/bootstrap-static/) | Players, prices, points, availability, clubs and gameweek metadata | Cached 15 min; `now_cost / 10` gives £m |
| [`fixtures/`](https://fantasy.premierleague.com/api/fixtures/) | Scheduled matches, gameweek assignments and difficulty | Cached with bootstrap; postponed fixtures without a gameweek are not assigned speculatively |
| `element-summary/{player_id}/` | Player fixture history | Loaded only on request, cached 1 hour; sums doubles before plotting |
| `entry/{team_id}/event/{gameweek}/picks/` | Public squad for a deadline that has passed | Cached 15 min; user verifies changes since that deadline |

Optional forecast endpoint: `https://fplcat.com/api/v1/projections`. Cache 15 minutes, validate its published gameweek, and show attribution. There is no promise of uptime. Uploaded CSV forecasts can be used when a feed is unavailable.

The private `my-team/{team_id}/` endpoint requires a signed-in session. This app avoids that login flow and asks the user to enter missing current-team information instead. See the [wrapper's authentication documentation](https://fpl.readthedocs.io/en/latest/user/quickstart.html#authentication).

## Rules checked against primary sources

- [How to pick a squad](https://www.premierleague.com/en/news/2174419/fpl-basics-how-to-pick-a-squad): initial £100m budget, 15-player positional composition and maximum three players per club.
- [Managing your team](https://www.premierleague.com/en/news/2174899): starting-XI formation restrictions and substitute rules.
- [How to make transfers](https://www.premierleague.com/en/news/2174907): up to five banked free transfers, four-point additional-transfer cost, and selling-price treatment.
- [Full FPL rules](https://fantasy.premierleague.com/help/rules): authoritative place to check subsequent changes. Chips are outside this version's optimization scope.

## Verification limits

Web browsing could open the public FPL bootstrap and fixtures URLs and the provider documentation. The optional FPL Cat and Sideline Quant JSON endpoints were not accessible through the browsing tool; their integration details are based on their publishers' documentation. The code-execution environment blocked outbound sockets to FPL and PyPI, so no live Python-to-provider integration check was possible here. The app and optimization tests use synthetic data and mocked HTTP failures. Test the live sources from a normally connected terminal before using recommendations.
