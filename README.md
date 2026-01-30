# mega-itmo
Мегашкола ИТМО 2026, Трек "Coding Agents"

Автоматизированная агентная система для полного цикла разработки (SDLC) в GitHub на основе **LangChain**.

## Режимы работы

Система поддерживает два режима работы:

### 1. CLI режим (для разработки и тестирования)
Запуск агентов вручную через командную строку для тестирования и отладки.

### 2. GitHub App режим (для продакшена)
Автоматическая обработка Issues и PR через webhooks GitHub:
- Автоматическая обработка новых Issues
- Автоматическое реагирование на PR reviews
- Развертывание в Docker контейнерах
- Готов к деплою на удаленном сервере

**Подробная инструкция по настройке GitHub App:** См. [GITHUB_APP_SETUP.md](./GITHUB_APP_SETUP.md)

## Возможности

### Code Agent
- **LangChain Agent** — автономный агент с 9 кастомными инструментами
- **Клонирование репозиториев** — работа с локальными копиями для быстрого доступа
- **Умное исследование** — динамическое изучение кодовой базы
- **Кастомные инструменты** — чтение файлов, поиск кода, создание/изменение файлов, запуск тестов
- **Универсальность** — работает с ЛЮБЫМ языком программирования
- **Итеративное решение** — до 20 итераций для сложных задач
- **Автоматические PR** — создание Pull Request с подробным описанием

### Review Agent
- **Автоматический ревью кода** — анализ изменений в Pull Request
- **Конструктивная обратная связь** — выявление багов, уязвимостей, проблем с производительностью
- **Проверка соответствия** — сравнение реализации с требованиями Issue
- **Анализ сложности** — оценка качества и сложности кода
- **Интеграция с GitHub** — публикация ревью непосредственно в PR

## Архитектура

```
Пользователь (GitHub Issue)
         ↓
    Клонирование репозитория (GitPython)
         ↓
    LangChain Agent с инструментами
         ↓
    Автономные изменения кода
         ↓
    Git commit & push
         ↓
    Создание Pull Request
```

## Быстрый старт

### Локально

```bash
# Клонируем репозиторий
git clone <repo-url>
cd mega-itmo

# Создаём окружение
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Настраиваем переменные
cp .env.example .env
# Заполни .env своими ключами:
# GITHUB_TOKEN=your_token
# OPENROUTER_API_KEY=your_key

# Запускаем Code Agent
python -m src.code_agent.cli --repo owner/repo --issue 123

# С подробным выводом
python -m src.code_agent.cli --repo owner/repo --issue 123 -v

# Создать PR автоматически
python -m src.code_agent.cli --repo owner/repo --issue 123 --execute

# Запускаем Review Agent
python -m src.review_agent.cli --repo owner/repo --pr 456

# Dry-run ревью (без публикации в GitHub)
python -m src.review_agent.cli --repo owner/repo --pr 456 -v

# Опубликовать ревью в GitHub
python -m src.review_agent.cli --repo owner/repo --pr 456 --execute

# Или через Makefile
make run-example  # Code Agent
make run-review-example REPO=owner/repo PR=456  # Review Agent
```

### Docker (GitHub App режим - РЕКОМЕНДУЕТСЯ)

```bash
# Настраиваем переменные
cp .env.example .env
# Заполни .env своими ключами:
# GITHUB_TOKEN, OPENROUTER_API_KEY, GITHUB_WEBHOOK_SECRET

# Запускаем Code Agent API
docker-compose up -d

# Проверяем статус
docker-compose ps

# Смотрим логи
docker-compose logs -f code-agent-api

# Проверяем здоровье сервиса
curl http://localhost:8000/health
```

**После запуска:**
1. API будет доступен на `http://localhost:8000`
2. Настрой GitHub App согласно [GITHUB_APP_SETUP.md](./GITHUB_APP_SETUP.md)
3. Подключи webhook к твоему серверу
4. Создавай Issues - система автоматически создаст PR!

## Использование разных моделей

Система использует OpenRouter для доступа к 300+ моделям AI:

```bash
# Llama 3.1 70B (по умолчанию)
python -m src.code_agent.cli --repo owner/repo --issue 123

# Claude 3.5 Sonnet
python -m src.code_agent.cli --repo owner/repo --issue 123 \
  --model anthropic/claude-3.5-sonnet

# GPT-4o
python -m src.code_agent.cli --repo owner/repo --issue 123 \
  --model openai/gpt-4o
```

## Как это работает

1. **Получение Issue**: Загрузка данных Issue через GitHub API
2. **Клонирование репозитория**: Клонирование в временную директорию
3. **Инициализация агента**: Создание LangChain агента с 9 инструментами
4. **Автономное исследование**:
   - Изучение структуры репозитория (`get_file_tree`, `list_directory`)
   - Чтение релевантных файлов (`read_file`)
   - Поиск паттернов в коде (`search_code`)
5. **Реализация**:
   - Создание/изменение/удаление файлов
   - Опционально запуск тестов (`run_command`)
   - Проверка изменений (`get_git_diff`)
6. **Commit & Push**: Создание новой ветки и отправка изменений
7. **Создание PR**: Генерация Pull Request с подробным описанием
8. **Очистка**: Сохранение клонированного репозитория для повторного использования

## Структура проекта

```
mega-itmo/
├── src/
│   ├── code_agent/
│   │   ├── agent.py           # Основная логика Code Agent
│   │   ├── cli.py             # CLI для Code Agent
│   │   └── tools.py           # 9 кастомных инструментов для разработки
│   ├── review_agent/
│   │   ├── agent.py           # Основная логика Review Agent
│   │   ├── cli.py             # CLI для Review Agent
│   │   └── tools.py           # 4 инструмента для ревью кода
│   └── utils/
│       ├── github_client.py   # GitHub API & Git операции
│       └── langchain_llm.py   # Обёртка LangChain агента
├── requirements.txt           # Зависимости Python
├── Makefile                   # Удобные команды
├── CLAUDE.md                  # Подробная документация
└── README.md                  # Этот файл
```

## Инструменты агентов

### Code Agent (9 инструментов)

| Инструмент | Описание |
|------------|----------|
| `read_file` | Чтение содержимого файла |
| `list_directory` | Список файлов и директорий |
| `search_code` | Поиск по коду через regex |
| `get_file_tree` | Древо структуры репозитория |
| `create_file` | Создание новых файлов |
| `update_file` | Обновление существующих файлов |
| `delete_file` | Удаление файлов |
| `run_command` | Выполнение shell команд |
| `get_git_diff` | Просмотр изменений git |

### Review Agent (4 инструмента)

| Инструмент | Описание |
|------------|----------|
| `read_pr_file` | Чтение файлов из PR для анализа |
| `search_code_in_pr` | Поиск связанного кода и паттернов |
| `run_test_command` | Запуск тестов и проверок |
| `analyze_pr_complexity` | Анализ сложности измененных файлов |

## Требования

### Обязательные переменные окружения

```bash
GITHUB_TOKEN=ghp_xxxxxxxxxxxxx      # GitHub Personal Access Token
OPENROUTER_API_KEY=sk-or-xxxxx     # OpenRouter API Key
```

**Разрешения:**
- `GITHUB_TOKEN`: токен с правами `repo` и `workflow`
- `OPENROUTER_API_KEY`: получить на https://openrouter.ai/keys

### Опциональные переменные

```bash
GITHUB_REPO=owner/repo  # Репозиторий по умолчанию
```

## Разработка

### Линтинг и форматирование

```bash
# Проверка линтером
ruff check src/

# Автоисправление
ruff check --fix src/

# Форматирование
black src/

# Проверка типов
mypy src/
```

### Тестирование

```bash
# Запуск тестов
pytest

# С покрытием
pytest --cov=src --cov-report=html
```

## Troubleshooting

**Ошибка: OpenRouter API key not found**
- Установи `OPENROUTER_API_KEY` в файле `.env`

**Ошибка: GitHub token not found**
- Установи `GITHUB_TOKEN` в `.env` с правами `repo` и `workflow`

**Ошибка: Permission denied**
- Убедись, что GitHub токен имеет права на запись в репозиторий

**Агент делает неправильные изменения**
- Попробуй более мощную модель (например, Claude 3.5 Sonnet)
- Используй verbose режим (`-v`) для просмотра рассуждений агента

## Технологии

- [LangChain](https://langchain.com/) - Фреймворк для агентов
- [OpenRouter](https://openrouter.ai/) - Доступ к LLM API
- [PyGithub](https://github.com/PyGithub/PyGithub) - GitHub API
- [GitPython](https://github.com/gitpython-developers/GitPython) - Git операции

## Лицензия

См. файл LICENSE для подробностей.
