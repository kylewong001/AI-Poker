import random
from dataclasses import dataclass
from typing import Optional
from helpers import (
    estimate_equity_vs_range,
    _board_codes,
)


@dataclass
class BotParams:
    # Core difficulty knobs
    call_edge: float = 0.02          # requires equity >= pot_odds + call_edge to call
    value_raise_freq: float = 0.90   # when strong, how often to raise instead of call/check

    # Style knobs
    bluff_freq: float = 0.05         # how often to bluff/semi-bluff when not +EV (positive equity value)

    # Sizing knobs
    value_raise_frac: float = 0.45   # raise-to size as fraction of stack (clamped to min/max)
    bluff_raise_frac: float = 0.30   # smaller than value sizing

    # All-in behavior
    jam_equity: float = 0.82         # if equity >= this, bot may jam
    jam_freq: float = 0.10           # chance to jam when jam_equity met (and jam is legal)

    # Monte Carlo trials
    trials_preflop: int = 1200
    trials_flop: int = 2000
    trials_postflop: int = 3000

    # Decision thresholds
    check_raise_threshold: float = 0.62  # raise when checking & strong
    value_raise_threshold: float = 0.70  # min equity for value raising
    value_raise_edge: float = 0.12       # equity cushion over pot odds for value
    bluff_range_threshold: float = 0.18  # min villain_top_frac to bluff into

    # Stack depth thresholds (in big blinds)
    deep_stack_bb: int = 50          # >= 50 BB: deep stack strategy
    medium_stack_bb: int = 15        # 15-50 BB: medium stack strategy
    short_stack_bb: int = 15         # < 15 BB: push/fold territory

    # Stack-depth adjustments
    deep_stack_range_frac: float = 0.55   # play wider in deep stacks
    medium_stack_range_frac: float = 0.35 # tighten up medium stacks
    short_stack_range_frac: float = 0.15  # very tight, push/fold only


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


def get_effective_stack_bb(state, actor_index: int, bb: int = 100) -> float:
    """
    Calculate effective stack (smallest stack at the table) in big blinds.
    """
    stacks = state.stacks
    effective_stack = min(int(stacks[0]), int(stacks[1]))
    return effective_stack / bb


def adjust_range_for_stack_depth(villain_top_frac: float, stack_bb: float, params: BotParams) -> float:
    """
    Adjust villain's estimated range based on stack depth.
    Deep stacks: opponent plays wider
    Short stacks: opponent plays tighter (push/fold)
    """
    if stack_bb >= params.deep_stack_bb:
        # Deep stack: widen opponent's range
        adjustment = 1.0 + (0.15 * (stack_bb / params.deep_stack_bb - 1))  # up to 1.15x wider
        return min(1.0, villain_top_frac * adjustment)
    elif stack_bb <= params.short_stack_bb:
        # Short stack: tighten (opponent only plays strong hands)
        return max(0.08, villain_top_frac * 0.6)
    else:
        # Medium stack: neutral
        return villain_top_frac


def choose_bot_action(state, params: BotParams) -> tuple[str, Optional[int]]:
    """
    Bot acts off of monte carlo equity in conjunction with opponent modeling
    which narrows the range of cards that the algorithm will simulate when calculating equity.
    Rather than sampling uniformly from unseen cards, the algorithm will sample from the top X percentage of hands,
    where X fluctuates based on call amount in relation to pot, and the current street
    (more pressure == stronger villain -> equity drops).

    Fold equity allows bot to now raise even if equity (chances of winning with current hand) are weaker than desired.
    Stack depth adjusts strategy: deep stacks play wider, short stacks tighter (push/fold).

    """
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
    
    # --- Stack depth awareness ---
    stack_bb = get_effective_stack_bb(state, actor, bb=100)

    # --- Decide how tight villain range is based on pressure ---
    required_eq = cca / (pot + cca) if (pot + cca) > 0 else 1.0
    villain_top_frac = estimate_villain_top_frac(board_len, required_eq, cca, pot)
    
    # Adjust range based on stack depth
    villain_top_frac = adjust_range_for_stack_depth(villain_top_frac, stack_bb, params)

    # --- Monte Carlo equity vs inferred range ---
    if board_len == 0:
        trials = params.trials_preflop
    elif board_len == 3:
        trials = params.trials_flop
    else:
        trials = params.trials_postflop

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
        if can_raise and eq >= params.check_raise_threshold and random.random() < params.value_raise_freq:
            amt = big_raise_to(params.value_raise_frac) or small_raise_to()
            if amt is not None:
                return ("r", amt)
        return ("c", None)

    # Value raise when clearly strong
    if can_raise and eq >= max(params.value_raise_threshold, required_eq + params.value_raise_edge):
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
        if villain_top_frac >= params.bluff_range_threshold:  # looser than threshold -> can fold more
            amt = big_raise_to(params.bluff_raise_frac) or small_raise_to()
            if amt is not None:
                fold_p = estimate_fold_probability(villain_top_frac, raise_to=amt, pot=pot)
                # approximate invest as raise_to amount (good enough for decision ranking)
                invest = amt
                # EV(raise) compared to EV(fold)=0 baseline
                evr = ev_of_raise(eq_when_called=eq, fold_p=fold_p, pot=pot, invest=invest)
                if evr > 0:
                    return ("r", amt)

    # --- Short stack push/fold logic ---
    if stack_bb <= params.short_stack_bb and cca > 0:
        # Facing aggression with short stack: push with decent equity or fold
        if eq >= 0.40:  # push if reasonable equity
            if can_raise and max_to is not None and state.can_complete_bet_or_raise_to(int(max_to)):
                return ("a", None)
        elif can_fold:
            return ("f", None)

    # Otherwise fold if facing a bet
    if can_fold:
        return ("f", None)

    return ("c", None) if can_call else ("f", None)
