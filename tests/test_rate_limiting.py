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


class TestRateLimitConfigValidation:
    """Tests for RateLimitConfig __post_init__ validation."""

    def test_rejects_zero_high_rpm(self) -> None:
        with pytest.raises(ValueError, match="high_rpm must be >= 1"):
            RateLimitConfig(high_rpm=0)

    def test_rejects_negative_medium_rpm(self) -> None:
        with pytest.raises(ValueError, match="medium_rpm must be >= 1"):
            RateLimitConfig(medium_rpm=-5)

    def test_rejects_zero_low_rpm(self) -> None:
        with pytest.raises(ValueError, match="low_rpm must be >= 1"):
            RateLimitConfig(low_rpm=0)

    def test_rejects_zero_burst_multiplier(self) -> None:
        with pytest.raises(ValueError, match="burst_multiplier must be > 0"):
            RateLimitConfig(burst_multiplier=0)

    def test_rejects_negative_burst_multiplier(self) -> None:
        with pytest.raises(ValueError, match="burst_multiplier must be > 0"):
            RateLimitConfig(burst_multiplier=-1.0)

    def test_accepts_valid_config(self) -> None:
        cfg = RateLimitConfig(high_rpm=1, medium_rpm=1, low_rpm=1, burst_multiplier=0.1)
        assert cfg.high_rpm == 1
        assert cfg.burst_multiplier == 0.1


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


class TestConcurrentAllow:
    """Tests for thread-safety of allow() under concurrency."""

    def test_concurrent_allow_does_not_exceed_capacity(self) -> None:
        """N threads hitting allow() simultaneously must not exceed bucket capacity."""
        import threading

        limiter = RateLimiter(RateLimitConfig(high_rpm=10, burst_multiplier=1.0))
        # Capacity = 10 tokens

        results: list[bool] = []
        barrier = threading.Barrier(20)

        def worker() -> None:
            barrier.wait()
            results.append(limiter.allow("high"))

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        allowed = sum(1 for r in results if r)
        denied = sum(1 for r in results if not r)
        # Exactly 10 should be allowed (capacity), 10 denied
        assert allowed == 10, f"Expected 10 allowed, got {allowed}"
        assert denied == 10, f"Expected 10 denied, got {denied}"

    def test_concurrent_mixed_risk_levels(self) -> None:
        """Concurrent calls at different risk levels use independent buckets."""
        import threading

        limiter = RateLimiter(
            RateLimitConfig(high_rpm=5, medium_rpm=10, low_rpm=20, burst_multiplier=1.0)
        )
        high_results: list[bool] = []
        medium_results: list[bool] = []
        barrier = threading.Barrier(20)

        def high_worker() -> None:
            barrier.wait()
            high_results.append(limiter.allow("high"))

        def medium_worker() -> None:
            barrier.wait()
            medium_results.append(limiter.allow("medium"))

        threads = []
        for _ in range(10):
            threads.append(threading.Thread(target=high_worker))
            threads.append(threading.Thread(target=medium_worker))
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        high_allowed = sum(1 for r in high_results if r)
        medium_allowed = sum(1 for r in medium_results if r)

        # High: 5 capacity, so exactly 5 allowed
        assert high_allowed == 5, f"High: expected 5, got {high_allowed}"
        # Medium: 10 capacity, so exactly 10 allowed
        assert medium_allowed == 10, f"Medium: expected 10, got {medium_allowed}"


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
