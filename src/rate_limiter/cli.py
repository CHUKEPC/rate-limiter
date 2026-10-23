"""Command-line interface for testing, inspecting, and managing rate limits.

Provides utilities to simulate high-concurrency traffic bursts, evaluate algorithm
behaviors, inspect quotas, and clear keys in both local memory and Redis.
"""

import asyncio

import typer
from rich.console import Console
from rich.table import Table

from rate_limiter.backends.base import BaseBackend
from rate_limiter.backends.memory import InMemoryBackend
from rate_limiter.backends.redis import RedisBackend
from rate_limiter.config import AlgorithmType, RateLimitRule

app = typer.Typer(
    name="rate-limiter",
    help="CLI tool for testing and benchmarking API rate limiting algorithms.",
    add_completion=False,
)
console = Console()


def _get_backend(redis_url: str | None = None) -> BaseBackend:
    """Instantiate storage backend based on CLI options."""
    if redis_url:
        return RedisBackend(redis_url=redis_url, fallback_on_error=False)
    return InMemoryBackend()


@app.command()
def test(
    algorithm: str = typer.Option(
        "sliding_window_counter",
        "--algorithm",
        "-a",
        help="Algorithm: fixed_window, sliding_window_log, sliding_window_counter, token_bucket, leaky_bucket",
    ),
    limit: int = typer.Option(10, "--limit", "-l", help="Max allowed requests in window"),
    period: float = typer.Option(5.0, "--period", "-p", help="Window duration in seconds"),
    burst: int | None = typer.Option(None, "--burst", "-b", help="Burst capacity"),
    requests: int = typer.Option(15, "--requests", "-n", help="Total requests to simulate"),
    delay: float = typer.Option(0.1, "--delay", "-d", help="Delay between requests in seconds"),
    cost: int = typer.Option(1, "--cost", "-c", help="Cost per request"),
    redis_url: str | None = typer.Option(None, "--redis", "-r", help="Redis URL (optional)"),
    key: str = typer.Option("cli:test", "--key", "-k", help="Rate limit test key"),
) -> None:
    """Simulate a stream of requests and display real-time rate limit decisions."""
    asyncio.run(
        _run_simulation(
            algorithm=algorithm,
            limit=limit,
            period=period,
            burst=burst,
            requests=requests,
            delay=delay,
            cost=cost,
            redis_url=redis_url,
            key=key,
        )
    )


async def _run_simulation(
    algorithm: str,
    limit: int,
    period: float,
    burst: int | None,
    requests: int,
    delay: float,
    cost: int,
    redis_url: str | None,
    key: str,
) -> None:
    """Execute asynchronous simulation loop."""
    try:
        algo_type = AlgorithmType(algorithm)
    except ValueError:
        console.print(f"[bold red]Error: Invalid algorithm '{algorithm}'[/bold red]")
        raise typer.Exit(code=1) from None

    rule = RateLimitRule(
        limit=limit,
        period=period,
        algorithm=algo_type,
        burst=burst,
        cost=cost,
    )
    backend = _get_backend(redis_url)

    # Clean key before test run
    await backend.reset(key)

    console.print(
        f"\n[bold green]Running simulation:[/bold green] {requests} requests, "
        f"limit={limit}/{period}s, algorithm=[cyan]{algo_type.value}[/cyan], cost={cost}"
    )

    table = Table(title="Simulation Results")
    table.add_column("Req #", justify="right", style="cyan")
    table.add_column("Allowed", justify="center")
    table.add_column("Remaining", justify="right")
    table.add_column("Reset After (s)", justify="right")
    table.add_column("Retry After (s)", justify="right")

    allowed_count = 0
    blocked_count = 0

    for i in range(1, requests + 1):
        res = await backend.acquire(key=key, rule=rule, cost=cost)
        if res.allowed:
            allowed_count += 1
            status_str = "[bold green]YES[/bold green]"
        else:
            blocked_count += 1
            status_str = "[bold red]NO (429)[/bold red]"

        table.add_row(
            str(i),
            status_str,
            str(res.remaining),
            f"{res.reset_after:.2f}",
            str(res.retry_after),
        )

        if delay > 0 and i < requests:
            await asyncio.sleep(delay)

    console.print(table)
    console.print(
        f"[bold]Summary:[/bold] [green]{allowed_count} Allowed[/green], "
        f"[red]{blocked_count} Blocked[/red] "
        f"({(allowed_count / requests) * 100:.1f}% acceptance rate)\n"
    )

    await backend.close()


@app.command()
def algorithms() -> None:
    """Display information and comparison of all 5 rate limiting algorithms."""
    table = Table(title="Rate Limiting Algorithms Comparison")
    table.add_column("Algorithm", style="cyan", no_wrap=True)
    table.add_column("Memory Complexity", style="magenta")
    table.add_column("Burst Support", style="green")
    table.add_column("Precision", style="yellow")
    table.add_column("Best Use Case")

    table.add_row(
        "Fixed Window",
        "O(1)",
        "No (Boundary spikes)",
        "Low (Window resets)",
        "Simple API thresholds, batch jobs",
    )
    table.add_row(
        "Sliding Window Log",
        "O(N)",
        "No",
        "Exact (100%)",
        "Strict low-frequency security endpoints",
    )
    table.add_row(
        "Sliding Window Counter",
        "O(1)",
        "No",
        "High (~99.5% approx)",
        "General high-throughput public APIs",
    )
    table.add_row(
        "Token Bucket",
        "O(1)",
        "Yes (Configurable burst)",
        "Continuous",
        "APIs that accommodate occasional bursts",
    )
    table.add_row(
        "Leaky Bucket",
        "O(1)",
        "Yes (Smoothing queue)",
        "Continuous",
        "Traffic shaping, background workers",
    )

    console.print(table)


@app.command()
def reset(
    key: str = typer.Argument(..., help="Key to reset"),
    redis_url: str | None = typer.Option(None, "--redis", "-r", help="Redis URL"),
) -> None:
    """Reset rate limit data for a specific partition key."""

    async def _do_reset() -> None:
        backend = _get_backend(redis_url)
        await backend.reset(key)
        await backend.close()

    asyncio.run(_do_reset())
    console.print(f"[bold green]Successfully reset rate limit for key:[/bold green] {key}")


if __name__ == "__main__":
    app()
