"""Основная логика Code Agent."""

from dataclasses import dataclass, field

from src.utils.github_client import GitHubClient, IssueData
from src.utils.llm_client import GeneratedSolution, LLMClient


@dataclass
class AgentContext:
    """Контекст для работы агента."""

    repo_name: str
    issue: IssueData
    repo_structure: str
    config_files: dict[str, str] = field(default_factory=dict)
    related_files: dict[str, str] = field(default_factory=dict)

    @property
    def all_context_files(self) -> dict[str, str]:
        """Все файлы для контекста LLM."""
        return {**self.config_files, **self.related_files}


class CodeAgent:
    """
    Агент для генерации кода на основе GitHub Issues.

    Работает с любыми репозиториями и любыми языками программирования.
    """

    def __init__(
        self,
        github_client: GitHubClient,
        llm_client: LLMClient,
    ):
        """
        Инициализация агента.

        Args:
            github_client: Клиент GitHub API
            llm_client: Клиент LLM
        """
        self.github = github_client
        self.llm = llm_client

    def analyze_issue(self, repo_name: str, issue_number: int) -> AgentContext:
        """
        Анализирует Issue и собирает контекст репозитория.

        Args:
            repo_name: Имя репозитория (owner/repo)
            issue_number: Номер Issue

        Returns:
            Контекст с информацией для генерации кода
        """
        # Получаем Issue
        issue = self.github.get_issue(repo_name, issue_number)

        # Получаем структуру репозитория (для понимания проекта)
        repo_structure = self.github.get_repo_structure(repo_name)

        # Получаем конфиги (для понимания стека)
        config_files = self.github.get_config_files(repo_name)

        # Получаем файлы, упомянутые в Issue
        related_files = self.github.find_related_files(repo_name, issue)

        return AgentContext(
            repo_name=repo_name,
            issue=issue,
            repo_structure=repo_structure,
            config_files=config_files,
            related_files=related_files,
        )

    def generate_solution(self, context: AgentContext) -> GeneratedSolution:
        """
        Генерирует решение для Issue.

        Args:
            context: Контекст с информацией об Issue и репозитории

        Returns:
            Сгенерированное решение с файлами для создания/изменения
        """
        return self.llm.generate_solution(
            issue_title=context.issue.title,
            issue_body=context.issue.body,
            repo_structure=context.repo_structure,
            existing_files=context.all_context_files if context.all_context_files else None,
        )

    def create_pull_request(
        self,
        context: AgentContext,
        solution: GeneratedSolution,
    ) -> str:
        """
        Создаёт Pull Request с решением.

        Args:
            context: Контекст Issue
            solution: Сгенерированное решение

        Returns:
            URL созданного Pull Request

        Raises:
            RuntimeError: При ошибках создания PR
        """
        repo = self.github.get_repo(context.repo_name)
        base_branch = repo.default_branch
        issue_number = context.issue.number

        # Создаём имя ветки
        branch_name = f"agent/issue-{issue_number}"

        # 1. Создаём ветку
        try:
            created_ref = self.github.create_branch(
                repo_name=context.repo_name,
                branch_name=branch_name,
                source_branch=base_branch,
            )
            # Извлекаем имя ветки из ref (refs/heads/branch-name -> branch-name)
            # refs/heads/agent/issue-3 -> agent/issue-3
            if created_ref.startswith("refs/heads/"):
                actual_branch = created_ref[len("refs/heads/") :]
            else:
                actual_branch = branch_name
        except RuntimeError as e:
            raise RuntimeError(f"Не удалось создать ветку: {e}") from e

        # 2. Коммитим файлы
        changes = [
            {
                "file_path": change.file_path,
                "content": change.content,
                "action": change.action,
            }
            for change in solution.changes
        ]

        try:
            self.github.commit_files(
                repo_name=context.repo_name,
                changes=changes,
                commit_message=solution.commit_message,
                branch=actual_branch,
            )
        except RuntimeError as e:
            raise RuntimeError(f"Не удалось закоммитить файлы: {e}") from e

        # 3. Создаём Pull Request
        pr_title = f"[Agent] Fix #{issue_number}: {context.issue.title}"
        pr_body = f"""## Автоматическое решение Issue #{issue_number}

**Оригинальный Issue:** {context.issue.url}

### Описание изменений
{solution.explanation}

### Изменённые файлы
{self._format_changes_list(solution.changes)}

### Commit message
```
{solution.commit_message}
```

---

Closes #{issue_number}

*🤖 Этот Pull Request был автоматически создан Code Agent*
"""

        try:
            pr = self.github.create_pull_request(
                repo_name=context.repo_name,
                title=pr_title,
                body=pr_body,
                head_branch=actual_branch,
                base_branch=base_branch,
            )
            return pr.html_url
        except RuntimeError as e:
            raise RuntimeError(f"Не удалось создать Pull Request: {e}") from e

    def _format_changes_list(self, changes: list) -> str:
        """Форматирует список изменений для PR описания."""
        lines = []
        for change in changes:
            action_emoji = {"create": "✨", "update": "📝", "delete": "🗑️"}.get(change.action, "📄")
            lines.append(f"- {action_emoji} `{change.file_path}` ({change.action})")
        return "\n".join(lines)
