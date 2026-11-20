import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

BENCH = Path(__file__).resolve().parents[1]/"benchmarks"
sys.path.insert(0,str(BENCH))
from audit_workbuddy import sha
from clm.context import Context, encode, write_json
from forced_context_edit.plugin import prompt, schedule, verify_phase


def exchange(identifier):
    return [{"type":"function_call","name":"shell","call_id":identifier,"arguments":"{}"},
            {"type":"function_call_output","call_id":identifier,"output":"data "*320}]


class ForcedContextTests(unittest.TestCase):
    def test_all_boundaries_including_final_pair(self):
        units = list(schedule([{"position":i} for i in range(1,51)]))
        self.assertEqual([i for k,i in units if k=="maintenance"],list(range(2,51,2)))
        self.assertEqual(units[:4],[("task",1),("task",2),("maintenance",2),("task",3)])
        self.assertEqual(units[-1],("maintenance",50))

    def fixture(self, root, *, maintenance_only=False):
        agent = root/"agent"
        agent.mkdir()
        context = Context(root)
        anchor = {"role":"user","content":"old synthetic problem"}
        boundary = {"role":"user","content":prompt(2)}
        items = [anchor,*exchange("old-1"),*exchange("old-2"),boundary,*exchange("housekeeping"),*exchange("newest")]
        context.apply(items)
        editable = json.loads((root/"LIVE_CTX_MAIN.json").read_bytes())["editable"]
        selected = next(x["id"] for x in editable
                        if any(y.get("call_id")==("housekeeping" if maintenance_only else "old-1") for y in x["items"]))
        write_json(root/"edit.json",{"revision":context.revision,"drop":[selected],"note":"Keep exact old result."})
        sent,detail = context.apply(items)
        self.assertEqual(detail["edit"],"accepted")
        wire = root/"wire/00002"
        wire.mkdir(parents=True)
        write_json(wire/"request.raw.json",{"input":items})
        write_json(wire/"request.sent.json",{"input":sent})
        (wire/"response.raw").write_text('data: {"type":"response.completed"}\n\n')
        write_json(wire/"receipt.json",{"path":"/v1/responses","delivered":True,"status":200,"started_ns":20,
                   "raw_sha256":sha(wire/"request.raw.json"),"sent_sha256":sha(wire/"request.sent.json"),"clm":detail})
        write_json(agent/"native-result.json",{"native_exit":0,"turn":"T","thread":"S","resumed":True})
        events = [
            ("to_codex",{"id":1,"method":"turn/start","params":{"threadId":"S","input":[{"text":prompt(2),"type":"text"}]}}),
            ("from_codex",{"id":1,"result":{"turn":{"id":"T"}}}),
            ("from_codex",{"method":"item/completed","params":{"threadId":"S","turnId":"T","item":{
                "type":"commandExecution","command":"clm-context edit --drop "+selected,"exitCode":0}}}),
            ("from_codex",{"method":"turn/completed","params":{"threadId":"S","turn":{"id":"T","status":"completed"}}})]
        (agent/"native.jsonl").write_bytes(b"".join(encode({"time_ns":i+1,"direction":d,"data":e})+b"\n"
                                                  for i,(d,e) in enumerate(events)))
        return wire

    def test_effective_edit_and_failed_delivery(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            wire = self.fixture(root)
            self.assertTrue(verify_phase(root,"S",2)["accepted"])
            receipt = json.loads((wire/"receipt.json").read_bytes())
            write_json(wire/"receipt.json",receipt | {"delivered":False})
            with self.assertRaises(ValueError):
                verify_phase(root,"S",2)

    def test_acknowledgement_alone_cannot_open_gate(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root)
            trace = root/"agent/native.jsonl"
            trace.write_bytes(b"".join(x for x in trace.read_bytes().splitlines(True) if b'commandExecution' not in x))
            with self.assertRaises(ValueError):
                verify_phase(root,"S",2)

    def test_dropping_only_housekeeping_is_insufficient(self):
        with TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root,maintenance_only=True)
            with self.assertRaises(ValueError):
                verify_phase(root,"S",2)
