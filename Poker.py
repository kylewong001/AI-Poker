from __future__ import annotations
import random
from dataclasses import dataclass
from typing import Optional

from pokerkit import Automation, NoLimitTexasHoldem


# ----------------------------
# Helpers: display / parsing
# ----------------------------

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
            print(f"\nBoard: {_board_str(state)}")
            print(f"Your hand: {_cards_to_str(player_hole)}")
            print(_stacks_str(state))

        actor = getattr(state, "actor_index", None)
        if actor is None:
            continue

        if actor == 0:
            print("\nYour turn.")
            print("Legal:", _legal_actions_str(state))
            cmd = input("Action (fold/check/raise <amt>/a): ").strip().lower()

            if cmd == "f" and state.can_fold():
                state.fold()
                print("You fold.")
            elif cmd == "c" and state.can_check_or_call():
                state.check_or_call()
                cca = getattr(state, "checking_or_calling_amount", None)
                print("You check." if (cca is None or cca == 0) else f"You call {cca}.")
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

    bot_params = BotParams(
        raise_chance_when_possible=0.15,
        all_in_chance_when_possible=0.03,
    )

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
