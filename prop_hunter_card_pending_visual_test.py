"""Pending original Telegram photo may be restyled without inventing a result."""
from prophunter_results import _decorate_card, _card_visual_text
pick={"date":"2026-11-17","type":"single","dedup_key":"verified-original",
      "player":"Sample Player","market":"Rebounds Under 4.5",
      "game":"Home @ Away","result":"pending","profit":None}
photo={"message_id":2435,"media_type":"photo","pick_keys":["verified-original"],
       "combo_ids":[],"text":"PROP HUNTER\n• Sample Player Rebounds Under 4.5 @1.70\n🏁 Auswertung: ⏳ offen\n@prophunter",
       "image_pick":{"type":"single","player":"Sample Player","game":"Home @ Away"}}
assert _decorate_card(photo,[pick],[]) is None
assert _card_visual_text(photo,[pick],[]) == photo["text"]
assert _card_visual_text(dict(photo,media_type="text"),[pick],[]) is None
assert _card_visual_text(dict(photo,pick_keys=["no-match"]),[pick],[]) is None
assert _card_visual_text(photo,[dict(pick,result="withdrawn")],[]) is None
closed=dict(pick,result="loss",actual_value=6,profit=-1)
assert "Auswertung:" in _card_visual_text(photo,[closed],[])
print("PENDING V3 PHOTO REPLACE / NO SYNTHETIC SETTLEMENT PASSED")
