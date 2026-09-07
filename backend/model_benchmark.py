import json
import logging
from typing import Optional, List, Dict
from PySide6.QtCore import QSettings

logger = logging.getLogger("AIPDFViewer.Benchmark")

MAX_BENCHMARK_HISTORY = 100

class ModelBenchmarkManager:
    """
    Tracks execution run times for local AI models (up to 100 runs per model)
    and estimates query durations based on empirical token throughput.
    """
    _instance = None

    @classmethod
    def reset(cls):
        """Reset singleton instance (useful for testing)."""
        cls._instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ModelBenchmarkManager, cls).__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self.settings = QSettings("AIPDFViewer", "Settings")

    def _get_key(self, model_name: str) -> str:
        clean = (model_name or "default").strip().lower().replace("/", "_").replace(":", "_")
        return f"benchmarks/{clean}"

    def get_model_runs(self, model_name: str) -> List[Dict]:
        """Retrieve the list of recent execution runs for a given model (up to 100)."""
        key = self._get_key(model_name)
        raw = self.settings.value(key, "[]")
        try:
            if isinstance(raw, str):
                return json.loads(raw)
            elif isinstance(raw, list):
                return raw
            return []
        except Exception as e:
            logger.debug(f"Failed to decode benchmark history for {model_name}: {e}")
            return []

    def get_run_count(self, model_name: str) -> int:
        """Return the number of recorded runs for a given model."""
        return len(self.get_model_runs(model_name))

    def record_run_time(self, model_name: str, in_tokens: int, out_tokens: int, duration_sec: float):
        """
        Record a completed query execution time for a model.
        Maintains a rolling window of up to 100 runs.
        """
        if not model_name or duration_sec <= 0:
            return
            
        runs = self.get_model_runs(model_name)
        
        entry = {
            "in_tokens": max(1, int(in_tokens)),
            "out_tokens": max(1, int(out_tokens)),
            "duration_sec": round(float(duration_sec), 3)
        }
        
        runs.append(entry)
        if len(runs) > MAX_BENCHMARK_HISTORY:
            runs = runs[-MAX_BENCHMARK_HISTORY:]
            
        key = self._get_key(model_name)
        self.settings.setValue(key, json.dumps(runs))
        self.settings.sync()
        logger.debug(f"Recorded run for {model_name}: {entry} (Total records: {len(runs)})")

    def clear_model_runs(self, model_name: Optional[str] = None):
        """Clear recorded benchmarks for a specific model or all models."""
        if model_name:
            key = self._get_key(model_name)
            self.settings.remove(key)
            self.settings.sync()
        else:
            self.settings.beginGroup("benchmarks")
            self.settings.remove("")
            self.settings.endGroup()
            self.settings.sync()

    def estimate_duration(self, model_name: str, in_tokens: int, expected_out_tokens: int) -> Optional[float]:
        """
        Calculate estimated response duration in seconds based on average token throughput
        across the last 100 runs. Returns None if no runs have been recorded yet.
        """
        runs = self.get_model_runs(model_name)
        if not runs:
            return None

        # Workload weighting: Decode tokens are ~8x more computationally intensive than prefill tokens
        total_time = 0.0
        total_workload = 0.0

        for r in runs:
            r_in = r.get("in_tokens", 1)
            r_out = r.get("out_tokens", 1)
            r_dur = r.get("duration_sec", 0.0)
            workload = r_in + (8.0 * r_out)
            if workload > 0 and r_dur > 0:
                total_time += r_dur
                total_workload += workload

        if total_workload <= 0 or total_time <= 0:
            return None

        # Unit workload cost (seconds per effective token)
        sec_per_workload_unit = total_time / total_workload

        query_workload = max(0, in_tokens) + (8.0 * max(1, expected_out_tokens))
        predicted = query_workload * sec_per_workload_unit
        
        # Add small baseline overhead (network + process scheduling ~0.5s)
        return max(0.1, predicted + 0.5)
