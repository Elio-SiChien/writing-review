# Writing Review · 写作复利

**Annotate locally. Save plain files. Let your AI read them when needed.**

A local review page for writers and researchers. Comments and edits save as JSON and
readable Markdown in a fixed folder, with version history. No model, login or external
network access is needed to save or hand off a review. Writing preferences can be maintained
in Obsidian by the assistant you already use, when you ask it to process the files.

[中文说明](README.zh-CN.md) · [Architecture](docs/architecture.md) · [Verification](docs/verification.md) · [Security](SECURITY.md) · [MIT](LICENSE)

[Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md) · [Sample document](examples/sample.md)

![Synthetic review example](docs/demo.png)

## Start

Python 3.10 or later; no third-party runtime dependencies.

```sh
git clone https://github.com/Elio-SiChien/writing-review.git
cd writing-review
python -X utf8 -m writing_review
```

Windows users can double-click `start.cmd`. The page opens at `http://127.0.0.1:8765`.
Import TXT, Markdown as plain text, or legacy review JSON. Select text and click
**添加批注**; without a selection, annotate the paragraph. Annotated text turns yellow.
Overlapping comments keep independent anchors. You can edit the prose directly.
Missing or ambiguous anchors ask for relinking instead of highlighting another passage.

## The fixed folder is the handoff

Choose your own location:

```sh
python -X utf8 -m writing_review --review-dir "/path/to/review-inbox"
```

Or connect your Obsidian vault:

```sh
python -X utf8 -m writing_review --vault "/path/to/vault"
```

With a vault, the default is `写作复利/批注收件箱/` inside it. Otherwise it is `reviews/`
inside the private data directory. The page displays the exact path. Previously saved
reviews are exported on startup, and each changed save updates the handoff files.

```text
review-inbox/
  AI读取说明.md
  document-ID/
    CURRENT.json
    latest.json
    latest.md
    history/
      v000001.json
      v000001.md
```

Click **复制给AI的指令**, then paste the instruction into an assistant that can read
your local files. It tells the assistant which document to read, to follow `CURRENT.json`,
revise against the comments, and preserve scoped writing preferences in Obsidian.
For an assistant without local access, attach the corresponding JSON or Markdown.
Saving a file does not mean the assistant has read it or learned from it.

Versioned JSON and Markdown are written before `CURRENT.json` is updated. This pointer
identifies a consistent pair; `latest` files are convenient reading copies. If writing
the folder fails, the review remains in SQLite and the page reports a pending file
export. It retries locally, or click **重新保存交接文件**. No model call is involved.

## Writing memory

Keep reusable preferences in the vault's `写作复利/` notes. Before writing, read the
quick reference and matching scene/project rules; after revision, record explicit
preferences with comment IDs, scope and examples. Inferences stay candidates. Do not
silently replace human notes or promote project wording into general preferences.

The page's **本次写作偏好** button retrieves existing active scoped notes. A CLI brief
is also available without calling a model:

```sh
python -X utf8 -m writing_review --profile academic introduction project:your-project
```

Other assistants need their own supported guidance entry or an explicit reading request;
this tool does not claim that every product automatically loads your vault.

## Optional advanced extraction

Background model extraction is **off by default**. Existing pending model jobs do not run.
The older Codex adapter is retained only for users who deliberately opt in:

```sh
python -X utf8 -m writing_review --vault "/path/to/vault" --auto-extract
```

This optional mode requires an authenticated compatible Codex CLI. It inherits the
configured model unless you choose `--codex-model YOUR_MODEL`. Model access errors have
no effect on the plain-file handoff. In this mode, relevant comments, prose and matching
preferences are sent to your configured Codex provider. It is not offline training.
Restart the service to change its startup settings.

## Recovery, tests and limits

Private data defaults to `%LOCALAPPDATA%/WritingReview` on Windows or
`~/.local/share/WritingReview` elsewhere; override with `--data-dir`. Keep it, the
configured review folder and your vault outside public repositories. The service binds
only to 127.0.0.1 and checks Host/Origin and a session token. It does not store login secrets.

Browser recovery preserves unsent changes. A stale tab cannot overwrite a newer saved
version; export its conflict recovery copy and reconcile manually. JSON export and
**下载离线页** remain available. A pure offline HTML page cannot automatically write
to the configured folder: export its JSON instead.

```sh
python -X utf8 -m unittest discover -s tests -v
```

Optional browser tests need `pip install playwright` and `playwright install chromium`.
Set `WR_BROWSER` to use an installed Chromium browser. Hosted CI is not enabled;
[ci-example.yml](docs/ci-example.yml) is an optional configuration. See
[CONTRIBUTING.md](CONTRIBUTING.md) and the [synthetic example](examples/sample.md).

The initial interface is Chinese. This is a single-user plain-text tool, without
DOCX/PDF import, rich Markdown rendering, automatic manuscript revision or scientific
fact checking. Use a current browser supporting CSS Custom Highlights. Back up your files.
