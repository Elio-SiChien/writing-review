# Security and privacy

This is a single-user local tool. Do not expose its port publicly. The service binds
to 127.0.0.1 and checks Host/Origin and a session token. These controls do not defend
against malicious software already running as your user.

By default, saving and handing off reviews performs no model calls or network inference.
Writable locations are the configured private data directory, configured review folder,
and the configured vault's writing-memory subtree. Keep these outside public repositories.
JSON, Markdown and offline HTML contain manuscript text and comments; treat them as private.
The repository screenshot uses synthetic material only.

Review contents are editorial data, never shell commands. Your chosen assistant is
responsible for respecting its own permissions when reading files or revising a manuscript.
An assistant without local access must be given the files explicitly.

The optional --auto-extract mode sends relevant prose, comments and matching preferences
to your configured Codex provider. It is off by default. Authentication stays with the
installed CLI; the tool does not read or export login tokens.

For security issues, provide a synthetic reproduction without private text or credentials.
Use GitHub private vulnerability reporting where available.

External chat approval is the assistant caller's responsibility. The round API requires
a note and an exact source version but cannot authenticate a chat transcript. Optional
background inference prepares proposals only and does not activate preferences.
