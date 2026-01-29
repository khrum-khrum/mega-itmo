"""Клиент для работы с GitHub API."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv
from github import Github
from github.Issue import Issue
from github.Repository import Repository

load_dotenv()


@dataclass
class IssueData:
    """Данные Issue в удобном формате."""

    number: int
    title: str
    body: str
    labels: list[str]
    state: str
    url: str

    def __str__(self) -> str:
        """Красивый вывод для отладки."""
        labels_str = ", ".join(self.labels) if self.labels else "нет"
        return (
            f"Issue #{self.number}: {self.title}\n"
            f"Status: {self.state}\n"
            f"Labels: {labels_str}\n"
            f"URL: {self.url}\n"
            f"---\n"
            f"{self.body or 'Описание отсутствует'}"
        )


class GitHubClient:
    """Клиент для работы с GitHub API."""

    def __init__(self, token: str | None = None):
        """
        Инициализация клиента.

        Args:
            token: GitHub Personal Access Token.
                   Если не передан, берётся из переменной окружения GITHUB_TOKEN.
        """
        self.token = token or os.getenv("GITHUB_TOKEN")
        if not self.token:
            raise ValueError(
                "GitHub token не найден. "
                "Передай его как аргумент или установи переменную GITHUB_TOKEN."
            )
        self._client = Github(self.token)

    def get_repo(self, repo_name: str) -> Repository:
        """
        Получить репозиторий.

        Args:
            repo_name: Имя репозитория в формате "owner/repo"

        Returns:
            Объект репозитория
        """
        return self._client.get_repo(repo_name)

    def get_issue(self, repo_name: str, issue_number: int) -> IssueData:
        """
        Получить данные Issue.

        Args:
            repo_name: Имя репозитория в формате "owner/repo"
            issue_number: Номер Issue

        Returns:
            Данные Issue в структурированном формате
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

    def get_repo_structure(self, repo_name: str, path: str = "", max_depth: int = 2) -> str:
        """
        Получить структуру файлов репозитория.

        Args:
            repo_name: Имя репозитория
            path: Начальный путь (по умолчанию корень)
            max_depth: Максимальная глубина обхода

        Returns:
            Строка со структурой файлов
        """
        repo = self.get_repo(repo_name)

        def _get_contents(current_path: str, depth: int) -> list[str]:
            if depth > max_depth:
                return []

            result = []
            try:
                contents = repo.get_contents(current_path)
                if not isinstance(contents, list):
                    contents = [contents]

                for content in contents:
                    indent = "  " * depth
                    if content.type == "dir":
                        result.append(f"{indent}📁 {content.name}/")
                        result.extend(_get_contents(content.path, depth + 1))
                    else:
                        result.append(f"{indent}📄 {content.name}")
            except Exception:
                pass

            return result

        lines = _get_contents(path, 0)
        return "\n".join(lines) if lines else "Репозиторий пуст"

    def get_file_content(self, repo_name: str, file_path: str) -> str | None:
        """
        Получить содержимое файла.

        Args:
            repo_name: Имя репозитория
            file_path: Путь к файлу

        Returns:
            Содержимое файла или None если файл не найден
        """
        repo = self.get_repo(repo_name)
        try:
            content = repo.get_contents(file_path)
            if isinstance(content, list):
                return None  # Это директория
            return content.decoded_content.decode("utf-8")
        except Exception:
            return None
