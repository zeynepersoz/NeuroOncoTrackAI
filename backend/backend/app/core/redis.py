"""
NeuroOncoTrack-AI — Redis Connection Management

Redis is used for:
  - Access token blacklist (jti → TTL = remaining token lifetime)
  - Login rate limiting (IP-based counters)
"""

from __future__ import annotations

from redis.asyncio import ConnectionPool, Redis

from app.core.config import settings

# Connection pool — created once, shared across the application
_pool: ConnectionPool | None = None


async def get_redis_pool() -> ConnectionPool:
    """Get or create the Redis connection pool."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=20,
        )
    return _pool


async def get_redis() -> Redis:
    """
    Get a Redis client instance.

    Usage as FastAPI dependency:
        redis: Redis = Depends(get_redis)
    """
    pool = await get_redis_pool()
    return Redis(connection_pool=pool)


async def close_redis() -> None:
    """Close the Redis connection pool. Called on application shutdown."""
    global _pool
    if _pool is not None:
        await _pool.disconnect()
        _pool = None


# ── Blacklist Operations ─────────────────────────────────────

BLACKLIST_PREFIX = "bl:jti:"


async def blacklist_token(redis: Redis, jti: str, ttl_seconds: int) -> None:
    """
    Add a token's JTI to the blacklist.

    TTL is set to the remaining lifetime of the access token,
    so the blacklist entry auto-expires when the token would have expired anyway.
    """
    key = f"{BLACKLIST_PREFIX}{jti}"
    await redis.set(key, "1", ex=ttl_seconds)


async def is_token_blacklisted(redis: Redis, jti: str) -> bool:
    """Check if a token's JTI is in the blacklist."""
    key = f"{BLACKLIST_PREFIX}{jti}"
    return await redis.exists(key) > 0


# ── Rate Limiting Operations ────────────────────────────────

RATE_LIMIT_PREFIX = "rl:login:"


async def check_rate_limit(redis: Redis, ip_address: str) -> tuple[bool, int]:
    """
    Check login rate limit for an IP address.

    Returns:
        tuple of (is_allowed, current_count)
    """
    key = f"{RATE_LIMIT_PREFIX}{ip_address}"
    count = await redis.get(key)

    if count is None:
        return True, 0

    current = int(count)
    return current < settings.LOGIN_RATE_LIMIT_ATTEMPTS, current


async def increment_rate_limit(redis: Redis, ip_address: str) -> int:
    """
    Increment the login attempt counter for an IP.

    Sets a TTL window on first attempt.
    Returns the new count.
    """
    key = f"{RATE_LIMIT_PREFIX}{ip_address}"
    pipe = redis.pipeline()
    pipe.incr(key)
    pipe.ttl(key)
    results = await pipe.execute()

    new_count = results[0]
    ttl = results[1]

    # Set TTL only on first increment (when TTL is -1, meaning no expiry set)
    if ttl == -1:
        await redis.expire(key, settings.LOGIN_RATE_LIMIT_WINDOW_MINUTES * 60)

    return new_count


async def reset_rate_limit(redis: Redis, ip_address: str) -> None:
    """Reset the login rate limit counter for an IP after successful login."""
    key = f"{RATE_LIMIT_PREFIX}{ip_address}"
    await redis.delete(key)
