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
