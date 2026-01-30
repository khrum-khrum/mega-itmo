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

Your task is to analyze Pull Request changes and provide constructive, actionable feedback.

WORKFLOW:
1. **Understand the PR**: Read the PR description and related Issue to understand the goals
2. **Analyze Changes**: Review the diff to see what was modified
3. **Examine Context**: Use tools to read changed files and search for related code
4. **Identify Issues**: Look for:
   - Bugs and logic errors
   - Security vulnerabilities
   - Performance issues
   - Code style violations
   - Missing tests or documentation
   - Deviations from the Issue requirements
5. **Verify Quality**: Check if tests pass and code meets standards
6. **Generate Review**: Provide clear, constructive feedback

REVIEW GUIDELINES:
- Be constructive and helpful, not overly critical
- Explain WHY something is an issue and HOW to fix it
- Praise good implementations
- Focus on significant issues, not minor style nitpicks
- Check if the PR actually solves the Issue requirements
- Verify that tests exist and pass (if applicable)

TOOL USAGE:
- Use `read_pr_file` to examine changed files in detail
- Use `search_code_in_pr` to find related code or patterns
- Use `run_test_command` to verify tests pass
- Use `analyze_pr_complexity` to identify complex code

OUTPUT FORMAT:
After your review, provide:
1. Overall assessment (APPROVE / REQUEST_CHANGES / COMMENT)
2. Summary of findings
3. Specific comments for issues found (with file path and approximate line number)

Be thorough but fair in your review.
"""

    def __init__(
        self,
        github_client: GitHubClient,
        model: str = "meta-llama/llama-3.1-70b-instruct",
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
            # 1. Get PR data
            if verbose:
                print(f"\n📋 Fetching Pull Request #{pr_number}...")
            pr_data = self._fetch_pr_data(repo_name, pr_number)

            if verbose:
                print(f"✅ PR #{pr_data.number}: {pr_data.title}")
                print(f"   Changed files: {len(pr_data.changed_files)}")
                print(f"   +{pr_data.additions} -{pr_data.deletions}")

            # 2. Clone repository
            if verbose:
                print(f"\n📦 Cloning repository {repo_name}...")
            self.repo_path = self.github.clone_repository(repo_name)

            if verbose:
                print(f"✅ Repository cloned to: {self.repo_path}")

            # 3. Change working directory to repo
            original_dir = os.getcwd()
            os.chdir(self.repo_path)

            try:
                # 4. Initialize LangChain agent with tools
                if verbose:
                    print(f"\n🤖 Initializing review agent with {len(ALL_REVIEW_TOOLS)} tools...")

                self.langchain_agent = LangChainAgent(
                    tools=ALL_REVIEW_TOOLS,
                    api_key=self.api_key,
                    model=self.model,
                )

                # Override system prompt for review agent
                self.langchain_agent.agent = self._create_review_agent()

                # 5. Prepare review prompt
                review_prompt = self._build_review_prompt(pr_data)

                # 6. Run the agent
                if verbose:
                    print(f"\n🧠 Running review agent...\n")
                    print("=" * 60)

                result = self.langchain_agent.run(review_prompt)

                if verbose:
                    print("=" * 60)
                    print(f"\n✅ Review agent finished\n")

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
            print(f"\n📝 Submitting review to PR #{pr_number}...")

        try:
            pr = self.github.get_pull_request(repo_name, pr_number)

            # Determine review event
            if review_result.approved:
                event = "APPROVE"
            elif review_result.comments:
                event = "REQUEST_CHANGES"
            else:
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
                print(f"✅ Review submitted: {review.html_url}")
                print(f"   Status: {event}")

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
            print(f"\n✅ Repository preserved at: {self.repo_path}")
        self.repo_path = None

    def _fetch_pr_data(self, repo_name: str, pr_number: int) -> PRData:
        """
        Fetch Pull Request data from GitHub.

        Args:
            repo_name: Repository name (owner/repo)
            pr_number: Pull Request number

        Returns:
            PRData object with PR information
        """
        pr = self.github.get_pull_request(repo_name, pr_number)

        # Extract issue number from PR body or title
        issue_number = None
        import re
        if pr.body:
            match = re.search(r"#(\d+)", pr.body)
            if match:
                issue_number = int(match.group(1))

        # Get changed files
        changed_files = [f.filename for f in pr.get_files()]

        # Get diff (limited to avoid overwhelming the LLM)
        diff_lines = []
        for file in pr.get_files():
            if file.patch:
                diff_lines.append(f"--- {file.filename}")
                diff_lines.append(file.patch[:1000])  # Limit patch size
        diff = "\n".join(diff_lines)

        return PRData(
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
        )

    def _build_review_prompt(self, pr_data: PRData) -> str:
        """
        Build review prompt from PR data.

        Args:
            pr_data: Pull Request data

        Returns:
            Formatted prompt for review agent
        """
        prompt = f"""# Pull Request to Review

**PR #:** {pr_data.number}
**Title:** {pr_data.title}
**State:** {pr_data.state}
**URL:** {pr_data.url}
**Related Issue:** #{pr_data.issue_number if pr_data.issue_number else 'Unknown'}

## Description

{pr_data.body}

## Changes Summary

- **Commits:** {pr_data.commits_count}
- **Changed Files:** {len(pr_data.changed_files)}
- **Additions:** +{pr_data.additions}
- **Deletions:** -{pr_data.deletions}

## Changed Files

{chr(10).join(f"- {f}" for f in pr_data.changed_files)}

## Diff (Preview)

```diff
{pr_data.diff}
```

---

**Your task:** Review this Pull Request thoroughly and provide feedback.

Use the available tools to:
1. Read changed files in detail
2. Search for related code
3. Run tests if applicable
4. Analyze code complexity

Provide your review in this format:

**DECISION:** [APPROVE / REQUEST_CHANGES / COMMENT]

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
        # Simple parsing logic
        approved = "APPROVE" in output and "REQUEST_CHANGES" not in output

        # Extract summary (everything between SUMMARY: and COMMENTS:)
        summary_match = output.split("**SUMMARY:**")
        if len(summary_match) > 1:
            summary_part = summary_match[1].split("**COMMENTS:**")[0].strip()
        else:
            summary_part = output[:500]  # Fallback to first 500 chars

        # Extract comments (simple heuristic)
        comments = []
        # For now, we'll include comments in the summary
        # Future improvement: parse individual comments with file/line info

        return ReviewResult(
            success=True,
            review_summary=summary_part,
            comments=comments,
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
        status_emoji = "✅" if review_result.approved else "⚠️"

        body = f"""{status_emoji} **Automated Code Review**

## Summary

{review_result.review_summary}

---

*🤖 This review was automatically generated by Review Agent using LangChain*
"""
        return body

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup."""
        self.cleanup()
        return False
