"""Central configuration for Maat, overridable through MAAT_* environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime settings. Gate parameters follow section 10 of the spec."""

    model_config = SettingsConfigDict(env_prefix="MAAT_", extra="ignore")

    # Paths
    db_path: str = "maat.db"
    data_dir: Path = ROOT / "data"
    results_dir: Path = ROOT / "results"

    # Knowledge base: "synthetic" (tests) or "real" (documents ingested and human-verified)
    kb_mode: str = "synthetic"

    # Determinism and backends
    seed: int = 1234
    backend: str = "mock"  # "mock" or "ollama"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b-instruct"
    judge_model: str = "llama3.1:8b"
    llm_timeout_s: float = 120.0
    llm_retries: int = 2

    # Gate parameters
    k_replays: int = 5
    aa_seeds: int = 3
    paraphrase_min: float = 0.8
    bootstrap_resamples: int = 1000
    z_one_sided: float = 1.645
    lambda_tier: dict[str, float] = Field(
        default_factory=lambda: {"low": 1.0, "medium": 2.0, "high": 4.0}
    )
    bar_tier: dict[str, float] = Field(
        default_factory=lambda: {"low": 0.0, "medium": 0.02, "high": 0.05}
    )
    trust_c: float = 0.5
    bar_min: float = 0.01
    tau: float = 0.2
    margin: float = 0.1
    scope_tolerance: int = 0
    n_min_probes: int = 8
    coverage_min: float = 0.75
    demo_mode: bool = False
    worker_enabled: bool = False
    worker_interval_s: float = 2.0

    # Warrant, clustering and trust
    n_corr: int = 3
    corr_trust_threshold: float = 0.6
    cluster_sim_threshold: float = 0.6
    cluster_user_cap: int = 2
    trust_gamma: float = 0.98
    trust_weight: dict[str, float] = Field(
        default_factory=lambda: {"low": 0.5, "medium": 1.0, "high": 2.0}
    )
    user_rate_limit_per_hour: int = 60
    account_age_full_days: float = 7.0

    # Lock 5: impact surface
    probes_per_family: int = 4
    n_in_scope_min: int = 3

    # Witness lock
    witness_base_max_pass: float = 0.2
    witness_patched_min_pass: float = 0.8
    n_paraphrases: int = 5


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
