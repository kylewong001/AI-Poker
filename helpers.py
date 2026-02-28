import re
import random
from functools import lru_cache
from pokerkit.hands import StandardHighHand


# === Display/Parsing Helpers ===

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


def _get_call_amount(state) -> int:
    """Extract call amount from state with fallbacks for version differences."""
    cca = getattr(state, "checking_or_calling_amount", None)
    if cca is None:
        cca = getattr(state, "check_or_call_amount", None)
    if cca is None:
        cca = getattr(state, "calling_amount", None)
    return 0 if cca is None else int(cca)


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


# === Card Code Parsing ===

_RANK_TO_VALUE = {
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7,
    "8": 8, "9": 9, "T": 10, "J": 11, "Q": 12, "K": 13, "A": 14,
}

RANKS = "23456789TJQKA"
SUITS = "CDHS"


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


# === Opponent Hand Range Modeling ===

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


# === Deck and Card Evaluation ===

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


def winner_on_one_random_runout(player_codes: list[str], bot_codes: list[str], board_codes: list[str], rng: random.Random) -> str:
    """Returns 'bot'/'player'/'tie' by completing board once randomly and comparing actual hands."""
    known = set(player_codes + bot_codes + board_codes)
    full_board = _complete_board_random(board_codes, known, rng)
    return determine_card_winner(player_codes, bot_codes, full_board)


# === Monte Carlo Equity Calculations ===

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
