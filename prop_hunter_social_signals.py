import os, re, xml.etree.ElementTree as ET
from prop_hunter_shared_utils import http_get, http_json, safe_json_write, upsert_rows, hash_key, now_iso, log, warn

OUT="prop_hunter_social_signals.json"
KW={"injury":["injury","out","questionable","doubtful","inactive","ruled out","illness","ankle","knee"],
"rest":["rest","load management","minutes limit","minute restriction","back-to-back"],
"lineup":["lineup","starting","starter","will start","available","will play"],
"trade":["trade","waived","signed","activated"],"weather":["wind","rain","weather","roof"],"training":["practice","shootaround","limited practice"]}

def sig(text):
    t=(text or "").lower(); best=("general",0.2)
    for k,words in KW.items():
        hits=sum(1 for w in words if w in t)
        if hits and 0.35+hits*0.15>best[1]: best=(k,min(.95,0.35+hits*0.15))
    return best

def row(platform,author,url,text,created=None,raw=None):
    s,c=sig(text)
    return {"signal_id":hash_key(platform,author,url,text[:180]),"platform":platform,"author":author,"url":url,
    "text":text,"created_at":created or now_iso(),"signal_type":s,"confidence":c,"player_key":None,"team_key":None,
    "source_reliability":None,"raw":raw or {},"ingested_at":now_iso()}

def rss():
    out=[]
    for url in [x.strip() for x in os.getenv("SOCIAL_RSS_URLS","").split(",") if x.strip()]:
        r=http_get(url,retries=1)
        if not r or r.status_code>=400: continue
        try: root=ET.fromstring(r.text)
        except Exception: continue
        for it in root.findall(".//item")[:50]:
            title=it.findtext("title") or ""; link=it.findtext("link") or url
            desc=re.sub("<[^>]+>"," ",it.findtext("description") or "")
            out.append(row("rss",url,link,f"{title} {desc}",it.findtext("pubDate"),{"rss_url":url}))
    return out

def youtube():
    key=os.getenv("YOUTUBE_API_KEY","").strip()
    if not key: return []
    out=[]; queries=[q.strip() for q in os.getenv("SOCIAL_QUERIES","NBA injury report,NFL injury report,MLB lineup weather,WNBA injury report").split(",") if q.strip()]
    for q in queries[:8]:
        data=http_json("https://www.googleapis.com/youtube/v3/search",params={"part":"snippet","q":q,"type":"video","maxResults":10,"order":"date","key":key},retries=1) or {}
        for it in data.get("items",[]):
            sn=it.get("snippet") or {}; vid=(it.get("id") or {}).get("videoId")
            out.append(row("youtube",sn.get("channelTitle"),f"https://www.youtube.com/watch?v={vid}",f"{sn.get('title','')} {sn.get('description','')}",sn.get("publishedAt"),it))
    return out

def reddit():
    out=[]
    for sub in [s.strip() for s in os.getenv("REDDIT_SUBREDDITS","nba,wnba,nfl,mlb,sportsbook").split(",") if s.strip()][:8]:
        r=http_get(f"https://www.reddit.com/r/{sub}/new.json",headers={"User-Agent":"PropHunter/1.0"},retries=1)
        if not r or r.status_code>=400: continue
        try: data=r.json()
        except Exception: continue
        for ch in ((data.get("data") or {}).get("children") or [])[:20]:
            d=ch.get("data") or {}
            out.append(row("reddit",f"r/{sub}","https://reddit.com"+str(d.get("permalink","")),f"{d.get('title','')} {d.get('selftext','')}",None,d))
    return out

def x_api():
    tok=os.getenv("X_BEARER_TOKEN","").strip()
    if not tok: return []
    out=[]; qs=[q.strip() for q in os.getenv("SOCIAL_QUERIES","NBA injury report,NFL injury report,MLB lineup").split(",") if q.strip()]
    for q in qs[:5]:
        data=http_json("https://api.x.com/2/tweets/search/recent",params={"query":q,"max_results":10,"tweet.fields":"created_at,author_id"},headers={"Authorization":f"Bearer {tok}"},retries=1) or {}
        for tw in data.get("data",[]): out.append(row("x",tw.get("author_id"),"https://x.com/i/web/status/"+str(tw.get("id")),tw.get("text"),tw.get("created_at"),tw))
    return out

def main():
    rows=[]
    for fn in [rss,youtube,reddit,x_api]:
        try:
            part=fn(); rows+=part; log(f"{fn.__name__}: {len(part)}")
        except Exception as e: warn(f"{fn.__name__} failed {e}")
    uniq={r["signal_id"]:r for r in rows}
    out=list(uniq.values())
    safe_json_write(OUT,out); upsert_rows("prop_hunter_news_social_signals",out,"signal_id")
    log(f"social signals done {len(out)}")
if __name__=="__main__": main()
