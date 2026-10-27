# Verification

Release: 0.2.0.0 · 2026-10-27

- 28 local tests passed, including four isolated Chromium browser acceptance cases.
- Two primary navigation actions, automatic project identity, newest-first ordering,
  edited-time labels, immediate file saving and proposal-first clipboard instructions checked.
- New rounds preserve manuscript identity, project and immutable parent versions;
  stale source versions and missing approval records are rejected. Duplicate requests
  are idempotent and unresolved comments retain their original anchors.
- A new round automatically opens; history is read-only. A stale tab's unsent changes
  survive approval and reload as a recovery copy. Failed file export never claims a
  successful Obsidian save. Retrying a comment does not duplicate it.
- Existing tests cover source checks, origin/token protection, file version pointers,
  persistence and protection of manually maintained preference notes.
- Optional inference only saves a proposal. The default workflow makes no model calls;
  no provider compatibility or external chat authentication is claimed.

Screenshots use synthetic prose and a synthetic folder path. Composition-event checks
do not replace manual input-method testing. Hosted CI is not enabled; the optional
configuration remains in [ci-example.yml](ci-example.yml).
