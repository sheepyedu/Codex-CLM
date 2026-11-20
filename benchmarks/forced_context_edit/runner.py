"""Prepare or execute the one-arm WorkBuddy experiment with forced CLM boundaries."""
import argparse
import asyncio
from collections import Counter
import fcntl
import json
from pathlib import Path
import shutil

from audit_workbuddy import valid_score
from checkpoint import restore_context
from clm.context import write_json
from clm.run import IMAGE
from continue_workbuddy_transport import resilient_trial, instance_key
from relay import SeriesContext
import run
from container import launch, own_tree
from plugin import NAME, INTERVAL, prompt, schedule, verify_phase

PREVIOUS_PLAN = "059cda0f3936af5bd3e64674fa95a60cb54713c0e2f15e01f48512746706d4e0"
COUNTS = {"code": 20, "office": 12, "web": 18}


def code_hashes():
    extra = [*Path(__file__).parent.glob("*.py"), run.HERE.parent/"continue_workbuddy_transport.py",
             run.HERE.parent/"audit_workbuddy.py", run.HERE.parent/"check_workbuddy_binding.py",
             run.HERE.parent/"provision_workbuddy_cbc.py", *(run.HERE.parent.parent/"clm"/f for f in ("edit.py","run.py","container_entry.py"))]
    return run.code_sha() | {str(p.relative_to(run.HERE.parent.parent)): run.sha(p) for p in extra}


def prepare(previous, root):
    prior = run.read(previous/"plan.json")
    if run.sha(previous/"plan.json") != PREVIOUS_PLAN or run.runtime_sha() != prior["runtime_sha256"]:
        raise ValueError("Expected the original skill50 rows and pinned Codex runtime")
    rows = [dict(row, marker=f"WB_PLUGIN_TASK_{row['position']:03d}") for row in prior["tasks"]]
    if Counter(r["domain"] for r in rows) != COUNTS or run.image_id(IMAGE) != IMAGE:
        raise ValueError("Unexpected domain distribution or neutral runtime image")
    for row in rows:
        task = run.task_dir(Path(prior["reference"]), row)
        if (run.sha(task/"instruction.md") != row["instruction_sha256"]
                or run.sha(task/"task.toml") != row["staged_task_config_sha256"]
                or run.image_id(row["image"]) != row["image_id"]):
            raise ValueError(f"Changed task or image at {row['position']}")
    units = list(schedule(rows))
    plan = {"stage":"clm-forced-context-edit", "arms":["clm"], "model":prior["model"],
            "tasks":rows, "chosen_totals":COUNTS, "reference":prior["reference"],
            "source_plan_sha256":PREVIOUS_PLAN, "runtime_sha256":run.runtime_sha(),
            "code_sha256":code_hashes(), "offline_sha256":run.sha(previous/"offline.yaml"),
            "context_policy":"no-pre-task-compaction-v1", "plugin":NAME,
            "interval":INTERVAL, "maintenance_image":IMAGE, "schedule":units}
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    shutil.copy2(previous/"offline.yaml", root/"offline.yaml")
    write_json(root/"plan.json", plan)
    (root/"plan.sha256").write_text(run.sha(root/"plan.json")+"\n")
    print(json.dumps({"tasks":len(rows),"maintenance":len(units)-len(rows),"plan_sha256":run.sha(root/"plan.json")}))


def live_session(home, thread):
    files = list((home/"codex/sessions").rglob(f"*{thread}.jsonl"))
    if len(files) != 1 or files[0].is_symlink():
        raise ValueError("Expected exactly one live native session")
    return files[0]


def maintenance(root, state, prior, thread, count, key, endpoint):
    phase = root/"maintenance"/f"{count:03d}"
    phase.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Uncommitted attempts live on private copies. They can never advance the task cursor.
    index = len(list(phase.glob("attempt-*"))) + 1
    attempt = phase/f"attempt-{index:03d}"
    attempt.mkdir(mode=0o700)
    new_state = attempt/"state"
    new_state.mkdir()
    for name in ("home","context"):
        shutil.copytree(state/name, new_state/name, symlinks=True)
        own_tree(new_state/name)
    if (new_state/"context/edit.json").exists():
        raise ValueError("A preceding tool edit remains pending; cannot attribute it to maintenance")
    ctx = restore_context(new_state/"context", prior)
    options = {"arm":"clm","phase":"context-maintenance","thread":thread,"compact":False,
               "marker":f"WB_PLUGIN_MAINT_{count:03d}"}
    write_json(attempt/"intent.json", {"arm":"clm","marker":options["marker"],
               "purpose":"context-maintenance","after_task":count,"thread":thread})
    try:
        launch(attempt,new_state,ctx,options,prompt(count),key,endpoint)
        proof = verify_phase(attempt,thread,count)
        proof.update(attempt=attempt.name, session_sha256=run.save_thread(new_state/"home",thread,attempt))
        write_json(phase/"receipt.json",proof)
    except Exception as error:
        write_json(attempt/"failure.json",{"type":type(error).__name__,"message":str(error)})
        raise
    return proof


async def execute(root):
    plan = run.read(root/"plan.json")
    if (run.sha(root/"plan.json") != (root/"plan.sha256").read_text().strip()
            or plan["stage"] != "clm-forced-context-edit" or plan["arms"] != ["clm"]
            or plan["maintenance_image"] != IMAGE or plan["interval"] != INTERVAL
            or plan["source_plan_sha256"] != PREVIOUS_PLAN or plan["code_sha256"] != code_hashes()
            or plan["runtime_sha256"] != run.runtime_sha() or plan["offline_sha256"] != run.sha(root/"offline.yaml")
            or Counter(r["domain"] for r in plan["tasks"]) != COUNTS):
        raise ValueError("Frozen experiment changed")
    units = list(schedule(plan["tasks"]))
    if plan["schedule"] != [list(x) for x in units]:
        raise ValueError("Schedule differs from the frozen plan")
    journal = root/"units.json"
    recorded = run.read(journal) if journal.exists() else []
    if [tuple(x["unit"]) for x in recorded] != units[:len(recorded)]:
        raise ValueError("Journal does not match the scheduled prefix")
    state = root/"clm"
    previous = prior = expected_sha = thread = None
    creds = None
    for i, (kind,n) in enumerate(units):
        row = plan["tasks"][n-1]
        private = (root/"clm/evidence"/instance_key(row) if kind=="task"
                   else root/"maintenance"/f"{n:03d}")
        path = private/"receipt.json"
        if i < len(recorded) and (not path.is_file() or run.sha(path) != recorded[i]["receipt_sha256"]):
            raise ValueError("Committed receipt changed or is missing")
        if not path.exists():
            if thread and run.sha(live_session(state/"home",thread)) != expected_sha:
                raise ValueError("Live thread differs from last committed snapshot; reconcile active attempt")
            if creds is None:
                creds = run.provider()
            print(f"START {kind} {n:03d}", flush=True)
            if kind == "task":
                if private.exists():
                    raise ValueError(f"Unresolved task attempt: {private}")
                ctx = restore_context(state/"context", prior) if prior else SeriesContext(state/"context")
                await resilient_trial(root, plan | {"state_home":str(state/"home")}, row, "clm", previous, *creds, ctx)
            else:
                maintenance(root,state,prior,thread,n,*creds)
        receipt = run.read(path)
        if not receipt["accepted"] or (thread and receipt["thread"] != thread):
            raise ValueError(f"{kind} {n} did not pass; next unit is locked")
        if kind == "task":
            if receipt["row"] != row or receipt["arm"] != "clm" or receipt["native"].get("protective_compaction"):
                raise ValueError("Scored receipt does not match the plugin experiment")
            valid_score(receipt)
            thread, previous, prior = receipt["thread"], receipt, private
        else:
            prior = private/receipt["attempt"]
            proof = verify_phase(prior,thread,n)
            if receipt["edits"] != proof["edits"] or receipt["turn"] != proof["turn"]:
                raise ValueError("Committed maintenance evidence differs from verified projection")
            state = prior/"state"
        expected_sha = receipt["session_sha256"]
        if run.sha(prior/"native-session.jsonl") != expected_sha:
            raise ValueError("Archived native session changed")
        if i == len(recorded):
            recorded.append({"unit":[kind,n],"thread":thread,"receipt_sha256":run.sha(path)})
            write_json(journal,recorded)
            print(f"ACCEPTED {kind} {n:03d}", flush=True)
    write_json(root/"accepted.json",{"tasks":len(plan["tasks"]),"maintenance":len(units)-len(plan["tasks"]),
               "thread":thread,"journal_sha256":run.sha(journal),"plan_sha256":run.sha(root/"plan.json")})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    cmds = parser.add_subparsers(dest="command",required=True)
    p = cmds.add_parser("prepare")
    p.add_argument("previous",type=Path)
    p.add_argument("root",type=Path)
    cmds.add_parser("run").add_argument("root",type=Path)
    args = parser.parse_args()
    if args.command=="prepare":
        prepare(args.previous.resolve(),args.root.resolve())
    else:
        with (args.root/"controller.lock").open("a") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
            asyncio.run(execute(args.root.resolve()))


if __name__=="__main__":
    main()
