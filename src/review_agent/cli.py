"""CLI для Review Agent."""

import click


@click.command()
@click.option("--repo", required=True, help="GitHub репозиторий (owner/repo)")
@click.option("--pr", required=True, type=int, help="Номер Pull Request")
def main(repo: str, pr: int) -> None:
    """Review Agent - анализирует PR и публикует результаты ревью."""
    click.echo("🔍 Review Agent запущен")
    click.echo(f"   Репозиторий: {repo}")
    click.echo(f"   PR: #{pr}")
    click.echo("✅ Заглушка работает! Реализация в следующем этапе.")


if __name__ == "__main__":
    main()
