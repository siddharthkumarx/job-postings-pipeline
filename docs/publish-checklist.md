# Publish checklist

The public repository is a **fresh repo, `siddharthkumarx/job-postings-pipeline`, with a clean `main`**. This private repo is not renamed: it keeps its full development history, and the public repo starts from one clean snapshot of it.

## 1. Prepare the snapshot (in a scratch copy of this repo)

1. Export the current tree without history:
   ```bash
   git archive --format=tar HEAD | (mkdir ../job-postings-pipeline && tar -x -C ../job-postings-pipeline)
   cd ../job-postings-pipeline
   ```
2. Drop the private files: `rm -rf docs/private/`.
3. Rename `docs/maintainers.md` to `docs/maintainers.md`, change its first heading to "# Maintainers' guide", and update the links that name it (`docs/build-progress.md`). Then run `python3 scripts/check_links.py`.
4. Decide on the live-check results: keep `checks/results/` (they show how the 1,500 companies were found and verified, and `docs/sources.md` links to them) or delete the bulky `site/` and `screenshots/` folders inside them.
5. Check `templates/readme.yml`: `public_repo: siddharthkumarx/job-postings-pipeline`, `branch: main`, `dashboard_url`, `hf_dataset`, `contact_email`. Then run `uv run jobpipe readme` and `python3 scripts/check_links.py`.
6. Run every check: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`.

## 2. Create the public repo

1. Create an empty public repository `job-postings-pipeline` (no README, no licence; they are already in the snapshot).
2. In the snapshot folder:
   ```bash
   git init -b main
   git config user.name "Siddharth Kumar"
   git config user.email 273157498+siddharthkumarx@users.noreply.github.com
   git config core.hooksPath .githooks
   git add -A
   git commit -m "Initial public release: daily US tech job postings pipeline"
   git remote add origin https://github.com/siddharthkumarx/job-postings-pipeline.git
   git push -u origin main
   ```

## 3. Move the state (so history continues instead of restarting)

The bronze snapshots, the warehouse snapshot and the monthly dataset live in this private repo's Releases. Copy them to the public repo **before its first scheduled run**; otherwise the first run starts history from zero.

```bash
for tag in $(gh release list -R siddharthkumarx/job-postings-pipeline-wip --json tagName -q '.[].tagName'); do
  mkdir -p "rel/$tag" && gh release download "$tag" -R siddharthkumarx/job-postings-pipeline-wip -D "rel/$tag"
  case "$tag" in dataset-*) flags="--latest" ;; *) flags="--prerelease --latest=false" ;; esac
  gh release create "$tag" -R siddharthkumarx/job-postings-pipeline --title "$tag" --notes "Pipeline data: $tag" $flags rel/$tag/*
done
```

## 4. Settings on the public repo

Apply `docs/repo-settings.md`:
- About text, website and topics; social preview `assets/social-preview.png`.
- Pages: Source "GitHub Actions"; repository variable `PAGES_ENABLED=true`.
- Secret `HF_TOKEN` (Hugging Face write token) for the dataset upload.
- Actions: allow workflows to write (`contents: write`, `issues: write` are requested per workflow).

## 5. Switch over

1. In the public repo, run the `daily` workflow once by hand (Actions → daily → Run workflow) and check it publishes. The README badges and the "Download the data" link work from then on.
2. In this private repo, disable the `daily` workflow (Actions → daily → ⋯ → Disable workflow) so the two repos never both collect on the same day.
3. Open the README on a phone and on a desktop, and open the live dashboard link.
