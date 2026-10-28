"""Observed ESPN basketball stats and the North-American official gameday."""
from datetime import date, datetime
from zoneinfo import ZoneInfo


def official_gameday(value):
    text = str(value or '').strip()
    if not text:
        return None
    if len(text) == 10:
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            return None
    try:
        start = datetime.fromisoformat(text.replace('Z', '+00:00'))
        if start.tzinfo is None:
            return None
        return start.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    except ValueError:
        return None


def observed_stats(group, athlete):
    if athlete.get('didNotPlay') is True or not athlete.get('stats'):
        return None
    aliases = {'MINUTES': 'MIN', 'POINTS': 'PTS', 'REBOUNDS': 'REB', 'ASSISTS': 'AST',
               'STEALS': 'STL', 'BLOCKS': 'BLK', 'TURNOVERS': 'TO',
               'THREEPOINTFIELDGOALSMADE-THREEPOINTFIELDGOALSATTEMPTED': '3PT'}
    labels = group.get('labels') or group.get('keys') or []
    sm = {aliases.get(str(label).upper(), str(label).upper()): value
          for label, value in zip(labels, athlete['stats'])}
    def number(key):
        value = sm.get(key)
        if value in (None, '', '--'):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    pts, reb, ast = (number(key) for key in ('PTS', 'REB', 'AST'))
    if all(value is None for value in (pts, reb, ast)):
        return None
    stl, blk = number('STL'), number('BLK')
    parts = (pts, reb, ast, stl, blk)
    def double(need):
        hits = sum(value is not None and value >= 10 for value in parts)
        return True if hits >= need else False if all(v is not None for v in parts) else None
    return {'stat_map': sm, 'points': pts, 'rebounds': reb, 'assists': ast,
            'minutes': number('MIN'), 'steals': stl, 'blocks': blk,
            'turnovers': number('TO') if 'TO' in sm else number('TOV'),
            'pra': sum((pts, reb, ast)) if None not in (pts, reb, ast) else None,
            'ra': reb + ast if None not in (reb, ast) else None,
            'double_double': double(2), 'triple_double': double(3)}


def unobserved_log(row):
    raw = row.get('raw') if isinstance(row.get('raw'), dict) else {}
    return (str(row.get('source') or '').startswith('espn')
            and 'stat_map' in raw and not raw['stat_map'])
