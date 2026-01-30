# Review Agent GitHub App Setup Guide

This guide explains how to create and configure a GitHub App for the **Review Agent**, which automatically reviews pull requests and provides feedback.

## Overview

The Review Agent GitHub App:
- Automatically triggers when a Pull Request is **opened** or when **new commits are pushed**
- Analyzes code changes against the original issue requirements
- Runs tests to verify functionality
- Checks code quality, security, and best practices
- Submits review feedback directly to the PR (APPROVE/REQUEST_CHANGES/COMMENT)

## Prerequisites

1. GitHub account with admin access to your organization or repository
2. Review Agent API deployed and accessible via HTTPS URL
3. HTTPS endpoint required for GitHub webhooks (use ngrok for local testing)

## Step 1: Create GitHub App

1. Navigate to GitHub Settings:
   - **For Organization**: `https://github.com/organizations/YOUR_ORG/settings/apps`
   - **For Personal Account**: `https://github.com/settings/apps`

2. Click **"New GitHub App"**

3. Fill in basic information:
   - **GitHub App name**: `Your Org Review Agent` (must be unique across GitHub)
   - **Description**: `Automated AI code review system for pull requests`
   - **Homepage URL**: Your organization/project website or GitHub repository URL
   - **Webhook URL**: `https://your-domain.com/webhook` (your Review Agent API endpoint)
     - For local testing with ngrok: `https://abc123.ngrok.io/webhook`
   - **Webhook secret**: Generate a strong random secret (save this for later!)
     - Example: `openssl rand -hex 32`

## Step 2: Configure Permissions

The Review Agent requires the following **Repository permissions**:

### Required Permissions

| Permission | Access Level | Why Needed |
|-----------|-------------|-----------|
| **Contents** | Read-only | Read repository files to analyze code |
| **Issues** | Read-only | Fetch original issue to verify requirements |
| **Pull requests** | Read & write | Read PR details and submit review comments |

### How to Set Permissions

1. Scroll to **"Permissions"** section
2. Under **"Repository permissions"**:
   - Set **"Contents"** to **"Read-only"**
   - Set **"Issues"** to **"Read-only"**
   - Set **"Pull requests"** to **"Read & write"**

## Step 3: Subscribe to Events

The Review Agent needs to receive webhooks for:

1. Scroll to **"Subscribe to events"** section
2. Check the following events:
   - ✅ **Pull request** - Triggered when PRs are opened or updated

### Event Actions Handled

The Review Agent specifically handles:
- `opened` - When a new pull request is created
- `synchronize` - When new commits are pushed to an existing PR

Other PR actions (e.g., `closed`, `assigned`, `labeled`) are ignored.

## Step 4: Installation Settings

1. Under **"Where can this GitHub App be installed?"**:
   - Choose **"Only on this account"** for organization-specific use
   - Or choose **"Any account"** if you want to allow external installations

2. Click **"Create GitHub App"**

## Step 5: Generate Private Key (Optional)

If you plan to use GitHub App authentication instead of Personal Access Tokens:

1. Scroll to **"Private keys"** section
2. Click **"Generate a private key"**
3. Save the downloaded `.pem` file securely
4. Configure your Review Agent API to use GitHub App authentication

**Note**: The current implementation uses Personal Access Tokens (`GITHUB_TOKEN`), so this step is optional.

## Step 6: Install GitHub App

1. Go to app settings page: `https://github.com/settings/apps/YOUR_APP_NAME`
2. Click **"Install App"** in the left sidebar
3. Select the account/organization to install to
4. Choose repository access:
   - **All repositories** - Review Agent will work on all repos
   - **Only select repositories** - Choose specific repos

5. Click **"Install"**

## Step 7: Configure Environment Variables

Add the following environment variables to your `.env` file:

```bash
# GitHub Configuration
GITHUB_TOKEN=ghp_your_personal_access_token_here
GITHUB_WEBHOOK_SECRET=your_webhook_secret_from_step1

# OpenRouter Configuration
OPENROUTER_API_KEY=your_openrouter_api_key

# Review Agent Configuration (Optional)
REVIEW_AGENT_MODEL=llama-3.3-70b-versatile
REVIEW_AGENT_EXECUTE=true  # Set to false for dry-run mode
REPOS_DIR=/app/repos
```

### Environment Variables Explained

| Variable | Required | Description |
|---------|----------|-------------|
| `GITHUB_TOKEN` | ✅ Yes | Personal Access Token with `repo` scope |
| `GITHUB_WEBHOOK_SECRET` | ✅ Yes | Secret from Step 1 for webhook signature verification |
| `OPENROUTER_API_KEY` | ✅ Yes | API key from https://openrouter.ai/keys |
| `REVIEW_AGENT_MODEL` | ❌ No | LLM model to use (default: llama-3.1-70b) |
| `REVIEW_AGENT_EXECUTE` | ❌ No | `true` to submit reviews, `false` for dry-run (default: true) |
| `REPOS_DIR` | ❌ No | Directory for cloned repos (default: ./repos) |

## Step 8: Deploy Review Agent API

### Using Docker Compose (Recommended)

Start both Code Agent and Review Agent APIs together:

```bash
# Start both services
docker-compose up -d

# View logs
docker-compose logs -f review-agent-api

# Stop services
docker-compose down
```

The `docker-compose.yml` includes both services:
- **code-agent-api** on port **8000** (handles issues and PR updates)
- **review-agent-api** on port **8001** (handles PR reviews)

### Using Docker (Standalone)

Build and run only the Review Agent API:

```bash
# Build the image
docker build -f Dockerfile.review -t review-agent-api .

# Run the container
docker run -d \
  --name review-agent \
  -p 8001:8001 \
  -e GITHUB_TOKEN=ghp_your_token \
  -e GITHUB_WEBHOOK_SECRET=your_secret \
  -e OPENROUTER_API_KEY=your_key \
  -e REVIEW_AGENT_EXECUTE=true \
  -v $(pwd)/repos:/app/repos \
  review-agent-api
```

## Step 9: Test the Integration

### 1. Verify API is Running

```bash
curl http://localhost:8001/health
# Expected: {"status": "healthy"}
```

### 2. Test Webhook Delivery

1. Create a test pull request in your repository
2. Check GitHub App webhook deliveries:
   - Go to `https://github.com/settings/apps/YOUR_APP_NAME/advanced`
   - View recent webhook deliveries
   - Verify 200 OK response

3. Check Review Agent logs:
```bash
docker-compose logs -f review-agent-api

# Expected output:
# INFO - Received webhook event: pull_request
# INFO - Scheduling Review Agent for new PR #123 in owner/repo
# INFO - Starting Review Agent for PR #123 in owner/repo
```

### 3. Manual Trigger (Testing)

You can manually trigger a review:

```bash
curl -X POST "http://localhost:8001/api/trigger-review?repo=owner/repo&pr_number=123"
```

## Step 10: Running Both Agents Together

The system supports running both agents simultaneously for a complete automated workflow:

```bash
# Start both agents
docker-compose up -d

# Check status
docker-compose ps

# View logs for both
docker-compose logs -f

# View logs for specific service
docker-compose logs -f code-agent-api
docker-compose logs -f review-agent-api
```

## Security Best Practices

1. **Always verify webhook signatures** - The Review Agent API verifies `X-Hub-Signature-256` headers
2. **Use strong webhook secrets** - Generate with `openssl rand -hex 32`
3. **Protect your tokens** - Never commit `.env` files or expose tokens in logs
4. **Use HTTPS** - GitHub requires HTTPS for webhook URLs (use ngrok for local testing)
5. **Limit repository access** - Only install the app on repositories that need it
6. **Monitor logs** - Regularly check logs for errors or unauthorized access attempts

## Troubleshooting

### Webhook not received

1. Check webhook delivery status in GitHub App settings
2. Verify your API is accessible from the internet (not localhost)
3. Ensure firewall allows incoming connections on port 8001
4. Check API logs: `docker-compose logs -f review-agent-api`

### Signature verification fails

1. Verify `GITHUB_WEBHOOK_SECRET` matches the secret in GitHub App settings
2. Check that the webhook is using `sha256` algorithm
3. Ensure the secret is properly URL-encoded if it contains special characters

### Review not submitted

1. Check `REVIEW_AGENT_EXECUTE` is set to `true` in `.env`
2. Verify `GITHUB_TOKEN` has `repo` scope and write access to Pull requests
3. Check Review Agent logs for errors during submission
4. Ensure the token hasn't expired

### Agent fails to clone repository

1. Verify `GITHUB_TOKEN` has read access to repository contents
2. Check that repository is not private (or token has private repo access)
3. Ensure `REPOS_DIR` directory exists and has write permissions
4. Check disk space is available

## Complete Workflow Example

1. **Developer creates Issue** → Code Agent creates PR (via Code Agent GitHub App on port 8000)
2. **PR is opened** → Review Agent reviews code (via Review Agent GitHub App on port 8001)
3. **Review Agent requests changes** → Code Agent addresses feedback (via webhook to port 8000)
4. **Developer pushes new commits** → Review Agent re-reviews (via webhook to port 8001)
5. **All checks pass** → Review Agent approves PR
6. **Developer merges** → Workflow complete

## Next Steps

- Set up CI/CD pipeline integration
- Configure custom review rules
- Add Slack/Discord notifications for reviews
- Implement review metrics dashboard
- Set up staging environment testing

## Support

For issues or questions:
- GitHub Issues: https://github.com/your-org/your-repo/issues
- Documentation: See `CLAUDE.md` for technical details
- API Documentation:
  - Code Agent: http://localhost:8000/docs
  - Review Agent: http://localhost:8001/docs
