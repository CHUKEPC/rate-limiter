# API Rate Limiter Library

[![CI](https://github.com/CHUKEPC/rate-limiter/actions/workflows/ci.yml/badge.svg)](https://github.com/CHUKEPC/rate-limiter/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://img.shields.io/badge/mypy-strict-blue)](https://mypy.readthedocs.io/)
[![Coverage](https://img.shields.io/badge/coverage-93%25-brightgreen.svg)](https://github.com/CHUKEPC/rate-limiter)

A high-performance, extensible, and framework-agnostic API rate limiting library for Python. It features **5 core rate limiting algorithms**, distributed **Redis** synchronization via atomic Lua scripts, a zero-dependency **In-memory** backend with automatic fallback, pure ASGI **FastAPI middleware**, an endpoint decorator, tiered quotas, and flexible key partitioning strategies.

---

## Features

- **5 Rate Limiting Algorithms**:
  - **Fixed Window**: Lightweight counter for simple thresholds.
  - **Sliding Window Log**: Exact precision tracking request timestamps in rolling windows.
  - **Sliding Window Counter**: High-performance, O(1) memory approximation weighting adjacent windows.
  - **Token Bucket**: Classic refill rate supporting burst allowances.
  - **Leaky Bucket**: Constant-rate queue smoothing bursty traffic.
- **Distributed & Single-node Storage**:
  - **Redis Backend**: Atomic Lua scripts prevent concurrency race conditions across horizontally scaled application nodes.
  - **In-Memory Backend**: Thread-safe and async-safe using asyncio locks.
  - **Automatic Fallback**: Gracefully degrades to local in-memory storage if Redis is temporarily unreachable.
- **Key Extraction Strategies**:
  - By client IP (inspecting `CF-Connecting-IP`, `X-Forwarded-For`, `X-Real-IP`, or socket host).
  - By API key (from request headers or query parameters).
  - By authenticated User ID (from `request.state.user` or `request.user`).
  - By custom callable (synchronous or asynchronous functions).
  - By composite keys (combining IP + user + route + tenant).
- **Web Integrations**:
  - Pure ASGI **FastAPI/Starlette** middleware.
  - Standalone `@rate_limit` route decorator with per-endpoint overrides.
  - Django middleware integration for synchronous and asynchronous views.
  - Standard HTTP headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After`, and IETF draft `RateLimit-*`.
- **Advanced Capabilities**:
  - **Rate Limit Tiers**: Free, Standard, Premium, and Enterprise user allocations.
  - **Cost-Based Limiting**: Heavy endpoints can consume multiple quota tokens per request.
  - **Whitelists & Blacklists**: Instant IP/Key/Path bypass or 403 Forbidden rejection.
- **Developer Tools**:
  - Full typing support (PEP 561 `py.typed` marker).
  - Interactive CLI tool for simulating traffic bursts and inspecting algorithms.
  - Comprehensive demo FastAPI service with Docker Compose.

---

## Algorithm Comparison

| Algorithm | Time Complexity | Memory Complexity | Burst Support | Precision | Best Use Case |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Fixed Window** | $O(1)$ | $O(1)$ | No (boundary spike risk) | Low | Simple API quotas, batch jobs |
| **Sliding Window Log** | $O(\log N)$ | $O(N)$ | No | 100% exact | Low-frequency sensitive/auth endpoints |
| **Sliding Window Counter** | $O(1)$ | $O(1)$ | No | ~99.5% approx | High-throughput public REST APIs |
| **Token Bucket** | $O(1)$ | $O(1)$ | Yes (up to burst capacity) | Continuous | General APIs permitting brief bursts |
| **Leaky Bucket** | $O(1)$ | $O(1)$ | Yes (queue buffer) | Continuous | Traffic shaping, downstream protecting |

---

## Project Structure

```
rate-limiter/
├── src/rate_limiter/
│   ├── __init__.py          # Public API exports
│   ├── config.py            # Rule, Tier, and Filter definitions
│   ├── decorators.py        # @rate_limit decorator
│   ├── exceptions.py        # Custom exceptions hierarchy
│   ├── headers.py           # Standard HTTP header formatters
│   ├── limiter.py           # Central RateLimiter coordinator
│   ├── cli.py               # Typer CLI utility
│   ├── py.typed             # PEP 561 marker
│   ├── algorithms/          # Rate limiting algorithms
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── fixed_window.py
│   │   ├── leaky_bucket.py
│   │   ├── sliding_window.py
│   │   └── token_bucket.py
│   ├── backends/            # Storage engines
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── memory.py
│   │   └── redis.py         # Distributed Redis backend (atomic Lua)
│   ├── keys/                # Client partition strategies
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── composite.py
│   │   ├── header.py
│   │   ├── ip.py
│   │   └── user.py
│   ├── middleware/          # Web framework middleware
│   │   ├── __init__.py
│   │   ├── django.py
│   │   └── fastapi.py       # Pure ASGI middleware
│   └── demo/                # Demonstration FastAPI application
│       ├── __init__.py
│       ├── app.py
│       └── routes.py
├── tests/                   # 93%+ coverage test suite
├── docker-compose.yml       # App + Redis composition
├── Dockerfile               # Multi-stage container build
├── Makefile                 # Development automation
└── pyproject.toml           # Unified packaging configuration
```

---

## Installation

```bash
# Basic installation
pip install rate-limiter

# With Redis support
pip install "rate-limiter[redis]"
```

For local development:
```bash
git clone https://github.com/CHUKEPC/rate-limiter.git
cd rate-limiter
make install
```

---

## Quickstart

### 1. FastAPI ASGI Middleware

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

# Configure Redis backend with automatic in-memory fallback
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

### 2. Route Decorator with Custom Quota & Cost

```python
from fastapi import FastAPI, Request
from rate_limiter import rate_limit, AlgorithmType

app = FastAPI()

# Specific endpoint limit overriding global middleware
@app.get("/search")
@rate_limit(limit=10, period=60.0, algorithm=AlgorithmType.TOKEN_BUCKET, burst=15)
async def search(request: Request, query: str):
    return {"results": [query]}

# Heavy endpoint consuming 5 quota tokens per call
@app.post("/export-pdf")
@rate_limit(limit=20, period=60.0, cost=5)
async def export_pdf(request: Request):
    return {"status": "exported"}
```

### 3. Key Strategies & Tiered Limiting

```python
from rate_limiter import (
    RateLimiter,
    RateLimitRule,
    Tier,
    ApiKeyStrategy,
    IPKeyStrategy,
    CompositeKeyStrategy,
)

# Limit based on client API key
api_key_limiter = RateLimiter(key_strategy=ApiKeyStrategy())

# Composite partition: IP address + API Key
composite_limiter = RateLimiter(
    key_strategy=CompositeKeyStrategy([IPKeyStrategy(), ApiKeyStrategy(fallback="public")])
)

# Dynamic tier resolver inspecting user role or headers
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

## Command Line Interface (CLI)

The library includes an interactive CLI for testing algorithms and benchmarking traffic bursts:

```bash
# Compare rate limiting algorithms
rate-limiter algorithms

# Simulate 20 requests with a burst capacity of 10
rate-limiter test --algorithm token_bucket --limit 5 --period 5 --burst 10 --requests 20

# Test distributed limits on a remote Redis instance
rate-limiter test --algorithm sliding_window_counter --limit 100 --period 60 --redis redis://localhost:6379/0

# Reset rate limit counter for a specific key
rate-limiter reset "ip:192.168.1.1" --redis redis://localhost:6379/0
```

---

## Running the Demo Application

Using Docker Compose:
```bash
docker-compose up -d
```

The demo API will be accessible at `http://localhost:8000`:
- Interactive Swagger UI: `http://localhost:8000/docs`
- Health check: `curl http://localhost:8000/health`
- Token bucket demo: `curl -i http://localhost:8000/api/token-bucket`
- Status inspection: `curl http://localhost:8000/api/status`

Or run locally with Make:
```bash
make demo
```

---

## Testing & Quality

```bash
# Run test suite with coverage report
make test

# Run linter
make lint

# Run strict type checking
make type-check

# Run all checks
make all
```

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
