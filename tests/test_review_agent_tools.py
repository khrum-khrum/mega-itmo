"""Unit tests for src/review_agent/tools.py — one test suite per tool."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.review_agent.tools import (
    analyze_pr_complexity,
    check_pr_workflows,
    fetch_issue_details,
    query_library_docs,
    read_pr_file,
    run_test_command,
    search_code_in_pr,
)

# --- read_pr_file ---


class TestReadPrFile:
    """Tests for read_pr_file tool."""

    def test_read_existing_file(self, tmp_path: Path) -> None:
        """Should return file content when file exists."""
        f = tmp_path / "test.py"
        f.write_text("def foo():\n    pass\n", encoding="utf-8")
        result = read_pr_file.invoke({"file_path": str(f)})
        assert "Content of " in result
        assert "def foo()" in result

    def test_read_file_not_found(self, tmp_path: Path) -> None:
        """Should return error when file does not exist."""
        result = read_pr_file.invoke({"file_path": str(tmp_path / "missing.py")})
        assert "Error" in result
        assert "not found" in result

    def test_read_file_with_special_characters(self, tmp_path: Path) -> None:
        """Should handle files with special characters."""
        f = tmp_path / "unicode.txt"
        f.write_text("Hello 世界 🌍\n", encoding="utf-8")
        result = read_pr_file.invoke({"file_path": str(f)})
        assert "Content of " in result
        assert "世界" in result


# --- search_code_in_pr ---


class TestSearchCodeInPr:
    """Tests for search_code_in_pr tool."""

    def test_search_finds_pattern(self, tmp_path: Path) -> None:
        """Should find regex matches with file path and line number."""
        py_file = tmp_path / "main.py"
        py_file.write_text("def foo():\n    x = 1\n", encoding="utf-8")
        result = search_code_in_pr.invoke(
            {
                "pattern": r"def foo",
                "file_pattern": "*.py",
                "directory": str(tmp_path),
            }
        )
        assert "Found matches" in result
        assert "main.py" in result
        assert "def foo" in result

    def test_search_no_matches(self, tmp_path: Path) -> None:
        """Should return no-matches message when pattern not found."""
        (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
        result = search_code_in_pr.invoke(
            {
                "pattern": r"nonexistent_pattern_xyz",
                "file_pattern": "*.py",
                "directory": str(tmp_path),
            }
        )
        assert "No matches found" in result

    def test_search_directory_not_found(self) -> None:
        """Should return error when directory does not exist."""
        result = search_code_in_pr.invoke(
            {
                "pattern": "x",
                "file_pattern": "*",
                "directory": "/nonexistent/dir/12345",
            }
        )
        assert "Error" in result
        assert "not found" in result

    def test_search_with_file_pattern(self, tmp_path: Path) -> None:
        """Should filter files by glob pattern."""
        (tmp_path / "test.py").write_text("foo = 1\n", encoding="utf-8")
        (tmp_path / "test.txt").write_text("foo = 2\n", encoding="utf-8")
        result = search_code_in_pr.invoke(
            {
                "pattern": "foo",
                "file_pattern": "*.py",
                "directory": str(tmp_path),
            }
        )
        assert "test.py" in result
        assert "test.txt" not in result

    def test_search_skips_hidden_files(self, tmp_path: Path) -> None:
        """Should skip files in hidden directories."""
        hidden_dir = tmp_path / ".git"
        hidden_dir.mkdir()
        (hidden_dir / "config").write_text("foo = 1\n", encoding="utf-8")
        (tmp_path / "visible.py").write_text("foo = 2\n", encoding="utf-8")
        result = search_code_in_pr.invoke(
            {
                "pattern": "foo",
                "file_pattern": "*",
                "directory": str(tmp_path),
            }
        )
        assert "visible.py" in result
        assert ".git" not in result


# --- run_test_command ---


class TestRunTestCommand:
    """Tests for run_test_command tool."""

    def test_run_success_with_output(self, tmp_path: Path) -> None:
        """Should return command output on success."""
        result = run_test_command.invoke(
            {
                "command": "echo hello",
                "working_dir": str(tmp_path),
            }
        )
        assert "Command output" in result or "hello" in result

    def test_run_failure_returns_exit_code(self, tmp_path: Path) -> None:
        """Should return failure message with exit code when command fails."""
        result = run_test_command.invoke(
            {
                "command": "exit 1",
                "working_dir": str(tmp_path),
            }
        )
        assert "Command failed" in result or "exit code" in result

    def test_run_timeout_returns_error(self) -> None:
        """Should return timeout error when command exceeds 60s."""
        with patch("src.review_agent.tools.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("sleep", 60)
            result = run_test_command.invoke(
                {
                    "command": "sleep 65",
                    "working_dir": ".",
                }
            )
        assert "timed out" in result

    def test_run_with_default_working_dir(self) -> None:
        """Should run command with default working directory."""
        result = run_test_command.invoke({"command": "pwd"})
        assert "Command output" in result or "Error" not in result


# --- analyze_pr_complexity ---


class TestAnalyzePrComplexity:
    """Tests for analyze_pr_complexity tool."""

    def test_analyze_python_file(self, tmp_path: Path) -> None:
        """Should analyze Python file and return metrics."""
        py_file = tmp_path / "module.py"
        py_file.write_text(
            """class Foo:
    def method1(self):
        pass

def function1():
    pass

# Comment
def function2():
    x = 1
""",
            encoding="utf-8",
        )
        result = analyze_pr_complexity.invoke({"file_path": str(py_file)})
        assert "Total lines" in result
        assert "Code lines" in result
        assert "Functions/methods" in result
        assert "Classes" in result

    def test_analyze_file_not_found(self, tmp_path: Path) -> None:
        """Should return error when file does not exist."""
        result = analyze_pr_complexity.invoke({"file_path": str(tmp_path / "missing.py")})
        assert "Error" in result
        assert "not found" in result

    def test_analyze_empty_file(self, tmp_path: Path) -> None:
        """Should handle empty file."""
        f = tmp_path / "empty.py"
        f.write_text("", encoding="utf-8")
        result = analyze_pr_complexity.invoke({"file_path": str(f)})
        assert "Total lines" in result
        assert "0" in result or "1" in result

    def test_analyze_counts_functions(self, tmp_path: Path) -> None:
        """Should correctly count functions."""
        py_file = tmp_path / "funcs.py"
        py_file.write_text(
            """def foo():
    pass

def bar():
    return 1
""",
            encoding="utf-8",
        )
        result = analyze_pr_complexity.invoke({"file_path": str(py_file)})
        assert "Functions/methods: 2" in result

    def test_analyze_counts_classes(self, tmp_path: Path) -> None:
        """Should correctly count classes."""
        py_file = tmp_path / "classes.py"
        py_file.write_text(
            """class A:
    pass

class B:
    pass
""",
            encoding="utf-8",
        )
        result = analyze_pr_complexity.invoke({"file_path": str(py_file)})
        assert "Classes: 2" in result


# --- fetch_issue_details ---


class TestFetchIssueDetails:
    """Tests for fetch_issue_details tool."""

    @patch("github.Github")
    @patch.dict("os.environ", {"GITHUB_TOKEN": "fake_token", "GITHUB_REPO": "owner/repo"})
    def test_fetch_issue_success(self, mock_github_class: MagicMock) -> None:
        """Should fetch and format issue details."""
        mock_issue = MagicMock()
        mock_issue.number = 123
        mock_issue.title = "Test Issue"
        mock_issue.state = "open"
        mock_issue.body = "This is a test issue"
        mock_issue.html_url = "https://github.com/owner/repo/issues/123"
        mock_issue.labels = []

        mock_repo = MagicMock()
        mock_repo.get_issue.return_value = mock_issue

        mock_github = MagicMock()
        mock_github.get_repo.return_value = mock_repo
        mock_github_class.return_value = mock_github

        result = fetch_issue_details.invoke({"issue_number": 123})
        assert "Issue #123" in result
        assert "Test Issue" in result
        assert "open" in result
        assert "This is a test issue" in result

    @patch.dict("os.environ", {}, clear=True)
    def test_fetch_issue_missing_env(self) -> None:
        """Should return error when environment variables are missing."""
        result = fetch_issue_details.invoke({"issue_number": 123})
        assert "Error" in result
        assert "GITHUB_TOKEN" in result or "environment" in result

    @patch("github.Github")
    @patch.dict("os.environ", {"GITHUB_TOKEN": "fake_token", "GITHUB_REPO": "owner/repo"})
    def test_fetch_issue_with_labels(self, mock_github_class: MagicMock) -> None:
        """Should include labels in issue details."""
        mock_label1 = MagicMock()
        mock_label1.name = "bug"
        mock_label2 = MagicMock()
        mock_label2.name = "enhancement"

        mock_issue = MagicMock()
        mock_issue.number = 456
        mock_issue.title = "Issue with labels"
        mock_issue.state = "open"
        mock_issue.body = "Test"
        mock_issue.html_url = "https://github.com/owner/repo/issues/456"
        mock_issue.labels = [mock_label1, mock_label2]

        mock_repo = MagicMock()
        mock_repo.get_issue.return_value = mock_issue

        mock_github = MagicMock()
        mock_github.get_repo.return_value = mock_repo
        mock_github_class.return_value = mock_github

        result = fetch_issue_details.invoke({"issue_number": 456})
        assert "bug" in result
        assert "enhancement" in result


# --- query_library_docs ---


class TestQueryLibraryDocs:
    """Tests for query_library_docs tool."""

    def test_query_library_docs_returns_placeholder(self) -> None:
        """Should return Context7 placeholder message."""
        result = query_library_docs.invoke(
            {
                "library_name": "langchain",
                "query": "how to create tools",
            }
        )
        assert "Context7" in result
        assert "langchain" in result
        assert "how to create tools" in result

    def test_query_library_docs_with_different_library(self) -> None:
        """Should handle different library names."""
        result = query_library_docs.invoke(
            {
                "library_name": "pytest",
                "query": "async testing",
            }
        )
        assert "pytest" in result
        assert "async testing" in result


# --- check_pr_workflows ---


class TestCheckPrWorkflows:
    """Tests for check_pr_workflows tool."""

    @patch("src.review_agent.tools._get_pr_github_client")
    def test_check_workflows_missing_env_returns_error(self, mock_get_client: MagicMock) -> None:
        """Should return error when GITHUB_REPO or GITHUB_TOKEN not set."""
        mock_get_client.side_effect = ValueError(
            "GITHUB_REPO and GITHUB_TOKEN environment variables must be set"
        )
        result = check_pr_workflows.invoke({"commit_sha": "abc123"})
        assert "Error" in result
        assert "GITHUB" in result or "environment" in result

    @patch("src.review_agent.tools._get_pr_github_client")
    @patch("src.review_agent.tools._resolve_pr_commit_sha")
    def test_check_workflows_all_pass(
        self, mock_resolve: MagicMock, mock_client: MagicMock
    ) -> None:
        """Should return success message when all workflows pass."""
        mock_resolve.return_value = "abc12345"
        mock_github = MagicMock()
        mock_github.get_workflow_runs_for_commit.return_value = {
            "CI": "success",
            "Lint": "success",
        }
        mock_client.return_value = (mock_github, "owner/repo")
        result = check_pr_workflows.invoke({"commit_sha": "HEAD"})
        assert "abc12345" in result or "GitHub workflows" in result
        assert "[PASS]" in result or "All workflows passed" in result
        assert "READY TO MERGE" in result

    @patch("src.review_agent.tools._get_pr_github_client")
    @patch("src.review_agent.tools._resolve_pr_commit_sha")
    def test_check_workflows_with_failures(
        self, mock_resolve: MagicMock, mock_client: MagicMock
    ) -> None:
        """Should return failure message when workflows fail."""
        mock_resolve.return_value = "def45678"
        mock_github = MagicMock()
        mock_github.get_workflow_runs_for_commit.return_value = {
            "CI": "failure",
            "Lint": "success",
        }
        mock_client.return_value = (mock_github, "owner/repo")
        result = check_pr_workflows.invoke({"commit_sha": "def45678"})
        assert "[FAIL]" in result or "FAILED" in result
        assert "NEEDS CHANGES" in result

    @patch("src.review_agent.tools._get_pr_github_client")
    @patch("src.review_agent.tools._resolve_pr_commit_sha")
    def test_check_workflows_pending(self, mock_resolve: MagicMock, mock_client: MagicMock) -> None:
        """Should handle pending workflows."""
        mock_resolve.return_value = "ghi91011"
        mock_github = MagicMock()
        mock_github.get_workflow_runs_for_commit.return_value = {
            "CI": "in_progress",
            "Lint": "queued",
        }
        mock_client.return_value = (mock_github, "owner/repo")
        result = check_pr_workflows.invoke({"commit_sha": "ghi91011"})
        assert "[RUNNING]" in result or "running" in result
        assert "REQUIRES DISCUSSION" in result or "Wait" in result

    @patch("src.review_agent.tools._get_pr_github_client")
    @patch("src.review_agent.tools._resolve_pr_commit_sha")
    def test_check_workflows_no_workflows(
        self, mock_resolve: MagicMock, mock_client: MagicMock
    ) -> None:
        """Should handle case when no workflows found."""
        mock_resolve.return_value = "jkl12131"
        mock_github = MagicMock()
        mock_github.get_workflow_runs_for_commit.return_value = {}
        mock_client.return_value = (mock_github, "owner/repo")
        result = check_pr_workflows.invoke({"commit_sha": "jkl12131"})
        assert "No GitHub workflows found" in result
        assert "WARNING" in result

    @patch("src.review_agent.tools.subprocess.run")
    def test_resolve_pr_commit_sha_head(self, mock_run: MagicMock) -> None:
        """Should resolve HEAD to actual commit SHA."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "abc123def456\n"
        mock_run.return_value = mock_result

        from src.review_agent.tools import _resolve_pr_commit_sha

        result = _resolve_pr_commit_sha("HEAD")
        assert result == "abc123def456"

    def test_resolve_pr_commit_sha_passthrough(self) -> None:
        """Should pass through non-HEAD commit SHAs."""
        from src.review_agent.tools import _resolve_pr_commit_sha

        result = _resolve_pr_commit_sha("abc123")
        assert result == "abc123"
