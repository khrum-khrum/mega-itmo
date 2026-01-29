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

    # Файлы конфигурации, которые помогают понять стек проекта
    CONFIG_FILES = [
        # JavaScript/TypeScript
        "package.json",
        "tsconfig.json",
        ".eslintrc.json",
        ".prettierrc",
        # Python
        "pyproject.toml",
        "requirements.txt",
        "setup.py",
        "setup.cfg",
        # Go
        "go.mod",
        "go.sum",
        # Rust
        "Cargo.toml",
        # Java
        "pom.xml",
        "build.gradle",
        # Ruby
        "Gemfile",
        # PHP
        "composer.json",
        # .NET
        "*.csproj",
        "*.sln",
        # General
        "Makefile",
        "Dockerfile",
        "docker-compose.yml",
        ".gitignore",
        "README.md",
    ]

    def __init__(self, token: str | None = None):
        """
        Инициализация клиента.

        Args:
            token: GitHub Personal Access Token.
                   Если не передан, берётся из переменной GITHUB_TOKEN.
        """
        self.token = token or os.getenv("GITHUB_TOKEN")
        if not self.token:
            raise ValueError(
                "GitHub token не найден. "
                "Передай его как аргумент или установи переменную GITHUB_TOKEN."
            )
        self._client = Github(self.token)

    def get_repo(self, repo_name: str) -> Repository:
        """Получить репозиторий."""
        return self._client.get_repo(repo_name)

    def get_issue(self, repo_name: str, issue_number: int) -> IssueData:
        """Получить данные Issue."""
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

    def get_repo_structure(
        self,
        repo_name: str,
        path: str = "",
        max_depth: int = 3,
        branch: str | None = None,
    ) -> str:
        """
        Получить структуру файлов репозитория.

        Args:
            repo_name: Имя репозитория
            path: Начальный путь
            max_depth: Максимальная глубина
            branch: Ветка (по умолчанию — default branch)

        Returns:
            Строка со структурой файлов
        """
        repo = self.get_repo(repo_name)
        ref = branch or repo.default_branch

        def _get_contents(current_path: str, depth: int) -> list[str]:
            if depth > max_depth:
                return ["  " * depth + "..."]

            result = []
            try:
                contents = repo.get_contents(current_path, ref=ref)
                if not isinstance(contents, list):
                    contents = [contents]

                # Сортируем: сначала папки, потом файлы
                contents = sorted(contents, key=lambda x: (x.type != "dir", x.name))

                for content in contents:
                    # Пропускаем скрытые файлы и node_modules
                    if content.name.startswith(".") and content.name not in [
                        ".github",
                        ".gitignore",
                    ]:
                        continue
                    if content.name in [
                        "node_modules",
                        "__pycache__",
                        ".git",
                        "venv",
                        "dist",
                        "build",
                    ]:
                        continue

                    indent = "  " * depth
                    if content.type == "dir":
                        result.append(f"{indent}📁 {content.name}/")
                        result.extend(_get_contents(content.path, depth + 1))
                    else:
                        # Добавляем размер для больших файлов
                        size_info = ""
                        if content.size > 10000:
                            size_info = f" ({content.size // 1000}KB)"
                        result.append(f"{indent}📄 {content.name}{size_info}")
            except Exception:
                pass

            return result

        lines = _get_contents(path, 0)
        return "\n".join(lines) if lines else "Репозиторий пуст"

    def get_file_content(
        self,
        repo_name: str,
        file_path: str,
        branch: str | None = None,
    ) -> str | None:
        """
        Получить содержимое файла.

        Args:
            repo_name: Имя репозитория
            file_path: Путь к файлу
            branch: Ветка (по умолчанию — default branch)

        Returns:
            Содержимое файла или None
        """
        repo = self.get_repo(repo_name)
        ref = branch or repo.default_branch

        try:
            content = repo.get_contents(file_path, ref=ref)
            if isinstance(content, list):
                return None  # Это директория
            return content.decoded_content.decode("utf-8")
        except Exception:
            return None

    def get_config_files(self, repo_name: str) -> dict[str, str]:
        """
        Получить содержимое конфигурационных файлов проекта.

        Помогает понять стек технологий.
        """
        configs = {}
        for config_file in self.CONFIG_FILES:
            if "*" in config_file:
                continue  # Пропускаем паттерны
            content = self.get_file_content(repo_name, config_file)
            if content:
                # Ограничиваем размер для промпта
                if len(content) > 2000:
                    content = content[:2000] + "\n... (truncated)"
                configs[config_file] = content
        return configs

    def find_related_files(
        self,
        repo_name: str,
        issue: IssueData,
        max_files: int = 5,
    ) -> dict[str, str]:
        """
        Найти файлы, связанные с Issue.

        Ищет упоминания путей в тексте Issue.
        """
        import re

        related = {}
        text = f"{issue.title} {issue.body}"

        # Ищем пути к файлам (любые расширения)
        # Паттерн: слова с / или . внутри, заканчивающиеся на расширение
        patterns = [
            r"[a-zA-Z0-9_\-/]+\.[a-zA-Z0-9]+",  # path/to/file.ext
            r"`([^`]+\.[a-zA-Z0-9]+)`",  # `file.ext` в backticks
        ]

        found_paths = set()
        for pattern in patterns:
            matches = re.findall(pattern, text)
            found_paths.update(matches)

        # Пробуем получить каждый файл
        for path in list(found_paths)[: max_files * 2]:
            # Очищаем путь
            path = path.strip("`'\"")
            if not path or path.startswith("http"):
                continue

            content = self.get_file_content(repo_name, path)
            if content:
                # Ограничиваем размер
                if len(content) > 5000:
                    content = content[:5000] + "\n... (truncated)"
                related[path] = content

                if len(related) >= max_files:
                    break

        return related
