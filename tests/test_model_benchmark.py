import pytest
from PySide6.QtCore import QSettings
from backend.model_benchmark import ModelBenchmarkManager
from backend.ai_assistant import (
    estimate_response_time_seconds,
    format_estimated_duration,
    estimate_expected_output_tokens
)

@pytest.fixture(autouse=True)
def clean_benchmark_settings():
    settings = QSettings("AIPDFViewer_Test", "Benchmark_Test")
    settings.clear()

    ModelBenchmarkManager.reset()
    mgr = ModelBenchmarkManager()
    mgr.settings = settings

    yield mgr

    settings.clear()
    ModelBenchmarkManager.reset()


def test_initial_benchmark_is_none_and_na(clean_benchmark_settings):
    mgr = clean_benchmark_settings
    # No runs recorded yet
    assert mgr.get_run_count("qwen2.5:7b") == 0
    assert mgr.get_model_runs("qwen2.5:7b") == []
    
    # Estimation should be None
    est = mgr.estimate_duration("qwen2.5:7b", in_tokens=5000, expected_out_tokens=500)
    assert est is None
    
    # AI assistant wrapper should return None and format as "NA"
    est_sec = estimate_response_time_seconds("local", "qwen2.5:7b", doc_tokens=5000, prompt_tokens=20)
    assert est_sec is None
    assert format_estimated_duration(est_sec) == "NA"


def test_record_runs_and_estimate(clean_benchmark_settings):
    mgr = clean_benchmark_settings
    model = "qwen2.5:7b"

    # Record 3 runs
    # Run 1: 1000 in, 100 out (workload = 1000 + 800 = 1800), took 18s -> ~0.01 sec/workload
    mgr.record_run_time(model, in_tokens=1000, out_tokens=100, duration_sec=18.0)
    # Run 2: 2000 in, 200 out (workload = 2000 + 1600 = 3600), took 36s -> ~0.01 sec/workload
    mgr.record_run_time(model, in_tokens=2000, out_tokens=200, duration_sec=36.0)

    assert mgr.get_run_count(model) == 2
    runs = mgr.get_model_runs(model)
    assert len(runs) == 2
    assert runs[0]["in_tokens"] == 1000
    assert runs[0]["duration_sec"] == 18.0

    # Estimate for 3000 in, 100 out: workload = 3000 + 800 = 3800
    # Expected duration: 3800 * 0.01 + 0.5 = 38.5s -> formats to ~39s (or ~38s)
    est = mgr.estimate_duration(model, in_tokens=3000, expected_out_tokens=100)
    assert est is not None
    assert 35.0 <= est <= 42.0

    formatted = format_estimated_duration(est)
    assert formatted.startswith("~")
    assert formatted.endswith("s")


def test_max_100_runs_ring_buffer(clean_benchmark_settings):
    mgr = clean_benchmark_settings
    model = "llama3.2:3b"

    # Record 150 runs
    for i in range(150):
        mgr.record_run_time(model, in_tokens=100 + i, out_tokens=50, duration_sec=5.0)

    # Should be capped at 100 entries
    assert mgr.get_run_count(model) == 100
    runs = mgr.get_model_runs(model)
    assert len(runs) == 100
    # The oldest entries (0..49) were purged, first entry in list should be run 50 (in_tokens = 150)
    assert runs[0]["in_tokens"] == 150
    assert runs[-1]["in_tokens"] == 249


def test_format_estimated_duration_precision():
    assert format_estimated_duration(None) == "NA"
    assert format_estimated_duration(0.0) == "< 1s"
    assert format_estimated_duration(0.4) == "< 1s"
    assert format_estimated_duration(14.2) == "~14s"
    assert format_estimated_duration(14.8) == "~15s"
    assert format_estimated_duration(59.4) == "~59s"
    assert format_estimated_duration(60.0) == "~1m"
    assert format_estimated_duration(65.0) == "~1m 05s"
    assert format_estimated_duration(125.4) == "~2m 05s"
    assert format_estimated_duration(180.0) == "~3m"


def test_clear_model_runs(clean_benchmark_settings):
    mgr = clean_benchmark_settings
    mgr.record_run_time("model_a", 100, 20, 3.0)
    mgr.record_run_time("model_b", 200, 40, 6.0)

    assert mgr.get_run_count("model_a") == 1
    assert mgr.get_run_count("model_b") == 1

    mgr.clear_model_runs("model_a")
    assert mgr.get_run_count("model_a") == 0
    assert mgr.get_run_count("model_b") == 1

    mgr.clear_model_runs()
    assert mgr.get_run_count("model_b") == 0
