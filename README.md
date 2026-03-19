# AI-Poker
Objective:

Implement an AI bot that is capable of playing Texas Hold 'Em poker at a high level. The bot should make optimal moves based on a number of metrics.

Goals:

-Implement the capability to play against more than one bot

-Implement a system for bots to keep track of players previous moves

-Implement decision making algorithms for bots to make optimal decisions

To run this code ensure you have installed PokerKit (pip install PokerKit)


Sources:
https://github.com/uoftcprg/pokerkit

- **Opponent Modeling**: PokerTracker/Hold'em Manager aggression index metrics; adaptive poker theory
- **Stack Depth Strategy**: Push/fold equilibrium (Jehu Baker et al.); ICM (Independent Chip Model); standard tournament poker theory
- **Fold Equity**: Fedor Holz, Daniel Negreanu - positional aggression; bankroll management literature
- **Monte Carlo Methods**: Equilibrium Poker research; computational game theory
- **Performance Metrics**: Professional poker statistics (Upswing Poker, Run It Once)



Updates: 

(2/4 - 2/11)

Bot Logic: 
In the current version, the bot utilizes Monte Carlo Equity to drive its decision making. The bot also takes into account pot odds to make decisions.

Monte Carlo Equity algorithim runs off of the principle:  Equity = (wins + .5 * ties) / trials
The algorithim will takes the known cards into account, such as the bots hand and the board cards. From there, it recreates the remaining cards in the deck, and samples opponents hand and missing board cards 2000 times in order to calculate equity.

Improvements:
Bot has progressed from making decisions simply on hands that it possesses. Rule based heuristics have been replaced with statistics of winning probability and profitable bets/hands. Now operates on simulated statistics rather than pattern recognition.

==========================================================
(2/11 - 2/18)

Bot Logic: 
In the current version, the bot still utilizes Monte Carlo Equity in conjuction with opponent modeling. What this does is it narrows down the hands that the Monte Carlo Equity algorithim will samples based on the opponents betting pressure. Rather than sampling all possible combinations, it will sample the top X% based on how hard the opponent is betting.In this scenario, X (pressure) is found by pressure = call / (pot + call). Based on the bet relative to the pot, we will infer how strong the opponents hand is. 

Fold equity modeling has also been implemented which prevents the bot from assuming the opponent will always call. Bot will play more loose now, and will not only raise when ahead at showdown. 
The new function estimate_fold_probability(villian_top_frac, raise_to, pot) allows the b ot to calculate probability that the opponent folds based on opponent range tightness and raise size. This in conjunction with approximate expected value directs the bots decision to bluff/pressure the opponent when the expected value is positive. Overall, the bot can now raise  even with lower equity if the fold equity allows so.

Improvements:
The bot will now sample from an inferred range of top hands utilizing the betting pressure of the opponent. THe range will also tighten as a result of what street the game is currently on. The bot also no longer assumes the opponent will always call, and sees the player folding as a way of winning. With this, the bot will now raise based on the probability of the opponent folding. The bot can now be more aggressive and bluff even if the equity is not as high.

==========================================================
(2/18 - 2/25)

Bot Logic:
Major refactoring and new opponent modeling features have been added.


Opponent History Tracking:
The bot now maintains an `OpponentProfile` that tracks opponent tendencies across sessions:
- **Aggression Index (AF)**: `(bets + raises) / calls` ratio indicating opponent's aggression level
- **Fold-to-Raise Frequency**: Tracked separately for preflop and postflop by street
- **Showdown Hands**: Records all hands opponent showed down for future analysis
- These stats directly influence the bot's `estimate_villain_top_frac()` and fold probability calculations

Stack Depth Awareness:
The bot now adapts strategy based on effective stack depth (in big blinds):
- **Deep Stacks (50+ BB)**: Widens opponent's range; bot plays more hands with implied odds potential
- **Medium Stacks (15-50 BB)**: Neutral strategy; standard GTO-based decisions
- **Short Stacks (<15 BB)**: Tightens to push/fold territory; bot uses `0.40 equity threshold` for all-in decisions
- Dynamic range adjustment via `adjust_range_for_stack_depth()` function

Improvements:
Bot now adapts to both opponent tendencies AND stack dynamics. Opponent tracking enables the bot to exploit tight/loose players. Stack depth awareness prevents poor decisions in late stages (ex. calling too wide when short, not using pressure when deep). This combination significantly improves win rate in varied game situations.

Performance Metrics & Tracking:

New metrics have been added to `GameStats` for comprehensive bot performance evaluation:

**Primary Metrics:**
- **BB/100 Hands**: Big blinds won per 100 hands (industry standard poker metric)
- **ROI (Return on Investment)**: `(Profit / Buy-in) × 100%` - shows capital efficiency
- **Win Rate**: Percentage of hands won
- **Profit per Hand**: Average chips gained/lost per hand
- **Variance & Std Dev**: Measure of result stability across hands
- **95% Confidence Interval**: Statistical reliability of win rate

**Secondary Metrics:**
- Showdown win % (what fraction of hands won at showdown)
- Bluff success rate (folds induced divided by bluffs attempted)
- Correct fold % (EV-based fold accuracy)
- "Folded winner" tracking (hands that would have won if not folded)

Example Output:
```
============================================================
POKER BOT SESSION STATS
============================================================

Hands played: 250
Bot wins (actual): 142
Bot losses (actual): 103
Ties (actual): 5

PROFITABILITY METRICS
Total profit/loss: +1,250 chips
Win rate: 56.8%
BB/100 hands: +1.25
ROI: +12.5%
Profit per hand: +5.0 chips

VARIANCE METRICS
Std deviation: ±87.3 chips
95% Confidence Interval: [+2.4, +7.6] chips/hand
============================================================
```

These metrics enable objective evaluation of bot improvements over time.



