from dataclasses import dataclass, field
import statistics


@dataclass
class FoldInfo:
    """Information captured when bot folds."""
    folded: bool
    board_codes: list
    pot: int
    call_amount: int


@dataclass
class OpponentProfile:
    """Tracks opponent tendencies across sessions."""
    # Aggression stats
    total_aggressive_actions: int = 0  # bets + raises
    total_passive_actions: int = 0    # calls
    total_folds: int = 0
    
    # Fold to aggression
    fold_to_raise_preflop: int = 0
    folds_to_raise_preflop: int = 0
    fold_to_raise_postflop: int = 0
    folds_to_raise_postflop: int = 0
    
    # Showdown stats
    showdown_hands: list = field(default_factory=list)  # list of (hole_cards, result)
    hands_seen_at_showdown: int = 0
    
    def aggression_index(self) -> float:
        """Aggression Index: (bets + raises) / calls. Higher = more aggressive."""
        if self.total_passive_actions == 0:
            return float(self.total_aggressive_actions) if self.total_aggressive_actions > 0 else 1.0
        return self.total_aggressive_actions / self.total_passive_actions
    
    def fold_to_raise_freq(self, street: str = "postflop") -> float:
        """Frequency opponent folds to raises. street: 'preflop' or 'postflop'."""
        if street == "preflop":
            total = self.fold_to_raise_preflop + self.folds_to_raise_preflop
        else:
            total = self.fold_to_raise_postflop + self.folds_to_raise_postflop
        
        if total == 0:
            return 0.5  # assume neutral if no data
        
        if street == "preflop":
            folds = self.folds_to_raise_preflop
        else:
            folds = self.folds_to_raise_postflop
        
        return folds / total if total > 0 else 0.5
    
    def print_summary(self):
        print("\n================== OPPONENT PROFILE ==================")
        print(f"Aggression Index: {self.aggression_index():.2f}")
        print(f"Total aggressive actions (bets+raises): {self.total_aggressive_actions}")
        print(f"Total passive actions (calls): {self.total_passive_actions}")
        print(f"Total folds: {self.total_folds}")
        print(f"\nFold to raise (preflop): {self.fold_to_raise_freq('preflop'):.1%}")
        print(f"Fold to raise (postflop): {self.fold_to_raise_freq('postflop'):.1%}")
        print(f"Hands seen at showdown: {self.hands_seen_at_showdown}")
        print("====================================================\n")


@dataclass
class GameStats:
    hands: int = 0
    bot_wins: int = 0
    bot_losses: int = 0
    ties: int = 0

    showdowns: int = 0
    bot_should_win: int = 0
    bot_should_lose: int = 0
    should_tie: int = 0

    # fold metrics
    bot_folds: int = 0
    bot_correct_folds_ev: int = 0
    bot_folded_winner_runout: int = 0  # "folded to bluff" proxy
    
    # Performance tracking
    total_profit: int = 0  # Total chips won/lost
    hand_profits: list = field(default_factory=list)  # Per-hand profit/loss for variance
    initial_buy_in: int = 10000  # Starting stack
    bb: int = 100  # Big blind size

    def calculate_bb_per_100(self) -> float:
        """Calculate win rate in big blinds per 100 hands."""
        if self.hands == 0:
            return 0.0
        return (self.total_profit / self.bb) / max(1, self.hands / 100)

    def calculate_roi(self) -> float:
        """Calculate ROI: (Profit / Buy-in) * 100."""
        if self.initial_buy_in == 0:
            return 0.0
        return (self.total_profit / self.initial_buy_in) * 100

    def calculate_win_percentage(self) -> float:
        """Calculate win percentage: (Wins / Total Hands) * 100."""
        if self.hands == 0:
            return 0.0
        return (self.bot_wins / self.hands) * 100

    def calculate_profit_per_hand(self) -> float:
        """Calculate average profit/loss per hand."""
        if self.hands == 0:
            return 0.0
        return self.total_profit / self.hands

    def calculate_variance(self) -> float:
        """Calculate variance of hand results."""
        if len(self.hand_profits) <= 1:
            return 0.0
        return statistics.variance(self.hand_profits)

    def calculate_std_dev(self) -> float:
        """Calculate standard deviation of results."""
        if len(self.hand_profits) <= 1:
            return 0.0
        return statistics.stdev(self.hand_profits)

    def calculate_confidence_interval(self, confidence: float = 0.95) -> tuple[float, float]:
        """Calculate 95% confidence interval for win rate."""
        if self.hands < 30:
            return (0.0, 0.0)  # Not enough hands for meaningful CI
        
        mean = self.calculate_profit_per_hand()
        std_dev = self.calculate_std_dev()
        # Approximate 95% CI: mean ± 1.96 * std_dev / sqrt(n)
        margin = 1.96 * std_dev / (self.hands ** 0.5)
        return (mean - margin, mean + margin)

    def print_summary(self):
        print("\n" + "=" * 60)
        print("POKER BOT SESSION STATS")
        print("=" * 60)
        
        # Basic stats
        print(f"\nHands played: {self.hands}")
        print(f"Bot wins (actual): {self.bot_wins}")
        print(f"Bot losses (actual): {self.bot_losses}")
        print(f"Ties (actual): {self.ties}")
        
        # Profitability metrics
        print(f"\n{'PROFITABILITY METRICS':^60}")
        print(f"Total profit/loss: {self.total_profit:+,} chips")
        print(f"Win rate: {self.calculate_win_percentage():.1f}%")
        print(f"BB/100 hands: {self.calculate_bb_per_100():+.2f}")
        print(f"ROI: {self.calculate_roi():+.1f}%")
        print(f"Profit per hand: {self.calculate_profit_per_hand():+.1f} chips")
        
        # Showdown analysis
        print(f"\n{'SHOWDOWN ANALYSIS':^60}")
        print(f"Hands with full board: {self.showdowns}")
        if self.showdowns > 0:
            print(f"Bot should-have-won (cards): {self.bot_should_win} ({self.bot_should_win/self.showdowns:.1%})")
            print(f"Bot should-have-lost (cards): {self.bot_should_lose} ({self.bot_should_lose/self.showdowns:.1%})")
            print(f"Should-have-tied (cards): {self.should_tie} ({self.should_tie/self.showdowns:.1%})")
        
        # Fold analysis
        print(f"\n{'FOLD ANALYSIS':^60}")
        print(f"Bot folds: {self.bot_folds}")
        if self.bot_folds > 0:
            print(f"Bot correct folds (EV-based): {self.bot_correct_folds_ev} ({self.bot_correct_folds_ev/self.bot_folds:.1%})")
            print(f"Bot folded winner (runout): {self.bot_folded_winner_runout} ({self.bot_folded_winner_runout/self.bot_folds:.1%})")
        
        # Variance metrics
        if len(self.hand_profits) > 0:
            print(f"\n{'VARIANCE METRICS':^60}")
            print(f"Std deviation: {self.calculate_std_dev():+.1f} chips")
            ci_lower, ci_upper = self.calculate_confidence_interval()
            print(f"95% Confidence Interval: [{ci_lower:+.1f}, {ci_upper:+.1f}] chips/hand")
        
        print("\n" + "=" * 60 + "\n")
