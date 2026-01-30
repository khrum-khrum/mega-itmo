"""Unit tests for src/review_api/service.py."""

from unittest.mock import MagicMock, patch

import pytest

from src.review_agent.agent import ReviewResult
from src.review_api.service import ReviewAgentService


class TestReviewAgentServiceInit:
    """Tests for ReviewAgentService initialization."""

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "OPENROUTER_API_KEY": "test-key"})
    def test_init_with_required_env_vars(self) -> None:
        """Should initialize with required environment variables."""
        service = ReviewAgentService()
        assert service.github_token == "test-token"
        assert service.openrouter_api_key == "test-key"
        assert service.model == "llama-3.3-70b-versatile"  # default
        assert service.repos_dir == "./repos"  # default
        assert service.execute is True  # default

    @patch.dict(
        "os.environ",
        {
            "GITHUB_TOKEN": "test-token",
            "OPENROUTER_API_KEY": "test-key",
            "REVIEW_AGENT_MODEL": "custom-model",
            "REPOS_DIR": "/custom/path",
            "REVIEW_AGENT_EXECUTE": "false",
        },
    )
    def test_init_with_custom_env_vars(self) -> None:
        """Should use custom environment variables when provided."""
        service = ReviewAgentService()
        assert service.model == "custom-model"
        assert service.repos_dir == "/custom/path"
        assert service.execute is False

    @patch.dict(
        "os.environ",
        {
            "GITHUB_TOKEN": "test-token",
            "OPENROUTER_API_KEY": "test-key",
            "REVIEW_AGENT_EXECUTE": "TRUE",
        },
    )
    def test_init_execute_case_insensitive(self) -> None:
        """Should handle REVIEW_AGENT_EXECUTE case-insensitively."""
        service = ReviewAgentService()
        assert service.execute is True

    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}, clear=True)
    def test_init_raises_without_github_token(self) -> None:
        """Should raise ValueError when GITHUB_TOKEN is missing."""
        with pytest.raises(ValueError, match="GITHUB_TOKEN environment variable is required"):
            ReviewAgentService()

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"}, clear=True)
    def test_init_raises_without_openrouter_key(self) -> None:
        """Should raise ValueError when OPENROUTER_API_KEY is missing."""
        with pytest.raises(ValueError, match="OPENROUTER_API_KEY environment variable is required"):
            ReviewAgentService()


class TestInitializeReviewAgent:
    """Tests for _initialize_review_agent helper."""

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "OPENROUTER_API_KEY": "test-key"})
    @patch("src.review_api.service.GitHubClient")
    @patch("src.review_api.service.ReviewAgent")
    def test_initialize_review_agent_creates_client_and_agent(
        self, mock_agent_class: MagicMock, mock_client_class: MagicMock
    ) -> None:
        """Should create GitHubClient and ReviewAgent with correct parameters."""
        service = ReviewAgentService()
        agent = service._initialize_review_agent()

        mock_client_class.assert_called_once_with(
            token="test-token",
            repos_dir="./repos",
        )
        mock_agent_class.assert_called_once_with(
            github_client=mock_client_class.return_value,
            model="llama-3.3-70b-versatile",
            api_key="test-key",
        )
        assert agent == mock_agent_class.return_value


class TestRunReview:
    """Tests for _run_review helper."""

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "OPENROUTER_API_KEY": "test-key"})
    def test_run_review_calls_review_pull_request(self) -> None:
        """Should call agent.review_pull_request with correct parameters."""
        service = ReviewAgentService()
        mock_agent = MagicMock()
        expected_result = ReviewResult(
            success=True,
            review_summary="Looks good",
            comments=[],
            approved=True,
        )
        mock_agent.review_pull_request.return_value = expected_result

        result = service._run_review("owner/repo", 456, mock_agent)

        mock_agent.review_pull_request.assert_called_once_with(
            repo_name="owner/repo",
            pr_number=456,
            verbose=True,
        )
        assert result == expected_result


class TestSubmitOrLogReview:
    """Tests for _submit_or_log_review helper."""

    @patch.dict(
        "os.environ",
        {
            "GITHUB_TOKEN": "test-token",
            "OPENROUTER_API_KEY": "test-key",
            "REVIEW_AGENT_EXECUTE": "true",
        },
    )
    def test_submit_or_log_review_submits_when_execute_enabled(self) -> None:
        """Should call agent.submit_review when execute is True."""
        service = ReviewAgentService()
        mock_agent = MagicMock()
        mock_agent.submit_review.return_value = "https://github.com/owner/repo/pull/456"

        result = ReviewResult(
            success=True,
            review_summary="Good work",
            comments=[],
            approved=True,
        )

        service._submit_or_log_review("owner/repo", 456, mock_agent, result)

        mock_agent.submit_review.assert_called_once_with(
            repo_name="owner/repo",
            pr_number=456,
            review_result=result,
            verbose=True,
        )

    @patch.dict(
        "os.environ",
        {
            "GITHUB_TOKEN": "test-token",
            "OPENROUTER_API_KEY": "test-key",
            "REVIEW_AGENT_EXECUTE": "false",
        },
    )
    def test_submit_or_log_review_logs_when_execute_disabled(self) -> None:
        """Should not submit review when execute is False (dry-run mode)."""
        service = ReviewAgentService()
        mock_agent = MagicMock()

        result = ReviewResult(
            success=True,
            review_summary="Needs work",
            comments=[],
            approved=False,
        )

        service._submit_or_log_review("owner/repo", 456, mock_agent, result)

        mock_agent.submit_review.assert_not_called()


class TestHandlePullRequest:
    """Tests for handle_pull_request main flow."""

    @patch.dict(
        "os.environ",
        {
            "GITHUB_TOKEN": "test-token",
            "OPENROUTER_API_KEY": "test-key",
            "REVIEW_AGENT_EXECUTE": "true",
        },
    )
    @patch.object(ReviewAgentService, "_initialize_review_agent")
    @patch.object(ReviewAgentService, "_run_review")
    @patch.object(ReviewAgentService, "_submit_or_log_review")
    def test_handle_pull_request_success_flow(
        self,
        mock_submit: MagicMock,
        mock_run: MagicMock,
        mock_init: MagicMock,
    ) -> None:
        """Should execute full workflow for successful PR review."""
        mock_agent = MagicMock()
        mock_init.return_value = mock_agent

        result = ReviewResult(
            success=True,
            review_summary="Approved",
            comments=[],
            approved=True,
        )
        mock_run.return_value = result

        service = ReviewAgentService()
        service.handle_pull_request("owner/repo", 456)

        mock_init.assert_called_once()
        mock_run.assert_called_once_with("owner/repo", 456, mock_agent)
        mock_submit.assert_called_once_with("owner/repo", 456, mock_agent, result)
        mock_agent.cleanup.assert_called_once_with(verbose=True)

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "OPENROUTER_API_KEY": "test-key"})
    @patch.object(ReviewAgentService, "_initialize_review_agent")
    @patch.object(ReviewAgentService, "_run_review")
    @patch.object(ReviewAgentService, "_submit_or_log_review")
    def test_handle_pull_request_stops_on_failure(
        self,
        mock_submit: MagicMock,
        mock_run: MagicMock,
        mock_init: MagicMock,
    ) -> None:
        """Should not submit review when review fails."""
        mock_agent = MagicMock()
        mock_init.return_value = mock_agent

        result = ReviewResult(
            success=False,
            review_summary="",
            comments=[],
            approved=False,
            error="Review failed",
        )
        mock_run.return_value = result

        service = ReviewAgentService()
        service.handle_pull_request("owner/repo", 456)

        mock_submit.assert_not_called()
        mock_agent.cleanup.assert_not_called()

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "OPENROUTER_API_KEY": "test-key"})
    @patch.object(ReviewAgentService, "_initialize_review_agent")
    def test_handle_pull_request_catches_exceptions(self, mock_init: MagicMock) -> None:
        """Should catch and log exceptions without crashing."""
        mock_init.side_effect = Exception("Network error")

        service = ReviewAgentService()
        # Should not raise
        service.handle_pull_request("owner/repo", 456)

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "OPENROUTER_API_KEY": "test-key"})
    @patch.object(ReviewAgentService, "_initialize_review_agent")
    @patch.object(ReviewAgentService, "_run_review")
    @patch.object(ReviewAgentService, "_submit_or_log_review")
    def test_handle_pull_request_with_comments(
        self,
        mock_submit: MagicMock,
        mock_run: MagicMock,
        mock_init: MagicMock,
    ) -> None:
        """Should handle review results with comments."""
        mock_agent = MagicMock()
        mock_init.return_value = mock_agent

        result = ReviewResult(
            success=True,
            review_summary="Needs changes",
            comments=["Fix test_foo.py:10", "Update README.md"],
            approved=False,
        )
        mock_run.return_value = result

        service = ReviewAgentService()
        service.handle_pull_request("owner/repo", 456)

        mock_init.assert_called_once()
        mock_run.assert_called_once_with("owner/repo", 456, mock_agent)
        mock_submit.assert_called_once_with("owner/repo", 456, mock_agent, result)
        mock_agent.cleanup.assert_called_once_with(verbose=True)
