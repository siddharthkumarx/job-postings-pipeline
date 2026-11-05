# Publish checklist

The repository was published **in place** on 2026-11-05: switched to public, renamed to `siddharthkumarx/job-postings-pipeline`, default branch renamed to `main`, then cleaned with one history rewrite. This page records what was done and what is still open.

## Done (2026-11-05)

1. History rewritten once with `git filter-repo`, which:
   - removed `docs/private/` from every commit;
   - moved the maintainers' guide to `docs/maintainers.md` and updated every mention of it;
   - dropped commit signatures;
   - removed trailers other than `Signed-off-by` and any "Generated with" footer from messages.

   Authors, dates and the daily data commits were kept.
2. `main` force-pushed once, with a lease on the previous head.
3. Every public URL points at the new name: `templates/readme.yml` (README badges and links), `CITATION.cff` and the dataset card. Then the README was re-rendered. `python3 scripts/check_links.py` passes.

## Still to do (repository settings, by hand)

Apply `docs/repo-settings.md`:

1. **About:** description, website and topics.
2. **Social preview:** upload `assets/social-preview.png`.
3. **Pages:** Source "GitHub Actions", then the repository variable `PAGES_ENABLED=true`.
4. **Secret `HF_TOKEN`**, for the Hugging Face dataset upload (the run skips it cleanly while it is missing).

## Release tags

The three release tags (`bronze-2026-11`, `dataset-2026-11`, `state`) were created by the pipeline and still point at commits from before the rewrite, so those old commits stay reachable through the tags. Moving each tag to its rewritten commit means a force update of the tag refs; do it only with the owner's go-ahead:

```bash
git push --force origin bronze-2026-11 dataset-2026-11 state
```

New monthly tags are created on the rewritten history automatically.
