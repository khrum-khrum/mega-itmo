# Финальный отчет по проекту: AI-Powered SDLC Automation

## Мегашкола ИТМО 2026, Трек "Coding Agents"

---

## Оглавление

1. [Обзор проекта](#обзор-проекта)
2. [Архитектура и технологии](#архитектура-и-технологии)
3. [Два независимых агента](#два-независимых-агента)
4. [Режимы работы: CLI и облачное развертывание](#режимы-работы-cli-и-облачное-развертывание)
5. [Интеграция с GitHub через Webhooks](#интеграция-с-github-через-webhooks)
6. [Качество и тестирование](#качество-и-тестирование)
7. [Направления для улучшения](#направления-для-улучшения)
8. [Заключение](#заключение)

---

## Обзор проекта

[Ссылка на задание](https://docs.google.com/document/d/1JIRdWHDSp1RsT7A0_wlADy_4lTHEg-DwoeIjSjB4MBo/edit?tab=t.0#heading=h.ess5k7fvs5zw)

[Ссылка на питч](https://drive.google.com/file/d/1EbgpbNtI6KWY-YZNkeblTyDxq1YMztPB/view?usp=share_link)

Разработана полноценная автоматизированная система для Software Development Lifecycle (SDLC) на базе LangChain, которая способна автономно решать задачи полного цикла разработки в GitHub:

- **Анализ Issues** — понимание требований и контекста задачи
- **Автономная разработка** — исследование кодовой базы, внесение изменений
- **Создание Pull Requests** — оформление и публикация изменений
- **Code Review** — автоматический анализ и проверка качества кода
- **Итеративная разработка** — обработка feedback и улучшение решения

Система работает с **любым языком программирования** и может быть подключена к **любому репозиторию на GitHub** через облачное развертывание.

---

## Архитектура и технологии

### Технологический стек

#### LangChain Framework
Система построена на базе **LangChain** — современного фреймворка для создания агентных систем:

- **`create_tool_calling_agent`** — базовая архитектура агента с поддержкой вызова инструментов
- **`AgentExecutor`** — оркестрация выполнения агента с управлением итерациями (до 20 итераций для сложных задач)
- **Custom Tools** — интеграция кастомных инструментов через декоратор `@tool`
- **OpenAI-compatible LLM Integration** — подключение к различным LLM через единый интерфейс

#### Инструменты агентов (Tools)

Система использует два набора специализированных инструментов:

**Code Agent Tools (9 инструментов):**
```python
# Исследование кодовой базы
- read_file           # Чтение содержимого файла
- list_directory      # Получение списка файлов в директории
- search_code         # Regex-поиск по файлам
- get_file_tree       # Древовидная структура репозитория

# Модификация кода
- create_file         # Создание новых файлов
- update_file         # Обновление существующих файлов
- delete_file         # Удаление файлов

# Проверка и тестирование
- run_command         # Выполнение shell команд (тесты, линтеры)
- get_git_diff        # Просмотр изменений через Git
```

**Review Agent Tools (6 инструментов):**
```python
# Анализ Pull Request
- read_pr_file              # Чтение измененных файлов
- search_code_in_pr         # Поиск связанного кода и паттернов
- fetch_issue_details       # Получение требований из исходного Issue
- run_test_command          # Запуск тестов (обязательный этап)
- analyze_pr_complexity     # Анализ метрик сложности кода
- query_library_docs        # Запрос актуальной документации библиотек (Context7 MCP)
```

#### GitHub Integration

**PyGithub** — работа с GitHub API:
- Получение Issues и Pull Requests
- Создание комментариев и reviews
- Работа с webhooks (верификация HMAC SHA-256)

**GitPython** — локальные Git операции:
- Клонирование репозиториев (shallow clone для оптимизации)
- Управление ветками и коммитами
- Push/Pull операции
- Умное переиспользование клонированных репозиториев

#### LLM Providers

Система поддерживает множество провайдеров LLM через OpenAI-compatible API:

- **OpenRouter** (по умолчанию) — доступ к 300+ моделям:
  - Llama 3.3 70B Versatile (default)
  - Claude 3.5 Sonnet
  - GPT-4o
  - Gemini Pro 1.5
  - И другие модели

- **Groq** — быстрый inference с open-source моделями
- **OpenAI** — прямое подключение к GPT моделям
- **Custom** — любой OpenAI-совместимый API endpoint

#### API и веб-сервисы

**FastAPI** — два независимых REST API:
- Асинхронная обработка запросов
- OpenAPI/Swagger документация
- Webhook endpoint'ы для GitHub
- Background tasks для долгих операций

**Docker & Docker Compose** — контейнеризация:
- Отдельные Dockerfile для каждого агента
- Docker Compose для оркестрации сервисов
- Готовность к production deployment

### Архитектура данных

Система использует строго типизированные структуры данных (Python dataclasses):

```python
@dataclass
class IssueData:
    """Представление GitHub Issue"""
    number: int
    title: str
    body: str
    labels: List[str]
    state: str
    url: str

@dataclass
class PRData:
    """Представление Pull Request с комментариями"""
    number: int
    title: str
    body: str
    state: str
    url: str
    base_branch: str
    head_branch: str
    comments: List[PRCommentData]

@dataclass
class AgentResult:
    """Результат работы агента"""
    success: bool
    output: str
    repo_path: str
    branch_name: str
    error: Optional[str]
```

---

## Два независимых агента

Ключевая архитектурная особенность проекта — **два полностью независимых агента**, которые работают как отдельные системы:

### Code Agent — Агент разработки

**Назначение:** Автономная реализация решений для GitHub Issues

**Ключевые возможности:**
- Анализ требований из Issue
- Исследование структуры репозитория
- Автономное внесение изменений в код
- Создание Pull Requests с автолинковкой к Issue
- Итеративная разработка (обработка review feedback)

**Рабочий процесс:**
```
Issue → Clone Repository → Explore Codebase →
Implement Changes → Run Tests → Commit & Push → Create PR
```

**Уникальная фича — итеративная разработка:**
```bash
# Первый запуск - создание PR
python -m src.code_agent.cli --repo owner/repo --issue 123 --execute

# После получения review - обработка feedback
python -m src.code_agent.cli --repo owner/repo --issue 123 --pr 456 --execute
```

При наличии флага `--pr`, агент:
- Извлекает все комментарии из PR (inline comments, review comments, issue comments)
- Анализирует feedback с учетом контекста
- Вносит изменения для устранения замечаний
- Добавляет новые коммиты в существующую ветку

### Review Agent — Агент код-ревью

**Назначение:** Автоматический анализ Pull Requests с проверкой соответствия требованиям

**Ключевые возможности:**
- Извлечение и анализ требований из связанного Issue
- Проверка полноты реализации всех требований
- **Обязательный запуск тестов** — критический этап проверки
- Анализ безопасности (SQL injection, XSS, и др.)
- Проверка качества кода и best practices
- Публикация детального feedback в виде комментариев

**Рабочий процесс:**
```
PR Opened → Fetch Issue Requirements → Clone & Checkout PR Branch →
Read Changed Files → Run Tests → Analyze Code Quality →
Submit Review Feedback
```

**Типы вердиктов:**
- **READY TO MERGE** — все требования выполнены, тесты проходят, высокое качество
- **NEEDS CHANGES** — тесты падают, недостающие требования, баги, проблемы безопасности
- **REQUIRES DISCUSSION** — минорные предложения, вопросы, уточнения

**Важно:** Review Agent использует GitHub API для публикации комментариев (event type: COMMENT), а не формальных approve/reject, чтобы избежать проблем с self-approval.

### Независимость агентов

Агенты являются **полностью автономными системами**:

1. **Разная кодовая база:**
   - `src/code_agent/` — модули Code Agent
   - `src/review_agent/` — модули Review Agent
   - `src/utils/` — общие утилиты (GitHub client, LangChain wrapper)

2. **Независимые API:**
   - Code Agent API: порт 8000 (`src/api/main.py`)
   - Review Agent API: порт 8001 (`src/review_api/main.py`)

3. **Разные webhook events:**
   - Code Agent: `issues`, `pull_request_review`, `pull_request_review_comment`, `issue_comment`
   - Review Agent: `pull_request` (actions: opened, synchronize)

4. **Независимое развертывание:**
   - Отдельные Dockerfile (`Dockerfile` и `Dockerfile.review`)
   - Могут быть развернуты на разных серверах
   - Независимое масштабирование

5. **Общая кодовая база для переиспользования:**
   - `src/utils/github_client.py` — единый клиент для работы с GitHub
   - `src/utils/langchain_llm.py` — обертка для LangChain агента
   - Shared data structures (`IssueData`, `PRData`, etc.)

---

## Режимы работы: CLI и облачное развертывание

Одна из **ключевых особенностей проекта** — возможность работы как локально (CLI), так и в облаке (GitHub Apps).

### CLI режим (для разработки и тестирования)

**Code Agent CLI:**
```bash
# Базовый запуск (dry-run)
python -m src.code_agent.cli --repo owner/repo --issue 123

# С подробным выводом (verbose)
python -m src.code_agent.cli --repo owner/repo --issue 123 -v

# Execute mode (создание PR)
python -m src.code_agent.cli --repo owner/repo --issue 123 --execute

# Итеративная разработка (обработка review)
python -m src.code_agent.cli --repo owner/repo --issue 123 --pr 456 --execute

# Использование разных моделей
python -m src.code_agent.cli --repo owner/repo --issue 123 \
  --model anthropic/claude-3.5-sonnet --execute
```

**Review Agent CLI:**
```bash
# Dry-run режим (без публикации в GitHub)
python -m src.review_agent.cli --repo owner/repo --pr 456

# Execute mode (публикация review)
python -m src.review_agent.cli --repo owner/repo --pr 456 --execute

# Использование переменных окружения
export GITHUB_REPO=owner/repo
export PR_NUMBER=456
python -m src.review_agent.cli --execute
```

### Облачное развертывание (Production-ready)

**Критическая фича:** Система развернута в **Yandex Cloud** в виде двух **независимых GitHub приложений**, которые можно подключить к **ЛЮБОМУ репозиторию** на GitHub.

#### GitHub Apps — глобальная доступность

1. **Code Agent GitHub App**
   - **URL приложения:** https://github.com/apps/coding-agent-itmo-egor
   - **Webhook Events:** issues, pull_request_review, pull_request_review_comment, issue_comment
   - **Функционал:**
     - Автоматически реагирует на открытые/переоткрытые Issues
     - Создает Pull Requests для решения задач
     - Обрабатывает review feedback и обновляет PR
   - **Permissions:** Contents (read), Issues (read/write), Pull requests (read/write)

2. **Review Agent GitHub App**
   - **URL приложения:** https://github.com/apps/review-agent-itmo-egor
   - **Webhook Events:** pull_request (opened, synchronize)
   - **Функционал:**
     - Автоматически анализирует новые Pull Requests
     - Проверяет соответствие требованиям Issue
     - Запускает тесты и публикует feedback
   - **Permissions:** Contents (read), Issues (read), Pull requests (read/write)

#### Примеры работы в production

**Тестовый репозиторий с примерами:**

1. **Пример работы Code Agent:**
   - Issue: https://github.com/khrum-khrum/mega-itmo-test/issues/46
   - Созданный PR: https://github.com/khrum-khrum/mega-itmo-test/pull/47

2. **Пример работы Review Agent:**
   - Issue: https://github.com/khrum-khrum/mega-itmo-test/issues/61
   - PR с review: https://github.com/khrum-khrum/mega-itmo-test/pull/62

#### Docker Compose для одновременного запуска

```bash
# Запуск обоих агентов одновременно
docker-compose up -d

# Просмотр логов
docker-compose logs -f code-agent-api
docker-compose logs -f review-agent-api

# Проверка состояния
curl http://localhost:8000/health  # Code Agent
curl http://localhost:8001/health  # Review Agent
```

**Конфигурация портов:**
- Code Agent API: `http://localhost:8000`
- Review Agent API: `http://localhost:8001`

#### Преимущества облачного развертывания

- **Plug & Play** — установка в любой репозиторий за 2 клика
- **Автоматизация** — работает без ручного вмешательства
- **Масштабируемость** — независимое масштабирование агентов
- **Мониторинг** — логи и метрики через Docker
- **Безопасность** — HMAC SHA-256 верификация webhook'ов

---

## Интеграция с GitHub через Webhooks

Система использует **webhook-driven архитектуру** для автоматической обработки событий в GitHub.

### Webhook Flow

#### Code Agent Webhook Processing

```
GitHub Event (Issue opened)
    ↓
Webhook payload → FastAPI endpoint (/webhook)
    ↓
Signature verification (HMAC SHA-256)
    ↓
Background task execution
    ↓
Code Agent processes Issue
    ↓
PR created and linked to Issue
```

**Поддерживаемые события:**
- `issues` (opened, reopened)
- `pull_request_review` (submitted)
- `pull_request_review_comment` (created)
- `issue_comment` (created)

#### Review Agent Webhook Processing

```
GitHub Event (PR opened/updated)
    ↓
Webhook payload → FastAPI endpoint (/webhook)
    ↓
Signature verification (HMAC SHA-256)
    ↓
Background task execution
    ↓
Review Agent analyzes PR
    ↓
Review feedback posted as comments
```

**Поддерживаемые события:**
- `pull_request` (opened, synchronize)

### Безопасность Webhooks

Все webhook запросы проходят **строгую верификацию**:

```python
def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Проверка GitHub webhook signature с использованием HMAC SHA-256"""
    expected_signature = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected_signature}", signature)
```

**Защита:**
- HMAC SHA-256 подпись каждого запроса
- Сравнение с использованием `hmac.compare_digest` (защита от timing attacks)
- Отклонение невалидных запросов с HTTP 403

### Background Task Execution

Агенты работают **асинхронно** через FastAPI background tasks:

```python
@app.post("/webhook")
async def handle_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    # Быстрая валидация и возврат 200 OK
    verify_webhook_signature(request)

    # Запуск агента в фоне (неблокирующий)
    background_tasks.add_task(run_agent, payload)

    return {"status": "processing"}
```

**Преимущества:**
- Webhook немедленно возвращает 200 OK (требование GitHub)
- Агент работает асинхронно без таймаутов
- Возможность обработки долгих задач (>30 секунд)

---

## Качество и тестирование

Проект разработан с акцентом на качество кода и надежность системы.

### Unit Testing

**Покрытие тестами:** Реализованы unit тесты для всех критических компонентов:

```
tests/
├── test_code_agent.py          # Тесты Code Agent
├── test_code_agent_tools.py    # Тесты инструментов Code Agent
├── test_review_agent.py        # Тесты Review Agent
├── test_github_client.py       # Тесты GitHub клиента
└── test_langchain_llm.py       # Тесты LangChain интеграции
```

**Запуск тестов:**
```bash
# Все тесты
pytest

# С покрытием кода
pytest --cov=src --cov-report=html

# Verbose режим
pytest -v
```

### Continuous Integration (CI/CD)

**GitHub Actions workflow** автоматически проверяет качество кода при каждом коммите:

```yaml
# .github/workflows/ci.yml
jobs:
  lint:
    - Ruff check (линтинг)
    - Black check (форматирование)
    - Mypy (статическая проверка типов)

  test:
    - Pytest (unit тесты)

  build:
    - Verify CLI entry points
    - Build Docker images (оба агента)
```

**Триггеры CI:**
- Каждый push в любую ветку
- Каждый Pull Request

### Code Quality Tools

**Ruff** — современный быстрый линтер:
```bash
ruff check src/
ruff check --fix src/  # Автофикс
```

**Black** — автоматическое форматирование:
```bash
black src/
black --check src/  # Проверка без изменений
```

**Mypy** — статическая проверка типов:
```bash
mypy src/
```

**Конфигурация качества:**
- Line length: 100 символов
- Python version: 3.11+
- Strict type checking enabled
- Selected Ruff rules: E, F, I, N, W, UP

### Type Safety

Весь код использует **строгую типизацию**:

```python
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

def process_issue(
    issue_data: IssueData,
    execute: bool = False
) -> AgentResult:
    """Обработка Issue с типизированными параметрами"""
    ...
```

---

## Направления для улучшения

Несмотря на полную функциональность системы, есть направления для дальнейшего развития:

### 1. Расширение возможностей агентов

**Code Agent:**
- Поддержка multi-file refactoring (рефакторинг нескольких связанных файлов)
- Интеграция с CI/CD для автоматического прогона тестов перед созданием PR
- Улучшение стратегии поиска кода (semantic search вместо regex)
- Поддержка incremental learning (обучение на предыдущих решениях в репозитории)

**Review Agent:**
- Интеграция с SAST инструментами (Bandit, Semgrep) для глубокого анализа безопасности
- Проверка test coverage для новых изменений
- Анализ производительности (профилирование изменений)
- Поддержка multi-language review (специализированные правила для каждого языка)

### 2. Оптимизация производительности

- **Кэширование embeddings** для файлов репозитория (ускорение семантического поиска)
- **Parallel tool execution** — одновременное выполнение независимых инструментов
- **Incremental cloning** — использование Git sparse-checkout для больших репозиториев
- **LLM response streaming** — потоковая передача ответов для улучшения UX

### 3. Улучшение пользовательского опыта

- **Real-time progress updates** — live статус работы агента в PR комментариях
- **Interactive mode** — возможность задавать вопросы агенту прямо в Issue/PR
- **Custom instructions** — поддержка `.github/agent-config.yml` для настройки поведения
- **Confidence scores** — оценка уверенности агента в своем решении

### 4. Расширенная аналитика

- **Metrics dashboard** — визуализация метрик работы агентов (время решения, качество, успешность)
- **Learning from feedback** — анализ паттернов rejected PR для улучшения агента
- **Cost tracking** — мониторинг затрат на LLM API calls
- **Quality trends** — отслеживание улучшения качества кода со временем

### 5. Интеграция с экосистемой

- **Jira/Linear integration** — синхронизация с task tracking системами
- **Slack/Discord notifications** — уведомления о работе агентов
- **GitLab/Bitbucket support** — поддержка других Git платформ
- **IDE plugins** — расширения для VS Code, JetBrains IDEs

### 6. Advanced AI capabilities

- **Multi-agent collaboration** — координация между несколькими специализированными агентами
- **RAG integration** — использование knowledge base репозитория для контекста
- **Fine-tuning** — дообучение моделей на специфике конкретного проекта
- **Self-improvement loop** — агент учится на собственных ошибках

### 7. Энтерпрайз фичи

- **Role-based access control** — управление правами доступа агентов
- **Audit logs** — детальное логирование всех действий для compliance
- **On-premise deployment** — поддержка деплоя в приватных сетях
- **Multi-tenancy** — изоляция данных для разных организаций

---

## Заключение

В рамках проекта была разработана **production-ready система автоматизации SDLC** на базе LangChain, которая демонстрирует:

### Ключевые достижения

- **Полный цикл разработки** — от анализа Issue до review кода
- **Независимые агенты** — Code Agent и Review Agent как отдельные системы
- **Универсальность** — работа с любым языком программирования
- **Облачная готовность** — развертывание в Yandex Cloud как GitHub Apps
- **Plug & Play** — подключение к любому репозиторию без доработок
- **Production качество** — unit тесты, CI/CD, type safety, code quality tools
- **Масштабируемость** — Docker, независимое развертывание, webhook architecture
- **Безопасность** — HMAC верификация, secure credential management

### Технологическая ценность

Проект демонстрирует глубокую интеграцию современных AI-технологий в процесс разработки ПО:

- **LangChain framework** — правильное применение агентной архитектуры
- **Tool-calling paradigm** — эффективное использование кастомных инструментов
- **Webhook-driven automation** — event-driven архитектура для GitHub интеграции
- **Multi-provider LLM support** — гибкость в выборе моделей (OpenRouter, Groq, OpenAI)
- **Cloud-native deployment** — готовность к enterprise использованию

### Практическая применимость

Система может быть немедленно использована в реальных проектах:

1. **GitHub Apps доступны по ссылкам:**
   - Code Agent: `[PLACEHOLDER_CODE_AGENT_GITHUB_APP_URL]`
   - Review Agent: `[PLACEHOLDER_REVIEW_AGENT_GITHUB_APP_URL]`

2. **Установка занимает <5 минут** — просто подключите к репозиторию

3. **Примеры работы в production:**
   - Тестовый репозиторий с демонстрацией возможностей
   - Real-world Issues и PR для изучения поведения
