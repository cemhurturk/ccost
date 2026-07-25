# `bin/ccost` launcher — design

Date: 2026-07-25

## Purpose

Let `ccost` be invoked as a plain command from any directory, without an
install step, a virtualenv, or a `cd` into the repo. `python3 -m ccost` only
works from the repo root; a symlinked launcher removes that constraint.

## Location

`bin/ccost`, committed and executable.

The obvious name — a `ccost` file at the repo root — is unavailable: the root
already holds the `ccost/` package directory. Putting the launcher under
`bin/` keeps the clean command name for the symlink:

    ln -s /path/to/ccost/bin/ccost /usr/local/bin/ccost

## Behaviour

**Path resolution.** The script resolves its own real path with a
`while [ -L ]` loop rather than `readlink -f`; BSD readlink has no `-f`, so the
coreutils idiom is not portable to macOS, which is the primary platform. The
repo root is the parent of the resolved script's directory.

**No `cd`.** The launcher sets `PYTHONPATH` to the repo root and execs
`python3 -m ccost "$@"` from wherever the caller stood. Changing directory
would silently re-root every relative path the caller typed —
`ccost --root tests/fixtures/dupes` must mean *their* `tests/fixtures/dupes`.

**`exec`.** Replaces the shell process, so exit codes and signals propagate
untouched. argparse's exit 2 on a bad flag reaches the caller as 2.

**Interpreter.** `$CCOST_PYTHON` if set, else `python3`. Both the presence and
the 3.9+ version of the interpreter are checked up front, so a wrong
interpreter fails with a clear message instead of an ImportError from inside
the package. Consistent with the zero-dependency constraint: no venv, nothing
installed.

**`usage()`.** Prints the wrapper's own notes — invocation, the symlink install
line, `CCOST_PYTHON`, a few examples. On `-h`/`--help` that block prints and
then execution falls through to the Python CLI, so the authoritative flag list
comes from argparse and cannot drift out of sync. The same block prints to
stderr ahead of an interpreter error.

**Passthrough.** Arguments are forwarded as `"$@"` verbatim, so
`--project=-Users-...` and every other flag behave exactly as documented.

## Out of scope

No install subcommand, no config seeding, no test or verify subcommands. Those
are separate concerns and none of them is needed to run the tool.

## Verification

Bash, so no unittest coverage. Verified by hand:

| Case | Result |
|---|---|
| Run from repo root against a fixture | correct total |
| Run through a symlink from an unrelated cwd | correct total |
| Relative `--root` from another cwd | resolves against caller's cwd, not repo root |
| `--help` | wrapper notes followed by the argparse list |
| Bad flag | exit 2, propagated from argparse |
| `CCOST_PYTHON` missing / not 3.9+ | usage plus a specific error, exit 1 |
| Real scan (`--since 2026-07`) | matches `python3 -m ccost` |

The Python suite is untouched by this change.
