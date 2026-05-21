# MiMo Commit Genius

**AI-powered Conventional Commit messages, changelogs, and semantic version bumps — powered by Xiaomi MiMo V2.5.**

Stop bikepainting commit messages. `mimo-commit` reads your staged diff, asks the ultra-cheap Xiaomi MiMo V2.5 model what changed, and gives you a clean Conventional Commit message — automatically, on every commit, via a `prepare-commit-msg` git hook. Plus first-class commands for generating release changelogs and suggesting the next semver version from your commit history.

![Python](https://img.shields.io/badge/python-3.10+-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![MiMo](https://img.shields.io/badge/powered%20by-MiMo%20V2.5-orange)
![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-yellow)

---

## Why?

Good commit messages compound. They let you `git log` and actually understand history, drive automated semver bumps, and produce changelogs without manual cleanup. The problem: nobody enjoys writing them. Existing tooling either forces interactive prompts (Commitizen) or uses LLMs that cost real money per commit (GPT-4 ~$0.05/commit, Claude ~$0.03/commit). At 50 commits/day across a team that's $750+/month *just for commit messages*.

| Approach              | Cost / commit  | Effort         | Conventional? |
| --------------------- | -------------- | -------------- | ------------- |
| Hand-written          | $0             | High, lazy in practice | Inconsistent |
| Commitizen prompts    | $0             | Medium, interactive | Yes |
| GPT-4 / Claude wrap   | ~$0.03–0.10    | None           | Yes |
| **MiMo Commit Genius**| **~$0.00005**  | **None — git hook** | **Yes** |

MiMo V2.5 is **600–2000x cheaper** than frontier models while being explicitly tuned for code-shaped inputs. At 50 commits/day, monthly spend goes from $750 → about $0.07.

---

## Features

- `mimo-commit suggest` — Conventional Commit message for the current staged diff
- `mimo-commit install-hook` — installs a `prepare-commit-msg` hook so `git commit` auto-fills the message
- `mimo-commit changelog 1.2.0` — markdown changelog from commits since the last tag (LLM-polished or deterministic)
- `mimo-commit release` — suggest the next semver version from commits since the last tag
- `mimo-commit stats --ping` — verify MiMo API connectivity and your configuration
- Strict Conventional Commits v1.0.0 parser/formatter (no `Any`, no regex soup leaking into business logic)
- Honors per-repo overrides via `.env` (model, temperature, bump types, breaking-change keywords)
- Zero hard dependencies beyond `requests` + `python-dotenv`
- 50+ tests including an isolated git fixture that exercises the CLI end-to-end without ever calling the real API

---

## Architecture

```
git add .                                      ┌──────────────────────┐
git commit              ┌──────────────────▶│ prepare-commit-msg   │
     │                  │                      │ (installed hook)     │
     │                  │                      └────────┬─────────────┘
     ▼                  │                               │ shells out
┌─────────────┐         │                               ▼
│ staged diff │─────────┘                  ┌──────────────────────────────┐
└─────────────┘                            │ mimo-commit suggest          │
                                           │  ┌─────────────────────────┐ │
                                           │  │ git_utils.staged_diff() │ │
                                           │  ├─────────────────────────┤ │
                                           │  │ suggester (truncate +   │ │
                                           │  │ prompt assembly)        │ │
                                           │  ├─────────────────────────┤ │
                                           │  │ MiMoClient.complete()   │─┼──▶ MiMo V2.5 API
                                           │  ├─────────────────────────┤ │
                                           │  │ conventional.parse()    │ │
                                           │  └─────────────────────────┘ │
                                           └──────────┬───────────────────┘
                                                      ▼
                                               .git/COMMIT_EDITMSG
                                               (auto-filled message)
```

For changelogs and release planning, the flow is similar but reads `git log <prev-tag>..HEAD` and groups commits with `conventional.parse()` before either rendering deterministic markdown or asking MiMo to polish it.

---

## Install

```bash
pip install mimo-commit-genius          # via PyPI (when published)
# or from source:
git clone https://github.com/rasop498/mimo-commit-genius.git
cd mimo-commit-genius
pip install -e .
```

Then configure your API key:

```bash
cp .env.example .env
$EDITOR .env       # set MIMO_API_KEY from https://platform.xiaomimimo.com/
```

Verify it works:

```bash
mimo-commit stats --ping
```

---

## Usage

### 1. Suggest a commit message manually

```bash
$ git add src/auth.py
$ mimo-commit suggest
# MiMo V2.5 — 312 tokens, 740ms, ~$0.000031

feat(auth): rotate session tokens on login

Rotates the bearer token issued to a session every time the user
re-authenticates, reducing the blast radius of token leaks.
```

Flags:

| Flag                  | Effect |
| --------------------- | ------ |
| `--apply`             | Write the message to `.git/COMMIT_EDITMSG`; finish with `git commit -F .git/COMMIT_EDITMSG` |
| `--write PATH`        | Write to an arbitrary path (used by the git hook) |
| `--type feat`         | Force a specific Conventional Commit type |
| `--include-unstaged`  | Also include unstaged working-tree changes |
| `--json`              | Emit a structured JSON payload (handy for editor integrations) |

### 2. Install the git hook (recommended)

```bash
$ cd your-repo
$ mimo-commit install-hook
installed: /your-repo/.git/hooks/prepare-commit-msg
```

From now on, every `git commit` will pre-fill the editor with a Conventional Commit suggestion. If you already wrote a message via `-m`, the hook gets out of the way.

Uninstall just as easily:

```bash
mimo-commit install-hook --uninstall
```

### 3. Generate a changelog

```bash
$ mimo-commit changelog 1.2.0 --from v1.1.0 -o CHANGELOG.md
# wrote 27 commits to CHANGELOG.md
# MiMo V2.5 — 1842 tokens, ~$0.000184
```

If you don't want to spend a request, `--no-llm` renders deterministic markdown straight from your commit history:

```bash
mimo-commit changelog 1.2.0 --no-llm
```

### 4. Suggest the next semver version

```bash
$ mimo-commit release
Current version : v1.2.0
Next version    : v1.3.0
Bump            : minor (feat)
Commits         : 12

Features:
  + add OAuth device flow
  + expose /healthz endpoint

Fixes:
  * handle empty token in middleware
```

JSON-friendly for CI:

```bash
$ mimo-commit release --json | jq .next
"v1.3.0"
```

Combine with `--notes` to also generate a 3–5 sentence summary suitable for a GitHub release body.

---

## Configuration

All settings can be set via environment variables or a `.env` file at the repo root.

| Variable                   | Default                                          | Purpose |
| -------------------------- | ------------------------------------------------ | ------- |
| `MIMO_API_KEY`             | _(required)_                                     | API key from <https://platform.xiaomimimo.com/> |
| `MIMO_API_BASE`            | `https://platform.xiaomimimo.com/api/v1`         | Override for staging / proxies |
| `MIMO_MODEL`               | `mimo-v2.5-instruct`                             | Any MiMo chat-completions model |
| `MIMO_TEMPERATURE`         | `0.2`                                            | Lower = more deterministic |
| `MIMO_MAX_TOKENS`          | `512`                                            | Per request |
| `MIMO_MINOR_BUMP_TYPES`    | `feat`                                           | Comma-separated Conventional types that trigger a minor bump |
| `MIMO_PATCH_BUMP_TYPES`    | `fix,perf,revert,refactor`                       | Types that trigger a patch bump |
| `MIMO_MAJOR_BUMP_KEYWORDS` | `BREAKING CHANGE,BREAKING-CHANGE`                | Footer keywords that force a major bump |

---

## Editor integration

`mimo-commit suggest --json` returns a stable shape that's easy to wire into VS Code tasks, JetBrains external tools, Vim mappings, etc.:

```json
{
  "message": "fix(api): handle null user in middleware",
  "conventional": true,
  "type": "fix",
  "scope": "api",
  "subject": "handle null user in middleware",
  "breaking": false,
  "usage": {
    "model": "mimo-v2.5-instruct",
    "total_tokens": 287,
    "cost_usd": 0.0000287,
    "latency_ms": 612.3
  }
}
```

---

## Development

```bash
git clone https://github.com/rasop498/mimo-commit-genius.git
cd mimo-commit-genius
pip install -e ".[dev]"

pytest -v                  # 50+ tests, none hit the real API
ruff check mimo_commit tests
```

The test suite uses a `git_repo` fixture (in `tests/conftest.py`) that creates a real but disposable git repository per test, with global git config stubbed out via `GIT_CONFIG_GLOBAL=/dev/null` so it works on any contributor's machine.

---

## Roadmap

- [ ] Pre-commit framework wrapper (so it works alongside `pre-commit` without conflicts)
- [ ] `mimo-commit fixup` — generate a `fixup!` message that targets the right ancestor commit
- [ ] First-class GitHub Actions workflow to publish releases + changelog on `tag push`
- [ ] Streamed responses so very large diffs feel instant
- [ ] JetBrains plugin that calls `--json`

---

## License

MIT — see [LICENSE](LICENSE).

---

## Acknowledgements

Built on top of [Xiaomi MiMo V2.5](https://mimo.xiaomi.com/) and the [Conventional Commits v1.0.0](https://www.conventionalcommits.org/en/v1.0.0/) spec.
