"""Original photo edits, legacy migration, result rendering and retry regression."""
import io,json,os
from types import SimpleNamespace as N
from unittest.mock import patch
from PIL import Image
import prop_hunter_image_cards as cards
import prophunter_results as results

pick=N(type='betbuilder',features={'combined_odds_observed':True,'combined_quote_id':'fixture-bookmaker-ticket'},game='Lakers @ Celtics',sport='NBA',odds=3.4,leg_details=[{'player':'Player A','market':'Points','point':25.5,'direction':'over','odds':1.8},{'player':'Player B','market':'Rebounds','point':6.5,'direction':'under','odds':1.9}])
with patch.object(cards,'player_photo',return_value=None),patch.object(cards,'team_logo',return_value=None):
 # Unverified builder total must never render or reach Telegram.
 unverified=N(**dict(vars(pick),features={}))
 assert cards.build_for_pick(unverified) is None
 data=cards.snapshot(pick)
 # Previously published legacy photos may lack provenance for their historical
 # combined quote; re-render their official result but NEVER invent/reverify it.
 legacy=dict(data,features={})
 with patch.object(cards,'render',return_value=b'LEGACY') as draw:
  assert cards.settled_image(legacy,'🏁 Auswertung: 1✅ 0❌ · +0.12u')==b'LEGACY'
  assert 'GESAMTQUOTE UNBESTÄTIGT' in draw.call_args.args[6]
  assert '@3.40' not in draw.call_args.args[6]
 # The exact same unverified combo must still fail the NEW production photo gate.
 assert cards.build_for_pick(N(**dict(vars(pick),features={}))) is None
 opened=cards.build_for_pick(pick)
 closed=cards.settled_image(data,'🏁 Auswertung: 1✅ 0❌ · +0.12u')
 assert opened and closed and opened!=closed
 img=Image.open(io.BytesIO(closed));assert img.width==1080 and img.height>700
 Image.open(io.BytesIO(closed)).save('/tmp/prop-hunter-settled-preview.png')
 sent=[]
 def post(url,**kw):
  sent.append((url,kw));return N(status_code=200,text='',content=b'{}')
 results.TG_TOKEN='TEST';results.TG_CHAT='TEST'
 with patch.object(results.requests,'post',side_effect=post),patch.object(results.time,'sleep'):
  assert results._edit_message(123,'🏁 Auswertung: 0✅ 1❌ · -0.05u',image_pick=data)
 assert sent[0][0].endswith('/editMessageMedia')
 assert sent[0][1]['data']['message_id']==123
 assert json.loads(sent[0][1]['data']['media'])['caption']==''
 assert sent[0][1]['files']['card'][1].startswith(b'\x89PNG')
 sent.clear();responses=[N(status_code=400,text='Bad Request: there is no text in the message to edit'),N(status_code=429,text='Too Many Requests',json=lambda:{'parameters':{'retry_after':1}}),N(status_code=200,text='')]
 def retry(url,**kw):sent.append(url);return responses.pop(0)
 with patch.object(results.requests,'post',side_effect=retry),patch.object(results.time,'sleep'):
  assert results._edit_message(123,'🏁 Auswertung: 1✅ 0❌ · +0.12u',fallback_pick=data)
 assert sent[0].endswith('/editMessageText') and all(x.endswith('/editMessageMedia') for x in sent[1:])
assert cards._label({'point':25.5,'direction':'over','market':'Points'})=='Over 25.5 Points'
assert results._card_pick({'pick_keys':['a']},[{'dedup_key':'a','player':'A','market':'Points','line':20.5}],[])['point']==20.5
assert results._card_pick({'pick_keys':['a','b']},[{'dedup_key':'a'},{'dedup_key':'b'}],[]) is None
print('MEDIA SETTLEMENT TEST PASSED: render, original ID, no caption, legacy upgrade, 429 retry')

assert cards._label({'point':25.5,'direction':'over','market':'Points Over 25.5'})=='Over 25.5 Points'
assert cards._label({'point':.5,'direction':'over','market':'Moneyline','raw':{'team_builder_market':'moneyline'}})=='Sieg (inkl. OT)'

assert not results._image_upgrade_due({},'2026-10-30')
assert results._image_upgrade_due({},'2026-11-04')
assert results._image_upgrade_due({'media_type':'photo'},'2026-10-30')
assert not results._image_upgrade_due({'media_type':'photo','image_settlement_version':1},'2026-11-05')
print('BOUNDED LEGACY PHOTO MIGRATION TEST PASSED')

assert cards._label({'market':'rushing_attempts Over 15.5','point':15.5,'direction':'over'})=='Over 15.5 rushing attempts'
