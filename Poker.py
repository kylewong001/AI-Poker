from __future__ import annotations
import random
from typing import Optional
from pokerkit import Automation, NoLimitTexasHoldem

# Import from our modules
from stats import GameStats, FoldInfo, OpponentProfile
from bot_logic import BotParams, choose_bot_action
from helpers import (
    _board_one_line,
    _cards_to_str,
    _stacks_str,
    _legal_actions_str,
    _board_codes,
    _hole_codes_for_player,
    _get_call_amount,
    determine_card_winner,
    estimate_equity_vs_known_hand,
    winner_on_one_random_runout,
)


def record_opponent_aggressive_action(opponent_profile: OpponentProfile, street_num: int):
    """Record that opponent made an aggressive action (bet/raise)."""
    opponent_profile.total_aggressive_actions += 1


def record_opponent_passive_action(opponent_profile: OpponentProfile):
    """Record that opponent made a passive action (call)."""
    opponent_profile.total_passive_actions += 1


def record_opponent_fold_to_raise(opponent_profile: OpponentProfile, street_num: int):
    """Record that opponent folded to a raise."""
    opponent_profile.total_folds += 1
    if street_num == 0:
        opponent_profile.folds_to_raise_preflop += 1
        opponent_profile.fold_to_raise_preflop += 1
    else:
        opponent_profile.folds_to_raise_postflop += 1
        opponent_profile.fold_to_raise_postflop += 1


def record_showdown_hand(opponent_profile: OpponentProfile, hole_codes: list, result: str):
    """Record opponent's hand at showdown."""
    opponent_profile.showdown_hands.append((hole_codes, result))
    opponent_profile.hands_seen_at_showdown += 1


def play_one_hand(
    stacks: tuple[int, int],
    *,
    sb: int = 50,
    bb: int = 100,
    min_bet: int = 100,
    bot_params: BotParams = BotParams(),
    opponent_profile: OpponentProfile | None = None,
    action_observer=None,
):

    if opponent_profile is None:
        opponent_profile = OpponentProfile()

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

    fold_info = FoldInfo(folded=False, board_codes=[], pot=0, call_amount=0)

    print("\n" + "=" * 60)
    print("New hand!")
    last_street = None

    while state.status:   
        if state.street_index != last_street:
            last_street = state.street_index
            print("\n" + _board_one_line(state))
            print(f"Your hand: {_cards_to_str(player_hole)}")
            print(_stacks_str(state))


        actor = getattr(state,"actor_index",None)
        if actor is None:
            continue

        cca = _get_call_amount(state)
        pot = int(getattr(state,"total_pot_amount",0) or 0)

        if actor == 0:
            print("\n=============================================================================")
            print("\nYour turn.")
            print("Legal:", _legal_actions_str(state))
            cmd = input("Action (fold/check/raise <amt>/a): ").strip().lower()
            if action_observer is not None:
                raise_to = None
                if cmd.startswith("r"):
                    parts = cmd.split()
                    if len(parts) == 2:
                        try:
                            raise_to = int(parts[1])
                        except ValueError:
                            pass
                action_observer.record_action(
                    action=cmd[0] if cmd else "c",
                    street=state.street_index or 0,
                    call_amount=cca,
                    raise_to=raise_to,
                    pot=pot,
                    facing_raise=cca > 0,
                )
            if cmd == "f" and state.can_fold():
                state.fold()
                print("You fold.")
            elif cmd == "c" and state.can_check_or_call():
                cca = _get_call_amount(state)
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
                bot_fold_pot = int(getattr(state, "total_pot_amount", 0) or 0)
                bot_fold_call = _get_call_amount(state)
                bot_fold_board_codes = _board_codes(state)
                
                state.fold()
                print("\nBot folds.")
                
                fold_info = FoldInfo(
                    folded=True,
                    board_codes=bot_fold_board_codes,
                    pot=bot_fold_pot,
                    call_amount=bot_fold_call,
                )

            elif act == "c" and state.can_check_or_call():
                cca = _get_call_amount(state)
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

    return ending_stacks, bot_delta, board_codes_end, player_codes, bot_codes, fold_info

def main() -> None:

    from adapt import EnhancedOpponentProfile, ActionObserver, adapt_params_to_opponent
    print("PokerKit: Heads-Up No Limit Hold 'Em — You vs Bot")

    stacks = (10000, 10000)
    sb, bb, min_bet = 50, 100, 100

    base_bot_params = BotParams()
    stats = GameStats()
    opponent_profile =EnhancedOpponentProfile()

    while True:
        # ── 1. Generate adapted params from what we've learned so far ──────
        adapted_params = adapt_params_to_opponent(base_bot_params, opponent_profile)

        # ── 2. Create a fresh observer for this hand ───────────────────────
        observer = ActionObserver(opponent_profile)
        observer.hand_start()

        # ── 3. Play the hand ───────────────────────────────────────────────
        (stacks, bot_delta, board_codes,
         player_codes, bot_codes, fold_info) = play_one_hand(
            stacks,
            sb=sb, bb=bb, min_bet=min_bet,
            bot_params=adapted_params,  # ← adapted, not base
            opponent_profile=opponent_profile,
            action_observer=observer,  # ← observer records opponent actions
        )

        # ── 4. Close out observer (triggers derived stat update) ───────────
        observer.hand_end()

        # ── 5. Update game stats (unchanged from your original) ────────────
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
                record_showdown_hand(opponent_profile, player_codes, "lost")
            elif should == "player":
                stats.bot_should_lose += 1
                record_showdown_hand(opponent_profile, player_codes, "won")
            else:
                stats.should_tie += 1
                record_showdown_hand(opponent_profile, player_codes, "tie")

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
                trials=2500,
            )
            if eq_vs_actual < required_eq + adapted_params.call_edge:
                stats.bot_correct_folds_ev += 1

            rng = random.Random(stats.hands * 99991 + 17)
            runout_winner = winner_on_one_random_runout(
                player_codes, bot_codes, fold_info.board_codes, rng
            )
            if runout_winner == "bot":
                stats.bot_folded_winner_runout += 1

        # ── 6. Print summaries ─────────────────────────────────────────────
        stats.print_summary()
        opponent_profile.print_summary()  # now shows adaptive metrics too

        # ── 7. Early-exit conditions ───────────────────────────────────────
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
