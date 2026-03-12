
import random
from typing import Optional
from dataclasses import dataclass, field

from pokerkit import Automation, NoLimitTexasHoldem
import csv
from datetime import datetime,timezone
from typing import Optional, List, Dict



from concurrent.futures import ProcessPoolExecutor




# ----------------------------
# Helpers: display / parsing
# ----------------------------


HANDS_CSV = "hands.csv"
ACTIONS_CSV = "actions.csv"

_HANDS_HEADER = [
    "hand_number", "timestamp",
    "starting_stack_player", "starting_stack_bot",
    "ending_stack_player", "ending_stack_bot",
    "player_position",
    "player_hole", "bot_hole",
    "flop", "turn", "river",
    "pot_size", "winner", "showdown",
]

_ACTIONS_HEADER = [
    "hand_number", "timestamp",
    "actor",            # "player" or "bot"
    "street",           # preflop/flop/turn/river
    "board",
    "action",           # fold/check/call/raise_to/all_in
    "amount",           # optional
    "to_call",
    "pot",
    "stack_player",
    "stack_bot",
    "seq",              # action sequence number within hand
]

def _ensure_csv(path: str, header: List[str]) -> None:
    try:
        with open(path, "r", newline="", encoding="utf-8") as _:
            return
    except FileNotFoundError:
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(header)

def _street_name(state) -> str:
    names = ["preflop", "flop", "turn", "river"]
    i = getattr(state, "street_index", 0)
    return names[i] if 0 <= i < len(names) else str(i)

def _pot_amount(state) -> int:
    return int(getattr(state, "total_pot_amount", 0) or 0)

def append_hand_csv(hand_metrics) -> None:
    _ensure_csv(HANDS_CSV, _HANDS_HEADER)
    row = [
        hand_metrics.hand_number,
        hand_metrics.timestamp,
        hand_metrics.starting_stacks[0], hand_metrics.starting_stacks[1],
        hand_metrics.ending_stacks[0], hand_metrics.ending_stacks[1],
        hand_metrics.player_position,
        hand_metrics.player_hole, hand_metrics.bot_hole,
        hand_metrics.flop or "", hand_metrics.turn or "", hand_metrics.river or "",
        hand_metrics.pot_size,
        hand_metrics.winner or "",
        int(bool(hand_metrics.showdown)),
    ]
    with open(HANDS_CSV, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)

def append_action_csv(
    *,
    hand_number: int,
    ts: str,
    actor: str,
    street: str,
    board: str,
    action: str,
    amount: Optional[int],
    to_call: int,
    pot: int,
    stack_player: int,
    stack_bot: int,
    seq: int,
) -> None:
    _ensure_csv(ACTIONS_CSV, _ACTIONS_HEADER)
    row = [
        hand_number, ts, actor, street, board, action,
        "" if amount is None else int(amount),
        int(to_call), int(pot),
        int(stack_player), int(stack_bot),
        int(seq),
    ]
    with open(ACTIONS_CSV, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)


def _cards_to_str(cards) -> str:
    if cards is None:
        return ""
    if isinstance(cards, str):
        return cards
    try:
        return " ".join(map(str, cards))
    except TypeError:
        return str(cards)


def _board_str(state) -> str:
    # For most hold'em states, state.board_cards holds community cards
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



# Bot policy (replace later)

@dataclass
class BotParams:
    #Passive by default, with occasional aggression.
    raise_chance_when_possible: float = 0.15
    all_in_chance_when_possible: float = 0.03

@dataclass
class HandMetrics:
    hand_number: int
    timestamp: str

    starting_stacks: tuple[int, int]
    player_position: str  # "SB" or "BB"

    player_hole: str
    bot_hole: str

    flop: Optional[str] = None
    turn: Optional[str] = None
    river: Optional[str] = None

    ending_stacks: tuple[int, int] = (0, 0)
    pot_size: int = 0
    winner: Optional[str] = None  # "player", "bot", "split"
    showdown: bool = False



def choose_bot_action(state, params: BotParams) -> tuple[str, Optional[int]]:
    """
    Returns ("fold"|"check"|"raise"|"all in", amount_if_any).
    Replace this entire function with Monte Carlo / CFR / etc.
    """
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

    if can_raise and random.random() < params.all_in_chance_when_possible:
        return ("a", None)

    if can_raise and random.random() < params.raise_chance_when_possible:
        # Simple sizing: min-raise / min-bet
        return ("r", int(min_to))

    if can_call:
        return ("c", None)

    if can_fold:
        return ("f", None)

    # Fallback (shouldn't happen)
    return ("c", None)


# ----------------------------
# One hand loop
# ----------------------------

def play_one_hand(
    stacks: tuple[int, int],
    *,
    hand_number: int,
    player_position: str,
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



    #Deal and remember hole cards (2 each for hold'em) ---

    def log(actor_label: str, action: str, amount: Optional[int] = None, *, to_call: Optional[int] = None):
        nonlocal seq
        seq += 1
        append_action_csv(
            hand_number=hand_metrics.hand_number,
            ts=datetime.now(timezone.utc).isoformat(),
            actor=actor_label,  # "player" or "bot"
            street=_street_name(state),
            board=_board_str(state),
            action=action,  # fold/check/call/raise_to/all_in
            amount=amount,
            to_call=int(to_call or 0),
            pot=_pot_amount(state),
            stack_player=int(state.stacks[0]),
            stack_bot=int(state.stacks[1]),
            seq=seq,
        )

    while any(len(h) < 2 for h in state.hole_cards):
        state.deal_hole()

    player_hole = tuple(state.hole_cards[0])
    bot_hole = tuple(state.hole_cards[1])


    hand_metrics = HandMetrics(
        hand_number=hand_number,
        timestamp=datetime.utcnow().isoformat(),
        starting_stacks=(int(stacks[0]), int(stacks[1])),
        player_position=player_position,
        player_hole=_cards_to_str(player_hole),
        bot_hole=_cards_to_str(bot_hole),
        ending_stacks=(0, 0),
    )
    seq = 0
    any_folded = False

    print("\n" + "=" * 60)
    print("New hand!")
    last_street = None

    while state.status:
        if state.street_index != last_street:
            last_street = state.street_index
            print(f"\nBoard: {_board_str(state)}")
            print(f"Your hand: {_cards_to_str(player_hole)}")
            print(_stacks_str(state))

        actor = getattr(state, "actor_index", None)
        if actor is None:
            continue
        board_cards = list(getattr(state, "board_cards", []) or [])
        if len(board_cards) >= 3 and hand_metrics.flop is None:
            hand_metrics.flop = " ".join(map(str, board_cards[:3]))
        if len(board_cards) >= 4 and hand_metrics.turn is None:
            hand_metrics.turn = str(board_cards[3])
        if len(board_cards) >= 5 and hand_metrics.river is None:
            hand_metrics.river = str(board_cards[4])

        if actor == 0:
            print("\nYour turn.")
            print("Legal:", _legal_actions_str(state))
            cmd = input("Action (f/c/r <amt>/a): ").strip().lower()

            if cmd == "f" and state.can_fold():
                to_call = int(getattr(state, "checking_or_calling_amount", 0) or 0)
                any_folded = True
                log("player", "fold", None, to_call=to_call)
                state.fold()
                print("You fold.")

            elif cmd == "c" and state.can_check_or_call():
                to_call = int(getattr(state, "checking_or_calling_amount", 0) or 0)
                log("player", "check" if to_call == 0 else "call", None if to_call == 0 else to_call, to_call=to_call)
                state.check_or_call()
                print("You check." if to_call == 0 else f"You call {to_call}.")

            elif cmd.startswith("r"):
                parts = cmd.split()
                if len(parts) != 2:
                    print("Use: r <amount_to_raise_to>")
                    continue
                try:
                    raise_to_amt = int(parts[1])
                except ValueError:
                    print("Raise amount must be an integer.")
                    continue

                if state.can_complete_bet_or_raise_to(raise_to_amt):
                    to_call = int(getattr(state, "checking_or_calling_amount", 0) or 0)
                    log("player", "raise_to", raise_to_amt, to_call=to_call)
                    state.complete_bet_or_raise_to(raise_to_amt)
                    print(f"You raise to {raise_to_amt}.")
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
                    to_call = int(getattr(state, "checking_or_calling_amount", 0) or 0)
                    log("player", "all_in", int(max_to), to_call=to_call)
                    state.complete_bet_or_raise_to(max_to)
                    print(f"You go all-in to {max_to}.")
                else:
                    print("All-in not legal here.")
            else:
                print("Invalid action. Try again.")
                continue

        else:
            act, amt = choose_bot_action(state, bot_params)

            if act == "f" and state.can_fold():

                to_call = int(getattr(state, "checking_or_calling_amount", 0) or 0)
                any_folded = True
                log("bot", "fold", None, to_call=to_call)
                state.fold()
                print("\nBot folds.")

            elif act == "c" and state.can_check_or_call():
                to_call = int(getattr(state, "checking_or_calling_amount", 0) or 0)
                log("bot", "check" if to_call == 0 else "call", None if to_call == 0 else to_call, to_call=to_call)
                state.check_or_call()
                print("\nBot checks." if to_call == 0 else f"\nBot calls {to_call}.")

            elif act == "a":
                max_to = getattr(state, "max_completion_betting_or_raising_to_amount", None)
                if max_to is not None and state.can_complete_bet_or_raise_to(max_to):
                    to_call = int(getattr(state, "checking_or_calling_amount", 0) or 0)
                    log("bot", "all_in", int(max_to), to_call=to_call)
                    state.complete_bet_or_raise_to(max_to)
                    print(f"\nBot goes all-in to {max_to}.")
                else:
                    # fallback
                    to_call = int(getattr(state, "checking_or_calling_amount", 0) or 0)
                    log("bot", "check" if to_call == 0 else "call", None if to_call == 0 else to_call, to_call=to_call)
                    state.check_or_call()
                    print("\nBot calls (fallback).")

            elif act == "r" and amt is not None and state.can_complete_bet_or_raise_to(amt):
                to_call = int(getattr(state, "checking_or_calling_amount", 0) or 0)
                log("bot", "raise_to", int(amt), to_call=to_call)
                state.complete_bet_or_raise_to(amt)
                print(f"\nBot raises to {amt}.")

            else:
                if state.can_check_or_call():
                    to_call = int(getattr(state, "checking_or_calling_amount", 0) or 0)
                    log("bot", "check" if to_call == 0 else "call", None if to_call == 0 else to_call, to_call=to_call)
                    state.check_or_call()
                    print("\nBot calls/checks (fallback).")
                else:
                    to_call = int(getattr(state, "checking_or_calling_amount", 0) or 0)
                    any_folded = True
                    log("bot", "fold", None, to_call=to_call)
                    state.fold()
                    print("\nBot folds (fallback).")
    # --- hand is over: finalize metrics + write hands.csv ---
    hand_metrics.ending_stacks = (int(state.stacks[0]), int(state.stacks[1]))
    hand_metrics.pot_size = _pot_amount(state)

    delta = hand_metrics.ending_stacks[0] - hand_metrics.starting_stacks[0]
    if delta > 0:
        hand_metrics.winner = "player"
    elif delta < 0:
        hand_metrics.winner = "bot"
    else:
        hand_metrics.winner = "split"

    hand_metrics.showdown = not any_folded

    append_hand_csv(hand_metrics)

    print("\nHand over.")
    print(f"Final board: {_board_str(state)}")
    print(f"Your hole: {_cards_to_str(player_hole)}")
    print(f"Bot hole:  {_cards_to_str(bot_hole)}")
    print(_stacks_str(state))

    return (int(state.stacks[0]), int(state.stacks[1]))



def main() -> None:
    print("PokerKit: Heads-Up No Limit Hold 'Em — You vs Bot")

    stacks = (10000, 10000)
    sb, bb, min_bet = 50, 100, 100
    hand_no = 1
    player_is_sb = True

    bot_params = BotParams(
        raise_chance_when_possible=0.15,
        all_in_chance_when_possible=0.03,
    )

    while True:
        stacks = play_one_hand(
            stacks,
            hand_number=hand_no,
            player_position="SB" if player_is_sb else "BB",
            sb=sb,
            bb=bb,
            min_bet=min_bet, bot_params=bot_params)
        hand_no += 1
        player_is_sb = not player_is_sb

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
