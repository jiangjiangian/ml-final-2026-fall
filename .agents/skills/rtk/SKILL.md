---
name: rtk
description: Reduce routine terminal output with the installed RTK CLI; preserve original evidence for ML and source audits.
---

# RTK command output

This is a project skill wrapping the official [RTK](https://github.com/rtk-ai/rtk)
Codex integration, not an upstream standalone SKILL.md. Installed release: v1.1.0;
source commit: `753a3b0e939f2e4490fc24e3a1984010f40a103c`.

## Use

- Check `rtk --version`; if missing, run `bash tools/setup_rtk.sh` from the repo.
- In this Codex Cloud session use explicit prefixes: `rtk git status`,
  `rtk git log -5`, `rtk git diff --stat`, `rtk rg pattern path`.
- For routine test summaries use `rtk test <python-path> -m unittest ...`;
  for lint use `rtk ruff check ...` with the intended environment on PATH.
- Unittest failure details may be omitted from the summary. Follow its
  `rtk recall <hash>` link for the complete saved output before diagnosing.
- Prefer several related commands in one tool call. RTK does not replace batching.
- Preserve exit codes; a compact success message alone is not verification.
- If output is missing, inconsistent, or insufficient for diagnosis, read the
  original saved log or use `rtk bypass <command>` / the original command.

## Keep original evidence

Use unfiltered commands when reading a required document to EOF, checking exact
source bytes/hashes, CSV rows, feature availability, official scores, receipts,
or security-sensitive command output. Do not use RTK summaries as evidence that
all source rows or failure details were examined. Never run credential-bearing
operations through RTK tracking/recovery. Keep private raw logs outside Git.

## Integration and scope

`rtk init --codex` installed the official `RTK.md`, `AGENTS.md` reference and
`.codex/hooks.json`. Native Codex CLI can load this Bash hook after restart and
its normal project trust flow. This Cloud interface uses `exec_command`, so do
not claim automatic interception here; use the explicit commands above.

`rtk gain` shows estimated savings in command output. It does not measure total
conversation tokens or billed cost, and does not compress existing chat history.
No RTK API proxy or model-provider configuration is needed for command filters.

Reinstall: `bash tools/setup_rtk.sh`. Remove the native project integration:
`rtk init --codex --uninstall`; this does not remove the binary or this skill.

Official reference: [Codex hook](https://github.com/rtk-ai/rtk/blob/v1.1.0/hooks/codex/README.md),
[savings explanation](https://github.com/rtk-ai/rtk/blob/v1.1.0/docs/guide/resources/savings-explained.md).
