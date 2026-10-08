"""ChangeGuard CLI tool to import and inspect a GitHub Pull Request directly."""
import argparse
import json
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.github.importer import GitHubPRImporter
from backend.app.core.exceptions import ChangeGuardException


def main():
    parser = argparse.ArgumentParser(
        description="ChangeGuard CLI - Fetch and inspect GitHub Pull Request metadata and diff."
    )
    parser.add_argument("--owner", required=True, help="GitHub repository owner (e.g. 'psf')")
    parser.add_argument("--repo", required=True, help="GitHub repository name (e.g. 'requests')")
    parser.add_argument("--pr", type=int, required=True, help="Pull Request number (e.g. 100)")
    parser.add_argument("--json", action="store_true", help="Output full raw JSON response")

    args = parser.parse_args()

    print(f"[*] ChangeGuard: Fetching PR #{args.pr} from '{args.owner}/{args.repo}'...")

    try:
        importer = GitHubPRImporter()
        details = importer.import_pull_request(owner=args.owner, repo=args.repo, pr_number=args.pr)

        if args.json:
            print(json.dumps(details.model_dump(), indent=2))
            return

        print("\n" + "=" * 60)
        print(f"PULL REQUEST DETAILS: #{details.pr_number} - {details.title}")
        print("=" * 60)
        print(f"Repository : {details.owner}/{details.repo}")
        print(f"Author     : {details.author}")
        print(f"State      : {details.state}")
        print(f"Created At : {details.created_at}")
        print(f"Branches   : {details.base_branch} <- {details.head_branch}")
        print(f"Commits    : {details.commits_count}")
        print(f"Files      : {details.changed_files_count} (+{details.total_additions} / -{details.total_deletions})")
        print("\nDESCRIPTION / INTENT:")
        print("-" * 60)
        print(details.description or "(No description provided)")
        print("-" * 60)

        print("\nCOMMITS:")
        for commit in details.commits[:5]:
            print(f"  * {commit.sha[:8]} - {commit.message.splitlines()[0]} ({commit.author_name})")
        if len(details.commits) > 5:
            print(f"  ... and {len(details.commits) - 5} more commits")

        print("\nCHANGED FILES & PATCH HUNKS:")
        for f in details.files:
            print(f"  * [{f.status.upper()}] {f.filename} (+{f.additions}/-{f.deletions})")
            if f.patch:
                patch_lines = f.patch.splitlines()
                first_few = patch_lines[:6]
                for l in first_few:
                    print(f"      {l}")
                if len(patch_lines) > 6:
                    print(f"      ... [{len(patch_lines) - 6} more patch lines]")
            else:
                print("      (No patch available - e.g. binary or unchanged file)")

        print("=" * 60)
        print("[SUCCESS] Successfully imported PR.\n")

    except ChangeGuardException as exc:
        print(f"\n[!] ChangeGuard Error: {exc.message}", file=sys.stderr)
        if exc.details:
            print(f"    Details: {json.dumps(exc.details)}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"\n[!] Unexpected Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
