"""Основная логика Code Agent."""
from dataclasses import dataclass, field

from src.utils.github_client import GitHubClient, IssueData
from src.utils.llm_client import LLMClient, GeneratedSolution


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
