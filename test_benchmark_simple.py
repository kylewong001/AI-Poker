"""Quick test of benchmark framework with simple opponent"""

import random
from benchmark import FixedOpponentStrategy, BotBenchmark, generate_benchmark_report

print("Testing FixedOpponentStrategy initialization...")
for diff in ["tight", "balanced", "loose", "aggressive"]:
    s = FixedOpponentStrategy(diff)
    print(f"  {diff}: raise_freq={s.raise_freq}, bluff_freq={s.bluff_freq}")

print("\nRunning quick simulation (10 hands)...")
stats = BotBenchmark.run_simulation(num_hands=10, opponent_type="balanced", verbose=True)

print(f"\nCompleted {stats.hands} hands")
print(f"Total profit: {stats.total_profit}")
print(f"Bot wins: {stats.bot_wins}, losses: {stats.bot_losses}, ties: {stats.ties}")

generate_benchmark_report(stats, "balanced", 10)
