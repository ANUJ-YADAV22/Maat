from maat.settings import Settings


def test_defaults_match_spec() -> None:
    s = Settings()
    assert s.k_replays == 5 and s.aa_seeds == 3
    assert s.lambda_tier == {"low": 1.0, "medium": 2.0, "high": 4.0}
    assert s.bar_tier["high"] == 0.05 and s.bar_min == 0.01 and s.trust_c == 0.5
    assert s.paraphrase_min == 0.8 and s.trust_gamma == 0.98
    assert s.backend == "mock" and s.ollama_model == "qwen2.5:7b-instruct"


def test_env_override(monkeypatch) -> None:
    monkeypatch.setenv("MAAT_K_REPLAYS", "9")
    monkeypatch.setenv("MAAT_BACKEND", "ollama")
    s = Settings()
    assert s.k_replays == 9 and s.backend == "ollama"
