#!/usr/bin/env python3
#--------------------git_activity.py v0.4---------------------
# Scans all local git repos under ~/Projects and queries GitHub
# (including private repos) for commits in a specified date range,
# then displays a combined, deduplicated summary grouped by repo.
# Commits present on GitHub but absent locally are flagged as
# [GitHub only], indicating they originated on another machine.
# Requires: git, gh CLI (authenticated with 'repo' scope).
#
# Created Mon 09 Mar 2026 by JAU
# Modified Mon 09 Mar 2026 by JAU v0.2 - added argparse --start/--end
#                                         flags and 'today' shortcut;
#                                         interactive mode preserved
#                                         when no args given
# Modified Mon 09 Mar 2026 by JAU v0.3 - added --project/-p filter
#                                         (one or more repo names);
#                                         interactive prompt added
# Modified Tue 10 Mar 2026 by JAU v0.4 - added save-to-file prompt;
#                                         filename built from date range
#                                         and project filter inputs
#--------------------------------------------------------------

import argparse
import contextlib
import io
import subprocess
import json
import os
from datetime import datetime, date
from pathlib import Path


PROJECTS_ROOT = Path.home() / "Projects"


def ask_date(prompt, default=None):
    """Prompt for a date in YYYY-MM-DD format."""
    while True:
        hint = f" [{default}]" if default else ""
        raw = input(f"{prompt}{hint}: ").strip()
        if not raw and default:
            raw = default
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            print("  Invalid format. Use YYYY-MM-DD.")


def ask_projects(prompt):
    """Prompt for an optional comma-separated list of project names.
    Returns a list of names, or None (meaning all projects)."""
    raw = input(f"{prompt} [leave blank for all]: ").strip()
    if not raw:
        return None
    return [p.strip() for p in raw.replace(",", " ").split() if p.strip()]


def find_git_repos(root):
    """Return list of repo root paths under root."""
    result = subprocess.run(
        ["find", str(root), "-name", ".git", "-type", "d"],
        capture_output=True, text=True
    )
    repos = []
    for line in result.stdout.strip().splitlines():
        repo = Path(line).parent
        # Skip archives and nested GitHub clones to reduce noise
        if "Archive" not in str(repo) and "/GitHub/" not in str(repo):
            repos.append(repo)
    return sorted(repos)


def get_local_commits(repo_path, start, end):
    """Return list of commit dicts from a local repo within the date range."""
    after = f"{start}T00:00:00"
    before = f"{end}T23:59:59"
    result = subprocess.run(
        ["git", "-C", str(repo_path), "log",
         f"--after={after}", f"--before={before}",
         "--format=COMMIT|%H|%ai|%s%n%b%nENDCOMMIT"],
        capture_output=True, text=True
    )
    commits = []
    if not result.stdout.strip():
        return commits

    # Parse the output: each commit ends with ENDCOMMIT sentinel
    for block in result.stdout.split("ENDCOMMIT"):
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        if not lines or not lines[0].startswith("COMMIT|"):
            continue
        header = lines[0].split("|", 3)
        if len(header) < 4:
            continue
        _, sha, timestamp, subject = header
        body_lines = [
            l for l in lines[1:]
            if l.strip() and not l.startswith("Co-Authored-By")
        ]
        commits.append({
            "sha": sha[:7],
            "full_sha": sha,
            "time": timestamp,
            "subject": subject,
            "body": body_lines,
            "source": "local",
            "repo_name": repo_path.name,
            "repo_path": str(repo_path),
        })
    return commits


def get_github_commits(start, end):
    """Return dict of {sha: commit_dict} for all GitHub repos in date range."""
    # Fetch all owned repos including private
    result = subprocess.run(
        ["gh", "api", "/user/repos?per_page=100&visibility=all&affiliation=owner"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("  Warning: could not reach GitHub API")
        return {}

    repos = json.loads(result.stdout)
    all_commits = {}

    since = f"{start}T00:00:00Z"
    until = f"{end}T23:59:59Z"

    for repo in repos:
        full_name = repo["full_name"]
        result = subprocess.run(
            ["gh", "api",
             f"/repos/{full_name}/commits?since={since}&until={until}&per_page=50"],
            capture_output=True, text=True
        )
        if result.returncode != 0 or not result.stdout.strip():
            continue
        try:
            commits = json.loads(result.stdout)
        except json.JSONDecodeError:
            continue

        for c in commits:
            sha = c["sha"]
            message = c["commit"]["message"]
            lines = message.splitlines()
            subject = lines[0]
            body_lines = [l for l in lines[1:] if l.strip() and not l.startswith("Co-Authored-By")]
            timestamp = c["commit"]["author"]["date"]
            all_commits[sha] = {
                "sha": sha[:7],
                "full_sha": sha,
                "time": timestamp,
                "subject": subject,
                "body": body_lines,
                "source": "github",
                "repo_name": full_name.split("/")[1],
                "repo_path": f"github:{full_name}",
                "private": repo.get("private", False),
            }

    return all_commits


def merge_commits(local_by_repo, github_commits):
    """
    Combine local and GitHub commits. GitHub is authoritative for dedup.
    Returns dict: {repo_name: [commits]} sorted by time.
    """
    # Build a set of full SHAs seen locally
    local_shas = {}
    for repo, commits in local_by_repo.items():
        for c in commits:
            local_shas[c["full_sha"]] = repo

    merged = {}  # repo_name -> list of commits

    # Add all local commits
    for repo, commits in local_by_repo.items():
        merged.setdefault(repo, []).extend(commits)

    # Add GitHub commits not already seen locally
    for sha, c in github_commits.items():
        if sha not in local_shas:
            repo = c["repo_name"]
            c["source"] = "github-only"
            merged.setdefault(repo, []).append(c)

    # Sort each repo's commits by time ascending
    for repo in merged:
        merged[repo].sort(key=lambda x: x["time"])

    return merged


def format_time(timestamp_str):
    """Convert ISO timestamp to local HH:MM AM/PM."""
    # Handle both Z and offset formats
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(timestamp_str, fmt)
            # Convert to local time if timezone aware
            if dt.tzinfo:
                import time as _time
                offset = -_time.timezone / 3600
                from datetime import timezone, timedelta
                local_tz = timezone(timedelta(hours=offset))
                dt = dt.astimezone(local_tz)
            date_part = dt.strftime("%b %d").replace(" 0", "  ")
            time_part = dt.strftime("%I:%M %p").lstrip("0")
            return f"{date_part}  {time_part}"
        except ValueError:
            continue
    return timestamp_str[:16]


def print_report(merged, start, end, projects=None):
    """Print the activity report."""
    label = str(start) if start == end else f"{start} to {end}"
    if projects:
        proj_label = ", ".join(sorted(projects))
        label = f"{label}  |  projects: {proj_label}"
    print()
    print("=" * 60)
    print(f"  Git & GitHub Activity  —  {label}")
    print("=" * 60)

    if not merged:
        print("\n  No commits found for this date range.")
        return

    total = sum(len(v) for v in merged.values())

    for repo_name, commits in sorted(merged.items()):
        print(f"\n{'─' * 60}")
        print(f"  {repo_name}")
        print(f"{'─' * 60}")
        for c in commits:
            flag = " [GitHub only]" if c["source"] == "github-only" else ""
            print(f"\n  {format_time(c['time'])}  {c['sha']}  [{c['repo_name']}]  {c['subject']}{flag}")
            for line in c["body"]:
                if line.startswith("-"):
                    print(f"    {line}")
                else:
                    print(f"    - {line}")

    print()
    print("=" * 60)
    print(f"  {total} commit(s) across {len(merged)} repo(s)")
    print("=" * 60)
    print()


def build_report_filename(start, end, projects):
    """Build a descriptive filename from the report inputs."""
    today = date.today().strftime("%Y-%m-%d")
    start_str = start.strftime("%b-%d")
    end_str = end.strftime("%b-%d")
    date_part = start_str if start == end else f"{start_str}-to-{end_str}"
    if projects:
        proj_part = "-".join(sorted(projects))
        return f"REPORT_git-activity-{date_part}_{proj_part}-{today}.txt"
    return f"REPORT_git-activity-{date_part}-{today}.txt"


def parse_args():
    parser = argparse.ArgumentParser(
        prog="git_activity.py",
        description=(
            "Git & GitHub Activity Reporter\n"
            "──────────────────────────────────────────────────────────────\n"
            "Scans all local git repos under ~/Projects for commits within\n"
            "a date range, then cross-references GitHub (including private\n"
            "repos) using the gh CLI. Results are deduplicated by commit\n"
            "SHA so commits pushed from other machines (e.g. a Windows box)\n"
            "appear alongside local commits without duplication.\n\n"
            "Commits found on GitHub but absent locally are marked\n"
            "[GitHub only], indicating they originated on another machine.\n\n"
            "Requirements:\n"
            "  - git installed and available on PATH\n"
            "  - gh CLI installed and authenticated (gh auth login)\n"
            "  - GitHub token scope must include 'repo' for private repos\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  Run interactively (prompts for dates):\n"
            "    python3 git_activity.py\n\n"
            "  Show activity for a single day:\n"
            "    python3 git_activity.py --start 2026-03-09\n\n"
            "  Show activity for a date range:\n"
            "    python3 git_activity.py --start 2026-03-01 --end 2026-03-09\n\n"
            "  Show just today's activity (non-interactive):\n"
            "    python3 git_activity.py --start today\n\n"
            "  Show activity for a specific project:\n"
            "    python3 git_activity.py --start today --project sandbox\n\n"
            "  Show activity for multiple projects:\n"
            "    python3 git_activity.py --start 2026-03-01 -p sandbox my-app\n\n"
            "Output format:\n"
            "  Grouped by repo, sorted by commit time (ascending).\n"
            "  Each commit shows: time  short-SHA  subject\n"
            "                       - bullet points from commit body\n"
        ),
    )
    parser.add_argument(
        "--start",
        metavar="DATE",
        help="Start date in YYYY-MM-DD format, or 'today' (default: prompt)",
    )
    parser.add_argument(
        "--end",
        metavar="DATE",
        help="End date in YYYY-MM-DD format, or 'today' (default: same as --start)",
    )
    parser.add_argument(
        "--project", "-p",
        metavar="NAME",
        nargs="+",
        dest="projects",
        help="Filter to one or more repo names (e.g. --project sandbox my-app). "
             "Matches against both local repo directory names and GitHub repo names. "
             "Omit to report all repos.",
    )
    return parser.parse_args()


def resolve_date(value):
    """Parse a date string, accepting 'today' as a shortcut."""
    if value.lower() == "today":
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def main():
    args = parse_args()
    today = date.today().isoformat()

    # Resolve start date
    if args.start:
        try:
            start = resolve_date(args.start)
        except ValueError:
            print(f"Error: invalid start date '{args.start}'. Use YYYY-MM-DD or 'today'.")
            raise SystemExit(1)
    else:
        print()
        print("Git & GitHub Activity Reporter")
        print("─" * 32)
        start = ask_date("Start date (YYYY-MM-DD)", default=today)

    # Resolve end date
    if args.end:
        try:
            end = resolve_date(args.end)
        except ValueError:
            print(f"Error: invalid end date '{args.end}'. Use YYYY-MM-DD or 'today'.")
            raise SystemExit(1)
    elif args.start:
        end = start  # non-interactive: default end = start
    else:
        end = ask_date("End date   (YYYY-MM-DD)", default=str(start))

    # Resolve project filter
    if args.projects:
        projects = set(args.projects)
    elif not args.start:
        # interactive mode — only prompt when no CLI args were given
        projects_input = ask_projects("Project(s) to report (space or comma-separated)")
        projects = set(projects_input) if projects_input else None
    else:
        projects = None

    print()

    print("Scanning local repos...", end="", flush=True)
    repos = find_git_repos(PROJECTS_ROOT)
    if projects:
        repos = [r for r in repos if r.name in projects]
    local_by_repo = {}
    for repo in repos:
        commits = get_local_commits(repo, start, end)
        if commits:
            local_by_repo[repo.name] = commits
    print(f" {sum(len(v) for v in local_by_repo.values())} local commits found.")

    print("Querying GitHub (incl. private repos)...", end="", flush=True)
    github_commits = get_github_commits(start, end)
    if projects:
        github_commits = {sha: c for sha, c in github_commits.items()
                          if c["repo_name"] in projects}
    print(f" {len(github_commits)} GitHub commits found.")

    merged = merge_commits(local_by_repo, github_commits)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        print_report(merged, start, end, projects)
    output = buf.getvalue()
    print(output, end="")

    save = input("Save report to file? [y/N]: ").strip().lower()
    if save == "y":
        filename = build_report_filename(start, end, projects)
        with open(filename, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"  Report saved to {filename}")


if __name__ == "__main__":
    main()
