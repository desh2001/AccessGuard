"""Transparent activity heuristics; observations, not security verdicts."""
from collections import defaultdict
from datetime import timezone


def summarize_activity(events, account_by_id):
    failures=defaultdict(int)
    for ev in events:
        if ev.outcome=='Failure':
            failures[ev.account_id]+=1
    output=[]
    for ev in events:
        if ev.occurred_at.tzinfo is None:
            from datetime import timezone as tz
            timestamp=ev.occurred_at.replace(tzinfo=tz.utc)
        else:
            timestamp=ev.occurred_at
        flags=[]
        if ev.outcome=='Failure' and failures[ev.account_id]>=4:
            flags.append('Multiple failed events in sampled period; investigate')
        if timestamp.astimezone(timezone.utc).hour in (0,1,2,3):
            flags.append('Unusual UTC hour in demo heuristic; not local time proof')
        a=account_by_id.get(ev.account_id)
        output.append({'id':ev.id,'account_id':ev.account_id,
            'username':a.username if a else 'Unknown account',
            'system_id':a.system_id if a else '',
            'occurred_at':timestamp.isoformat(), 'action':ev.action,
            'outcome':ev.outcome,'ip_address':ev.ip_address,
            'source':ev.source,'flags':flags})
    return output
