# Incidents

What broke, the impact, and the fix. Newest first. Each entry gives the date (UTC), the run or check id, the symptom, the root cause, the fix (commit) and any follow-up.

| Date | Run / check | Symptom | Root cause | Fix | Follow-up |
|---|---|---|---|---|---|
| 2026-11-03 | recon-harvest-001 | Harvest took 92 min; 42 Common Crawl index requests still failed with HTTP 504 after retries (335 retries in total), so some crawl/pattern pages were skipped (see the log in `summary.json`) | Common Crawl index server overloaded | Polite client kept retrying with backoff; harvest finished with 9,904 candidates from the pages that loaded plus the YC directory | Added progress output and a time budget to the harvester; Lever coverage from the index is thin, so YC guesses matter most there |
| 2026-11-03 | recon-cc-pages-001 | One Common Crawl index request returned HTTP 504; 16 retries in total over 12 requests | Shared Common Crawl index server under load | Polite client retried with backoff; no data lost | Kept index concurrency at 1 with 2 s spacing |
