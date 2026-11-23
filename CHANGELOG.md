# Changelog

## 0.5.0 · 2026-11-23

- Open a PDF by dropping it anywhere on the page or picking it: the local service converts it with PyMuPDF (optional dependency) into paragraphs labelled with page numbers, reading two-column layouts in order, dropping running headers, footers, page numbers and review line numbers, and joining words hyphenated at line breaks. The original PDF is kept with the document's assets. Scanned PDFs get a clear message; a missing PyMuPDF gets an install hint.
- Stop snapshot bloat: adding or editing a comment no longer stores a whole-document version; SQLite keeps a text version only when the body text changes or a round is created. The save protocol (expectedVersion, X-Review-Token) and `/api/rounds` are unchanged.
- Vault export now keeps three files per document: CURRENT.json (pointer with the embedded record), ROUND.json and latest.md. No more `history/` files in the vault.
- New export folders get readable names such as `20261119_论文2_讨论_第1轮`; existing folders keep their names and paths. Overwrite protection now refuses foreign folders, rollbacks and same-version content changes.
- The reading guide in the vault is upgraded to describe the new layout; the previous guide is archived in `说明归档/`.
- Cleanup keeps the final version of legacy export folders that revision notes cite and trims only their intermediate snapshots.
- Add `tools/cleanup_redundancy.py`: a dry run by default that reports old snapshots, duplicate snapshots, legacy `latest.json` copies and orphan folders with sizes; `--execute` backs up, archives to a verified zip outside the vault, then removes.
- Earlier v0.5 steps: desktop shortcut without a console window, `tools/push_latex.py` for pushing LaTeX sections, and figure cards.

## Unreleased · 2026-10-29

- Check running-service data and handoff locations before reusing an instance.
- Report actual data paths and manuscript counts at startup, preserving active jobs on compatible relaunches.
- Add synthetic startup regression coverage and document Windows voice typing.

## 0.2.0.2 · 2026-10-27

- Offer only Academic writing, Grant writing and General scenes.
- Default new manuscripts to General and map old scenes without rewriting history.
- Preserve section-specific preference conditions and prevent cross-scene leakage.


## 0.2.0.1 · 2026-10-27

- Upgrade known legacy reading instructions with an archived original.
- Preserve custom instructions and supply the current approval policy separately.
- Refresh parent round metadata immediately when a new draft is created.


## 0.2.0.0 · 2026-10-27

- Reduce the main page to opening a document and requesting an AI proposal.
- Save comments immediately and show newest comments first.
- Add stable manuscript identity, approved-source checks and linked review rounds.
- Preserve historical rounds and recover unsent feedback when a new draft appears.
- Keep optional model inference proposal-only until the user approves in chat.


## 0.1.0.2 · 2026-10-27

- Save every review as JSON and readable Markdown in a fixed folder with version history.
- Display the folder and provide a copyable instruction for an assistant to read it.
- Disable background model extraction by default; keep it as an explicit advanced opt-in.
- Backfill old reviews and retry file export without losing database records.


## 0.1.0.1 · 2026-10-27

- Preserve existing human note bodies when extending provenance in later rounds.
- Add regression coverage for adopting and updating manually maintained preferences.
- Clarify restart behavior, documentation links and optional CI setup.

## 0.1.0.0 · 2026-10-27

- Import plain text, Markdown as plain editable text, and legacy review JSON.
- Annotate selections or paragraphs using non-mutating CSS highlights.
- Persist reviews and revisions locally with conflict protection and recovery.
- Extract scoped preferences using the locally authenticated Codex CLI.
- Sync evidence-backed preferences to Obsidian; retain inferences as candidates.
- Export JSON and a standalone offline review page.
