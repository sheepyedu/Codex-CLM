"""Exercise two synthetic tasks, an actual CLM maintenance turn, then a third task."""
import argparse
from pathlib import Path

from clm.context import write_json
from checkpoint import restore_context
from relay import SeriesContext
from container import launch, own_tree
from plugin import schedule
from runner import maintenance
import run

TASKS = (
    "Use the shell to print the integers 1 through 500 (one per line). Then reply with their sum.",
    "Use the shell to calculate the square of 121, and print it. Reply with the result.",
    "Use the shell to calculate 17 * 13. Reply with the result.",
)


def main(root):
    root.mkdir(mode=0o700,parents=True,exist_ok=False)
    state = root/"starting-state"
    for name in ("home/notes","context"):
        (state/name).mkdir(parents=True)
    own_tree(state)
    context = SeriesContext(state/"context")
    key, endpoint = run.provider()
    steps = []
    thread = prior = None
    for kind,n in schedule([{"position":i} for i in range(1,4)]):
        if kind == "maintenance":
            proof = maintenance(root,state,prior,thread,n,key,endpoint)
            prior = root/"maintenance"/f"{n:03d}"/proof["attempt"]
            state = prior/"state"
            context = restore_context(state/"context",prior)
            steps.append([kind,n,proof["turn"]])
        else:
            target = root/f"synthetic-{n}"
            target.mkdir()
            options = {"arm":"clm","compact":False,"thread":thread,"marker":f"SYNTHETIC_{n}"}
            launch(target,state,context,options,TASKS[n-1],key,endpoint)
            native = run.read(target/"agent/native-result.json")
            if not native.get("turn") or (thread and native["thread"] != thread):
                raise ValueError("Synthetic continuation failed")
            thread, prior = native["thread"], target
            steps.append([kind,n,native["turn"]])
    # Check the adopted memory survives into the very first model request of task 3.
    first = run.read(root/"synthetic-3/wire/00001/request.sent.json")
    proof = verify_adoption(root,first)
    write_json(root/"PASS.json",{"thread":thread,"units":steps,"adoption":proof,"formal_tasks_sent":0})
    print((root/"PASS.json").read_text(),flush=True)


def verify_adoption(root, first):
    from audit_workbuddy import projection_proof
    phase = root/"maintenance/002"
    receipt = run.read(phase/"receipt.json")
    edit = receipt["edits"][-1]
    path = phase/receipt["attempt"]/"wire"/edit["wire"]/"receipt.json"
    proof = projection_proof(path,run.read(path))
    if not any("CLM memory written by the assistant:\n"+proof["note"] in run.message_text(i)
               for i in first["input"] if i.get("role") == "user"):
        raise ValueError("Task 3 did not receive the accepted maintenance note")
    return {"revision":edit["revision"],"dropped_ids":edit["dropped_ids"],"next_request_contains_note":True}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root",type=Path)
    main(p.parse_args().root.resolve())
