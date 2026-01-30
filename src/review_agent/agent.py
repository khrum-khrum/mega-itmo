"""Review Agent using LangChain with tools."""

import os
from dataclasses import dataclass

from src.review_agent.tools import ALL_REVIEW_TOOLS
from src.utils.github_client import GitHubClient
from src.utils.langchain_llm import LangChainAgent


@dataclass
class PRData:
    """Pull Request data for review."""

    number: int
    title: str
    body: str
    state: str
    url: str
    issue_number: int | None
    changed_files: list[str]
    diff: str
    commits_count: int
    additions: int
    deletions: int
    head_branch: str  # PR branch to checkout
    base_branch: str  # Target branch


@dataclass
class ReviewResult:
    """Result of PR review."""

    success: bool
    review_summary: str
    comments: list[dict[str, str]]  # List of {path, line, body}
    approved: bool
    error: str | None = None


class ReviewAgent:
    """
    Review Agent using LangChain with custom tools.

    This agent:
    1. Fetches Pull Request data from GitHub
    2. Clones repository and analyzes changes
    3. Uses LangChain agent with tools to review code
    4. Generates review comments
    5. Submits review to GitHub PR
    """

    SYSTEM_PROMPT = """You are an expert code reviewer performing automated code review.

Your PRIMARY GOAL is to ensure that Pull Requests:
1. **IMPLEMENT THE ISSUE REQUIREMENTS** - The code must solve what the issue asks for
2. **ACTUALLY WORK** - Tests must pass, code must be functional
3. **PASS GITHUB WORKFLOWS** - All CI/CD pipelines must be successful
4. **FOLLOW BEST PRACTICES** - Code quality, security, performance

CRITICAL WORKFLOW:
1. **Understand Issue Requirements**:
   - Use `fetch_issue_details` to get the original issue
   - Identify ALL requirements and acceptance criteria
   - Understand what problem needs to be solved

2. **Verify Implementation**:
   - Read changed files using `read_pr_file`
   - Check if code implements ALL issue requirements
   - Look for missing functionality or partial implementations

3. **Run Tests (MANDATORY)**:
   - Use `run_test_command` to execute tests
   - Verify all tests pass
   - Check for test coverage of new functionality
   - **DO NOT APPROVE if tests fail or don't exist**

4. **Check GitHub Workflows (MANDATORY)**:
   - Use `check_pr_workflows` to verify all CI/CD pipelines pass
   - Check workflows with commit_sha='HEAD' for the latest PR commit
   - **DO NOT APPROVE if workflows fail or are still running**
   - Workflows must be successful for READY TO MERGE status

5. **Check Code Quality**:
   - Security vulnerabilities (SQL injection, XSS, etc.)
   - Bugs and logic errors
   - Performance issues
   - Best practices for libraries used
   - Use `query_library_docs` to verify correct library usage

6. **Examine Context**:
   - Use `search_code_in_pr` to find related code
   - Use `analyze_pr_complexity` for complex files
   - Ensure consistency with existing codebase

VERIFICATION REQUIREMENTS (ALL MANDATORY):
✅ Issue requirements are FULLY implemented (not partially)
✅ Tests exist and PASS
✅ GitHub workflows (CI/CD) are SUCCESSFUL
✅ Code actually works (no broken functionality)
✅ No security vulnerabilities
✅ Libraries are used correctly
✅ Implementation solves the problem correctly

TOOL USAGE (in this order):
1. `fetch_issue_details` - Get original issue requirements
2. `read_pr_file` - Read changed files to understand implementation
3. `run_test_command` - Run tests (e.g., "pytest", "npm test", etc.)
4. `check_pr_workflows` - Check GitHub Actions workflow status (MANDATORY)
5. `query_library_docs` - Verify library usage if needed
6. `search_code_in_pr` - Find related code patterns
7. `analyze_pr_complexity` - Check complex files

REVIEW FEEDBACK:
Provide comprehensive review feedback in the form of comments. You should:
- **POSITIVE FEEDBACK**: Acknowledge what's implemented correctly
- **CRITICAL ISSUES**: Highlight missing requirements, failing tests, failing workflows, bugs, security issues
- **SUGGESTIONS**: Recommend improvements for code quality and best practices
- **QUESTIONS**: Ask for clarification when needed

**FLAG CRITICAL ISSUES IF CODE:**
- Doesn't implement the full issue requirements
- Has failing tests or no tests
- Has failing GitHub workflows or workflows still running
- Doesn't work or has bugs
- Has security vulnerabilities
- Uses libraries incorrectly

OUTPUT FORMAT:
**ASSESSMENT:** [READY TO MERGE / NEEDS CHANGES / REQUIRES DISCUSSION]

**ISSUE VERIFICATION:**
[List each issue requirement and confirm if implemented]

**TESTS:**
[Report test execution results - MUST run tests]

**GITHUB WORKFLOWS:**
[Report workflow status - MUST check workflows]

**SUMMARY:**
[Overall assessment]

**COMMENTS:**
[Specific issues with file:line references]

Be thorough, rigorous, and prioritize correctness over speed.
"""

    def __init__(
        self,
        github_client: GitHubClient,
        model: str = "llama-3.3-70b-versatile",
        api_key: str | None = None,
    ):
        """
        Initialize the Review Agent.

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

    def review_pull_request(
        self,
        repo_name: str,
        pr_number: int,
        verbose: bool = False,
    ) -> ReviewResult:
        """
        Analyze a Pull Request and generate review.

        Args:
            repo_name: Repository name (owner/repo)
            pr_number: Pull Request number
            verbose: Whether to print verbose output

        Returns:
            ReviewResult with review details
        """
        try:
            # 1. Get PR data and related issue
            if verbose:
                print(f"\nFetching Pull Request #{pr_number}...")
            pr_data, issue_details = self._fetch_pr_data(repo_name, pr_number)

            if verbose:
                print(f"PR #{pr_data.number}: {pr_data.title}")
                print(f"   Changed files: {len(pr_data.changed_files)}")
                print(f"   +{pr_data.additions} -{pr_data.deletions}")
                print(f"   Branch: {pr_data.head_branch} -> {pr_data.base_branch}")
                if issue_details:
                    print(f"   Related Issue: #{pr_data.issue_number}")

            # 2. Clone repository and checkout PR branch
            if verbose:
                print(f"\nCloning repository {repo_name} (branch: {pr_data.head_branch})...")
            self.repo_path = self.github.clone_repository(repo_name, branch=pr_data.head_branch)

            if verbose:
                print(f"Repository cloned to: {self.repo_path}")
                print(f"Checked out to PR branch: {pr_data.head_branch}")

            # 3. Change working directory to repo
            original_dir = os.getcwd()
            os.chdir(self.repo_path)

            try:
                # 4. Initialize LangChain agent with tools
                if verbose:
                    print(f"\nInitializing review agent with {len(ALL_REVIEW_TOOLS)} tools...")

                self.langchain_agent = LangChainAgent(
                    tools=ALL_REVIEW_TOOLS,
                    api_key=self.api_key,
                    model=self.model,
                )

                # Override system prompt for review agent
                self.langchain_agent.agent = self._create_review_agent()

                # 5. Prepare review prompt with issue details
                review_prompt = self._build_review_prompt(pr_data, issue_details)

                # 6. Run the agent
                if verbose:
                    print(f"\nRunning review agent...\n")
                    print("=" * 60)

                result = self.langchain_agent.run(review_prompt)

                if verbose:
                    print("=" * 60)
                    print(f"\nReview agent finished\n")

                # 7. Parse review result
                review_output = result.get("output", "")
                review_result = self._parse_review_output(review_output)

                return review_result

            finally:
                # Always return to original directory
                os.chdir(original_dir)

        except Exception as e:
            return ReviewResult(
                success=False,
                review_summary="",
                comments=[],
                approved=False,
                error=str(e),
            )

    def submit_review(
        self,
        repo_name: str,
        pr_number: int,
        review_result: ReviewResult,
        verbose: bool = False,
    ) -> str:
        """
        Submit review to GitHub Pull Request.

        Args:
            repo_name: Repository name (owner/repo)
            pr_number: Pull Request number
            review_result: ReviewResult from review_pull_request
            verbose: Whether to print verbose output

        Returns:
            Review URL

        Raises:
            RuntimeError: If review submission fails
        """
        if not review_result.success:
            raise RuntimeError(f"Cannot submit failed review: {review_result.error}")

        if verbose:
            print(f"\nSubmitting review to PR #{pr_number}...")

        try:
            pr = self.github.get_pull_request(repo_name, pr_number)

            # Always use COMMENT event to avoid "cannot approve your own PR" error
            # Since the Code Agent and Review Agent use the same GitHub account,
            # we can't use APPROVE or REQUEST_CHANGES
            event = "COMMENT"

            # Format review comments for GitHub API
            # Note: GitHub requires specific format for inline comments
            # We'll add them as part of the review body instead
            review_body = self._format_review_body(review_result)

            # Create review
            review = pr.create_review(
                body=review_body,
                event=event,
            )

            if verbose:
                print(f"Review submitted: {review.html_url}")
                print(f"Status: {event}")

            return review.html_url

        except Exception as e:
            raise RuntimeError(f"Failed to submit review: {str(e)}") from e

    def cleanup(self, verbose: bool = False) -> None:
        """
        Clean up - repository is preserved for reuse.

        Args:
            verbose: Whether to print verbose output
        """
        if verbose and self.repo_path:
            print(f"\nRepository preserved at: {self.repo_path}")
        self.repo_path = None

    def _fetch_pr_data(self, repo_name: str, pr_number: int) -> tuple[PRData, str | None]:
        """
        Fetch Pull Request data and related Issue from GitHub.

        Args:
            repo_name: Repository name (owner/repo)
            pr_number: Pull Request number

        Returns:
            Tuple of (PRData object with PR information, Issue details string or None)
        """
        pr = self.github.get_pull_request(repo_name, pr_number)

        # Extract issue number from PR body or title
        issue_number = None
        issue_details = None
        import re
        if pr.body:
            match = re.search(r"#(\d+)", pr.body)
            if match:
                issue_number = int(match.group(1))
                # Fetch the issue details
                try:
                    issue = self.github.get_issue(repo_name, issue_number)
                    issue_details = f"""**Issue #{issue.number}: {issue.title}**

**Status:** {issue.state}
**Labels:** {', '.join(issue.labels)}

**Description:**
{issue.body}

**URL:** {issue.url}
"""
                except Exception as e:
                    issue_details = f"Failed to fetch issue #{issue_number}: {str(e)}"

        # Get changed files
        changed_files = [f.filename for f in pr.get_files()]

        # Get diff (limited to avoid overwhelming the LLM)
        diff_lines = []
        for file in pr.get_files():
            if file.patch:
                diff_lines.append(f"--- {file.filename}")
                diff_lines.append(file.patch[:1000])  # Limit patch size
        diff = "\n".join(diff_lines)

        pr_data = PRData(
            number=pr.number,
            title=pr.title,
            body=pr.body or "",
            state=pr.state,
            url=pr.html_url,
            issue_number=issue_number,
            changed_files=changed_files,
            diff=diff,
            commits_count=pr.commits,
            additions=pr.additions,
            deletions=pr.deletions,
            head_branch=pr.head.ref,  # PR branch name
            base_branch=pr.base.ref,  # Target branch name
        )

        return pr_data, issue_details

    def _build_review_prompt(self, pr_data: PRData, issue_details: str | None = None) -> str:
        """
        Build review prompt from PR data and related issue.

        Args:
            pr_data: Pull Request data
            issue_details: Related issue details (optional)

        Returns:
            Formatted prompt for review agent
        """
        # Build issue section if available
        issue_section = ""
        if issue_details:
            issue_section = f"""## Related Issue - REQUIREMENTS TO VERIFY

{issue_details}

**CRITICAL:** You MUST verify that the PR implementation addresses ALL requirements from the issue above.
The PR should only be approved if it fully implements the issue requirements and the code works.

"""

        prompt = f"""# Pull Request to Review

**PR #:** {pr_data.number}
**Title:** {pr_data.title}
**State:** {pr_data.state}
**Branch:** {pr_data.head_branch} → {pr_data.base_branch}
**URL:** {pr_data.url}
**Related Issue:** #{pr_data.issue_number if pr_data.issue_number else 'Unknown'}

## Description

{pr_data.body}

{issue_section}

## Changes Summary

- **Commits:** {pr_data.commits_count}
- **Changed Files:** {len(pr_data.changed_files)}
- **Additions:** +{pr_data.additions}
- **Deletions:** -{pr_data.deletions}

**Note:** You are currently on branch `{pr_data.head_branch}` which contains all the PR changes.

## Changed Files

{chr(10).join(f"- {f}" for f in pr_data.changed_files)}

## Diff (Preview)

```diff
{pr_data.diff}
```

---

**Your task:** Review this Pull Request thoroughly and provide feedback.

**VERIFICATION CHECKLIST (MANDATORY):**
1. **Issue Requirements:** Does the PR implement ALL requirements from the issue?
2. **Code Quality:** Is the code well-written, secure, and follows best practices?
3. **Tests:** Run tests to verify the code works (use run_test_command)
4. **GitHub Workflows:** Check that all CI/CD pipelines pass (use check_pr_workflows)
5. **Correctness:** Does the implementation solve the problem correctly?
6. **Library Usage:** If using external libraries, verify correct usage (use query_library_docs)

Use the available tools to:
1. Fetch issue details (if not already provided) using fetch_issue_details
2. Read changed files in detail using read_pr_file
3. Search for related code using search_code_in_pr
4. **RUN TESTS** using run_test_command (MANDATORY - must verify code works!)
5. **CHECK WORKFLOWS** using check_pr_workflows with commit_sha='HEAD' (MANDATORY - must verify pipelines pass!)
6. Query library documentation using query_library_docs if needed
7. Analyze code complexity using analyze_pr_complexity

**FLAG AS "NEEDS CHANGES"** if:
- Tests are failing
- GitHub workflows are failing
- Issue requirements are not fully implemented
- Code has bugs or security issues
- Implementation doesn't work

**FLAG AS "REQUIRES DISCUSSION"** if:
- GitHub workflows are still running (not complete)
- Minor issues that need clarification
- Questions about implementation approach

Provide your review in this format:

**ASSESSMENT:** [READY TO MERGE / NEEDS CHANGES / REQUIRES DISCUSSION]

**ISSUE VERIFICATION:**
[Confirm whether the PR implements all issue requirements. Be specific.]

**TESTS:**
[Report on test results. Did you run tests? Did they pass?]

**GITHUB WORKFLOWS:**
[Report on GitHub Actions workflow status. Did all workflows pass?]

**SUMMARY:**
[Overall assessment of the PR]

**COMMENTS:**
[Specific issues found, if any. Format as:
- File: path/to/file.py, Line: ~XX
  Issue: [description]
  Suggestion: [how to fix]
]
"""
        return prompt

    def _create_review_agent(self):
        """
        Create a review agent with custom system prompt.

        Returns:
            Configured LangChain agent
        """
        from langchain.agents import create_agent
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=self.model,
            openai_api_key=self.api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=0.2,
            max_tokens=4096,
        )

        return create_agent(
            llm,
            tools=ALL_REVIEW_TOOLS,
            system_prompt=self.SYSTEM_PROMPT,
        )

    def _parse_review_output(self, output: str) -> ReviewResult:
        """
        Parse agent output into ReviewResult.

        Args:
            output: Raw output from agent

        Returns:
            Parsed ReviewResult
        """
        # Simple parsing logic - check if ready to merge
        approved = "READY TO MERGE" in output and "NEEDS CHANGES" not in output

        # Build comprehensive summary including all sections
        summary_parts = []

        # Extract issue verification
        if "**ISSUE VERIFICATION:**" in output:
            issue_match = output.split("**ISSUE VERIFICATION:**")
            if len(issue_match) > 1:
                issue_part = issue_match[1].split("**")[0].strip()
                summary_parts.append(f"**Issue Verification:**\n{issue_part}")

        # Extract test results
        if "**TESTS:**" in output:
            test_match = output.split("**TESTS:**")
            if len(test_match) > 1:
                test_part = test_match[1].split("**")[0].strip()
                summary_parts.append(f"\n**Tests:**\n{test_part}")

        # Extract GitHub workflows section
        if "**GITHUB WORKFLOWS:**" in output:
            workflows_match = output.split("**GITHUB WORKFLOWS:**")
            if len(workflows_match) > 1:
                workflows_part = workflows_match[1].split("**")[0].strip()
                summary_parts.append(f"\n**GitHub Workflows:**\n{workflows_part}")

        # Extract summary
        if "**SUMMARY:**" in output:
            summary_match = output.split("**SUMMARY:**")
            if len(summary_match) > 1:
                summary_part = summary_match[1].split("**COMMENTS:**")[0].strip()
                summary_parts.append(f"\n**Summary:**\n{summary_part}")

        # Extract comments
        if "**COMMENTS:**" in output:
            comments_match = output.split("**COMMENTS:**")
            if len(comments_match) > 1:
                comments_part = comments_match[1].strip()
                if comments_part:
                    summary_parts.append(f"\n**Comments:**\n{comments_part}")

        # Combine all parts or use fallback
        if summary_parts:
            full_summary = "\n".join(summary_parts)
        else:
            full_summary = output[:1000]  # Fallback to first 1000 chars

        return ReviewResult(
            success=True,
            review_summary=full_summary,
            comments=[],  # Comments are included in summary for now
            approved=approved,
        )

    def _format_review_body(self, review_result: ReviewResult) -> str:
        """
        Format review result as GitHub review body.

        Args:
            review_result: ReviewResult to format

        Returns:
            Formatted markdown review body
        """
        status_prefix = "[APPROVED]" if review_result.approved else "[REVIEW]"

        body = f"""{status_prefix} **Automated Code Review Feedback**

## Review Summary

{review_result.review_summary}

---

*This review feedback was automatically generated by Review Agent using LangChain*
*Note: This is advisory feedback only. Final approval decisions are made by human reviewers.*
"""
        return body

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup."""
        self.cleanup()
        return False
