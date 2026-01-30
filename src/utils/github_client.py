"""GitHub client for repository operations."""

import os
from dataclasses import dataclass
from pathlib import Path

import git
from dotenv import load_dotenv
from github import Github, GithubException
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
        """
        return self._client.get_repo(repo_name)

    def get_issue(self, repo_name: str, issue_number: int) -> IssueData:
        """
        Fetch Issue data from GitHub.

        Args:
            repo_name: Repository name (owner/repo)
            issue_number: Issue number

        Returns:
            Parsed Issue data
        """
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
    ) -> None:
        """
        Commit and push changes to a branch.

        Args:
            repo_path: Path to local repository
            branch_name: Branch name for commit
            commit_message: Commit message
            author_name: Author name
            author_email: Author email

        Raises:
            RuntimeError: If git operations fail
        """
        try:
            repo = git.Repo(repo_path)

            # Create new branch or switch to existing
            try:
                repo.git.checkout("-b", branch_name)
            except git.GitCommandError:
                # Branch already exists, switch to it
                repo.git.checkout(branch_name)

            # Stage all changes
            repo.git.add(A=True)

            # Check if there are changes to commit
            if not repo.is_dirty() and not repo.untracked_files:
                raise RuntimeError("No changes to commit")

            # Commit
            repo.index.commit(
                commit_message,
                author=git.Actor(author_name, author_email),
            )

            # Push to remote
            origin = repo.remote("origin")
            origin.push(branch_name, set_upstream=True)

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
