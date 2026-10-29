#!/usr/bin/env python3
"""Daily static control and safe auto-repair for every PROP HUNTER workflow.

This script is intentionally conservative: it auto-fixes only deterministic
configuration drift (runtime-version pins and git-push race protection). It
never edits betting logic, secrets, model state or source data.
"""
from __future__ import annotations
import argparse,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent;WF_DIR=ROOT/'.github'/'workflows';RUNTIME_FILE=ROOT/'prophunter.py'
_RUNTIME_RE=re.compile(r"PH_RUNTIME_VERSION\s*=\s*['\"]([^'\"]+)['\"]");_EXPECTED_RE=re.compile(r"(PH_EXPECTED_RUNTIME_VERSION:\s*)([^\s#]+)");_PY_REF_RE=re.compile(r"(?:^|[\s;|&])python(?:3)?\s+(?!-)([A-Za-z0-9_./-]+\.py)\b",re.M);_REQ_REF_RE=re.compile(r"pip\s+install[^\n]*?-r\s+([A-Za-z0-9_./-]+)");_MERGE_MARKERS=("<<<<<<<","=======",">>>>>>>")
ALL_SPORT_RESULT_CMDS=(
 'prop_hunter_results_mlb.py','prop_hunter_results_mlb_extras.py','prop_hunter_results_nba.py','prop_hunter_results_wnba.py','prop_hunter_results_nfl.py','prop_hunter_results_nhl.py','prop_hunter_results_ncaa.py','prop_hunter_results_euroleague.py','prop_hunter_settler.py','prop_hunter_settler_extras.py')

def runtime_version():
 text=RUNTIME_FILE.read_text(encoding='utf-8');m=_RUNTIME_RE.search(text)
 if not m:raise RuntimeError('PH_RUNTIME_VERSION not found in prophunter.py')
 return m.group(1)
def workflow_paths():return sorted([*WF_DIR.glob('*.yml'),*WF_DIR.glob('*.yaml')]) if WF_DIR.exists() else []
def _insert_pull_before_git_add(text):
 if 'git push' not in text or 'git pull --rebase' in text:return text,False
 lines=text.splitlines()
 for i,line in enumerate(lines):
  if re.search(r'\bgit\s+add\b',line):
   indent=line[:len(line)-len(line.lstrip())];lines.insert(i,f'{indent}git pull --rebase --autostash origin main');return '\n'.join(lines)+('\n' if text.endswith('\n') else ''),True
 return text,False
def safe_fix(path,runtime):
 text=path.read_text(encoding='utf-8');changed=[];new=_EXPECTED_RE.sub(lambda m:m.group(1)+runtime,text)
 if new!=text:text=new;changed.append('runtime-pin')
 text2,repaired=_insert_pull_before_git_add(text)
 if repaired:text=text2;changed.append('git-push-race')
 if changed:path.write_text(text,encoding='utf-8')
 return changed
def _require_commands(errors,text,commands,label):
 for cmd in commands:
  if cmd not in text:errors.append(f'{label} missing: {cmd}')
def inspect_workflow(path,runtime):
 text=path.read_text(encoding='utf-8');errors=[]
 if any(re.match(r"^(<<<<<<< |=======\s*$|>>>>>>> )", line) for line in text.splitlines()):errors.append('merge-conflict marker')
 for marker in ('name:','jobs:','runs-on:','timeout-minutes:'):
  if marker not in text:errors.append(f'missing {marker}')
 if not re.search(r'(?m)^\s*(?:"on"|on):\s*$',text):errors.append('missing on trigger')
 if 'git push' in text and 'git pull --rebase' not in text:errors.append('git push without rebase protection')
 if 'PH_EXPECTED_RUNTIME_VERSION:' in text and runtime not in text:errors.append('stale runtime pin')
 if path.name=='prophunter.yml':
  if "PH_BROWSER_ENABLED: '0'" not in text:errors.append('normal card browser gate missing')
  if 'python prop_hunter_runtime_guard.py' not in text:errors.append('normal card runtime guard missing')
  for sport in ('MLB','NBA','WNBA','NFL','NHL','NCAAB','NCAAF','EUROLEAGUE'):
   if sport not in text:errors.append(f'normal card sport missing: {sport}')
 if path.name=='prophunter_results.yml':
  _require_commands(errors,text,ALL_SPORT_RESULT_CMDS,'results all-sports settlement')
  for cmd in ('prop_hunter_learning_update.py','prop_hunter_feature_builder.py','prop_hunter_expansion_test.py','prop_hunter_euroleague_test.py'):
   if cmd not in text:errors.append(f'results learning/regression missing: {cmd}')
 if path.name=='prop_hunter_maintenance.yml':
  if 'python prop_hunter_hard_test.py' not in text:errors.append('maintenance hard test missing')
  if 'EUROLEAGUE' not in text:errors.append('maintenance EuroLeague source coverage missing')
 if path.name=='prop_hunter_daily_control.yml':
  for cmd in ('python prop_hunter_daily_control.py --fix','python prop_hunter_runtime_guard.py','python prop_hunter_hard_test.py','python prop_hunter_market_regression_test.py','python prop_hunter_expansion_test.py','python prop_hunter_euroleague_test.py'):
   if cmd not in text:errors.append(f'daily control missing: {cmd}')
 for ref in _PY_REF_RE.findall(text):
  if not (ROOT/ref).exists():errors.append(f'missing python target {ref}')
 for ref in _REQ_REF_RE.findall(text):
  if not (ROOT/ref).exists():errors.append(f'missing requirements file {ref}')
 return errors
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--fix',action='store_true');ap.add_argument('--check',action='store_true');args=ap.parse_args();runtime=runtime_version();paths=workflow_paths()
 if not paths:print('DAILY CONTROL FAILED: no workflows found');return 2
 repaired={}
 if args.fix:
  for path in paths:
   changes=safe_fix(path,runtime)
   if changes:repaired[str(path.relative_to(ROOT))]=changes
 failures={}
 for path in workflow_paths():
  errs=inspect_workflow(path,runtime)
  if errs:failures[str(path.relative_to(ROOT))]=errs
 print(f'DAILY CONTROL: runtime={runtime} workflows={len(workflow_paths())}')
 if repaired:
  for path,changes in repaired.items():print(f'DAILY CONTROL FIXED: {path}: {", ".join(changes)}')
 else:print('DAILY CONTROL: no safe repairs needed')
 if failures:
  for path,errs in failures.items():print(f'DAILY CONTROL ERROR: {path}: {"; ".join(errs)}')
  return 1
 print('DAILY CONTROL OK: all workflows structurally consistent');return 0
if __name__=='__main__':raise SystemExit(main())
