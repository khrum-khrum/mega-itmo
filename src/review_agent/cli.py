"""CLI for Review Agent."""

import os
import sys

import click
from dotenv import load_dotenv

from src.review_agent.agent import ReviewAgent
from src.utils.github_client import GitHubClient

load_dotenv()


@click.command()
@click.option(
    "--repo",
    envvar="GITHUB_REPO",
    help="GitHub repository (owner/repo). Can also be set via GITHUB_REPO env var.",
)
@click.option(
    "--pr",
    envvar="PR_NUMBER",
    type=int,
    help="Pull Request number. Can also be set via PR_NUMBER env var.",
)
@click.option(
    "--model",
    default="llama-3.3-70b-versatile",
    help="LLM model to use (OpenRouter format). Default: llama-3.1-70b-instruct",
)
@click.option(
    "--execute",
    is_flag=True,
    default=False,
    help="Execute mode: submit review to GitHub (default: dry-run only)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Verbose output",
)
@click.option(
    "--repos-dir",
    default="./repos",
    help="Directory to store cloned repositories (default: ./repos)",
)
def main(
    repo: str | None,
    pr: int | None,
    model: str,
    execute: bool,
    verbose: bool,
    repos_dir: str,
) -> None:
    """
    Review Agent - analyzes Pull Requests and publishes review feedback.

    This agent:
    1. Fetches PR data from GitHub
    2. Analyzes code changes using LangChain agent
    3. Generates constructive review feedback
    4. Submits review to GitHub (in --execute mode)

    Examples:

        # Dry-run review (no GitHub submission)
        python -m src.review_agent.cli --repo owner/repo --pr 123

        # Execute and submit review to GitHub
        python -m src.review_agent.cli --repo owner/repo --pr 123 --execute

        # Use different model
        python -m src.review_agent.cli --repo owner/repo --pr 123 --model anthropic/claude-3.5-sonnet

        # With verbose output
        python -m src.review_agent.cli --repo owner/repo --pr 123 -v

        # Using environment variables
        export GITHUB_REPO=owner/repo
        export PR_NUMBER=123
        python -m src.review_agent.cli --execute
    """
    # Validate required parameters
    if not repo:
        click.echo("❌ Error: --repo is required (or set GITHUB_REPO env var)", err=True)
        sys.exit(1)

    if not pr:
        click.echo("❌ Error: --pr is required (or set PR_NUMBER env var)", err=True)
        sys.exit(1)

    click.echo("🔍 Review Agent starting...")
    click.echo(f"   Repository: {repo}")
    click.echo(f"   PR: #{pr}")
    click.echo(f"   Model: {model}")
    click.echo(f"   Mode: {'EXECUTE' if execute else 'DRY-RUN'}")
    click.echo()

    try:
        # Initialize clients
        github_token = os.getenv("GITHUB_TOKEN")
        api_key = os.getenv("OPENROUTER_API_KEY")

        if not github_token:
            click.echo("❌ Error: GITHUB_TOKEN environment variable not set", err=True)
            sys.exit(1)

        if not api_key:
            click.echo("❌ Error: OPENROUTER_API_KEY environment variable not set", err=True)
            sys.exit(1)

        # Set GITHUB_REPO env var for tools to access
        os.environ["GITHUB_REPO"] = repo

        github_client = GitHubClient(token=github_token, repos_dir=repos_dir)

        # Run review agent
        with ReviewAgent(github_client, model=model, api_key=api_key) as agent:
            # 1. Review PR
            result = agent.review_pull_request(
                repo_name=repo,
                pr_number=pr,
                verbose=verbose,
            )

            if not result.success:
                click.echo(f"\n❌ Review failed: {result.error}", err=True)
                sys.exit(1)

            # 2. Display review result
            click.echo("\n" + "=" * 60)
            click.echo("📋 REVIEW RESULT")
            click.echo("=" * 60)
            click.echo(f"\n{'✅ APPROVED' if result.approved else '⚠️  CHANGES REQUESTED'}")
            click.echo(f"\n{result.review_summary}")
            click.echo("\n" + "=" * 60)

            # 3. Submit review if in execute mode
            if execute:
                review_url = agent.submit_review(
                    repo_name=repo,
                    pr_number=pr,
                    review_result=result,
                    verbose=verbose,
                )
                click.echo(f"\n✅ Review submitted: {review_url}")
            else:
                click.echo("\n⚠️  Dry-run mode: Review not submitted to GitHub")
                click.echo("   Use --execute to submit the review")

            click.echo("\n✅ Review Agent completed successfully!")

    except KeyboardInterrupt:
        click.echo("\n\n⚠️  Interrupted by user", err=True)
        sys.exit(130)
    except Exception as e:
        click.echo(f"\n❌ Error: {str(e)}", err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
