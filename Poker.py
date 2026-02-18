from __future__ import annotations
import re
import random
from dataclasses import dataclass
from typing import Optional
import itertools
from functools import lru_cache
from pokerkit import Automation, NoLimitTexasHoldem
from pokerkit.hands import StandardHighHand


# Metric Evaluation
from dataclasses import dataclass

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

    # NEW: fold metrics
    bot_folds: int = 0
    bot_correct_folds_ev: int = 0
    bot_folded_winner_runout: int = 0  # “folded to bluff” proxy

    def print_summary(self):
        print("\n================== SESSION STATS ==================")
        print(f"Hands played: {self.hands}")
        print(f"Bot wins (actual): {self.bot_wins}")
        print(f"Bot losses (actual): {self.bot_losses}")
        print(f"Ties (actual): {self.ties}")

        if self.hands:
            print(f"Bot win rate: {self.bot_wins / self.hands:.2%}")

        print(f"\nHands with full board (showdown-able): {self.showdowns}")
        print(f"Bot should-have-won (cards): {self.bot_should_win}")
        print(f"Bot should-have-lost (cards): {self.bot_should_lose}")
        print(f"Should-have-tied (cards): {self.should_tie}")

        print(f"\nBot folds: {self.bot_folds}")
        print(f"Bot correct folds (EV-based): {self.bot_correct_folds_ev}")
        print(f"Bot folded winner (runout proxy): {self.bot_folded_winner_runout}")
        print("====================================================\n")
# Helpers: display / parsing


_RANK_NAME = {
    "2": "Two",
    "3": "Three",
    "4": "Four",
    "5": "Five",
    "6": "Six",
    "7": "Seven",
    "8": "Eight",
    "9": "Nine",
    "T": "Ten",
    "J": "Jack",
    "Q": "Queen",
    "K": "King",
    "A": "Ace",
}

_SUIT_NAME = {
    "C": "Clubs",
    "D": "Diamonds",
    "H": "Hearts",
    "S": "Spades",
}


def _code_to_english(rank: str, suit: str) -> str:
    r = _RANK_NAME.get(rank.upper(), rank.upper())
    s = _SUIT_NAME.get(suit.upper(), suit.upper())
    return f"{r} of {s}"


def _card_to_english(card) -> str:
    if card is None:
        return ""

    s = str(card).strip()

    m = re.fullmatch(r"\[?\s*([2-9TJQKA])\s*([CDHS])\s*\]?", s, flags=re.IGNORECASE)
    if m:
        return _code_to_english(m.group(1), m.group(2))

    if "(" in s and ")" in s:
        s2 = s.split("(", 1)[0].strip()
        s2 = s2.title().replace(" Of ", " of ")
        return s2

    return s.title().replace(" Of ", " of ")


def _cards_to_str(cards) -> str:
    if cards is None:
        return ""
    try:
        return ", ".join(_card_to_english(c) for c in cards)
    except TypeError:
        return _card_to_english(cards)


def _board_str(state) -> str:
    return _cards_to_str(state.board_cards)



def _stacks_str(state) -> str:
    return f"You: {state.stacks[0]} | Bot: {state.stacks[1]} | Pot: {getattr(state, 'total_pot_amount', '??')}"


def _legal_actions_str(state) -> str:
    actions = []
    if state.can_fold():
        actions.append("f=fold")
    if state.can_check_or_call():
        cca = getattr(state, "checking_or_calling_amount", None)
        if cca is None or cca == 0:
            actions.append("c=check")
        else:
            actions.append(f"c=call({cca})")
    # Raise/bet
    min_to = getattr(state, "min_completion_betting_or_raising_to_amount", None)
    max_to = getattr(state, "max_completion_betting_or_raising_to_amount", None)
    if min_to is not None and max_to is not None and min_to <= max_to and state.can_complete_bet_or_raise_to(min_to):
        actions.append(f"r <amt>=raise_to [{min_to}..{max_to}]")
        actions.append("a=all-in")
    return " | ".join(actions) if actions else "(no actions?)"


def _prompt_int(msg: str, lo: int, hi: int) -> int:
    while True:
        s = input(msg).strip()
        try:
            v = int(s)
            if lo <= v <= hi:
                return v
        except ValueError:
            pass
        print(f"Enter an integer in [{lo}, {hi}].")


def _street_name(state) -> str:
  
    i = getattr(state, "street_index", None)
    if i is None:
        return "Preflop"
    return {0: "Preflop", 1: "Flop", 2: "Turn", 3: "River"}.get(i, f"Street {i}")


def _board_one_line(state) -> str:

    cards = list(getattr(state, "board_cards", None) or [])
    if not cards:
        # Preflop or no board yet
        return f"{_street_name(state)}: (no board)"

    return f"{_street_name(state)}: " + _cards_to_str(cards)


_RANK_TO_VALUE = {
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7,
    "8": 8, "9": 9, "T": 10, "J": 11, "Q": 12, "K": 13, "A": 14,
}

def _card_code(card: object) -> str:
    """Return short code like 'As' or '4d' for a pokerkit Card or code string."""
    s = str(card).strip()
    m = re.fullmatch(r"\[?\s*([2-9TJQKA])\s*([CDHS])\s*\]?", s, flags=re.IGNORECASE)
    if m:
        return m.group(1).upper() + m.group(2).upper()
    # try to parse trailing (As)
    if "(" in s and ")" in s:
        inside = s.split("(", 1)[1].split(")", 1)[0].strip()
        if len(inside) >= 2:
            return inside[0].upper() + inside[1].upper()
    # fallback
    return s

def _rank_of(code: str) -> str:
    return code[0]

def _suit_of(code: str) -> str:
    return code[1]

def _value_of(code: str) -> int:
    return _RANK_TO_VALUE.get(_rank_of(code).upper(), 0)

def _hole_codes_for_player(state, player_index: int):
    """Return list of two short codes like ['As','Kd'] for the player's hole cards."""
    try:
        hc = state.hole_cards[player_index]
    except Exception:
        # defensive: try to read cached fields
        hc = getattr(state, "hole_cards", [[], []])[player_index]
    return [_card_code(c) for c in hc]

def _board_codes(state):
    return [_card_code(c) for c in (getattr(state, "board_cards", None) or [])]


import itertools
from functools import lru_cache

# Opponent Modeling Helpers
# Assists monte carlo equity calculator by narrowing down possible hands opponent can have based on betting pressure

def _combo_key(c1: str, c2: str) -> tuple[str, str]:
    """Canonical ordering for 2-card combo codes like 'AS','KD'."""
    return tuple(sorted([c1, c2]))

def _preflop_strength_score(c1: str, c2: str) -> float:
    """
    Heuristic score for a 2-card hand (higher is stronger).
    Not perfect; good enough to build "tight vs loose" ranges.
    """
    r1, s1 = c1[0], c1[1]
    r2, s2 = c2[0], c2[1]
    v1 = _RANK_TO_VALUE[r1]
    v2 = _RANK_TO_VALUE[r2]
    hi, lo = max(v1, v2), min(v1, v2)

    suited = (s1 == s2)
    pair = (r1 == r2)
    gap = abs(v1 - v2)

    score = 0.0
    if pair:
        # pairs are very strong, especially high
        score += 100 + hi * 6
    else:
        # high cards matter a lot
        score += hi * 4 + lo * 2
        if suited:
            score += 6
        # connectors / one-gappers slightly better
        if gap == 1:
            score += 5
        elif gap == 2:
            score += 2
        # broadway bonus
        if hi >= 11 and lo >= 10:
            score += 6
        # ace bonus
        if hi == 14:
            score += 4

    return score

@lru_cache(maxsize=1)
def _preflop_percentile_table():
    """
    Build percentile ranks for all unordered 2-card combos in a 52-card deck.
    Returns dict: (c1,c2) -> percentile in [0,1], where 1.0 = strongest.
    """
    deck = [r + s for r in "23456789TJQKA" for s in "CDHS"]
    combos = []
    for i in range(len(deck)):
        for j in range(i + 1, len(deck)):
            c1, c2 = deck[i], deck[j]
            score = _preflop_strength_score(c1, c2)
            combos.append((score, _combo_key(c1, c2)))

    combos.sort(key=lambda x: x[0])  # ascending by score
    n = len(combos)
    pct = {}
    for idx, (_, key) in enumerate(combos):
        # percentile: strongest near 1.0
        pct[key] = (idx + 1) / n
    return pct

def _is_in_top_fraction(c1: str, c2: str, top_frac: float) -> bool:
    """
    True if combo is in top 'top_frac' fraction of hands according to percentile table.
    Example: top_frac=0.20 means top 20% hands.
    """
    top_frac = max(0.01, min(1.0, top_frac))
    pct = _preflop_percentile_table()
    p = pct.get(_combo_key(c1, c2), 0.0)
    return p >= (1.0 - top_frac)


#================================================================
# Helpers for bot's Monte Carlo Equity Calculations:
# Improved Opponent Modeling (narrows range of opponents possible strong hands)
# Samples top 15% of hands in equity simulations
RANKS = "23456789TJQKA"
SUITS = "CDHS"

def _all_deck_codes():
    return [r + s for r in RANKS for s in SUITS]

def _codes_to_eval_str(codes) -> str:
    # evaluator examples use lowercase suits, so normalize
    return "".join(c[0].upper() + c[1].lower() for c in codes)

def determine_card_winner(player_hole_codes, bot_hole_codes, board_codes) -> str:
    """
    Returns: 'bot', 'player', or 'tie' based purely on final board + hole cards.
    Requires board_codes to have 5 cards.
    """
    if len(board_codes) != 5:
        return "tie"  # undefined without full board

    player_hand = StandardHighHand.from_game(
        _codes_to_eval_str(player_hole_codes),
        _codes_to_eval_str(board_codes),
    )
    bot_hand = StandardHighHand.from_game(
        _codes_to_eval_str(bot_hole_codes),
        _codes_to_eval_str(board_codes),
    )

    if bot_hand > player_hand:
        return "bot"
    if bot_hand < player_hand:
        return "player"
    return "tie"

def _remaining_deck_excluding(known_codes: set[str]) -> list[str]:
    deck = [r + s for r in "23456789TJQKA" for s in "CDHS"]
    return [c for c in deck if c not in known_codes]

def _complete_board_random(board_codes: list[str], known_codes: set[str], rng: random.Random) -> list[str]:
    """Fill board to 5 cards by sampling uniformly from remaining deck."""
    need = 5 - len(board_codes)
    if need <= 0:
        return board_codes[:5]
    deck = _remaining_deck_excluding(known_codes)
    rng.shuffle(deck)
    return board_codes + deck[:need]

def estimate_equity_vs_known_hand(
    hero_hole_codes: list[str],
    villain_hole_codes: list[str],
    board_codes: list[str],
    trials: int = 3000,
    rng: random.Random | None = None,
) -> float:
    """
    Monte Carlo equity against opponent's ACTUAL hole cards.
    Only samples remaining board cards.
    """
    if rng is None:
        rng = random

    wins = ties = 0
    hero_s = _codes_to_eval_str(hero_hole_codes)
    vil_s = _codes_to_eval_str(villain_hole_codes)

    known = set(hero_hole_codes + villain_hole_codes + board_codes)

    for _ in range(trials):
        full_board = _complete_board_random(board_codes, known, rng)
        board_s = _codes_to_eval_str(full_board)

        hero_hand = StandardHighHand.from_game(hero_s, board_s)
        vil_hand = StandardHighHand.from_game(vil_s, board_s)

        if hero_hand > vil_hand:
            wins += 1
        elif hero_hand == vil_hand:
            ties += 1

    return (wins + 0.5 * ties) / trials

def winner_on_one_random_runout(player_codes: list[str], bot_codes: list[str], board_codes: list[str], rng: random.Random) -> str:
    """Returns 'bot'/'player'/'tie' by completing board once randomly and comparing actual hands."""
    known = set(player_codes + bot_codes + board_codes)
    full_board = _complete_board_random(board_codes, known, rng)
    return determine_card_winner(player_codes, bot_codes, full_board)


def estimate_equity_vs_range(
    state,
    hero_index: int,
    *,
    trials: int = 2000,
    villain_top_frac: float = 0.50,
    rng: random.Random | None = None,
) -> float:
    """
    Monte Carlo equity where villain hole cards are sampled from a 'top X%' range.

    villain_top_frac:
      1.00 = uniform random (everyone plays everything)
      0.20 = villain has top 20% hands (tight/strong)
      0.10 = top 10% hands (very strong line)
    """
    if rng is None:
        rng = random

    hero_hole = _hole_codes_for_player(state, hero_index)
    board = _board_codes(state)

    known = set(hero_hole + board)
    deck = [c for c in _all_deck_codes() if c not in known]

    need_board = max(0, 5 - len(board))
    hero_hole_s = _codes_to_eval_str(hero_hole)

    wins = ties = 0

    # To avoid rare infinite loops when range is too tight + cards removed,
    # cap attempts at finding a villain hand in-range.
    max_pick_attempts = 40

    for _ in range(trials):
        sample = deck[:]
        rng.shuffle(sample)

        # --- Pick villain hole from range ---
        villain_hole = None
        # try a few random pairs from the shuffled sample
        # (fast enough for now; optimize later if needed)
        for t in range(max_pick_attempts):
            c1 = sample[(2 * t) % len(sample)]
            c2 = sample[(2 * t + 1) % len(sample)]
            if c1 == c2:
                continue
            if _is_in_top_fraction(c1, c2, villain_top_frac):
                villain_hole = [c1, c2]
                break

        # fallback: if we couldn't find an in-range hand (too tight),
        # just take the first two available.
        if villain_hole is None:
            villain_hole = sample[:2]

        # remove villain hole from availability for board fill
        remaining = [c for c in sample if c not in villain_hole]

        fill = remaining[:need_board]
        full_board = board + fill

        villain_hole_s = _codes_to_eval_str(villain_hole)
        board_s = _codes_to_eval_str(full_board)

        hero_hand = StandardHighHand.from_game(hero_hole_s, board_s)
        vil_hand = StandardHighHand.from_game(villain_hole_s, board_s)

        if hero_hand > vil_hand:
            wins += 1
        elif hero_hand == vil_hand:
            ties += 1

    return (wins + 0.5 * ties) / trials

# Fold Equity Modeling

def estimate_villain_top_frac(board_len: int, required_eq: float, cca: int, pot: int) -> float:
    """
    Opponent modeling heuristic:
    Use betting pressure to infer villain range strength/tightness.

    Returns villain_top_frac:
      0.15 => villain likely strong/tight range (top 15%)
      0.60 => villain wider/weaker range (top 60%)
    """
    # pressure: call cost relative to pot
    pressure = cca / (pot + cca) if (pot + cca) > 0 else 0.0

    # baseline by street: later streets tend to be narrower when money goes in
    base = {0: 0.55, 3: 0.45, 4: 0.40, 5: 0.35}.get(board_len, 0.50)

    # tighten with pressure
    # bigger pressure => smaller top_frac (stronger range)
    top_frac = base - 0.60 * pressure

    # clamp
    return max(0.10, min(0.70, top_frac))

def estimate_fold_probability(villain_top_frac: float, raise_to: int, pot: int) -> float:
    """
    Fold equity model:
    - tighter villain ranges call more (lower fold prob)
    - bigger raises win more folds (higher fold prob)

    Returns fold probability in [0.05, 0.75].
    """
    # tighter range => less folding
    tightness = 1.0 - villain_top_frac  # e.g. top 0.15 => tightness 0.85

    # raise pressure relative to pot
    r = raise_to / max(1, pot)
    size_term = min(1.0, 0.35 * r)  # bigger raises increase folds

    # base fold depends on opponent looseness + size
    # loose villain (top_frac high) folds more; tight villain folds less.
    base = 0.40 * villain_top_frac + 0.10  # 0.10..0.38

    fold_p = base + size_term - 0.25 * tightness
    return max(0.05, min(0.75, fold_p))

def ev_of_raise(eq_when_called: float, fold_p: float, pot: int, invest: int) -> float:
    """
    Simplified EV model for a raise:
    - With prob fold_p, we win current pot.
    - With prob 1-fold_p, we go to showdown with equity eq_when_called,
      in a pot approx pot + 2*invest (we put in invest; villain calls invest).
    - Cost to us: invest (this is approximate; good enough to drive behavior).
    """
    pot_if_called = pot + 2 * invest
    return fold_p * pot + (1.0 - fold_p) * (eq_when_called * pot_if_called - (1.0 - eq_when_called) * invest)

# Bot policy ========================================================

@dataclass
class BotParams:
    # Core difficulty knobs
    call_edge: float = 0.02          # requires equity >= pot_odds + call_edge to call
    value_raise_freq: float = 0.90   # when strong, how often to raise instead of call/check

    # Style knobs
    bluff_freq: float = 0.05         # how often to bluff/semi-bluff when not +EV (positive equity value)
    bluff_additional_risk: float = 0.08  # only bluff if required_eq isn't too high 

    # Sizing knobs
    value_raise_frac: float = 0.45   # raise-to size as fraction of stack (clamped to min/max)
    bluff_raise_frac: float = 0.30   # smaller than value sizing

    # All-in behavior
    jam_equity: float = 0.82         # if equity >= this, bot may jam
    jam_freq: float = 0.10           # chance to jam when jam_equity met (and jam is legal)


"""""
bot acts off of monte carlo equity in conjuction with opponent modeling
which narrows the range of cards that the algorithim will simulate when calculating equity
Rather than sampling uniformly from unseen cards, the algorithim will sample from the top X percentage of hands,
where X fluctuates based on call amount in relation to pot, and the current street
(more pressure == stronger villain -> equity drops)

Fold equity allows bot to now raise even if equity (chances of winning with current hand) are weaker than desired)

"""""
def choose_bot_action(state, params: BotParams) -> tuple[str, Optional[int]]:
    actor = getattr(state, "actor_index", None)
    if actor is None:
        return ("c", None)

    can_call = state.can_check_or_call()
    can_fold = state.can_fold()

    min_to = getattr(state, "min_completion_betting_or_raising_to_amount", None)
    max_to = getattr(state, "max_completion_betting_or_raising_to_amount", None)
    can_raise = (
        min_to is not None
        and max_to is not None
        and min_to <= max_to
        and state.can_complete_bet_or_raise_to(int(min_to))
    )

    # call amount BEFORE acting
    cca = getattr(state, "checking_or_calling_amount", None)
    if cca is None:
        cca = getattr(state, "check_or_call_amount", None)
    if cca is None:
        cca = getattr(state, "calling_amount", None)
    cca = 0 if cca is None else int(cca)

    pot = getattr(state, "total_pot_amount", None)
    pot = 0 if pot is None else int(pot)

    my_stack = int(state.stacks[actor])
    board_len = len(_board_codes(state))

    # --- Decide how tight villain range is based on pressure ---
    required_eq = cca / (pot + cca) if (pot + cca) > 0 else 1.0
    villain_top_frac = estimate_villain_top_frac(board_len, required_eq, cca, pot)

    # --- Monte Carlo equity vs inferred range ---
    if board_len == 0:
        trials = 1200
    elif board_len == 3:
        trials = 2000
    else:
        trials = 3000

    eq = estimate_equity_vs_range(
        state,
        actor,
        trials=trials,
        villain_top_frac=villain_top_frac,
    )

    # --- helper sizing ---
    def small_raise_to():
        if can_raise and min_to is not None and state.can_complete_bet_or_raise_to(int(min_to)):
            return int(min_to)
        return None

    def big_raise_to(frac_of_stack: float):
        if not can_raise or min_to is None or max_to is None:
            return None
        target = int(my_stack * frac_of_stack)
        amt = max(int(min_to), target)
        amt = min(int(max_to), amt)
        if state.can_complete_bet_or_raise_to(amt):
            return amt
        return small_raise_to()

    # Decision Logic
  
    # Free check spots: bet sometimes when strong
    if cca == 0 and can_call:
        if can_raise and eq >= 0.62 and random.random() < params.value_raise_freq:
            amt = big_raise_to(params.value_raise_frac) or small_raise_to()
            if amt is not None:
                return ("r", amt)
        return ("c", None)

    # Value raise when clearly strong
    if can_raise and eq >= max(0.70, required_eq + 0.12):
        # occasional jam
        if eq >= params.jam_equity and random.random() < params.jam_freq:
            if max_to is not None and state.can_complete_bet_or_raise_to(int(max_to)):
                return ("a", None)

        if random.random() < params.value_raise_freq:
            amt = big_raise_to(params.value_raise_frac) or small_raise_to()
            if amt is not None:
                return ("r", amt)

        # otherwise call if +EV
        if can_call and eq >= required_eq + params.call_edge:
            return ("c", None)

    # Call if +EV with cushion
    if can_call and eq >= required_eq + params.call_edge:
        return ("c", None)

    # --- Bluff / semi-bluff using fold equity modeling ---
    if can_raise and random.random() < params.bluff_freq:
        # Don't bluff into extremely strong lines (very tight range)
        if villain_top_frac >= 0.18:  # looser than top 18% -> can fold more
            amt = big_raise_to(params.bluff_raise_frac) or small_raise_to()
            if amt is not None:
                fold_p = estimate_fold_probability(villain_top_frac, raise_to=amt, pot=pot)
                # approximate invest as raise_to amount (good enough for decision ranking)
                invest = amt
                # EV(raise) compared to EV(fold)=0 baseline
                evr = ev_of_raise(eq_when_called=eq, fold_p=fold_p, pot=pot, invest=invest)
                if evr > 0:
                    return ("r", amt)

    # Otherwise fold if facing a bet
    if can_fold:
        return ("f", None)

    return ("c", None) if can_call else ("f", None)

# Game Logic ========================================================

def play_one_hand(
    stacks: tuple[int, int],
    *,
    sb: int = 50,
    bb: int = 100,
    min_bet: int = 100,
    bot_params: BotParams = BotParams(),
) -> tuple[int, int]:

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

    starting_stacks = tuple(int(x) for x in stacks)

    #Deal and remember hole cards (2 each for hold'em) ---

    while any(len(h) < 2 for h in state.hole_cards):
        state.deal_hole()

    player_hole = tuple(state.hole_cards[0])
    bot_hole = tuple(state.hole_cards[1])

    bot_folded = False
    bot_fold_board_codes = []
    bot_fold_pot = 0
    bot_fold_call = 0

    print("\n" + "=" * 60)
    print("New hand!")
    last_street = None

    while state.status:   
        if state.street_index != last_street:
            last_street = state.street_index
            print("\n" + _board_one_line(state))
            print(f"Your hand: {_cards_to_str(player_hole)}")
            print(_stacks_str(state))


        actor = getattr(state, "actor_index", None)
        if actor is None:
            continue

        if actor == 0:
            print("\n=============================================================================")
            print("\nYour turn.")
            print("Legal:", _legal_actions_str(state))
            cmd = input("Action (fold/check/raise <amt>/a): ").strip().lower()

            if cmd == "f" and state.can_fold():
                state.fold()
                print("You fold.")
            elif cmd == "c" and state.can_check_or_call():
            # Read call amount BEFORE acting (after acting it may become 0)
                cca = getattr(state, "checking_or_calling_amount", None)

            # Fallbacks for version differences
                if cca is None:
                    cca = getattr(state, "check_or_call_amount", None)
                if cca is None:
                    cca = getattr(state, "calling_amount", None)

            # If still unknown, treat as check
                cca = 0 if cca is None else int(cca)

                state.check_or_call()

                if cca == 0:
                    print("You check.")
                else:
                    print(f"You call {cca}.")

            elif cmd.startswith("r"):
                parts = cmd.split()
                if len(parts) != 2:
                    print("Use: r <amount_to_raise_to>")
                    continue
                try:
                    amt = int(parts[1])
                except ValueError:
                    print("Raise amount must be an integer.")
                    continue
                if state.can_complete_bet_or_raise_to(amt):
                    state.complete_bet_or_raise_to(amt)
                    print(f"You raise to {amt}.")
                else:
                    min_to = getattr(state, "min_completion_betting_or_raising_to_amount", None)
                    max_to = getattr(state, "max_completion_betting_or_raising_to_amount", None)
                    print(f"Illegal raise_to. Range is typically [{min_to}..{max_to}] if raising is allowed.")
            elif cmd == "a":
                max_to = getattr(state, "max_completion_betting_or_raising_to_amount", None)
                if max_to is None:
                    print("All-in not available here.")
                    continue
                if state.can_complete_bet_or_raise_to(max_to):
                    state.complete_bet_or_raise_to(max_to)
                    print(f"You go all-in to {max_to}.")
                else:
                    print("All-in not legal here.")
            else:
                print("Invalid action. Try again.")
                continue
            print("\n=============================================================================")
   

        else:
            act, amt = choose_bot_action(state, bot_params)
            if act == "f" and state.can_fold():
                # capture fold context BEFORE folding
                bot_folded = True
                bot_fold_board_codes = _board_codes(state)

                bot_fold_pot = int(getattr(state, "total_pot_amount", 0) or 0)

                cca2 = getattr(state, "checking_or_calling_amount", None)
                if cca2 is None:
                    cca2 = getattr(state, "check_or_call_amount", None)
                if cca2 is None:
                    cca2 = getattr(state, "calling_amount", None)
                bot_fold_call = int(cca2 or 0)

                state.fold()
                print("\nBot folds.")

            elif act == "c" and state.can_check_or_call():
                cca = getattr(state, "checking_or_calling_amount", None)
                if cca is None:
                    cca = getattr(state, "check_or_call_amount", None)
                if cca is None:
                    cca = getattr(state, "calling_amount", None)
                cca = 0 if cca is None else int(cca)

                state.check_or_call()
                print("\nBot checks." if cca == 0 else f"\nBot calls {cca}.")

            elif act == "a":
                max_to = getattr(state, "max_completion_betting_or_raising_to_amount", None)
                if max_to is not None and state.can_complete_bet_or_raise_to(max_to):
                    state.complete_bet_or_raise_to(max_to)
                    print(f"\nBot goes all-in to {max_to}.")
                else:
                    state.check_or_call()
                    print("\nBot calls (fallback).")
            elif act == "r" and amt is not None and state.can_complete_bet_or_raise_to(amt):
                state.complete_bet_or_raise_to(amt)
                print(f"\nBot raises to {amt}.")
            else:
                if state.can_check_or_call():
                    state.check_or_call()
                    print("\nBot calls/checks (fallback).")
                else:
                    state.fold()
                    print("\nBot folds (fallback).")
    
    ending_stacks = (int(state.stacks[0]), int(state.stacks[1]))
    bot_delta = ending_stacks[1] - starting_stacks[1]
    delta = ending_stacks[0] - starting_stacks[0]
        
    if delta > 0:
        outcome = f"You WON the hand (+{delta})."
    elif delta < 0:
        outcome = f"You LOST the hand ({delta})."
    else:
        outcome = "Hand was a CHOP (0)."
    
    print("\nHand over.")
    print("Final board:")
    print(_board_one_line(state)) 
    print(f"Your cards: {_cards_to_str(player_hole)}")
    print(f"Bot cards:  {_cards_to_str(bot_hole)}")
    print(_stacks_str(state))
    print(outcome)

    board_codes_end = _board_codes(state)
    player_codes = _hole_codes_for_player(state, 0)
    bot_codes = _hole_codes_for_player(state, 1)

    fold_info = (bot_folded, bot_fold_board_codes, bot_fold_pot, bot_fold_call)

    return (ending_stacks, bot_delta, board_codes_end, player_codes, bot_codes, fold_info)

def main() -> None:
    print("PokerKit: Heads-Up No Limit Hold 'Em — You vs Bot")

    stacks = (10000, 10000)
    sb, bb, min_bet = 50, 100, 100

    bot_params = BotParams()
    stats = GameStats()

    while True:
        
        (stacks, bot_delta, board_codes, player_codes, bot_codes, fold_info) = play_one_hand(
        stacks, sb=sb, bb=bb, min_bet=min_bet, bot_params=bot_params) 

        (bot_folded, fold_board, fold_pot, fold_call) = fold_info

        # ---- update stats ----
        stats.hands += 1

        # Actual winner (by chip delta)
        if bot_delta > 0:
            stats.bot_wins += 1
        elif bot_delta < 0:
            stats.bot_losses += 1
        else:
            stats.ties += 1

        # "Should have won" (by cards), only if board completed
        if len(board_codes) == 5:
            stats.showdowns += 1
            should = determine_card_winner(player_codes, bot_codes, board_codes)
            if should == "bot":
                stats.bot_should_win += 1
            elif should == "player":
                stats.bot_should_lose += 1
            else:
                stats.should_tie += 1
        if bot_folded:
            stats.bot_folds += 1

            # required equity to call (pot odds)
            required_eq = (fold_call / (fold_pot + fold_call)) if (fold_pot + fold_call) > 0 else 1.0

            # equity vs your *actual* hand at fold time (simulate remaining board only)
            eq_vs_actual = estimate_equity_vs_known_hand(
                hero_hole_codes=bot_codes,          # bot hole cards
                villain_hole_codes=player_codes,    # your hole cards
                board_codes=fold_board,             # board at fold time (0/3/4/5 cards)
                trials=2500,
            )

            # If equity wasn't enough to justify calling, fold is correct (EV-based)
            if eq_vs_actual < required_eq + bot_params.call_edge:
                stats.bot_correct_folds_ev += 1

            # “folded to bluff” proxy: random runout once
            rng = random.Random(stats.hands * 99991 + 17)
            runout_winner = winner_on_one_random_runout(player_codes, bot_codes, fold_board, rng)

            if runout_winner == "bot":
                stats.bot_folded_winner_runout += 1

        # Print summary after each hand (or comment this out and print only at end)
        stats.print_summary()

        if stacks[0] <= 0:
            print("\nYou lost it all. Game over.")
            stats.print_summary()
            return
        if stacks[1] <= 0:
            print("\nBot is broke. You win!")
            stats.print_summary()
            return

        s = input("\nPlay another hand? (y/n): ").strip().lower()
        if s != "y":
            stats.print_summary()
            return

        


if __name__ == "__main__":
    main()
