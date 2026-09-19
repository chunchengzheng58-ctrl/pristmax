"""
Storage Tiering Policy Engine

Provides automatic tier classification based on data access patterns,
age, and importance. Makes decisions about which tier data should
reside in for optimal cost/performance.

Policies are evaluated in order:
1. Explicit user policy (highest priority)
2. Access pattern policy (hot/warm/cold based on access)
3. Age-based policy (time since creation)
4. Size-based policy (large objects favor cold storage)
5. Default policy
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
import time

from tiering.storage_backend import StorageTier, TierPolicy, DEFAULT_POLICIES


class PolicyPriority(Enum):
    """Priority levels for policies"""
    CRITICAL = 1   # User explicitly pinned data
    HIGH = 2       # Frequently accessed data
    NORMAL = 3     # Standard classification
    LOW = 4        # Infrequently accessed
    ARCHIVE = 5    # Long-term retention only


@dataclass
class ClassificationContext:
    """Context for tier classification decisions"""
    fingerprint: str
    size: int                      # Size in bytes
    created_at: float              # Unix timestamp
    last_accessed: float           # Unix timestamp
    access_count: int              # Total access count
    refcount: int                  # Reference count (how many files use this chunk)
    explicit_tags: Dict[str, str] = field(default_factory=dict)  # User tags
    content_type: Optional[str] = None  # e.g., "text", "image", "video"
    compression_ratio: float = 1.0  # How well data compresses


@dataclass
class ClassificationResult:
    """Result of tier classification"""
    tier: StorageTier
    priority: PolicyPriority
    reason: str                    # Human-readable reason for classification
    confidence: float              # 0.0 to 1.0
    estimated_monthly_cost: float  # Estimated cost per month in $
    migration_candidates: List[str] = field(default_factory=list)  # Other tiers to check


class TierPolicyEngine:
    """
    Policy engine for automatic tier classification.

    Evaluates multiple policies and returns the best tier assignment.
    """

    def __init__(self, custom_policies: Optional[Dict[str, TierPolicy]] = None):
        self.policies = DEFAULT_POLICIES.copy()
        if custom_policies:
            self.policies.update(custom_policies)

        # Policy rules (evaluated in order)
        self._rules: List[Callable[[ClassificationContext], Optional[ClassificationResult]]] = [
            self._evaluate_critical_tags,
            self._evaluate_access_pattern,
            self._evaluate_age,
            self._evaluate_refcount,
            self._evaluate_size,
            self._evaluate_default,
        ]

    def classify(self, ctx: ClassificationContext) -> ClassificationResult:
        """
        Classify a chunk into the appropriate tier.

        Args:
            ctx: Classification context with access patterns

        Returns:
            ClassificationResult with tier recommendation
        """
        # Evaluate each rule in priority order
        for rule in self._rules:
            result = rule(ctx)
            if result is not None:
                return result

        # Should never reach here, but default fallback
        return self._evaluate_default(ctx)

    def _evaluate_critical_tags(self, ctx: ClassificationContext) -> Optional[ClassificationResult]:
        """Check for explicit user policies via tags."""
        if "pinned" in ctx.explicit_tags:
            return ClassificationResult(
                tier=StorageTier.HOT,
                priority=PolicyPriority.CRITICAL,
                reason="User pinned data",
                confidence=1.0,
                estimated_monthly_cost=self._estimate_cost(StorageTier.HOT, ctx.size)
            )

        if "archive_only" in ctx.explicit_tags:
            return ClassificationResult(
                tier=StorageTier.COLD,
                priority=PolicyPriority.CRITICAL,
                reason="User specified archive-only",
                confidence=1.0,
                estimated_monthly_cost=self._estimate_cost(StorageTier.COLD, ctx.size)
            )

        return None

    def _evaluate_access_pattern(self, ctx: ClassificationContext) -> Optional[ClassificationResult]:
        """Evaluate based on access pattern."""
        now = time.time()
        age_days = (now - ctx.created_at) / 86400
        days_since_access = (now - ctx.last_accessed) / 86400

        # Hot: accessed recently and frequently
        hot_policy = self.policies[StorageTier.HOT]
        if (hot_policy.max_age_days and age_days < hot_policy.max_age_days and
            hot_policy.max_access_count and ctx.access_count < hot_policy.max_access_count):
            return ClassificationResult(
                tier=StorageTier.HOT,
                priority=PolicyPriority.HIGH,
                reason=f"Hot: {ctx.access_count} accesses, {age_days:.1f} days old",
                confidence=0.85,
                estimated_monthly_cost=self._estimate_cost(StorageTier.HOT, ctx.size)
            )

        # Warm: moderate access
        warm_policy = self.policies[StorageTier.WARM]
        if (warm_policy.max_age_days and age_days < warm_policy.max_age_days):
            return ClassificationResult(
                tier=StorageTier.WARM,
                priority=PolicyPriority.NORMAL,
                reason=f"Warm: {age_days:.1f} days old, {ctx.access_count} accesses",
                confidence=0.75,
                estimated_monthly_cost=self._estimate_cost(StorageTier.WARM, ctx.size)
            )

        return None

    def _evaluate_age(self, ctx: ClassificationContext) -> Optional[ClassificationResult]:
        """Evaluate based on age."""
        now = time.time()
        age_days = (now - ctx.created_at) / 86400

        # Very old data -> cold
        if age_days > 365:  # 1 year
            return ClassificationResult(
                tier=StorageTier.COLD,
                priority=PolicyPriority.LOW,
                reason=f"Archive: {age_days:.0f} days old (>1 year)",
                confidence=0.7,
                estimated_monthly_cost=self._estimate_cost(StorageTier.COLD, ctx.size)
            )

        return None

    def _evaluate_refcount(self, ctx: ClassificationContext) -> Optional[ClassificationResult]:
        """Evaluate based on reference count (shared chunks)."""
        # High refcount = important data, keep in warm
        if ctx.refcount > 10:
            return ClassificationResult(
                tier=StorageTier.WARM,
                priority=PolicyPriority.NORMAL,
                reason=f"Shared chunk: {ctx.refcount} references",
                confidence=0.65,
                estimated_monthly_cost=self._estimate_cost(StorageTier.WARM, ctx.size)
            )

        return None

    def _evaluate_size(self, ctx: ClassificationContext) -> Optional[ClassificationResult]:
        """Evaluate based on data size."""
        # Large cold data is expensive - compress or archive
        if ctx.size > 100 * 1024 * 1024:  # > 100MB
            # Large data with poor compression -> cold with high compression
            if ctx.compression_ratio < 1.5:
                return ClassificationResult(
                    tier=StorageTier.COLD,
                    priority=PolicyPriority.NORMAL,
                    reason=f"Large data ({ctx.size // (1024*1024)}MB) with poor compression",
                    confidence=0.6,
                    estimated_monthly_cost=self._estimate_cost(StorageTier.COLD, ctx.size)
                )

        return None

    def _evaluate_default(self, ctx: ClassificationContext) -> ClassificationResult:
        """Default classification."""
        return ClassificationResult(
            tier=StorageTier.WARM,
            priority=PolicyPriority.NORMAL,
            reason="Default classification",
            confidence=0.5,
            estimated_monthly_cost=self._estimate_cost(StorageTier.WARM, ctx.size)
        )

    def _estimate_cost(self, tier: StorageTier, size: int) -> float:
        """Estimate monthly cost for storing data in a tier."""
        # Cost per GB per month (approximate)
        costs = {
            StorageTier.HOT: 0.03,   # $0.03/GB/month (NVMe SSD)
            StorageTier.WARM: 0.01,  # $0.01/GB/month (HDD)
            StorageTier.COLD: 0.001, # $0.001/GB/month (S3 Glacier)
        }
        return (size / (1024**3)) * costs.get(tier, 0.01)


class TierOptimizer:
    """
    Optimizes tier assignments to minimize cost while maintaining performance.

    Analyzes current tier distribution and suggests migrations.
    """

    def __init__(self, policy_engine: TierPolicyEngine):
        self.policy_engine = policy_engine

    def analyze_migration_candidates(
        self,
        current_assignments: Dict[str, StorageTier],  # fingerprint -> current tier
        contexts: Dict[str, ClassificationContext]
    ) -> List[Dict[str, Any]]:
        """
        Analyze data and return migration recommendations.

        Args:
            current_assignments: Current tier for each fingerprint
            contexts: Classification context for each fingerprint

        Returns:
            List of migration recommendations
        """
        recommendations = []

        for fp, current_tier in current_assignments.items():
            ctx = contexts.get(fp)
            if ctx is None:
                continue

            result = self.policy_engine.classify(ctx)
            recommended_tier = result.tier

            # Check if migration would save money
            if recommended_tier != current_tier:
                current_cost = self.policy_engine._estimate_cost(current_tier, ctx.size)
                new_cost = self.policy_engine._estimate_cost(recommended_tier, ctx.size)
                savings = current_cost - new_cost

                if savings > 0:  # Migration would save money
                    recommendations.append({
                        "fingerprint": fp,
                        "current_tier": current_tier,
                        "recommended_tier": recommended_tier,
                        "savings_per_month": savings,
                        "total_savings": savings * 12,  # Annual savings
                        "reason": result.reason,
                        "confidence": result.confidence,
                        "size": ctx.size
                    })

        # Sort by savings (highest first)
        recommendations.sort(key=lambda x: x["total_savings"], reverse=True)

        return recommendations

    def estimate_total_savings(
        self,
        current_assignments: Dict[str, StorageTier],
        contexts: Dict[str, ClassificationContext]
    ) -> Dict[str, float]:
        """
        Estimate potential savings from tier optimization.

        Returns:
            Dict with current_cost, optimal_cost, and monthly_savings
        """
        current_cost = 0.0
        optimal_cost = 0.0

        for fp, current_tier in current_assignments.items():
            ctx = contexts.get(fp)
            if ctx is None:
                continue

            current_cost += self.policy_engine._estimate_cost(current_tier, ctx.size)

            result = self.policy_engine.classify(ctx)
            optimal_cost += self.policy_engine._estimate_cost(result.tier, ctx.size)

        return {
            "current_monthly_cost": current_cost,
            "optimal_monthly_cost": optimal_cost,
            "monthly_savings": current_cost - optimal_cost,
            "annual_savings": (current_cost - optimal_cost) * 12
        }


# Example usage
if __name__ == "__main__":
    engine = TierPolicyEngine()

    # Simulate classification
    ctx = ClassificationContext(
        fingerprint="abc123" * 10 + "456",
        size=32768,
        created_at=time.time() - (60 * 86400),  # 60 days old
        last_accessed=time.time() - (5 * 86400),  # 5 days ago
        access_count=50,
        refcount=3
    )

    result = engine.classify(ctx)
    print(f"Classification: {result.tier.value}")
    print(f"Reason: {result.reason}")
    print(f"Priority: {result.priority.name}")
    print(f"Estimated cost: ${result.estimated_monthly_cost:.4f}/month")
