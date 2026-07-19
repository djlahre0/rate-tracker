import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _clear_cache():
    """Keep the Redis cache from leaking state between tests."""
    cache.clear()
    yield
    cache.clear()
