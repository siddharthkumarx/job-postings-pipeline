# README plan (notes until the owner sends the README rules)

The README is written last, from real run data only.

Ideas to collect while building:
- Badges from `public/status.json` via shields.io endpoint: days running, last run, missed runs, jobs tracked.
- One architecture diagram (bronze → silver → history → gold → outputs), drawn as an animated SVG.
- Real numbers from runs: companies per provider, open jobs, US share, median days open, data-role salary bands.
- "How it stays polite and private": per-host limits, Lever 1 req/s, no description text, no personal data.
- Quality story: tests count, contracts, hold logic, incidents log.
- Links: dashboard (after Pages is on), dataset (Release + Hugging Face), dbt docs.

## Real figures so far (from `public/runs.jsonl` / `public/summary/`, first published run 2026-11-04)

- 1,500 companies tracked: Greenhouse 779, Ashby 669, Lever 52; all 1,500 boards fetched OK.
- 64,315 open postings; 83.7 % in the US; 67.8 % publish a salary (US roles: 76 %).
- Full daily run 9.4–9.7 min (ingest 8.3–8.7 min), against the 45 min budget.
- Median US salary across all roles $171.5k (p25 $130k, p75 $217.5k).
- Largest boards: SpaceX, Anduril, Databricks, OpenAI, Stripe.
- Incidents on day one (both fixed, logged): salary format `140.000.00`, separator-only location strings.
- Wait for ≥ 2 weeks of runs before quoting trends, days open or velocity.
