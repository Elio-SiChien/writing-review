# Verification

Release: 0.1.0.2 · 2026-10-27

- 18 local tests passed, including Chromium browser acceptance.
- The default save path wrote readable JSON and Markdown without calling a model.
- Versioned file pairs, CURRENT pointer, duplicate saves, existing-review backfill,
  export failure with database preservation, and successful retry were checked.
- Existing tests cover highlights, editing/undo, refresh, offline export, recovery
  conflicts, source mismatch, origin checks and protection of human preference notes.
- Optional extractor behavior is tested using structured synthetic output. Actual
  provider compatibility is not required for the default file-based workflow.

Only synthetic content is included in the screenshot. Any displayed folder is a
synthetic demonstration path, not a private review directory.

No hosted CI workflow is enabled; see [ci-example.yml](ci-example.yml). Browser
composition events do not replace manual testing with a real input method.
