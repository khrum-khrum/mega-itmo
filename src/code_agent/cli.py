"""CLI для Code Agent."""

import sys

import click

from src.utils.github_client import GitHubClient


@click.command()
@click.option(
    "--repo",
    required=True,
    help="GitHub репозиторий в формате owner/repo",
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
    help="GitHub Personal Access Token (или переменная GITHUB_TOKEN)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Только показать информацию, не вносить изменения",
)
@click.option(
    "--show-structure",
    is_flag=True,
    help="Показать структуру репозитория",
)
def main(
    repo: str,
    issue: int,
    token: str | None,
    dry_run: bool,
    show_structure: bool,
) -> None:
    """
    Code Agent - анализирует Issue и создаёт PR с решением.

    Примеры использования:

        # Прочитать Issue
        python -m src.code_agent.cli --repo owner/repo --issue 1

        # Показать структуру репозитория
        python -m src.code_agent.cli --repo owner/repo --issue 1 --show-structure
    """
    click.echo("🤖 Code Agent запущен\n")

    # Инициализируем клиент
    try:
        client = GitHubClient(token=token)
    except ValueError as e:
        click.echo(f"❌ Ошибка: {e}", err=True)
        sys.exit(1)

    # Получаем Issue
    click.echo(f"📋 Загружаю Issue #{issue} из {repo}...")
    try:
        issue_data = client.get_issue(repo, issue)
    except Exception as e:
        click.echo(f"❌ Не удалось получить Issue: {e}", err=True)
        sys.exit(1)

    click.echo("\n" + "=" * 50)
    click.echo(str(issue_data))
    click.echo("=" * 50 + "\n")

    # Показываем структуру репозитория
    if show_structure:
        click.echo("📁 Структура репозитория:")
        click.echo("-" * 30)
        structure = client.get_repo_structure(repo)
        click.echo(structure)
        click.echo("-" * 30 + "\n")

    if dry_run:
        click.echo("ℹ️  Режим dry-run: изменения не вносятся")

    click.echo("✅ Issue успешно загружен!")
    click.echo("\n🚧 Генерация кода будет реализована в следующем этапе.")


if __name__ == "__main__":
    main()
