"""Chronological out-of-sample gate; no model deployment from this module."""
from datetime import datetime, timezone
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score


def dataset(history, extract):
    rows=[]
    for entry in history:
        for pick in entry.get('picks',[]):
            if pick.get('result') not in ('win','loss') or pick.get('quote_invalidated') or pick.get('settlement_invalidated'):
                continue
            # Group by the tip's UTC issue day: no same-day rows cross a fold.
            try:
                stamp=str(pick.get('created_at') or pick.get('date') or entry.get('date'))
                dt=datetime.fromisoformat(stamp.replace('Z','+00:00'))
                dt=dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
                feats=extract(pick)
                if feats is None or not np.isfinite(feats).all() or not 1.0<float(feats[0]):continue
            except (ValueError,TypeError,OverflowError):continue
            rows.append((dt.isoformat(),feats,int(pick['result']=='win')))
    rows.sort(key=lambda r:r[0])
    return [r[1] for r in rows],[r[2] for r in rows],[r[0][:10] for r in rows]


def evaluate(X,y,days):
    report=dict(validation_version=1,validated_for_live=False,n_samples=len(y),status='collecting',folds=[])
    if len(y)<80 or len(set(y))<2 or len(set(days))<6:return report,None,None
    X=np.asarray(X,dtype=float);y=np.asarray(y)
    unique=sorted(set(days));days=np.asarray(days)
    observed=[];predicted=[];baseline=[]
    for train,test in TimeSeriesSplit(n_splits=min(5,len(unique)-1)).split(unique):
        train_days=[unique[i] for i in train];test_days=[unique[i] for i in test]
        tr=np.isin(days,train_days);te=np.isin(days,test_days)
        if len(set(y[tr]))<2:continue
        # Fit preprocessing exclusively on this fold's past observations.
        scaler=StandardScaler().fit(X[tr])
        model=LogisticRegression(max_iter=500,C=.5).fit(scaler.transform(X[tr]),y[tr])
        p=model.predict_proba(scaler.transform(X[te]))[:,1]
        b=np.clip(1/X[te,0],.001,.999)
        observed.extend(y[te]);predicted.extend(p);baseline.extend(b)
        report['folds'].append(dict(train_last_day=max(train_days),test_first_day=min(test_days),test_samples=int(te.sum())))
    if not observed:return report,None,None
    auc=float(roc_auc_score(observed,predicted)) if len(set(observed))>1 else .5
    report.update(auc=auc,brier=float(brier_score_loss(observed,predicted)),
        baseline_brier=float(brier_score_loss(observed,baseline)),
        log_loss=float(log_loss(observed,predicted,labels=[0,1])),
        baseline_log_loss=float(log_loss(observed,baseline,labels=[0,1])),test_samples=len(observed),
        baseline='raw_bookmaker_implied_1_over_odds')
    eligible=(len(report['folds'])>=3 and len(observed)>=60 and auc>=.52
        and report['brier']<report['baseline_brier'] and report['log_loss']<report['baseline_log_loss'])
    report.update(validated_for_live=eligible,status='active' if eligible else 'shadow')
    if not eligible:return report,None,None
    scaler=StandardScaler().fit(X)
    model=LogisticRegression(max_iter=500,C=.5).fit(scaler.transform(X),y)
    return report,model,scaler

if __name__=='__main__':
    import ast,json
    from pathlib import Path
    # Use the production feature extractor without booting network collectors.
    tree=ast.parse(Path('prophunter_core_1391.py').read_text())
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_pick_features')
    ns={'datetime':datetime}
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'production-features','exec'),ns)
    X,y,days=dataset(json.loads(Path('picks_history.json').read_text()),ns['_pick_features'])
    report,_,_=evaluate(X,y,days)
    Path('prop_hunter_ml_validation.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
