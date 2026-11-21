# Incidents

What broke, the impact, and the fix, newest first. Every entry has the same fields. The two "In plain words" lines are what the README shows, so keep them short and free of jargon. The other fields are for engineers.

### 2026-11-21 · The count of closed roles was always 0

- **Run / check:** daily runs 2026-11-04 to 2026-11-21 (`public/runs.jsonl`, `closed_postings`)
- **In plain words:** Every daily run reported 0 roles closed, even though about 1,000 roles close each day. The open-role count was right; only the closed count was wrong, in the README and on the dashboard.
- **Fix in plain words:** A role is still counted as closed once it is missing two days in a row, and it is now counted on that second day. The next daily run shows the real number.
- **Symptom:** `closed_postings = 0` in every run from 2026-11-04 to 2026-11-21 while open postings fell and about 1,000 postings arrived per run (20 Nov open 64,204; 21 Nov open 64,062 with 879 new, so 1,021 net closings). The README said "0 roles closed" and the dashboard's newest new-vs-closed bar was always 0; older bars were shifted one run early.
- **Root cause:** `int_posting_lifecycle` sets `closed_on` to the first successful board fetch after `last_seen`, but only once a second successful fetch also misses the posting. A closing is therefore known one run after its `closed_on`, and every "closed in this run" count (`guards.collect`, `publish.changes_today`, the dashboard flows) filtered on `closed_on = <run date>`, which can never match on the newest run.
- **Fix:** New column `close_confirmed_on` (the second missed successful fetch) in `int_posting_lifecycle`, `gold.fct_job_postings` and `mart_data_roles`, the contracts and the data dictionary. All per-run counts use it; the lifecycle marts (days open, weekly velocity, days-open bands) keep `closed_on`. A flow check (open today = open in the previous run + new + first fetch + reopened − closed) runs every day and writes a note to `runs.jsonl` when it does not balance. `runs.jsonl` also gets `reopened_postings`, `first_fetch_postings` and `open_previous`.
- **Follow-up:** Tests in `tests/test_pipeline.py` (written first; they failed with `[0, 0, 0, 0, 0, 0]` closings) check on the synthetic runs that each closing is counted once, in the run that confirms it, in `runs.jsonl`, the README changes and the dashboard; that a failed board fetch never confirms a closing; that a returning posting is reopened and not counted again; and that the flow check balances. Re-run on the 21 Nov warehouse snapshot: 1,053 closings confirmed on 21 Nov (1,093 on 20 Nov, 1,196 on 19 Nov), and the flow check balances on the last five run dates. Earlier lines of `runs.jsonl` stay as written (append-only, D-015).

### 2026-11-04 · A saved copy of the database was missing a table

- **Run / check:** site-screenshots-001
- **In plain words:** The nightly saved copy of the database was taken a moment too early, so it could miss the newest changes.
- **Fix in plain words:** Every copy is now completed and checked before it is saved. A bad copy is never used; the data is rebuilt from the raw daily files instead.
- **Symptom:** The screenshot check restored the `state` snapshot and found `gold.dim_company` missing.
- **Root cause:** `push_warehouse` gzipped the DuckDB file while dbt's in-process connection still held recent writes in the write-ahead log, so the snapshot could lack tables or incremental rows. The next incremental run would have built on it, losing history, without noticing.
- **Fix:** `FORCE CHECKPOINT` before every snapshot. `validate_warehouse` checks that the required tables exist and that every loaded bronze date is in silver, both before upload (it refuses to upload) and after restore (it falls back to a rebuild from bronze). Runs now note when they rebuilt.
- **Follow-up:** `test_pipeline` asserts that only day one rebuilds, and it fails without the checkpoint. The bad snapshot was replaced by a re-run.

### 2026-11-04 · Locations made only of dashes stopped the data model

- **Run / check:** daily run 41747584811
- **In plain words:** A few job ads gave their location as just a dash. The step that reads locations did not expect that, so the run was held back and nothing wrong was published.
- **Fix in plain words:** Empty locations are now handled. The same day's data was re-processed and published.
- **Symptom:** The run was held. Ingest was fine (1,500/1,500 boards OK, 64,314 postings, 8.2 min), but the dbt model `int_locations` errored and 75 nodes were skipped.
- **Root cause:** Some location strings contain only separators (e.g. `-`). `split_locations` returned an empty list and `parse_location` indexed `[0]`.
- **Fix:** Guard the empty case. Hold reasons now keep the end of a dbt traceback.
- **Follow-up:** Added a test for separator-only locations. Bronze for 2026-11-04 was stored, and the run was repeated.

### 2026-11-04 · An odd salary format stopped the first run

- **Run / check:** daily run 41747241373 (first real run)
- **In plain words:** One job ad wrote its salary as "140.000.00". The salary reader did not expect that format and stopped the whole first run.
- **Fix in plain words:** It now reads that format. One odd ad can only skip itself and can never stop a run again. A test guards it.
- **Symptom:** The run failed after 58 s; `runs.jsonl` status `failed`.
- **Root cause:** A Greenhouse description wrote a salary as `140.000.00`. `extract._num` raised `ValueError`, and the exception propagated out of the board task and the whole ingest.
- **Fix:** The number parser handles `140.000.00` / `140.000,00` / `120,000.00`. Salary extraction can no longer raise. A parsing error now marks one posting invalid or one board `error`, never the run.
- **Follow-up:** Regression tests in `tests/test_extract.py` and `tests/test_ingest.py`; the daily run was re-run.

### 2026-11-03 · The public web archive used to find companies was overloaded

- **Run / check:** recon-harvest-001
- **In plain words:** The public web archive used to find company job boards was overloaded, and many of its pages timed out.
- **Fix in plain words:** The collector waited and retried politely. It still found 9,904 candidate boards, and 1,500 companies were kept after checks.
- **Symptom:** The harvest took 92 min, and 42 Common Crawl index requests still failed with HTTP 504 after retries (335 retries in total). Some crawl/pattern pages were skipped (see the log in `summary.json`).
- **Root cause:** The Common Crawl index server was overloaded.
- **Fix:** The polite client kept retrying with backoff. The harvest finished with 9,904 candidates from the pages that loaded plus the YC directory.
- **Follow-up:** Added progress output and a time budget to the harvester. Lever coverage from the index is thin, so YC guesses matter most there.

### 2026-11-03 · One slow answer from the web archive

- **Run / check:** recon-cc-pages-001
- **In plain words:** One request to the public web archive timed out once.
- **Fix in plain words:** It was retried after a pause; nothing was lost.
- **Symptom:** One Common Crawl index request returned HTTP 504; 16 retries in total over 12 requests.
- **Root cause:** The shared Common Crawl index server was under load.
- **Fix:** The polite client retried with backoff; no data was lost.
- **Follow-up:** Kept index concurrency at 1 with 2 s spacing.
