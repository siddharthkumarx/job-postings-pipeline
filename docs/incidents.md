# Incidents

What broke, the impact, and the fix, newest first. Every entry has the same fields. The two "In plain words" lines are what the README shows, so keep them short and free of jargon. The other fields are for engineers.

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
