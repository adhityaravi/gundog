"""Test query engine utilities."""

import time

from gundog._query import QueryEngine


class TestScoreRescaling:
    """Test score rescaling functionality."""

    def test_rescale_score_at_baseline(self):
        """Test score at baseline returns 0."""
        assert QueryEngine._rescale_score(0.5, baseline=0.5) == 0.0

    def test_rescale_score_below_baseline(self):
        """Test score below baseline returns 0."""
        assert QueryEngine._rescale_score(0.3, baseline=0.5) == 0.0
        assert QueryEngine._rescale_score(0.0, baseline=0.5) == 0.0

    def test_rescale_score_perfect(self):
        """Test perfect score returns 1."""
        assert QueryEngine._rescale_score(1.0, baseline=0.5) == 1.0

    def test_rescale_score_midpoint(self):
        """Test midpoint between baseline and 1.0."""
        # With baseline 0.5, score 0.75 should be 0.5 (halfway)
        result = QueryEngine._rescale_score(0.75, baseline=0.5)
        assert abs(result - 0.5) < 0.001

    def test_rescale_score_custom_baseline(self):
        """Test rescaling with custom baseline."""
        # With baseline 0.4, score 0.7 should be 0.5 (halfway to 1.0)
        result = QueryEngine._rescale_score(0.7, baseline=0.4)
        assert abs(result - 0.5) < 0.001

    def test_rescale_score_typical_values(self):
        """Test typical score values."""
        # Random query ~0.55 raw should show as low relevance
        result = QueryEngine._rescale_score(0.55, baseline=0.5)
        assert abs(result - 0.1) < 0.001  # (0.55 - 0.5) / 0.5 = 0.1

        # Good match ~0.75 raw should show as moderate relevance
        result = QueryEngine._rescale_score(0.75, baseline=0.5)
        assert abs(result - 0.5) < 0.001  # (0.75 - 0.5) / 0.5 = 0.5

        # Excellent match ~0.9 raw should show as high relevance
        result = QueryEngine._rescale_score(0.9, baseline=0.5)
        assert abs(result - 0.8) < 0.001  # (0.9 - 0.5) / 0.5 = 0.8


def test_recency_score_none():
    """None timestamp returns 0."""
    assert QueryEngine._compute_recency_score(None, 30) == 0.0


def test_recency_score_now():
    """Current timestamp returns ~1.0."""
    assert QueryEngine._compute_recency_score(int(time.time()), 30) > 0.99


def test_recency_score_at_half_life():
    """Score at half-life is 0.5."""
    ts = int(time.time()) - (30 * 86400)
    assert abs(QueryEngine._compute_recency_score(ts, 30) - 0.5) < 0.01
