"""Actual timeout fixture plus full existing zero-model recovery qualification."""
import asyncio
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parent
SOURCE = BASE / 'source-environment-v6'
sys.path[:0] = [str(SOURCE / 'benchmarks/workbuddy'), str(SOURCE / 'benchmarks'),
               str(SOURCE), str(BASE / 'framework')]
import run
import check_workbuddy_recovery as check
from clm.context import write_json
from continue_workbuddy_transport import eligible_checkpoint
from relay import temporary_provider_failure


async def main():
    output = BASE / 'transport-v6-check-01'
    await check.main(BASE, output)
    failed = BASE / 'formal-66/native/evidence/061-sec-bb-bin-int-length-005'
    policy = BASE / 'formal-65/native/evidence/061-sec-bb-bin-int-length-005'
    failure = failed / 'wire/00015/response.raw'
    original_policy = policy / 'wire/00001/response.raw'
    success = failed / 'wire/00014/response.raw'
    assert temporary_provider_failure(failure)
    assert not temporary_provider_failure(original_policy)
    retry = check.transport_check(failure.read_bytes(), success.read_bytes(), True)
    suppressed = check.transport_check(failure.read_bytes(), success.read_bytes(), False)
    assert eligible_checkpoint(failed, run.read(failed / 'receipt.json')) == run.read(failed / 'checkpoint/receipt.json')
    assert eligible_checkpoint(policy, run.read(policy / 'receipt.json')) is None
    synthetic = output / 'policy-with-timeout-words.raw'
    synthetic.write_text('data: ' + json.dumps({'type':'response.failed','response':{'error':{
        'code':'cyber_policy','message':'Upstream response stream timed out; policy denied'}}}) + '\n\n')
    assert not temporary_provider_failure(synthetic)
    proof = run.read(output / 'RESULT.json')
    proof.update(actual_upstream_timeout_retry=retry, actual_upstream_timeout_suppressed=suppressed,
                 original_cyber_policy_not_retryable=True, policy_with_timeout_words_not_retryable=True,
                 actual_new_checkpoint_eligible=True, original_policy_checkpoint_not_eligible=True,
                 actual_failure_sha256=run.sha(failure), original_policy_sha256=run.sha(original_policy),
                 safety_metadata_modified=False, model_api_calls=0)
    write_json(output / 'RESULT.json', proof)
    print(json.dumps({'qualification_complete':True,'actual_timeout_retry':retry,
        'actual_timeout_suppressed':suppressed,'original_policy_still_nonretryable':True,
        'model_api_calls':0}), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
