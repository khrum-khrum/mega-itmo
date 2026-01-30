"""
Service layer for Review Agent API.

This module wraps the Review Agent CLI functionality to be used by FastAPI.
"""

from __future__ import annotations

import logging
import os

from src.review_agent.agent import ReviewAgent, ReviewResult
from src.utils.github_client import GitHubClient

logger = logging.getLogger(__name__)


class ReviewAgentService:
    """Service for executing Review Agent tasks."""

    def __init__(self) -> None:
        """Initialize the Review Agent service."""
        self.github_token = os.getenv("GITHUB_TOKEN")
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        self.model = os.getenv("REVIEW_AGENT_MODEL", "llama-3.3-70b-versatile")
        self.repos_dir = os.getenv("REPOS_DIR", "./repos")
        self.execute = os.getenv("REVIEW_AGENT_EXECUTE", "true").lower() == "true"

        if not self.github_token:
            raise ValueError("GITHUB_TOKEN environment variable is required")
        if not self.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable is required")

    def handle_pull_request(self, repo_full_name: str, pr_number: int) -> None:
        """
        Handle a pull request by running Review Agent.

        This method is executed in the background by FastAPI.

        Args:
            repo_full_name: Full repository name (owner/repo)
            pr_number: Pull request number
        """
        logger.info(f"Starting Review Agent for PR #{pr_number} in {repo_full_name}")

        try:
            agent = self._initialize_review_agent()
            result = self._run_review(repo_full_name, pr_number, agent)

            if not result.success:
                logger.error(f"Review Agent failed: {result.error}")
                return

            logger.info(
                f"Review Agent completed successfully. "
                f"Approved: {result.approved}, Comments: {len(result.comments)}"
            )

            self._submit_or_log_review(repo_full_name, pr_number, agent, result)
            agent.cleanup(verbose=True)

        except Exception as e:
            logger.error(f"Error handling PR #{pr_number}: {str(e)}", exc_info=True)

    def _initialize_review_agent(self) -> ReviewAgent:
        """Initialize GitHub client and Review Agent."""
        github_client = GitHubClient(
            token=self.github_token,
            repos_dir=self.repos_dir,
        )

        return ReviewAgent(
            github_client=github_client,
            model=self.model,
            api_key=self.openrouter_api_key,
        )

    def _run_review(self, repo_full_name: str, pr_number: int, agent: ReviewAgent) -> ReviewResult:
        """Run review agent on the PR."""
        logger.info(f"Analyzing PR #{pr_number}...")
        return agent.review_pull_request(
            repo_name=repo_full_name,
            pr_number=pr_number,
            verbose=True,
        )

    def _submit_or_log_review(
        self,
        repo_full_name: str,
        pr_number: int,
        agent: ReviewAgent,
        result: ReviewResult,
    ) -> None:
        """Submit review to GitHub or log dry-run results."""
        if self.execute:
            logger.info("Submitting review to GitHub...")
            agent.submit_review(
                repo_name=repo_full_name,
                pr_number=pr_number,
                review_result=result,
                verbose=True,
            )
            logger.info(f"Successfully submitted review for PR #{pr_number}")
        else:
            logger.info(
                "Dry-run mode: Review not submitted to GitHub. "
                "Set REVIEW_AGENT_EXECUTE=true to enable."
            )
            logger.info(f"Review summary:\n{result.review_summary}")
