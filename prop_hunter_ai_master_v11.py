prop_hunter_ai_master_v11.pyimport subprocess, sys
from pathlib import Path
SCRIPTS=["prop_hunter_source_audit.py","prop_hunter_odds_oddsapi_io.py","prop_hunter_odds_sportsgameodds.py","prop_hunter_odds_opticodds.py","prop_hunter_results_nba.py","prop_hunter_results_wnba.py","prop_hunter_results_nfl.py","prop_hunter_results_mlb.py","espn_multisport_results.py","prop_hunter_feature_builder.py","prop_hunter_settler.py","prop_hunter_clv_engine.py","prop_hunter_learning_update.py","prop_hunter_social_signals.py","prop_hunter_github_source_scanner.py","prop_hunter_source_reliability.py"]
def main():
    warnings=0
    for s in SCRIPTS:
        if not Path(s).exists():
            print("SKIP",s,flush=True); continue
        print("="*50,flush=True); print("RUN",s,flush=True)
        rc=subprocess.run([sys.executable,s]).returncode
        if rc: warnings+=1; print("WARNING",s,rc,flush=True)
    print("="*50,flush=True); print("AI MASTER V11 done warnings=",warnings,flush=True)
if __name__=="__main__": main()
