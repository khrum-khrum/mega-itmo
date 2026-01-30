"""LangChain tools for Code Agent."""

import os
import re
import subprocess
from pathlib import Path
from typing import Annotated

from langchain.tools import tool


@tool
def read_file(file_path: Annotated[str, "Path to the file to read"]) -> str:
    """
    Read the contents of a file from the cloned repository.

    Use this tool to examine existing code, configuration files, or any text files
    in the repository. This helps understand the codebase structure and existing
    implementations before making changes.

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
def list_directory(
    directory_path: Annotated[str, "Path to the directory to list"] = "."
) -> str:
    """
    List all files and directories in a given path.

    Use this tool to explore the repository structure, find existing files,
    and understand the organization of the codebase.

    Args:
        directory_path: Relative path to the directory (default: current directory)

    Returns:
        Formatted list of files and directories
    """
    try:
        path = Path(directory_path)
        if not path.exists():
            return f"Error: Directory {directory_path} not found"

        if not path.is_dir():
            return f"Error: {directory_path} is not a directory"

        items = []
        for item in sorted(path.iterdir()):
            if item.name.startswith("."):
                continue
            icon = "[DIR]" if item.is_dir() else "[FILE]"
            items.append(f"{icon} {item.name}")

        if not items:
            return f"Directory {directory_path} is empty"

        return f"Contents of {directory_path}:\n" + "\n".join(items)
    except Exception as e:
        return f"Error listing directory {directory_path}: {str(e)}"


@tool
def search_code(
    pattern: Annotated[str, "Regex pattern to search for"],
    file_pattern: Annotated[str, "File glob pattern (e.g., '*.py', '*.js')"] = "*",
    directory: Annotated[str, "Directory to search in"] = ".",
) -> str:
    """
    Search for code patterns in the repository using regex.

    Use this tool to find specific functions, classes, variables, or patterns
    in the codebase. This helps locate where certain functionality is implemented.

    Args:
        pattern: Regular expression pattern to search for
        file_pattern: Glob pattern for file types (e.g., '*.py', '*.js', '*.ts')
        directory: Directory to search in (default: current directory)

    Returns:
        List of matches with file paths and line numbers
    """
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
def get_file_tree(
    directory: Annotated[str, "Directory to get tree for"] = ".",
    max_depth: Annotated[int, "Maximum depth to traverse"] = 3,
) -> str:
    """
    Get a tree-like structure of the repository.

    Use this tool to understand the overall project structure and file organization.

    Args:
        directory: Directory to get tree for (default: current directory)
        max_depth: Maximum depth to traverse (default: 3)

    Returns:
        Tree structure as a string
    """
    try:
        path = Path(directory)
        if not path.exists():
            return f"Error: Directory {directory} not found"

        def build_tree(current_path: Path, prefix: str = "", depth: int = 0) -> list[str]:
            if depth > max_depth:
                return []

            items = []
            try:
                entries = sorted(current_path.iterdir(), key=lambda x: (not x.is_dir(), x.name))
                # Filter out common non-essential directories
                entries = [
                    e for e in entries
                    if e.name not in {
                        ".git", "node_modules", "__pycache__", "venv",
                        ".venv", "dist", "build", ".pytest_cache"
                    }
                    and not e.name.startswith(".")
                ]

                for i, entry in enumerate(entries):
                    is_last = i == len(entries) - 1
                    current_prefix = "└── " if is_last else "├── "
                    items.append(f"{prefix}{current_prefix}{entry.name}")

                    if entry.is_dir() and depth < max_depth:
                        extension = "    " if is_last else "│   "
                        items.extend(build_tree(entry, prefix + extension, depth + 1))
            except PermissionError:
                pass

            return items

        tree_lines = [str(path) + "/"] + build_tree(path)
        return "\n".join(tree_lines)
    except Exception as e:
        return f"Error building tree: {str(e)}"


@tool
def create_file(
    file_path: Annotated[str, "Path where the file should be created"],
    content: Annotated[str, "Content to write to the file"],
) -> str:
    """
    Create a new file with the given content.

    Use this tool to create new files in the repository as part of the solution.

    Args:
        file_path: Relative path for the new file
        content: Content to write to the file

    Returns:
        Success or error message
    """
    try:
        full_path = Path(file_path)

        if full_path.exists():
            return f"Error: File {file_path} already exists. Use update_file to modify it."

        # Create parent directories if they don't exist
        full_path.parent.mkdir(parents=True, exist_ok=True)

        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

        return f"Successfully created file: {file_path}"
    except Exception as e:
        return f"Error creating file {file_path}: {str(e)}"


@tool
def update_file(
    file_path: Annotated[str, "Path to the file to update"],
    content: Annotated[str, "New content for the file"],
) -> str:
    """
    Update an existing file with new content.

    Use this tool to modify existing files in the repository. The entire file
    content will be replaced with the new content.

    Args:
        file_path: Relative path to the file to update
        content: New content to write to the file

    Returns:
        Success or error message
    """
    try:
        full_path = Path(file_path)

        if not full_path.exists():
            return f"Error: File {file_path} not found. Use create_file to create it."

        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

        return f"Successfully updated file: {file_path}"
    except Exception as e:
        return f"Error updating file {file_path}: {str(e)}"


@tool
def delete_file(file_path: Annotated[str, "Path to the file to delete"]) -> str:
    """
    Delete a file from the repository.

    Use this tool to remove files that are no longer needed.

    Args:
        file_path: Relative path to the file to delete

    Returns:
        Success or error message
    """
    try:
        full_path = Path(file_path)

        if not full_path.exists():
            return f"Error: File {file_path} not found"

        full_path.unlink()
        return f"Successfully deleted file: {file_path}"
    except Exception as e:
        return f"Error deleting file {file_path}: {str(e)}"


@tool
def run_command(
    command: Annotated[str, "Shell command to execute"],
    working_dir: Annotated[str, "Working directory for the command"] = ".",
) -> str:
    """
    Execute a shell command in the repository.

    Use this tool to run tests, build commands, or other shell operations
    needed to verify the solution.

    WARNING: Be careful with this tool. Only run safe, read-only commands
    or commands that are necessary for the solution.

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
            timeout=30,
        )

        output = result.stdout + result.stderr
        if result.returncode != 0:
            return f"Command failed (exit code {result.returncode}):\n{output}"

        return f"Command output:\n{output}" if output else "Command executed successfully (no output)"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 30 seconds"
    except Exception as e:
        return f"Error executing command: {str(e)}"


@tool
def get_git_diff(file_path: Annotated[str, "Path to file to check"] = None) -> str:
    """
    Get git diff for changes made in the working directory.

    Use this tool to review what changes have been made before finalizing
    the solution.

    Args:
        file_path: Optional path to a specific file (default: all changes)

    Returns:
        Git diff output
    """
    try:
        cmd = ["git", "diff"]
        if file_path:
            cmd.append(file_path)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if not result.stdout:
            return "No changes detected"

        return f"Git diff:\n{result.stdout}"
    except Exception as e:
        return f"Error getting git diff: {str(e)}"


@tool
def check_github_workflows(
    commit_sha: Annotated[str, "Commit SHA to check workflows for (use 'HEAD' for current commit)"],
) -> str:
    """
    Check GitHub Actions workflow status for a specific commit.

    Use this tool to verify that GitHub workflows (CI/CD pipelines) are passing
    for your changes. This is CRITICAL before finalizing your work.

    IMPORTANT: You MUST verify workflows pass before completing your task.
    If workflows fail, you need to fix the issues causing the failures.

    Args:
        commit_sha: Commit SHA to check (use 'HEAD' for the latest commit)

    Returns:
        Status of all workflows for the commit
    """
    try:
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
            return f"No GitHub workflows found for commit {commit_sha[:8]}"

        # Format output
        output_lines = [f"GitHub workflows status for commit {commit_sha[:8]}:\n"]

        all_passed = True
        for workflow_name, status in workflows.items():
            if status == "success":
                status_icon = "[PASS]"
            elif status == "failure":
                status_icon = "[FAIL]"
                all_passed = False
            elif status in ["in_progress", "queued"]:
                status_icon = "[RUNNING]"
                all_passed = False
            else:
                status_icon = "[UNKNOWN]"
                all_passed = False

            output_lines.append(f"{status_icon} {workflow_name}: {status}")

        if all_passed:
            output_lines.append("\nAll workflows passed successfully")
        else:
            output_lines.append(
                "\nSome workflows failed or are still running. "
                "You MUST fix any failures before completing the task."
            )

        return "\n".join(output_lines)

    except Exception as e:
        return f"Error checking GitHub workflows: {str(e)}"


# Export all tools
ALL_TOOLS = [
    read_file,
    list_directory,
    search_code,
    get_file_tree,
    create_file,
    update_file,
    delete_file,
    run_command,
    get_git_diff,
    check_github_workflows,
]
