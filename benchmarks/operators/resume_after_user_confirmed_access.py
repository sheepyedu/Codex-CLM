"""User-requested continuation with unchanged native SDK and safety enforcement.

This never reclassifies cyber_policy as temporary. A renewed policy refusal ends
the run. The immutable original refusal and current native histories are retained.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone

sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parent
PINNED = BASE / 'source-environment-v5'
sys.path[:0] = [str(PINNED / 'benchmarks/workbuddy'), str(PINNED / 'benchmarks'),
               str(PINNED), str(BASE / 'framework')]
import run
from checkpoint import restore_context
from clm.context import write_json
from continue_workbuddy_transport import resilient_trial, instance_key


def validate(old, target, assertion):
    frozen = run.read(old / 'plan.json')
    progress = run.read(old / 'progress.json')
    approval = run.read(assertion)
    if (len(frozen['tasks']) != 65 or len(progress) != 121
            or sum(r.get('accepted') is True for r in progress) != 120
            or progress[-1].get('accepted') or progress[-1]['arm'] != 'native'
            or progress[-1]['row']['position'] != 61):
        raise ValueError('Expected original120 accepted trials and one failed native61')
    if frozen['code_sha256'] != run.code_sha() or frozen['runtime_sha256'] != run.runtime_sha():
        raise ValueError('Frozen runtime changed')
    if (approval.get('user_confirmation') != '已取得确认，我补充说明'
            or not approval.get('current_account_and_existing_batch_confirmed_by_user')
            or approval.get('service') != 'gpt'
            or approval.get('base_url') != 'https://cn.affordablerouter.com/v1'
            or approval.get('model') != 'gpt-6.1-sol'):
        raise ValueError('Missing applicable user-confirmed access assertion')
    actual = run.read(Path('/mount-data/Tools/services.json'))['services']['gpt']
    if actual['base_url'] != approval['base_url']:
        raise ValueError('Configured endpoint differs from the user-confirmed scope')
    if target.exists():
        raise ValueError('Never overwrite an earlier run')
    original = old / 'native/evidence' / instance_key(progress[-1]['row'])
    checkpoint = run.read(original / 'checkpoint/receipt.json')
    if (run.sha(original / 'checkpoint/receipt.json') != 'd4340a67f045e9c81a9eee26f2e42ea592ca4608e18196b7f0b77630b443cf95'
            or checkpoint['row'] != progress[-1]['row']
            or checkpoint['thread'] != '01a1ef4b-a2b1-7d60-9728-0039856c7099'):
        raise ValueError('Original failed task or native thread changed')
    return frozen, progress, checkpoint


def require_completed(root, receipt):
    if not receipt['accepted']:
        return
    events = root / receipt['arm'] / 'trials' / receipt['trial_name'] / 'agent/native.jsonl'
    completed = []
    for line in events.open():
        event = json.loads(line).get('data') or {}
        if event.get('method') == 'turn/completed':
            completed.append(event.get('params') or {})
    native = receipt['native']
    matches = [r for r in completed if (r.get('turn') or {}).get('id') == native.get('turn')]
    if (len(matches) != 1 or matches[0].get('threadId') != receipt['thread']
            or matches[0]['turn'].get('status') != 'completed' or matches[0]['turn'].get('error')):
        raise ValueError('A successful process alone is not a completed native turn')


async def execute(old, target, assertion, dry_run):
    frozen, prior, saved = validate(old, target, assertion)
    if dry_run:
        print(json.dumps({'qualified': True, 'accepted_prefix': 120, 'next': 'native61',
            'model_api_calls': 0, 'native_sdk_and_safety_metadata_unchanged': True}), flush=True)
        return
    target.mkdir(mode=0o700)
    shutil.copy2(old / 'offline.yaml', target / 'offline.yaml')
    for arm in run.ARMS:
        shutil.copytree(old / arm, target / arm, symlinks=True)
    failed = target / 'native/evidence' / instance_key(prior[-1]['row'])
    archive = target / 'native/failed-attempts' / instance_key(prior[-1]['row']) / 'source-formal-65-policy'
    archive.parent.mkdir(parents=True, exist_ok=True)
    failed.rename(archive)
    saved['artifacts'] = str(archive / 'checkpoint/artifacts')
    saved['archive'] = str(archive / 'checkpoint/image.tar')
    intent = {'source': str(old), 'user_assertion': run.read(assertion),
        'user_assertion_sha256': run.sha(assertion), 'controller_sha256': run.sha(Path(__file__)),
        'original_refusal_retained': True, 'manual_initial_attempts': 1,
        'cyber_policy_remains_non_temporary': True, 'native_sdk_and_safety_metadata_unchanged': True,
        'started_at': datetime.now(timezone.utc).isoformat()}
    frozen = {**frozen, 'user_requested_access_continuation': intent}
    write_json(target / 'plan.json', frozen)
    write_json(target / 'recovery.json', {'checkpoint': saved, **intent})
    receipts, previous = [], {}
    for row in frozen['tasks'][:60]:
        for arm in run.ARMS:
            record = run.read(target / arm / 'evidence' / instance_key(row) / 'receipt.json')
            if not record['accepted'] or record['row'] != row:
                raise ValueError('Accepted prefix changed')
            snapshot = target / arm / 'evidence' / instance_key(row) / 'native-session.jsonl'
            if run.sha(snapshot) != record['session_sha256']:
                raise ValueError('Accepted native snapshot changed')
            previous[arm] = record
            receipts.append(record)
    write_json(target / 'progress.json', [{k:v for k,v in r.items() if k != 'wire'} for r in receipts])
    context = restore_context(target / 'clm/context', target / 'clm')
    key, base_url = run.provider()
    sequence = [(r, a) for r in frozen['tasks'][60:] for a in run.ARMS]
    for index, (row, arm) in enumerate(sequence):
        print(f'START {row["position"]:03d} {arm} {row["task"]}', flush=True)
        if index == 0:
            # An explicit user-requested new attempt; never an automatic retry of
            # a permanent error, and never a modification of SDK safety metadata.
            receipt = await run.one_trial(target, frozen, row, arm, previous[arm], key, base_url,
                None, recovery={'checkpoint': saved, 'failed_evidence': str(archive),
                                'user_access_assertion': str(assertion)}, attempt=1)
        else:
            receipt = await resilient_trial(target, frozen, row, arm, previous[arm], key, base_url,
                                            context if arm == 'clm' else None)
        require_completed(target, receipt)
        receipts.append(receipt)
        write_json(target / 'progress.json', [{k:v for k,v in r.items() if k != 'wire'} for r in receipts])
        if not receipt['accepted']:
            write_json(target / 'HALTED.json', {'position': row['position'], 'arm': arm,
                'automatic_policy_retry': False, 'original_failure_and_new_attempt_retained': True})
            raise RuntimeError(f'Continuation stopped at {row["position"]} {arm}; no policy bypass')
        previous[arm] = receipt
    write_json(target / 'accepted.json', {'pairs':65, 'stage':'formal',
        'code_sha256':frozen['code_sha256'], 'runtime_sha256':frozen['runtime_sha256'],
        'plan_sha256':run.sha(target / 'plan.json'),
        'threads':{a:r['thread'] for a,r in previous.items()}})


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('old',type=Path)
    parser.add_argument('target',type=Path)
    parser.add_argument('assertion',type=Path)
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    asyncio.run(execute(args.old.resolve(),args.target.resolve(),args.assertion.resolve(),args.dry_run))
