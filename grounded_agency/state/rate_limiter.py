"""
Rate Limiter

Token bucket rate limiter for capability invocations.
Provides per-risk-level rate limiting to prevent abuse
of high-risk capabilities.

SEC-010: Prevents unbounded invocation rates.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _Bucket:
    """Internal token bucket state."""

    tokens: float
    last_refill: float
    capacity: int
    refill_rate: float  # tokens per second


@dataclass(slots=True)
class RateLimitConfig:
    """Per-risk-level rate limit configuration.

    Attributes:
        high_rpm: Max requests per minute for high-risk capabilities.
        medium_rpm: Max requests per minute for medium-risk capabilities.
        low_rpm: Max requests per minute for low-risk capabilities.
        burst_multiplier: Multiplier for burst capacity (default 1.5).
    """

    high_rpm: int = 10
    medium_rpm: int = 30
    low_rpm: int = 120
    burst_multiplier: float = 1.5

    def __post_init__(self) -> None:
        """Validate configuration invariants."""
        for attr in ("high_rpm", "medium_rpm", "low_rpm"):
            val = getattr(self, attr)
            if val < 1:
                raise ValueError(f"{attr} must be >= 1, got {val}")
        if self.burst_multiplier <= 0:
            raise ValueError(
                f"burst_multiplier must be > 0, got {self.burst_multiplier}"
            )


class RateLimiter:
    """Token bucket rate limiter with per-risk-level buckets.

    Thread-safe: uses a lock to protect bucket state.

    Example:
        limiter = RateLimiter(RateLimitConfig(high_rpm=10))

        if limiter.allow("high"):
            # proceed with high-risk operation
            pass
        else:
            # rate limited — reject or queue
            pass
    """

    def __init__(self, config: RateLimitConfig | None = None) -> None:
        self._config = config or RateLimitConfig()
        self._lock = threading.Lock()
        self._buckets: dict[str, _Bucket] = {}
        self._init_buckets()

    def _init_buckets(self) -> None:
        """Initialize token buckets for each risk level."""
        now = time.monotonic()
        cfg = self._config
        burst = cfg.burst_multiplier

        for risk, rpm in [
            ("high", cfg.high_rpm),
            ("medium", cfg.medium_rpm),
            ("low", cfg.low_rpm),
        ]:
            capacity = max(1, int(rpm * burst))
            self._buckets[risk] = _Bucket(
                tokens=float(capacity),
                last_refill=now,
                capacity=capacity,
                refill_rate=rpm / 60.0,  # tokens per second
            )

    def allow(self, risk_level: str) -> bool:
        """Check if a request at the given risk level is allowed.

        Consumes one token if available. Returns False if rate limited.

        Args:
            risk_level: One of "high", "medium", "low".

        Returns:
            True if the request is allowed, False if rate limited.
        """
        with self._lock:
            bucket = self._buckets.get(risk_level)
            if bucket is None:
                # Unknown risk level — allow but log
                logger.warning("Unknown risk level for rate limiting: %s", risk_level)
                return True

            self._refill(bucket)

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return True

            logger.warning(
                "Rate limited: %s-risk capability (%.1f tokens remaining)",
                risk_level,
                bucket.tokens,
            )
            return False

    def _refill(self, bucket: _Bucket) -> None:
        """Add tokens based on elapsed time since last refill."""
        now = time.monotonic()
        elapsed = now - bucket.last_refill
        if elapsed <= 0:
            return

        bucket.tokens = min(
            float(bucket.capacity),
            bucket.tokens + elapsed * bucket.refill_rate,
        )
        bucket.last_refill = now

    def get_remaining(self, risk_level: str) -> float:
        """Get remaining tokens for a risk level (for diagnostics)."""
        with self._lock:
            bucket = self._buckets.get(risk_level)
            if bucket is None:
                return 0.0
            self._refill(bucket)
            return bucket.tokens

    def reset(self) -> None:
        """Reset all buckets to full capacity."""
        with self._lock:
            self._init_buckets()
