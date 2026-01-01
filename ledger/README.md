# Failed Claims Ledger

Append-only record of ideas that did not survive falsification.

## Rules

1. **Append-only** - Entries are never edited or deleted
2. **Non-resurrection** - A failed claim cannot be retried unless its failure mode has been explicitly addressed (new data, new method, new constraint)
3. **No prose** - Entries are structured YAML, not justification essays

## Entry Format

```yaml
id: FC-YYYY-NNN
date: YYYY-MM-DD
project: project_name
claim: >
  The falsifiable claim that was tested
test:
  method: gold_set | benchmark | unit_test | metric_threshold | manual
  dataset: reference to test data (if applicable)
failure_condition: what would constitute failure
result: actual measured result
status: failed
failure_mode:
  - specific reason 1
  - specific reason 2
lesson: one-line insight gained
decision: what action was taken as a result
revisit: conditions under which this could be reconsidered
```

## Why This Exists

- Externalizes memory
- Removes ego from failure
- Turns "wrong" into reusable asset
- Prevents zombie ideas from returning in different costumes
