"""Unit tests for src/utils/github_client.py."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from github import (
    BadCredentialsException,
    GithubException,
    UnknownObjectException,
)

from src.utils.github_client import (
    GitHubClient,
    IssueData,
    PRCommentData,
    PRData,
)

# --- Dataclasses ---


class TestIssueData:
    """Tests for IssueData dataclass."""

    def test_str_includes_all_fields(self) -> None:
        """Should format issue with number, title, state, labels, URL and body."""
        issue = IssueData(
            number=42,
            title="Fix bug",
            body="Description here",
            labels=["bug", "urgent"],
            state="open",
            url="https://github.com/owner/repo/issues/42",
        )
        s = str(issue)
        assert "42" in s
        assert "Fix bug" in s
        assert "open" in s
        assert "bug" in s and "urgent" in s
        assert "Description here" in s
        assert "https://github.com/owner/repo/issues/42" in s

    def test_str_empty_body_shows_placeholder(self) -> None:
        """Should show 'No description' when body is empty."""
        issue = IssueData(number=1, title="T", body="", labels=[], state="open", url="https://x")
        assert "No description" in str(issue)


class TestPRCommentData:
    """Tests for PRCommentData dataclass."""

    def test_str_with_path_and_line(self) -> None:
        """Should include file path and line number for review comments."""
        comment = PRCommentData(
            author="alice",
            body="Fix this",
            comment_type="review_comment",
            created_at="2024-01-15T10:00:00",
            path="src/main.py",
            line=42,
        )
        s = str(comment)
        assert "review_comment" in s
        assert "alice" in s
        assert "src/main.py" in s
        assert "42" in s
        assert "Fix this" in s

    def test_str_with_review_state(self) -> None:
        """Should include review state for review-type comments."""
        comment = PRCommentData(
            author="bob",
            body="LGTM",
            comment_type="review",
            created_at="2024-01-15T11:00:00",
            review_state="APPROVED",
        )
        s = str(comment)
        assert "APPROVED" in s
        assert "LGTM" in s


class TestPRData:
    """Tests for PRData dataclass."""

    def test_str_includes_branches_and_comments(self) -> None:
        """Should include PR title, branches, and comment count."""
        comment = PRCommentData(
            author="alice",
            body="Comment",
            comment_type="issue_comment",
            created_at="2024-01-15T10:00:00",
        )
        pr = PRData(
            number=10,
            title="Add feature",
            body="PR body",
            state="open",
            url="https://github.com/owner/repo/pull/10",
            head_branch="feature",
            base_branch="main",
            comments=[comment],
        )
        s = str(pr)
        assert "10" in s
        assert "Add feature" in s
        assert "feature" in s and "main" in s
        assert "Comment" in s

    def test_str_no_comments(self) -> None:
        """Should show 'No comments' when comments list is empty."""
        pr = PRData(
            number=1,
            title="T",
            body="",
            state="open",
            url="https://x",
            head_branch="a",
            base_branch="b",
            comments=[],
        )
        assert "No comments" in str(pr)


# --- GitHubClient ---


class TestGitHubClientInit:
    """Tests for GitHubClient initialization."""

    @patch("src.utils.github_client.Github")
    def test_init_with_token(self, mock_github_class: MagicMock) -> None:
        """Should create client with provided token and default repos_dir."""
        client = GitHubClient(token="test-token")
        assert client.token == "test-token"
        assert client.repos_dir.name == "repos"
        mock_github_class.assert_called_once_with("test-token")

    @patch("src.utils.github_client.Github")
    @patch.dict("os.environ", {"GITHUB_TOKEN": "env-token"})
    def test_init_uses_env_token_when_not_provided(self, mock_github_class: MagicMock) -> None:
        """Should use GITHUB_TOKEN from environment when token not passed."""
        client = GitHubClient()
        assert client.token == "env-token"

    @patch.dict("os.environ", {}, clear=True)
    def test_init_without_token_raises(self) -> None:
        """Should raise ValueError when no token is available."""
        with pytest.raises(ValueError, match="GitHub token not found"):
            GitHubClient()

    @patch("src.utils.github_client.Github")
    def test_init_with_repos_dir(self, mock_github_class: MagicMock, tmp_path: Path) -> None:
        """Should use provided repos_dir."""
        custom_repos = tmp_path / "custom_repos"
        client = GitHubClient(token="test-token", repos_dir=str(custom_repos))
        assert client.repos_dir == custom_repos


class TestGitHubClientGetRepo:
    """Tests for GitHubClient.get_repo."""

    @patch("src.utils.github_client.Github")
    def test_get_repo_success(self, mock_github_class: MagicMock) -> None:
        """Should return repository when it exists."""
        mock_repo = MagicMock()
        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo
        mock_github_class.return_value = mock_client

        client = GitHubClient(token="test-token")
        result = client.get_repo("owner/repo")

        assert result is mock_repo
        mock_client.get_repo.assert_called_once_with("owner/repo")

    @patch("src.utils.github_client.Github")
    def test_get_repo_not_found_raises_runtime_error(self, mock_github_class: MagicMock) -> None:
        """Should raise RuntimeError when repository not found."""
        mock_client = MagicMock()
        mock_client.get_repo.side_effect = UnknownObjectException(404, {"message": "Not Found"})
        mock_github_class.return_value = mock_client

        client = GitHubClient(token="test-token")
        with pytest.raises(RuntimeError, match="not found"):
            client.get_repo("owner/nonexistent")

    @patch("src.utils.github_client.Github")
    def test_get_repo_bad_credentials_raises_runtime_error(
        self, mock_github_class: MagicMock
    ) -> None:
        """Should raise RuntimeError when credentials are invalid."""
        mock_client = MagicMock()
        mock_client.get_repo.side_effect = BadCredentialsException(
            401, {"message": "Bad credentials"}
        )
        mock_github_class.return_value = mock_client

        client = GitHubClient(token="bad-token")
        with pytest.raises(RuntimeError, match="Authentication failed"):
            client.get_repo("owner/repo")

    @patch("src.utils.github_client.Github")
    def test_get_repo_403_raises_access_denied(self, mock_github_class: MagicMock) -> None:
        """Should raise RuntimeError with access denied message on 403."""
        mock_client = MagicMock()
        exc = GithubException(403, {"message": "Forbidden"})
        mock_client.get_repo.side_effect = exc
        mock_github_class.return_value = mock_client

        client = GitHubClient(token="test-token")
        with pytest.raises(RuntimeError, match="Access denied"):
            client.get_repo("owner/repo")

    @patch("src.utils.github_client.Github")
    def test_get_repo_404_raises_not_found(self, mock_github_class: MagicMock) -> None:
        """Should raise RuntimeError when GitHub returns 404."""
        mock_client = MagicMock()
        exc = GithubException(404, {"message": "Not Found"})
        mock_client.get_repo.side_effect = exc
        mock_github_class.return_value = mock_client

        client = GitHubClient(token="test-token")
        with pytest.raises(RuntimeError, match="not found"):
            client.get_repo("owner/repo")


class TestGitHubClientGetIssue:
    """Tests for GitHubClient.get_issue."""

    @patch("src.utils.github_client.Github")
    def test_get_issue_success(self, mock_github_class: MagicMock) -> None:
        """Should return IssueData when issue exists."""
        label_bug = MagicMock()
        label_bug.name = "bug"
        label_urgent = MagicMock()
        label_urgent.name = "urgent"
        mock_issue = MagicMock()
        mock_issue.number = 5
        mock_issue.title = "Bug report"
        mock_issue.body = "Steps to reproduce"
        mock_issue.labels = [label_bug, label_urgent]
        mock_issue.state = "open"
        mock_issue.html_url = "https://github.com/owner/repo/issues/5"

        mock_repo = MagicMock()
        mock_repo.get_issue.return_value = mock_issue
        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo
        mock_github_class.return_value = mock_client

        client = GitHubClient(token="test-token")
        result = client.get_issue("owner/repo", 5)

        assert isinstance(result, IssueData)
        assert result.number == 5
        assert result.title == "Bug report"
        assert result.body == "Steps to reproduce"
        assert result.labels == ["bug", "urgent"]
        assert result.state == "open"

    @patch("src.utils.github_client.Github")
    def test_get_issue_not_found_raises_runtime_error(self, mock_github_class: MagicMock) -> None:
        """Should raise RuntimeError when issue does not exist."""
        mock_repo = MagicMock()
        mock_repo.get_issue.side_effect = UnknownObjectException(404, {})
        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo
        mock_github_class.return_value = mock_client

        client = GitHubClient(token="test-token")
        with pytest.raises(RuntimeError, match="Issue #99 not found"):
            client.get_issue("owner/repo", 99)


class TestGitHubClientGetPullRequest:
    """Tests for GitHubClient.get_pull_request."""

    @patch("src.utils.github_client.Github")
    def test_get_pull_request_success(self, mock_github_class: MagicMock) -> None:
        """Should return PullRequest when PR exists."""
        mock_pr = MagicMock()
        mock_repo = MagicMock()
        mock_repo.get_pull.return_value = mock_pr
        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo
        mock_github_class.return_value = mock_client

        client = GitHubClient(token="test-token")
        result = client.get_pull_request("owner/repo", 7)

        assert result is mock_pr
        mock_repo.get_pull.assert_called_once_with(7)

    @patch("src.utils.github_client.Github")
    def test_get_pull_request_not_found_raises_runtime_error(
        self, mock_github_class: MagicMock
    ) -> None:
        """Should raise RuntimeError when PR does not exist."""
        mock_repo = MagicMock()
        mock_repo.get_pull.side_effect = UnknownObjectException(404, {})
        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo
        mock_github_class.return_value = mock_client

        client = GitHubClient(token="test-token")
        with pytest.raises(RuntimeError, match="Pull Request #100 not found"):
            client.get_pull_request("owner/repo", 100)


class TestGitHubClientGetPRDataWithComments:
    """Tests for GitHubClient.get_pr_data_with_comments."""

    @patch("src.utils.github_client.Github")
    def test_get_pr_data_with_comments_success(self, mock_github_class: MagicMock) -> None:
        """Should return PRData with comments sorted by created_at."""
        from datetime import datetime

        mock_review_comment = MagicMock()
        mock_review_comment.user.login = "alice"
        mock_review_comment.body = "Fix typo"
        mock_review_comment.created_at = datetime(2024, 1, 15, 10, 0, 0)
        mock_review_comment.path = "readme.md"
        mock_review_comment.line = 1

        mock_issue_comment = MagicMock()
        mock_issue_comment.user.login = "bob"
        mock_issue_comment.body = "Looks good"
        mock_issue_comment.created_at = datetime(2024, 1, 15, 11, 0, 0)

        mock_pr = MagicMock()
        mock_pr.number = 3
        mock_pr.title = "Update docs"
        mock_pr.body = "PR body"
        mock_pr.state = "open"
        mock_pr.html_url = "https://github.com/owner/repo/pull/3"
        mock_pr.head.ref = "docs"
        mock_pr.base.ref = "main"
        mock_pr.get_review_comments.return_value = [mock_review_comment]
        mock_pr.get_reviews.return_value = []

        mock_issue = MagicMock()
        mock_issue.get_comments.return_value = [mock_issue_comment]

        mock_repo = MagicMock()
        mock_repo.get_pull.return_value = mock_pr
        mock_repo.get_issue.return_value = mock_issue
        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo
        mock_github_class.return_value = mock_client

        client = GitHubClient(token="test-token")
        result = client.get_pr_data_with_comments("owner/repo", 3)

        assert isinstance(result, PRData)
        assert result.number == 3
        assert result.title == "Update docs"
        assert result.head_branch == "docs"
        assert result.base_branch == "main"
        assert len(result.comments) == 2
        # Sorted by created_at: review_comment first (10:00), then issue_comment (11:00)
        assert result.comments[0].comment_type == "review_comment"
        assert result.comments[0].path == "readme.md"
        assert result.comments[1].comment_type == "issue_comment"


class TestGitHubClientCreatePullRequest:
    """Tests for GitHubClient.create_pull_request."""

    @patch("src.utils.github_client.Github")
    def test_create_pull_request_success(self, mock_github_class: MagicMock) -> None:
        """Should return created PullRequest."""
        mock_pr = MagicMock()
        mock_repo = MagicMock()
        mock_repo.default_branch = "main"
        mock_repo.create_pull.return_value = mock_pr
        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo
        mock_github_class.return_value = mock_client

        client = GitHubClient(token="test-token")
        result = client.create_pull_request(
            repo_name="owner/repo",
            title="New feature",
            body="Description",
            head_branch="feature",
        )

        assert result is mock_pr
        mock_repo.create_pull.assert_called_once_with(
            title="New feature",
            body="Description",
            head="feature",
            base="main",
        )

    @patch("src.utils.github_client.Github")
    def test_create_pull_request_already_exists_raises_runtime_error(
        self, mock_github_class: MagicMock
    ) -> None:
        """Should raise RuntimeError when PR from same branch already exists."""
        mock_repo = MagicMock()
        mock_repo.default_branch = "main"
        exc = GithubException(422, {"message": "A pull request already exists"})
        mock_repo.create_pull.side_effect = exc
        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo
        mock_github_class.return_value = mock_client

        client = GitHubClient(token="test-token")
        with pytest.raises(RuntimeError, match="already exists"):
            client.create_pull_request(
                repo_name="owner/repo",
                title="T",
                body="B",
                head_branch="feature",
            )

    @patch("src.utils.github_client.Github")
    def test_create_pull_request_no_commits_raises_runtime_error(
        self, mock_github_class: MagicMock
    ) -> None:
        """Should raise RuntimeError when there are no commits between branches."""
        mock_repo = MagicMock()
        mock_repo.default_branch = "main"
        exc = GithubException(422, {"message": "No commits between main and feature"})
        mock_repo.create_pull.side_effect = exc
        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo
        mock_github_class.return_value = mock_client

        client = GitHubClient(token="test-token")
        with pytest.raises(RuntimeError, match="No changes between"):
            client.create_pull_request(
                repo_name="owner/repo",
                title="T",
                body="B",
                head_branch="feature",
            )


class TestGitHubClientGetWorkflowRunsForCommit:
    """Tests for GitHubClient.get_workflow_runs_for_commit."""

    @patch("src.utils.github_client.Github")
    def test_get_workflow_runs_empty(self, mock_github_class: MagicMock) -> None:
        """Should return empty dict when no workflow runs for commit."""
        mock_runs = MagicMock()
        mock_runs.totalCount = 0
        mock_runs.__iter__ = lambda self: iter([])
        mock_repo = MagicMock()
        mock_repo.get_workflow_runs.return_value = mock_runs
        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo
        mock_github_class.return_value = mock_client

        client = GitHubClient(token="test-token")
        result = client.get_workflow_runs_for_commit("owner/repo", "abc123")

        assert result == {}
        mock_repo.get_workflow_runs.assert_called_once_with(head_sha="abc123")

    @patch("src.utils.github_client.Github")
    def test_get_workflow_runs_with_runs(self, mock_github_class: MagicMock) -> None:
        """Should return map of workflow name to status."""
        mock_run1 = MagicMock()
        mock_run1.name = "CI"
        mock_run1.status = "completed"
        mock_run1.conclusion = "success"
        mock_run2 = MagicMock()
        mock_run2.name = "Lint"
        mock_run2.status = "completed"
        mock_run2.conclusion = "failure"
        mock_runs = MagicMock()
        mock_runs.totalCount = 2
        mock_runs.__iter__ = lambda self: iter([mock_run1, mock_run2])
        mock_repo = MagicMock()
        mock_repo.get_workflow_runs.return_value = mock_runs
        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo
        mock_github_class.return_value = mock_client

        client = GitHubClient(token="test-token")
        result = client.get_workflow_runs_for_commit("owner/repo", "abc123")

        assert result == {"CI": "success", "Lint": "failure"}

    @patch("src.utils.github_client.Github")
    def test_get_workflow_runs_pending_uses_status(self, mock_github_class: MagicMock) -> None:
        """Should use status when run is not yet completed."""
        mock_run = MagicMock()
        mock_run.name = "CI"
        mock_run.status = "in_progress"
        mock_run.conclusion = None
        mock_runs = MagicMock()
        mock_runs.totalCount = 1
        mock_runs.__iter__ = lambda self: iter([mock_run])
        mock_repo = MagicMock()
        mock_repo.get_workflow_runs.return_value = mock_runs
        mock_client = MagicMock()
        mock_client.get_repo.return_value = mock_repo
        mock_github_class.return_value = mock_client

        client = GitHubClient(token="test-token")
        result = client.get_workflow_runs_for_commit("owner/repo", "abc123")

        assert result == {"CI": "in_progress"}
