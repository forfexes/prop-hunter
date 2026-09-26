#!/usr/bin/env python3
"""Offline regression test for observed game-market builder legs."""
from prop_hunter_event_markets import event_market_key, parse_draftkings_event_markets, parse_fanduel_event_markets

class KB:
    @staticmethod
    def _f(v):
        try:return float(v)
        except Exception:return None
    @staticmethod
    def _dec(v):
        try:x=float(str(v).replace('+',''))
        except Exception:return None
        if x>=100:return round(1+x/100,4)
        if x<=-100:return round(1+100/abs(x),4)
        return x if x>1 else None
    @staticmethod
    def _game(name):
        if ' @ ' in str(name):
            a,h=str(name).split(' @ ',1);return a,h
        return '', ''
    @staticmethod
    def _safe(row):return row

def check(v,msg):
    if not v:raise AssertionError(msg)

def main():
    check(event_market_key('Alternate Total Points')=='alternate_total_points','alt total mapping')
    check(event_market_key('Match Point Spread')=='point_spread','spread mapping')
    check(event_market_key('Both Teams to Score 100 Points in the Match - Yes')=='both_teams_100_points','100+ mapping')

    dk={
      'events':[{'id':'e1','name':'IND Pacers @ NY Knicks','startEventDate':'2026-10-01T00:00:00Z'}],
      'markets':[{'id':'m1','eventId':'e1','name':'Alternate Total Points'}],
      'selections':[
        {'marketId':'m1','label':'Over 204.5','points':204.5,'displayOdds':{'american':'+110'}},
        {'marketId':'m1','label':'Under 204.5','points':204.5,'displayOdds':{'american':'-120'}},
      ]}
    rows=parse_draftkings_event_markets(KB,dk,'NBA')
    check(len(rows)==2,f'DK event rows={rows}')
    check({r['direction'] for r in rows}=={'over','under'},'DK two-sided total')
    check(all(r['player_name']=='GAME' and r['market']=='alternate_total_points' for r in rows),'DK event identity')

    fd={'attachments':{'markets':{'x':{
      'marketName':'Both Teams to Score 100 Points in the Match',
      'runners':[
        {'runnerName':'Yes','winRunnerOdds':{'americanDisplayOdds':{'americanOdds':'+105'}}},
        {'runnerName':'No','winRunnerOdds':{'americanDisplayOdds':{'americanOdds':'-125'}}},
      ]
    }}}}
    event={'eventId':'e2','name':'MIN Timberwolves @ OKC Thunder','openDate':'2026-10-02T00:00:00Z'}
    rows=parse_fanduel_event_markets(KB,fd,'NBA',event)
    check(len(rows)==2,f'FD event rows={rows}')
    check(all(r['line']==.5 and r['market']=='both_teams_100_points' for r in rows),'FD binary event line')
    print('EVENT MARKET TEST PASSED: DK/FD totals, spreads and 100+ mappings')

if __name__=='__main__':main()
