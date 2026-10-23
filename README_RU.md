# Библиотека API Rate Limiter

[![CI](https://github.com/CHUKEPC/rate-limiter/actions/workflows/ci.yml/badge.svg)](https://github.com/CHUKEPC/rate-limiter/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://img.shields.io/badge/mypy-strict-blue)](https://mypy.readthedocs.io/)
[![Coverage](https://img.shields.io/badge/coverage-93%25-brightgreen.svg)](https://github.com/CHUKEPC/rate-limiter)

Высокопроизводительная, расширяемая и независимая от фреймворков Python-библиотека для ограничения частоты запросов к API (Rate Limiting). Включает в себя **5 ключевых алгоритмов rate limiting**, распределенную синхронизацию в **Redis** на атомарных Lua-скриптах, **In-memory** хранилище с автопереключением при сбоях (fallback), чистый ASGI **middleware для FastAPI**, декоратор эндпоинтов, тарификацию (tiers) и гибкие стратегии извлечения ключей клиентов.

---

## Возможности

- **5 алгоритмов Rate Limiting**:
  - **Fixed Window (Фиксированное окно)**: Легковесный целочисленный счетчик с минимальными накладными расходами.
  - **Sliding Window Log (Журнал скользящего окна)**: 100% точный учет временных меток запросов в скользящем временном интервале.
  - **Sliding Window Counter (Счетчик скользящего окна)**: Высокопроизводительная аппроксимация со сложностью $O(1)$ по памяти, взвешивающая соседние интервалы.
  - **Token Bucket (Корзина токенов)**: Классический алгоритм непрерывного пополнения с поддержкой кратковременных всплесков (burst).
  - **Leaky Bucket (Протекающее ведро)**: Очередь с постоянной скоростью утечки для сглаживания импульсного трафика (traffic shaping).
- **Хранилища данных**:
  - **Redis Backend**: Атомарные Lua-скрипты исключают состояние гонки (race conditions) при горизонтальном масштабировании на кластере серверов.
  - **In-Memory Backend**: Потокобезопасная и асинхронная реализация на `asyncio.Lock` без сторонних зависимостей.
  - **Автоматический Fallback**: Прозрачное переключение на локальную память в случае сетевых сбоев или недоступности Redis.
- **Стратегии извлечения ключей (Key Strategies)**:
  - По IP-адресу клиента (проверка заголовков `CF-Connecting-IP`, `X-Forwarded-For`, `X-Real-IP` или сокета).
  - По API-ключу (из заголовков `X-API-Key` или query-параметров).
  - По идентификатору пользователя (из `request.state.user` или `request.user`).
  - По произвольному синхронному или асинхронному колбэку (`CustomKeyStrategy`).
  - Составные ключи (`CompositeKeyStrategy`, например IP + User ID + Route).
- **Интеграция с веб-фреймворками**:
  - Чистый ASGI **FastAPI / Starlette** middleware с минимальным оверхедом.
  - Декоратор `@rate_limit` для тонкой настройки отдельных эндпоинтов.
  - Django middleware для синхронных и асинхронных представлений (views).
  - Стандартные HTTP-заголовки: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After` и черновик IETF `RateLimit-*`.
- **Продвинутые функции**:
  - **Уровни доступа (Tiers)**: Динамическое распределение квот для Free, Standard, Premium и Enterprise пользователей.
  - **Cost-Based Limiting (Стоимость запроса)**: Различные эндпоинты могут расходовать разное количество токенов за один вызов.
  - **Белые и черные списки**: Мгновенный пропуск проверенных IP/путей и блокировка (403 Forbidden) нежелательных клиентов.
- **Инструменты разработчика**:
  - Полная поддержка строгой типизации (маркер PEP 561 `py.typed`).
  - Интерактивный CLI-инструмент для тестирования всплесков нагрузки и сравнения алгоритмов.
  - Демонстрационное FastAPI приложение и готовый `docker-compose.yml`.

---

## Сравнение алгоритмов

| Алгоритм | Временная сложность | Сложность по памяти | Поддержка всплесков (Burst) | Точность | Рекомендуемое применение |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Fixed Window** | $O(1)$ | $O(1)$ | Нет (риск всплеска на границах) | Низкая | Простые лимиты, фоновые пакетные задачи |
| **Sliding Window Log** | $O(\log N)$ | $O(N)$ | Нет | 100% точная | Редкие критически важные эндпоинты (авторизация, оплата) |
| **Sliding Window Counter** | $O(1)$ | $O(1)$ | Нет | ~99.5% (оценка) | Высоконагруженные публичные REST API |
| **Token Bucket** | $O(1)$ | $O(1)$ | Да (до объема burst) | Непрерывная | Общие API с допущением пиковых всплесков |
| **Leaky Bucket** | $O(1)$ | $O(1)$ | Да (буфер очереди) | Непрерывная | Защита медленных сервисов, сглаживание трафика |

---

## Структура проекта

```
rate-limiter/
├── src/rate_limiter/
│   ├── __init__.py          # Экспорт публичного API
│   ├── config.py            # Модели правил, тарифов и фильтрации
│   ├── decorators.py        # Декоратор @rate_limit
│   ├── exceptions.py        # Иерархия исключений
│   ├── headers.py           # Форматирование HTTP-заголовков
│   ├── limiter.py           # Главный координатор RateLimiter
│   ├── cli.py               # Консольная утилита Typer
│   ├── py.typed             # Маркер PEP 561
│   ├── algorithms/          # Реализации алгоритмов
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── fixed_window.py
│   │   ├── leaky_bucket.py
│   │   ├── sliding_window.py
│   │   └── token_bucket.py
│   ├── backends/            # Движки хранения состояния
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── memory.py
│   │   └── redis.py         # Распределенный Redis бэкенд (Lua)
│   ├── keys/                # Стратегии идентификации клиентов
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── composite.py
│   │   ├── header.py
│   │   ├── ip.py
│   │   └── user.py
│   ├── middleware/          # Интеграции с фреймворками
│   │   ├── __init__.py
│   │   ├── django.py
│   │   └── fastapi.py       # Чистый ASGI middleware
│   └── demo/                # Демо-сервис FastAPI
│       ├── __init__.py
│       ├── app.py
│       └── routes.py
├── tests/                   # Набор тестов с покрытием 93%+
├── docker-compose.yml       # Стек сервисов (API + Redis)
├── Dockerfile               # Многоэтапный Docker-образ
├── Makefile                 # Команды автоматизации
└── pyproject.toml           # Единая конфигурация проекта
```

---

## Установка

```bash
# Базовая установка
pip install rate-limiter

# С поддержкой Redis
pip install "rate-limiter[redis]"
```

Локальная установка для разработки:
```bash
git clone https://github.com/CHUKEPC/rate-limiter.git
cd rate-limiter
make install
```

---

## Примеры использования

### 1. Подключение FastAPI ASGI Middleware

```python
from fastapi import FastAPI
from rate_limiter import (
    RateLimiter,
    RateLimitMiddleware,
    RateLimitRule,
    AlgorithmType,
    RedisBackend,
)

app = FastAPI()

# Подключение Redis с резервным переключением на In-memory
backend = RedisBackend(redis_url="redis://localhost:6379/0", fallback_on_error=True)

limiter = RateLimiter(
    backend=backend,
    default_rule=RateLimitRule(
        limit=100,
        period=60.0,
        algorithm=AlgorithmType.SLIDING_WINDOW_COUNTER,
    ),
)

app.add_middleware(RateLimitMiddleware, limiter=limiter, include_headers=True)

@app.get("/items")
async def get_items():
    return [{"id": 1, "name": "Item 1"}]
```

### 2. Декоратор для отдельных маршрутов с кастомной стоимостью

```python
from fastapi import FastAPI, Request
from rate_limiter import rate_limit, AlgorithmType

app = FastAPI()

# Индивидуальный лимит для эндпоинта поиска
@app.get("/search")
@rate_limit(limit=10, period=60.0, algorithm=AlgorithmType.TOKEN_BUCKET, burst=15)
async def search(request: Request, query: str):
    return {"results": [query]}

# Тяжелая операция, списывающая 5 единиц квоты за запрос
@app.post("/export-pdf")
@rate_limit(limit=20, period=60.0, cost=5)
async def export_pdf(request: Request):
    return {"status": "exported"}
```

### 3. Стратегии ключей и тарифные планы (Tiers)

```python
from rate_limiter import (
    RateLimiter,
    RateLimitRule,
    Tier,
    ApiKeyStrategy,
    IPKeyStrategy,
    CompositeKeyStrategy,
)

# Ограничение по API-ключу
api_key_limiter = RateLimiter(key_strategy=ApiKeyStrategy())

# Составной ключ: IP-адрес + API-ключ
composite_limiter = RateLimiter(
    key_strategy=CompositeKeyStrategy([IPKeyStrategy(), ApiKeyStrategy(fallback="public")])
)

# Определение тарифа пользователя
def resolve_tier(request):
    return request.headers.get("x-user-tier", "free")

tiered_limiter = RateLimiter(
    tier_rules={
        Tier.FREE.value: RateLimitRule(limit=20, period=60.0),
        Tier.PREMIUM.value: RateLimitRule(limit=500, period=60.0),
        Tier.ENTERPRISE.value: RateLimitRule(limit=5000, period=60.0),
    },
    tier_resolver=resolve_tier,
)
```

---

## Консольная утилита (CLI)

Библиотека предоставляет интерактивный CLI для бенчмаркинга и моделирования потока запросов:

```bash
# Таблица сравнения алгоритмов
rate-limiter algorithms

# Симуляция 20 запросов с емкостью burst=10
rate-limiter test --algorithm token_bucket --limit 5 --period 5 --burst 10 --requests 20

# Проверка удаленного Redis
rate-limiter test --algorithm sliding_window_counter --limit 100 --period 60 --redis redis://localhost:6379/0

# Сброс лимита для конкретного ключа
rate-limiter reset "ip:192.168.1.1" --redis redis://localhost:6379/0
```

---

## Запуск демонстрационного приложения

Через Docker Compose:
```bash
docker-compose up -d
```

Сервер станет доступен по адресу `http://localhost:8000`:
- Swagger документация: `http://localhost:8000/docs`
- Проверка работоспособности: `curl http://localhost:8000/health`
- Пример Token Bucket: `curl -i http://localhost:8000/api/token-bucket`
- Статус лимитов клиента: `curl http://localhost:8000/api/status`

Или локально через Make:
```bash
make demo
```

---

## Тестирование и проверка качества

```bash
# Запуск тестов с отчетом о покрытии
make test

# Проверка линтером ruff
make lint

# Строгая проверка типов mypy
make type-check

# Полный комплекс проверок
make all
```

---

## Лицензия

Проект распространяется под свободной лицензией MIT — подробности в файле [LICENSE](LICENSE).
