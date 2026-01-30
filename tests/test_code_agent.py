"""Unit tests for src/code_agent/agent.py."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.code_agent.agent import (
    AgentResult,
    CodeAgent,
)
from src.utils.github_client import (
    IssueData,
    PRCommentData,
    PRData,
)

# --- AgentResult ---


class TestAgentResult:
    """Tests for AgentResult dataclass."""

    def test_success_result(self) -> None:
        """Should create success result with expected fields."""
        result = AgentResult(
            success=True,
            output="Done",
            repo_path="/path/to/repo",
            branch_name="agent/issue-1",
        )
        assert result.success is True
        assert result.output == "Done"
        assert result.repo_path == "/path/to/repo"
        assert result.branch_name == "agent/issue-1"
        assert result.error is None

    def test_failure_result_with_error(self) -> None:
        """Should create failure result with error message."""
        result = AgentResult(
            success=False,
            output="",
            repo_path="",
            branch_name="",
            error="GitHub API error",
        )
        assert result.success is False
        assert result.error == "GitHub API error"


# --- CodeAgent Init ---


class TestCodeAgentInit:
    """Tests for CodeAgent initialization."""

    def test_init_defaults(self) -> None:
        """Should initialize with default model and no langchain agent."""
        github = MagicMock()
        agent = CodeAgent(github_client=github)
        assert agent.github is github
        assert agent.model == "llama-3.3-70b-versatile"
        assert agent.api_key is None
        assert agent.langchain_agent is None
        assert agent.repo_path is None

    def test_init_with_custom_params(self) -> None:
        """Should accept custom model and api_key."""
        github = MagicMock()
        agent = CodeAgent(
            github_client=github,
            model="anthropic/claude-3.5-sonnet",
            api_key="test-key",
        )
        assert agent.model == "anthropic/claude-3.5-sonnet"
        assert agent.api_key == "test-key"


# --- PR Feedback Logic ---


class TestShouldProcessPRFeedback:
    """Tests for _should_process_pr_feedback logic."""

    def test_no_comments_returns_false(self) -> None:
        """Should return False when PR has no comments."""
        github = MagicMock()
        agent = CodeAgent(github_client=github)
        pr_data = PRData(
            number=1,
            title="PR",
            body="",
            state="open",
            url="https://x",
            head_branch="a",
            base_branch="b",
            comments=[],
        )
        assert agent._should_process_pr_feedback(pr_data) is False

    def test_changes_requested_returns_true(self) -> None:
        """Should return True when any review has CHANGES_REQUESTED."""
        github = MagicMock()
        agent = CodeAgent(github_client=github)
        comment = PRCommentData(
            author="reviewer",
            body="Looks good",
            comment_type="review",
            created_at="2024-01-15T10:00:00",
            review_state="CHANGES_REQUESTED",
        )
        pr_data = PRData(
            number=1,
            title="PR",
            body="",
            state="open",
            url="https://x",
            head_branch="a",
            base_branch="b",
            comments=[comment],
        )
        assert agent._should_process_pr_feedback(pr_data) is True

    def test_negative_keywords_returns_true(self) -> None:
        """Should return True when comment contains negative keywords."""
        github = MagicMock()
        agent = CodeAgent(github_client=github)
        comment = PRCommentData(
            author="reviewer",
            body="Please fix the bug in this function",
            comment_type="issue_comment",
            created_at="2024-01-15T10:00:00",
        )
        pr_data = PRData(
            number=1,
            title="PR",
            body="",
            state="open",
            url="https://x",
            head_branch="a",
            base_branch="b",
            comments=[comment],
        )
        assert agent._should_process_pr_feedback(pr_data) is True

    def test_approved_only_returns_false(self) -> None:
        """Should return False when review is APPROVED and no negative feedback."""
        github = MagicMock()
        agent = CodeAgent(github_client=github)
        comment = PRCommentData(
            author="reviewer",
            body="LGTM, looks good!",
            comment_type="review",
            created_at="2024-01-15T10:00:00",
            review_state="APPROVED",
        )
        pr_data = PRData(
            number=1,
            title="PR",
            body="",
            state="open",
            url="https://x",
            head_branch="a",
            base_branch="b",
            comments=[comment],
        )
        assert agent._should_process_pr_feedback(pr_data) is False

    def test_positive_only_returns_false(self) -> None:
        """Should return False when comments have only positive feedback."""
        github = MagicMock()
        agent = CodeAgent(github_client=github)
        comment = PRCommentData(
            author="reviewer",
            body="Great job, well done!",
            comment_type="issue_comment",
            created_at="2024-01-15T10:00:00",
        )
        pr_data = PRData(
            number=1,
            title="PR",
            body="",
            state="open",
            url="https://x",
            head_branch="a",
            base_branch="b",
            comments=[comment],
        )
        assert agent._should_process_pr_feedback(pr_data) is False

    def test_unclear_feedback_returns_true(self) -> None:
        """Should return True (process) when feedback is unclear."""
        github = MagicMock()
        agent = CodeAgent(github_client=github)
        comment = PRCommentData(
            author="reviewer",
            body="Just a neutral note about the architecture",
            comment_type="issue_comment",
            created_at="2024-01-15T10:00:00",
        )
        pr_data = PRData(
            number=1,
            title="PR",
            body="",
            state="open",
            url="https://x",
            head_branch="a",
            base_branch="b",
            comments=[comment],
        )
        assert agent._should_process_pr_feedback(pr_data) is True


# --- Prompt Building ---


class TestBuildIssuePrompt:
    """Tests for prompt building methods."""

    def test_build_issue_header(self) -> None:
        """Should build issue header with all fields."""
        github = MagicMock()
        agent = CodeAgent(github_client=github)
        issue = IssueData(
            number=42,
            title="Fix bug",
            body="Description",
            labels=["bug"],
            state="open",
            url="https://github.com/owner/repo/issues/42",
        )
        header = agent._build_issue_header(issue, "owner/repo")
        assert "owner/repo" in header
        assert "42" in header
        assert "Fix bug" in header
        assert "open" in header
        assert "bug" in header
        assert "Description" in header

    def test_build_issue_prompt_new_issue(self) -> None:
        """Should include issue instructions when no PR data."""
        github = MagicMock()
        agent = CodeAgent(github_client=github)
        issue = IssueData(
            number=1,
            title="Task",
            body="Do something",
            labels=[],
            state="open",
            url="https://x",
        )
        prompt = agent._build_issue_prompt(issue, "owner/repo", pr_data=None)
        assert "Analyze this issue" in prompt
        assert "Existing Pull Request" not in prompt
        assert "WORKFLOW:" in prompt

    def test_build_issue_prompt_with_pr(self) -> None:
        """Should include PR feedback section when PR data provided."""
        github = MagicMock()
        agent = CodeAgent(github_client=github)
        issue = IssueData(
            number=1,
            title="Task",
            body="Do something",
            labels=[],
            state="open",
            url="https://x",
        )
        pr_data = PRData(
            number=5,
            title="PR title",
            body="PR body",
            state="open",
            url="https://x",
            head_branch="agent/issue-1",
            base_branch="main",
            comments=[],
        )
        prompt = agent._build_issue_prompt(issue, "owner/repo", pr_data=pr_data)
        assert "Existing Pull Request" in prompt
        assert "PR title" in prompt
        assert "agent/issue-1" in prompt
        assert "Review the feedback" in prompt


# --- Commit and Push ---


class TestCommitAndPush:
    """Tests for commit_and_push method."""

    def test_raises_on_failed_result(self) -> None:
        """Should raise RuntimeError when result is not successful."""
        github = MagicMock()
        agent = CodeAgent(github_client=github)
        result = AgentResult(
            success=False,
            output="",
            repo_path="",
            branch_name="",
            error="Previous error",
        )
        with pytest.raises(RuntimeError, match="Cannot commit failed execution"):
            agent.commit_and_push(result, "Fix bug")

    def test_calls_github_commit_and_push(self) -> None:
        """Should call github client with correct params."""
        github = MagicMock()
        github.commit_and_push_changes.return_value = True
        agent = CodeAgent(github_client=github)
        result = AgentResult(
            success=True,
            output="Done",
            repo_path="/path/to/repo",
            branch_name="agent/issue-1",
        )
        agent.commit_and_push(result, "Fix bug")
        github.commit_and_push_changes.assert_called_once_with(
            repo_path="/path/to/repo",
            branch_name="agent/issue-1",
            commit_message="Fix bug",
        )

    def test_raises_on_github_error(self) -> None:
        """Should raise RuntimeError when github commit fails."""
        github = MagicMock()
        github.commit_and_push_changes.side_effect = Exception("Push failed")
        agent = CodeAgent(github_client=github)
        result = AgentResult(
            success=True,
            output="Done",
            repo_path="/path",
            branch_name="agent/issue-1",
        )
        with pytest.raises(RuntimeError, match="Failed to commit and push"):
            agent.commit_and_push(result, "Fix bug")


# --- Create Pull Request ---


class TestCreatePullRequest:
    """Tests for create_pull_request method."""

    def test_raises_on_failed_result(self) -> None:
        """Should raise RuntimeError when result is not successful."""
        github = MagicMock()
        agent = CodeAgent(github_client=github)
        result = AgentResult(
            success=False,
            output="",
            repo_path="",
            branch_name="",
            error="Previous error",
        )
        with pytest.raises(RuntimeError, match="Cannot create PR for failed execution"):
            agent.create_pull_request("owner/repo", 1, result)

    def test_creates_pr_with_correct_format(self) -> None:
        """Should create PR with proper title, body, and branch."""
        mock_pr = MagicMock()
        mock_pr.html_url = "https://github.com/owner/repo/pull/123"
        github = MagicMock()
        github.get_issue.return_value = MagicMock(
            title="Fix bug",
            url="https://github.com/owner/repo/issues/1",
        )
        github.create_pull_request.return_value = mock_pr
        agent = CodeAgent(github_client=github)
        result = AgentResult(
            success=True,
            output="Implemented the fix",
            repo_path="/path",
            branch_name="agent/issue-1",
        )
        url = agent.create_pull_request("owner/repo", 1, result)
        assert url == "https://github.com/owner/repo/pull/123"
        github.create_pull_request.assert_called_once()
        call_kwargs = github.create_pull_request.call_args[1]
        assert "[Agent] Fix #1: Fix bug" in call_kwargs["title"]
        assert "Closes #1" in call_kwargs["body"]
        assert "Implemented the fix" in call_kwargs["body"]
        assert call_kwargs["head_branch"] == "agent/issue-1"

    def test_raises_on_github_error(self) -> None:
        """Should raise RuntimeError when github PR creation fails."""
        github = MagicMock()
        github.get_issue.return_value = MagicMock(title="T", url="https://x")
        github.create_pull_request.side_effect = Exception("API error")
        agent = CodeAgent(github_client=github)
        result = AgentResult(
            success=True,
            output="Done",
            repo_path="/path",
            branch_name="agent/issue-1",
        )
        with pytest.raises(RuntimeError, match="Failed to create Pull Request"):
            agent.create_pull_request("owner/repo", 1, result)


# --- Cleanup ---


class TestCleanup:
    """Tests for cleanup method."""

    def test_cleanup_clears_repo_path(self) -> None:
        """Should set repo_path to None."""
        github = MagicMock()
        agent = CodeAgent(github_client=github)
        agent.repo_path = "/path/to/repo"
        agent.cleanup()
        assert agent.repo_path is None


# --- analyze_and_solve_issue ---


class TestAnalyzeAndSolveIssue:
    """Tests for main analyze_and_solve_issue flow."""

    @patch("src.code_agent.agent.LangChainAgent")
    def test_full_flow_new_issue_success(
        self, mock_langchain_class: MagicMock, tmp_path: Path
    ) -> None:
        """Should complete full flow for new issue and return success."""
        repo_path = str(tmp_path / "repo")
        Path(repo_path).mkdir(parents=True)

        github = MagicMock()
        github.get_issue.return_value = IssueData(
            number=1,
            title="Fix bug",
            body="Fix the bug",
            labels=[],
            state="open",
            url="https://x",
        )
        github.get_pr_data_with_comments.return_value = None
        github.clone_repository.return_value = repo_path

        mock_llm_agent = MagicMock()
        mock_llm_agent.run.return_value = {"output": "Fixed the bug"}
        mock_langchain_class.return_value = mock_llm_agent

        agent = CodeAgent(github_client=github, api_key="test-key")
        result = agent.analyze_and_solve_issue("owner/repo", 1, pr_number=None)

        assert result.success is True
        assert result.output == "Fixed the bug"
        assert result.repo_path == repo_path
        assert result.branch_name == "agent/issue-1"
        assert result.error is None
        github.get_issue.assert_called_once_with("owner/repo", 1)
        github.clone_repository.assert_called_once_with("owner/repo")
        mock_llm_agent.run.assert_called_once()

    def test_early_exit_when_pr_feedback_positive(self) -> None:
        """Should return early with success when PR feedback is all positive."""
        github = MagicMock()
        issue = IssueData(
            number=1,
            title="Task",
            body="Do it",
            labels=[],
            state="open",
            url="https://x",
        )
        github.get_issue.return_value = issue
        pr_data = PRData(
            number=5,
            title="PR",
            body="",
            state="open",
            url="https://x",
            head_branch="agent/issue-1",
            base_branch="main",
            comments=[
                PRCommentData(
                    author="reviewer",
                    body="LGTM, great job!",
                    comment_type="review",
                    created_at="2024-01-15T10:00:00",
                    review_state="APPROVED",
                )
            ],
        )
        github.get_pr_data_with_comments.return_value = pr_data

        agent = CodeAgent(github_client=github)
        result = agent.analyze_and_solve_issue("owner/repo", 1, pr_number=5)

        assert result.success is True
        assert "No changes needed" in result.output
        assert result.branch_name == "agent/issue-1"
        github.clone_repository.assert_not_called()

    def test_returns_error_result_on_exception(self) -> None:
        """Should return AgentResult with error when exception occurs."""
        github = MagicMock()
        github.get_issue.side_effect = RuntimeError("GitHub API down")
        agent = CodeAgent(github_client=github)

        result = agent.analyze_and_solve_issue("owner/repo", 1)

        assert result.success is False
        assert result.output == ""
        assert result.error == "GitHub API down"

    @patch("src.code_agent.agent.LangChainAgent")
    def test_full_flow_with_existing_pr(
        self, mock_langchain_class: MagicMock, tmp_path: Path
    ) -> None:
        """Should use PR branch when working on existing PR."""
        repo_path = str(tmp_path / "repo")
        Path(repo_path).mkdir(parents=True)

        github = MagicMock()
        issue = IssueData(
            number=1,
            title="Task",
            body="Do it",
            labels=[],
            state="open",
            url="https://x",
        )
        pr_data = PRData(
            number=5,
            title="PR",
            body="",
            state="open",
            url="https://x",
            head_branch="agent/issue-1",
            base_branch="main",
            comments=[
                PRCommentData(
                    author="r",
                    body="Please fix this bug",
                    comment_type="issue_comment",
                    created_at="2024-01-15T10:00:00",
                )
            ],
        )
        github.get_issue.return_value = issue
        github.get_pr_data_with_comments.return_value = pr_data
        github.clone_repository.return_value = repo_path

        mock_llm_agent = MagicMock()
        mock_llm_agent.run.return_value = {"output": "Fixed"}
        mock_langchain_class.return_value = mock_llm_agent

        agent = CodeAgent(github_client=github, api_key="test-key")
        result = agent.analyze_and_solve_issue("owner/repo", 1, pr_number=5)

        assert result.success is True
        assert result.branch_name == "agent/issue-1"
        github.clone_repository.assert_called_once_with("owner/repo", branch="agent/issue-1")


# --- Context Manager ---


class TestCodeAgentContextManager:
    """Tests for context manager protocol."""

    def test_context_manager_cleanup_on_exit(self) -> None:
        """Should call cleanup on context exit."""
        github = MagicMock()
        agent = CodeAgent(github_client=github)
        agent.repo_path = "/path"
        with agent:
            assert agent.repo_path == "/path"
        assert agent.repo_path is None
