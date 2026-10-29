from copy import deepcopy
from prop_hunter_quote_incidents import invalidate
from prophunter_results import _decorate_card, _performance_rows

def ticket():
    return dict(player='Charlie Coyle', market='Shots On Goal Over 1.5', point=1.5,
                direction='over', odds=8.9, bookmaker='fanduel',
                game='Columbus Blue Jackets @ Carolina Hurricanes', result='win',profit=.395,
                dedup_key='test')
p=ticket()
assert invalidate(p,'2026-10-29')
assert p['result']=='withdrawn' and p['profit'] is None
assert not invalidate(p,'2026-10-29')
assert not _performance_rows([{'picks':[p]}])
card=dict(text='Test\n📈 Prob 6.9% · EV +473.2%\n🏁 Auswertung: offen\n@prophunter',pick_keys=['test'])
text=_decorate_card(card,[p],[])
assert 'TIPP ZURÜCKGEZOGEN' in text and '473.2%' not in text and 'offen' not in text
for key,value in [('player','Other Player'),('game','Other Game'),('odds',1.96),('point',2.5),('bookmaker','bet365'),('direction','under')]:
    other=ticket();other[key]=value
    assert not invalidate(other,'2026-10-29'),(key,value)
assert not invalidate(ticket(),'2026-10-30')
c=dict(type='big',leg_details=[ticket()],result='pending')
assert invalidate(c,'2026-10-29')
# Retained production incident: same proven quote must catch single, ladder,
# cross-game and SGP without reclassifying unrelated tickets.
import json
history=json.load(open('picks_history.json'))
count=0
for entry in history:
    for pick in (entry.get('picks') or [])+(entry.get('kombis') or []):
        count+=invalidate(deepcopy(pick),entry.get('date'))
print(f'QUOTE INCIDENT TEST OK; retained affected tickets={count}')

from prop_hunter_learning_update import unique_results
bad=ticket();bad["date"]="2026-10-29"
assert not unique_results([dict(pick_id="bad",result="win",pick_raw=bad)])
good=dict(bad,odds=1.96)
assert len(unique_results([dict(pick_id="good",result="win",pick_raw=good)]))==1
