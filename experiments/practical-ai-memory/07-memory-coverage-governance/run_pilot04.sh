#!/usr/bin/env bash
# Pilot-04: 5 tasks x 3 conditions x 1 repeat = 15 cells, deepseek-v4-flash (max).
# Runs serially; stops on first non-zero exit. Metadata JSONs printed per cell.
set -uo pipefail
cd "$(dirname "$0")"

TASKS=(coverage-gap review-due governance-queue scope-slice source-trace)
CONDITIONS=(source-only state-projection coverage-governance-projection)
LABEL=pilot-04-deepseek

fail=0
for task in "${TASKS[@]}"; do
  for cond in "${CONDITIONS[@]}"; do
    out="runs/private/macos/${LABEL}-${task}-${cond}/metadata.json"
    if [ -f "$out" ] && python3 -c "
import json,sys
m=json.load(open('$out'))
sys.exit(0 if m.get('exit_code')==0 and m.get('runtime_tool_access_calls')==0 and m.get('protocol_environment_isolated') else 1)
" 2>/dev/null; then
      echo "SKIP ${task}/${cond} (already complete)"
      continue
    fi
    python3 run_experiment.py "$cond" \
      --label "$LABEL" --task "$task" \
      --model deepseek-v4-flash --reasoning-effort max \
      --platform-tag macos > /tmp/cell.json 2>&1
    rc=$?
    if [ $rc -ne 0 ]; then
      echo "FAIL ${task}/${cond} rc=${rc}"
      python3 -c "
import json,sys
m=json.load(open('/tmp/cell.json'))
print('exit_code:',m.get('exit_code'),'access:',m.get('runtime_tool_access_calls'),'iso:',m.get('protocol_environment_isolated'))
" 2>/dev/null || cat /tmp/cell.json | head -5
      fail=1
      break 2
    fi
    echo "OK ${task}/${cond} -> $out"
  done
done
echo "PILOT_DONE fail=${fail}"
exit $fail
