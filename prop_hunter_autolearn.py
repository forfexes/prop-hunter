#!/usr/bin/env python3
"""Autonomous calibrated probability learning for PROP HUNTER.

The learner uses only settled historical picks. Candidate models are evaluated in
chronological folds with Brier score and log loss. A candidate replaces the current
champion only when it is better than both the implied-odds baseline and the stored
champion. Models are saved as JSON so GitHub Actions can persist them safely.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from prop_hunter_shared_utils import safe_json_load, safe_json_write, select_rows, select_pick_rows, to_float

MODEL_FILE = Path(os.getenv("PH_AUTOML_MODEL_FILE", "prop_hunter_model_registry.json"))
HISTORY_FILE = Path(os.getenv("PH_HISTORY_FILE", "picks_history.json"))
MIN_GLOBAL = int(os.getenv("PH_AUTOML_MIN_GLOBAL", "60"))
MIN_GROUP = int(os.getenv("PH_AUTOML_MIN_GROUP", "45"))
N_HASH = 24
NUMERIC_FEATURES = (
    "implied_prob", "log_odds", "edge", "stake", "line", "confidence",
    "hit_l5", "hit_l10", "hit_l20", "avg_l5", "avg_l10", "line_vs_avg",
    "source_trust", "book_consensus", "line_move", "rest_days", "minutes",
)
DIM = len(NUMERIC_FEATURES) + N_HASH


def _clip(value: float, lo: float = 1e-5, hi: float = 1 - 1e-5) -> float:
    return max(lo, min(hi, float(value)))


def _market_group(market: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(market or "").lower()).strip()
    rules = (
        (("home run", "homer", " hr "), "home_runs"),
        (("strikeout", "pitcher k"), "strikeouts"),
        (("hits runs rbi", "hits runs rbis", "h+r+rbi"), "hrr"),
        (("total bases",), "total_bases"),
        (("hits",), "hits"),
        (("points rebounds assists", "pra"), "pra"),
        (("points rebounds", "pr"), "points_rebounds"),
        (("points assists", "pa"), "points_assists"),
        (("rebounds assists", "ra"), "rebounds_assists"),
        (("3 pt", "three", "3pm"), "threes"),
        (("points",), "points"),
        (("rebounds",), "rebounds"),
        (("assists",), "assists"),
        (("passing",), "passing"),
        (("rushing",), "rushing"),
        (("receiving", "reception"), "receiving"),
        (("touchdown",), "touchdowns"),
        (("shots",), "shots"),
    )
    padded = f" {text} "
    for needles, label in rules:
        if any(n in padded for n in needles):
            return label
    return (text[:40].replace(" ", "_") or "other")


def _hash_index(token: str) -> int:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big") % N_HASH


def _deep_get(row: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    containers = [row]
    for name in ("features", "pick_raw", "raw", "metadata"):
        value = row.get(name)
        if isinstance(value, dict):
            containers.append(value)
    for container in containers:
        for key in keys:
            if container.get(key) not in (None, ""):
                return container.get(key)
    return default


def _canonical_row(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    result = str(_deep_get(row, "result", "outcome", "status", default="")).lower()
    if result not in {"win", "loss", "won", "lost", "hit", "miss"}:
        return None
    y = 1 if result in {"win", "won", "hit"} else 0
    odds = to_float(_deep_get(row, "odds", "odds_decimal", "decimal_odds"))
    if not odds or odds <= 1:
        return None
    created = str(_deep_get(row, "date", "event_date", "sent_date", "game_date", "created_at", "settled_at", default=""))
    sport = str(_deep_get(row, "sport", "league", default="UNKNOWN")).upper()
    market = str(_deep_get(row, "market", "market_key", default="other"))
    direction = str(_deep_get(row, "direction", "side", default="over")).lower()
    source = str(_deep_get(row, "source", default="unknown")).lower()
    book = str(_deep_get(row, "bookmaker", "book", default=source)).lower()
    return {
        "y": y, "date": created, "player": str(_deep_get(row, "player", "player_name", default="")),
        "game": str(_deep_get(row, "game", "event_id", "game_id", default="")),
        "sport": sport, "market": market,
        "market_group": _market_group(market), "direction": direction,
        "source": source, "book": book, "odds": odds,
        "line": to_float(_deep_get(row, "line", "point"), 0.0) or 0.0,
        "edge": (to_float(_deep_get(row, "edge_pct", "edge"), 0.0) or 0.0) / (100.0 if abs(to_float(_deep_get(row, "edge_pct", "edge"), 0.0) or 0.0) > 1 else 1.0),
        "stake": to_float(_deep_get(row, "stake"), 0.0) or 0.0,
        "confidence": (to_float(_deep_get(row, "confidence"), 0.0) or 0.0) / 100.0,
        "hit_l5": to_float(_deep_get(row, "hit_rate_l5", "l5_hit_rate"), 0.0) or 0.0,
        "hit_l10": to_float(_deep_get(row, "hit_rate_l10", "l10_hit_rate"), 0.0) or 0.0,
        "hit_l20": to_float(_deep_get(row, "hit_rate_l20", "l20_hit_rate"), 0.0) or 0.0,
        "avg_l5": to_float(_deep_get(row, "avg_l5"), 0.0) or 0.0,
        "avg_l10": to_float(_deep_get(row, "avg_l10"), 0.0) or 0.0,
        "line_vs_avg": to_float(_deep_get(row, "line_vs_avg"), 0.0) or 0.0,
        "source_trust": to_float(_deep_get(row, "source_trust"), 1.0) or 1.0,
        "book_consensus": to_float(_deep_get(row, "book_consensus", "consensus_prob"), 0.0) or 0.0,
        "line_move": to_float(_deep_get(row, "line_move", "line_movement"), 0.0) or 0.0,
        "rest_days": to_float(_deep_get(row, "rest_days"), 0.0) or 0.0,
        "minutes": to_float(_deep_get(row, "minutes", "projected_minutes"), 0.0) or 0.0,
    }


def load_training_rows(limit: int = 10000) -> List[Dict[str, Any]]:
    raw: List[Dict[str, Any]] = []
    raw.extend(select_rows("prop_hunter_results", limit=limit))
    raw.extend(select_pick_rows(limit=limit))
    history = safe_json_load(HISTORY_FILE, {}) or {}
    for entry in history.values() if isinstance(history, dict) else []:
        if isinstance(entry, dict):
            raw.extend(entry.get("picks", []) or [])
    rows = [x for x in (_canonical_row(r) for r in raw) if x]
    # Dedup exact historical records before training.
    dedup: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = "|".join(str(row.get(k, "")) for k in ("date", "sport", "game", "player", "market", "direction", "odds", "line", "y"))
        dedup[key] = row
    return sorted(dedup.values(), key=lambda r: r.get("date") or "")


def _vector(row: Dict[str, Any]) -> List[float]:
    implied = _clip(1.0 / float(row["odds"]))
    numeric = {
        "implied_prob": implied,
        "log_odds": math.log(float(row["odds"])),
        "edge": float(row.get("edge", 0)), "stake": float(row.get("stake", 0)),
        "line": float(row.get("line", 0)), "confidence": float(row.get("confidence", 0)),
        "hit_l5": float(row.get("hit_l5", 0)), "hit_l10": float(row.get("hit_l10", 0)),
        "hit_l20": float(row.get("hit_l20", 0)), "avg_l5": float(row.get("avg_l5", 0)),
        "avg_l10": float(row.get("avg_l10", 0)), "line_vs_avg": float(row.get("line_vs_avg", 0)),
        "source_trust": float(row.get("source_trust", 1)), "book_consensus": float(row.get("book_consensus", 0)),
        "line_move": float(row.get("line_move", 0)), "rest_days": float(row.get("rest_days", 0)),
        "minutes": float(row.get("minutes", 0)),
    }
    vec = [numeric[k] for k in NUMERIC_FEATURES] + [0.0] * N_HASH
    for token in (
        f"sport={row.get('sport')}", f"market={row.get('market_group')}",
        f"direction={row.get('direction')}", f"source={row.get('source')}", f"book={row.get('book')}",
    ):
        vec[len(NUMERIC_FEATURES) + _hash_index(token)] += 1.0
    return vec


def _sigmoid(z: float) -> float:
    z = max(-35.0, min(35.0, z))
    return 1.0 / (1.0 + math.exp(-z))


def _metrics(y: Sequence[int], p: Sequence[float]) -> Dict[str, float]:
    if not y:
        return {"brier": 1.0, "logloss": 9.0, "calibration_error": 1.0}
    probs = [_clip(x) for x in p]
    brier = sum((a - b) ** 2 for a, b in zip(probs, y)) / len(y)
    logloss = -sum(t * math.log(q) + (1 - t) * math.log(1 - q) for t, q in zip(y, probs)) / len(y)
    bins: Dict[int, List[Tuple[float, int]]] = {}
    for q, t in zip(probs, y): bins.setdefault(min(9, int(q * 10)), []).append((q, t))
    ece = sum(len(v) / len(y) * abs(sum(q for q, _ in v) / len(v) - sum(t for _, t in v) / len(v)) for v in bins.values())
    return {"brier": round(brier, 6), "logloss": round(logloss, 6), "calibration_error": round(ece, 6)}


def _serialise_model(pipe: Any, calibrator: Any, metrics: Dict[str, float], n: int) -> Dict[str, Any]:
    scaler = pipe.named_steps["scale"]
    model = pipe.named_steps["model"]
    cal_model = calibrator.named_steps["model"] if calibrator is not None else None
    return {
        "n_samples": n, "dimension": DIM, "numeric_features": list(NUMERIC_FEATURES), "hash_bins": N_HASH,
        "mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(),
        "coef": model.coef_[0].tolist(), "intercept": float(model.intercept_[0]),
        "calibration_coef": float(cal_model.coef_[0][0]) if cal_model is not None else 1.0,
        "calibration_intercept": float(cal_model.intercept_[0]) if cal_model is not None else 0.0,
        "metrics": metrics, "trained_at": datetime.now(timezone.utc).isoformat(),
    }


def _fit_candidate(rows: List[Dict[str, Any]], folds: int = 5) -> Optional[Dict[str, Any]]:
    if len(rows) < 30 or len({r["y"] for r in rows}) < 2:
        return None
    try:
        import numpy as np
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
    except Exception as exc:
        print(f"AutoML skipped: sklearn unavailable: {exc}")
        return None

    X = np.asarray([_vector(r) for r in rows], dtype=float)
    y = np.asarray([r["y"] for r in rows], dtype=int)
    n = len(rows)
    test_size = max(8, n // (folds + 2))
    starts = list(range(max(20, n - folds * test_size), n, test_size))
    oof_y: List[int] = []
    oof_raw: List[float] = []
    for start in starts:
        end = min(n, start + test_size)
        if start < 20 or end <= start or len(set(y[:start])) < 2:
            continue
        pipe = Pipeline([("scale", StandardScaler()), ("model", LogisticRegression(max_iter=1200, C=0.35, class_weight="balanced"))])
        pipe.fit(X[:start], y[:start])
        pred = pipe.predict_proba(X[start:end])[:, 1]
        oof_y.extend(y[start:end].tolist()); oof_raw.extend(pred.tolist())
    if len(oof_y) < 15 or len(set(oof_y)) < 2:
        return None

    # Platt calibrator trained only on chronological out-of-fold predictions.
    logits = np.asarray([[math.log(_clip(p) / (1 - _clip(p)))] for p in oof_raw], dtype=float)
    calibrator = Pipeline([("model", LogisticRegression(max_iter=600, C=0.5))])
    calibrator.fit(logits, np.asarray(oof_y))
    calibrated = calibrator.predict_proba(logits)[:, 1].tolist()
    candidate_metrics = _metrics(oof_y, calibrated)
    baseline = [1.0 / rows[i]["odds"] for i in range(n - len(oof_y), n)]
    if len(baseline) != len(oof_y): baseline = [0.5] * len(oof_y)
    candidate_metrics["baseline_brier"] = _metrics(oof_y, baseline)["brier"]

    final_pipe = Pipeline([("scale", StandardScaler()), ("model", LogisticRegression(max_iter=1200, C=0.35, class_weight="balanced"))])
    final_pipe.fit(X, y)
    return _serialise_model(final_pipe, calibrator, candidate_metrics, n)


def _groups(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = {"global": rows}
    for row in rows:
        groups.setdefault(f"sport:{row['sport']}", []).append(row)
        groups.setdefault(f"market:{row['sport']}:{row['market_group']}", []).append(row)
    return groups


def train_and_promote() -> Dict[str, Any]:
    rows = load_training_rows()
    old = safe_json_load(MODEL_FILE, {}) or {}
    old_models = old.get("models", {}) if isinstance(old, dict) else {}
    models = dict(old_models)
    report: Dict[str, Any] = {"rows": len(rows), "trained_at": datetime.now(timezone.utc).isoformat(), "groups": {}}

    for key, group_rows in _groups(rows).items():
        minimum = MIN_GLOBAL if key == "global" else MIN_GROUP
        if len(group_rows) < minimum:
            report["groups"][key] = {"status": "insufficient", "n": len(group_rows)}
            continue
        candidate = _fit_candidate(group_rows)
        if not candidate:
            report["groups"][key] = {"status": "not_trainable", "n": len(group_rows)}
            continue
        cm = candidate["metrics"]
        old_brier = float(((old_models.get(key) or {}).get("metrics") or {}).get("brier", 99))
        baseline_brier = float(cm.get("baseline_brier", 99))
        improves_market = cm["brier"] <= baseline_brier - 0.001
        improves_champion = old_brier == 99 or cm["brier"] <= old_brier - 0.0005
        status = "promoted" if improves_market and improves_champion else "rejected"
        if status == "promoted":
            models[key] = candidate
        report["groups"][key] = {"status": status, "n": len(group_rows), **cm, "old_brier": old_brier}

    payload = {
        "version": 2, "updated_at": datetime.now(timezone.utc).isoformat(),
        "training_rows": len(rows), "models": models, "last_report": report,
    }
    safe_json_write(MODEL_FILE, payload)
    safe_json_write("prop_hunter_autolearn_report.json", report)
    print(f"AutoML: rows={len(rows)} champions={len(models)}")
    for key, info in report["groups"].items():
        if info.get("status") in {"promoted", "rejected"}:
            print(f"  {key}: {info['status']} n={info['n']} brier={info.get('brier')} baseline={info.get('baseline_brier')}")
    return report


def _predict_model(model: Dict[str, Any], vec: Sequence[float]) -> Optional[float]:
    try:
        mean, scale, coef = model["mean"], model["scale"], model["coef"]
        if not (len(vec) == len(mean) == len(scale) == len(coef)):
            return None
        z = float(model["intercept"])
        for x, m, s, c in zip(vec, mean, scale, coef):
            z += ((float(x) - float(m)) / (float(s) if abs(float(s)) > 1e-12 else 1.0)) * float(c)
        raw = _sigmoid(z)
        logit = math.log(_clip(raw) / (1 - _clip(raw)))
        calibrated = _sigmoid(float(model.get("calibration_intercept", 0)) + float(model.get("calibration_coef", 1)) * logit)
        return _clip(calibrated, 0.02, 0.98)
    except Exception:
        return None


def predict_probability(data: Dict[str, Any]) -> Optional[float]:
    registry = safe_json_load(MODEL_FILE, {}) or {}
    models = registry.get("models", {}) if isinstance(registry, dict) else {}
    odds = to_float(data.get("odds") or data.get("odds_decimal"))
    if not odds or odds <= 1:
        return None
    row = {
        "sport": str(data.get("sport") or data.get("league") or "UNKNOWN").upper(),
        "market": str(data.get("market") or data.get("market_key") or "other"),
        "market_group": _market_group(data.get("market") or data.get("market_key")),
        "direction": str(data.get("direction") or "over").lower(),
        "source": str(data.get("source") or "unknown").lower(),
        "book": str(data.get("bookmaker") or data.get("book") or data.get("source") or "unknown").lower(),
        "odds": odds, "line": to_float(data.get("line") or data.get("point"), 0.0) or 0.0,
        "edge": (to_float(data.get("edge_pct") or data.get("edge"), 0.0) or 0.0) / 100.0,
        "stake": to_float(data.get("stake"), 0.0) or 0.0,
        "confidence": (to_float(data.get("confidence"), 0.0) or 0.0) / 100.0,
    }
    features = data.get("features") if isinstance(data.get("features"), dict) else {}
    for key in ("hit_l5", "hit_l10", "hit_l20", "avg_l5", "avg_l10", "line_vs_avg", "source_trust", "book_consensus", "line_move", "rest_days", "minutes"):
        row[key] = to_float(data.get(key) if data.get(key) is not None else features.get(key), 0.0) or 0.0
    keys = [f"market:{row['sport']}:{row['market_group']}", f"sport:{row['sport']}", "global"]
    preds = []
    weights = []
    for rank, key in enumerate(keys):
        model = models.get(key)
        if not model: continue
        pred = _predict_model(model, _vector(row))
        if pred is not None:
            preds.append(pred); weights.append(3 - rank)
    if not preds:
        return None
    return sum(p * w for p, w in zip(preds, weights)) / sum(weights)


def predict_pick_probability(pick: Any, sport_label: str) -> Optional[float]:
    data = pick.model_dump() if hasattr(pick, "model_dump") else dict(pick)
    data["sport"] = sport_label
    return predict_probability(data)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true")
    args = parser.parse_args()
    if args.train:
        train_and_promote()
    else:
        print(json.dumps(safe_json_load(MODEL_FILE, {}), indent=2)[:4000])


if __name__ == "__main__":
    main()
