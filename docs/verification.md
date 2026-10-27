# Initial release verification

Release: 0.1.0.0 · 2026-10-27

- 13 local tests passed, including Chromium browser acceptance.
- Source and JSON validation, optimistic-version protection, retry persistence,
  preference scope, duplicate provenance and manual-edit protection passed.
- Browser acceptance covered overlapping CSS highlights, refresh, editing and undo,
  composition events, malformed imports and standalone offline export.
- A private legacy v1 fixture was checked outside this repository. Its contents and
  screenshots are not included here. The shipped screenshot uses synthetic text.
- A Python wheel was built successfully, including web assets.
- The source tree was reviewed for private documents, user paths and credentials.

The full authenticated inference path could not be completed on the release machine:
its configured Codex model was rejected by the account. The failure was surfaced and
raw annotations remained saved. Successful inference-to-vault behavior was tested with
a structured synthetic extractor. That test does not establish successful access to
every model or account. A compatible configured CLI model is required for live extraction.

Real input-method behavior and very large manuscripts still need broader user testing.
No GitHub CI workflow is active in the initial release. An optional configuration is
provided in [ci-example.yml](ci-example.yml); the local results above are not hosted CI results.
