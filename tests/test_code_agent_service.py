"""Unit tests for src/api/service.py."""

from unittest.mock import MagicMock, patch

import pytest

from src.api.service import CodeAgentService
from src.code_agent.agent import AgentResult
from src.utils.github_client import IssueData


class TestCodeAgentServiceInit:
    """Tests for CodeAgentService initialization."""

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "OPENROUTER_API_KEY": "test-key"})
    def test_init_with_required_env_vars(self) -> None:
        """Should initialize with required environment variables."""
        service = CodeAgentService()
        assert service.github_token == "test-token"
        assert service.openrouter_api_key == "test-key"
        assert service.model == "llama-3.3-70b-versatile"  # default
        assert service.repos_dir == "./repos"  # default

    @patch.dict(
        "os.environ",
        {
            "GITHUB_TOKEN": "test-token",
            "OPENROUTER_API_KEY": "test-key",
            "CODE_AGENT_MODEL": "custom-model",
            "REPOS_DIR": "/custom/path",
        },
    )
    def test_init_with_custom_env_vars(self) -> None:
        """Should use custom environment variables when provided."""
        service = CodeAgentService()
        assert service.model == "custom-model"
        assert service.repos_dir == "/custom/path"

    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}, clear=True)
    def test_init_raises_without_github_token(self) -> None:
        """Should raise ValueError when GITHUB_TOKEN is missing."""
        with pytest.raises(ValueError, match="GITHUB_TOKEN environment variable is required"):
            CodeAgentService()

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"}, clear=True)
    def test_init_raises_without_openrouter_key(self) -> None:
        """Should raise ValueError when OPENROUTER_API_KEY is missing."""
        with pytest.raises(ValueError, match="OPENROUTER_API_KEY environment variable is required"):
            CodeAgentService()


class TestInitializeAgent:
    """Tests for _initialize_agent helper."""

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "OPENROUTER_API_KEY": "test-key"})
    @patch("src.api.service.GitHubClient")
    @patch("src.api.service.CodeAgent")
    def test_initialize_agent_creates_client_and_agent(
        self, mock_agent_class: MagicMock, mock_client_class: MagicMock
    ) -> None:
        """Should create GitHubClient and CodeAgent with correct parameters."""
        service = CodeAgentService()
        github_client, agent = service._initialize_agent()

        mock_client_class.assert_called_once_with(
            token="test-token",
            repos_dir="./repos",
        )
        mock_agent_class.assert_called_once_with(
            github_client=mock_client_class.return_value,
            model="llama-3.3-70b-versatile",
            api_key="test-key",
        )
        assert github_client == mock_client_class.return_value
        assert agent == mock_agent_class.return_value


class TestRunAgentForIssue:
    """Tests for _run_agent_for_issue helper."""

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "OPENROUTER_API_KEY": "test-key"})
    def test_run_agent_for_issue_calls_analyze_and_solve(self) -> None:
        """Should call agent.analyze_and_solve_issue with correct parameters."""
        service = CodeAgentService()
        mock_agent = MagicMock()
        expected_result = AgentResult(
            success=True,
            output="Done",
            repo_path="/path",
            branch_name="branch",
        )
        mock_agent.analyze_and_solve_issue.return_value = expected_result

        result = service._run_agent_for_issue("owner/repo", 123, mock_agent)

        mock_agent.analyze_and_solve_issue.assert_called_once_with(
            repo_name="owner/repo",
            issue_number=123,
            verbose=True,
        )
        assert result == expected_result


class TestRunAgentForPR:
    """Tests for _run_agent_for_pr helper."""

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "OPENROUTER_API_KEY": "test-key"})
    def test_run_agent_for_pr_calls_with_pr_number(self) -> None:
        """Should call agent.analyze_and_solve_issue with pr_number parameter."""
        service = CodeAgentService()
        mock_agent = MagicMock()
        expected_result = AgentResult(
            success=True,
            output="Updated PR",
            repo_path="/path",
            branch_name="pr-branch",
        )
        mock_agent.analyze_and_solve_issue.return_value = expected_result

        result = service._run_agent_for_pr("owner/repo", 123, 456, mock_agent)

        mock_agent.analyze_and_solve_issue.assert_called_once_with(
            repo_name="owner/repo",
            issue_number=123,
            pr_number=456,
            verbose=True,
        )
        assert result == expected_result


class TestCreateAndPushPR:
    """Tests for _create_and_push_pr helper."""

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "OPENROUTER_API_KEY": "test-key"})
    def test_create_and_push_pr_workflow(self) -> None:
        """Should get issue, commit changes, and create PR."""
        service = CodeAgentService()
        mock_github = MagicMock()
        mock_issue = IssueData(
            number=123,
            title="Test Issue",
            body="Description",
            labels=[],
            state="open",
            url="https://github.com/owner/repo/issues/123",
        )
        mock_github.get_issue.return_value = mock_issue

        mock_agent = MagicMock()
        mock_agent.create_pull_request.return_value = "https://github.com/owner/repo/pull/1"

        result = AgentResult(
            success=True,
            output="Changes made",
            repo_path="/path",
            branch_name="agent/issue-123",
        )

        service._create_and_push_pr("owner/repo", 123, mock_github, mock_agent, result)

        mock_github.get_issue.assert_called_once_with("owner/repo", 123)
        mock_agent.commit_and_push.assert_called_once()
        commit_args = mock_agent.commit_and_push.call_args
        assert "Fix #123: Test Issue" in commit_args[0][1]
        assert "Generated by Code Agent" in commit_args[0][1]
        assert commit_args[1]["verbose"] is True

        mock_agent.create_pull_request.assert_called_once_with(
            repo_name="owner/repo",
            issue_number=123,
            result=result,
            verbose=True,
        )


class TestCommitPRChanges:
    """Tests for _commit_pr_changes helper."""

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "OPENROUTER_API_KEY": "test-key"})
    def test_commit_pr_changes_success(self) -> None:
        """Should commit and push changes for PR update."""
        service = CodeAgentService()
        mock_agent = MagicMock()
        result = AgentResult(
            success=True,
            output="Updated",
            repo_path="/path",
            branch_name="pr-branch",
        )

        service._commit_pr_changes(456, mock_agent, result)

        mock_agent.commit_and_push.assert_called_once()
        commit_args = mock_agent.commit_and_push.call_args
        assert "Address PR #456 feedback" in commit_args[0][1]
        assert "Generated by Code Agent" in commit_args[0][1]

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "OPENROUTER_API_KEY": "test-key"})
    def test_commit_pr_changes_handles_no_changes(self) -> None:
        """Should handle RuntimeError when no changes to commit."""
        service = CodeAgentService()
        mock_agent = MagicMock()
        mock_agent.commit_and_push.side_effect = RuntimeError("No changes to commit")
        result = AgentResult(
            success=True,
            output="No updates",
            repo_path="/path",
            branch_name="pr-branch",
        )

        # Should not raise
        service._commit_pr_changes(456, mock_agent, result)

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "OPENROUTER_API_KEY": "test-key"})
    def test_commit_pr_changes_raises_other_errors(self) -> None:
        """Should raise RuntimeError for errors other than 'No changes to commit'."""
        service = CodeAgentService()
        mock_agent = MagicMock()
        mock_agent.commit_and_push.side_effect = RuntimeError("Permission denied")
        result = AgentResult(
            success=True,
            output="Failed",
            repo_path="/path",
            branch_name="pr-branch",
        )

        with pytest.raises(RuntimeError, match="Permission denied"):
            service._commit_pr_changes(456, mock_agent, result)


class TestHandleIssue:
    """Tests for handle_issue main flow."""

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "OPENROUTER_API_KEY": "test-key"})
    @patch.object(CodeAgentService, "_initialize_agent")
    @patch.object(CodeAgentService, "_run_agent_for_issue")
    @patch.object(CodeAgentService, "_create_and_push_pr")
    def test_handle_issue_success_flow(
        self,
        mock_create_pr: MagicMock,
        mock_run_agent: MagicMock,
        mock_init: MagicMock,
    ) -> None:
        """Should execute full workflow for successful issue resolution."""
        mock_github = MagicMock()
        mock_agent = MagicMock()
        mock_init.return_value = (mock_github, mock_agent)

        result = AgentResult(
            success=True,
            output="Done",
            repo_path="/path",
            branch_name="agent/issue-123",
        )
        mock_run_agent.return_value = result

        service = CodeAgentService()
        service.handle_issue("owner/repo", 123)

        mock_init.assert_called_once()
        mock_run_agent.assert_called_once_with("owner/repo", 123, mock_agent)
        mock_create_pr.assert_called_once_with("owner/repo", 123, mock_github, mock_agent, result)
        mock_agent.cleanup.assert_called_once_with(verbose=True)

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "OPENROUTER_API_KEY": "test-key"})
    @patch.object(CodeAgentService, "_initialize_agent")
    @patch.object(CodeAgentService, "_run_agent_for_issue")
    @patch.object(CodeAgentService, "_create_and_push_pr")
    def test_handle_issue_stops_on_failure(
        self,
        mock_create_pr: MagicMock,
        mock_run_agent: MagicMock,
        mock_init: MagicMock,
    ) -> None:
        """Should not create PR when agent fails."""
        mock_github = MagicMock()
        mock_agent = MagicMock()
        mock_init.return_value = (mock_github, mock_agent)

        result = AgentResult(
            success=False,
            output="",
            repo_path=None,
            branch_name=None,
            error="Agent failed",
        )
        mock_run_agent.return_value = result

        service = CodeAgentService()
        service.handle_issue("owner/repo", 123)

        mock_create_pr.assert_not_called()
        mock_agent.cleanup.assert_not_called()

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "OPENROUTER_API_KEY": "test-key"})
    @patch.object(CodeAgentService, "_initialize_agent")
    def test_handle_issue_catches_exceptions(self, mock_init: MagicMock) -> None:
        """Should catch and log exceptions without crashing."""
        mock_init.side_effect = Exception("Network error")

        service = CodeAgentService()
        # Should not raise
        service.handle_issue("owner/repo", 123)


class TestHandlePRReview:
    """Tests for handle_pr_review main flow."""

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "OPENROUTER_API_KEY": "test-key"})
    @patch.object(CodeAgentService, "_initialize_agent")
    @patch.object(CodeAgentService, "_run_agent_for_pr")
    @patch.object(CodeAgentService, "_commit_pr_changes")
    def test_handle_pr_review_success_flow(
        self,
        mock_commit: MagicMock,
        mock_run_agent: MagicMock,
        mock_init: MagicMock,
    ) -> None:
        """Should execute full workflow for successful PR update."""
        mock_github = MagicMock()
        mock_agent = MagicMock()
        mock_init.return_value = (mock_github, mock_agent)

        result = AgentResult(
            success=True,
            output="Updated",
            repo_path="/path",
            branch_name="pr-branch",
        )
        mock_run_agent.return_value = result

        service = CodeAgentService()
        service.handle_pr_review("owner/repo", 123, 456)

        mock_init.assert_called_once()
        mock_run_agent.assert_called_once_with("owner/repo", 123, 456, mock_agent)
        mock_commit.assert_called_once_with(456, mock_agent, result)
        mock_agent.cleanup.assert_called_once_with(verbose=True)

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "OPENROUTER_API_KEY": "test-key"})
    @patch.object(CodeAgentService, "_initialize_agent")
    @patch.object(CodeAgentService, "_run_agent_for_pr")
    @patch.object(CodeAgentService, "_commit_pr_changes")
    def test_handle_pr_review_stops_on_failure(
        self,
        mock_commit: MagicMock,
        mock_run_agent: MagicMock,
        mock_init: MagicMock,
    ) -> None:
        """Should not commit when agent fails."""
        mock_github = MagicMock()
        mock_agent = MagicMock()
        mock_init.return_value = (mock_github, mock_agent)

        result = AgentResult(
            success=False,
            output="",
            repo_path=None,
            branch_name=None,
            error="Agent failed",
        )
        mock_run_agent.return_value = result

        service = CodeAgentService()
        service.handle_pr_review("owner/repo", 123, 456)

        mock_commit.assert_not_called()
        mock_agent.cleanup.assert_not_called()

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "OPENROUTER_API_KEY": "test-key"})
    @patch.object(CodeAgentService, "_initialize_agent")
    @patch.object(CodeAgentService, "_run_agent_for_pr")
    @patch.object(CodeAgentService, "_commit_pr_changes")
    def test_handle_pr_review_skips_when_no_changes_needed(
        self,
        mock_commit: MagicMock,
        mock_run_agent: MagicMock,
        mock_init: MagicMock,
    ) -> None:
        """Should skip commit when output indicates no changes needed."""
        mock_github = MagicMock()
        mock_agent = MagicMock()
        mock_init.return_value = (mock_github, mock_agent)

        result = AgentResult(
            success=True,
            output="No changes needed - feedback is positive",
            repo_path="/path",
            branch_name="pr-branch",
        )
        mock_run_agent.return_value = result

        service = CodeAgentService()
        service.handle_pr_review("owner/repo", 123, 456)

        mock_commit.assert_not_called()
        mock_agent.cleanup.assert_not_called()

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "OPENROUTER_API_KEY": "test-key"})
    @patch.object(CodeAgentService, "_initialize_agent")
    @patch.object(CodeAgentService, "_run_agent_for_pr")
    @patch.object(CodeAgentService, "_commit_pr_changes")
    def test_handle_pr_review_skips_when_no_repo_path(
        self,
        mock_commit: MagicMock,
        mock_run_agent: MagicMock,
        mock_init: MagicMock,
    ) -> None:
        """Should skip commit when repo_path is None."""
        mock_github = MagicMock()
        mock_agent = MagicMock()
        mock_init.return_value = (mock_github, mock_agent)

        result = AgentResult(
            success=True,
            output="Something",
            repo_path=None,
            branch_name="pr-branch",
        )
        mock_run_agent.return_value = result

        service = CodeAgentService()
        service.handle_pr_review("owner/repo", 123, 456)

        mock_commit.assert_not_called()
        mock_agent.cleanup.assert_not_called()

    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token", "OPENROUTER_API_KEY": "test-key"})
    @patch.object(CodeAgentService, "_initialize_agent")
    def test_handle_pr_review_catches_exceptions(self, mock_init: MagicMock) -> None:
        """Should catch and log exceptions without crashing."""
        mock_init.side_effect = Exception("Network error")

        service = CodeAgentService()
        # Should not raise
        service.handle_pr_review("owner/repo", 123, 456)
