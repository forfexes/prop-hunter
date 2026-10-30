"""Bounded scoreboard scans without starving current games or historical debt."""
from datetime import date, timedelta

def select_scan_dates(by_date, limit, today=None):
    today = today or date.today()
    limit = max(1, int(limit))
    parsed=[]
    for key in by_date:
        try:
            parsed.append((date.fromisoformat(f'{key[:4]}-{key[4:6]}-{key[6:8]}'),key))
        except (ValueError,TypeError):
            continue
    recent=sorted((x for x in parsed if today-timedelta(days=2)<=x[0]<=today),reverse=True)
    old=sorted(x for x in parsed if x[0]<today-timedelta(days=2))
    future=sorted(x for x in parsed if x[0]>today)
    # At most three current scoreboard days, with historical slots remaining
    # under normal limits. Rotate the old window daily, including unresolvable
    # legacy dates, so a permanently missing game cannot monopolize every run.
    chosen=recent[:limit]
    slots=limit-len(chosen)
    if old and slots:
        count=min(slots,len(old))
        offset=(today.toordinal()*count)%len(old)
        chosen.extend((old+old)[offset:offset+count])
    chosen.extend(future[:max(0,limit-len(chosen))])
    return [(key,by_date[key]) for _,key in chosen]
