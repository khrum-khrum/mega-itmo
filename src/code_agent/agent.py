"""Refactored Code Agent using LangChain with tools."""

import os
from dataclasses import dataclass

from src.code_agent.tools import ALL_TOOLS
from src.utils.github_client import GitHubClient, IssueData, PRData
from src.utils.langchain_llm import LangChainAgent


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
            # 1. Get Issue data
            if verbose:
                print(f"\nFetching Issue #{issue_number}...")
            issue = self.github.get_issue(repo_name, issue_number)

            # 2. Get PR data if working on existing PR
            pr_data: PRData | None = None
            if pr_number:
                if verbose:
                    print(f"\nFetching PR #{pr_number} with comments...")
                pr_data = self.github.get_pr_data_with_comments(repo_name, pr_number)
                if verbose:
                    print(f"Found {len(pr_data.comments)} comments in PR")

                # Check if changes are actually needed based on feedback
                if not self._should_process_pr_feedback(pr_data, verbose):
                    if verbose:
                        print("\nNo changes needed - all feedback is positive")
                    return AgentResult(
                        success=True,
                        output="No changes needed - PR feedback is positive",
                        repo_path="",
                        branch_name=pr_data.head_branch if pr_data else "",
                    )

            # 3. Clone repository (or checkout to PR branch if exists)
            if verbose:
                if pr_data:
                    print(f"\nCloning repository and checking out PR branch '{pr_data.head_branch}'...")
                else:
                    print(f"\nCloning repository {repo_name}...")

            # If we have PR data, clone and checkout to that branch
            if pr_data:
                self.repo_path = self.github.clone_repository(repo_name, branch=pr_data.head_branch)
            else:
                self.repo_path = self.github.clone_repository(repo_name)

            if verbose:
                print(f"Repository prepared at: {self.repo_path}")

            # 3. Change working directory to repo
            original_dir = os.getcwd()
            os.chdir(self.repo_path)

            try:
                # 4. Initialize LangChain agent with tools
                if verbose:
                    print(f"\nInitializing LangChain agent with {len(ALL_TOOLS)} tools...")

                self.langchain_agent = LangChainAgent(
                    tools=ALL_TOOLS,
                    api_key=self.api_key,
                    model=self.model,
                )

                # 5. Prepare issue description for the agent
                issue_prompt = self._build_issue_prompt(issue, repo_name, pr_data)

                # 6. Run the agent
                if verbose:
                    if pr_data:
                        print(f"\nRunning agent to address PR feedback...\n")
                    else:
                        print(f"\nRunning agent to solve the issue...\n")
                    print("=" * 60)

                result = self.langchain_agent.run(issue_prompt)

                if verbose:
                    print("=" * 60)
                    print(f"\nAgent finished execution\n")

                # 7. Determine branch name
                # If working on existing PR, use that branch; otherwise create new one
                if pr_data:
                    branch_name = pr_data.head_branch
                else:
                    branch_name = f"agent/issue-{issue_number}"

                return AgentResult(
                    success=True,
                    output=result.get("output", ""),
                    repo_path=self.repo_path,
                    branch_name=branch_name,
                )

            finally:
                # Always return to original directory
                os.chdir(original_dir)

        except Exception as e:
            return AgentResult(
                success=False,
                output="",
                repo_path=self.repo_path or "",
                branch_name="",
                error=str(e),
            )

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
                    print(f"No changes to commit - PR is already in good state")

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
            print(f"\nCreating Pull Request...")

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

        # Keywords that indicate changes are needed
        negative_keywords = [
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

        # Positive keywords that indicate approval
        positive_keywords = [
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

        has_changes_requested = False
        has_approval = False
        negative_comment_count = 0
        positive_comment_count = 0

        for comment in pr_data.comments:
            # Check review state
            if comment.review_state == "CHANGES_REQUESTED":
                has_changes_requested = True
                if verbose:
                    print(f"  → Found CHANGES_REQUESTED review from @{comment.author}")

            elif comment.review_state == "APPROVED":
                has_approval = True
                if verbose:
                    print(f"  → Found APPROVED review from @{comment.author}")

            # Analyze comment body for keywords
            comment_body_lower = comment.body.lower()

            # Check for negative keywords
            if any(keyword in comment_body_lower for keyword in negative_keywords):
                negative_comment_count += 1
                if verbose:
                    print(
                        f"  → Found change request in comment from @{comment.author}: "
                        f'"{comment.body[:60]}..."'
                    )

            # Check for positive keywords
            elif any(keyword in comment_body_lower for keyword in positive_keywords):
                positive_comment_count += 1
                if verbose:
                    print(
                        f"  → Found positive feedback from @{comment.author}: "
                        f'"{comment.body[:60]}..."'
                    )

        # Decision logic
        if has_changes_requested:
            if verbose:
                print("  Changes are needed (CHANGES_REQUESTED state found)")
            return True

        if negative_comment_count > 0:
            if verbose:
                print(f"  Changes are needed ({negative_comment_count} change request(s) found)")
            return True

        if has_approval and negative_comment_count == 0:
            if verbose:
                print("  No changes needed (PR is approved with no change requests)")
            return False

        if positive_comment_count > 0 and negative_comment_count == 0:
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
        prompt = f"""# GitHub Issue to Solve

**Repository:** {repo_name}
**Issue #:** {issue.number}
**Title:** {issue.title}
**State:** {issue.state}
**Labels:** {', '.join(issue.labels) if issue.labels else 'None'}
**URL:** {issue.url}

## Description

{issue.body}
"""

        # Add PR information and feedback if available
        if pr_data:
            prompt += f"""

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
                    prompt += f"""
**Comment {i}:**
{str(comment)}

"""
            else:
                prompt += "No comments yet.\n"

            prompt += """
---

**Your task:** This PR already exists for the issue. Review the feedback and comments above, then make the necessary changes to address them. You are working on the existing branch, so your changes will be added as new commits to the PR.

Focus on:
1. Understanding the feedback from reviewers
2. Addressing all requested changes
3. Fixing any issues or bugs mentioned
4. Improving code quality based on suggestions

"""
        else:
            prompt += """

---

**Your task:** Analyze this issue and implement a solution by modifying the code in the repository.

"""

        # Common instructions for both cases
        prompt += """
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
        return prompt

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup repository."""
        self.cleanup()
        return False
