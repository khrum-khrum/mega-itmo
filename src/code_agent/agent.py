"""Refactored Code Agent using LangChain with tools."""

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from src.code_agent.tools import ALL_TOOLS
from src.utils.github_client import GitHubClient, IssueData
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
        model: str = "meta-llama/llama-3.1-70b-instruct",
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
        verbose: bool = False,
    ) -> AgentResult:
        """
        Analyze a GitHub Issue and generate a solution.

        Args:
            repo_name: Repository name (owner/repo)
            issue_number: Issue number
            verbose: Whether to print verbose output

        Returns:
            AgentResult with execution details
        """
        try:
            # 1. Get Issue data
            if verbose:
                print(f"\n📋 Fetching Issue #{issue_number}...")
            issue = self.github.get_issue(repo_name, issue_number)

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
                    print(f"\n🤖 Initializing LangChain agent with {len(ALL_TOOLS)} tools...")

                self.langchain_agent = LangChainAgent(
                    tools=ALL_TOOLS,
                    api_key=self.api_key,
                    model=self.model,
                )

                # 5. Prepare issue description for the agent
                issue_prompt = self._build_issue_prompt(issue, repo_name)

                # 6. Run the agent
                if verbose:
                    print(f"\n🧠 Running agent to solve the issue...\n")
                    print("=" * 60)

                result = self.langchain_agent.run(issue_prompt)

                if verbose:
                    print("=" * 60)
                    print(f"\n✅ Agent finished execution\n")

                # 7. Create branch name
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
            print(f"\n📝 Committing and pushing changes to branch '{result.branch_name}'...")

        try:
            self.github.commit_and_push_changes(
                repo_path=result.repo_path,
                branch_name=result.branch_name,
                commit_message=commit_message,
            )

            if verbose:
                print(f"✅ Changes pushed to {result.branch_name}")

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
            print(f"\n🚀 Creating Pull Request...")

        try:
            issue = self.github.get_issue(repo_name, issue_number)

            pr_title = f"[Agent] Fix #{issue_number}: {issue.title}"
            pr_body = f"""## Автоматическое решение Issue #{issue_number}

**Оригинальный Issue:** {issue.url}

### Решение
{result.output}

---

Closes #{issue_number}

*🤖 Этот Pull Request был автоматически создан Code Agent с использованием LangChain*
"""

            pr = self.github.create_pull_request(
                repo_name=repo_name,
                title=pr_title,
                body=pr_body,
                head_branch=result.branch_name,
            )

            if verbose:
                print(f"✅ Pull Request created: {pr.html_url}")

            return pr.html_url

        except Exception as e:
            raise RuntimeError(f"Failed to create Pull Request: {str(e)}") from e

    def cleanup(self, verbose: bool = False) -> None:
        """
        Clean up cloned repository.

        Args:
            verbose: Whether to print verbose output
        """
        if self.repo_path and os.path.exists(self.repo_path):
            if verbose:
                print(f"\n🧹 Cleaning up: {self.repo_path}")
            shutil.rmtree(self.repo_path)
            self.repo_path = None

    def _build_issue_prompt(self, issue: IssueData, repo_name: str) -> str:
        """
        Build a detailed prompt for the agent from the Issue data.

        Args:
            issue: Issue data
            repo_name: Repository name

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

---

**Your task:** Analyze this issue and implement a solution by modifying the code in the repository.

You have access to tools for:
- Exploring the repository structure
- Reading and searching files
- Creating, updating, and deleting files
- Running commands
- Checking git diff

Start by understanding the repository structure, then implement the required changes.
"""
        return prompt

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup repository."""
        self.cleanup()
        return False
