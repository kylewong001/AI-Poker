from __future__ import annotations
import re
import random
from dataclasses import dataclass
from typing import Optional

from pokerkit import Automation, NoLimitTexasHoldem, StandardHighHand


# ----------------------------
# Helpers: display / parsing
# ----------------------------

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

# quick made-hand detectors (very light-weight)
def _counts_by_rank(codes):
    d = {}
    for c in codes:
        r = _rank_of(c)
        d[r] = d.get(r, 0) + 1
    return d

def _counts_by_suit(codes):
    d = {}
    for c in codes:
        s = _suit_of(c)
        d[s] = d.get(s, 0) + 1
    return d

def _has_pair_or_better(hole_codes, board_codes):
    """Return (best_made) where best_made in ('trips','two_pair','pair','none') from the player's perspective."""
    codes = hole_codes + board_codes
    rank_counts = _counts_by_rank(codes)
    hole_rank_counts = _counts_by_rank(hole_codes)
    # trips
    if any(v >= 3 for v in rank_counts.values()):
        return "trips"
    # two pair: either two distinct ranks with count>=2 or hole pair + board pair
    pairs = [r for r, v in rank_counts.items() if v >= 2]
    if len(pairs) >= 2:
        return "two_pair"
    # pair: check if either hole card rank appears on board
    for hr in hole_rank_counts:
        if rank_counts.get(hr, 0) >= 2:
            return "pair"
    return "none"

def _has_top_pair_or_better(hole_codes, board_codes):
    """
    Heuristic: top pair if one of your hole ranks matches the highest-rank card on the board.
    Returns True if top pair or better (two_pair/trips).
    """
    made = _has_pair_or_better(hole_codes, board_codes)
    if made in ("trips", "two_pair"):
        return True
    if made == "pair":
        # determine highest board rank
        if not board_codes:
            return False
        board_vals = sorted((_value_of(c) for c in board_codes), reverse=True)
        top_val = board_vals[0]
        # if one of hole ranks equals top board rank -> top pair
        for hc in hole_codes:
            if _value_of(hc) == top_val:
                return True
    return False

def _has_flush_draw(hole_codes, board_codes):
    """Return True if player has 4 cards to a flush (i.e., a flush draw)."""
    codes = hole_codes + board_codes
    suit_counts = _counts_by_suit(codes)
    if any(v >= 4 for v in suit_counts.values()):
        return True
    return False

def _is_suited(hole_codes):
    return _suit_of(hole_codes[0]) == _suit_of(hole_codes[1])

def _is_pair(hole_codes):
    return _rank_of(hole_codes[0]) == _rank_of(hole_codes[1])

def _is_connector(hole_codes, gap_allowed=1):
    """Rough connector test: ranks adjacent or one-gap. gap_allowed=0 for exact connector."""
    v0, v1 = _value_of(hole_codes[0]), _value_of(hole_codes[1])
    g = abs(v0 - v1)
    return g <= gap_allowed


#================================================================
# Helpers for bot's Monte Carlo Equity Calculations:

RANKS = "23456789TJQKA"
SUITS = "CDHS"

def _all_deck_codes():
    return [r + s for r in RANKS for s in SUITS]

def _codes_to_str(codes) -> str:
    out = []
    for c in codes:
        r = c[0].upper()
        s = c[1].lower()  # evaluator examples use lowercase suits
        out.append(r + s)
    return "".join(out)

def estimate_equity_vs_random(state, hero_index: int, trials, rng: random.Random | None = None) -> float:
    """
    Monte Carlo equity vs a random opponent range.
    Equity = (wins + 0.5 * ties) / trials.
    """
    if rng is None:
        rng = random

    hero_hole = _hole_codes_for_player(state, hero_index)
    board = _board_codes(state)

    known = set(hero_hole + board)
    deck = [c for c in _all_deck_codes() if c not in known]

    need_board = max(0, 5 - len(board))

    wins = ties = 0

    hero_hole_s = _codes_to_str(hero_hole)  # constant across trials

    for _ in range(trials):
        sample = deck[:]           # copy
        rng.shuffle(sample)

        opp_hole = sample[:2]
        fill = sample[2:2 + need_board]
        full_board = board + fill

        opp_hole_s = _codes_to_str(opp_hole)
        board_s = _codes_to_str(full_board)

        hero_hand = StandardHighHand.from_game(hero_hole_s, board_s)
        opp_hand = StandardHighHand.from_game(opp_hole_s, board_s)

        if hero_hand > opp_hand:
            wins += 1
        elif hero_hand == opp_hand:
            ties += 1

    return (wins + 0.5 * ties) / trials

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



def choose_bot_action(state, params: BotParams) -> tuple[str, Optional[int]]:
    
    #Equity-driven bot using Monte Carlo vs a random opponent.

    actor = getattr(state, "actor_index", None)
    if actor is None:
        return ("c", None)

    # --- legality / betting bounds ---
    can_call = state.can_check_or_call()
    can_fold = state.can_fold()

    min_to = getattr(state, "min_completion_betting_or_raising_to_amount", None)
    max_to = getattr(state, "max_completion_betting_or_raising_to_amount", None)
    can_raise = (
        min_to is not None
        and max_to is not None
        and min_to <= max_to
        and state.can_complete_bet_or_raise_to(min_to)
    )

    # Call/check amount (read BEFORE acting)
    cca = getattr(state, "checking_or_calling_amount", None)
    if cca is None:
        cca = getattr(state, "check_or_call_amount", None)
    if cca is None:
        cca = getattr(state, "calling_amount", None)
    cca = 0 if cca is None else int(cca)

    pot = getattr(state, "total_pot_amount", None)
    pot = 0 if pot is None else int(pot)

    my_stack = int(state.stacks[actor])

    # --- Monte Carlo equity ---
    # fewer trials preflop / earlier for speed, more later for accuracy
    board_len = len(_board_codes(state))
    if board_len == 0:
        trials = 1200
    elif board_len == 3:
        trials = 2000
    else:
        trials = 3000

    eq = estimate_equity_vs_random(state, actor, trials=trials)

    # --- helper sizing ---
    def small_raise_to():
        if can_raise and min_to is not None and state.can_complete_bet_or_raise_to(int(min_to)):
            return int(min_to)
        return None

    def big_raise_to(frac_of_stack: float):
        """Raise-to target as a fraction of our remaining stack, clamped to [min_to, max_to]."""
        if not can_raise or min_to is None or max_to is None:
            return None
        target = int(my_stack * frac_of_stack)
        amt = max(int(min_to), target)
        amt = min(int(max_to), amt)
        if state.can_complete_bet_or_raise_to(amt):
            return amt
        # fallback
        sr = small_raise_to()
        return sr

    # --- Decision logic ---

    # If bot can check for free, mostly check; sometimes bet when strong
    if cca == 0 and can_call:
        if eq >= 0.62 and can_raise and random.random() < params.value_raise_freq:
            amt = big_raise_to(params.value_raise_frac) or small_raise_to()
            if amt is not None:
                return ("r", amt)
        return ("c", None)  # check

    # Facing a bet: pot odds
    required_eq = cca / (pot + cca) if (pot + cca) > 0 else 1.0

    # 1) Value raise when strong
    if eq >= max(0.70, required_eq + 0.12) and can_raise:
        # occasional jam
        if eq >= params.jam_equity and random.random() < params.jam_freq:
            if max_to is not None and state.can_complete_bet_or_raise_to(int(max_to)):
                return ("a", None)

        # raise with some frequency, otherwise call
        if random.random() < params.value_raise_freq:
            amt = big_raise_to(params.value_raise_frac) or small_raise_to()
            if amt is not None:
                return ("r", amt)

        if can_call:
            return ("c", None)

    # 2) Call if +EV with cushion
    if can_call and eq >= required_eq + params.call_edge:
        return ("c", None)

    # 3) Bluff occasionally (only if the required equity isn't huge)
    if can_raise and random.random() < params.bluff_freq:
        if required_eq <= (0.33 + params.bluff_additional_risk):
            amt = big_raise_to(params.bluff_raise_frac) or small_raise_to()
            if amt is not None:
                return ("r", amt)

    # 4) Otherwise fold/check
    if can_fold and cca > 0:
        return ("f", None)
    if can_call:
        return ("c", None)
    return ("f", None)


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
                state.fold()
                print("\nBot folds.")
            elif act == "c" and state.can_check_or_call():
                cca = getattr(state, "checking_or_calling_amount", None)
                state.check_or_call()
                print("\nBot checks." if (cca is None or cca == 0) else f"\nBot calls {cca}.")
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

    return (int(state.stacks[0]), int(state.stacks[1]))
def main() -> None:
    print("PokerKit: Heads-Up No Limit Hold 'Em — You vs Bot")

    stacks = (10000, 10000)
    sb, bb, min_bet = 50, 100, 100

    bot_params = BotParams()

    while True:
        stacks = play_one_hand(stacks, sb=sb, bb=bb, min_bet=min_bet, bot_params=bot_params)

        if stacks[0] <= 0:
            print("\nYou lost it all. Game over.")
            return
        if stacks[1] <= 0:
            print("\nBot is broke. You win!")
            return

        s = input("\nPlay another hand? (y/n): ").strip().lower()
        if s != "y":
            return


if __name__ == "__main__":
    main()
