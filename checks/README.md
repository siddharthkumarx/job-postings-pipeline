# Live checks

The development sandbox does not call the job boards. To run a live check, edit
`checks/request.yml` (new `id`, a whitelisted `command`, `params`) and push. The
`checks` workflow runs it on GitHub Actions and commits the outputs to
`checks/results/<id>/` on the same branch (`summary.json` always, plus
command-specific files). Commands: see `COMMANDS` in `src/jobpipe/checks.py`.
