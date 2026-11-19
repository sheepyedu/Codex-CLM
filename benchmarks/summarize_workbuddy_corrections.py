"""Recompute bounded, confirmed corrections without changing frozen official scores.

Usage: python3 benchmarks/summarize_workbuddy_corrections.py INPUT_JSON OUTPUT_DIR
Input includes all original scores, Web penalties, declared correction IDs and
Office counts. Evidence SHA256 values bind it to the separately shared full audit.
No network, model calls, or actor execution.
"""
import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


def summarize(rows, field):
    result = {}
    for domain in ['code', 'office', 'sec', 'web', 'all']:
        arms = {}
        for arm in ['native', 'clm']:
            selected = [r for r in rows if r['arm'] == arm and (domain == 'all' or r['domain'] == domain)]
            values = [r[field] for r in selected]
            arms[arm] = {'n': len(values), 'mean': sum(values) / len(values),
                         'full': sum(v == 1 for v in values), 'zero': sum(v == 0 for v in values),
                         'partial': sum(0 < v < 1 for v in values)}
        arms['gap_clm_minus_native'] = arms['clm']['mean'] - arms['native']['mean']
        result[domain] = arms
    return result


def main(source, output):
    data = json.loads(source.read_text())
    raw = data['rows']
    keys = [(r['position'], r['arm']) for r in raw]
    assert len(keys) == len(set(keys)) == 130
    assert set(keys) == {(p, a) for p in range(1, 66) for a in ['native', 'clm']}
    assert Counter(r['domain'] for r in raw) == {'code': 40, 'office': 24, 'sec': 30, 'web': 36}
    rows = []
    for r in raw:
        v = r['reward']
        assert 0 <= v <= 1
        rule = v
        ids = set(r['correct_rule_ids'])
        if r['domain'] == 'web':
            failed = {i['id']: i for i in r['items'] if i['status'] != 'pass'}
            assert ids <= failed.keys()
            assert round(max(0, 1 - sum(i['penalty'] for i in failed.values())), 4) == v
            rule = round(max(0, 1 - sum(i['penalty'] for k, i in failed.items() if k not in ids)), 4)
        else:
            assert not ids
        corrected = rule
        changes = ['web:' + k for k in sorted(ids)]
        if r['position'] == 54:
            assert r['domain'] == 'office' and r['canonical_total'] == 2151
            assert (r['tests_passed'], r['tests_total']) == ((214, 293) if r['arm'] == 'native' else (1363, 1888))
            corrected = r['tests_passed'] / 2151
            changes.append('office54:fixed2151;missing_checks_fail')
        if r['position'] == 49:
            assert r['domain'] == 'office' and r['tests_total'] == 134 and r['exclude_environment_checks'] == 5
            assert r['tests_passed'] == (76 if r['arm'] == 'native' else 79)
            corrected = r['tests_passed'] / 129
            changes.append('office49:exclude5_unprovided_protected_fixture_checks')
        rows.append({k: r[k] for k in ['position', 'arm', 'domain', 'task']} |
                    {'original': v, 'web_rule_only': rule, 'corrected': corrected, 'changes': ';'.join(changes)})
    assert sum(len(r['correct_rule_ids']) for r in raw) == 10
    assert sum(r['original'] != r['web_rule_only'] for r in rows) == 7
    assert sum(r['original'] != r['corrected'] for r in rows) == 11
    paired = {p: {r['arm']: r for r in rows if r['position'] == p} for p in range(1, 66)}
    outcomes = Counter('win' if p['clm']['corrected'] > p['native']['corrected'] else
                       'loss' if p['clm']['corrected'] < p['native']['corrected'] else 'tie' for p in paired.values())
    summary = {'protocol': data['protocol'], 'input_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
               'source_sha256': data['source_sha256'], 'model_calls_added': 0,
               'official_scores_overwritten': False, 'complete_fair_regrade': False,
               'corrected_score_records': 11, 'affected_tasks': 7, 'changed_score_tasks': 6,
               'clm_paired_outcomes': dict(outcomes),
               'original': summarize(rows, 'original'), 'web_rule_only': summarize(rows, 'web_rule_only'),
               'corrected': summarize(rows, 'corrected'),
               'pending': ['Office20/31 also have output-dependent denominators; canonical universes not yet verified.',
                           'Missing-view LLM judgments have not been rerun; no automatic pass assigned.',
                           'Code6 API contract ambiguity and Web42 breadcrumb overconstraint are disclosed, not adjusted.',
                           'New no-pre-task-compaction policy has not been benchmarked; this is the old guarded run.']}
    output.mkdir(parents=True, exist_ok=True)
    (output/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    with (output/'paired.csv').open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n'); w.writeheader(); w.writerows(rows)
    print(json.dumps({'corrected': summary['corrected'], 'outcomes': dict(outcomes)}, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', type=Path); p.add_argument('output', type=Path)
    a = p.parse_args(); main(a.input, a.output)
