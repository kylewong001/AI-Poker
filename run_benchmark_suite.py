"""
<<<<<<< HEAD
Comprehensive bot benchmark with results saved to file
Run this for detailed performance analysis against different opponent types
"""

from benchmark import BotBenchmark, generate_benchmark_report
from datetime import datetime

if __name__ == "__main__":
    results_file = f"benchmark_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    
    print(f"Starting comprehensive benchmark suite")
    print(f"Results will be saved to: {results_file}\n")
    
    with open(results_file, "w") as f:
        f.write("=" * 80 + "\n")
        f.write(f"BOT PERFORMANCE BENCHMARK - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")
        
        for opponent_type in ["tight", "balanced", "loose", "aggressive"]:
            print(f"Testing vs {opponent_type} opponent (50 hands)...")
            
            stats = BotBenchmark.run_simulation(
                num_hands=50,
                opponent_type=opponent_type,
                verbose=False
            )
            
            # Generate report to string and save
            f.write(f"\n{'='*80}\n")
            f.write(f"BOT BENCHMARK REPORT vs {opponent_type.upper()} OPPONENT\n")
            f.write(f"{'='*80}\n")
            
            f.write(f"\nSample Size: 50 hands requested, {stats.hands:,} hands completed\n")
            
            if stats.hands == 0:
                f.write("No hands completed - insufficient data\n")
                continue
            
            f.write(f"\n{'PROFITABILITY':^80}\n")
            f.write("-" * 80 + "\n")
            f.write(f"Total Profit/Loss: {stats.total_profit:+,} chips\n")
            f.write(f"Win Rate: {stats.calculate_win_percentage():.1f}%\n")
            f.write(f"BB/100: {stats.calculate_bb_per_100():+.2f}\n")
            f.write(f"ROI: {stats.calculate_roi():+.1f}%\n")
            f.write(f"Profit per Hand: {stats.calculate_profit_per_hand():+.1f} chips\n")
            
            f.write(f"\n{'HAND RESULTS':^80}\n")
            f.write("-" * 80 + "\n")
            f.write(f"Wins: {stats.bot_wins:,} ({stats.bot_wins/stats.hands:.1%})\n")
            f.write(f"Losses: {stats.bot_losses:,} ({stats.bot_losses/stats.hands:.1%})\n")
            f.write(f"Ties: {stats.ties:,} ({stats.ties/stats.hands:.1%})\n")
            
            f.write(f"\n{'VARIANCE METRICS':^80}\n")
            f.write("-" * 80 + "\n")
            f.write(f"Std Deviation: {stats.calculate_std_dev():+.1f} chips\n")
            if len(stats.hand_profits) > 30:
                ci_lower, ci_upper = stats.calculate_confidence_interval()
                f.write(f"95% CI: [{ci_lower:+.1f}, {ci_upper:+.1f}] chips/hand\n")
            else:
                f.write(f"95% CI: Insufficient data (need 30+ hands, have {len(stats.hand_profits)})\n")
            
            f.write(f"\n{'SHOWDOWN ANALYSIS':^80}\n")
            f.write("-" * 80 + "\n")
            if stats.showdowns > 0:
                f.write(f"Showdowns: {stats.showdowns:,} ({stats.showdowns/stats.hands:.1%})\n")
                f.write(f"Should-have-won: {stats.bot_should_win:,} ({stats.bot_should_win/stats.showdowns:.1%})\n")
                f.write(f"Should-have-lost: {stats.bot_should_lose:,} ({stats.bot_should_lose/stats.showdowns:.1%})\n")
                f.write(f"Should-have-tied: {stats.should_tie:,} ({stats.should_tie/stats.showdowns:.1%})\n")
            else:
                f.write("No showdowns\n")
            
            f.write(f"\n{'FOLD ANALYSIS':^80}\n")
            f.write("-" * 80 + "\n")
            f.write(f"Bot folds: {stats.bot_folds:,} ({stats.bot_folds/stats.hands:.1%})\n")
            if stats.bot_folds > 0:
                f.write(f"Correct folds (EV): {stats.bot_correct_folds_ev:,} ({stats.bot_correct_folds_ev/stats.bot_folds:.1%})\n")
                f.write(f"Folded winner: {stats.bot_folded_winner_runout:,} ({stats.bot_folded_winner_runout/stats.bot_folds:.1%})\n")
            
            print(f"  ✓ Completed: +{stats.total_profit:,} chips" if stats.total_profit >= 0 else f"  ✓ Completed: {stats.total_profit:,} chips")
    
    print(f"\n✓ Benchmark complete. Results saved to {results_file}")
=======
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
                num_hands=2000,
                checkpoint_interval=200,
                verbose=False,
            )
        finally:
            sys.stdout = original_stdout

    print(f"Results saved to {results_file}")
>>>>>>> 0a41cfd96eb5cf44af49c7be4538ea564034a9c7
