"""Bot-owned Telegram card replacement regression: no duplicates, no old-card deletion."""
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import patch
import prophunter_results as results
import prop_hunter_image_cards as images

now=datetime.now(timezone.utc)
fresh=lambda: {"created_at":(now-timedelta(hours=2)).isoformat(),
               "chat_id":"-100123","message_id":111,"media_type":"text"}
visual={"type":"single","player":"Player A","sport":"NBA","market":"Points",
        "point":10.5,"direction":"over","odds":1.8}
class Reply:
    def __init__(self,status,id=None):
        self.status_code=status;self._id=id
    def json(self):return {"result":{"message_id":self._id}} if self._id else {}

calls=[]
def respond(*answers):
    queue=list(answers)
    def post(url,**kwargs):
        calls.append((url,kwargs))
        return queue.pop(0)
    return post

results.TG_TOKEN="TEST";results.TG_CHAT="-100123"
with patch.object(images,"settled_image",return_value=b"PNG"),patch.object(results.requests,"post",
     side_effect=respond(Reply(200,222),Reply(200))):
    card=fresh()
    assert results._replace_recent_text_with_photo(card,visual,"pending")
    assert card["message_id"]==222 and card["media_type"]=="photo"
    assert card["card_design_version"]==5
    assert calls[-2][0].endswith("/sendPhoto") and calls[-1][0].endswith("/deleteMessage")
    assert calls[-1][1]["json"]["message_id"]==111

calls.clear()
with patch.object(images,"settled_image",return_value=b"PNG"),patch.object(results.requests,"post",
     side_effect=respond(Reply(200,333),Reply(400),Reply(200))):
    card=fresh()
    assert not results._replace_recent_text_with_photo(card,visual,"pending")
    assert card["message_id"]==111 and card["media_type"]=="text"
    assert [x[0].split("/")[-1] for x in calls]==["sendPhoto","deleteMessage","deleteMessage"]
    assert calls[-1][1]["json"]["message_id"]==333

calls.clear()
with patch.object(results.requests,"post",side_effect=AssertionError("must not send")):
    card=fresh()
    card["created_at"]=(now-timedelta(days=3)).isoformat()
    assert not results._replace_recent_text_with_photo(card,visual,"pending")
    card=fresh();card["media_type"]="photo"
    assert not results._replace_recent_text_with_photo(card,visual,"pending")
print("TELEGRAM TEXT-TO-ORIGINAL-V5-PHOTO SAFE REPLACEMENT REGRESSION PASSED")
