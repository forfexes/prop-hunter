"""Keep multiplied same-game prices out of published tips and realised P/L."""
import math
import os
import re

def _estimated_same_game_allowed():
    # Opt-in: publish same-game builders with an ESTIMATED (multiplied) price,
    # clearly flagged on the card and invalidated in realised P/L, instead of
    # dropping them. Honest middle ground — the user still sees the combo but
    # knows the final quote must be checked at the book.
    return os.getenv("PH_ESTIMATED_SAME_GAME_BUILDERS", "0").strip().lower() in {"1","true","yes","on"}

def value(obj,key,default=None):
    return obj.get(key,default) if isinstance(obj,dict) else getattr(obj,key,default)

def features(obj):
    result=value(obj,'features',{})
    return result if isinstance(result,dict) else {}

def confirmed_ticket(obj):
    f=features(obj)
    # Whitespace or placeholder IDs are not bookmaker-issued receipts.
    return (f.get('combined_odds_observed') is True
            and bool(str(f.get('combined_quote_id') or '').strip()))

def unpriced_sgp(obj):
    if value(obj,'type') in {'single','ladder'} or confirmed_ticket(obj):
        return False
    legs=value(obj,'leg_details',[]) or []
    games=[re.sub(r'\s+',' ',str(value(x,'game','') or '').strip().lower()) for x in legs]
    # Cross-Game zuerst ausschliessen: unabhaengige Spiele, das Quoten-PRODUKT
    # ist mathematisch korrekt (keine Korrelation), also KEIN unpriced SGP —
    # auch wenn der Builder aus Einzelquoten abgeleitet wurde. Vorher hat das
    # Flag 'derived_builder'/'estimated_from_legs' unten faelschlich auch alle
    # Cross-Game-Builder invalidiert (combo_scope=cross_game wurde ignoriert).
    scope=str(value(obj,'combo_scope') or features(obj).get('combo_scope') or '').lower()
    if scope=='cross_game':
        return False
    if len(legs)>=2 and all(games) and len(set(games))==len(games):
        return False
    f=features(obj)
    if value(obj,'builder_odds_estimated_from_legs') or f.get('builder_odds_estimated_from_legs') or f.get('price_type')=='derived_builder':
        return True
    if len(legs)<2:
        return False
    # A repeated event creates an SGP component even in a mixed-match ticket.
    if not all(games) or len(set(games))==len(games):
        return False
    try:
        product=math.prod(float(value(x,'odds')) for x in legs)
        return abs(float(value(obj,'odds'))-product)<=.02
    except (TypeError,ValueError):
        return False

def calculated_combo_odds(obj):
    """Product of observed decimal leg odds; not a bookmaker combined ticket."""
    legs=value(obj,'leg_details',[]) or []
    if len(legs)<2:
        return None
    prices=[]
    for leg in legs:
        try:
            price=float(value(leg,'odds'))
        except (TypeError,ValueError,OverflowError):
            return None
        if not math.isfinite(price) or price<=1.01:
            return None
        prices.append(price)
    result=math.prod(prices)
    return result if math.isfinite(result) and result>1.01 else None



def prepare_calculated_combo(obj):
    """Attach formula analysis to Combo/Builder/Lottery without inventing EV.

    The mathematical leg-product is retained in a SEPARATE marked feature.
    Real combined ticket prices, when present, remain authoritative.
    Unknown same-game correlations never produce a fair model probability.
    """
    if str(value(obj, 'type') or '').lower() in {'single', 'longshot', 'ladder'}:
        return obj
    legs=value(obj, 'leg_details', []) or []
    if len(legs)<2:
        return obj
    from premium_joint_formula import estimate_combo
    f=features(obj)
    ticket=dict(combined_odds_observed=f.get('combined_odds_observed'),
                combined_quote_id=f.get('combined_quote_id'),
                odds=value(obj,'odds'))
    try:
        analysis=estimate_combo(
            legs,
            conditional_probabilities=f.get('conditional_probabilities'),
            joint_observations=f.get('joint_observations'),
            observed_ticket=ticket)
    except ValueError:
        return obj
    calculated=analysis['indicative_leg_product']
    f.update(formula_indicative_leg_product=calculated,
             formula_joint_probability=analysis['joint_probability'],
             formula_fair_odds=analysis['fair_model_odds'],
             formula_method=analysis['joint_probability_method'],
             formula_scope=analysis['scope'],
             formula_ev_real_ticket_only=analysis['ev_percent_using_real_ticket_only'],
             formula_individual_odds_verified=analysis['individual_prices_observed'])
    if confirmed_ticket(obj):
        return obj
    # Preserve an honest calculation preview for offline diagnostics only.
    # publishable_extra() still blocks an unbookable combined ticket.
    f.update(builder_odds_estimated_from_legs=True,
             combined_odds_observed=False, price_type='calculated_from_leg_odds',
             calculated_combined_odds=round(calculated,4))
    if isinstance(obj,dict):
        obj['features']=f
        obj['odds']=round(calculated,4)
    else:
        setattr(obj,'features',f)
        setattr(obj,'odds',round(calculated,4))
    return obj


def _published_legs(obj):
    """Check all historically used leg containers, not just leg_details.

    A combined bet mislabeled as a single or ladder must never bypass the
    global bookmaker-ticket gate.
    """
    for key in ('leg_details', 'ladder_legs', 'legs', 'picks'):
        raw = value(obj, key)
        if isinstance(raw, (list, tuple)) and raw:
            return raw
    return []


def _ladder_stages_are_individual(obj, legs):
    """One athlete, one prop market and independently observed rung prices.

    A same-player multi-stat builder is not a ladder: it requires a verified
    combined bookmaker ticket even if stored with type='ladder'.
    """
    if len(legs) < 2:
        return True
    parent = str(value(obj, 'player') or '').strip().casefold()
    players = {
        str(value(leg, 'player') or value(leg, 'player_name') or '').strip().casefold()
        for leg in legs
    }
    players.discard('')
    if len(players) > 1 or (parent and players and players != {parent}):
        return False
    if not parent and not players:
        return False

    def market_key(raw):
        # Ignore each rung's threshold while keeping the underlying prop.
        market = str(raw or '').strip().casefold()
        market = re.sub(r'\b(?:over|under)\s*\d+(?:[.,]\d+)?', '', market)
        market = re.sub(r'\s+', ' ', market).strip(' -:')
        return market

    markets = {market_key(value(leg, 'market') or value(obj, 'market')) for leg in legs}
    markets.discard('')
    if len(markets) > 1:
        return False
    directions = {
        str(value(leg, 'direction') or value(obj, 'direction') or '').strip().lower()
        for leg in legs
    }
    directions.discard('')
    if len(directions) > 1:
        return False
    for leg in legs:
        try:
            price = float(value(leg, 'odds'))
        except (TypeError, ValueError, OverflowError):
            return False
        if not math.isfinite(price) or price <= 1:
            return False
    return True


def publishable_extra(obj):
    """Never present an unverified multi-leg product as a bookmaker quote.

    Includes deliberately misclassified Single/Longshot/Ladder picks. Genuine
    one-player ladders have separate observed rung prices, not a multiplied
    combined price; all other multi-leg tickets require their actual receipt.
    """
    kind = str(value(obj, 'type') or '').strip().lower()
    legs = _published_legs(obj)
    if kind in {'single', 'longshot'}:
        return len(legs) <= 1
    if kind == 'ladder':
        return _ladder_stages_are_individual(obj, legs)
    if not confirmed_ticket(obj):
        return False
    try:
        price = float(value(obj, 'odds'))
    except (TypeError, ValueError, OverflowError):
        return False
    return math.isfinite(price) and price > 1


def quote_withdrawal_reason(ticket):
    legs=value(ticket,'leg_details',[]) or []
    games=[re.sub(r'\s+',' ',str(value(x,'game','') or '').strip().lower()) for x in legs]
    if len(games)>=2 and all(games):
        scope='Cross-Game-' if len(set(games))==len(games) else 'Same-Game-'
    else:
        scope='Kombi-'
    return scope+'Gesamtquote nur aus Einzelquoten berechnet; keine bestätigte Buchmacherquote'

def invalidate_unpriced_combo(ticket):
    if ticket.get('quote_invalidated'):
        # Migrate only our old generic reason; preserve other incident evidence
        # and original result/profit. This does not reinstate withdrawn tips.
        old='Same-Game-Gesamtquote nur aus Einzelquoten berechnet; keine bestätigte Buchmacherquote'
        if ticket.get('quote_invalidation_reason')==old and unpriced_sgp(ticket):
            reason=quote_withdrawal_reason(ticket)
            if reason!=old:
                ticket['quote_invalidation_reason']=reason
                return True
        return False
    # Publishing without a combined quote is allowed; do not retroactively
    # withdraw otherwise valid selections solely for this missing quote.
    # Previously withdrawn records are left untouched by the branch above.
    if publishable_extra(ticket) or not unpriced_sgp(ticket):
        return False
    ticket['quote_original_result']=ticket.get('result')
    ticket['quote_original_profit']=ticket.get('profit')
    ticket.update(quote_invalidated=True,settlement_invalidated=True,
        quote_invalidation_reason=quote_withdrawal_reason(ticket),
        result='withdrawn',status='withdrawn',profit=None,actual_value=None)
    return True


def publishable_extra_reason(obj):
    """Explain price-scope rejection without relaxing the safety gate."""
    if publishable_extra(obj):
        return "accepted"
    if unpriced_sgp(obj):
        return "same_game_unverified_combined_price"
    legs=value(obj,"leg_details",[]) or []
    if len(legs)<2:
        return "missing_or_single_leg_details"
    games=[re.sub(r"\s+"," ",str(value(x,"game","") or "").strip().lower()) for x in legs]
    if not all(games):
        return "missing_event_identity"
    if len(set(games))<len(games):
        return "same_game_missing_confirmed_quote"
    return "cross_game_missing_confirmed_quote"
