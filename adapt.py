import copy
from dataclasses import dataclass, field
from typing import Optional
from stats import OpponentProfile
from bot_logic import BotParams

@dataclass
class EnhancedOpponentProfile(OpponentProfile):
    hands_dealt: int = 0  # total hands opponent was dealt in
    hands_vpip: int = 0  # hands where opponent voluntarily put chips in preflop
    hands_pfr: int = 0  # hands where opponent raised preflop

    # ── Raise sizing tells (raise_to / pot) per street ──
    preflop_raise_sizes: list = field(default_factory=list)  # list of floats
    flop_raise_sizes: list = field(default_factory=list)
    turn_raise_sizes: list = field(default_factory=list)
    river_raise_sizes: list = field(default_factory=list)

    # ── Street-level aggression (bets+raises) and checks+calls ──
    flop_aggressive: int = 0
    flop_passive: int = 0
    turn_aggressive: int = 0
    turn_passive: int = 0
    river_aggressive: int = 0
    river_passive: int = 0

    # ── C-bet (continuation bet) tracking ──
    cbets_faced: int = 0  # times bot faced a bet on flop after opponent raised preflop
    cbets_folded_to: int = 0  # bot folded to those cbets (from bot side, useful context)
    opponent_cbets: int = 0  # how often opponent cbets
    opponent_cbet_opportunities: int = 0

    # ── Check-raise tracking ──
    opponent_check_raises: int = 0
    opponent_check_raise_opportunities: int = 0  # times opponent checked then faced a bet

    # ── Derived estimates (recalculated after each hand) ──
    # Start with neutral priors; will drift toward observed values
    estimated_vpip: float = 0.40
    estimated_pfr: float = 0.20
    estimated_aggression_factor: float = 1.0  # (bets+raises) / calls
    estimated_range_tightness: float = 0.40  # top_frac: 0.15=tight, 0.60=loose
    estimated_fold_to_raise: float = 0.50  # blended preflop+postflop
    estimated_cbet_freq: float = 0.55
    estimated_check_raise_freq: float = 0.08

    # ── Confidence (0→1): how much to trust estimates vs. prior ──
    # Increases with hands_dealt, caps at 1.0
    confidence: float = 0.0

    # ── Running prior weights for Bayesian-style blending ──
    _PRIOR_VPIP: float = 0.40
    _PRIOR_PFR: float = 0.20
    _PRIOR_AF: float = 1.0
    _PRIOR_RANGE: float = 0.40
    _PRIOR_FOLD_RAISE: float = 0.50
    _MIN_HANDS_ADAPT: int = 6  # don't adapt at all until this many hands
    _FULL_CONFIDENCE_HANDS: int = 60
    def update_derived_stats(self):
        n = self.hands_dealt
        if n==0:
            return
        raw_conf=max(0.0,n-self._MIN_HANDS_ADAPT)/ max(1, self._FULL_CONFIDENCE_HANDS - self._MIN_HANDS_ADAPT
                                                      )
        self.confidence=min(1.0,raw_conf)
        w = self.confidence
        #VPIP
        obs_vpip = min(1.0,self.hands_vpip/ max(1,self.hands_dealt))
        self.estimated_vpip = (1-w) * self._PRIOR_VPIP + w * obs_vpip
        #PFR
        obs_pfr = min(1.0,self.hands_pfr/ max(1,self.hands_dealt))
        self.estimated_pfr = (1-w) * self._PRIOR_PFR + w * obs_pfr

        #Aggression Factor
        total_agg = self.total_aggressive_actions
        total_pas = self.total_passive_actions
        obs_af = total_agg / max(1,total_pas)
        self.estimated_aggression_factor = (1-w) * self._PRIOR_AF + w * obs_af
        #the range of the aggression

        obs_range = min(.70, self.estimated_vpip * 1.1)
        self.estimated_range_tightness = (1-w) * self._PRIOR_RANGE + w * obs_range

        #fold to raise blended preflop + postflop
        pre_total = self.fold_to_raise_preflop + self.folds_to_raise_preflop
        pre_folds = self.folds_to_raise_preflop
        post_total = self.fold_to_raise_postflop + self.folds_to_raise_postflop
        post_folds = self.folds_to_raise_postflop
        combined_total = pre_total + post_total
        if combined_total >= 3:
            obs_fold_raise = (pre_folds + post_folds) / combined_total
            self.estimated_fold_to_raise = (1 - w) * self._PRIOR_FOLD_RAISE + w * obs_fold_raise

        # ── C-bet frequency ──
        if self.opponent_cbet_opportunities >= 3:
            obs_cbet = self.opponent_cbets / self.opponent_cbet_opportunities
            self.estimated_cbet_freq = (1 - w) * 0.55 + w * obs_cbet

        # ── Check-raise frequency ──
        if self.opponent_check_raise_opportunities >= 5:
            obs_cr = self.opponent_check_raises / self.opponent_check_raise_opportunities
            self.estimated_check_raise_freq = (1 - w) * 0.08 + w * obs_cr
    def classify_opponent(self) -> str :
        #"human-readable opponent"
        vpip = self.estimated_vpip
        af = self.estimated_aggression_factor

        if vpip < 0.22 and af > 1.5:
            return "TAG ( Tight aggressive"
        elif vpip < 0.22 and af <=1.5:
            return "Nit ( very Tight-Passive"
        elif 0.22 <= vpip < 0.40 and af > 1.5:
            return "Lag Loose Aggro"
        elif 0.22 <= vpip < 0.40 and af <= 1.5:
            return "Balanced"
        elif vpip >= 0.40 and af <= 1.0:
            return "calling station (loose- Passive"
        elif vpip >= 0.40 and af > 1.0:
            return "Maniac ( loose aggressive)"
        else:
            return "Unknown"
    def print_summary(self):
        super().print_summary()
        print("\n──────── ADAPTIVE METRICS ────────")
        print(f"Hands observed: {self.hands_dealt}")
        print(f"Confidence level: {self.confidence:.0%}")
        print(f"Opponent type: {self.classify_opponent()}")
        print(f"Est. VPIP: {self.estimated_vpip:.1%}  |  Est. PFR: {self.estimated_pfr:.1%}")
        print(f"Est. Aggression Factor: {self.estimated_aggression_factor:.2f}")
        print(f"Est. Range tightness: {self.estimated_range_tightness:.2f} (top_frac)")
        print(f"Est. Fold-to-raise: {self.estimated_fold_to_raise:.1%}")
        print(f"Est. C-bet freq: {self.estimated_cbet_freq:.1%}")
        print(f"Est. Check-raise freq: {self.estimated_check_raise_freq:.1%}")
        print("──────────────────────────────────\n")
class ActionObserver:
    def __init__(self,profile: EnhancedOpponentProfile):
        self._pfr_counted = False
        self._vpip_counted = False
        self.profile = profile
        self._raised_preflop = False
        self._checked_this_street = False
        self._last_street = -1

    def hand_start(self):
        self.profile.hands_dealt +=1
        self._raised_preflop = False
        self._checked_this_street = False
        self._pfr_counted = False
        self._vpip_counted = False
        self._last_street = -1
    def record_action(self
                      , action: str,
                      street: int,
                      call_amount: int,
                      raise_to: Optional[int],
                      pot: int,
                      facing_raise: bool,):
        p = self.profile

        if street != self._last_street:
            self._checked_this_street = False
            self._last_street = street
        is_raise = action in ("r", "a")
        is_call = action =="c" and call_amount > 0
        is_check = action =="c" and call_amount == 0
        is_fold = action == "f"
        #Global Aggression
        if is_raise:
            p.total_aggressive_actions +=1
        elif is_call:
            p.total_passive_actions +=1
        elif is_fold:
            p.total_folds +=1

        # -- fold to- raise tracking
        if facing_raise:
            if street ==0:
                p.fold_to_raise_preflop += 1
                if is_fold:
                    p.folds_to_raise_preflop += 1
            else:
                p.fold_to_raise_postflop += 1
                if is_fold:
                    p.folds_to_raise_postflop += 1

                #preflop vpip / pfr
        if street == 0:
            if is_raise or is_call:
                if not self._vpip_counted:
                    p.hands_vpip += 1
                    self._vpip_counted = True
            if is_raise:
                self._raised_preflop = True
                if not self._pfr_counted:
                    p.hands_pfr +=1
                    self._pfr_counted = True
        #Raise sizing tells
        if is_raise and raise_to is not None and pot >0:
            size = raise_to / pot
            if street == 0:
                p.preflop_raise_sizes.append(size)
            elif street == 1:
                p.flop_raise_sizes.append(size)
            elif street ==2:
                p.turn_raise_sizes.append(size)
            elif street == 3:
                p.river_raise_sizes.append(size)
                #Street level aggression
        if street == 1:
            if is_raise: p.flop_aggressive +=1
            elif is_call or is_check: p.flop_passive +=1
        elif street == 2:
            if is_raise:
                p.turn_aggressive += 1
            elif is_call or is_check:
                p.turn_passive += 1
        elif street == 3:
            if is_raise:
                p.river_aggressive += 1
            elif is_call or is_check:
                p.river_passive += 1

            # ── C-bet detection (opponent bets flop after raising preflop) ──
        if street == 1 and self._raised_preflop:
            p.opponent_cbet_opportunities += 1
            if is_raise:
                p.opponent_cbets += 1

            # ── Check-raise detection ──
        if is_check:
            self._checked_this_street = True
            p.opponent_check_raise_opportunities += 1
        elif is_raise and self._checked_this_street:
            p.opponent_check_raises += 1
            self._checked_this_street = False


    def hand_end(self):
        self.profile.update_derived_stats()
def adapt_params_to_opponent(base_params: BotParams,
                            profile: EnhancedOpponentProfile,) ->BotParams:
    if profile.confidence <= 0:
        return base_params  # no data yet, use defaults

    params = copy.copy(base_params)
    w = profile.confidence  # blend weight 0→1

    vpip = profile.estimated_vpip
    af = profile.estimated_aggression_factor
    fold_raise = profile.estimated_fold_to_raise
    range_tight = profile.estimated_range_tightness
    cr_freq = profile.estimated_check_raise_freq

    # ── Calling Station: high VPIP, low AF ──
    # They call too much → value-bet thinner, bluff less
    if vpip > 0.50 and af < 0.8:
        delta_bluff = -0.04 * w  # bluff less
        delta_vr_thresh = -0.07 * w  # raise with weaker hands (they call)
        delta_call_edge = +0.02 * w  # be selective calling their rare raises
        params.bluff_freq = max(0.01, base_params.bluff_freq + delta_bluff)
        params.value_raise_threshold = max(0.50, base_params.value_raise_threshold + delta_vr_thresh)
        params.call_edge = base_params.call_edge + delta_call_edge

    # ── Nit: low VPIP, low AF ──
    # They play only premiums → bluff more, steal pots, respect their aggression
    elif vpip < 0.22 and af < 1.5:
        delta_bluff = +0.06 * w
        delta_vr_thresh = +0.05 * w  # need stronger hand to value-raise a nit
        params.bluff_freq = min(0.18, base_params.bluff_freq + delta_bluff)
        params.value_raise_threshold = min(0.80, base_params.value_raise_threshold + delta_vr_thresh)
        params.bluff_range_threshold = max(0.08, base_params.bluff_range_threshold - 0.05 * w)

    # ── Maniac/LAG: high VPIP, high AF ──
    # They bet/raise a lot with wide range → call down more, trap, raise less as bluff
    elif af > 2.0:
        delta_call_edge = -0.04 * w  # call with less equity (they bluff a lot)
        delta_bluff = -0.03 * w  # don't get into raising wars as bluffs
        delta_cr_thresh = -0.05 * w  # check-raise more (they'll bet into us)
        params.call_edge = max(0.0, base_params.call_edge + delta_call_edge)
        params.bluff_freq = max(0.01, base_params.bluff_freq + delta_bluff)
        params.check_raise_threshold = max(0.55, base_params.check_raise_threshold + delta_cr_thresh)

    # ── TAG (general): low VPIP, high AF ──
    # Solid player: balanced approach, slight tightening
    elif vpip < 0.30 and af >= 1.5:
        delta_call_edge = +0.01 * w
        params.call_edge = base_params.call_edge + delta_call_edge

    # ── High fold-to-raise opponent ──
    # Folds often → bluff more aggressively regardless of type
    if fold_raise > 0.60:
        extra_bluff = 0.04 * w * (fold_raise - 0.60) / 0.40  # scales with how often they fold
        params.bluff_freq = min(0.20, params.bluff_freq + extra_bluff)
        params.bluff_range_threshold = max(0.08, params.bluff_range_threshold - 0.04 * w)

    # ── Low fold-to-raise → they call/re-raise raises a lot ──
    # Don't bluff, focus on value
    elif fold_raise < 0.30:
        cut_bluff = 0.03 * w
        params.bluff_freq = max(0.01, params.bluff_freq - cut_bluff)

    # ── Check-raise happy opponent ──
    # Bet smaller/less on flop to avoid bloating pot and getting check-raised
    if cr_freq > 0.15:
        # Shrink our betting size when they love to check-raise
        params.value_raise_frac = max(0.25, base_params.value_raise_frac - 0.10 * w)

    # ── Raise sizing tells: polarized large bets ──
    # If they often overbet (>1.5x pot), call them down lighter (high bluff freq)
    all_sizes = (
            profile.flop_raise_sizes +
            profile.turn_raise_sizes +
            profile.river_raise_sizes
    )
    if len(all_sizes) >= 5:
        avg_size = sum(all_sizes) / len(all_sizes)
        if avg_size > 1.5:
            # Big bet = polarized; call wider
            params.call_edge = max(0.0, params.call_edge - 0.03 * w)
        elif avg_size < 0.4:
            # Tiny bets = merged/weak; raise more
            params.value_raise_freq = min(0.97, params.value_raise_freq + 0.05 * w)

    return params
def estimate_villain_top_frac_adaptive(
        board_len: int,
        required_eq: float,
        cca: int,
        pot: int,
        profile: EnhancedOpponentProfile,
) -> float:
    from bot_logic import estimate_villain_top_frac

    heuristic = estimate_villain_top_frac(board_len, required_eq, cca,pot)

    if profile.confidence <= 0:
        return heuristic
    blended = (
    ( 1- profile.confidence) * heuristic + profile.confidence * profile.estimated_range_tightness
    )

    street_squeeze = {0:1.0, 3: 0.95, 4: 0.88, 5: 0.82}.get(board_len, 0.90)
    return max(0.10, min(0.70, blended * street_squeeze))

def get_adapted_params_and_range(
    base_params: BotParams,
    profile: EnhancedOpponentProfile,
    board_len: int,
    required_eq: float,
    cca: int,
    pot: int,
) -> tuple[BotParams, float]:
    """
    Convenience function: returns (adapted_params, villain_top_frac) together.
    Call once per decision point instead of calling both functions separately.
    """
    adapted = adapt_params_to_opponent(base_params, profile)
    top_frac = estimate_villain_top_frac_adaptive(board_len, required_eq, cca, pot, profile)
    return adapted, top_frac









