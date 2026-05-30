# QA Summary

Repository hygiene review completed before initial GitHub commit.

- Source code lives under `app/`.
- Tests live under `tests/`.
- Local research packs live under `data/research/`.
- Carousel patterns live under `data/patterns/`.
- `README.md`, `requirements.txt`, `.env.example`, and `.gitignore` are safe to commit.
- `.env` exists locally and is ignored.
- Generated posts, discovery reports, QA reports, verification outputs, logs, caches, virtual environments, and generated media are ignored.
- Generated outputs include local media and post artifacts; they should stay out of GitHub.
- No likely literal API key values were found in the files selected for commit. Placeholder environment variable names are present in docs and `.env.example`.

Recommended repository visibility: private.
