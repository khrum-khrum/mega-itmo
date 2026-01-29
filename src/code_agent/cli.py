"""CLI для Code Agent."""

import click


@click.command()
@click.option("--repo", required=True, help="GitHub репозиторий (owner/repo)")
@click.option("--issue", required=True, type=int, help="Номер Issue")
@click.option("--dry-run", is_flag=True, help="Только показать, что будет сделано")
def main(repo: str, issue: int, dry_run: bool) -> None:
    """Code Agent - анализирует Issue и создаёт PR с решением."""
    click.echo("🤖 Code Agent запущен")
    click.echo(f"   Репозиторий: {repo}")
    click.echo(f"   Issue: #{issue}")
    click.echo(f"   Dry run: {dry_run}")
    click.echo("✅ Заглушка работает! Реализация в следующем этапе.")


if __name__ == "__main__":
    main()
