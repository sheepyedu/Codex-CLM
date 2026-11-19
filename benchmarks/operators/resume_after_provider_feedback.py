"""Explicit user feedback retry; preserve SDK enforcement and accumulated history."""
import argparse,asyncio,json,shutil,sys
from pathlib import Path
from datetime import datetime,timezone

sys.dont_write_bytecode=True
BASE=Path(__file__).resolve().parent
SOURCE=BASE/'source-environment-v6'
sys.path[:0]=[str(SOURCE/'benchmarks/workbuddy'),str(SOURCE/'benchmarks'),str(SOURCE),str(BASE/'framework')]
import run
from checkpoint import restore_context
from clm.context import write_json
from continue_workbuddy_transport import resilient_trial,instance_key,eligible_checkpoint,validate_upgrade

def completed(root,receipt):
    if not receipt['accepted']:return
    events=root/receipt['arm']/'trials'/receipt['trial_name']/'agent/native.jsonl'
    matches=[]
    for line in events.open():
        e=json.loads(line).get('data') or {}
        p=e.get('params') or {}
        if e.get('method')=='turn/completed' and (p.get('turn') or {}).get('id')==receipt['native'].get('turn'):
            matches.append(p)
    if len(matches)!=1 or matches[0].get('threadId')!=receipt['thread'] or matches[0]['turn'].get('status')!='completed' or matches[0]['turn'].get('error'):
        raise ValueError('Missing successful native turn completion')

def validate(old,target,request):
    frozen=run.read(old/'plan.json');progress=run.read(old/'progress.json');user=run.read(request)
    ordered=[(r,a) for r in frozen['tasks'] for a in run.ARMS]
    assert len(frozen['tasks'])==65 and len(progress)==122
    assert all(r['accepted'] for r in progress[:-1]) and not progress[-1]['accepted']
    assert [(r['row'],r['arm']) for r in progress]==ordered[:122]
    assert progress[-1]['arm']=='clm' and progress[-1]['row']['position']==61
    assert (old/'controller.exit').read_text().strip()=='1' and not target.exists()
    assert frozen['code_sha256']==run.code_sha() and frozen['runtime_sha256']==run.runtime_sha()
    validate_upgrade(BASE,old,BASE/'pilot-07',BASE/'transport-v6-check-01')
    assert user['user_request']=='继续尝试重试，我已经提交了问题反馈'
    assert user['feedback_submitted_by_user'] and user['goal_cleared_by_user']
    assert user['model']=='gpt-6.1-sol' and user['provider_resolution_independently_confirmed'] is False
    endpoint=run.read(Path('/mount-data/Tools/services.json'))['services']['gpt']['base_url']
    assert endpoint=='https://cn.affordablerouter.com/v1'
    failed=old/'clm/evidence'/instance_key(progress[-1]['row'])
    receipt=run.read(failed/'receipt.json');saved=run.read(failed/'checkpoint/receipt.json')
    assert eligible_checkpoint(failed,receipt) is None,'Policy must remain ineligible for automatic retry'
    assert saved['row']==receipt['row'] and saved['thread']==receipt['thread']=='01a1ef4f-5341-76e3-88d4-2bfc9655ff96'
    assert run.sha(failed/'checkpoint/receipt.json')=='516af30c690b106b524b6b7cea3dadc1257df9ee3fb3872453e6b87364a7e50f'
    assert receipt['native']['protective_compaction']['saw_compaction']
    pressure=receipt['wire']
    assert pressure['final_raw_input_bytes']<run.COMPACT_BYTES and pressure['last_input_tokens']<run.COMPACT_TOKENS
    for a in run.ARMS:
        last=next(r for r in reversed(progress) if r['arm']==a)
        home=old/a/'home/codex/sessions'
        paths=list(home.rglob('*'+last['thread']+'.jsonl'))
        assert len(paths)==1 and run.sha(paths[0])==last['session_sha256'],'Current history changed'
    completed(old,progress[-2])
    return frozen,progress,receipt,saved

async def main(old,target,request,dry):
    frozen,prior,last,saved=validate(old,target,request)
    if dry:
        print(json.dumps({'qualified':True,'accepted_prefix':121,'first_retry':'061-clm',
            'uses_current_failed_history':True,'extra_pre_task_compaction':False,
            'policy_remains_nonretryable':True,'model_api_calls':0}),flush=True);return
    target.mkdir(mode=0o700)
    shutil.copy2(old/'offline.yaml',target/'offline.yaml')
    for a in run.ARMS:shutil.copytree(old/a,target/a,symlinks=True)
    failed=target/'clm/evidence'/instance_key(last['row'])
    archive=target/'clm/failed-attempts'/instance_key(last['row'])/'source-formal-67-policy'
    archive.parent.mkdir(parents=True,exist_ok=True);failed.rename(archive)
    saved={**saved,'artifacts':str(archive/'checkpoint/artifacts'),'archive':str(archive/'checkpoint/image.tar')}
    intent={'source':str(old),'user_request':run.read(request),'user_request_sha256':run.sha(request),
        'controller_sha256':run.sha(Path(__file__)),'started_at':datetime.now(timezone.utc).isoformat(),
        'native_sdk_safety_metadata_unchanged':True,'permanent_failure_classification_unchanged':True,
        'failed_history_and_original_compaction_preserved':True,'new_goal_created':False}
    frozen={**frozen,'user_feedback_retry':intent};write_json(target/'plan.json',frozen)
    write_json(target/'recovery.json',{'checkpoint':saved,**intent})
    receipts=[];previous={}
    for r in prior[:-1]:
        p=target/r['arm']/'evidence'/instance_key(r['row'])
        actual=run.read(p/'receipt.json')
        assert actual['accepted'] and actual['row']==r['row'] and run.sha(p/'native-session.jsonl')==actual['session_sha256']
        receipts.append(actual);previous[r['arm']]=actual
    write_json(target/'progress.json',[{k:v for k,v in r.items() if k!='wire'} for r in receipts])
    context=restore_context(target/'clm/context',target/'clm')
    key,endpoint=run.provider()
    ordered=[(r,a) for r in frozen['tasks'] for a in run.ARMS]
    for i,(row,a) in enumerate(ordered[len(receipts):]):
        print(f'START {row["position"]:03d} {a} {row["task"]}',flush=True)
        # Use the actual latest failed receipt for pressure/thread bookkeeping.
        # It includes the successful native compaction; no history is removed.
        prev=last if i==0 else previous[a]
        initial={'checkpoint':saved,'failed_evidence':str(archive),'explicit_user_feedback_retry':str(request)} if i==0 else None
        receipt=await resilient_trial(target,frozen,row,a,prev,key,endpoint,context if a=='clm' else None,initial=initial)
        completed(target,receipt)
        receipts.append(receipt)
        write_json(target/'progress.json',[{k:v for k,v in r.items() if k!='wire'} for r in receipts])
        if not receipt['accepted']:
            write_json(target/'HALTED.json',{'position':row['position'],'arm':a,'policy_automatic_retry':False})
            raise RuntimeError(f'Continuation halted at {row["position"]} {a}')
        previous[a]=receipt
    write_json(target/'accepted.json',{'pairs':65,'stage':'formal','code_sha256':frozen['code_sha256'],
        'runtime_sha256':frozen['runtime_sha256'],'plan_sha256':run.sha(target/'plan.json'),
        'threads':{a:r['thread'] for a,r in previous.items()}})

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ['old','target','request']:p.add_argument(name,type=Path)
    p.add_argument('--dry-run',action='store_true');a=p.parse_args()
    asyncio.run(main(a.old.resolve(),a.target.resolve(),a.request.resolve(),a.dry_run))
