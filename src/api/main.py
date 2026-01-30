"""
FastAPI application for Code Agent GitHub webhook handling.

This module provides webhook endpoints for the Code Agent only.
The Review Agent is separate and will have its own API.
"""

import hmac
import hashlib
import logging
import os
from typing import Any, Dict

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request

from src.api.service import CodeAgentService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Code Agent API",
    description="Automated code generation system using AI for GitHub issues and PRs",
    version="1.0.0",
)

# Initialize Code Agent service
code_agent_service = CodeAgentService()

# GitHub webhook secret for signature verification
WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")


def verify_webhook_signature(payload_body: bytes, signature_header: str) -> bool:
    """
    Verify GitHub webhook signature.

    Args:
        payload_body: Raw request body as bytes
        signature_header: X-Hub-Signature-256 header value

    Returns:
        True if signature is valid, False otherwise
    """
    if not WEBHOOK_SECRET:
        logger.warning("GITHUB_WEBHOOK_SECRET not set, skipping signature verification")
        return True

    if not signature_header:
        return False

    # GitHub sends signature as "sha256=<signature>"
    try:
        hash_algorithm, github_signature = signature_header.split("=")
    except ValueError:
        return False

    if hash_algorithm != "sha256":
        return False

    # Compute expected signature
    mac = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        msg=payload_body,
        digestmod=hashlib.sha256,
    )
    expected_signature = mac.hexdigest()

    # Compare signatures
    return hmac.compare_digest(expected_signature, github_signature)


@app.get("/")
async def root() -> Dict[str, str]:
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "Code Agent API",
        "version": "1.0.0",
    }


@app.get("/health")
async def health() -> Dict[str, str]:
    """Health check endpoint for monitoring."""
    return {"status": "healthy"}


@app.post("/webhook")
async def handle_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: str = Header(None),
    x_hub_signature_256: str = Header(None),
) -> Dict[str, str]:
    """
    Handle GitHub webhook events.

    This endpoint receives webhook events from GitHub and processes them.
    Supported events:
    - issues: opened, reopened (triggers Code Agent to implement feature)
    - pull_request_review: submitted with changes_requested (triggers Code Agent to fix issues)

    Args:
        request: FastAPI request object
        background_tasks: Background task manager
        x_github_event: GitHub event type header
        x_hub_signature_256: GitHub signature header

    Returns:
        Response indicating webhook was received

    Raises:
        HTTPException: If signature verification fails or event is invalid
    """
    # Get raw body for signature verification
    body = await request.body()

    # Verify webhook signature
    if not verify_webhook_signature(body, x_hub_signature_256):
        logger.error("Invalid webhook signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse JSON payload
    payload = await request.json()

    logger.info(f"Received webhook event: {x_github_event}")

    # Handle different event types
    if x_github_event == "issues":
        return await handle_issue_event(payload, background_tasks)
    elif x_github_event == "pull_request_review":
        return await handle_pr_review_event(payload, background_tasks)
    elif x_github_event == "ping":
        logger.info("Received ping event")
        return {"status": "pong"}
    else:
        logger.warning(f"Unsupported event type: {x_github_event}")
        return {"status": "ignored", "reason": f"Event {x_github_event} not supported"}


async def handle_issue_event(
    payload: Dict[str, Any],
    background_tasks: BackgroundTasks,
) -> Dict[str, str]:
    """
    Handle issue webhook events.

    Triggers Code Agent when an issue is opened or reopened.

    Args:
        payload: Webhook payload
        background_tasks: Background task manager

    Returns:
        Response indicating task was scheduled
    """
    action = payload.get("action")
    issue = payload.get("issue", {})
    repository = payload.get("repository", {})

    # Only handle opened and reopened issues
    if action not in ["opened", "reopened"]:
        logger.info(f"Ignoring issue action: {action}")
        return {"status": "ignored", "reason": f"Action {action} not handled"}

    # Extract issue details
    repo_full_name = repository.get("full_name")
    issue_number = issue.get("number")

    if not repo_full_name or not issue_number:
        raise HTTPException(status_code=400, detail="Missing repository or issue number")

    logger.info(f"Scheduling Code Agent for issue #{issue_number} in {repo_full_name}")

    # Schedule agent execution in background
    background_tasks.add_task(
        code_agent_service.handle_issue,
        repo_full_name=repo_full_name,
        issue_number=issue_number,
    )

    return {
        "status": "accepted",
        "message": f"Code Agent scheduled for issue #{issue_number}",
    }


async def handle_pr_review_event(
    payload: Dict[str, Any],
    background_tasks: BackgroundTasks,
) -> Dict[str, str]:
    """
    Handle pull request review webhook events.

    Triggers Code Agent when changes are requested in a PR review.

    Args:
        payload: Webhook payload
        background_tasks: Background task manager

    Returns:
        Response indicating task was scheduled
    """
    action = payload.get("action")
    review = payload.get("review", {})
    pull_request = payload.get("pull_request", {})
    repository = payload.get("repository", {})

    # Only handle submitted reviews with changes requested
    if action != "submitted":
        logger.info(f"Ignoring PR review action: {action}")
        return {"status": "ignored", "reason": f"Action {action} not handled"}

    review_state = review.get("state", "").lower()
    if review_state != "changes_requested":
        logger.info(f"Ignoring review state: {review_state}")
        return {
            "status": "ignored",
            "reason": f"Review state {review_state} not handled",
        }

    # Extract PR details
    repo_full_name = repository.get("full_name")
    pr_number = pull_request.get("number")

    # Try to get issue number from PR body or use PR number
    pr_body = pull_request.get("body", "")
    issue_number = extract_issue_number_from_pr(pr_body, pr_number)

    if not repo_full_name or not pr_number or not issue_number:
        raise HTTPException(
            status_code=400,
            detail="Missing repository, PR number, or issue number",
        )

    logger.info(
        f"Scheduling Code Agent for PR #{pr_number} (issue #{issue_number}) in {repo_full_name}"
    )

    # Schedule agent execution in background
    background_tasks.add_task(
        code_agent_service.handle_pr_review,
        repo_full_name=repo_full_name,
        issue_number=issue_number,
        pr_number=pr_number,
    )

    return {
        "status": "accepted",
        "message": f"Code Agent scheduled for PR #{pr_number}",
    }


def extract_issue_number_from_pr(pr_body: str, pr_number: int) -> int:
    """
    Extract issue number from PR body.

    Looks for patterns like "Closes #123" or "Fixes #123".
    Falls back to PR number if no issue reference found.

    Args:
        pr_body: Pull request body text
        pr_number: Pull request number (fallback)

    Returns:
        Issue number
    """
    import re

    # Common patterns for issue references
    patterns = [
        r"[Cc]loses?\s+#(\d+)",
        r"[Ff]ixes?\s+#(\d+)",
        r"[Rr]esolves?\s+#(\d+)",
        r"[Ii]ssue\s+#(\d+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, pr_body)
        if match:
            return int(match.group(1))

    # Fallback to PR number
    logger.warning(
        f"Could not extract issue number from PR body, using PR number {pr_number}"
    )
    return pr_number


@app.post("/api/trigger-issue")
async def trigger_issue(
    repo: str,
    issue_number: int,
    background_tasks: BackgroundTasks,
) -> Dict[str, str]:
    """
    Manual trigger endpoint for issue processing.

    Use this endpoint to manually trigger the Code Agent for a specific issue.

    Args:
        repo: Repository full name (owner/repo)
        issue_number: Issue number
        background_tasks: Background task manager

    Returns:
        Response indicating task was scheduled
    """
    logger.info(f"Manual trigger: Code Agent for issue #{issue_number} in {repo}")

    background_tasks.add_task(
        code_agent_service.handle_issue,
        repo_full_name=repo,
        issue_number=issue_number,
    )

    return {
        "status": "accepted",
        "message": f"Code Agent scheduled for issue #{issue_number}",
    }


@app.post("/api/trigger-pr")
async def trigger_pr(
    repo: str,
    issue_number: int,
    pr_number: int,
    background_tasks: BackgroundTasks,
) -> Dict[str, str]:
    """
    Manual trigger endpoint for PR review processing.

    Use this endpoint to manually trigger the Code Agent to address PR review feedback.

    Args:
        repo: Repository full name (owner/repo)
        issue_number: Issue number
        pr_number: Pull request number
        background_tasks: Background task manager

    Returns:
        Response indicating task was scheduled
    """
    logger.info(
        f"Manual trigger: Code Agent for PR #{pr_number} (issue #{issue_number}) in {repo}"
    )

    background_tasks.add_task(
        code_agent_service.handle_pr_review,
        repo_full_name=repo,
        issue_number=issue_number,
        pr_number=pr_number,
    )

    return {
        "status": "accepted",
        "message": f"Code Agent scheduled for PR #{pr_number}",
    }
