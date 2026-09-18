# Contributing Guide

## Team -- AgroOptimize, Team 52 (Amrita Vishwa Vidyapeetham)

| Member | GitHub | Area |
|---|---|---|
| VVS Vamsi | VamsiVarada-3632 | NSGA-II core, API, CLI demo, frontend (upcoming) |
| Vennela Harshini | Harshini3105 | Fuzzy engine, data pipeline, TOPSIS, economic calibration |
| Garudammagari Sreenithya | nithya16o1 | Test suite, architecture/API docs, fuzzy-vs-non-fuzzy study |
| Gaddam Jahnavi | jahnavi-25-cmd | Literature survey, problem statement, results write-up, paper |

Guide: Dr. G. Jeyakumar

## Branch strategy

- `main` -- production-ready
- `develop` -- integration branch
- `feature/<name>-<area>` -- one branch per person for their own work

## Current state (as of 2026-08-12)

The backend is built and committed to `main`/`develop`: data pipeline, fuzzy
engine, NSGA-II optimizer, TOPSIS ranking, FastAPI, CLI demo, and an initial
test suite (`tests/test_pipeline.py`). All of those commits are mine (Vamsi)
-- I wrote/assembled this part, so the log says so.

## How to commit your own work

Commit from your own machine using your own GitHub account, so the history
actually reflects who wrote what:

    git clone <repo-url>
    cd agrooptimize-backend
    git checkout feature/<your-branch>
    git config user.name "Your Name"
    git config user.email "you@example.com"
    # make your changes
    git add <files>
    git commit -m "type(scope): description"
    git push origin feature/<your-branch>

No `--author` flag needed -- when you commit from your own account, you're
already the author.

## Commit message format

    feat(module): ...
    fix(module): ...
    test(module): ...
    docs: ...
    data: ...
    chore: ...

## Real remaining work

- Vamsi -- frontend (React dashboard consuming the API)
- Harshini -- calibrate economic constants (real TNAU fertilizer prices,
  MGNREGA labour rates, sourced carbon factors) in app/config.py; expand the
  fuzzy rule base with region-specific rules
- Sreenithya -- expand the test suite beyond test_pipeline.py (data/fuzzy/API
  unit tests); write docs/architecture.md and docs/api_docs.md; run a
  fuzzy-vs-non-fuzzy comparison for the paper
- Jahnavi -- literature survey (see note below), problem statement, dataset
  documentation, per-district results write-up, guide review status doc

### Note on the literature survey

This needs to cite papers that actually exist and that have actually been
read. It wasn't pre-written here because sources can't be verified without
doing real research -- ask and I'll help search for and verify real,
relevant papers rather than inventing citations.

## Once you're ready to push to GitHub

Run from your own machine (this needs your GitHub auth, which this sandbox
doesn't have):

    git remote add origin <your-repo-url>
    git push -u origin main
    git push origin develop
    git push origin feature/vamsi-nsga2-core
    git push origin feature/harshini-fuzzy-data
    git push origin feature/sreenithya-testing-docs
    git push origin feature/jahnavi-research-docs

    gh repo invite <owner>/<repo> Harshini3105
    gh repo invite <owner>/<repo> nithya16o1
    gh repo invite <owner>/<repo> jahnavi-25-cmd

    gh issue create --title "Build frontend -- React dashboard" --assignee VamsiVarada-3632 --label enhancement
    gh issue create --title "Calibrate economic constants with real TN market rates" --assignee Harshini3105 --label research
    gh issue create --title "Expand fuzzy rule base" --assignee Harshini3105 --label enhancement
    gh issue create --title "Expand test suite" --assignee nithya16o1 --label research
    gh issue create --title "Fuzzy vs non-fuzzy comparison study" --assignee nithya16o1 --label research
    gh issue create --title "Literature survey + results write-up" --assignee jahnavi-25-cmd --label research
