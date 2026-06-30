#!/usr/bin/env python3
from __future__ import annotations
import os, re, requests
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

TELEGRAM_BOT_TOKEN=os.environ.get('TELEGRAM_BOT_TOKEN','').strip(); TELEGRAM_CHAT_ID=os.environ.get('TELEGRAM_CHAT_ID','').strip()
SUPABASE_URL=os.environ.get('SUPABASE_URL','').rstrip('/'); SUPABASE_KEY=os.environ.get('SUPABASE_KEY','').strip()
MIN_EDGE=float(os.environ.get('PH_MIN_EDGE','3.0')); MAX_TOTAL=int(os.environ.get('PH_MAX_PICKS_TOTAL','50')); MAX_PER_PLAYER=int(os.environ.get('PH_MAX_PER_PLAYER','3')); MAX_PER_GAME=int(os.environ.get('PH_MAX_PER_GAME','6'))
TODAY_HUMAN=datetime.now(timezone.utc).strftime('%d.%m.%Y'); TODAY_SQL=datetime.now(timezone.utc).strftime('%Y-%m-%d')

def log(m): print(f"{datetime.now(timezone.utc).strftime('%H:%M:%S')} INFO    {m}", flush=True)
def warn(m): print(f"{datetime.now(timezone.utc).strftime('%H:%M:%S')} WARNING {m}", flush=True)
def hdr(): return {'apikey':SUPABASE_KEY,'Authorization':f'Bearer {SUPABASE_KEY}','Content-Type':'application/json'}
def norm(x): return str(x or '').strip()
def fnum(x, default=0.0):
    try:
        if x is None or x=='': return default
        return float(x)
    except Exception: return default

def line_txt(x):
    if x is None: return ''
    try:
        f=float(x)
        return str(int(f)) if f.is_integer() else str(f).rstrip('0').rstrip('.')
    except Exception: return norm(x)

def clean_market(market, side, line):
    m=norm(market).replace('3Pm','3PM').replace('3pm','3PM') or 'Prop'
    if m.lower()=='home run': return 'Home Run'
    sd=norm(side) or 'Over'; ln=line_txt(line)
    txt=f'{m} {sd} {ln}'.strip() if ln else f'{m} {sd}'.strip()
    return re.sub(r'\b(Over|Under)\s+([0-9]+(?:\.[0-9]+)?)\s+\2\b', r'\1 \2', txt, flags=re.I).replace('3Pm','3PM')

@dataclass
class Pick:
    row:Dict[str,Any]; sport:str; league:str; team:str; player:str; market:str; line:Any; side:str; odds:float; edge:float; prob:float; stake:float; event_id:str; game:str
    @property
    def clean_market(self): return clean_market(self.market,self.side,self.line)
    @property
    def label_sport(self):
        s=f'{self.sport} {self.league}'.lower()
        if 'mlb' in s or 'baseball' in s: return '⚾ MLB'
        if 'nfl' in s or 'americanfootball' in s: return '🏈 NFL'
        if 'wnba' in s: return '🏀 WNBA'
        if 'nba' in s: return '🏀 NBA'
        return '🏀 BASKETBALL'

def priority(m):
    m=norm(m).lower(); order=[('pra',1),('pr',2),('pa',3),('reb+ast',4),('points',5),('strikeouts',6),('total bases',7),('home run',8),('rebounds',9),('assists',10),('3pm',11)]
    for k,v in order:
        if k in m: return v
    return 50

def stake(edge,odds):
    if edge>=10: return 0.75
    if edge>=7: return 0.60
    if edge>=4: return 0.50
    if odds>=4: return 0.20
    return 0.33

def fetch_rows():
    if not SUPABASE_URL or not SUPABASE_KEY: warn('Supabase env missing'); return []
    for table in ['v_prop_hunter_today_value','prop_hunter_normalized']:
        try:
            params={'select':'*','limit':'1000'}
            if table=='prop_hunter_normalized': params.update({'date':f'eq.{TODAY_SQL}','edge':f'gte.{MIN_EDGE}','order':'edge.desc'})
            r=requests.get(f'{SUPABASE_URL}/rest/v1/{table}',headers=hdr(),params=params,timeout=30)
            if r.status_code>=300: warn(f'{table} status={r.status_code}: {r.text[:250]}'); continue
            data=r.json()
            if isinstance(data,list) and data: log(f'loaded {len(data)} rows from {table}'); return data
            log(f'{table}: 0 rows')
        except Exception as e: warn(f'{table} failed: {e}')
    return []

def row_pick(r):
    odds=fnum(r.get('odds')); edge=fnum(r.get('edge'))
    if odds<=1.01 or edge<MIN_EDGE: return None
    player=norm(r.get('player')); market=norm(r.get('market'))
    if not player or not market: return None
    st=fnum(r.get('stake')) or stake(edge,odds)
    return Pick(r,norm(r.get('sport')),norm(r.get('league')),norm(r.get('team')),player,market,r.get('line'),norm(r.get('side')) or 'Over',odds,edge,fnum(r.get('prob')),st,norm(r.get('event_id')),norm(r.get('game')))

def dedupe(picks):
    picks=sorted(picks,key=lambda p:(p.label_sport,priority(p.market),-p.edge,-p.odds)); out=[]; seen=set(); pp=defaultdict(int); pg=defaultdict(int)
    for p in picks:
        key=(p.player.lower(),p.clean_market.lower(),round(p.odds,3))
        if key in seen: continue
        seen.add(key); g=p.event_id or p.game or f'{p.label_sport}:{p.team}'
        if pp[p.player.lower()]>=MAX_PER_PLAYER or pg[g]>=MAX_PER_GAME: continue
        out.append(p); pp[p.player.lower()]+=1; pg[g]+=1
        if len(out)>=MAX_TOTAL: break
    return out

def fmt_odds(x): return f'{x:.2f}'.rstrip('0').rstrip('.')
def fmt_edge(x): return f'+{x:.1f}%' if x>=0 else f'{x:.1f}%'

def builders(picks):
    base=[]; used=set()
    for p in sorted(picks,key=lambda x:(-x.edge,priority(x.market),-x.odds)):
        if p.player.lower() in used: continue
        base.append(p); used.add(p.player.lower())
        if len(base)>=6: break
    blocks=[]
    if len(base)>=2: blocks.append(f'🎯 SAFE BUILDER\n✅ {base[0].player} — {base[0].clean_market}\n✅ {base[1].player} — {base[1].clean_market}\n💰 Quote: siehe Book')
    if len(base)>=3: blocks.append(f'💎 VALUE BUILDER\n✅ {base[0].player} — {base[0].clean_market}\n✅ {base[1].player} — {base[1].clean_market}\n✅ {base[2].player} — {base[2].clean_market}\n💰 Quote: siehe Book')
    longs=[p for p in picks if p.odds>=3 or 'home run' in p.clean_market.lower()]
    if len(longs)>=2: blocks.append('💣 LOTTERY\n'+'\n'.join(f'⭐ {p.player} — {p.clean_market} @{fmt_odds(p.odds)}' for p in longs[:3]))
    return blocks

def card(picks):
    lines=['🎯 PROP HUNTER',f'📅 {TODAY_HUMAN}','','━━━━━━━━━━━━━━━━━━']
    if not picks: return '\n'.join(lines+['','Keine sauberen Value Picks gefunden.','','@prophunter'])
    grouped=defaultdict(list)
    for p in picks: grouped[p.label_sport].append(p)
    total=0
    for sport in sorted(grouped):
        lines+=['',sport,'','🔥 BEST PICKS','']
        for i,p in enumerate(grouped[sport],1):
            total+=1; prefix=f'{p.team} — ' if p.team else ''
            lines += [f'{i}️⃣ {prefix}{p.player}', f'🎯 {p.clean_market} @{fmt_odds(p.odds)}', f'📈 Edge {fmt_edge(p.edge)}' + (f' · Model {p.prob:.0f}%' if p.prob else '') + f' · Stake {p.stake:.2f}u','']
        lines.append('━━━━━━━━━━━━━━━━━━')
    b=builders(picks)
    if b: lines+=['','\n\n'.join(b),'','━━━━━━━━━━━━━━━━━━']
    lines+=['','📊 CARD',f'✅ Singles: {total}',f'🎯 Builder: {sum(1 for x in b if not x.startswith("💣"))}',f'💣 Lottery/Kombis: {sum(1 for x in b if x.startswith("💣"))}','','✅ Nur positive Edge','✅ Konzentration begrenzt','✅ Lines bestätigt','','@prophunter']
    return '\n'.join(lines).strip()

def send(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: warn('Telegram env missing'); print(text); return False
    r=requests.post(f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage',json={'chat_id':TELEGRAM_CHAT_ID,'text':text,'disable_web_page_preview':True},timeout=20)
    if r.status_code>=300: warn(f'Telegram failed {r.status_code}: {r.text[:300]}'); print(text); return False
    log('Telegram OK'); return True

def persist(picks):
    if not SUPABASE_URL or not SUPABASE_KEY or not picks: return
    rows=[{'sent_date':TODAY_SQL,'pick_type':'single','sport':p.label_sport,'league':p.league,'event_id':p.event_id,'game':p.game,'team':p.team,'player':p.player,'market':p.market,'line':p.line,'side':p.side,'odds':p.odds,'prob':p.prob,'edge':p.edge,'stake':p.stake,'raw':p.row,'dedup_key':f'{p.player.lower()}|{p.clean_market.lower()}|{p.line}|{p.side.lower()}'} for p in picks]
    r=requests.post(f'{SUPABASE_URL}/rest/v1/prop_hunter_picks',headers={**hdr(),'Prefer':'resolution=ignore-duplicates'},params={'on_conflict':'dedup_key,sent_date'},json=rows,timeout=30)
    if r.status_code>=300: warn(f'persist failed {r.status_code}: {r.text[:300]}')
    else: log(f'persisted {len(rows)} picks')

def main():
    log('PROP HUNTER FINAL READER V7')
    picks=[p for r in fetch_rows() if (p:=row_pick(r))]
    log(f'quality picks: {len(picks)}')
    picks=dedupe(picks); log(f'final picks: {len(picks)}')
    txt=card(picks); send(txt); persist(picks); print(txt); return 0
if __name__=='__main__': raise SystemExit(main())
