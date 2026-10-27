# Writing Review · 写作复利

**Annotate locally. Keep the feedback. Reuse your writing preferences.**

A local-first review page for writers and researchers. Highlight a passage, leave a
comment, and keep both the original and revised text. An optional local Codex worker
turns feedback into scoped, evidence-backed Obsidian notes for the next writing task.

[中文说明](README.zh-CN.md) · [Architecture](docs/architecture.md) · [Security](SECURITY.md) · MIT

![Synthetic review example](docs/demo.png)

## Start in a minute

Requires Python 3.10 or later. The service has no third-party runtime dependencies.

```sh
git clone https://github.com/Elio-SiChien/writing-review.git
cd writing-review
python -X utf8 -m writing_review
```

Windows users can double-click `start.cmd`. A browser opens at
`http://127.0.0.1:8765`. Import `.txt`, `.md`, or existing review `.json` files.
Markdown is editable plain text, rather than a rendered preview.

- Select text and click **添加批注**; without a selection, annotate the paragraph.
- Annotated text turns yellow. Overlapping comments keep independent anchors.
- Edit the prose directly. An ambiguous or missing anchor asks for relinking.
- Reviews save to a private local SQLite database. JSON export is your portable backup.
- **下载离线页** creates a standalone HTML review page with browser recovery and JSON export.

The interface currently uses Chinese labels. English interface translation is planned.

## Optional Obsidian memory

Install the official Codex CLI and authenticate using `codex login` first.

```sh
python -X utf8 -m writing_review --vault "/path/to/your/vault"
```

The vault setting is kept in the private data directory, outside this repository.
After approximately 15 seconds without another saved change, the worker invokes the
already authenticated CLI with `--sandbox read-only`, `--ephemeral` and a structured
output schema. It inherits your Codex model configuration. If that model is not
available to your account, reviews remain saved and the job retries; set an explicitly
chosen supported model with `--codex-model YOUR_MODEL`. There is no silent model fallback.

The local service writes the resulting notes under `写作复利/`:

| Content | Purpose |
| --- | --- |
| `风格速查.md` / `自动索引.md` | Entry point and current preference index |
| `偏好条目/` | Principle, scope, status, source IDs and before/after evidence |
| `批注与修订记录/` | Versioned review snapshots |
| `候选与冲突/` | Inferences and protected manual edits |

Explicit preferences apply only in their scope. Inferred preferences remain candidates.
Importing the same feedback again does not increase its confirmation count. Existing
human-maintained notes are adopted without replacing their prose; later manual changes
produce a conflict note. This is retrievable writing memory, not model training.

**Your comments, selected prose, revised prose and matching preference notes are sent
to your configured Codex provider during extraction.** The web service itself is local;
model inference is not offline. Without the CLI or vault, review and export still work.

## Use preferences in another project

```sh
python -X utf8 -m writing_review --profile academic introduction project:your-project
```

Or click **本次写作偏好** and give the generated text to your writing assistant.
An assistant can be instructed through its own guidance file to read
`写作复利/风格速查.md` before writing. Other products do not automatically load it.
Project-specific terminology is included only when the corresponding project ID is selected.

## Data and recovery

Defaults: `%LOCALAPPDATA%/WritingReview` on Windows, `~/.local/share/WritingReview`
elsewhere. Override with `--data-dir`. Keep this directory outside a public repository.
The service binds only to `127.0.0.1`, validates Host/Origin, and requires a session token
for private APIs. It does not install an extension, expose a public server or store login secrets.

Browser recovery retains unsent changes. If another tab changes the saved version,
the stale tab cannot overwrite it; export its conflict recovery copy and reconcile manually.
SQLite retains prior versions. Back up the private data directory and your vault regularly.
Offline pages use browser storage; clearing it removes that convenience copy, so export JSON.

## Tests

```sh
python -X utf8 -m unittest discover -s tests -v
```

Browser acceptance is optional:

```sh
pip install playwright
playwright install chromium
python -X utf8 -m unittest discover -s tests -v
```

Set `WR_BROWSER` to use an installed Chromium-based browser. `WR_SCREENSHOT` optionally
saves a screenshot of the synthetic fixture. Tests cover overlapping highlights, edits
and undo, composition events, offline export, source mismatch, persistence, origin checks,
preference scope, duplicate feedback, retry and protection of manual edits. Automated IME
events do not replace a manual test with a real input method.

## Limits

The initial release supports plain paragraph text and a single local user. It does not
render complex Markdown, import DOCX/PDF, automatically revise your manuscript, or validate
scientific claims. Very large reviews may exceed model context. Model extraction remains
fallible; consult the recorded sources, candidates and conflicts. Browser APIs require a
current Chrome/Edge or another browser supporting CSS Custom Highlights.

Built with [CSS Custom Highlights](https://developer.mozilla.org/en-US/docs/Web/API/CSS_Custom_Highlight_API)
and [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode).

Optional GitHub Actions configuration is provided in `docs/ci-example.yml`. Copy it to
`.github/workflows/test.yml` using an account authorized to manage workflows.
