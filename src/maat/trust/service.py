"""Beta-posterior trust per (user, domain). Trust only lowers the evidence bar; it never skips a
lock (spec section 11)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from maat.repo import Repo
from maat.settings import Settings


class TrustService:
    def __init__(
        self, repo: Repo, settings: Settings, clock: Callable[[], datetime] | None = None
    ) -> None:
        self.repo, self.settings = repo, settings
        self.clock = clock or (lambda: datetime.now(UTC))

    def _days_since(self, iso: str) -> float:
        then = datetime.fromisoformat(iso)
        return max(0.0, (self.clock() - then).total_seconds() / 86400)

    def get(self, user_id: str, domain: str) -> tuple[float, float]:
        """(alpha, beta) with lazy exponential decay toward the Beta(1,1) prior."""
        row = self.repo.get_trust_row(user_id, domain)
        if row is None:
            return 1.0, 1.0
        factor = self.settings.trust_gamma ** self._days_since(row["updated_at"])
        return 1 + (row["alpha"] - 1) * factor, 1 + (row["beta"] - 1) * factor

    def expected(self, user_id: str, domain: str) -> float:
        a, b = self.get(user_id, domain)
        return a / (a + b)

    def age_weight(self, user_id: str) -> float:
        """New accounts earn trust slowly: 0.25 at creation, 1.0 after account_age_full_days."""
        user = self.repo.get_user(user_id)
        if user is None:
            return 0.25
        age = self._days_since(user["created_at"])
        return min(1.0, 0.25 + 0.75 * age / self.settings.account_age_full_days)

    def update(self, user_id: str, domain: str, outcome: str, tier: str) -> float:
        """Apply a gate outcome ('pass' | 'fail' | 'inconclusive'); return the new E[trust]."""
        a, b = self.get(user_id, domain)
        w = self.settings.trust_weight[tier]
        if outcome == "pass":
            a += w * self.age_weight(user_id)
        elif outcome == "fail":
            b += w
        elif outcome != "inconclusive":
            raise ValueError(f"unknown outcome {outcome}")
        if outcome != "inconclusive":
            self.repo.put_trust_row(
                user_id, domain, a, b, self.clock().isoformat(timespec="seconds")
            )
            self.repo.audit(
                "trust.updated",
                "trust",
                {
                    "user_id": user_id,
                    "domain": domain,
                    "outcome": outcome,
                    "tier": tier,
                    "expected": a / (a + b),
                },
            )
        return a / (a + b)

    def trusted_users(self, user_ids: list[str], domain: str) -> list[str]:
        """Users whose E[trust] in ``domain`` clears the corroboration threshold."""
        thr = self.settings.corr_trust_threshold
        return [u for u in dict.fromkeys(user_ids) if self.expected(u, domain) >= thr]

    def board(self, user_id: str) -> dict[str, float]:
        return {
            d: round(self.expected(user_id, d), 4)
            for d in ("structural_codes", "site_safety", "tender_docs")
        }
