"""CLI для Code Agent."""

import sys

import click

from src.code_agent.agent import CodeAgent
from src.utils.github_client import GitHubClient
from src.utils.llm_client import LLMClient


@click.command()
@click.option(
    "--repo",
    envvar="GITHUB_REPO",
    help=(
        "GitHub репозиторий в формате owner/repo (любой репозиторий). "
        "Если не указан, используется GITHUB_REPO из .env"
    ),
)
@click.option(
    "--issue",
    required=True,
    type=int,
    help="Номер Issue для обработки",
)
@click.option(
    "--token",
    envvar="GITHUB_TOKEN",
    help="GitHub Personal Access Token",
)
@click.option(
    "--api-key",
    envvar="OPENROUTER_API_KEY",
    help="OpenRouter API Key",
)
@click.option(
    "--model",
    default="meta-llama/llama-3.1-70b-instruct",
    help=(
        "Модель LLM. Примеры: meta-llama/llama-3.1-70b-instruct, "
        "anthropic/claude-3.5-sonnet, openai/gpt-4o"
    ),
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=True,
    help="Только показать сгенерированный код (по умолчанию)",
)
@click.option(
    "--execute",
    is_flag=True,
    help="Создать PR с решением (отключает dry-run)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Подробный вывод (показать контекст)",
)
def main(
    repo: str | None,
    issue: int,
    token: str | None,
    api_key: str | None,
    model: str,
    dry_run: bool,
    execute: bool,
    verbose: bool,
) -> None:
    """
    Code Agent - анализирует Issue и генерирует код для решения.

    Работает с ЛЮБЫМИ репозиториями на ЛЮБЫХ языках программирования.

    \b
    Примеры:
        # Анализ Issue с Llama (по умолчанию)
        python -m src.code_agent.cli --repo facebook/react --issue 1234

        # Использование GITHUB_REPO из .env
        python -m src.code_agent.cli --issue 1234

        # Использование другой модели
        python -m src.code_agent.cli --repo owner/repo --issue 1 --model anthropic/claude-3.5-sonnet

        # Использование GPT-4o
        python -m src.code_agent.cli --repo owner/repo --issue 1 --model openai/gpt-4o

        # С подробным выводом контекста
        python -m src.code_agent.cli --repo owner/repo --issue 1 -v

        # Создать PR (когда будет реализовано)
        python -m src.code_agent.cli --repo owner/repo --issue 1 --execute
    """
    if execute:
        dry_run = False

    if not repo:
        click.echo("❌ Ошибка: --repo не указан и GITHUB_REPO не задан в .env", err=True)
        sys.exit(1)

    click.echo("🤖 Code Agent запущен")
    click.echo(f"   Целевой репозиторий: {repo}")
    click.echo()

    # === Инициализация ===
    try:
        github_client = GitHubClient(token=token)
        click.echo("✅ GitHub клиент инициализирован")
    except ValueError as e:
        click.echo(f"❌ Ошибка GitHub: {e}", err=True)
        sys.exit(1)

    try:
        llm_client = LLMClient(api_key=api_key, model=model)
        click.echo(f"✅ LLM клиент инициализирован (OpenRouter: {model})")
    except ValueError as e:
        click.echo(f"❌ Ошибка LLM: {e}", err=True)
        sys.exit(1)

    agent = CodeAgent(github_client=github_client, llm_client=llm_client)

    # === Анализ Issue ===
    click.echo(f"\n📋 Анализирую Issue #{issue}...")

    try:
        context = agent.analyze_issue(repo, issue)
    except Exception as e:
        click.echo(f"❌ Ошибка при анализе: {e}", err=True)
        sys.exit(1)

    # Выводим информацию об Issue
    click.echo(f"\n{'='*60}")
    click.echo(f"📌 Issue #{context.issue.number}: {context.issue.title}")
    click.echo(f"🏷️  Labels: {', '.join(context.issue.labels) or 'нет'}")
    click.echo(f"🔗 {context.issue.url}")
    click.echo(f"{'='*60}")
    click.echo(f"\n{context.issue.body[:800]}{'...' if len(context.issue.body) > 800 else ''}")

    # Показываем собранный контекст
    click.echo("\n📊 Собранный контекст:")
    click.echo(f"   - Конфигурационных файлов: {len(context.config_files)}")
    click.echo(f"   - Связанных файлов: {len(context.related_files)}")

    if verbose:
        click.echo(f"\n{'─'*60}")
        click.echo("📁 Структура репозитория:")
        click.echo(f"{'─'*60}")
        click.echo(context.repo_structure[:2000])
        if len(context.repo_structure) > 2000:
            click.echo("... (truncated)")

        if context.config_files:
            click.echo(f"\n{'─'*60}")
            click.echo("⚙️ Найденные конфиги:")
            click.echo(f"{'─'*60}")
            for path in context.config_files:
                click.echo(f"   - {path}")

        if context.related_files:
            click.echo(f"\n{'─'*60}")
            click.echo("📄 Связанные файлы:")
            click.echo(f"{'─'*60}")
            for path in context.related_files:
                click.echo(f"   - {path}")

    # === Генерация решения ===
    click.echo("\n🧠 Генерирую решение...")

    try:
        solution = agent.generate_solution(context)
    except Exception as e:
        click.echo(f"❌ Ошибка генерации: {e}", err=True)
        sys.exit(1)

    # === Вывод результата ===
    click.echo(f"\n{'='*60}")
    click.echo("📦 СГЕНЕРИРОВАННОЕ РЕШЕНИЕ")
    click.echo(f"{'='*60}\n")

    click.echo(str(solution))

    # Показываем файлы
    click.echo(f"\n{'─'*60}")
    click.echo("📄 СОДЕРЖИМОЕ ФАЙЛОВ")
    click.echo(f"{'─'*60}")

    for change in solution.changes:
        click.echo(f"\n{'═'*60}")
        click.echo(f"📄 {change.file_path} [{change.action.upper()}]")
        click.echo(f"{'═'*60}")

        # Подсветка синтаксиса в терминале (просто выводим код)
        click.echo(change.content)

    # === Итог ===
    if dry_run:
        click.echo(f"\n{'─'*60}")
        click.echo("ℹ️  Режим DRY-RUN: изменения НЕ применены")
        click.echo("   Для создания PR добавь флаг --execute")
        click.echo(f"{'─'*60}")
    else:
        # === Создание Pull Request ===
        click.echo(f"\n{'='*60}")
        click.echo("🚀 СОЗДАНИЕ PULL REQUEST")
        click.echo(f"{'='*60}\n")

        try:
            pr_url = agent.create_pull_request(context, solution)
            click.echo("✅ Pull Request успешно создан!")
            click.echo(f"🔗 {pr_url}")
        except RuntimeError as e:
            click.echo(f"❌ Ошибка создания PR: {e}", err=True)
            sys.exit(1)


if __name__ == "__main__":
    main()
