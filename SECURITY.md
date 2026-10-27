# Security and privacy

This tool is intended for one user on a trusted local machine. Do not expose its
port through a reverse proxy, tunnel or public interface. Host/Origin and API-token
checks reduce cross-origin attacks; they do not defend against malicious software
already running as your local user.

The companion writes only to its configured private data directory and the configured
vault's `写作复利` subtree. Keep these outside public repositories. Review JSON and
offline HTML contain manuscript text and comments. Treat exported files as private.
Screenshots in this repository use synthetic material only.

Optional extraction sends relevant writing material to the Codex provider configured
on your machine. Check that provider's data policy before using confidential work.
Authentication remains with the installed CLI; this project does not read or export
your login token. Review contents are data, never shell arguments or executable code.

For a security issue, avoid including private manuscripts or credentials in a public
issue. Use GitHub's private vulnerability reporting if enabled, or provide a minimal
synthetic reproduction without sensitive details.
