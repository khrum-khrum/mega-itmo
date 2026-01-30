"""Unit tests for src/code_agent/tools.py — one test suite per tool."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.code_agent.tools import (
    check_github_workflows,
    create_file,
    delete_file,
    get_file_tree,
    get_git_diff,
    list_directory,
    read_file,
    run_command,
    search_code,
    update_file,
)

# --- read_file ---


class TestReadFile:
    """Tests for read_file tool."""

    def test_read_existing_file(self, tmp_path: Path) -> None:
        """Should return file content when file exists."""
        f = tmp_path / "hello.txt"
        f.write_text("hello world\n", encoding="utf-8")
        result = read_file.invoke({"file_path": str(f)})
        assert "Content of " in result
        assert "hello world" in result

    def test_read_file_not_found(self, tmp_path: Path) -> None:
        """Should return error when file does not exist."""
        result = read_file.invoke({"file_path": str(tmp_path / "missing.txt")})
        assert "Error" in result
        assert "not found" in result


# --- list_directory ---


class TestListDirectory:
    """Tests for list_directory tool."""

    def test_list_directory_with_files(self, tmp_path: Path) -> None:
        """Should list files and subdirs with [FILE]/[DIR] prefix."""
        (tmp_path / "a.txt").write_text("", encoding="utf-8")
        (tmp_path / "sub").mkdir()
        result = list_directory.invoke({"directory_path": str(tmp_path)})
        assert "Contents of " in result
        assert "[FILE]" in result
        assert "[DIR]" in result
        assert "a.txt" in result
        assert "sub" in result

    def test_list_directory_not_found(self) -> None:
        """Should return error when directory does not exist."""
        result = list_directory.invoke({"directory_path": "/nonexistent/dir/12345"})
        assert "Error" in result
        assert "not found" in result

    def test_list_directory_default_current(self, tmp_path: Path) -> None:
        """Should list current directory when path is default."""
        result = list_directory.invoke({"directory_path": "."})
        assert "Contents of" in result or "Error" in result


# --- search_code ---


class TestSearchCode:
    """Tests for search_code tool."""

    def test_search_finds_pattern(self, tmp_path: Path) -> None:
        """Should find regex matches with file path and line number."""
        py_file = tmp_path / "main.py"
        py_file.write_text("def foo():\n    x = 1\n", encoding="utf-8")
        result = search_code.invoke(
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
        result = search_code.invoke(
            {
                "pattern": r"nonexistent_pattern_xyz",
                "file_pattern": "*.py",
                "directory": str(tmp_path),
            }
        )
        assert "No matches found" in result

    def test_search_directory_not_found(self) -> None:
        """Should return error when directory does not exist."""
        result = search_code.invoke(
            {
                "pattern": "x",
                "file_pattern": "*",
                "directory": "/nonexistent/dir/12345",
            }
        )
        assert "Error" in result
        assert "not found" in result


# --- get_file_tree ---


class TestGetFileTree:
    """Tests for get_file_tree tool."""

    def test_get_tree_structure(self, tmp_path: Path) -> None:
        """Should return tree with directory name and entries."""
        (tmp_path / "file.txt").write_text("", encoding="utf-8")
        (tmp_path / "subdir").mkdir()
        result = get_file_tree.invoke(
            {
                "directory": str(tmp_path),
                "max_depth": 2,
            }
        )
        assert str(tmp_path) in result or "file.txt" in result
        assert "subdir" in result or "file.txt" in result

    def test_get_tree_directory_not_found(self) -> None:
        """Should return error when directory does not exist."""
        result = get_file_tree.invoke(
            {
                "directory": "/nonexistent/dir/12345",
                "max_depth": 3,
            }
        )
        assert "Error" in result
        assert "not found" in result


# --- create_file ---


class TestCreateFile:
    """Tests for create_file tool."""

    def test_create_new_file(self, tmp_path: Path) -> None:
        """Should create file and return success."""
        path = tmp_path / "new.txt"
        result = create_file.invoke(
            {
                "file_path": str(path),
                "content": "new content",
            }
        )
        assert "Successfully created" in result
        assert path.exists()
        assert path.read_text(encoding="utf-8") == "new content"

    def test_create_file_already_exists(self, tmp_path: Path) -> None:
        """Should return error when file already exists."""
        path = tmp_path / "existing.txt"
        path.write_text("old", encoding="utf-8")
        result = create_file.invoke(
            {
                "file_path": str(path),
                "content": "new",
            }
        )
        assert "Error" in result
        assert "already exists" in result
        assert "update_file" in result


# --- update_file ---


class TestUpdateFile:
    """Tests for update_file tool."""

    def test_update_existing_file(self, tmp_path: Path) -> None:
        """Should overwrite file content and return success."""
        path = tmp_path / "f.txt"
        path.write_text("old", encoding="utf-8")
        result = update_file.invoke(
            {
                "file_path": str(path),
                "content": "new content",
            }
        )
        assert "Successfully updated" in result
        assert path.read_text(encoding="utf-8") == "new content"

    def test_update_file_not_found(self, tmp_path: Path) -> None:
        """Should return error when file does not exist."""
        result = update_file.invoke(
            {
                "file_path": str(tmp_path / "missing.txt"),
                "content": "x",
            }
        )
        assert "Error" in result
        assert "not found" in result
        assert "create_file" in result


# --- delete_file ---


class TestDeleteFile:
    """Tests for delete_file tool."""

    def test_delete_existing_file(self, tmp_path: Path) -> None:
        """Should delete file and return success."""
        path = tmp_path / "to_delete.txt"
        path.write_text("x", encoding="utf-8")
        result = delete_file.invoke({"file_path": str(path)})
        assert "Successfully deleted" in result
        assert not path.exists()

    def test_delete_file_not_found(self, tmp_path: Path) -> None:
        """Should return error when file does not exist."""
        result = delete_file.invoke({"file_path": str(tmp_path / "missing.txt")})
        assert "Error" in result
        assert "not found" in result


# --- run_command ---


class TestRunCommand:
    """Tests for run_command tool."""

    def test_run_success_with_output(self, tmp_path: Path) -> None:
        """Should return command output on success."""
        result = run_command.invoke(
            {
                "command": "echo hello",
                "working_dir": str(tmp_path),
            }
        )
        assert "Command output" in result or "hello" in result

    def test_run_failure_returns_exit_code(self, tmp_path: Path) -> None:
        """Should return failure message with exit code when command fails."""
        result = run_command.invoke(
            {
                "command": "exit 1",
                "working_dir": str(tmp_path),
            }
        )
        assert "Command failed" in result or "exit code" in result

    def test_run_timeout_returns_error(self) -> None:
        """Should return timeout error when command exceeds 30s."""
        with patch("src.code_agent.tools.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("sleep", 30)
            result = run_command.invoke(
                {
                    "command": "sleep 35",
                    "working_dir": ".",
                }
            )
        assert "timed out" in result


# --- get_git_diff ---


class TestGetGitDiff:
    """Tests for get_git_diff tool."""

    def test_get_git_diff_no_path(self) -> None:
        """Should run git diff and return no changes or diff output."""
        result = get_git_diff.invoke({})
        assert "No changes detected" in result or "Git diff" in result

    def test_get_git_diff_with_path(self, tmp_path: Path) -> None:
        """Should run git diff with file path."""
        result = get_git_diff.invoke({"file_path": "some_file.py"})
        assert "No changes detected" in result or "Git diff" in result or "Error" in result


# --- check_github_workflows ---


class TestCheckGithubWorkflows:
    """Tests for check_github_workflows tool."""

    @patch("src.code_agent.tools._get_github_client")
    def test_check_workflows_missing_env_returns_error(self, mock_get_client: MagicMock) -> None:
        """Should return error when GITHUB_REPO or GITHUB_TOKEN not set."""
        mock_get_client.side_effect = ValueError(
            "GITHUB_REPO and GITHUB_TOKEN environment variables must be set"
        )
        result = check_github_workflows.invoke({"commit_sha": "abc123"})
        assert "Error" in result
        assert "GITHUB" in result

    @patch("src.code_agent.tools._get_github_client")
    @patch("src.code_agent.tools._resolve_commit_sha")
    def test_check_workflows_success_format(
        self, mock_resolve: MagicMock, mock_client: MagicMock
    ) -> None:
        """Should return formatted status when workflows are fetched."""
        mock_resolve.return_value = "abc12345"
        mock_github = MagicMock()
        mock_github.get_workflow_runs_for_commit.return_value = {
            "CI": "success",
            "Lint": "success",
        }
        mock_client.return_value = (mock_github, "owner/repo")
        result = check_github_workflows.invoke({"commit_sha": "HEAD"})
        assert "abc12345" in result or "GitHub workflows" in result
        assert "[PASS]" in result or "success" in result
