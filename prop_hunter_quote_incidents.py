"""Conservative repairs for quotes verified against retained source snapshots.

2026-10-29 FanDuel: period prices were labelled as full-game NHL props.
Match exact player, game, date, book, line and rounded issued price only.
"""
import re

# Original source_event_id 36230599 / 36230600, retained FanDuel snapshots.
_EVIDENCE = (
    ('Charlie Coyle', 'Columbus Blue Jackets @ Carolina Hurricanes', 1.5, 8.10, '2nd Period Player 2+ Shots on Goal'),
    ('Charlie Coyle', 'Columbus Blue Jackets @ Carolina Hurricanes', 1.5, 8.90, '1st Period 2+ Shots on Goal'),
    ('Nikita Kucherov', 'Winnipeg Jets @ Tampa Bay Lightning', .5, 1.53, '1st Period 1+ Shots on Goal'),
    ('Nikita Kucherov', 'Winnipeg Jets @ Tampa Bay Lightning', 2.5, 9.30, '1st Period 3+ Shots on Goal'),
    ('Jack Hughes', 'New Jersey Devils @ Colorado Avalanche', .5, 3.75, '1st Period 1+ Points'),
    ('Nathan MacKinnon', 'New Jersey Devils @ Colorado Avalanche', .5, 1.38, '1st Period 1+ Shots on Goal'),
    ('Nazem Kadri', 'New Jersey Devils @ Colorado Avalanche', .5, 5.15, '1st Period 1+ Points'),
    ('Matthew Knies', 'Columbus Blue Jackets @ Carolina Hurricanes', 1.5, 8.90, '1st Period 2+ Shots on Goal'),
)

def evidence_for(ticket, day):
    incident_day = str(day)[:10]
    if incident_day not in {'2026-10-28', '2026-10-29'}:
        return []
    details = ticket.get('leg_details') or [ticket]
    found = []
    for leg in details:
        if not isinstance(leg, dict):
            continue
        if str(leg.get('bookmaker') or ticket.get('bookmaker') or '').lower() != 'fanduel':
            continue
        market = re.sub(r'[^a-z0-9]+', ' ', str(leg.get('market') or '').lower()).strip()
        if str(leg.get('direction') or ticket.get('direction') or '').lower() != 'over':
            continue
        try:
            line = float(leg.get('point') if leg.get('point') is not None else leg.get('line'))
            price = round(float(leg.get('odds')), 2)
        except (TypeError, ValueError):
            continue
        for player, game, threshold, odds, original in _EVIDENCE:
            # Overnight NJD/COL quotes were also persisted under the preceding
            # sent_date. Both dates refer to the same quoted October 29 event.
            if incident_day == '2026-10-28' and game != 'New Jersey Devils @ Colorado Avalanche':
                continue
            expected_market = 'shots on goal' if 'Shots on Goal' in original else 'points'
            if expected_market not in market:
                continue
            if leg.get('player') == player and (leg.get('game') or ticket.get('game')) == game and line == threshold and price == odds:
                found.append(dict(player=player, game=game, line=line, odds=odds, original_market=original))
    return found

def invalidate(ticket, day):
    proof = evidence_for(ticket, day)
    if not proof or ticket.get('quote_invalidated'):
        return False
    ticket['quote_original_result'] = ticket.get('result')
    ticket.update(quote_invalidated=True, settlement_invalidated=True,
                  quote_invalidation_reason='Drittelquote wurde als Gesamtspielquote ausgegeben',
                  quote_invalidation_evidence=proof, result='withdrawn', status='withdrawn',
                  profit=None, actual_value=None)
    return True

if __name__ == '__main__':
    from prophunter_results import _load_history, _save_history, _sync_pick_table
    history = _load_history()
    changed = 0
    for entry in history:
        for ticket in (entry.get('picks') or []) + (entry.get('kombis') or []):
            if invalidate(ticket, entry.get('date')):
                changed += 1
            if ticket.get('quote_invalidated'):
                _sync_pick_table(dict(ticket, date=entry.get('date')))
    if changed:
        _save_history(history)
    print(f'Verified quote withdrawals before settlement={changed}')
