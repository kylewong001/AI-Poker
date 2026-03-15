# AI-Poker
CSC 480 - Artificial Intelligence | Cal Poly San Luis Obispo

Instructor: Rodrigo Canaan

Objective:

Implement an AI bot that is capable of playing Texas Hold 'Em poker at a high level. The bot should make optimal moves based on a number of metrics.

Goals:

-Implement the capability to play against more than one bot

-Implement a system for bots to keep track of players previous moves

-Implement decision making algorithms for bots to make optimal decisions

Installation:

Requires Python 3.11+. Install the one dependency:
```
pip install pokerkit
```

Running the Project:

**Play interactively (you vs. the adaptive bot):**
```
python Poker.py
```
Starts a heads-up No Limit Texas Hold 'Em session with 10,000 chip stacks, 50/100 blinds. The bot adapts its strategy in real time based on your play.

**Run the adaptive vs. static benchmark:**
```
python run_benchmark_suite.py
```
Simulates 2000 hands per opponent type (tight, balanced, loose, aggressive) and compares the adaptive bot against a non-adaptive baseline. Results are printed to the console and saved to a timestamped file (e.g. `benchmark_results_20260314_120000.txt`).

To change the number of hands or checkpoint interval, edit the parameters in `run_benchmark_suite.py`:
```python
run_adaptive_comparison(
    num_hands=2000,        # hands per opponent type
    checkpoint_interval=200,  # how often to record BB/100 snapshots
    verbose=False,         # set True for hand-by-hand output
)
```


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

==========================================================
(3/4 - 3/14)

Bot Logic:
Adaptive opponent modeling has been implemented, allowing the bot to update its strategy in real time based on observed opponent behavior across hands.

Opponent Profiling:
The bot now builds an `EnhancedOpponentProfile` that tracks detailed opponent tendencies each hand:
- **VPIP / PFR**: Voluntarily put in preflop / preflop raise frequency, tracking how often the opponent enters pots and raises
- **Aggression Factor (AF)**: `(bets + raises) / calls` computed separately per street (flop, turn, river)
- **Fold-to-Raise**: Tracked independently for preflop and postflop, revealing whether an opponent folds to pressure before or after the board is dealt
- **C-bet Frequency**: How often the opponent continuation bets the flop after raising preflop
- **Check-Raise Frequency**: How often the opponent check-raises, used to shrink bet sizing to avoid inflating pots

Bayesian Confidence Blending:
All estimates use a Bayesian-style prior blend that ramps from neutral priors toward observed values as sample size grows:
- Confidence starts at 0 and reaches 1.0 after 200 observed hands, preventing early noisy data from locking in unreliable estimates
- Each derived stat (VPIP, PFR, AF, fold rates) is blended as: `(1 - confidence) * prior + confidence * observed`

Opponent Classification:
Each hand, the bot classifies the opponent into one of four types using postflop fold-to-raise as the primary discriminator:
- **TAG (Tight Aggressive)**: Postflop FTR > 90% — plays few hands but raises aggressively
- **Balanced**: Postflop FTR 25–90% — standard mix of calls and folds
- **Maniac (Loose Aggressive)**: Postflop FTR < 25%, AF > 2 — wide range, rarely folds
- **Calling Station**: Postflop FTR < 25%, AF ≤ 2 — wide range, passively calls everything

Parameter Adaptation:
Based on the classification, the bot adjusts its `BotParams` each hand:
- **vs TAG**: Increases bluff frequency and lowers bluff range threshold to exploit their high fold rate
- **vs Maniac**: Reduces bluffing (they rarely fold), gates thin value bets and check-raises behind a minimum fold rate to avoid inflating pots with no fold equity
- **vs Calling Station**: Maximizes thin value betting, eliminates bluffing entirely
- **vs Balanced**: Scales bluff frequency proportionally to observed postflop fold rate

Bluff EV Correction:
The fold probability used in bluff EV calculations now blends the model estimate with the opponent's observed postflop fold-to-raise rate. This corrects a systematic underestimation where the model predicted ~12% fold probability for tight players whose actual fold rate was ~97%, causing the EV filter to block profitable bluffs.

Improvements:
The bot now exploits opponent tendencies in real time rather than using fixed parameters for every opponent type. Against a tight folder it bluffs more aggressively; against a calling station it value bets thinner and never bluffs. Benchmarks show the adaptive bot consistently outperforms the static baseline against tight and loose opponents across 2000+ hand samples.

Benchmark Suite:
A full adaptive vs. non-adaptive benchmark suite (`run_benchmark_suite.py`) runs both versions head-to-head across all four opponent types, producing a learning curve at configurable checkpoints and a final BB/100 comparison table. Results are saved to a timestamped file for tracking progress across iterations.

