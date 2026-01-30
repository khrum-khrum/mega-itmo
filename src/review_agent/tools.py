"""LangChain tools for Review Agent."""

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


# Export all tools
ALL_REVIEW_TOOLS = [
    read_pr_file,
    search_code_in_pr,
    run_test_command,
    analyze_pr_complexity,
]
