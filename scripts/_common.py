#!/usr/bin/env python3
"""Helpers shared by the build scripts.

Named with a leading underscore because it is not a build script itself — every
other file in scripts/ is meant to be run directly.
"""

from __future__ import annotations

import html
import re


def esc(s) -> str:
    """HTML-escape, collapsing whitespace. Used for every value that comes out
    of a YAML file and into generated markup."""
    return html.escape(" ".join(str(s or "").split()), quote=False)


def warn_if_preview_running(warnings: list) -> None:
    """Append a warning if a Quarto preview server is running.

    The preview server renders into the same _site/ and .quarto/ as a manual
    `quarto render`. When both run, the preview can re-render a page from its
    own cached view and overwrite correct output — which is how five excluded
    conference abstracts reappeared on the publications page after they had been
    verified as gone. The generated .md was right and the HTML was a build
    behind, which is very easy to miss.

    Getting this detection right took three attempts, so the reasoning is
    recorded here:

    * `pgrep -f "quarto preview"` is unusable. It matches any command line
      containing that phrase — including a `grep` for it — and these scripts are
      often run from a shell whose argv holds the whole compound command.
    * Requiring the project path in the command line fails: the preview is
      started with the project as its working directory, not as an argument.
    * Skipping anything starting with a shell fails too, because `quarto` IS a
      bash script — the real process is `bash /path/to/quarto preview ...`.

    So: match "quarto" and "preview" in the command line, and exclude only
    inline shell commands (`bash -c ...`) and the inspection tools. The check
    does not verify which project the preview belongs to; over-warning is much
    cheaper than the silent overwrite it exists to prevent.
    """
    try:
        import os
        import subprocess
        out = subprocess.run(["ps", "-Ao", "pid=,command="],
                             capture_output=True, text=True, timeout=5)
        mine = {str(os.getpid()), str(os.getppid())}
        inline_shell = re.compile(r"^\S*(?:ba|z|d)?sh\s+-\w*c\b")
        tools = re.compile(r"^\S*(?:grep|pgrep|ps|rg|awk|sed)\b")
        for line in out.stdout.splitlines():
            pid, _, cmd = line.strip().partition(" ")
            if pid in mine or not cmd:
                continue
            if inline_shell.match(cmd) or tools.match(cmd):
                continue
            low = cmd.lower()
            if "quarto" in low and "preview" in low:
                warnings.append(
                    f"A `quarto preview` server is running (pid {pid}). It "
                    f"writes to the same _site/ as `quarto render` and can "
                    f"overwrite this build's output. Stop it, run "
                    f"`quarto render`, then restart it.")
                return
    except Exception:
        pass   # a missing or unusual `ps` must never break the build


def touch_pages(root, warnings: list, *names: str) -> None:
    """Bump the mtime of pages that {{< include >}} a generated file.

    Quarto's incremental render does not treat an include as a dependency, so
    after a script rewrites its .md the page including it is considered up to
    date and keeps its old content — with a NEWER timestamp than the file it is
    stale against, which makes it easy to miss.
    """
    for name in names:
        path = root / name
        if path.exists():
            path.touch()
            warnings.append(f"touched {name} so Quarto re-renders it")
