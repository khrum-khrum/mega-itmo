"""GitHub client for repository operations."""

import os
from dataclasses import dataclass
from pathlib import Path

import git
from dotenv import load_dotenv
from github import Github, GithubException, UnknownObjectException, BadCredentialsException
from github.Issue import Issue
from github.PullRequest import PullRequest
from github.Repository import Repository

load_dotenv()


@dataclass
class IssueData:
    """Parsed GitHub Issue data."""

    number: int
    title: str
    body: str
    labels: list[str]
    state: str
    url: str

    def __str__(self) -> str:
        labels_str = ", ".join(self.labels) if self.labels else "none"
        return (
            f"Issue #{self.number}: {self.title}\n"
            f"Status: {self.state}\n"
            f"Labels: {labels_str}\n"
            f"URL: {self.url}\n"
            f"---\n"
            f"{self.body or 'No description'}"
        )


@dataclass
class PRCommentData:
    """Single comment from a Pull Request."""

    author: str
    body: str
    comment_type: str  # "review_comment", "issue_comment", or "review"
    created_at: str
    path: str | None = None  # File path for review comments
    line: int | None = None  # Line number for review comments
    review_state: str | None = None  # APPROVED, CHANGES_REQUESTED, COMMENTED for reviews

    def __str__(self) -> str:
        location = ""
        if self.path and self.line:
            location = f" [{self.path}:{self.line}]"
        elif self.path:
            location = f" [{self.path}]"

        state_info = ""
        if self.review_state:
            state_info = f" ({self.review_state})"

        return (
            f"[{self.comment_type}{state_info}] @{self.author}{location} "
            f"at {self.created_at}:\n{self.body}"
        )


@dataclass
class PRData:
    """Parsed GitHub Pull Request data."""

    number: int
    title: str
    body: str
    state: str
    url: str
    head_branch: str
    base_branch: str
    comments: list[PRCommentData]

    def __str__(self) -> str:
        comments_str = "\n\n".join(str(c) for c in self.comments) if self.comments else "No comments"
        return (
            f"Pull Request #{self.number}: {self.title}\n"
            f"Status: {self.state}\n"
            f"Branch: {self.head_branch} -> {self.base_branch}\n"
            f"URL: {self.url}\n"
            f"---\n"
            f"{self.body or 'No description'}\n"
            f"\n### Comments ({len(self.comments)}):\n\n"
            f"{comments_str}"
        )


class GitHubClient:
    """
    GitHub client for Issue management and repository operations.

    Supports:
    - Fetching Issues
    - Cloning repositories locally
    - Git operations (commit, push)
    - Creating Pull Requests
    """

    def __init__(self, token: str | None = None, repos_dir: str | None = None):
        """
        Initialize GitHub client.

        Args:
            token: GitHub Personal Access Token.
                   If not provided, uses GITHUB_TOKEN environment variable.
            repos_dir: Directory where cloned repositories will be stored.
                      If not provided, uses ./repos directory.

        Raises:
            ValueError: If token is not found
        """
        self.token = token or os.getenv("GITHUB_TOKEN")
        if not self.token:
            raise ValueError(
                "GitHub token not found. "
                "Pass it as argument or set GITHUB_TOKEN environment variable."
            )
        self._client = Github(self.token)
        self.repos_dir = Path(repos_dir) if repos_dir else Path("./repos")
        self.repos_dir.mkdir(parents=True, exist_ok=True)

    def get_repo(self, repo_name: str) -> Repository:
        """
        Get repository object.

        Args:
            repo_name: Repository name (owner/repo)

        Returns:
            Repository object

        Raises:
            RuntimeError: If repository not found or access denied
        """
        try:
            return self._client.get_repo(repo_name)
        except UnknownObjectException as e:
            raise RuntimeError(
                f"Repository '{repo_name}' not found. "
                f"Please check the repository name format (owner/repo) and ensure it exists."
            ) from e
        except BadCredentialsException as e:
            raise RuntimeError(
                "Authentication failed. Please check your GITHUB_TOKEN has valid credentials."
            ) from e
        except GithubException as e:
            if e.status == 403:
                raise RuntimeError(
                    f"Access denied to repository '{repo_name}'. "
                    f"Ensure your GITHUB_TOKEN has 'repo' scope and access to this repository."
                ) from e
            elif e.status == 404:
                raise RuntimeError(
                    f"Repository '{repo_name}' not found. "
                    f"Verify the repository exists and your token has access."
                ) from e
            else:
                raise RuntimeError(
                    f"GitHub API error when accessing '{repo_name}': {e.data.get('message', str(e))}"
                ) from e

    def get_issue(self, repo_name: str, issue_number: int) -> IssueData:
        """
        Fetch Issue data from GitHub.

        Args:
            repo_name: Repository name (owner/repo)
            issue_number: Issue number

        Returns:
            Parsed Issue data

        Raises:
            RuntimeError: If issue not found
        """
        try:
            repo = self.get_repo(repo_name)
            issue: Issue = repo.get_issue(issue_number)

            return IssueData(
                number=issue.number,
                title=issue.title,
                body=issue.body or "",
                labels=[label.name for label in issue.labels],
                state=issue.state,
                url=issue.html_url,
            )
        except UnknownObjectException as e:
            raise RuntimeError(
                f"Issue #{issue_number} not found in repository '{repo_name}'."
            ) from e
        except GithubException as e:
            raise RuntimeError(
                f"Failed to fetch issue #{issue_number}: {e.data.get('message', str(e))}"
            ) from e

    def get_pull_request(self, repo_name: str, pr_number: int) -> PullRequest:
        """
        Fetch Pull Request from GitHub.

        Args:
            repo_name: Repository name (owner/repo)
            pr_number: Pull Request number

        Returns:
            PullRequest object

        Raises:
            RuntimeError: If pull request not found
        """
        try:
            repo = self.get_repo(repo_name)
            pr = repo.get_pull(pr_number)
            return pr
        except UnknownObjectException as e:
            raise RuntimeError(
                f"Pull Request #{pr_number} not found in repository '{repo_name}'. "
                f"Please verify the PR number is correct."
            ) from e
        except GithubException as e:
            raise RuntimeError(
                f"Failed to fetch PR #{pr_number}: {e.data.get('message', str(e))}"
            ) from e

    def get_pr_data_with_comments(self, repo_name: str, pr_number: int) -> PRData:
        """
        Fetch Pull Request data with all comments.

        This includes:
        - Review comments (inline code comments)
        - Issue comments (general discussion)
        - Review summaries (with approval state)

        Args:
            repo_name: Repository name (owner/repo)
            pr_number: Pull Request number

        Returns:
            Parsed PR data with all comments

        Raises:
            RuntimeError: If PR not found
        """
        try:
            repo = self.get_repo(repo_name)
            pr = repo.get_pull(pr_number)

            comments: list[PRCommentData] = []

            # 1. Fetch review comments (inline code comments)
            for review_comment in pr.get_review_comments():
                comments.append(
                    PRCommentData(
                        author=review_comment.user.login,
                        body=review_comment.body,
                        comment_type="review_comment",
                        created_at=review_comment.created_at.isoformat(),
                        path=review_comment.path,
                        line=review_comment.line,
                    )
                )

            # 2. Fetch issue comments (general discussion)
            # PR comments are also accessible as issue comments
            issue = repo.get_issue(pr_number)
            for issue_comment in issue.get_comments():
                comments.append(
                    PRCommentData(
                        author=issue_comment.user.login,
                        body=issue_comment.body,
                        comment_type="issue_comment",
                        created_at=issue_comment.created_at.isoformat(),
                    )
                )

            # 3. Fetch reviews (with approval state)
            for review in pr.get_reviews():
                # Only include reviews with body text or state changes
                if review.body or review.state in ["APPROVED", "CHANGES_REQUESTED"]:
                    comments.append(
                        PRCommentData(
                            author=review.user.login,
                            body=review.body or f"Review: {review.state}",
                            comment_type="review",
                            created_at=review.submitted_at.isoformat() if review.submitted_at else "",
                            review_state=review.state,
                        )
                    )

            # Sort all comments by creation time
            comments.sort(key=lambda c: c.created_at)

            return PRData(
                number=pr.number,
                title=pr.title,
                body=pr.body or "",
                state=pr.state,
                url=pr.html_url,
                head_branch=pr.head.ref,
                base_branch=pr.base.ref,
                comments=comments,
            )

        except UnknownObjectException as e:
            raise RuntimeError(
                f"Pull Request #{pr_number} not found in repository '{repo_name}'."
            ) from e
        except GithubException as e:
            raise RuntimeError(
                f"Failed to fetch PR data for #{pr_number}: {e.data.get('message', str(e))}"
            ) from e

    def clone_repository(
        self,
        repo_name: str,
        branch: str | None = None,
    ) -> str:
        """
        Clone repository to local filesystem or pull latest changes if exists.

        If the repository already exists in the configured directory, it will:
        1. Fetch latest changes from remote
        2. Reset to clean state
        3. Checkout target branch
        4. Pull latest changes

        Args:
            repo_name: Repository name (owner/repo)
            branch: Branch to clone (default: repository's default branch)

        Returns:
            Path to cloned repository

        Raises:
            RuntimeError: If cloning or pulling fails
        """
        repo_obj = self.get_repo(repo_name)
        target_branch = branch or repo_obj.default_branch

        # Use configured repos directory
        target_dir = self.repos_dir / repo_name.replace("/", "_")
        target_dir.mkdir(parents=True, exist_ok=True)

        # Build clone URL with authentication
        clone_url = f"https://{self.token}@github.com/{repo_name}.git"

        try:
            # Check if repository already exists
            if (target_dir / ".git").exists():
                # Repository exists - pull latest changes
                local_repo = git.Repo(str(target_dir))

                # Fetch latest changes
                origin = local_repo.remote("origin")
                origin.fetch()

                # Reset any local changes to ensure clean state
                local_repo.git.reset("--hard")
                local_repo.git.clean("-fd")

                # Checkout target branch
                try:
                    local_repo.git.checkout(target_branch)
                except git.GitCommandError:
                    # Branch might not exist locally, create tracking branch
                    local_repo.git.checkout("-b", target_branch, f"origin/{target_branch}")

                # Pull latest changes
                origin.pull(target_branch)

                return str(target_dir)
            else:
                # Repository doesn't exist - clone it
                git.Repo.clone_from(
                    clone_url,
                    str(target_dir),
                    branch=target_branch,
                    depth=1,  # Shallow clone for efficiency
                )
                return str(target_dir)

        except git.GitCommandError as e:
            raise RuntimeError(f"Failed to clone/pull repository: {str(e)}") from e

    def commit_and_push_changes(
        self,
        repo_path: str,
        branch_name: str,
        commit_message: str,
        author_name: str = "Code Agent",
        author_email: str = "code-agent@github.com",
    ) -> bool:
        """
        Commit and push changes to a branch.

        If the branch already exists locally (e.g., from an existing PR),
        this will add a new commit to it. Otherwise, it creates the branch.

        Args:
            repo_path: Path to local repository
            branch_name: Branch name for commit
            commit_message: Commit message
            author_name: Author name
            author_email: Author email

        Returns:
            True if changes were committed and pushed, False if no changes to commit

        Raises:
            RuntimeError: If git operations fail
        """
        try:
            repo = git.Repo(repo_path)

            # Get current branch
            current_branch = repo.active_branch.name

            # If not on target branch, checkout to it
            if current_branch != branch_name:
                try:
                    # Try to create new branch
                    repo.git.checkout("-b", branch_name)
                except git.GitCommandError:
                    # Branch already exists (locally or remotely), switch to it
                    try:
                        repo.git.checkout(branch_name)
                    except git.GitCommandError:
                        # Branch might exist on remote but not locally
                        repo.git.checkout("-b", branch_name, f"origin/{branch_name}")

            # Stage all changes
            repo.git.add(A=True)

            # Check if there are changes to commit
            if not repo.is_dirty() and not repo.untracked_files:
                # No changes to commit - this is not an error, just nothing to do
                return False

            # Commit
            repo.index.commit(
                commit_message,
                author=git.Actor(author_name, author_email),
            )

            # Push to remote
            # Use --force-with-lease for safety when updating existing branches
            origin = repo.remote("origin")
            try:
                origin.push(branch_name, set_upstream=True)
            except git.GitCommandError:
                # If push fails, might need to force push (for existing PR branches)
                # Use --force-with-lease which is safer than --force
                origin.push(branch_name, set_upstream=True, force_with_lease=True)

            return True

        except git.GitCommandError as e:
            raise RuntimeError(f"Git operation failed: {str(e)}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to commit and push: {str(e)}") from e

    def create_pull_request(
        self,
        repo_name: str,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str | None = None,
    ) -> PullRequest:
        """
        Create a Pull Request.

        Args:
            repo_name: Repository name (owner/repo)
            title: PR title
            body: PR description
            head_branch: Branch with changes
            base_branch: Target branch (default: repository's default branch)

        Returns:
            Created Pull Request object

        Raises:
            RuntimeError: If PR creation fails
        """
        repo = self.get_repo(repo_name)
        base = base_branch or repo.default_branch

        try:
            pr = repo.create_pull(
                title=title,
                body=body,
                head=head_branch,
                base=base,
            )
            return pr

        except GithubException as e:
            if e.status == 422:
                error_message = e.data.get("message", str(e))
                if "pull request already exists" in error_message.lower():
                    raise RuntimeError(
                        f"Pull Request from {head_branch} to {base} already exists"
                    ) from e
                elif "no commits between" in error_message.lower():
                    raise RuntimeError(
                        f"No changes between {base} and {head_branch}"
                    ) from e
                else:
                    raise RuntimeError(f"Validation error: {error_message}") from e
            elif e.status == 403:
                raise RuntimeError(
                    f"Permission denied: Cannot create PR in {repo_name}"
                ) from e
            else:
                raise RuntimeError(
                    f"Failed to create Pull Request: {e.data.get('message', str(e))}"
                ) from e

    def get_workflow_runs_for_commit(
        self,
        repo_name: str,
        commit_sha: str,
    ) -> dict[str, str]:
        """
        Get GitHub Actions workflow runs status for a specific commit.

        Args:
            repo_name: Repository name (owner/repo)
            commit_sha: Commit SHA to check workflows for

        Returns:
            Dictionary mapping workflow names to their status
            Status can be: "success", "failure", "pending", "in_progress", etc.
            Empty dict if no workflows found

        Raises:
            RuntimeError: If workflow check fails
        """
        try:
            repo = self.get_repo(repo_name)

            # Get all workflow runs for this commit
            workflow_runs = repo.get_workflow_runs(head_sha=commit_sha)

            if workflow_runs.totalCount == 0:
                return {}

            # Build status map: workflow name -> status
            status_map = {}
            for run in workflow_runs:
                # Status: queued, in_progress, completed
                # Conclusion: success, failure, neutral, cancelled, skipped, timed_out, action_required
                if run.status == "completed":
                    status_map[run.name] = run.conclusion or "unknown"
                else:
                    status_map[run.name] = run.status

            return status_map

        except GithubException as e:
            raise RuntimeError(
                f"Failed to get workflow runs for commit {commit_sha}: {e.data.get('message', str(e))}"
            ) from e
