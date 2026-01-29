"""Клиент для работы с GitHub API."""

import os
import time
from dataclasses import dataclass

from dotenv import load_dotenv
from github import Github, GithubException
from github.Issue import Issue
from github.PullRequest import PullRequest
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

    def create_branch(
        self,
        repo_name: str,
        branch_name: str,
        source_branch: str | None = None,
    ) -> str:
        """
        Создать новую ветку в репозитории.

        Args:
            repo_name: Имя репозитория
            branch_name: Имя новой ветки (без refs/heads/)
            source_branch: Исходная ветка (по умолчанию — default branch)

        Returns:
            Полный ref созданной ветки

        Raises:
            RuntimeError: Если ветка уже существует или нет прав
        """
        repo = self.get_repo(repo_name)
        source = source_branch or repo.default_branch

        try:
            # Получаем SHA коммита исходной ветки
            source_branch_obj = repo.get_branch(source)
            source_sha = source_branch_obj.commit.sha

            # Создаём новую ветку
            ref = repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=source_sha)
            return ref.ref

        except GithubException as e:
            if e.status == 422:
                # Ветка уже существует, пробуем добавить суффикс
                timestamp = int(time.time())
                new_branch_name = f"{branch_name}-{timestamp}"
                try:
                    ref = repo.create_git_ref(ref=f"refs/heads/{new_branch_name}", sha=source_sha)
                    return ref.ref
                except GithubException:
                    raise RuntimeError(
                        f"Не удалось создать ветку {branch_name} или {new_branch_name}"
                    ) from e
            elif e.status == 403:
                raise RuntimeError(f"Нет прав для создания ветки в репозитории {repo_name}") from e
            else:
                raise RuntimeError(f"Ошибка создания ветки: {e.data.get('message', str(e))}") from e

    def commit_files(
        self,
        repo_name: str,
        changes: list[dict[str, str]],
        commit_message: str,
        branch: str,
    ) -> None:
        """
        Закоммитить изменения файлов в ветку.

        Args:
            repo_name: Имя репозитория
            changes: Список изменений
                [{"file_path": str, "content": str, "action": "create|update|delete"}]
            commit_message: Сообщение коммита
            branch: Ветка для коммита

        Raises:
            RuntimeError: При ошибках коммита
        """
        repo = self.get_repo(repo_name)

        for change in changes:
            file_path = change["file_path"]
            content = change["content"]
            action = change["action"]

            try:
                if action == "create":
                    # Создаём новый файл
                    repo.create_file(
                        path=file_path,
                        message=commit_message,
                        content=content,
                        branch=branch,
                    )

                elif action == "update":
                    # Обновляем существующий файл
                    # Сначала получаем SHA файла
                    file_content = repo.get_contents(file_path, ref=branch)
                    if isinstance(file_content, list):
                        raise RuntimeError(f"{file_path} является директорией, не файлом")

                    repo.update_file(
                        path=file_path,
                        message=commit_message,
                        content=content,
                        sha=file_content.sha,
                        branch=branch,
                    )

                elif action == "delete":
                    # Удаляем файл
                    file_content = repo.get_contents(file_path, ref=branch)
                    if isinstance(file_content, list):
                        raise RuntimeError(f"{file_path} является директорией, не файлом")

                    repo.delete_file(
                        path=file_path,
                        message=commit_message,
                        sha=file_content.sha,
                        branch=branch,
                    )

                else:
                    raise ValueError(f"Неизвестное действие: {action}")

            except GithubException as e:
                if e.status == 404:
                    if action == "update":
                        raise RuntimeError(
                            f"Файл {file_path} не найден для обновления. "
                            f"Возможно, он был удалён или изменён."
                        ) from e
                    elif action == "delete":
                        # Файл уже удалён, можно игнорировать
                        continue
                    else:
                        # 404 при создании файла может означать что ветка не найдена
                        error_msg = e.data.get("message", str(e)) if hasattr(e, "data") else str(e)
                        raise RuntimeError(
                            f"Ошибка при создании файла {file_path}. "
                            f"Возможно, ветка '{branch}' не существует. "
                            f"Детали: {error_msg}"
                        ) from e
                elif e.status == 409:
                    raise RuntimeError(
                        f"Конфликт при изменении {file_path}. "
                        f"Файл был изменён с момента анализа."
                    ) from e
                elif e.status == 403:
                    raise RuntimeError(f"Нет прав для изменения {file_path}") from e
                else:
                    raise RuntimeError(
                        f"Ошибка при {action} файла {file_path}: {e.data.get('message', str(e))}"
                    ) from e

    def create_pull_request(
        self,
        repo_name: str,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str | None = None,
    ) -> PullRequest:
        """
        Создать Pull Request.

        Args:
            repo_name: Имя репозитория
            title: Заголовок PR
            body: Описание PR
            head_branch: Ветка с изменениями
            base_branch: Целевая ветка (по умолчанию — default branch)

        Returns:
            Созданный Pull Request

        Raises:
            RuntimeError: При ошибках создания PR
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
                        f"Pull Request из {head_branch} в {base} уже существует"
                    ) from e
                elif "no commits between" in error_message.lower():
                    raise RuntimeError(f"Нет изменений между {base} и {head_branch}") from e
                else:
                    raise RuntimeError(f"Ошибка валидации: {error_message}") from e
            elif e.status == 403:
                raise RuntimeError(f"Нет прав для создания Pull Request в {repo_name}") from e
            else:
                raise RuntimeError(
                    f"Ошибка создания Pull Request: {e.data.get('message', str(e))}"
                ) from e
