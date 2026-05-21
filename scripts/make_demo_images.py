"""Generate demo screenshots and a banner for the README.

Renders the *actual* CLI output (with a stubbed MiMo client so we never
have to hit the network) as terminal-style PNGs.

Outputs are written to ``docs/``.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import textwrap
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Output capture helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"
DOCS.mkdir(exist_ok=True)


def _make_temp_git_repo(tmp: Path) -> Path:
    repo = tmp / "demo-repo"
    repo.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Demo",
        "GIT_AUTHOR_EMAIL": "demo@example.com",
        "GIT_COMMITTER_NAME": "Demo",
        "GIT_COMMITTER_EMAIL": "demo@example.com",
        "GIT_AUTHOR_DATE": "2026-05-21T12:00:00Z",
        "GIT_COMMITTER_DATE": "2026-05-21T12:00:00Z",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }

    def git(*args, msg=None):
        subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            env=env,
            capture_output=True,
            text=True,
            input=msg,
        )

    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, env=env, capture_output=True)
    (repo / "README.md").write_text("hello\n")
    git("add", "README.md")
    git("commit", "-m", "chore: initial commit")
    git("tag", "v0.1.0")

    (repo / "auth.py").write_text(
        "def login(token):\n"
        "    return token.rotate()\n"
    )
    git("add", "auth.py")
    git("commit", "-m", "feat(auth): rotate session tokens on login")

    (repo / "auth.py").write_text(
        "def login(token):\n"
        "    if token is None:\n"
        "        return None\n"
        "    return token.rotate()\n"
    )
    git("add", "auth.py")
    git("commit", "-m", "fix(auth): guard against missing token")

    return repo


def _run_suggest_demo(repo: Path) -> str:
    """Stage a diff and run `mimo-commit suggest` with a stubbed client."""
    # stage some new changes
    (repo / "middleware.py").write_text(
        "def auth_middleware(request):\n"
        "    if not request.user:\n"
        "        return _reject(request)\n"
        "    return _continue(request)\n"
    )
    subprocess.run(
        ["git", "-C", str(repo), "add", "middleware.py"],
        check=True,
        env={
            **os.environ,
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
        },
        capture_output=True,
    )

    os.chdir(repo)
    os.environ["MIMO_API_KEY"] = "demo-key"

    from mimo_commit import cli
    from mimo_commit.mimo_client import CompletionResult

    class _Stub:
        def __init__(self, *a, **kw):
            self.total_requests = 0

        def complete(self, *a, **kw):
            return CompletionResult(
                content=(
                    "feat(auth): add auth middleware to reject unauthenticated requests\n"
                    "\n"
                    "Adds `auth_middleware` that short-circuits the request pipeline when\n"
                    "the incoming request has no `user` attached, returning a 401 via the\n"
                    "existing `_reject` helper. Authenticated requests are passed through\n"
                    "to `_continue` unchanged."
                ),
                model="mimo-v2.5-instruct",
                prompt_tokens=287,
                completion_tokens=82,
                total_tokens=369,
                latency_ms=612.4,
                cost_usd=0.0000369,
            )

        def health_check(self):
            return True

    cli.MiMoClient = _Stub  # type: ignore[assignment]

    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        cli.main(["suggest"])
    return f"$ mimo-commit suggest\n{err.getvalue()}{out.getvalue()}"


def _run_changelog_demo(repo: Path) -> str:
    os.chdir(repo)
    from mimo_commit import cli

    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        cli.main(["changelog", "0.2.0", "--no-llm"])
    return f"$ mimo-commit changelog 0.2.0 --no-llm\n{out.getvalue()}"


def _run_release_demo(repo: Path) -> str:
    os.chdir(repo)
    from mimo_commit import cli

    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        cli.main(["release", "--json"])
    payload = json.loads(out.getvalue())
    pretty = json.dumps(payload, indent=2)
    return f"$ mimo-commit release --json\n{pretty}"


# ---------------------------------------------------------------------------
# Image rendering
# ---------------------------------------------------------------------------


@dataclass
class Theme:
    bg: tuple[int, int, int] = (24, 26, 33)
    title_bar: tuple[int, int, int] = (40, 44, 52)
    fg: tuple[int, int, int] = (230, 233, 240)
    muted: tuple[int, int, int] = (130, 138, 154)
    accent: tuple[int, int, int] = (244, 165, 96)  # MiMo-ish orange
    green: tuple[int, int, int] = (146, 209, 132)
    blue: tuple[int, int, int] = (110, 184, 245)
    purple: tuple[int, int, int] = (197, 139, 232)
    red: tuple[int, int, int] = (224, 108, 117)
    yellow: tuple[int, int, int] = (240, 196, 110)


THEME = Theme()
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"


def _measure(font: ImageFont.FreeTypeFont, text: str) -> tuple[int, int]:
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _colorize_token(token: str) -> tuple[int, int, int]:
    if token.startswith("#"):
        return THEME.muted
    if token.startswith("$"):
        return THEME.green
    if token in {"feat", "fix", "refactor", "docs", "test", "chore", "perf", "build", "ci", "style"}:
        return THEME.accent
    if token.endswith(":"):
        return THEME.purple
    if token.startswith("v0.") or token.startswith("v1.") or token.startswith("v2."):
        return THEME.blue
    return THEME.fg


def _render_terminal(
    lines: list[str],
    out_path: Path,
    title: str = "mimo-commit",
    font_size: int = 18,
) -> None:
    font = ImageFont.truetype(FONT_PATH, font_size)
    font_bold = ImageFont.truetype(FONT_BOLD, font_size)

    char_w, char_h = _measure(font, "M")
    line_h = int(char_h * 1.55)

    width = max(800, max((_measure(font, line)[0] for line in lines), default=0) + 80)
    title_h = 38
    padding_top = 24
    padding_bottom = 24
    height = title_h + padding_top + line_h * len(lines) + padding_bottom

    img = Image.new("RGB", (width, height), THEME.bg)
    draw = ImageDraw.Draw(img)

    # Title bar
    draw.rectangle([(0, 0), (width, title_h)], fill=THEME.title_bar)
    # Traffic lights
    for i, color in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        draw.ellipse([(16 + i * 22, 12), (30 + i * 22, 26)], fill=color)
    # Title text
    title_w, _ = _measure(font, title)
    draw.text(((width - title_w) // 2, 10), title, font=font, fill=THEME.muted)

    # Body
    y = title_h + padding_top
    for line in lines:
        x = 24
        stripped = line.rstrip()

        if stripped.startswith("$ "):
            # Prompt
            draw.text((x, y), "$", font=font_bold, fill=THEME.green)
            draw.text((x + char_w * 2, y), stripped[2:], font=font_bold, fill=THEME.fg)
        elif stripped.startswith("#"):
            draw.text((x, y), stripped, font=font, fill=THEME.muted)
        elif stripped.startswith("==") or stripped.startswith("--"):
            draw.text((x, y), stripped, font=font_bold, fill=THEME.accent)
        elif "BREAKING" in stripped:
            draw.text((x, y), stripped, font=font_bold, fill=THEME.red)
        elif stripped.startswith("### "):
            draw.text((x, y), stripped, font=font_bold, fill=THEME.blue)
        elif stripped.startswith("## "):
            draw.text((x, y), stripped, font=font_bold, fill=THEME.yellow)
        elif stripped.startswith("- ") or stripped.startswith("+ ") or stripped.startswith("* ") or stripped.startswith("! "):
            color = {"-": THEME.muted, "+": THEME.green, "*": THEME.blue, "!": THEME.red}[stripped[0]]
            draw.text((x, y), stripped[:2], font=font_bold, fill=color)
            draw.text((x + char_w * 2, y), stripped[2:], font=font, fill=THEME.fg)
        else:
            # token-coloring for the first token if it looks like a CC type
            first_space = stripped.find(" ")
            if first_space > 0:
                first_token = stripped[:first_space]
            else:
                first_token = stripped
            # Type:scope pattern
            if ":" in first_token and "(" in first_token:
                colon = first_token.index(":")
                type_part = first_token[:colon]
                color = _colorize_token(type_part.split("(", 1)[0])
                draw.text((x, y), type_part + ":", font=font_bold, fill=color)
                draw.text((x + char_w * (colon + 1), y), stripped[colon + 1:], font=font, fill=THEME.fg)
            elif ":" in first_token and first_token.split(":")[0] in {
                "feat", "fix", "refactor", "docs", "test", "chore", "perf", "build", "ci", "style", "revert",
            }:
                colon = first_token.index(":")
                color = _colorize_token(first_token[:colon])
                draw.text((x, y), first_token[:colon] + ":", font=font_bold, fill=color)
                draw.text((x + char_w * (colon + 1), y), stripped[colon + 1:], font=font, fill=THEME.fg)
            else:
                draw.text((x, y), stripped, font=font, fill=THEME.fg)

        y += line_h

    img.save(out_path)


def _render_banner() -> None:
    width, height = 1280, 400
    img = Image.new("RGB", (width, height), THEME.bg)
    draw = ImageDraw.Draw(img)

    # Accent bar
    draw.rectangle([(0, 0), (width, 6)], fill=THEME.accent)

    title_font = ImageFont.truetype(FONT_BOLD, 80)
    sub_font = ImageFont.truetype(FONT_PATH, 28)
    small_font = ImageFont.truetype(FONT_PATH, 22)

    title = "MiMo Commit Genius"
    sub = "AI-powered Conventional Commits, changelogs and semver bumps."
    powered = "powered by Xiaomi MiMo V2.5  ·  ~$0.00005/commit"

    tw, th = _measure(title_font, title)
    draw.text(((width - tw) // 2, 80), title, font=title_font, fill=THEME.fg)
    sw, sh = _measure(sub_font, sub)
    draw.text(((width - sw) // 2, 80 + th + 24), sub, font=sub_font, fill=THEME.muted)
    pw, ph = _measure(small_font, powered)
    draw.text(((width - pw) // 2, 80 + th + 24 + sh + 20), powered, font=small_font, fill=THEME.accent)

    # Decorative terminal snippet on the right? Skip — keep clean.
    img.save(DOCS / "banner.png")


def main() -> None:
    sys.path.insert(0, str(REPO_ROOT))

    _render_banner()

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_temp_git_repo(Path(tmp))
        suggest_text = _run_suggest_demo(repo)
        changelog_text = _run_changelog_demo(repo)
        release_text = _run_release_demo(repo)

    def _split(text: str) -> list[str]:
        out: list[str] = []
        for line in text.rstrip().splitlines():
            if not line:
                out.append("")
            else:
                # wrap very long lines
                for wrapped in textwrap.wrap(line, width=100, drop_whitespace=False, replace_whitespace=False) or [""]:
                    out.append(wrapped)
        return out

    _render_terminal(_split(suggest_text), DOCS / "demo-suggest.png", title="mimo-commit suggest")
    _render_terminal(_split(changelog_text), DOCS / "demo-changelog.png", title="mimo-commit changelog")
    _render_terminal(_split(release_text), DOCS / "demo-release.png", title="mimo-commit release")
    print("wrote:", *sorted(p.name for p in DOCS.glob("*.png")))


if __name__ == "__main__":
    main()
