# Contributing

Use synthetic documents in tests, issues and screenshots. Never commit personal
reviews, Obsidian notes, absolute user paths, credentials or model output from real work.

Run `python -X utf8 -m unittest discover -s tests -v`. Add browser acceptance when
changing selection, highlight, import or recovery behavior. Browser tests need Playwright
and a Chromium installation. Keep runtime dependencies minimal, preserve legacy JSON,
and ensure persistence succeeds before inference is attempted.

Use `codex/` for Codex-created feature branches. Describe behavior, validation and
known limitations in a pull request. Do not silently promote inferred preferences,
change scope, overwrite manual notes or replace a user's selected model.
