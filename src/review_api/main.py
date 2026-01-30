"""
FastAPI application for Review Agent GitHub webhook handling.

This module provides webhook endpoints for the Review Agent only.
The Code Agent is separate and has its own API.
"""

import hashlib
import hmac
import logging
import os
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request

from src.review_api.service import ReviewAgentService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Review Agent API",
    description="Automated code review system using AI for GitHub pull requests",
    version="1.0.0",
)

# Initialize Review Agent service
review_agent_service = ReviewAgentService()

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
async def root() -> dict[str, str]:
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "Review Agent API",
        "version": "1.0.0",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint for monitoring."""
    return {"status": "healthy"}


@app.post("/webhook")
async def handle_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: str = Header(None),
    x_hub_signature_256: str = Header(None),
) -> dict[str, str]:
    """
    Handle GitHub webhook events.

    This endpoint receives webhook events from GitHub and processes them.
    Supported events:
    - pull_request: opened (triggers Review Agent to review new PR)
    - pull_request: synchronize (triggers Review Agent when new commits are pushed)

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
    if x_github_event == "pull_request":
        return await handle_pull_request_event(payload, background_tasks)
    elif x_github_event == "ping":
        logger.info("Received ping event")
        return {"status": "pong"}
    else:
        logger.warning(f"Unsupported event type: {x_github_event}")
        return {"status": "ignored", "reason": f"Event {x_github_event} not supported"}


async def handle_pull_request_event(
    payload: dict[str, Any],
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """
    Handle pull request webhook events.

    Triggers Review Agent when:
    - A pull request is opened (action: opened)
    - New commits are pushed to a pull request (action: synchronize)

    Args:
        payload: Webhook payload
        background_tasks: Background task manager

    Returns:
        Response indicating task was scheduled
    """
    action = payload.get("action")
    pull_request = payload.get("pull_request", {})
    repository = payload.get("repository", {})

    # Only handle opened and synchronize actions
    if action not in ["opened", "synchronize"]:
        logger.info(f"Ignoring pull request action: {action}")
        return {"status": "ignored", "reason": f"Action {action} not handled"}

    # Extract PR details
    repo_full_name = repository.get("full_name")
    pr_number = pull_request.get("number")

    if not repo_full_name or not pr_number:
        raise HTTPException(status_code=400, detail="Missing repository or PR number")

    # Log the action
    if action == "opened":
        logger.info(f"Scheduling Review Agent for new PR #{pr_number} in {repo_full_name}")
    elif action == "synchronize":
        logger.info(
            f"Scheduling Review Agent for PR #{pr_number} "
            f"(new commits pushed) in {repo_full_name}"
        )

    # Schedule agent execution in background
    background_tasks.add_task(
        review_agent_service.handle_pull_request,
        repo_full_name=repo_full_name,
        pr_number=pr_number,
    )

    return {
        "status": "accepted",
        "message": f"Review Agent scheduled for PR #{pr_number}",
    }


@app.post("/api/trigger-review")
async def trigger_review(
    repo: str,
    pr_number: int,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """
    Manual trigger endpoint for PR review processing.

    Use this endpoint to manually trigger the Review Agent for a specific PR.

    Args:
        repo: Repository full name (owner/repo)
        pr_number: Pull request number
        background_tasks: Background task manager

    Returns:
        Response indicating task was scheduled
    """
    logger.info(f"Manual trigger: Review Agent for PR #{pr_number} in {repo}")

    background_tasks.add_task(
        review_agent_service.handle_pull_request,
        repo_full_name=repo,
        pr_number=pr_number,
    )

    return {
        "status": "accepted",
        "message": f"Review Agent scheduled for PR #{pr_number}",
    }
