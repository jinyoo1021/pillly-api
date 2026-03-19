import redis
from app.core.config import settings


def get_redis_client() -> redis.Redis:
    """
    local: redis://localhost:6379
    production: Upstash Redis URL (https://xxx.upstash.io)
    """
    return redis.from_url(
        settings.UPSTASH_REDIS_URL,
        decode_responses=True,
    )


redis_client = get_redis_client()