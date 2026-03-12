"""
Comprehensive bot benchmark suite — saves results to a timestamped file.
Runs adaptive vs. non-adaptive comparison across all opponent types.
"""

import sys
from datetime import datetime
from benchmark import run_adaptive_comparison


class _Tee:
    """Writes to both stdout and a file simultaneously."""
    def __init__(self, file):
        self._file = file
        self._stdout = sys.stdout

    def write(self, data):
        self._stdout.write(data)
        self._file.write(data)

    def flush(self):
        self._stdout.flush()
        self._file.flush()


if __name__ == "__main__":
    results_file = f"benchmark_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    print(f"Starting adaptive vs. non-adaptive benchmark suite")
    print(f"Results will be saved to: {results_file}\n")

    with open(results_file, "w") as f:
        f.write("=" * 82 + "\n")
        f.write(f"BOT PERFORMANCE BENCHMARK — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 82 + "\n\n")

        tee = _Tee(f)
        original_stdout = sys.stdout
        sys.stdout = tee

        try:
            run_adaptive_comparison(
                num_hands=150,
                checkpoint_interval=50,
                verbose=False,
            )
        finally:
            sys.stdout = original_stdout

    print(f"Results saved to {results_file}")
