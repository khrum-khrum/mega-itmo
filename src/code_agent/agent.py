"""Refactored Code Agent using LangChain with tools."""

import os
from dataclasses import dataclass
from typing import Any, Literal, Self

from src.code_agent.tools import ALL_TOOLS
from src.utils.github_client import (
    GitHubClient,
    IssueData,
    PRCommentData,
    PRData,
)
from src.utils.langchain_llm import LangChainAgent

# Keywords for PR feedback analysis
NEGATIVE_KEYWORDS = [
    "fix",
    "change",
    "update",
    "modify",
    "incorrect",
    "wrong",
    "bug",
    "issue",
    "problem",
    "should",
    "need",
    "must",
    "please",
    "todo",
    "needs changes",
    "requested changes",
]

POSITIVE_KEYWORDS = [
    "lgtm",
    "looks good",
    "great",
    "perfect",
    "approved",
    "ready to merge",
    "well done",
    "nice",
    "good job",
]


@dataclass
class AgentResult:
    """Result of agent execution."""

    success: bool
    output: str
    repo_path: str
    branch_name: str
    error: str | None = None


class CodeAgent:
    """
    Refactored Code Agent using LangChain with custom tools.

    This agent:
    1. Clones the target repository
    2. Uses LangChain agent with tools to analyze and modify code
    3. Commits and pushes changes
    4. Creates Pull Request
    """

    def __init__(
        self,
        github_client: GitHubClient,
        model: str = "llama-3.3-70b-versatile",
        api_key: str | None = None,
    ):
        """
        Initialize the Code Agent.

        Args:
            github_client: GitHub API client
            model: LLM model to use (OpenRouter format)
            api_key: OpenRouter API key
        """
        self.github = github_client
        self.model = model
        self.api_key = api_key
        self.langchain_agent: LangChainAgent | None = None
        self.repo_path: str | None = None

    def analyze_and_solve_issue(
        self,
        repo_name: str,
        issue_number: int,
        pr_number: int | None = None,
        verbose: bool = False,
    ) -> AgentResult:
        """
        Analyze a GitHub Issue and generate a solution.

        If pr_number is provided, works on existing PR by:
        - Fetching all PR comments and feedback
        - Checking out the existing PR branch
        - Including feedback in the agent prompt

        Args:
            repo_name: Repository name (owner/repo)
            issue_number: Issue number
            pr_number: Pull Request number (optional, for existing PRs)
            verbose: Whether to print verbose output

        Returns:
            AgentResult with execution details
        """
        try:
            # Fetch issue and PR data
            issue, pr_data = self._fetch_issue_and_pr_data(
                repo_name, issue_number, pr_number, verbose
            )

            # Check if changes are needed for PR feedback
            if pr_data:
                early_exit = self._check_if_changes_needed(pr_data, verbose)
                if early_exit:
                    return early_exit

            # Prepare repository
            self.repo_path = self._prepare_repository(repo_name, pr_data, verbose)

            # Run agent analysis
            result = self._run_agent_analysis(issue, repo_name, pr_data, verbose)

            # Determine branch name
            branch_name = pr_data.head_branch if pr_data else f"agent/issue-{issue_number}"

            return AgentResult(
                success=True,
                output=result.get("output", ""),
                repo_path=self.repo_path,
                branch_name=branch_name,
            )

        except Exception as e:
            return AgentResult(
                success=False,
                output="",
                repo_path=self.repo_path or "",
                branch_name="",
                error=str(e),
            )

    def _fetch_issue_and_pr_data(
        self,
        repo_name: str,
        issue_number: int,
        pr_number: int | None,
        verbose: bool,
    ) -> tuple[IssueData, PRData | None]:
        """Fetch issue data and optional PR data from GitHub."""
        if verbose:
            print(f"\nFetching Issue #{issue_number}...")
        issue = self.github.get_issue(repo_name, issue_number)

        pr_data = None
        if pr_number:
            if verbose:
                print(f"\nFetching PR #{pr_number} with comments...")
            pr_data = self.github.get_pr_data_with_comments(repo_name, pr_number)
            if verbose:
                print(f"Found {len(pr_data.comments)} comments in PR")

        return issue, pr_data

    def _check_if_changes_needed(self, pr_data: PRData, verbose: bool) -> AgentResult | None:
        """Check if PR feedback requires changes. Returns early exit result if no changes needed."""
        if not self._should_process_pr_feedback(pr_data, verbose):
            if verbose:
                print("\nNo changes needed - all feedback is positive")
            return AgentResult(
                success=True,
                output="No changes needed - PR feedback is positive",
                repo_path="",
                branch_name=pr_data.head_branch,
            )
        return None

    def _prepare_repository(self, repo_name: str, pr_data: PRData | None, verbose: bool) -> str:
        """Clone repository and checkout appropriate branch."""
        if verbose:
            if pr_data:
                print(f"\nCloning repository and checking out PR branch '{pr_data.head_branch}'...")
            else:
                print(f"\nCloning repository {repo_name}...")

        if pr_data:
            repo_path = self.github.clone_repository(repo_name, branch=pr_data.head_branch)
        else:
            repo_path = self.github.clone_repository(repo_name)

        if verbose:
            print(f"Repository prepared at: {repo_path}")

        return repo_path

    def _run_agent_analysis(
        self, issue: IssueData, repo_name: str, pr_data: PRData | None, verbose: bool
    ) -> dict:
        """Initialize agent and run analysis within the repository directory."""
        if self.repo_path is None:
            raise RuntimeError("Repository path not set")
        original_dir = os.getcwd()
        os.chdir(self.repo_path)

        try:
            if verbose:
                print(f"\nInitializing LangChain agent with {len(ALL_TOOLS)} tools...")

            self.langchain_agent = LangChainAgent(
                tools=ALL_TOOLS,
                api_key=self.api_key,
                model=self.model,
            )

            issue_prompt = self._build_issue_prompt(issue, repo_name, pr_data)

            if verbose:
                if pr_data:
                    print("\nRunning agent to address PR feedback...\n")
                else:
                    print("\nRunning agent to solve the issue...\n")
                print("=" * 60)

            result = self.langchain_agent.run(issue_prompt)

            if verbose:
                print("=" * 60)
                print("\nAgent finished execution\n")

            return result

        finally:
            os.chdir(original_dir)

    def commit_and_push(
        self,
        result: AgentResult,
        commit_message: str,
        verbose: bool = False,
    ) -> None:
        """
        Commit and push changes made by the agent.

        Args:
            result: AgentResult from analyze_and_solve_issue
            commit_message: Commit message
            verbose: Whether to print verbose output

        Raises:
            RuntimeError: If commit/push fails
        """
        if not result.success:
            raise RuntimeError(f"Cannot commit failed execution: {result.error}")

        if verbose:
            print(f"\nCommitting and pushing changes to branch '{result.branch_name}'...")

        try:
            has_changes = self.github.commit_and_push_changes(
                repo_path=result.repo_path,
                branch_name=result.branch_name,
                commit_message=commit_message,
            )

            if has_changes:
                if verbose:
                    print(f"Changes pushed to {result.branch_name}")
            else:
                if verbose:
                    print("No changes to commit - PR is already in good state")

        except Exception as e:
            raise RuntimeError(f"Failed to commit and push: {str(e)}") from e

    def create_pull_request(
        self,
        repo_name: str,
        issue_number: int,
        result: AgentResult,
        verbose: bool = False,
    ) -> str:
        """
        Create a Pull Request with the solution.

        Args:
            repo_name: Repository name (owner/repo)
            issue_number: Issue number
            result: AgentResult from analyze_and_solve_issue
            verbose: Whether to print verbose output

        Returns:
            Pull Request URL

        Raises:
            RuntimeError: If PR creation fails
        """
        if not result.success:
            raise RuntimeError(f"Cannot create PR for failed execution: {result.error}")

        if verbose:
            print("\nCreating Pull Request...")

        try:
            issue = self.github.get_issue(repo_name, issue_number)

            pr_title = f"[Agent] Fix #{issue_number}: {issue.title}"
            pr_body = f"""## Автоматическое решение Issue #{issue_number}

**Оригинальный Issue:** {issue.url}

### Решение
{result.output}

---

Closes #{issue_number}

*Этот Pull Request был автоматически создан Code Agent с использованием LangChain*
"""

            pr = self.github.create_pull_request(
                repo_name=repo_name,
                title=pr_title,
                body=pr_body,
                head_branch=result.branch_name,
            )

            if verbose:
                print(f"Pull Request created: {pr.html_url}")

            return pr.html_url

        except Exception as e:
            raise RuntimeError(f"Failed to create Pull Request: {str(e)}") from e

    def cleanup(self, verbose: bool = False) -> None:
        """
        Clean up - no longer removes repositories as they are reused.

        Args:
            verbose: Whether to print verbose output
        """
        if verbose and self.repo_path:
            print(f"\nRepository preserved at: {self.repo_path}")
        self.repo_path = None

    def _should_process_pr_feedback(self, pr_data: PRData, verbose: bool = False) -> bool:
        """
        Determine if PR feedback requires code changes.

        Returns False (skip processing) if:
        - No comments exist
        - All reviews are APPROVED with no change requests
        - Comments contain only positive feedback

        Returns True (process) if:
        - Any review has state CHANGES_REQUESTED
        - Comments contain negative feedback or change requests
        - Comments mention specific issues or bugs

        Args:
            pr_data: Pull Request data with comments
            verbose: Whether to print verbose output

        Returns:
            True if changes are needed, False if PR is ready to merge
        """
        if not pr_data.comments:
            if verbose:
                print("  → No comments found, skipping changes")
            return False

        # Analyze all comments and count feedback types
        feedback_counts = self._count_feedback_types(pr_data.comments, verbose)

        # Make decision based on feedback analysis
        return self._make_feedback_decision(feedback_counts, verbose)

    def _count_feedback_types(self, comments: list[PRCommentData], verbose: bool) -> dict[str, Any]:
        """Count different types of feedback in PR comments."""
        counts = {
            "has_changes_requested": False,
            "has_approval": False,
            "negative_count": 0,
            "positive_count": 0,
        }

        for comment in comments:
            self._analyze_comment_sentiment(comment, counts, verbose)

        return counts

    def _analyze_comment_sentiment(
        self,
        comment: PRCommentData,
        counts: dict[str, Any],
        verbose: bool,
    ) -> None:
        """Analyze a single comment for sentiment and review state."""
        # Check review state
        if comment.review_state == "CHANGES_REQUESTED":
            counts["has_changes_requested"] = True
            if verbose:
                print(f"  → Found CHANGES_REQUESTED review from @{comment.author}")

        elif comment.review_state == "APPROVED":
            counts["has_approval"] = True
            if verbose:
                print(f"  → Found APPROVED review from @{comment.author}")

        # Analyze comment body for keywords
        comment_body_lower = comment.body.lower()

        if any(keyword in comment_body_lower for keyword in NEGATIVE_KEYWORDS):
            counts["negative_count"] += 1
            if verbose:
                print(
                    f"  → Found change request in comment from @{comment.author}: "
                    f'"{comment.body[:60]}..."'
                )

        elif any(keyword in comment_body_lower for keyword in POSITIVE_KEYWORDS):
            counts["positive_count"] += 1
            if verbose:
                print(
                    f"  → Found positive feedback from @{comment.author}: "
                    f'"{comment.body[:60]}..."'
                )

    def _make_feedback_decision(self, counts: dict, verbose: bool) -> bool:
        """Make decision about whether changes are needed based on feedback counts."""
        if counts["has_changes_requested"]:
            if verbose:
                print("  Changes are needed (CHANGES_REQUESTED state found)")
            return True

        if counts["negative_count"] > 0:
            if verbose:
                print(f"  Changes are needed ({counts['negative_count']} change request(s) found)")
            return True

        if counts["has_approval"] and counts["negative_count"] == 0:
            if verbose:
                print("  No changes needed (PR is approved with no change requests)")
            return False

        if counts["positive_count"] > 0 and counts["negative_count"] == 0:
            if verbose:
                print("  No changes needed (only positive feedback found)")
            return False

        # Default: if unclear, process to be safe
        if verbose:
            print("  Unclear feedback, processing to be safe")
        return True

    def _build_issue_prompt(
        self, issue: IssueData, repo_name: str, pr_data: PRData | None = None
    ) -> str:
        """
        Build a detailed prompt for the agent from the Issue data.

        Args:
            issue: Issue data
            repo_name: Repository name
            pr_data: Pull Request data with comments (if working on existing PR)

        Returns:
            Formatted prompt
        """
        prompt = self._build_issue_header(issue, repo_name)

        if pr_data:
            prompt += self._build_pr_feedback_section(pr_data)
            prompt += self._build_task_instructions_for_pr()
        else:
            prompt += self._build_task_instructions_for_issue()

        prompt += self._build_workflow_instructions()

        return prompt

    def _build_issue_header(self, issue: IssueData, repo_name: str) -> str:
        """Build the issue header section of the prompt."""
        return f"""# GitHub Issue to Solve

**Repository:** {repo_name}
**Issue #:** {issue.number}
**Title:** {issue.title}
**State:** {issue.state}
**Labels:** {', '.join(issue.labels) if issue.labels else 'None'}
**URL:** {issue.url}

## Description

{issue.body}
"""

    def _build_pr_feedback_section(self, pr_data: PRData) -> str:
        """Build the PR feedback section of the prompt."""
        section = f"""

---

## Existing Pull Request

**PR #{pr_data.number}:** {pr_data.title}
**Status:** {pr_data.state}
**Branch:** {pr_data.head_branch} -> {pr_data.base_branch}
**URL:** {pr_data.url}

### PR Description

{pr_data.body}

### Feedback and Comments ({len(pr_data.comments)})

"""
        if pr_data.comments:
            for i, comment in enumerate(pr_data.comments, 1):
                section += f"""
**Comment {i}:**
{str(comment)}

"""
        else:
            section += "No comments yet.\n"

        return section

    def _build_task_instructions_for_pr(self) -> str:
        """Build task instructions for PR feedback mode."""
        return """
---

**Your task:** This PR already exists for the issue. Review the feedback and comments above,
then make the necessary changes to address them. You are working on the existing branch,
so your changes will be added as new commits to the PR.

Focus on:
1. Understanding the feedback from reviewers
2. Addressing all requested changes
3. Fixing any issues or bugs mentioned
4. Improving code quality based on suggestions

"""

    def _build_task_instructions_for_issue(self) -> str:
        """Build task instructions for new issue mode."""
        return """

---

**Your task:** Analyze this issue and implement a solution by modifying the code in the repository.

"""

    def _build_workflow_instructions(self) -> str:
        """Build the workflow verification instructions section."""
        return """
You have access to tools for:
- Exploring the repository structure
- Reading and searching files
- Creating, updating, and deleting files
- Running commands
- Checking git diff
- Checking GitHub workflow status

**WORKFLOW:**
1. Understand the repository structure and requirements
2. Check baseline: Use check_github_workflows with 'HEAD' to see current workflow status
3. Implement the required changes
4. Commit your changes using git commands
5. Verify: Use check_github_workflows with 'HEAD' again to ensure workflows still pass
6. If workflows fail: Analyze errors, fix issues, commit, and re-verify
7. Only complete when ALL workflows are successful

**CRITICAL WORKFLOW VERIFICATION:**
GitHub workflows (CI/CD pipelines) are the primary indicator of code quality:

**BEFORE STARTING:**
- Check current workflow status to establish a baseline
- Note which workflows exist and their status

**AFTER MAKING CHANGES:**
- Commit your changes first
- Use check_github_workflows tool with commit_sha='HEAD' to check workflow status
- ALL workflows that were passing before MUST pass after your changes
- If ANY workflow fails:
  * Read the workflow file (.github/workflows/*.yml) to understand what it does
  * Use run_command to execute the same tests locally
  * Analyze the error messages
  * Fix the underlying issues in your code
  * Commit the fixes
  * Re-run check_github_workflows until ALL workflows pass
- Only complete your task when ALL workflows are successful

**IMPORTANT:**
If workflows were passing before your changes, they MUST pass after your changes.
Failing workflows indicate that your code has issues that MUST be fixed.
Do not consider the task complete until all workflows pass.
"""

    def __enter__(self) -> Self:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Literal[False]:
        """Context manager exit - cleanup repository."""
        self.cleanup()
        return False
