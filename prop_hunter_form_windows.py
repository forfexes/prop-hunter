"""Current-season form windows, with retained older history kept for comparison."""
from datetime import date,datetime,timedelta,timezone

def reference_date(value=None):
    if isinstance(value,datetime):return value.date()
    if isinstance(value,date):return value
    try:return date.fromisoformat(str(value)[:10])
    except (ValueError,TypeError):return datetime.now(timezone.utc).date()

def season_floor(league,reference):
    league=str(league or '').upper()
    day=reference_date(reference)
    if league == 'NBA':
        season_year = day.year if day.month >= 9 else day.year - 1
        # NBA 2026/27 regular season starts on Oct 20, 2026. Earlier
        # October ESPN backfill rows include preseason and must not
        # inflate L10/L15 player-prop evidence. Fail closed for this season.
        if season_year == 2026:
            return date(2026,10,20)
        if season_year == 2025:
            return date(2025,10,21)  # 2025/26 regular season start (no preseason)
        return date(season_year,9,1)
    if league in {'NHL','NCAAB','EUROLEAGUE','AHL','SHL','SWISS_NL'}:
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


def select_prev_season_rows(rows,league,reference=None,limit=15):
    """Regular-season rows of the PREVIOUS season (never preseason), newest first.
    Used only to pad a thin current-season sample; callers keep current games first."""
    ref=reference_date(reference)
    floor=season_floor(league,ref)
    if floor is None:return []
    prev_floor=season_floor(league,floor-timedelta(days=200))
    if prev_floor is None:return []
    out=[]
    for row in rows or []:
        if str(row.get('league') or '').upper()!=str(league or '').upper():continue
        try:day=date.fromisoformat(str(row.get('game_date') or '')[:10])
        except ValueError:continue
        if prev_floor<=day<floor:out.append(row)
    out.sort(key=lambda x:(str(x.get('game_date')),str(x.get('game_id') or '')),reverse=True)
    return out[:limit]
