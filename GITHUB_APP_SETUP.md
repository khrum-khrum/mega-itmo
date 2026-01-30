# GitHub App Setup Guide

This guide explains how to set up the Code Agent as a GitHub App with webhook integration.

## Architecture

The Code Agent API runs as a standalone service that receives webhook events from GitHub:

```
GitHub Repository → GitHub App → Webhook → Code Agent API
                                              ↓
                                   Clone, Analyze, Code, PR
```

**Important:** The Code Agent and Review Agent are completely separate and will run in different containers (potentially on different VMs).

## Prerequisites

- Docker and Docker Compose installed
- A server with a public IP or domain name (for receiving webhooks)
- GitHub account with repository access
- OpenRouter API key (https://openrouter.ai/keys)

## Quick Start

### 1. Clone and Configure

```bash
# Clone the repository
git clone <your-repo>
cd mega-itmo

# Copy environment template
cp .env.example .env

# Edit .env with your credentials
nano .env
```

Required environment variables:
```bash
GITHUB_TOKEN=ghp_your_token_here              # GitHub Personal Access Token
OPENROUTER_API_KEY=sk-or-v1-your_key_here    # OpenRouter API key
GITHUB_WEBHOOK_SECRET=your_secret_here         # Secret for webhook verification
CODE_AGENT_MODEL=meta-llama/llama-3.1-70b-instruct  # Optional: LLM model
REPOS_DIR=./repos                              # Optional: repos directory
```

### 2. Start the Service

```bash
# Start the Code Agent API
docker-compose up -d

# Check logs
docker-compose logs -f code-agent-api

# Check health
curl http://localhost:8000/health
```

The API will be available at `http://localhost:8000`.

### 3. Expose to Internet (for Webhooks)

You need to expose your local service to the internet so GitHub can send webhooks. Options:

#### Option A: Using ngrok (for testing)

```bash
# Install ngrok: https://ngrok.com/
ngrok http 8000

# Copy the HTTPS URL (e.g., https://abc123.ngrok.io)
# This will be your webhook URL
```

#### Option B: Using a VPS/Cloud Server

Deploy to a server with a public IP:

```bash
# On your server
git clone <your-repo>
cd mega-itmo
cp .env.example .env
# Edit .env
docker-compose up -d
```

Your webhook URL will be: `http://your-server-ip:8000/webhook`

#### Option C: Using Cloud Services

- **Yandex Cloud**: https://console.yandex.cloud (free tier available)
- **Cloud.ru**: https://cloud.ru (free trial available)

## GitHub App Setup

### Step 1: Create a GitHub App

1. Go to GitHub Settings: https://github.com/settings/apps
2. Click "New GitHub App"
3. Fill in the details:

**Basic Information:**
- **GitHub App name**: `Code Agent` (or any name you prefer)
- **Homepage URL**: `https://github.com/your-org/mega-itmo`
- **Webhook URL**: `https://your-domain.com/webhook` (from Step 3 above)
- **Webhook secret**: Generate a random string and use it in `.env` as `GITHUB_WEBHOOK_SECRET`

**Permissions:**
- Repository permissions:
  - **Contents**: Read & Write (to clone and push code)
  - **Issues**: Read & Write (to read issues and comment)
  - **Pull requests**: Read & Write (to create PRs and read reviews)
  - **Metadata**: Read-only (required)

**Subscribe to events:**
- ✅ Issues (for new issue events)
- ✅ Pull request review (for PR review feedback)
- ✅ Pull request review comment (for inline code comments)
- ✅ Issue comment (for general PR comments)

**Where can this GitHub App be installed?**
- Choose "Any account" or "Only on this account"

4. Click "Create GitHub App"

### Step 2: Generate a Private Key (Optional)

**Note:** For this implementation, we use a Personal Access Token instead of a GitHub App private key. If you want to use GitHub App authentication:

1. Scroll down to "Private keys"
2. Click "Generate a private key"
3. Download the `.pem` file
4. Store it securely on your server

For now, we'll use a Personal Access Token (simpler setup).

### Step 3: Install the App on Repositories

1. Go to your GitHub App settings
2. Click "Install App" in the left sidebar
3. Choose the account/organization
4. Select repositories:
   - "All repositories" or
   - "Only select repositories" (choose the repos you want the agent to work on)
5. Click "Install"

### Step 4: Get Your Personal Access Token

Since we're using a PAT instead of GitHub App authentication:

1. Go to: https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Name: `Code Agent Token`
4. Scopes needed:
   - ✅ `repo` (all)
   - ✅ `workflow`
5. Click "Generate token"
6. Copy the token to your `.env` file as `GITHUB_TOKEN`

## Testing the Integration

### Test 1: Health Check

```bash
curl http://localhost:8000/health
# Expected: {"status":"healthy"}
```

### Test 2: Manual Trigger (Issue)

```bash
curl -X POST "http://localhost:8000/api/trigger-issue?repo=owner/repo&issue_number=1"
# Expected: {"status":"accepted","message":"Code Agent scheduled for issue #1"}
```

### Test 3: Create a Test Issue on GitHub

1. Go to your repository on GitHub
2. Create a new issue with a simple task:
   ```
   Title: Add hello world function
   Body: Please create a function that prints "Hello, World!"
   ```
3. The webhook should trigger automatically
4. Check logs: `docker-compose logs -f code-agent-api`
5. Wait for the Code Agent to create a PR

### Test 4: Manual Trigger (PR Review)

```bash
curl -X POST "http://localhost:8000/api/trigger-pr?repo=owner/repo&issue_number=1&pr_number=2"
# Expected: {"status":"accepted","message":"Code Agent scheduled for PR #2"}
```

## Webhook Events

The Code Agent API handles the following GitHub webhook events:

### 1. Issues Events

**Trigger:** When an issue is opened or reopened

**Webhook event:** `issues`

**Actions handled:**
- `opened` - New issue created
- `reopened` - Closed issue reopened

**Behavior:**
1. Code Agent receives issue description
2. Clones repository
3. Analyzes requirements
4. Implements solution
5. Creates Pull Request automatically

### 2. Pull Request Review Events

**Trigger:** When a reviewer submits a review with "Request changes"

**Webhook event:** `pull_request_review`

**Actions handled:**
- `submitted` with state `changes_requested`

**Behavior:**
1. Code Agent fetches PR and all review comments
2. Checks out existing PR branch
3. Addresses all feedback
4. Commits changes to the same PR branch
5. PR is automatically updated

### 3. Pull Request Review Comment Events

**Trigger:** When a reviewer adds an inline code comment on a specific line in a PR

**Webhook event:** `pull_request_review_comment`

**Actions handled:**
- `created` - New inline review comment added

**Behavior:**
1. Code Agent fetches PR and all comments (including the new one)
2. Checks out existing PR branch
3. Analyzes and addresses the specific comment
4. Commits changes to the same PR branch
5. PR is automatically updated

**Note:** This event is for inline code comments on specific lines/files in the "Files changed" tab.

### 4. Issue Comment Events

**Trigger:** When someone adds a general comment to a Pull Request (conversation tab)

**Webhook event:** `issue_comment`

**Actions handled:**
- `created` - New comment added to PR (only processes PR comments, not issue comments)

**Behavior:**
1. Code Agent checks if comment is on a PR (not a regular issue)
2. Fetches PR and all comments
3. Checks out existing PR branch
4. Analyzes and addresses the comment feedback
5. Commits changes to the same PR branch
6. PR is automatically updated

**Note:** GitHub treats PRs as issues, so PR comments trigger `issue_comment` events. The API filters to only process PR comments, not regular issue comments.

## Manual API Endpoints

For testing or manual triggering:

### POST /api/trigger-issue

Manually trigger Code Agent for an issue.

**Parameters:**
- `repo` (string, required): Repository full name (owner/repo)
- `issue_number` (int, required): Issue number

**Example:**
```bash
curl -X POST "http://localhost:8000/api/trigger-issue?repo=myorg/myrepo&issue_number=5"
```

### POST /api/trigger-pr

Manually trigger Code Agent to address PR feedback.

**Parameters:**
- `repo` (string, required): Repository full name (owner/repo)
- `issue_number` (int, required): Original issue number
- `pr_number` (int, required): Pull request number

**Example:**
```bash
curl -X POST "http://localhost:8000/api/trigger-pr?repo=myorg/myrepo&issue_number=5&pr_number=12"
```

## Troubleshooting

### Webhook not triggering

1. **Check webhook deliveries:**
   - Go to GitHub App settings → Advanced → Recent Deliveries
   - Look for failed deliveries and error messages

2. **Verify webhook URL is accessible:**
   ```bash
   curl https://your-domain.com/webhook
   # Should return 405 Method Not Allowed (POST required)
   ```

3. **Check webhook signature:**
   - Ensure `GITHUB_WEBHOOK_SECRET` in `.env` matches GitHub App settings
   - Check logs: `docker-compose logs -f code-agent-api`

### Agent not creating PR

1. **Check logs:**
   ```bash
   docker-compose logs -f code-agent-api
   ```

2. **Verify GitHub token has correct permissions:**
   - Go to: https://github.com/settings/tokens
   - Check that `repo` and `workflow` scopes are enabled

3. **Check OpenRouter API key:**
   - Verify key is valid: https://openrouter.ai/keys
   - Check if you have credits available

### Container not starting

1. **Check Docker logs:**
   ```bash
   docker-compose logs code-agent-api
   ```

2. **Verify environment variables:**
   ```bash
   docker-compose config
   ```

3. **Check port is not in use:**
   ```bash
   lsof -i :8000
   ```

## Security Considerations

1. **Webhook Signature Verification:**
   - Always set `GITHUB_WEBHOOK_SECRET`
   - The API verifies all incoming webhook requests

2. **Token Security:**
   - Never commit `.env` file to git
   - Use `.env.example` as a template
   - Rotate tokens regularly

3. **Network Security:**
   - Use HTTPS in production (not HTTP)
   - Consider using a reverse proxy (nginx, Caddy)
   - Set up firewall rules to restrict access

## Production Deployment

### Using Docker on VPS

```bash
# 1. SSH to your server
ssh user@your-server

# 2. Install Docker and Docker Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
sudo apt-get install docker-compose-plugin

# 3. Clone and configure
git clone <your-repo>
cd mega-itmo
cp .env.example .env
nano .env

# 4. Start service
docker-compose up -d

# 5. Set up reverse proxy (nginx example)
sudo apt-get install nginx
sudo nano /etc/nginx/sites-available/code-agent

# Add configuration:
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}

sudo ln -s /etc/nginx/sites-available/code-agent /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# 6. Set up SSL with Let's Encrypt
sudo apt-get install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

### Using Yandex Cloud

1. Create a Compute VM instance
2. Follow the "Docker on VPS" steps above
3. Configure security groups to allow HTTP/HTTPS
4. Use Yandex Certificate Manager for SSL

### Using Cloud.ru

1. Create a Virtual Server
2. Follow the "Docker on VPS" steps above
3. Configure firewall rules
4. Set up DNS and SSL

## Monitoring

### Check service status

```bash
docker-compose ps
```

### View logs

```bash
# All logs
docker-compose logs -f

# Last 100 lines
docker-compose logs --tail=100 code-agent-api

# Filter by severity
docker-compose logs code-agent-api | grep ERROR
```

### Health endpoint

```bash
curl http://localhost:8000/health
```

## Scaling Considerations

For high-traffic scenarios:

1. **Use a task queue** (Redis + Celery) instead of FastAPI background tasks
2. **Run multiple API instances** behind a load balancer
3. **Use separate workers** for long-running agent tasks
4. **Monitor resource usage** (CPU, memory, disk)
5. **Set up logging** to external services (ELK, Datadog, etc.)

## Next Steps

After setting up the Code Agent API:

1. **Test with simple issues** to verify everything works
2. **Set up the Review Agent** (separate service, will be documented separately)
3. **Configure CI/CD pipelines** for your repositories
4. **Monitor performance** and adjust LLM model if needed
5. **Scale infrastructure** based on usage patterns

## Support

For issues or questions:
- Check logs first: `docker-compose logs -f`
- Review GitHub webhook deliveries
- Verify environment variables
- Check server resources (disk space, memory)
