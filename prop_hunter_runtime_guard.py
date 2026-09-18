#!/usr/bin/env python3
"""PROP HUNTER — guarded automatic retraining.

Runs only in maintenance/results contexts. It refuses to retrain with insufficient
settled history and records the outcome in the model registry.
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
from prop_hunter_model_registry import build_registry, FILE

MIN_RETRAIN_SAMPLES=80


def main():
    reg=build_registry()
    active=sum(1 for v in reg.get("groups",{}).values() if v.get("status") in {"active","degraded"})
    try:
        import prophunter
        X,y=prophunter.build_ml_dataset()
        if len(y) < MIN_RETRAIN_SAMPLES or len(set(y)) < 2:
            reg["global_model"]={"status":"collecting","samples":len(y),"min_samples":MIN_RETRAIN_SAMPLES}
        else:
            payload=prophunter.train_ml_model()
            if payload:
                auc=float(payload.get("auc") or 0)
                reg["global_model"]={"status":"active" if auc>=0.52 else "shadow","samples":payload.get("n_samples",len(y)),
                    "auc":round(auc,4),"trained_at":payload.get("trained_at")}
            else:
                reg["global_model"]={"status":"skipped","samples":len(y)}
    except Exception as exc:
        reg["global_model"]={"status":"error","error":str(exc)[:300]}
    reg["updated_at"]=datetime.now(timezone.utc).isoformat(); reg["active_groups"]=active
    FILE.write_text(json.dumps(reg,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    print(f"retrainer: groups={len(reg.get('groups',{}))} global={reg.get('global_model',{}).get('status')}")

if __name__ == "__main__": main()
