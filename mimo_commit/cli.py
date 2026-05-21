"""Command-line interface for mimo-commit-genius."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from dotenv import load_dotenv

from . import __version__
from .changelog import generate_changelog, generate_release_notes
from .config import AppConfig
from .git_utils import (
    GitError,
    commits_between,
    is_git_repo,
    latest_tag,
    repo_root,
    run_git,
    staged_diff,
)
from .hook import install_hook, uninstall_hook
from .mimo_client import MiMoClient, MiMoError
from .release import plan_release
from .suggester import CommitSuggester

logger = logging.getLogger("mimo_commit")


def _setup_logging(quiet: bool, debug: bool) -> None:
    if debug:
        level = logging.DEBUG
    elif quiet:
        level = logging.WARNING
    else:
        level = logging.INFO
    logging.basicConfig(level=level, format="%(message)s")


def _load_config() -> AppConfig:
    load_dotenv(override=False)
    return AppConfig.from_env()


def _require_api_key(config: AppConfig) -> None:
    if not config.mimo.api_key:
        sys.stderr.write(
            "error: MIMO_API_KEY is not set.\n"
            "       Get a key at https://platform.xiaomimimo.com/ "
            "and add it to your .env file.\n"
        )
        sys.exit(2)


def _current_branch() -> str:
    try:
        return run_git(["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    except GitError:
        return ""


def _recent_subjects(limit: int = 5) -> list[str]:
    try:
        out = run_git(["log", f"-n{limit}", "--pretty=format:%s"])
    except GitError:
        return []
    return [s for s in out.splitlines() if s.strip()]


def cmd_suggest(args: argparse.Namespace) -> int:
    if not is_git_repo():
        sys.stderr.write("error: not inside a git repository\n")
        return 2

    diff = staged_diff()
    if not diff.strip():
        sys.stderr.write(
            "error: no staged changes — run `git add` first, "
            "or use --include-unstaged to also include working-tree changes.\n"
        )
        if args.include_unstaged:
            from .git_utils import working_diff

            diff = (diff + "\n" + working_diff()).strip()
            if not diff:
                return 2
        else:
            return 2

    config = _load_config()
    _require_api_key(config)

    suggester = CommitSuggester(MiMoClient(config.mimo))
    try:
        suggestion = suggester.suggest(
            diff,
            branch=_current_branch(),
            recent_subjects=_recent_subjects(),
            forced_type=args.type,
        )
    except (MiMoError, ValueError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    if args.json:
        payload = {
            "message": suggestion.message,
            "conventional": suggestion.is_valid,
            "type": suggestion.parsed.type if suggestion.parsed else None,
            "scope": suggestion.parsed.scope if suggestion.parsed else None,
            "subject": suggestion.parsed.subject if suggestion.parsed else None,
            "breaking": suggestion.parsed.breaking if suggestion.parsed else False,
            "usage": {
                "model": suggestion.completion.model,
                "total_tokens": suggestion.completion.total_tokens,
                "cost_usd": suggestion.completion.cost_usd,
                "latency_ms": round(suggestion.completion.latency_ms, 1),
            },
        }
        print(json.dumps(payload, indent=2))
    else:
        if not args.quiet:
            sys.stderr.write(
                f"# MiMo V2.5 — {suggestion.completion.total_tokens} tokens, "
                f"{suggestion.completion.latency_ms:.0f}ms, "
                f"~${suggestion.completion.cost_usd:.6f}\n\n"
            )
        print(suggestion.message)

    if args.write:
        Path(args.write).write_text(suggestion.message)
        if not args.quiet:
            sys.stderr.write(f"# wrote message to {args.write}\n")

    if args.apply:
        commit_msg_file = repo_root() / ".git" / "COMMIT_EDITMSG"
        commit_msg_file.parent.mkdir(parents=True, exist_ok=True)
        commit_msg_file.write_text(suggestion.message)
        sys.stderr.write(
            f"# message staged in {commit_msg_file}.\n"
            "# run: git commit -F .git/COMMIT_EDITMSG\n"
        )

    return 0


def _resolve_range(
    from_ref: str | None, to_ref: str
) -> tuple[str | None, str]:
    if from_ref:
        return from_ref, to_ref
    tag = latest_tag()
    return tag, to_ref


def cmd_changelog(args: argparse.Namespace) -> int:
    if not is_git_repo():
        sys.stderr.write("error: not inside a git repository\n")
        return 2

    from_ref, to_ref = _resolve_range(args.from_ref, args.to_ref)
    try:
        commits = commits_between(from_ref, to_ref)
    except GitError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    if not commits:
        sys.stderr.write("error: no commits in the requested range\n")
        return 1

    config = _load_config()
    client: MiMoClient | None = None
    if args.use_llm:
        _require_api_key(config)
        client = MiMoClient(config.mimo)

    try:
        result = generate_changelog(
            version=args.version,
            commits=commits,
            client=client,
            previous=from_ref or "",
            use_llm=args.use_llm,
        )
    except MiMoError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    if args.output:
        Path(args.output).write_text(result.markdown)
        sys.stderr.write(f"# wrote {len(commits)} commits to {args.output}\n")
    else:
        sys.stdout.write(result.markdown)

    if result.completion and not args.quiet:
        sys.stderr.write(
            f"# MiMo V2.5 — {result.completion.total_tokens} tokens, "
            f"~${result.completion.cost_usd:.6f}\n"
        )

    return 0


def cmd_release(args: argparse.Namespace) -> int:
    if not is_git_repo():
        sys.stderr.write("error: not inside a git repository\n")
        return 2

    config = _load_config()
    current_tag = args.from_tag or latest_tag()
    commits = commits_between(current_tag, "HEAD")

    plan = plan_release(
        commits=commits,
        current_tag=current_tag,
        config=config.release,
        initial_version=args.initial_version,
    )

    if args.json:
        print(
            json.dumps(
                {
                    "current": plan.current_version,
                    "next": plan.next_version,
                    "bump": plan.bump.value,
                    "reason": plan.reason,
                    "commits": len(commits),
                    "breaking": plan.breaking_subjects,
                    "features": plan.feature_subjects,
                    "fixes": plan.fix_subjects,
                },
                indent=2,
            )
        )
        return 0

    sys.stdout.write(f"Current version : {plan.current_version or '(none)'}\n")
    sys.stdout.write(f"Next version    : {plan.next_version}\n")
    sys.stdout.write(f"Bump            : {plan.bump.value} ({plan.reason})\n")
    sys.stdout.write(f"Commits         : {len(commits)}\n")
    if plan.breaking_subjects:
        sys.stdout.write("\nBreaking changes:\n")
        for s in plan.breaking_subjects:
            sys.stdout.write(f"  ! {s}\n")
    if plan.feature_subjects:
        sys.stdout.write("\nFeatures:\n")
        for s in plan.feature_subjects:
            sys.stdout.write(f"  + {s}\n")
    if plan.fix_subjects:
        sys.stdout.write("\nFixes:\n")
        for s in plan.fix_subjects:
            sys.stdout.write(f"  * {s}\n")

    if args.notes:
        _require_api_key(config)
        client = MiMoClient(config.mimo)
        completion = generate_release_notes(plan.next_version, commits, client)
        sys.stdout.write(f"\nRelease notes:\n{completion.content}\n")

    return 0


def cmd_install_hook(args: argparse.Namespace) -> int:
    if args.uninstall:
        removed = uninstall_hook()
        if removed:
            print("Removed mimo-commit prepare-commit-msg hook.")
            return 0
        sys.stderr.write("No mimo-commit hook to remove.\n")
        return 1

    try:
        result = install_hook(force=args.force, command=args.command)
    except RuntimeError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    print(f"{result.action}: {result.hook_path}")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    config = _load_config()
    sys.stdout.write(f"Model       : {config.mimo.model}\n")
    sys.stdout.write(f"API base    : {config.mimo.api_base}\n")
    sys.stdout.write(f"API key set : {'yes' if config.mimo.api_key else 'no'}\n")

    if args.ping:
        if not config.mimo.api_key:
            sys.stderr.write("error: MIMO_API_KEY not set\n")
            return 2
        client = MiMoClient(config.mimo)
        ok = client.health_check()
        sys.stdout.write(f"Health check: {'ok' if ok else 'failed'}\n")
        return 0 if ok else 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mimo-commit",
        description="AI-powered commit messages, changelogs and semver bumps powered by Xiaomi MiMo V2.5.",
    )
    parser.add_argument("--version", action="version", version=f"mimo-commit {__version__}")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress informational output")
    parser.add_argument("--debug", action="store_true", help="Verbose debug logging")

    sub = parser.add_subparsers(dest="command", required=True)

    # suggest
    s_suggest = sub.add_parser("suggest", help="Suggest a Conventional Commit message for staged diff")
    s_suggest.add_argument("--apply", action="store_true",
                           help="Write message to .git/COMMIT_EDITMSG so `git commit -F` picks it up")
    s_suggest.add_argument("--write", metavar="PATH",
                           help="Write the message to PATH (used by the prepare-commit-msg hook)")
    s_suggest.add_argument("--type", choices=[
        "feat", "fix", "docs", "style", "refactor", "perf", "test",
        "build", "ci", "chore", "revert",
    ], help="Force a specific Conventional Commit type")
    s_suggest.add_argument("--include-unstaged", action="store_true",
                           help="Also include unstaged working-tree changes")
    s_suggest.add_argument("--json", action="store_true",
                           help="Emit a JSON payload instead of plain text")
    s_suggest.set_defaults(func=cmd_suggest)

    # changelog
    s_changelog = sub.add_parser("changelog", help="Generate a markdown changelog")
    s_changelog.add_argument("version", help="Version to use as the heading (e.g. 1.2.0)")
    s_changelog.add_argument("--from", dest="from_ref", help="Starting ref (default: latest tag)")
    s_changelog.add_argument("--to", dest="to_ref", default="HEAD", help="Ending ref (default: HEAD)")
    s_changelog.add_argument("--output", "-o", help="Write to file instead of stdout")
    s_changelog.add_argument("--no-llm", dest="use_llm", action="store_false",
                             help="Render deterministically without calling MiMo")
    s_changelog.set_defaults(func=cmd_changelog, use_llm=True)

    # release
    s_release = sub.add_parser("release", help="Suggest the next semver version")
    s_release.add_argument("--from-tag", help="Override the previous tag (default: latest)")
    s_release.add_argument("--initial-version", default="0.1.0",
                           help="Version to propose when there is no prior tag")
    s_release.add_argument("--notes", action="store_true",
                           help="Also generate human-friendly release notes via MiMo")
    s_release.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    s_release.set_defaults(func=cmd_release)

    # install-hook
    s_hook = sub.add_parser("install-hook", help="Install the prepare-commit-msg git hook")
    s_hook.add_argument("--force", action="store_true",
                        help="Overwrite an existing hook even if it was not installed by mimo-commit")
    s_hook.add_argument("--uninstall", action="store_true",
                        help="Remove the hook instead of installing it")
    s_hook.add_argument("--command", default=os.environ.get("MIMO_COMMIT_COMMAND", "mimo-commit"),
                        help="CLI command invoked by the hook (default: mimo-commit)")
    s_hook.set_defaults(func=cmd_install_hook)

    # stats
    s_stats = sub.add_parser("stats", help="Show configuration / health")
    s_stats.add_argument("--ping", action="store_true",
                         help="Ping the MiMo /models endpoint to verify connectivity")
    s_stats.set_defaults(func=cmd_stats)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(quiet=args.quiet, debug=args.debug)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
