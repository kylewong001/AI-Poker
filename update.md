The first change was to understand the opponent from the bots perspective so created an actionObserver. SO that eac each action
is recorded and used in the calculation.
Next using bayesian confidence blending ot have the raw observations are blended with sensible priors using a weighted confidence as it grows with the sample size.
This accounts for lucky draws from the oppoenent and won't panic.
Then a sharper range estimeates. So the villain range estimate feeds into every monte carlo equity calculation now blends real data instead of pure heuristic we have been using so far.
