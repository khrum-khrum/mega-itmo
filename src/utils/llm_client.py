"""Клиент для работы с LLM (Large Language Models)."""

import json
import os
import re
from dataclasses import dataclass, field

from dotenv import load_dotenv
from openrouter import OpenRouter
from openrouter.errors import (
    BadGatewayResponseError,
    BadRequestResponseError,
    ChatError,
    EdgeNetworkTimeoutResponseError,
    InternalServerResponseError,
    NotFoundResponseError,
    OpenRouterDefaultError,
    PayloadTooLargeResponseError,
    PaymentRequiredResponseError,
    ProviderOverloadedResponseError,
    RequestTimeoutResponseError,
    ServiceUnavailableResponseError,
    TooManyRequestsResponseError,
    UnauthorizedResponseError,
    UnprocessableEntityResponseError,
)

load_dotenv()


@dataclass
class CodeChange:
    """Изменение в одном файле."""

    file_path: str
    content: str
    action: str = "create"  # create, update, delete

    def __str__(self) -> str:
        return f"[{self.action.upper()}] {self.file_path}"


@dataclass
class GeneratedSolution:
    """Сгенерированное решение от LLM."""

    changes: list[CodeChange] = field(default_factory=list)
    commit_message: str = ""
    explanation: str = ""
    language: str = ""  # Определённый язык проекта

    def __str__(self) -> str:
        files_str = "\n".join(f"  - {change}" for change in self.changes)
        return (
            f"📝 Commit: {self.commit_message}\n"
            f"🗣️ Язык проекта: {self.language}\n"
            f"📁 Файлы ({len(self.changes)}):\n{files_str}\n"
            f"💬 Пояснение: {self.explanation}"
        )


class LLMClient:
    """Клиент для генерации кода через LLM."""

    SYSTEM_PROMPT = """Ты — опытный software engineer, работающий с любыми языками программирования и технологиями.
Твоя задача — анализировать GitHub Issues и генерировать код для их решения.

ВАЖНО: Ты работаешь с ЛЮБЫМИ репозиториями на ЛЮБЫХ языках (Python, JavaScript, TypeScript, Go, Rust, Java, C++, и т.д.).

ПРОЦЕСС РАБОТЫ:
1. Проанализируй структуру репозитория, чтобы понять:
   - Какой язык/языки используются (по расширениям файлов, конфигам)
   - Какой стек технологий (фреймворки, библиотеки)
   - Какой стиль кода принят в проекте
   - Структуру директорий проекта

2. Изучи существующие файлы (если предоставлены), чтобы:
   - Понять паттерны и соглашения проекта
   - Использовать существующие утилиты/хелперы
   - Следовать принятому стилю именования

3. Сгенерируй решение, которое:
   - Соответствует стилю и конвенциям проекта
   - Использует правильные пути для файлов
   - Интегрируется с существующим кодом

ОПРЕДЕЛЕНИЕ ЯЗЫКА ПО ФАЙЛАМ:
- package.json, tsconfig.json, *.js, *.ts → JavaScript/TypeScript
- requirements.txt, pyproject.toml, *.py → Python
- go.mod, *.go → Go
- Cargo.toml, *.rs → Rust
- pom.xml, build.gradle, *.java → Java
- *.cpp, *.hpp, CMakeLists.txt → C++
- Gemfile, *.rb → Ruby
- composer.json, *.php → PHP

ФОРМАТ ОТВЕТА:
Верни ТОЛЬКО валидный JSON (без markdown-блоков, без ```):
{
    "language": "определённый основной язык проекта",
    "changes": [
        {
            "file_path": "путь/к/файлу.ext",
            "content": "полное содержимое файла",
            "action": "create|update|delete"
        }
    ],
    "commit_message": "тип: краткое описание на английском",
    "explanation": "что сделано и почему (на русском)"
}

ТИПЫ КОММИТОВ: feat, fix, refactor, docs, test, chore

ПРАВИЛА:
- Путь файла должен соответствовать структуре проекта
- content содержит ПОЛНОЕ содержимое файла
- Для update — верни весь файл с изменениями, не только diff
- Следуй code style проекта (отступы, кавычки, точки с запятой и т.д.)
- Добавляй комментарии/документацию согласно конвенциям языка
- Если в Issue указаны конкретные пути — используй их"""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "meta-llama/llama-3.1-70b-instruct",
    ):
        """
        Инициализация клиента.

        Args:
            api_key: API Key для OpenRouter. Если не передан, берётся из переменной окружения OPENROUTER_API_KEY.
            model: Модель для использования.
                  Примеры: meta-llama/llama-3.1-70b-instruct, anthropic/claude-3.5-sonnet, openai/gpt-4o
        """
        self.model = model
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")

        if not self.api_key:
            raise ValueError(
                "OpenRouter API key не найден. "
                "Передай его как аргумент или установи переменную OPENROUTER_API_KEY."
            )

        self._client = OpenRouter(api_key=self.api_key)

    def generate_solution(
        self,
        issue_title: str,
        issue_body: str,
        repo_structure: str,
        existing_files: dict[str, str] | None = None,
    ) -> GeneratedSolution:
        """
        Генерирует решение для Issue.

        Args:
            issue_title: Заголовок Issue
            issue_body: Текст Issue
            repo_structure: Структура файлов репозитория
            existing_files: Содержимое существующих файлов (для контекста)

        Returns:
            Сгенерированное решение
        """
        user_prompt = self._build_prompt(issue_title, issue_body, repo_structure, existing_files)

        try:
            response = self._client.chat.send(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=4096,
            )

            content = response.choices[0].message.content
            return self._parse_response(content)

        except UnauthorizedResponseError as e:
            error_msg = e.data.error.message if hasattr(e.data, "error") else str(e)
            raise RuntimeError(f"Authentication failed: {error_msg}") from e

        except PaymentRequiredResponseError as e:
            error_msg = e.data.error.message if hasattr(e.data, "error") else str(e)
            raise RuntimeError(f"Insufficient credits: {error_msg}") from e

        except TooManyRequestsResponseError as e:
            error_msg = e.data.error.message if hasattr(e.data, "error") else str(e)
            raise RuntimeError(f"Rate limited: {error_msg}") from e

        except BadRequestResponseError as e:
            error_msg = e.data.error.message if hasattr(e.data, "error") else str(e)
            raise RuntimeError(f"Invalid request: {error_msg}") from e

        except ProviderOverloadedResponseError as e:
            error_msg = e.data.error.message if hasattr(e.data, "error") else str(e)
            raise RuntimeError(f"Provider overloaded, try again later: {error_msg}") from e

        except InternalServerResponseError as e:
            error_msg = e.data.error.message if hasattr(e.data, "error") else str(e)
            raise RuntimeError(f"Server error: {error_msg}") from e

        except BadGatewayResponseError as e:
            error_msg = e.data.error.message if hasattr(e.data, "error") else str(e)
            raise RuntimeError(f"Bad gateway: {error_msg}") from e

        except ServiceUnavailableResponseError as e:
            error_msg = e.data.error.message if hasattr(e.data, "error") else str(e)
            raise RuntimeError(f"Service unavailable: {error_msg}") from e

        except NotFoundResponseError as e:
            error_msg = e.data.error.message if hasattr(e.data, "error") else str(e)
            raise RuntimeError(f"Model not found: {error_msg}") from e

        except RequestTimeoutResponseError as e:
            error_msg = e.data.error.message if hasattr(e.data, "error") else str(e)
            raise RuntimeError(f"Request timeout: {error_msg}") from e

        except PayloadTooLargeResponseError as e:
            error_msg = e.data.error.message if hasattr(e.data, "error") else str(e)
            raise RuntimeError(f"Payload too large: {error_msg}") from e

        except UnprocessableEntityResponseError as e:
            error_msg = e.data.error.message if hasattr(e.data, "error") else str(e)
            raise RuntimeError(f"Unprocessable entity: {error_msg}") from e

        except EdgeNetworkTimeoutResponseError as e:
            error_msg = e.data.error.message if hasattr(e.data, "error") else str(e)
            raise RuntimeError(f"Network timeout: {error_msg}") from e

        except ChatError as e:
            error_msg = e.error.message if hasattr(e, "error") else str(e)
            raise RuntimeError(f"Chat error: {error_msg}") from e

        except OpenRouterDefaultError as e:
            raise RuntimeError(f"OpenRouter API error: {str(e)}") from e

        except Exception as e:
            raise RuntimeError(f"Unexpected error during LLM generation: {str(e)}") from e

    def _build_prompt(
        self,
        issue_title: str,
        issue_body: str,
        repo_structure: str,
        existing_files: dict[str, str] | None = None,
    ) -> str:
        """Формирует промпт для LLM."""
        prompt_parts = [
            "# ЗАДАЧА (GitHub Issue)",
            f"**Title:** {issue_title}",
            "",
            "**Description:**",
            issue_body,
            "",
            "# СТРУКТУРА РЕПОЗИТОРИЯ",
            "(используй для определения языка, стека и правильных путей)",
            "```",
            repo_structure,
            "```",
        ]

        if existing_files:
            prompt_parts.extend(
                [
                    "",
                    "# СУЩЕСТВУЮЩИЕ ФАЙЛЫ",
                    "(изучи для понимания стиля кода и контекста)",
                ]
            )
            for path, content in existing_files.items():
                # Определяем расширение для подсветки синтаксиса
                ext = path.split(".")[-1] if "." in path else ""
                prompt_parts.extend(
                    [
                        f"## {path}",
                        f"```{ext}",
                        content,
                        "```",
                        "",
                    ]
                )

        prompt_parts.extend(
            [
                "# ИНСТРУКЦИЯ",
                "1. Определи язык и стек проекта по структуре и файлам",
                "2. Сгенерируй решение, соответствующее стилю проекта",
                "3. Верни JSON в указанном формате",
            ]
        )

        return "\n".join(prompt_parts)

    def _extract_json_from_text(self, text: str) -> str | None:
        """
        Извлекает JSON из текста различных форматов.

        Поддерживает:
        - Прямой JSON
        - JSON в markdown блоках (```json ... ```)
        - JSON после reasoning текста (DeepSeek R1, o1)
        - JSON в тегах или после них
        """
        text = text.strip()

        # Способ 1: Убираем markdown блоки в начале и конце
        # Обрабатываем случай: ```json\n{...}\n```
        if text.startswith("```"):
            # Находим первую строку (```json или просто ```)
            first_newline = text.find("\n")
            if first_newline != -1:
                text = text[first_newline + 1 :]  # Убираем первую строку с ```

        if text.endswith("```"):
            text = text[:-3]  # Убираем закрывающие ```

        text = text.strip()

        # Способ 2: Regex поиск JSON в markdown блоках
        # Ищем ```json\n{...}\n``` или ```\n{...}\n```
        json_block_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, re.DOTALL)
        if json_block_match:
            return json_block_match.group(1).strip()

        # Способ 3: Если текст уже начинается с { (после удаления markdown)
        if text.startswith("{"):
            return text

        # Способ 4: Ищем JSON объект в тексте (между { и })
        # Используем regex для поиска валидного JSON объекта
        json_match = re.search(r"\{[\s\S]*\}", text, re.DOTALL)
        if json_match:
            potential_json = json_match.group(0)
            # Проверяем, что это валидный JSON
            try:
                json.loads(potential_json)
                return potential_json
            except json.JSONDecodeError:
                # Если не валидный, пробуем найти более точный JSON
                pass

        return None

    def _parse_response(self, content: str) -> GeneratedSolution:
        """
        Парсит ответ LLM в структурированный формат.

        Поддерживает различные форматы ответов:
        - Прямой JSON (GPT, Claude, Llama)
        - JSON в markdown блоках
        - Reasoning + JSON (DeepSeek R1, o1, QwQ)
        """
        original_content = content
        content = content.strip()

        # Извлекаем JSON из различных форматов
        json_str = self._extract_json_from_text(content)

        if not json_str:
            return GeneratedSolution(
                changes=[],
                commit_message="error: failed to extract JSON from response",
                explanation=(
                    f"Не удалось найти JSON в ответе модели.\n\n"
                    f"Ответ LLM (первые 1000 символов):\n{original_content[:1000]}..."
                ),
            )

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            return GeneratedSolution(
                changes=[],
                commit_message="error: failed to parse LLM response",
                explanation=(
                    f"Ошибка парсинга JSON: {e}\n\n"
                    f"Извлечённый JSON (первые 500 символов):\n{json_str[:500]}...\n\n"
                    f"Полный ответ LLM (первые 1000 символов):\n{original_content[:1000]}..."
                ),
            )

        changes = []
        for change_data in data.get("changes", []):
            changes.append(
                CodeChange(
                    file_path=change_data.get("file_path", ""),
                    content=change_data.get("content", ""),
                    action=change_data.get("action", "create"),
                )
            )

        return GeneratedSolution(
            changes=changes,
            commit_message=data.get("commit_message", "chore: update code"),
            explanation=data.get("explanation", ""),
            language=data.get("language", "unknown"),
        )
