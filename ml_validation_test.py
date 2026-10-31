from ml_validation import dataset,evaluate
import numpy as np
# Scrambled issue times and invalid historical tips must not contaminate folds.
h=[dict(date='2026-10-02',picks=[dict(result='win',odds=2,created_at='2026-10-02T10:00:00Z'),dict(result='loss',odds=2,quote_invalidated=True)]),dict(date='2026-10-01',picks=[dict(result='loss',odds=2)])]
X,y,d=dataset(h,lambda p:[p['odds'],0])
assert d==['2026-10-01','2026-10-02'] and y==[0,1]
r,m,s=evaluate(X,y,d);assert not r['validated_for_live'] and m is None
# A genuine predictive signal must pass against uninformative even-money odds.
n=360;y=np.tile([0,1],n//2);X=np.column_stack([np.full(n,2),y]);days=[f'2026-10-{i//15+1:02}' for i in range(n)]
r,m,s=evaluate(X,y,days)
assert r['validated_for_live'] and m is not None
assert all(f['train_last_day']<f['test_first_day'] for f in r['folds'])
# A flat signal must not deploy against the same even-money baseline.
X[:,1]=0
r,m,s=evaluate(X,y,days)
assert not r['validated_for_live'] and m is None
print('ML CHRONOLOGY / INVALIDATION / BASELINE DEPLOYMENT GATE PASSED')
