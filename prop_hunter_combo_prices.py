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
    return f.get('combined_odds_observed') is True and bool(f.get('combined_quote_id'))

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

def publishable_extra(obj):
    if value(obj,'type') in {'single','ladder'}:
        return True
    if confirmed_ticket(obj):
        return True
    if unpriced_sgp(obj):
        # Opt-in: let an ESTIMATED same-game builder through if it is explicitly
        # flagged as such. The card shows the "quote estimated" warning and the
        # settlement pipeline still invalidates its P/L, so nothing is misrepresented.
        if _estimated_same_game_allowed():
            f=features(obj)
            if value(obj,'builder_odds_estimated_from_legs') or f.get('builder_odds_estimated_from_legs'):
                return True
        return False
    legs=value(obj,'leg_details',[]) or []
    games=[re.sub(r'\s+',' ',str(value(x,'game','') or '').strip().lower()) for x in legs]
    return len(games)>=2 and all(games) and len(set(games))==len(games)

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
    if not unpriced_sgp(ticket):
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
    games=[re.sub(r"\\s+"," ",str(value(x,"game","") or "").strip().lower()) for x in legs]
    if not all(games):
        return "missing_event_identity"
    if len(set(games))<len(games):
        return "same_game_missing_confirmed_quote"
    return "unknown_price_scope"
