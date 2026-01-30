"""
Service layer for Review Agent API.

This module wraps the Review Agent CLI functionality to be used by FastAPI.
"""

import logging
import os

from src.review_agent.agent import ReviewAgent
from src.utils.github_client import GitHubClient

logger = logging.getLogger(__name__)


class ReviewAgentService:
    """Service for executing Review Agent tasks."""

    def __init__(self):
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
            # Initialize GitHub client
            github_client = GitHubClient(
                token=self.github_token,
                repos_dir=self.repos_dir,
            )

            # Initialize Review Agent
            agent = ReviewAgent(
                github_client=github_client,
                model=self.model,
                api_key=self.openrouter_api_key,
            )

            # Run agent to review PR
            logger.info(f"Analyzing PR #{pr_number}...")
            result = agent.review_pull_request(
                repo_name=repo_full_name,
                pr_number=pr_number,
                verbose=True,
            )

            if not result.success:
                logger.error(f"Review Agent failed: {result.error}")
                return

            logger.info(
                f"Review Agent completed successfully. "
                f"Approved: {result.approved}, Comments: {len(result.comments)}"
            )

            # Submit review to GitHub if execute mode is enabled
            if self.execute:
                logger.info("Submitting review to GitHub...")
                agent.submit_review(
                    repo_name=repo_full_name,
                    pr_number=pr_number,
                    review_result=result,
                    verbose=True,
                )
                logger.info(f"✅ Successfully submitted review for PR #{pr_number}")
            else:
                logger.info(
                    f"Dry-run mode: Review not submitted to GitHub. "
                    f"Set REVIEW_AGENT_EXECUTE=true to enable."
                )
                logger.info(f"Review summary:\n{result.review_summary}")

            # Cleanup
            agent.cleanup(verbose=True)

        except Exception as e:
            logger.error(f"Error handling PR #{pr_number}: {str(e)}", exc_info=True)
