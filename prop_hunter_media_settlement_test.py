"""Premium-only Telegram card edits and results regression (offline mocks)."""
import io,json,os
from types import SimpleNamespace as N
from unittest.mock import patch
from PIL import Image
import prop_hunter_image_cards as cards
import prophunter_results as results

pick=N(type='betbuilder',features={
    'combined_odds_observed':True,
    'combined_quote_id':'fixture-bookmaker-ticket',
    'bookmaker':'FIXTURE ONLY'},game='Lakers @ Celtics',sport='NBA',
    commence_time='2026-11-20T19:00:00+00:00',odds=3.4,
    leg_details=[
        {'player':'Player A','market':'Points','point':25.5,'direction':'over','odds':1.8},
        {'player':'Player B','market':'Rebounds','point':6.5,'direction':'under','odds':1.9}])
data=cards.snapshot(pick)
with patch.object(cards,'ON',True), \
     patch.object(cards,'player_photo',return_value=None), \
     patch.object(cards,'team_logo',return_value=None), \
     patch.object(cards,'render',side_effect=AssertionError('old card used')):
    # A new combo without a real ticket may not be published.
    assert cards.build_for_pick(N(**dict(vars(pick),features={}))) is None
    # Even already-published legacy image snapshots may NEVER resurrect the old
    # renderer or falsely label an unverified combined quote as observed.
    legacy=dict(data,features={'bookmaker':'FIXTURE ONLY'})
    assert cards.settled_image(legacy,'🏁 Auswertung: 1✅ 0❌ · +0.12u') is None

# The premium adapter itself is covered by its dedicated 1080x1440 render
# suite. Here we isolate Telegram retries, settlement and exact message IDs.
premium_calls=[]
def premium_preview(pick,rows,teams):
    summary=str(getattr(pick,'settlement_summary','') or '')
    premium_calls.append((summary,rows))
    out=io.BytesIO()
    Image.new('RGB',(1080,1440),(42,80,63) if 'gewonnen' in summary else (20,35,57)).save(out,'PNG')
    return out.getvalue()

with patch.object(cards,'ON',True), \
     patch.object(cards,'player_photo',return_value=None), \
     patch.object(cards,'team_logo',return_value=None), \
     patch.object(cards,'render',side_effect=AssertionError('old card used')), \
     patch('prop_hunter_nba_premium_adapter.render_nba_pick',side_effect=premium_preview):
    opened=cards.build_for_pick(pick)
    closed=cards.settled_image(data,'🏁 Auswertung: 1✅ 0❌ · +0.12u')
assert opened and closed and opened!=closed
assert '1 gewonnen' in premium_calls[-1][0], premium_calls[-1][0]
img=Image.open(io.BytesIO(closed))
assert img.size==(1080,1440)

sent=[]
def post(url,**kw):
    sent.append((url,kw))
    mid=(kw.get('data') or kw.get('json') or {}).get('message_id')
    return N(status_code=200,text='',content=b'{}',
             json=lambda:{'ok':True,'result':{'message_id':mid,'photo':[{'file_id':'new-photo'}]}})
results.TG_TOKEN='TEST';results.TG_CHAT='TEST'
with patch.object(cards,'settled_image',return_value=closed), \
     patch.object(results.requests,'post',side_effect=post), \
     patch.object(results.time,'sleep'):
    assert results._edit_message(123,'🏁 Auswertung: 0✅ 1❌ · -0.05u',image_pick=data)
assert sent[0][0].endswith('/editMessageMedia')
assert sent[0][1]['data']['message_id']==123
assert json.loads(sent[0][1]['data']['media'])['caption']==''
assert sent[0][1]['files']['card'][1].startswith(b'\xff\xd8')
assert sent[0][1]['files']['card'][2]=='image/jpeg'

sent.clear()
responses=[
    N(status_code=400,text='Bad Request: there is no text in the message to edit'),
    N(status_code=429,text='Too Many Requests',json=lambda:{'parameters':{'retry_after':1}}),
    N(status_code=200,text='',json=lambda:{'ok':True,'result':{
        'message_id':123,'photo':[{'file_id':'new-photo'}]}})
]
def retry(url,**kw):
    sent.append(url)
    return responses.pop(0)
with patch.object(cards,'settled_image',return_value=closed), \
     patch.object(results.requests,'post',side_effect=retry), \
     patch.object(results.time,'sleep'):
    assert results._edit_message(123,'🏁 Auswertung: 1✅ 0❌ · +0.12u',fallback_pick=data)
assert sent[0].endswith('/editMessageText')
assert all(x.endswith('/editMessageMedia') for x in sent[1:])
print('PREMIUM MEDIA SETTLEMENT PASSED: no legacy, original ID, JPEG, 429 retry')

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

# An HTTP 200 alone is not a valid photo-edit acknowledgement.
with patch.object(results.requests,'post',return_value=N(status_code=200,text='',json=lambda:{'ok':True,'result':{'message_id':123}})), patch.object(results.time,'sleep'):
 assert not results._edit_message(123,'Pending',image_pick=data)
print('TELEGRAM EXACT MESSAGE / PHOTO ACKNOWLEDGEMENT PASSED')

# Regression: only explicitly published model metrics may be reprinted.
single={'type':'single','player':'Verified Athlete','sport':'NBA','game':'Away @ Home',
        'market':'points','direction':'under','point':20.5,'odds':1.77,
        'features':{'recent_form':{'l10':{'hits':7,'n':9}}},'stake':1}
with patch.object(cards,'ON',True), \
     patch.object(cards,'player_photo',return_value=None), \
     patch.object(cards,'team_logo',return_value=None), \
     patch.object(cards,'render',side_effect=AssertionError('old card used')), \
     patch('prop_hunter_nba_premium_adapter.render_nba_pick',return_value=b'PNG') as draw:
 assert cards.settled_image(single,'📈 Prob 72% · Edge +20.8% · Confidence 91/100\\n🏁 Auswertung: 1⏳ · +0.00u')==b'PNG'
 assert draw.call_args.args[1][0]['model']=={'prob':'72','edge':'+20.8','confidence':'91/100'}
 assert cards.settled_image(single,'🏁 Auswertung: 1⏳ · +0.00u')==b'PNG'
 assert not any(draw.call_args.args[1][0]['model'].values())
print('ORIGINAL PUBLISHED MODEL METRICS / MISSING EVIDENCE GUARDS PASSED')

# Sustained Telegram HTTP 502 must not trigger 35 futile requests.
results._EDIT_STATE["gateway_unavailable"] = False
with patch.object(cards, "settled_image", return_value=b"VALID-PNG"), \
     patch.object(results.requests, "post", return_value=N(status_code=502, text='{"description":"Bad Gateway"}')) as posts, \
     patch.object(results.time, "sleep"):
    assert not results._edit_message(123, 'Pending', image_pick=data)
    assert posts.call_count == 3, posts.call_count
    assert results._EDIT_STATE["gateway_unavailable"] is True
    assert not results._edit_message(124, 'Pending', image_pick=data)
    assert posts.call_count == 3
results._EDIT_STATE["gateway_unavailable"] = False
print("TELEGRAM GATEWAY 502 BACKOFF / SAFETY CIRCUIT PASS")

# A 400 'message is not modified' is a safe, already-identical photo,
# NOT an actual photo replacement. The writer must count it separately.
with patch.object(cards,"settled_image",return_value=b"VALID-PNG"), \
     patch.object(results.requests,"post",return_value=N(
         status_code=400,text="Bad Request: message is not modified")), \
     patch.object(results.time,"sleep"):
    assert results._edit_message(123,"Pending",image_pick=data)
    assert results._EDIT_STATE["unchanged"] is True
    assert results._EDIT_STATE["reason"]=="telegram_media_already_identical"
results._EDIT_STATE["unchanged"]=False
print("TELEGRAM 400 ALREADY-IDENTICAL IS NOT COUNTED AS A REPLACED PHOTO")

# Strict all-sport premium settlement: historical NHL/NFL/WNBA/MLB photos
# cannot be repainted from unapproved sample-filled templates.
legacy_photo={'sport':'NHL','type':'single','player':'TEST NHL','features':{}}
with patch.dict(os.environ,{"PH_OWNER_APPROVED_ALL_SPORTS":"1"}), \
     patch.object(cards,'settled_image',
                  side_effect=AssertionError('unapproved legacy card repainted')), \
     patch.object(results.requests,'post',side_effect=post) as caption_send, \
     patch.object(results.time,'sleep'):
    sent.clear()
    assert results._edit_message(123,'🏁 Auswertung: ✅ gewonnen',
                                  image_pick=legacy_photo)
    assert sent[-1][0].endswith('/editMessageCaption')
    assert sent[-1][1]['json']['message_id']==123
    assert sent[-1][1]['json']['caption']=='🏁 Auswertung: ✅ gewonnen'
    caption_send.assert_called_once()
    sent.clear()
    assert not results._edit_message(123,'LONG-RESULT-'*110,
                                      image_pick=legacy_photo)
    assert not sent
    assert results._EDIT_STATE['reason']=='original_photo_caption_exceeds_1024_no_truncation'
    assert not results._replace_recent_text_with_photo(
        {'media_type':'text','message_id':123},
        legacy_photo,'🏁 Auswertung: ✅ gewonnen')
print('HISTORICAL ALL-SPORT PHOTO IMMUTABILITY AND SAME-ID CAPTION VERIFIED')
