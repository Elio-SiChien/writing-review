# Changelog

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
