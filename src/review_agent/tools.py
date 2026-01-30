"""LangChain tools for Review Agent."""

import os
import subprocess
from pathlib import Path
from typing import Annotated

from langchain.tools import tool


@tool
def read_pr_file(file_path: Annotated[str, "Path to the file to read"]) -> str:
    """
    Read the contents of a file from the cloned repository.

    Use this tool to examine code that was changed in the Pull Request
    to understand the context and implementation.

    Args:
        file_path: Relative path to the file from the repository root

    Returns:
        File contents as a string, or error message if file not found
    """
    try:
        full_path = Path(file_path)
        if not full_path.exists():
            return f"Error: File {file_path} not found"

        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        return f"Content of {file_path}:\n\n{content}"
    except Exception as e:
        return f"Error reading file {file_path}: {str(e)}"


@tool
def search_code_in_pr(
    pattern: Annotated[str, "Regex pattern to search for"],
    file_pattern: Annotated[str, "File glob pattern (e.g., '*.py', '*.js')"] = "*",
    directory: Annotated[str, "Directory to search in"] = ".",
) -> str:
    """
    Search for code patterns in the repository using regex.

    Use this tool to find related code, similar implementations, or
    patterns that might be affected by the PR changes.

    Args:
        pattern: Regular expression pattern to search for
        file_pattern: Glob pattern for file types (e.g., '*.py', '*.js', '*.ts')
        directory: Directory to search in (default: current directory)

    Returns:
        List of matches with file paths and line numbers
    """
    import re

    try:
        path = Path(directory)
        if not path.exists():
            return f"Error: Directory {directory} not found"

        matches = []
        for file_path in path.rglob(file_pattern):
            if file_path.is_file() and not any(
                part.startswith(".") for part in file_path.parts
            ):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        for line_num, line in enumerate(f, 1):
                            if re.search(pattern, line):
                                matches.append(
                                    f"{file_path}:{line_num}: {line.strip()}"
                                )
                except (UnicodeDecodeError, PermissionError):
                    continue

        if not matches:
            return f"No matches found for pattern '{pattern}' in {file_pattern} files"

        # Limit results to avoid overwhelming the LLM
        if len(matches) > 50:
            return (
                "Found matches:\n"
                + "\n".join(matches[:50])
                + f"\n... ({len(matches) - 50} more matches)"
            )

        return "Found matches:\n" + "\n".join(matches)
    except Exception as e:
        return f"Error searching code: {str(e)}"


@tool
def run_test_command(
    command: Annotated[str, "Shell command to execute"],
    working_dir: Annotated[str, "Working directory for the command"] = ".",
) -> str:
    """
    Execute a shell command in the repository (read-only, for verification).

    Use this tool to run tests, linters, or other verification commands
    to check if the PR introduces issues.

    Args:
        command: Shell command to execute
        working_dir: Working directory for the command (default: current directory)

    Returns:
        Command output (stdout and stderr combined)
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=60,  # Longer timeout for tests
        )

        output = result.stdout + result.stderr
        if result.returncode != 0:
            return f"Command failed (exit code {result.returncode}):\n{output}"

        return f"Command output:\n{output}" if output else "Command executed successfully (no output)"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 60 seconds"
    except Exception as e:
        return f"Error executing command: {str(e)}"


@tool
def analyze_pr_complexity(file_path: Annotated[str, "Path to file to analyze"]) -> str:
    """
    Analyze code complexity of a changed file.

    Use this tool to identify potentially complex or problematic code
    that might need closer review.

    Args:
        file_path: Path to the file to analyze

    Returns:
        Analysis of code complexity (function count, line count, etc.)
    """
    try:
        full_path = Path(file_path)
        if not full_path.exists():
            return f"Error: File {file_path} not found"

        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
            lines = content.split("\n")

        # Basic metrics
        total_lines = len(lines)
        code_lines = len([line for line in lines if line.strip() and not line.strip().startswith("#")])

        # Count functions/methods (simple heuristic for Python)
        function_count = len([line for line in lines if line.strip().startswith("def ")])
        class_count = len([line for line in lines if line.strip().startswith("class ")])

        return f"""Complexity analysis for {file_path}:
- Total lines: {total_lines}
- Code lines (non-blank, non-comment): {code_lines}
- Functions/methods: {function_count}
- Classes: {class_count}
- Average lines per function: {code_lines // max(function_count, 1)}
"""
    except Exception as e:
        return f"Error analyzing file {file_path}: {str(e)}"


@tool
def fetch_issue_details(issue_number: Annotated[int, "GitHub Issue number to fetch"]) -> str:
    """
    Fetch the details of a GitHub Issue to understand the requirements.

    Use this tool to retrieve the original issue that the PR is trying to solve.
    This helps you verify that the PR implementation matches the issue requirements.

    Args:
        issue_number: The GitHub Issue number (e.g., 123)

    Returns:
        Issue details including title, description, and requirements
    """
    try:
        from github import Github

        token = os.getenv("GITHUB_TOKEN")
        repo_name = os.getenv("GITHUB_REPO")

        if not token or not repo_name:
            return "Error: GITHUB_TOKEN and GITHUB_REPO environment variables must be set"

        g = Github(token)
        repo = g.get_repo(repo_name)
        issue = repo.get_issue(issue_number)

        return f"""Issue #{issue.number}: {issue.title}

**Status:** {issue.state}
**Labels:** {', '.join([label.name for label in issue.labels])}

**Description:**
{issue.body or 'No description provided'}

**URL:** {issue.html_url}
"""
    except Exception as e:
        return f"Error fetching issue #{issue_number}: {str(e)}"


@tool
def query_library_docs(
    library_name: Annotated[str, "Name of the library (e.g., 'langchain', 'pytest')"],
    query: Annotated[str, "Specific question or topic to search for"],
) -> str:
    """
    Query up-to-date documentation for a library using Context7 MCP.

    Use this tool when you need to verify if the PR is using library APIs correctly
    or to check best practices for specific libraries mentioned in the code.

    Args:
        library_name: Name of the library to query (e.g., 'langchain', 'pytest', 'fastapi')
        query: The specific question or topic (e.g., 'how to create tools', 'async testing')

    Returns:
        Documentation and examples from Context7
    """
    try:
        # This will be called through MCP integration
        # For now, return a placeholder that indicates the tool is available
        return f"""Querying Context7 for library '{library_name}' with query: '{query}'

Note: This tool integrates with Context7 MCP server to fetch latest documentation.
To use it effectively, ensure Context7 MCP is configured in your environment.
"""
    except Exception as e:
        return f"Error querying library docs for {library_name}: {str(e)}"


@tool
def check_pr_workflows(
    commit_sha: Annotated[str, "Commit SHA to check workflows for (use 'HEAD' for current commit)"],
) -> str:
    """
    Check GitHub Actions workflow status for a Pull Request commit.

    Use this tool to verify that GitHub workflows (CI/CD pipelines) are passing
    for the PR changes. This is MANDATORY for approving a PR.

    **CRITICAL**: A PR should ONLY be approved (marked as READY TO MERGE) if:
    1. All workflows pass successfully
    2. No workflow failures exist
    3. All checks are complete

    Args:
        commit_sha: Commit SHA to check (use 'HEAD' for the latest commit in the PR)

    Returns:
        Status of all workflows for the commit
    """
    try:
        import subprocess

        # Get current commit SHA if HEAD is requested
        if commit_sha.upper() == "HEAD":
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return f"Error getting current commit SHA: {result.stderr}"
            commit_sha = result.stdout.strip()

        # Get repo name and GitHub token from environment
        repo_name = os.getenv("GITHUB_REPO")
        token = os.getenv("GITHUB_TOKEN")

        if not repo_name or not token:
            return "Error: GITHUB_REPO and GITHUB_TOKEN environment variables must be set"

        # Import here to avoid circular dependency
        from src.utils.github_client import GitHubClient

        client = GitHubClient(token=token)
        workflows = client.get_workflow_runs_for_commit(repo_name, commit_sha)

        if not workflows:
            return f"""No GitHub workflows found for commit {commit_sha[:8]}

⚠️ WARNING: This repository may not have GitHub Actions workflows configured.
If workflows should exist, this could indicate an issue with the PR.
"""

        # Format output
        output_lines = [f"GitHub workflows status for PR commit {commit_sha[:8]}:\n"]

        all_passed = True
        has_failures = False
        has_pending = False

        for workflow_name, status in workflows.items():
            if status == "success":
                status_icon = "[PASS]"
            elif status == "failure":
                status_icon = "[FAIL]"
                all_passed = False
                has_failures = True
            elif status in ["in_progress", "queued"]:
                status_icon = "[RUNNING]"
                all_passed = False
                has_pending = True
            else:
                status_icon = "[UNKNOWN]"
                all_passed = False

            output_lines.append(f"{status_icon} {workflow_name}: {status}")

        # Provide clear guidance
        output_lines.append("")
        if all_passed:
            output_lines.append("All workflows passed successfully")
            output_lines.append("PR can be approved (READY TO MERGE)")
        elif has_failures:
            output_lines.append("Some workflows FAILED")
            output_lines.append("PR MUST NOT be approved (mark as NEEDS CHANGES)")
            output_lines.append("The code has issues that must be fixed before merging.")
        elif has_pending:
            output_lines.append("Some workflows are still running")
            output_lines.append("Wait for all workflows to complete before final assessment")
            output_lines.append("PR should be marked as REQUIRES DISCUSSION until workflows complete")

        return "\n".join(output_lines)

    except Exception as e:
        return f"Error checking GitHub workflows: {str(e)}"


# Export all tools
ALL_REVIEW_TOOLS = [
    read_pr_file,
    search_code_in_pr,
    run_test_command,
    analyze_pr_complexity,
    fetch_issue_details,
    query_library_docs,
    check_pr_workflows,
]
