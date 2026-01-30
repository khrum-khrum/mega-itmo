"""CLI for LangChain-based Code Agent."""

import sys

import click

from src.code_agent.agent import CodeAgent
from src.utils.github_client import GitHubClient


@click.command()
@click.option(
    "--repo",
    envvar="GITHUB_REPO",
    required=True,
    help="GitHub repository in format owner/repo",
)
@click.option(
    "--issue",
    required=True,
    type=int,
    help="Issue number to solve",
)
@click.option(
    "--pr",
    type=int,
    help="Pull Request number (if working on existing PR for the issue)",
)
@click.option(
    "--token",
    envvar="GITHUB_TOKEN",
    help="GitHub Personal Access Token",
)
@click.option(
    "--api-key",
    envvar="OPENROUTER_API_KEY",
    help="OpenRouter API Key",
)
@click.option(
    "--model",
    default="llama-3.3-70b-versatile",
    help=(
        "LLM model to use. Examples: llama-3.3-70b-versatile, "
        "anthropic/claude-3.5-sonnet, openai/gpt-4o"
    ),
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=True,
    help="Only show solution without creating PR (default)",
)
@click.option(
    "--execute",
    is_flag=True,
    help="Create PR with the solution (disables dry-run)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Verbose output",
)
@click.option(
    "--repos-dir",
    default="./repos",
    help="Directory where cloned repositories will be stored (default: ./repos)",
)
def main(
    repo: str,
    issue: int,
    pr: int | None,
    token: str | None,
    api_key: str | None,
    model: str,
    dry_run: bool,
    execute: bool,
    verbose: bool,
    repos_dir: str,
) -> None:
    """
    LangChain-based Code Agent - analyzes Issues and generates code solutions.

    This version uses LangChain with custom tools to work directly with the
    cloned repository, providing a more intelligent and autonomous approach.

    \b
    Examples:
        # Analyze Issue with Llama (default)
        python -m src.code_agent.cli --repo owner/repo --issue 123

        # Use Claude 3.5 Sonnet
        python -m src.code_agent.cli --repo owner/repo --issue 1 \\
            --model anthropic/claude-3.5-sonnet

        # Create PR automatically
        python -m src.code_agent.cli --repo owner/repo --issue 1 --execute

        # Work on existing PR (address feedback)
        python -m src.code_agent.cli --repo owner/repo --issue 1 --pr 456 --execute

        # Custom repos directory
        python -m src.code_agent.cli --repo owner/repo --issue 1 \\
            --repos-dir /path/to/repos

        # Verbose mode
        python -m src.code_agent.cli --repo owner/repo --issue 1 -v
    """
    if execute:
        dry_run = False

    click.echo("LangChain Code Agent")
    click.echo(f"Repository: {repo}")
    click.echo(f"Issue: #{issue}")
    if pr:
        click.echo(f"PR: #{pr} (existing PR - will add commits)")
    click.echo(f"Model: {model}")
    click.echo()

    # Initialize GitHub client
    try:
        github_client = GitHubClient(token=token, repos_dir=repos_dir)
        if verbose:
            click.echo(f"GitHub client initialized (repos directory: {repos_dir})")
    except ValueError as e:
        click.echo(f"Error: GitHub client error: {e}", err=True)
        sys.exit(1)

    # Initialize Code Agent
    try:
        agent = CodeAgent(
            github_client=github_client,
            model=model,
            api_key=api_key,
        )
        if verbose:
            click.echo("Code Agent initialized")
    except ValueError as e:
        click.echo(f"Error: Code Agent error: {e}", err=True)
        sys.exit(1)

    # Use context manager for automatic cleanup
    with agent:
        # Analyze and solve the issue
        click.echo(f"\n{'='*60}")
        click.echo(f"Analyzing Issue #{issue}")
        click.echo(f"{'='*60}\n")

        try:
            result = agent.analyze_and_solve_issue(
                repo_name=repo,
                issue_number=issue,
                pr_number=pr,
                verbose=verbose,
            )
        except Exception as e:
            click.echo(f"\nError during analysis: {e}", err=True)
            sys.exit(1)

        if not result.success:
            click.echo(f"\nError: Agent execution failed: {result.error}", err=True)
            sys.exit(1)

        # Display results
        click.echo(f"\n{'='*60}")
        click.echo("SOLUTION")
        click.echo(f"{'='*60}\n")
        click.echo(result.output)
        click.echo()

        # Check if agent decided no changes are needed
        if not result.repo_path or "No changes needed" in result.output:
            click.echo(f"{'─'*60}")
            click.echo("No changes needed - PR feedback is positive")
            if pr:
                existing_pr = agent.github.get_pull_request(repo, pr)
                click.echo(f"PR: {existing_pr.html_url}")
            click.echo(f"{'─'*60}")
            return

        if dry_run:
            click.echo(f"{'─'*60}")
            click.echo("DRY-RUN MODE: Changes not pushed")
            click.echo(f"Repository cloned to: {result.repo_path}")
            click.echo("Review changes manually or use --execute to create PR")
            click.echo(f"{'─'*60}")
        else:
            # Execute mode: commit, push, and create PR
            click.echo(f"\n{'='*60}")
            click.echo("CREATING PULL REQUEST")
            click.echo(f"{'='*60}\n")

            # Get commit message
            commit_message = f"feat: solve issue #{issue}\n\nAutomatically generated by Code Agent"

            try:
                # Commit and push
                agent.commit_and_push(
                    result=result,
                    commit_message=commit_message,
                    verbose=verbose,
                )

                # Create or update PR
                if pr:
                    # PR already exists, just show the URL
                    existing_pr = agent.github.get_pull_request(repo, pr)
                    click.echo("\nChanges pushed to existing Pull Request")
                    click.echo(f"PR: {existing_pr.html_url}")
                else:
                    # Create new PR
                    pr_url = agent.create_pull_request(
                        repo_name=repo,
                        issue_number=issue,
                        result=result,
                        verbose=verbose,
                    )

                    click.echo("\nPull Request created successfully")
                    click.echo(f"PR: {pr_url}")

            except RuntimeError as e:
                click.echo(f"\nError creating PR: {e}", err=True)
                sys.exit(1)


if __name__ == "__main__":
    main()
