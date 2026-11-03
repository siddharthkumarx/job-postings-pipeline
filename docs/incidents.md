# Incidents

What broke, the impact, and the fix. Newest first. Each entry gives the date (UTC), the run or check id, the symptom, the root cause, the fix (commit) and any follow-up.

| Date | Run / check | Symptom | Root cause | Fix | Follow-up |
|---|---|---|---|---|---|
| 2026-11-03 | recon-cc-pages-001 | One Common Crawl index request returned HTTP 504; 16 retries in total over 12 requests | Shared Common Crawl index server under load | Polite client retried with backoff; no data lost | Kept index concurrency at 1 with 2 s spacing |
