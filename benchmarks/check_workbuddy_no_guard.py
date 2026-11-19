"""Zero-API regression: serial high-pressure continuation never requests compaction.

Executes the production options builder and native turn driver against an RPC
recorder. Also checks explicit probe support and real native event handling.
Does not claim live provider capacity qualification of a new benchmark chain.
"""
import ast
import importlib.util
import json
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent / 'workbuddy'
THREAD = '01234567-89ab-cdef-0123-456789abcdef'


def main():
    tree = ast.parse((HERE/'run.py').read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'task_options')
    env = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(HERE/'run.py'), 'exec'), env)
    trial = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'one_trial')
    assert any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'task_options' for n in ast.walk(trial))
    spec = importlib.util.spec_from_file_location('native_turn_no_guard', HERE/'native_turn.py')
    native = importlib.util.module_from_spec(spec); spec.loader.exec_module(native)
    OriginalNative = native.Native
    calls = []

    class Recorder:
        def request(self, method, params):
            calls.append((method, params))
            if method in ['thread/resume', 'thread/start']:
                return {'thread': {'id': THREAD, 'path': '/retained/session.jsonl'}}
            if method == 'turn/start':
                return {'turn': {'id': 'turn-1'}}
            return {}
        def send(self, data):
            pass
        def complete(self, thread_id, turn_id=None, compacting=False):
            assert thread_id == THREAD
            return {'turn': turn_id or 'manual-probe', 'saw_compaction': compacting}
        def close(self):
            return 0

    native.Native = Recorder
    native.configure = lambda opts: None
    pressures = [{}, {'final_raw_input_bytes': 3*1024*1024}, {'last_input_tokens': 165000},
                 {'final_raw_input_bytes': 20*1024*1024, 'last_input_tokens': 2_000_000}]
    cases = 0
    with tempfile.TemporaryDirectory() as tmp:
        native.ROOT = Path(tmp)
        for arm in ['native', 'clm']:
            for pressure in pressures:
                calls.clear()
                opts = env['task_options']({'thread': THREAD, 'wire': pressure}, {'marker': 'marker'}, arm, Path('/task'))
                native.run(opts, 'Original task text')
                assert [m for m, _ in calls] == ['initialize', 'thread/resume', 'turn/start']
                assert calls[1][1]['threadId'] == calls[2][1]['threadId'] == THREAD
                assert calls[2][1]['input'][0]['text'].endswith('Original task text')
                result = json.loads((native.ROOT/'native-result.json').read_text())
                assert result['resumed'] and 'protective_compaction' not in result
                cases += 1
        calls.clear()
        # Explicit capacity probes keep working, independently of serial dispatch.
        native.run(opts | {'compact': True}, 'Probe')
        assert [m for m, _ in calls] == ['initialize', 'thread/resume', 'thread/compact/start', 'turn/start']
        assert json.loads((native.ROOT/'native-result.json').read_text())['protective_compaction']['saw_compaction']
    events = iter([
        {'method': 'item/completed', 'params': {'threadId': THREAD, 'item': {'type': 'contextCompaction'}}},
        {'method': 'turn/completed', 'params': {'threadId': THREAD, 'turn': {'id': 'auto-1', 'status': 'completed'}}}])
    class EventSource:
        def event(self):
            return next(events)
    assert OriginalNative.complete(EventSource(), THREAD, 'auto-1')['saw_compaction']
    print(json.dumps({'serial_cases': cases, 'pre_task_compact_requests': 0,
                      'same_thread_and_instruction_verified': True, 'explicit_probe_supported': True,
                      'native_auto_compaction_event_supported': True, 'model_calls': 0}))


if __name__ == '__main__':
    main()
