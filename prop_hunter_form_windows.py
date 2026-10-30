"""Current-season form windows, with retained older history kept for comparison."""
from datetime import date,datetime,timezone

def reference_date(value=None):
    if isinstance(value,datetime):return value.date()
    if isinstance(value,date):return value
    try:return date.fromisoformat(str(value)[:10])
    except (ValueError,TypeError):return datetime.now(timezone.utc).date()

def season_floor(league,reference):
    league=str(league or '').upper()
    day=reference_date(reference)
    if league in {'NBA','NHL','NCAAB','EUROLEAGUE','AHL','SHL','SWISS_NL'}:
        return date(day.year if day.month>=9 else day.year-1,9,1)
    if league in {'NFL','NCAAF'}:
        return date(day.year if day.month>=7 else day.year-1,7,1)
    if league in {'MLB','WNBA'}:
        return date(day.year,1,1)
    return None

def select_form_rows(rows,league,reference=None,limit=15):
    ref=reference_date(reference)
    floor=season_floor(league,ref)
    selected=[]
    for row in rows or []:
        if str(row.get('league') or '').upper()!=str(league or '').upper():continue
        try:day=date.fromisoformat(str(row.get('game_date') or '')[:10])
        except ValueError:continue
        if floor is None or not floor<=day<=ref:continue
        selected.append(row)
    if str(league).upper() in {'NBA','WNBA'}:
        by_day={}
        for row in selected:by_day.setdefault(str(row.get('game_date'))[:10],[]).append(row)
        unique=[]
        for daily in by_day.values():
            if len(daily)==1:
                unique.extend(daily);continue
            timed=[row for row in daily if isinstance(row.get('raw'),dict) and row['raw'].get('start_time_utc')]
            if len(timed)==1:
                unique.extend(timed);continue
            fields=('points','rebounds','assists','threes_made','steals','blocks','turnovers')
            signatures={tuple(row.get(k) for k in fields) for row in daily}
            if len(signatures)==1:unique.append(daily[0])
            # Conflicting same-day rows without unique observed event context
            # cannot count as two games or be resolved by an arbitrary game id.
        selected=unique
    selected.sort(key=lambda x:(str(x.get('game_date')),str(x.get('game_id') or '')),reverse=True)
    return selected[:limit]

def form_context(rows,league,reference=None):
    ref=reference_date(reference)
    floor=season_floor(league,ref)
    current=select_form_rows(rows,league,ref)
    return dict(form_window_policy='current_season',form_reference_date=ref.isoformat(),
                form_season_start=floor.isoformat() if floor else None,
                form_games_available=len(current),
                form_first_game_date=current[-1].get('game_date') if current else None,
                form_last_game_date=current[0].get('game_date') if current else None)
