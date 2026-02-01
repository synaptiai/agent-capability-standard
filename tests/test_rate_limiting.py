"""Tests for rate limiter (SEC-010).

Validates token bucket rate limiting for capability invocations.
"""

from __future__ import annotations

import time

import pytest

from grounded_agency.state.rate_limiter import RateLimitConfig, RateLimiter


@pytest.fixture
def strict_limiter() -> RateLimiter:
    """Rate limiter with very low limits for testing."""
    return RateLimiter(
        RateLimitConfig(
            high_rpm=3,
            medium_rpm=6,
            low_rpm=12,
            burst_multiplier=1.0,  # No burst headroom
        )
    )


@pytest.fixture
def default_limiter() -> RateLimiter:
    """Rate limiter with default config."""
    return RateLimiter()


class TestTokenBucket:
    """Tests for basic token bucket behavior."""

    def test_allows_within_limit(self, strict_limiter: RateLimiter) -> None:
        # 3 high-risk RPM with burst=1.0 => 3 tokens
        assert strict_limiter.allow("high") is True
        assert strict_limiter.allow("high") is True
        assert strict_limiter.allow("high") is True

    def test_denies_over_limit(self, strict_limiter: RateLimiter) -> None:
        # Exhaust all tokens
        for _ in range(3):
            strict_limiter.allow("high")
        # Next should be denied
        assert strict_limiter.allow("high") is False

    def test_refills_over_time(self, strict_limiter: RateLimiter) -> None:
        # Exhaust all high tokens
        for _ in range(3):
            strict_limiter.allow("high")

        # Wait for 1 second — should refill ~0.05 tokens (3/60)
        # Not enough for 1 full token at 3 RPM
        time.sleep(0.1)
        # Still should be denied (3 RPM = 0.05 t/s, 0.1s = 0.005 tokens)
        assert strict_limiter.allow("high") is False

    def test_different_risk_levels_independent(
        self, strict_limiter: RateLimiter
    ) -> None:
        # Exhaust high-risk tokens
        for _ in range(3):
            strict_limiter.allow("high")
        assert strict_limiter.allow("high") is False

        # Medium-risk should still be available
        assert strict_limiter.allow("medium") is True

        # Low-risk should still be available
        assert strict_limiter.allow("low") is True

    def test_unknown_risk_level_allowed(self, strict_limiter: RateLimiter) -> None:
        assert strict_limiter.allow("unknown") is True

    def test_burst_multiplier(self) -> None:
        limiter = RateLimiter(
            RateLimitConfig(
                high_rpm=10,
                burst_multiplier=2.0,  # 20 burst capacity
            )
        )
        # Should allow up to 20 (10 * 2.0) high-risk requests
        for _ in range(20):
            assert limiter.allow("high") is True
        assert limiter.allow("high") is False


class TestGetRemaining:
    """Tests for diagnostics."""

    def test_starts_at_capacity(self, default_limiter: RateLimiter) -> None:
        remaining = default_limiter.get_remaining("high")
        # Default: 10 RPM * 1.5 burst = 15
        assert remaining == 15.0

    def test_decreases_after_use(self, default_limiter: RateLimiter) -> None:
        default_limiter.allow("high")
        remaining = default_limiter.get_remaining("high")
        assert remaining < 15.0

    def test_unknown_level_returns_zero(self, default_limiter: RateLimiter) -> None:
        assert default_limiter.get_remaining("unknown") == 0.0


class TestReset:
    """Tests for reset functionality."""

    def test_reset_restores_tokens(self, strict_limiter: RateLimiter) -> None:
        # Exhaust tokens
        for _ in range(3):
            strict_limiter.allow("high")
        assert strict_limiter.allow("high") is False

        # Reset
        strict_limiter.reset()
        assert strict_limiter.allow("high") is True
