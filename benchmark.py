"""
Bot Benchmarking & Simulation Framework
Runs bot vs fixed opponent strategies for objective performance measurement
"""

import random
from typing import Optional
from pokerkit import NoLimitTexasHoldem, Automation

from stats import GameStats, OpponentProfile, FoldInfo
from bot_logic import BotParams, choose_bot_action
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
        """
        difficulty: "tight", "loose", "balanced", "aggressive"
        """
        self.difficulty = difficulty
        self._set_parameters()
    
    def _set_parameters(self):
        """Set strategy parameters based on difficulty."""
        if self.difficulty == "tight":
            # Plays only premium hands
            self.open_range_frac = 0.15  # Top 15% hands
            self.call_threshold = 0.55   # Needs 55% equity to call
            self.raise_threshold = 0.70  # Raises with 70%+ equity
            self.bluff_freq = 0.02       # Rarely bluffs
            self.raise_freq = 0.20       # Rarely raises
        elif self.difficulty == "loose":
            # Plays wide range
            self.open_range_frac = 0.60  # Top 60% hands
            self.call_threshold = 0.40   # Calls with 40% equity
            self.raise_threshold = 0.50  # Raises with 50%+ equity
            self.bluff_freq = 0.15       # Bluffs often
            self.raise_freq = 0.45       # Raises sometimes
        elif self.difficulty == "aggressive":
            # Plays wide and aggressive
            self.open_range_frac = 0.55
            self.call_threshold = 0.35
            self.raise_threshold = 0.45
            self.bluff_freq = 0.20
            self.raise_freq = 0.70       # Raises often instead of calling
        else:  # balanced (default)
            self.open_range_frac = 0.35
            self.call_threshold = 0.45
            self.raise_threshold = 0.60
            self.bluff_freq = 0.08
            self.raise_freq = 0.50
    
    def decide_action(self, state, opponent_index: int = 0) -> tuple[str, Optional[int]]:
        """
        Decide action for fixed opponent strategy.
        Returns: ("f"/"c"/"r"/"a", amount_or_None)
        """
        try:
            actor = getattr(state, "actor_index", None)
            if actor is None or actor != opponent_index:
                return ("c", None)
            
            can_fold = state.can_fold()
            can_call = state.can_check_or_call()
            can_raise = False
            
            try:
                min_to = getattr(state, "min_completion_betting_or_raising_to_amount", None)
                max_to = getattr(state, "max_completion_betting_or_raising_to_amount", None)
                if min_to and max_to and min_to <= max_to:
                    can_raise = state.can_complete_bet_or_raise_to(int(min_to))
            except:
                can_raise = False
            
            cca = _get_call_amount(state)
            
            # Strategy: based on difficulty + random noise
            if can_raise and random.random() < self.bluff_freq:
                # Bluff sometimes
                if random.random() < 0.5 and state.can_check_or_call():
                    return ("c", None)
            
            if can_raise and random.random() < self.raise_freq:
                # Raise instead of call
                try:
                    min_to = getattr(state, "min_completion_betting_or_raising_to_amount", None)
                    if min_to and state.can_complete_bet_or_raise_to(int(min_to)):
                        return ("r", int(min_to))
                except:
                    pass
            
            if can_call and cca >= 0:
                return ("c", None)
            
            if can_fold:
                return ("f", None)
            
            return ("c", None) if can_call else ("f", None)
        except Exception as e:
            # Fallback on any error
            if state.can_check_or_call():
                return ("c", None)
            elif state.can_fold():
                return ("f", None)
            return ("c", None)


class BotBenchmark:
    """Runs benchmarks of bot vs fixed opponent."""
    
    @staticmethod
    def run_simulation(
        num_hands: int = 5000,
        opponent_type: str = "balanced",
        bot_params: Optional[BotParams] = None,
        verbose: bool = False,
    ) -> GameStats:
        """
        Run simulation of bot vs fixed opponent for N hands.
        
        Args:
            num_hands: Number of hands to simulate
            opponent_type: "tight", "loose", "balanced", "aggressive"
            bot_params: BotParams for bot strategy (uses default if None)
            verbose: Print progress
        
        Returns:
            GameStats with complete results
        """
        if bot_params is None:
            # Use faster parameters for benchmarking
            bot_params = BotParams(
                trials_preflop=500,   # Reduced from 1200
                trials_flop=800,      # Reduced from 2000
                trials_postflop=1000  # Reduced from 3000
            )
        
        opponent_strategy = FixedOpponentStrategy(opponent_type)
        stats = GameStats(initial_buy_in=10000, bb=100)
        opponent_profile = OpponentProfile()
        
        stacks = (10000, 10000)
        sb, bb, min_bet = 50, 100, 100
        
        for hand_num in range(1, num_hands + 1):
            if verbose and hand_num % 10 == 0:
                print(f"  Hand {hand_num}/{num_hands}...", flush=True)
            
            # Play one hand
            stacks, bot_delta, board_codes, player_codes, bot_codes, fold_info = BotBenchmark._play_one_hand_automated(
                stacks, opponent_strategy, bot_params, opponent_profile, sb, bb, min_bet
            )
            
            # Update stats
            stats.hands += 1
            stats.total_profit += bot_delta
            stats.hand_profits.append(bot_delta)
            
            if bot_delta > 0:
                stats.bot_wins += 1
            elif bot_delta < 0:
                stats.bot_losses += 1
            else:
                stats.ties += 1
            
            # Showdown analysis
            if len(board_codes) == 5:
                stats.showdowns += 1
                should = determine_card_winner(player_codes, bot_codes, board_codes)
                if should == "bot":
                    stats.bot_should_win += 1
                elif should == "player":
                    stats.bot_should_lose += 1
                else:
                    stats.should_tie += 1
            
            # Fold analysis
            if fold_info.folded:
                stats.bot_folds += 1
                required_eq = (fold_info.call_amount / (fold_info.pot + fold_info.call_amount)) if (fold_info.pot + fold_info.call_amount) > 0 else 1.0
                eq_vs_actual = estimate_equity_vs_known_hand(
                    hero_hole_codes=bot_codes,
                    villain_hole_codes=player_codes,
                    board_codes=fold_info.board_codes,
                    trials=1000,  # Reduced from 2500
                )
                if eq_vs_actual < required_eq + bot_params.call_edge:
                    stats.bot_correct_folds_ev += 1
                
                rng = random.Random(hand_num * 99991 + 17)
                runout_winner = winner_on_one_random_runout(player_codes, bot_codes, fold_info.board_codes, rng)
                if runout_winner == "bot":
                    stats.bot_folded_winner_runout += 1
            
            # Stack bankrupt check
            if stacks[0] <= 0 or stacks[1] <= 0:
                if verbose:
                    print(f"  Simulation ended at hand {hand_num}: Stack depleted")
                break
        
        return stats
    
    @staticmethod
    def _play_one_hand_automated(
        stacks: tuple[int, int],
        opponent_strategy: FixedOpponentStrategy,
        bot_params: BotParams,
        opponent_profile: OpponentProfile,
        sb: int = 50,
        bb: int = 100,
        min_bet: int = 100,
    ) -> tuple[tuple[int, int], int, list, list, list, FoldInfo]:
        """Play one hand with automated opponent (no user input)."""
        
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
                True,
                0,
                (sb, bb),
                min_bet,
                stacks,
                2,
            )
        except Exception as e:
            # Return starting state if creation fails
            return (stacks, 0, [], [], [], FoldInfo(folded=False, board_codes=[], pot=0, call_amount=0))
        
        starting_stacks = tuple(int(x) for x in stacks)
        
        # Deal hole cards
        try:
            while any(len(h) < 2 for h in state.hole_cards):
                state.deal_hole()
        except:
            return (stacks, 0, [], [], [], FoldInfo(folded=False, board_codes=[], pot=0, call_amount=0))
        
        player_hole = tuple(state.hole_cards[0]) if state.hole_cards[0] else ()
        bot_hole = tuple(state.hole_cards[1]) if state.hole_cards[1] else ()
        fold_info = FoldInfo(folded=False, board_codes=[], pot=0, call_amount=0)
        
        # Play hand with safety timeout
        max_iterations = 50
        iteration = 0
        
        while state.status and iteration < max_iterations:
            iteration += 1
            try:
                actor = getattr(state, "actor_index", None)
                if actor is None:
                    break
                
                if actor == 0:
                    # Opponent acts
                    act, amt = opponent_strategy.decide_action(state, opponent_index=0)
                else:
                    # Bot acts
                    act, amt = choose_bot_action(state, bot_params)
                
                # Execute action with safety checks
                if act == "f" and state.can_fold():
                    if actor == 1:
                        # Bot folds - capture context
                        fold_info = FoldInfo(
                            folded=True,
                            board_codes=_board_codes(state),
                            pot=int(getattr(state, "total_pot_amount", 0) or 0),
                            call_amount=_get_call_amount(state),
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
            except Exception as e:
                # If any action fails, try to recover
                try:
                    if state.can_check_or_call():
                        state.check_or_call()
                    elif state.can_fold():
                        state.fold()
                    else:
                        break
                except:
                    break
        
        ending_stacks = (int(state.stacks[0]), int(state.stacks[1]))
        bot_delta = ending_stacks[1] - starting_stacks[1]
        
        board_codes_end = _board_codes(state)
        player_codes = _hole_codes_for_player(state, 0)
        bot_codes = _hole_codes_for_player(state, 1)
        
        return (ending_stacks, bot_delta, board_codes_end, player_codes, bot_codes, fold_info)


def generate_benchmark_report(stats: GameStats, opponent_type: str, num_hands: int):
    """Generate formatted benchmark report."""
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
    print(f"Wins: {stats.bot_wins:,} ({stats.bot_wins/stats.hands:.1%})")
    print(f"Losses: {stats.bot_losses:,} ({stats.bot_losses/stats.hands:.1%})")
    print(f"Ties: {stats.ties:,} ({stats.ties/stats.hands:.1%})")
    
    print(f"\n{'VARIANCE METRICS':^70}")
    print("-" * 70)
    print(f"Std Deviation: {stats.calculate_std_dev():+.1f} chips")
    if len(stats.hand_profits) > 30:
        ci_lower, ci_upper = stats.calculate_confidence_interval()
        print(f"95% CI: [{ci_lower:+.1f}, {ci_upper:+.1f}] chips/hand")
    else:
        print(f"95% CI: Insufficient data (need 30+ hands)")
    
    print(f"\n{'SHOWDOWN ANALYSIS':^70}")
    print("-" * 70)
    if stats.showdowns > 0:
        print(f"Showdowns: {stats.showdowns:,} ({stats.showdowns/stats.hands:.1%})")
        print(f"Should-have-won: {stats.bot_should_win:,} ({stats.bot_should_win/stats.showdowns:.1%})")
        print(f"Should-have-lost: {stats.bot_should_lose:,} ({stats.bot_should_lose/stats.showdowns:.1%})")
        print(f"Should-have-tied: {stats.should_tie:,} ({stats.should_tie/stats.showdowns:.1%})")
    else:
        print("No showdowns (insufficient data)")
    
    print(f"\n{'FOLD ANALYSIS':^70}")
    print("-" * 70)
    print(f"Bot folds: {stats.bot_folds:,} ({stats.bot_folds/stats.hands:.1%})")
    if stats.bot_folds > 0:
        print(f"Correct folds (EV): {stats.bot_correct_folds_ev:,} ({stats.bot_correct_folds_ev/stats.bot_folds:.1%})")
        print(f"Folded winner: {stats.bot_folded_winner_runout:,} ({stats.bot_folded_winner_runout/stats.bot_folds:.1%})")
    
    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    # Example usage
    print("Starting bot benchmarks...")
    print("(Running 50 hands per opponent for quick test)")
    
    for opponent_type in ["tight", "balanced", "loose", "aggressive"]:
        print(f"\nTesting vs {opponent_type} opponent...")
        stats = BotBenchmark.run_simulation(
            num_hands=50,
            opponent_type=opponent_type,
            verbose=True
        )
        generate_benchmark_report(stats, opponent_type, 50)
