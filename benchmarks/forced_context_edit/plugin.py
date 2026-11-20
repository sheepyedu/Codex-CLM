"""强制题中编辑 Context: schedule and verify a dedicated native maintenance turn."""
import json
import re
from pathlib import Path

from audit_workbuddy import projection_proof, sha
from check_workbuddy_binding import completed_response, native_prompt
from clm.context import candidates, is_message
from provision_workbuddy_cbc import actor_done

NAME = "强制题中编辑 Context"
INTERVAL = 2
PROMPT = """[{marker}] Mandatory CLM context maintenance after {count} completed tasks.
You are in a separate housekeeping turn on the same thread. Use clm-context status now.
Choose one or more no-longer-needed completed tool exchanges from before this turn.
Preserve useful decisions, precise constraints, and reusable facts in a concise note.
Use clm-context edit --drop ID [ID ...] --note '...' to submit a real edit.
In a subsequent tool call, run clm-context status and check acceptance. If an edit is
rejected, inspect the current revision and correct it. Do not solve a benchmark task
or change task artifacts. End the turn after verifying the edit. If no safe edit is
possible, report the reason. The controller will check the actual projected request."""


def schedule(rows):
    for index, row in enumerate(rows, 1):
        if row["position"] != index:
            raise ValueError("Task positions must form a consecutive sequence")
        yield "task", index
        if index % INTERVAL == 0:
            yield "maintenance", index


def prompt(count):
    return PROMPT.format(count=count, marker=f"WB_PLUGIN_MAINT_{count:03d}")


def content(item):
    value = item.get("content", [])
    return value if isinstance(value, str) else "".join(x.get("text", "") for x in value)


def verify_phase(attempt, thread, count):
    """Accept only a completed same-thread turn with a model-issued, effective edit."""
    expected = prompt(count)
    native = actor_done(attempt)
    if not native or native["thread"] != thread:
        raise ValueError("Incomplete or mismatched native maintenance turn")
    record = json.loads((attempt/"agent/native-result.json").read_bytes())
    if (not record["resumed"] or record.get("protective_compaction") or
            native_prompt(attempt, {"native": record, "thread": thread}) != expected):
        raise ValueError("Maintenance prompt or native session binding failed")
    commands = []
    with (attempt/"agent/native.jsonl").open() as trace:
        for line in trace:
            evt = json.loads(line)
            data = evt["data"]
            p = data.get("params", {})
            it = p.get("item", {})
            if (data.get("method") == "item/completed" and p.get("threadId") == thread
                    and p.get("turnId") == record["turn"] and it.get("type") == "commandExecution"
                    and it.get("exitCode") == 0 and re.search(r"\bclm-context\s+edit\s", it.get("command", ""))):
                commands.append((evt["time_ns"], it["command"], it.get("aggregatedOutput", "")))
    proofs = []
    for path in sorted(attempt.glob("wire/*/receipt.json")):
        event = json.loads(path.read_bytes())
        edit = event.get("clm") or {}
        if (edit.get("edit") != "accepted" or event.get("path") != "/v1/responses"
                or not event.get("delivered") or event.get("status") != 200
                or not completed_response(path.parent/"response.raw")):
            continue
        # This also validates both request hashes, preserved messages and complete batches.
        proof = projection_proof(path, event)
        raw = json.loads((path.parent/"request.raw.json").read_bytes())["input"]
        users = [i for i, x in enumerate(raw) if is_message(x, "user")]
        if not users or content(raw[users[-1]]) != expected:
            continue
        groups = candidates(raw, users[0])
        dropped = edit["dropped_ids"]
        if (not proof["note"].strip() or not dropped or
                not any(groups[k][1] <= users[-1] for k in dropped) or
                not any(ts <= event["started_ns"] and (all(k in cmd for k in dropped) or
                        "Submitted. Use clm-context status" in output) for ts, cmd, output in commands)):
            continue
        proofs.append({"revision":edit["revision"], "dropped_ids":dropped,
                       "wire":path.parent.name, "receipt_sha256":sha(path),
                       "raw_input_sha256":edit["raw_input_sha256"], "upstream_input_sha256":edit["upstream_input_sha256"]})
    if not proofs:
        raise ValueError("No delivered, model-authored CLM edit of pre-phase history; next task is locked")
    return {"accepted":True, "after_task":count, "thread":thread, "turn":record["turn"], "edits":proofs}
