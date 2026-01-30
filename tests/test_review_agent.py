"""Unit tests for src/review_agent/agent.py."""

from unittest.mock import MagicMock, patch

import pytest

from src.review_agent.agent import (
    PRData,
    ReviewAgent,
    ReviewResult,
)
from src.utils.github_client import IssueData

# --- PRData ---


class TestPRData:
    """Tests for PRData dataclass."""

    def test_pr_data_fields(self) -> None:
        """Should hold all PR fields."""
        pr = PRData(
            number=42,
            title="Fix bug",
            body="Closes #1",
            state="open",
            url="https://github.com/o/r/pull/42",
            issue_number=1,
            changed_files=["src/foo.py", "tests/test_foo.py"],
            diff="--- a/src/foo.py\n+++ b/src/foo.py",
            commits_count=2,
            additions=10,
            deletions=3,
            head_branch="feature/foo",
            base_branch="main",
        )
        assert pr.number == 42
        assert pr.title == "Fix bug"
        assert pr.issue_number == 1
        assert pr.changed_files == ["src/foo.py", "tests/test_foo.py"]
        assert pr.head_branch == "feature/foo"
        assert pr.base_branch == "main"


# --- ReviewResult ---


class TestReviewResult:
    """Tests for ReviewResult dataclass."""

    def test_success_result(self) -> None:
        """Should create success result with approved flag."""
        result = ReviewResult(
            success=True,
            review_summary="Looks good",
            comments=[],
            approved=True,
        )
        assert result.success is True
        assert result.approved is True
        assert result.error is None

    def test_failure_result_with_error(self) -> None:
        """Should create failure result with error message."""
        result = ReviewResult(
            success=False,
            review_summary="",
            comments=[],
            approved=False,
            error="API error",
        )
        assert result.success is False
        assert result.error == "API error"


# --- ReviewAgent Init ---


class TestReviewAgentInit:
    """Tests for ReviewAgent initialization."""

    def test_init_defaults(self) -> None:
        """Should initialize with default model and no langchain agent."""
        github = MagicMock()
        agent = ReviewAgent(github_client=github)
        assert agent.github is github
        assert agent.model == "llama-3.3-70b-versatile"
        assert agent.api_key is None
        assert agent.langchain_agent is None
        assert agent.repo_path is None

    def test_init_with_custom_params(self) -> None:
        """Should accept custom model and api_key."""
        github = MagicMock()
        agent = ReviewAgent(
            github_client=github,
            model="anthropic/claude-3.5-sonnet",
            api_key="test-key",
        )
        assert agent.model == "anthropic/claude-3.5-sonnet"
        assert agent.api_key == "test-key"


# --- _extract_issue_from_pr ---


class TestExtractIssueFromPR:
    """Tests for _extract_issue_from_pr."""

    def test_no_body_returns_none(self) -> None:
        """Should return None when PR has no body."""
        github = MagicMock()
        agent = ReviewAgent(github_client=github)
        pr = MagicMock()
        pr.body = None
        issue_number, issue_details = agent._extract_issue_from_pr("owner/repo", pr)
        assert issue_number is None
        assert issue_details is None
        github.get_issue.assert_not_called()

    def test_body_without_hash_returns_none(self) -> None:
        """Should return None when body has no #number."""
        github = MagicMock()
        agent = ReviewAgent(github_client=github)
        pr = MagicMock()
        pr.body = "Just a description"
        issue_number, issue_details = agent._extract_issue_from_pr("owner/repo", pr)
        assert issue_number is None
        assert issue_details is None
        github.get_issue.assert_not_called()

    def test_body_with_issue_number_fetches_issue(self) -> None:
        """Should extract issue number and fetch issue details."""
        github = MagicMock()
        github.get_issue.return_value = IssueData(
            number=5,
            title="Add feature",
            body="Do something",
            labels=["enhancement"],
            state="open",
            url="https://github.com/owner/repo/issues/5",
        )
        agent = ReviewAgent(github_client=github)
        pr = MagicMock()
        pr.body = "Closes #5"
        issue_number, issue_details = agent._extract_issue_from_pr("owner/repo", pr)
        assert issue_number == 5
        assert issue_details is not None
        assert "Issue #5" in issue_details
        assert "Add feature" in issue_details
        assert "Do something" in issue_details
        github.get_issue.assert_called_once_with("owner/repo", 5)

    def test_issue_fetch_failure_returns_error_message(self) -> None:
        """Should return error message when get_issue fails."""
        github = MagicMock()
        github.get_issue.side_effect = Exception("Not found")
        agent = ReviewAgent(github_client=github)
        pr = MagicMock()
        pr.body = "Fixes #99"
        issue_number, issue_details = agent._extract_issue_from_pr("owner/repo", pr)
        assert issue_number == 99
        assert issue_details is not None
        assert "Failed to fetch issue #99" in issue_details
        assert "Not found" in issue_details


# --- _collect_pr_changes ---


class TestCollectPRChanges:
    """Tests for _collect_pr_changes."""

    def test_empty_files(self) -> None:
        """Should return empty lists when no files changed."""
        github = MagicMock()
        agent = ReviewAgent(github_client=github)
        pr = MagicMock()
        pr.get_files.return_value = []
        changed_files, diff = agent._collect_pr_changes(pr)
        assert changed_files == []
        assert diff == ""

    def test_collects_files_and_diff(self) -> None:
        """Should collect filenames and patch content."""
        github = MagicMock()
        agent = ReviewAgent(github_client=github)
        f1 = MagicMock()
        f1.filename = "src/a.py"
        f1.patch = "+line1\n+line2"
        f2 = MagicMock()
        f2.filename = "tests/test_a.py"
        f2.patch = None
        pr = MagicMock()
        pr.get_files.return_value = [f1, f2]
        changed_files, diff = agent._collect_pr_changes(pr)
        assert changed_files == ["src/a.py", "tests/test_a.py"]
        assert "--- src/a.py" in diff
        assert "+line1" in diff
        assert "tests/test_a.py" not in diff  # no patch


# --- Prompt building ---


class TestBuildReviewPrompt:
    """Tests for prompt building: pr_header, issue_section, changes_summary, review_prompt."""

    def test_build_pr_header(self) -> None:
        """Should include PR number, title, state, branches, URL."""
        github = MagicMock()
        agent = ReviewAgent(github_client=github)
        pr_data = PRData(
            number=10,
            title="Fix bug",
            body="Description",
            state="open",
            url="https://github.com/o/r/pull/10",
            issue_number=1,
            changed_files=[],
            diff="",
            commits_count=1,
            additions=5,
            deletions=2,
            head_branch="fix/bug",
            base_branch="main",
        )
        header = agent._build_pr_header(pr_data)
        assert "PR #: 10" in header or "10" in header
        assert "Fix bug" in header
        assert "open" in header
        assert "fix/bug" in header
        assert "main" in header
        assert "Description" in header

    def test_build_issue_section_empty_when_no_issue(self) -> None:
        """Should return empty string when no issue details."""
        github = MagicMock()
        agent = ReviewAgent(github_client=github)
        assert agent._build_issue_section(None) == ""
        assert agent._build_issue_section("") == ""

    def test_build_issue_section_includes_details(self) -> None:
        """Should include issue details and verification note."""
        github = MagicMock()
        agent = ReviewAgent(github_client=github)
        details = "**Issue #1:** Fix bug\n\n**Description:** Do X"
        section = agent._build_issue_section(details)
        assert "Related Issue" in section
        assert "Fix bug" in section
        assert "CRITICAL" in section
        assert "Do X" in section

    def test_build_changes_summary(self) -> None:
        """Should include commits, file count, additions, deletions, file list, diff."""
        github = MagicMock()
        agent = ReviewAgent(github_client=github)
        pr_data = PRData(
            number=1,
            title="T",
            body="",
            state="open",
            url="https://x",
            issue_number=None,
            changed_files=["a.py", "b.py"],
            diff="--- a.py\n+change",
            commits_count=3,
            additions=20,
            deletions=5,
            head_branch="feat",
            base_branch="main",
        )
        summary = agent._build_changes_summary(pr_data)
        assert "3" in summary
        assert "2" in summary or "a.py" in summary
        assert "+20" in summary
        assert "-5" in summary
        assert "a.py" in summary
        assert "b.py" in summary
        assert "--- a.py" in summary

    def test_build_review_prompt_combines_sections(self) -> None:
        """Should combine header, issue (if any), changes, and instructions."""
        github = MagicMock()
        agent = ReviewAgent(github_client=github)
        pr_data = PRData(
            number=1,
            title="PR",
            body="Body",
            state="open",
            url="https://x",
            issue_number=1,
            changed_files=["x.py"],
            diff="",
            commits_count=1,
            additions=0,
            deletions=0,
            head_branch="main",
            base_branch="main",
        )
        prompt = agent._build_review_prompt(pr_data, "Issue details")
        assert "Pull Request" in prompt
        assert "PR" in prompt
        assert "Issue details" in prompt
        assert "x.py" in prompt
        assert "Your task" in prompt or "Review" in prompt
        assert "ASSESSMENT" in prompt or "READY TO MERGE" in prompt


# --- _parse_review_output, _extract_section, _build_summary_parts ---


class TestParseReviewOutput:
    """Tests for review output parsing."""

    def test_parse_ready_to_merge_sets_approved(self) -> None:
        """Should set approved=True when output contains READY TO MERGE."""
        github = MagicMock()
        agent = ReviewAgent(github_client=github)
        output = "**ASSESSMENT:** READY TO MERGE\n\n**SUMMARY:** All good."
        result = agent._parse_review_output(output)
        assert result.success is True
        assert result.approved is True

    def test_parse_needs_changes_sets_not_approved(self) -> None:
        """Should set approved=False when output contains NEEDS CHANGES."""
        github = MagicMock()
        agent = ReviewAgent(github_client=github)
        output = "**ASSESSMENT:** NEEDS CHANGES\n\n**SUMMARY:** Fix tests."
        result = agent._parse_review_output(output)
        assert result.success is True
        assert result.approved is False

    def test_parse_extracts_summary_parts(self) -> None:
        """Should extract ISSUE VERIFICATION, TESTS, SUMMARY, COMMENTS into review_summary."""
        github = MagicMock()
        agent = ReviewAgent(github_client=github)
        output = """**ASSESSMENT:** NEEDS CHANGES

**ISSUE VERIFICATION:**
Done.

**TESTS:**
Passed.

**GITHUB WORKFLOWS:**
OK.

**SUMMARY:**
Overall fine.

**COMMENTS:**
None.
"""
        result = agent._parse_review_output(output)
        assert "Done" in result.review_summary or "Issue" in result.review_summary
        assert "Passed" in result.review_summary or "Tests" in result.review_summary
        assert "Overall fine" in result.review_summary or "Summary" in result.review_summary

    def test_extract_section_missing_returns_empty(self) -> None:
        """_extract_section should return empty when marker absent."""
        github = MagicMock()
        agent = ReviewAgent(github_client=github)
        assert agent._extract_section("No sections here", "**TESTS:**") == ""

    def test_extract_section_returns_content_after_marker(self) -> None:
        """_extract_section should return content after marker until next **."""
        github = MagicMock()
        agent = ReviewAgent(github_client=github)
        text = "Preamble **TESTS:** pytest passed. **SUMMARY:** Done."
        content = agent._extract_section(text, "**TESTS:**")
        assert "pytest passed" in content


# --- _format_review_body ---


class TestFormatReviewBody:
    """Tests for _format_review_body."""

    def test_format_approved_includes_prefix(self) -> None:
        """Should include [APPROVED] when approved."""
        github = MagicMock()
        agent = ReviewAgent(github_client=github)
        result = ReviewResult(
            success=True,
            review_summary="Summary text",
            comments=[],
            approved=True,
        )
        body = agent._format_review_body(result)
        assert "[APPROVED]" in body
        assert "Summary text" in body
        assert "Review Agent" in body or "LangChain" in body

    def test_format_not_approved_includes_review_prefix(self) -> None:
        """Should include [REVIEW] when not approved."""
        github = MagicMock()
        agent = ReviewAgent(github_client=github)
        result = ReviewResult(
            success=True,
            review_summary="Issues found",
            comments=[],
            approved=False,
        )
        body = agent._format_review_body(result)
        assert "[REVIEW]" in body
        assert "Issues found" in body


# --- submit_review ---


class TestSubmitReview:
    """Tests for submit_review."""

    def test_submit_raises_on_failed_review(self) -> None:
        """Should raise RuntimeError when review_result.success is False."""
        github = MagicMock()
        agent = ReviewAgent(github_client=github)
        result = ReviewResult(
            success=False,
            review_summary="",
            comments=[],
            approved=False,
            error="Previous error",
        )
        with pytest.raises(RuntimeError, match="Cannot submit failed review"):
            agent.submit_review("owner/repo", 1, result)

    def test_submit_creates_review_with_comment_event(self) -> None:
        """Should call create_review with COMMENT event and formatted body."""
        mock_pr = MagicMock()
        mock_pr.create_review.return_value = MagicMock(html_url="https://github.com/o/r/pull/1")
        github = MagicMock()
        github.get_pull_request.return_value = mock_pr
        agent = ReviewAgent(github_client=github)
        result = ReviewResult(
            success=True,
            review_summary="Summary",
            comments=[],
            approved=False,
        )
        url = agent.submit_review("owner/repo", 1, result)
        assert url == "https://github.com/o/r/pull/1"
        mock_pr.create_review.assert_called_once()
        call_kwargs = mock_pr.create_review.call_args[1]
        assert call_kwargs["event"] == "COMMENT"
        assert "Summary" in call_kwargs["body"]

    def test_submit_raises_on_github_error(self) -> None:
        """Should raise RuntimeError when create_review fails."""
        mock_pr = MagicMock()
        mock_pr.create_review.side_effect = Exception("API error")
        github = MagicMock()
        github.get_pull_request.return_value = mock_pr
        agent = ReviewAgent(github_client=github)
        result = ReviewResult(
            success=True,
            review_summary="OK",
            comments=[],
            approved=True,
        )
        with pytest.raises(RuntimeError, match="Failed to submit review"):
            agent.submit_review("owner/repo", 1, result)


# --- cleanup ---


class TestCleanup:
    """Tests for cleanup."""

    def test_cleanup_clears_repo_path(self) -> None:
        """Should set repo_path to None."""
        github = MagicMock()
        agent = ReviewAgent(github_client=github)
        agent.repo_path = "/path/to/repo"
        agent.cleanup()
        assert agent.repo_path is None


# --- Context manager ---


class TestReviewAgentContextManager:
    """Tests for context manager protocol."""

    def test_enter_returns_self(self) -> None:
        """__enter__ should return self."""
        github = MagicMock()
        agent = ReviewAgent(github_client=github)
        assert agent.__enter__() is agent

    def test_exit_calls_cleanup(self) -> None:
        """__exit__ should call cleanup."""
        github = MagicMock()
        agent = ReviewAgent(github_client=github)
        agent.repo_path = "/some/path"
        agent.__exit__(None, None, None)
        assert agent.repo_path is None


# --- review_pull_request main flow ---


class TestReviewPullRequest:
    """Tests for review_pull_request main flow."""

    def test_returns_error_result_on_exception(self) -> None:
        """Should return ReviewResult with success=False when any step raises."""
        github = MagicMock()
        github.get_pull_request.side_effect = Exception("Network error")
        agent = ReviewAgent(github_client=github)
        result = agent.review_pull_request("owner/repo", 1)
        assert result.success is False
        assert result.error == "Network error"
        assert result.review_summary == ""
        assert result.comments == []

    @patch.object(ReviewAgent, "_clone_and_prepare_repo")
    @patch.object(ReviewAgent, "_fetch_pr_data")
    def test_full_flow_success(
        self,
        mock_fetch: MagicMock,
        mock_clone: MagicMock,
    ) -> None:
        """Should fetch PR, clone repo, run agent, and return parsed result."""
        pr_data = PRData(
            number=1,
            title="PR",
            body="",
            state="open",
            url="https://x",
            issue_number=None,
            changed_files=[],
            diff="",
            commits_count=1,
            additions=0,
            deletions=0,
            head_branch="main",
            base_branch="main",
        )
        mock_fetch.return_value = (pr_data, None)
        mock_clone.return_value = "/tmp/repo"

        def run_agent(_self: object, pr: PRData, issue: str | None, verbose: bool) -> ReviewResult:
            return ReviewResult(
                success=True,
                review_summary="Parsed summary",
                comments=[],
                approved=True,
            )

        github = MagicMock()
        agent = ReviewAgent(github_client=github)
        with patch.object(ReviewAgent, "_run_review_agent", run_agent):
            result = agent.review_pull_request("owner/repo", 1)

        assert result.success is True
        assert result.review_summary == "Parsed summary"
        assert result.approved is True
        mock_fetch.assert_called_once_with("owner/repo", 1)
        mock_clone.assert_called_once()
        assert agent.repo_path == "/tmp/repo"
