"""
Bot Benchmarking & Simulation Framework
Runs bot vs fixed opponent strategies for objective performance measurement.
Now with adaptive learning — bot updates BotParams each hand based on observed opponent behavior.
"""

import random
from typing import Optional
from pokerkit import NoLimitTexasHoldem, Automation

from stats import GameStats, FoldInfo, Checkpoint
from bot_logic import BotParams, choose_bot_action
from adapt import (
    EnhancedOpponentProfile,
    ActionObserver,
    adapt_params_to_opponent,
)
from helpers import (
    _board_one_line,
    _cards_to_str,
    _board_codes,
    _hole_codes_for_player,
    _get_call_amount,
    determine_card_winner,
    estimate_equity_vs_known_hand,
    winner_on_one_random_runout,
)


class FixedOpponentStrategy:
    """Fixed opponent strategy for benchmarking."""

    def __init__(self, difficulty: str = "balanced"):
        self.difficulty = difficulty
        self._set_parameters()

    def _set_parameters(self):
        if self.difficulty == "tight":
            self.open_range_frac = 0.15
            self.call_threshold  = 0.58  # folds to bets > ~0.72x pot
            self.raise_threshold = 0.70
            self.bluff_freq      = 0.02
            self.raise_freq      = 0.20
        elif self.difficulty == "loose":
            self.open_range_frac = 0.60
            self.call_threshold  = 0.52  # folds to bets > ~1.08x pot
            self.raise_threshold = 0.50
            self.bluff_freq      = 0.15
            self.raise_freq      = 0.45
        elif self.difficulty == "aggressive":
            self.open_range_frac = 0.55
            self.call_threshold  = 0.48  # folds to bets > ~0.92x pot
            self.raise_threshold = 0.45
            self.bluff_freq      = 0.20
            self.raise_freq      = 0.70
        else:  # balanced
            self.open_range_frac = 0.35
            self.call_threshold  = 0.55  # folds to bets > ~0.82x pot
            self.raise_threshold = 0.60
            self.bluff_freq      = 0.08
            self.raise_freq      = 0.50

    def decide_action(self, state, opponent_index: int = 0) -> tuple[str, Optional[int]]:
        """Returns ("f"/"c"/"r"/"a", amount_or_None)"""
        try:
            actor = getattr(state, "actor_index", None)
            if actor is None or actor != opponent_index:
                return ("c", None)

            can_fold  = state.can_fold()
            can_call  = state.can_check_or_call()
            can_raise = False

            try:
                min_to = getattr(state, "min_completion_betting_or_raising_to_amount", None)
                max_to = getattr(state, "max_completion_betting_or_raising_to_amount", None)
                if min_to and max_to and min_to <= max_to:
                    can_raise = state.can_complete_bet_or_raise_to(int(min_to))
            except Exception:
                can_raise = False

            cca = _get_call_amount(state)
            pot = int(getattr(state, "total_pot_amount", 0) or 0)
            street = getattr(state, "street_index", 0) or 0

            # Fraction of pot equity required to break even on a call
            pot_odds = cca / (pot + cca) if (pot + cca) > 0 else 0.0

            # -- Preflop: only enter the pot with open_range_frac of hands --
            if street == 0 and cca > 0 and can_fold:
                if random.random() > self.open_range_frac:
                    return ("f", None)

            # -- Bluff: occasionally raise regardless of pot odds --
            if can_raise and cca > 0 and random.random() < self.bluff_freq:
                try:
                    if min_to and state.can_complete_bet_or_raise_to(int(min_to)):
                        return ("r", int(min_to))
                except Exception:
                    pass

            # -- Value raise when facing a bet: gate by pot odds --
            # raise_threshold=0.70 (tight) → raises only when pot_odds < 0.30
            # raise_threshold=0.45 (aggressive) → raises when pot_odds < 0.55
            if can_raise and cca > 0 and pot_odds < (1.0 - self.raise_threshold) and random.random() < self.raise_freq:
                try:
                    if min_to and state.can_complete_bet_or_raise_to(int(min_to)):
                        return ("r", int(min_to))
                except Exception:
                    pass

            # -- Bet into free check spots at a controlled frequency --
            # Uses raise_freq * 0.4 to produce realistic c-bet / donk-bet rates:
            # tight=8%, balanced=20%, loose=18%, aggressive=28%
            if can_raise and cca == 0 and random.random() < self.raise_freq * 0.4:
                try:
                    if min_to and state.can_complete_bet_or_raise_to(int(min_to)):
                        return ("r", int(min_to))
                except Exception:
                    pass

            # -- Call or fold based on pot odds vs call_threshold --
            # call_threshold=0.55 (tight) → folds if pot_odds >= 0.45 (~82% pot bets)
            # call_threshold=0.40 (loose) → folds if pot_odds >= 0.60 (~1.5x pot bets)
            if cca > 0:
                if can_call and pot_odds < (1.0 - self.call_threshold):
                    return ("c", None)
                if can_fold:
                    return ("f", None)

            # -- Free check --
            if can_call:
                return ("c", None)

            return ("f", None) if can_fold else ("c", None)

        except Exception:
            if state.can_check_or_call():
                return ("c", None)
            elif state.can_fold():
                return ("f", None)
            return ("c", None)


class BotBenchmark:
    """Runs benchmarks of bot vs fixed opponent, with optional adaptive learning."""

    @staticmethod
    def run_simulation(
        num_hands: int = 5000,
        opponent_type: str = "balanced",
        bot_params: Optional[BotParams] = None,
        verbose: bool = False,
        adaptive: bool = True,
        checkpoint_interval: int = 50,
    ) -> tuple[GameStats, EnhancedOpponentProfile]:
        """
        Run simulation of bot vs fixed opponent for N hands.

        Args:
            num_hands:      Number of hands to simulate
            opponent_type:  "tight", "loose", "balanced", "aggressive"
            bot_params:     Base BotParams (uses benchmark defaults if None)
            verbose:        Print progress
            adaptive:       If True, bot adapts params each hand from observations

        Returns:
            (GameStats, EnhancedOpponentProfile) — stats + what the bot learned
        """
        if bot_params is None:
            bot_params = BotParams(
                trials_preflop=500,
                trials_flop=800,
                trials_postflop=1000,
            )

        base_params       = bot_params          # never mutated — used as adaptation base
        opponent_strategy = FixedOpponentStrategy(opponent_type)
        stats             = GameStats(initial_buy_in=10000, bb=100)
        opponent_profile  = EnhancedOpponentProfile()  # replaces plain OpponentProfile

        initial_stack = 10000
        stacks = (initial_stack, initial_stack)
        sb, bb_size, min_bet = 50, 100, 100

        for hand_num in range(1, num_hands + 1):
            # ── Stack reset: rebuy any depleted stack so simulation runs full N hands ──
            # We track profit separately via bot_delta, so resetting stacks doesn't
            # distort the stats — it just keeps the game going.
            if stacks[0] <= bb_size or stacks[1] <= bb_size:
                stacks = (initial_stack, initial_stack)

            if verbose and hand_num % 100 == 0:
                conf = opponent_profile.confidence
                otype = opponent_profile.classify_opponent() if conf > 0 else "learning..."
                print(
                    f"  Hand {hand_num}/{num_hands} | "
                    f"Profit: {stats.total_profit:+,} | "
                    f"Confidence: {conf:.0%} | "
                    f"Reads as: {otype}",
                    flush=True,
                )

            # ── 1. Adapt params from observations so far ──────────────────
            current_params = (
                adapt_params_to_opponent(base_params, opponent_profile)
                if adaptive else base_params
            )

            # ── 2. Create observer for this hand ──────────────────────────
            observer = ActionObserver(opponent_profile)
            observer.hand_start()

            # ── 3. Play the hand ──────────────────────────────────────────
            stacks, bot_delta, board_codes, player_codes, bot_codes, fold_info = (
                BotBenchmark._play_one_hand_automated(
                    stacks,
                    opponent_strategy,
                    current_params,
                    opponent_profile,
                    observer,          # NEW: passes observer in to record actions
                    sb, bb_size, min_bet,
                )
            )

            # ── 4. Close observer → triggers EnhancedOpponentProfile update ──
            observer.hand_end()

            # ── 5. Update stats (unchanged from original) ─────────────────
            stats.hands += 1
            stats.total_profit += bot_delta
            stats.hand_profits.append(bot_delta)

            if bot_delta > 0:
                stats.bot_wins += 1
            elif bot_delta < 0:
                stats.bot_losses += 1
            else:
                stats.ties += 1

            if len(board_codes) == 5:
                stats.showdowns += 1
                should = determine_card_winner(player_codes, bot_codes, board_codes)
                if should == "bot":
                    stats.bot_should_win += 1
                elif should == "player":
                    stats.bot_should_lose += 1
                else:
                    stats.should_tie += 1

            if hand_num % checkpoint_interval == 0 or hand_num == num_hands:
                stats.checkpoints.append(Checkpoint(
                    hand_num=hand_num,
                    cumulative_profit=stats.total_profit,
                    bb_per_100=stats.calculate_bb_per_100(),
                    confidence=opponent_profile.confidence,
                ))

            if fold_info.folded:
                stats.bot_folds += 1
                required_eq = (
                    fold_info.call_amount / (fold_info.pot + fold_info.call_amount)
                    if (fold_info.pot + fold_info.call_amount) > 0 else 1.0
                )
                eq_vs_actual = estimate_equity_vs_known_hand(
                    hero_hole_codes=bot_codes,
                    villain_hole_codes=player_codes,
                    board_codes=fold_info.board_codes,
                    trials=1000,
                )
                if eq_vs_actual < required_eq + current_params.call_edge:
                    stats.bot_correct_folds_ev += 1

                rng = random.Random(hand_num * 99991 + 17)
                runout_winner = winner_on_one_random_runout(
                    player_codes, bot_codes, fold_info.board_codes, rng
                )
                if runout_winner == "bot":
                    stats.bot_folded_winner_runout += 1

            # (stacks reset at top of loop — simulation always runs full num_hands)

        return stats, opponent_profile   # NOW RETURNS PROFILE TOO

    # ─────────────────────────────────────────────────────────────────────────
    @staticmethod
    def _play_one_hand_automated(
        stacks: tuple[int, int],
        opponent_strategy: FixedOpponentStrategy,
        bot_params: BotParams,
        opponent_profile: EnhancedOpponentProfile,
        observer: ActionObserver,       # NEW param
        sb: int = 50,
        bb: int = 100,
        min_bet: int = 100,
    ) -> tuple[tuple[int, int], int, list, list, list, FoldInfo]:
        """Play one hand. Observer records every opponent action."""

        try:
            state = NoLimitTexasHoldem.create_state(
                (
                    Automation.ANTE_POSTING,
                    Automation.BET_COLLECTION,
                    Automation.BLIND_OR_STRADDLE_POSTING,
                    Automation.CARD_BURNING,
                    Automation.BOARD_DEALING,
                    Automation.HOLE_CARDS_SHOWING_OR_MUCKING,
                    Automation.HAND_KILLING,
                    Automation.CHIPS_PUSHING,
                    Automation.CHIPS_PULLING,
                ),
                True, 0, (sb, bb), min_bet, stacks, 2,
            )
        except Exception:
            return (stacks, 0, [], [], [], FoldInfo(folded=False, board_codes=[], pot=0, call_amount=0))

        starting_stacks = tuple(int(x) for x in stacks)

        try:
            while any(len(h) < 2 for h in state.hole_cards):
                state.deal_hole()
        except Exception:
            return (stacks, 0, [], [], [], FoldInfo(folded=False, board_codes=[], pot=0, call_amount=0))

        fold_info     = FoldInfo(folded=False, board_codes=[], pot=0, call_amount=0)
        max_iters     = 50
        iteration     = 0

        while state.status and iteration < max_iters:
            iteration += 1
            try:
                actor = getattr(state, "actor_index", None)
                if actor is None:
                    break

                cca = _get_call_amount(state)
                pot = int(getattr(state, "total_pot_amount", 0) or 0)

                if actor == 0:
                    # ── Opponent acts ──────────────────────────────────────
                    act, amt = opponent_strategy.decide_action(state, opponent_index=0)

                    # Record into observer BEFORE executing
                    observer.record_action(
                        action=act,
                        street=state.street_index or 0,
                        call_amount=cca,
                        raise_to=amt if act in ("r", "a") else None,
                        pot=pot,
                        facing_raise=cca > 0,
                    )

                    # Execute
                    if act == "f" and state.can_fold():
                        state.fold()
                    elif act == "c" and state.can_check_or_call():
                        state.check_or_call()
                    elif act == "a":
                        max_to = getattr(state, "max_completion_betting_or_raising_to_amount", None)
                        if max_to and state.can_complete_bet_or_raise_to(int(max_to)):
                            state.complete_bet_or_raise_to(int(max_to))
                        elif state.can_check_or_call():
                            state.check_or_call()
                    elif act == "r" and amt and state.can_complete_bet_or_raise_to(amt):
                        state.complete_bet_or_raise_to(amt)
                    else:
                        if state.can_check_or_call():
                            state.check_or_call()
                        elif state.can_fold():
                            state.fold()

                else:
                    # ── Bot acts ───────────────────────────────────────────
                    act, amt = choose_bot_action(state, bot_params, opponent_profile)

                    if act == "f" and state.can_fold():
                        fold_info = FoldInfo(
                            folded=True,
                            board_codes=_board_codes(state),
                            pot=pot,
                            call_amount=cca,
                        )
                        state.fold()
                    elif act == "c" and state.can_check_or_call():
                        state.check_or_call()
                    elif act == "a":
                        max_to = getattr(state, "max_completion_betting_or_raising_to_amount", None)
                        if max_to and state.can_complete_bet_or_raise_to(int(max_to)):
                            state.complete_bet_or_raise_to(int(max_to))
                        elif state.can_check_or_call():
                            state.check_or_call()
                    elif act == "r" and amt and state.can_complete_bet_or_raise_to(amt):
                        state.complete_bet_or_raise_to(amt)
                    else:
                        if state.can_check_or_call():
                            state.check_or_call()
                        elif state.can_fold():
                            state.fold()

            except Exception:
                try:
                    if state.can_check_or_call():
                        state.check_or_call()
                    elif state.can_fold():
                        state.fold()
                    else:
                        break
                except Exception:
                    break

        ending_stacks = (int(state.stacks[0]), int(state.stacks[1]))
        bot_delta     = ending_stacks[1] - starting_stacks[1]

        return (
            ending_stacks,
            bot_delta,
            _board_codes(state),
            _hole_codes_for_player(state, 0),
            _hole_codes_for_player(state, 1),
            fold_info,
        )


# ─────────────────────────────────────────────────────────────────────────────
def generate_benchmark_report(
    stats: GameStats,
    opponent_type: str,
    num_hands: int,
    profile: Optional[EnhancedOpponentProfile] = None,  # NEW optional param
):
    """Generate formatted benchmark report, including adaptive learning summary."""
    print("\n" + "=" * 70)
    print(f"BOT BENCHMARK REPORT vs {opponent_type.upper()} OPPONENT")
    print("=" * 70)

    print(f"\nSample Size: {num_hands:,} hands requested, {stats.hands:,} hands completed")

    if stats.hands == 0:
        print("No hands completed - insufficient data")
        return

    print(f"\n{'PROFITABILITY':^70}")
    print("-" * 70)
    print(f"Total Profit/Loss: {stats.total_profit:+,} chips")
    print(f"Win Rate: {stats.calculate_win_percentage():.1f}%")
    print(f"BB/100: {stats.calculate_bb_per_100():+.2f}")
    print(f"ROI: {stats.calculate_roi():+.1f}%")
    print(f"Profit per Hand: {stats.calculate_profit_per_hand():+.1f} chips")

    print(f"\n{'HAND RESULTS':^70}")
    print("-" * 70)
    print(f"Wins:   {stats.bot_wins:,} ({stats.bot_wins/stats.hands:.1%})")
    print(f"Losses: {stats.bot_losses:,} ({stats.bot_losses/stats.hands:.1%})")
    print(f"Ties:   {stats.ties:,} ({stats.ties/stats.hands:.1%})")

    print(f"\n{'VARIANCE METRICS':^70}")
    print("-" * 70)
    print(f"Std Deviation: {stats.calculate_std_dev():+.1f} chips")
    if len(stats.hand_profits) > 30:
        ci_lower, ci_upper = stats.calculate_confidence_interval()
        print(f"95% CI: [{ci_lower:+.1f}, {ci_upper:+.1f}] chips/hand")
    else:
        print("95% CI: Insufficient data (need 30+ hands)")

    print(f"\n{'SHOWDOWN ANALYSIS':^70}")
    print("-" * 70)
    if stats.showdowns > 0:
        print(f"Showdowns:        {stats.showdowns:,} ({stats.showdowns/stats.hands:.1%})")
        print(f"Should-have-won:  {stats.bot_should_win:,} ({stats.bot_should_win/stats.showdowns:.1%})")
        print(f"Should-have-lost: {stats.bot_should_lose:,} ({stats.bot_should_lose/stats.showdowns:.1%})")
        print(f"Should-have-tied: {stats.should_tie:,} ({stats.should_tie/stats.showdowns:.1%})")
    else:
        print("No showdowns (insufficient data)")

    print(f"\n{'FOLD ANALYSIS':^70}")
    print("-" * 70)
    print(f"Bot folds: {stats.bot_folds:,} ({stats.bot_folds/stats.hands:.1%})")
    if stats.bot_folds > 0:
        print(f"Correct folds (EV): {stats.bot_correct_folds_ev:,} ({stats.bot_correct_folds_ev/stats.bot_folds:.1%})")
        print(f"Folded winner:      {stats.bot_folded_winner_runout:,} ({stats.bot_folded_winner_runout/stats.bot_folds:.1%})")

    # ── NEW: adaptive learning summary ────────────────────────────────────
    if profile is not None and profile.hands_dealt > 0:
        print(f"\n{'ADAPTIVE LEARNING SUMMARY':^70}")
        print("-" * 70)
        print(f"Hands observed:         {profile.hands_dealt:,}")
        print(f"Final confidence:       {profile.confidence:.0%}")
        print(f"Opponent classified as: {profile.classify_opponent()}")
        print(f"Est. VPIP:              {profile.estimated_vpip:.1%}")
        print(f"Est. PFR:               {profile.estimated_pfr:.1%}")
        print(f"Est. Aggression Factor: {profile.estimated_aggression_factor:.2f}")
        print(f"Est. Range tightness:   {profile.estimated_range_tightness:.2f} (top_frac)")
        print(f"Est. Fold-to-raise (pre):  {profile.estimated_preflop_fold_to_raise:.1%}")
        print(f"Est. Fold-to-raise (post): {profile.estimated_postflop_fold_to_raise:.1%}")
        print(f"Est. C-bet freq:           {profile.estimated_cbet_freq:.1%}")

        # Show how params shifted from base
        from bot_logic import BotParams as _BP
        base = _BP(trials_preflop=500, trials_flop=800, trials_postflop=1000)
        final = adapt_params_to_opponent(base, profile)
        print(f"\n  Parameter drift (base → final adapted):")
        print(f"    bluff_freq:              {base.bluff_freq:.3f} → {final.bluff_freq:.3f}")
        print(f"    call_edge:               {base.call_edge:.3f} → {final.call_edge:.3f}")
        print(f"    value_raise_threshold:   {base.value_raise_threshold:.3f} → {final.value_raise_threshold:.3f}")
        print(f"    check_raise_threshold:   {base.check_raise_threshold:.3f} → {final.check_raise_threshold:.3f}")
        print(f"    value_raise_frac:        {base.value_raise_frac:.3f} → {final.value_raise_frac:.3f}")

    print("\n" + "=" * 70 + "\n")


# ─────────────────────────────────────────────────────────────────────────────
def run_adaptive_comparison(
    num_hands: int = 500,
    opponent_types: Optional[list] = None,
    checkpoint_interval: int = 50,
    verbose: bool = False,
) -> dict:
    """
    Run adaptive vs. non-adaptive simulations for each opponent type and
    print a side-by-side comparison showing learning curve over time.
    """
    if opponent_types is None:
        opponent_types = ["tight", "balanced", "loose", "aggressive"]

    results = {}

    for opponent_type in opponent_types:
        print(f"  Running adaptive vs {opponent_type}...")
        adaptive_stats, adaptive_profile = BotBenchmark.run_simulation(
            num_hands=num_hands,
            opponent_type=opponent_type,
            adaptive=True,
            checkpoint_interval=checkpoint_interval,
            verbose=verbose,
        )

        print(f"  Running non-adaptive vs {opponent_type}...")
        static_stats, static_profile = BotBenchmark.run_simulation(
            num_hands=num_hands,
            opponent_type=opponent_type,
            adaptive=False,
            checkpoint_interval=checkpoint_interval,
            verbose=verbose,
        )

        results[opponent_type] = (adaptive_stats, static_stats, adaptive_profile)

    _print_adaptive_comparison(results, num_hands)
    return results


def _print_adaptive_comparison(results: dict, num_hands: int) -> None:
    """Print side-by-side adaptive vs. non-adaptive report."""
    W = 82

    print("\n" + "=" * W)
    print(f"{'ADAPTIVE vs NON-ADAPTIVE COMPARISON':^{W}}")
    print(f"{'(' + str(num_hands) + ' hands per opponent)':^{W}}")
    print("=" * W)

    # ── Summary table ──────────────────────────────────────────────────────
    print(f"\n{'FINAL RESULTS SUMMARY':^{W}}")
    print("-" * W)
    print(f"{'Opponent':<13} {'Adaptive BB/100':>16} {'Static BB/100':>14} {'Delta':>8} {'Confidence':>12} {'Reads As'}")
    print("-" * W)

    for opponent_type, (a_stats, s_stats, a_profile) in results.items():
        a_bb = a_stats.calculate_bb_per_100()
        s_bb = s_stats.calculate_bb_per_100()
        delta = a_bb - s_bb
        conf = a_profile.confidence
        label = a_profile.classify_opponent() if conf > 0 else "learning..."
        print(
            f"{opponent_type:<13} {a_bb:>+16.2f} {s_bb:>+14.2f} {delta:>+8.2f} "
            f"{conf:>11.0%}  {label}"
        )

    print("-" * W)

    # ── Per-opponent learning curve ────────────────────────────────────────
    for opponent_type, (a_stats, s_stats, a_profile) in results.items():
        print(f"\n  {'LEARNING CURVE — vs ' + opponent_type.upper():^{W - 2}}")
        print("  " + "-" * (W - 2))
        print(f"  {'Hand':>6}  {'Adaptive BB/100':>16}  {'Static BB/100':>14}  {'Confidence':>11}  {'Profit Delta':>13}")
        print("  " + "-" * (W - 2))

        for a_cp, s_cp in zip(a_stats.checkpoints, s_stats.checkpoints):
            profit_delta = a_cp.cumulative_profit - s_cp.cumulative_profit
            print(
                f"  {a_cp.hand_num:>6}  {a_cp.bb_per_100:>+16.2f}  "
                f"{s_cp.bb_per_100:>+14.2f}  {a_cp.confidence:>10.0%}  "
                f"{profit_delta:>+13,}"
            )

        print(f"\n  Opponent classified as: {a_profile.classify_opponent()}")
        print(
            f"  Est. VPIP: {a_profile.estimated_vpip:.1%}  |  "
            f"Est. PFR: {a_profile.estimated_pfr:.1%}  |  "
            f"Est. AF: {a_profile.estimated_aggression_factor:.2f}"
        )
        print(
            f"  Fold-to-raise preflop: {a_profile.estimated_preflop_fold_to_raise:.1%}  |  "
            f"Fold-to-raise postflop: {a_profile.estimated_postflop_fold_to_raise:.1%}"
        )

    print("\n" + "=" * W + "\n")


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Starting adaptive vs. non-adaptive comparison...")
    print("(Running 150 hands per opponent, checkpoints every 50 hands)\n")

    run_adaptive_comparison(
        num_hands=150,
        checkpoint_interval=50,
        verbose=False,
    )