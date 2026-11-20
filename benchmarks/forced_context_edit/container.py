"""Run the housekeeping turn in a neutral container with its own trace directory."""
import os
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path

from clm.run import IMAGE, UID
from clm.context import write_json
from relay import Wire
import run

REPO = run.HERE.parent.parent
DRIVER = """set -eu
python3 /opt/workbuddy/loopback.py >/tmp/loopback.log 2>&1 &
for i in $(seq 1 100); do test ! -f /tmp/workbuddy-relay-ready || break; sleep .1; done
test -f /tmp/workbuddy-relay-ready
exec python3 /opt/workbuddy/native_turn.py /phase/options.json /phase/prompt.txt
"""


def own_tree(path):
    for directory, dirs, files in os.walk(path, followlinks=False):
        for child in [Path(directory), *(Path(directory)/n for n in dirs+files)]:
            os.chown(child, UID, UID, follow_symlinks=False)


def launch(attempt, state, context, options, instruction, key, base_url):
    logs = attempt/"agent"
    logs.mkdir()
    os.chown(logs, UID, UID)
    (attempt/"wire").mkdir()
    write_json(attempt/"options.json", options)
    (attempt/"prompt.txt").write_text(instruction)
    (attempt/"prompt.txt").chmod(0o644)
    with tempfile.TemporaryDirectory(prefix="wb-edit-") as temp:
        socket = Path(temp)/"responses.sock"
        with Wire(socket, attempt/"wire", base_url, key, context) as gateway:
            name = "wb-context-"+uuid.uuid4().hex[:16]
            args = ["docker", "run", "--rm", "--name", name, "--network", "none",
                    "--user", f"{UID}:{UID}", "--read-only",
                    "--cpus", "2", "--memory", "2g",
                    "--pids-limit", "256", "--tmpfs", "/tmp:rw,nosuid,nodev",
                    "--tmpfs", f"/workspace:rw,uid={UID},gid={UID}", "--workdir", "/workspace",
                    "-e", "HOME=/serial-home", "-e", "CODEX_HOME=/serial-home/codex",
                    "-e", "CLM_CONTEXT_DIR=/context", "-e", "PYTHONDONTWRITEBYTECODE=1",
                    "-e", "PATH=/opt/codex/codex-path:/usr/local/bin:/usr/bin:/bin"]
            mounts = [(run.RUNTIME,"/opt/codex","ro"),(REPO/"clm","/opt/codex-clm/clm","ro"),
                      (run.HERE/"native_turn.py","/opt/workbuddy/native_turn.py","ro"),
                      (run.HERE/"loopback.py","/opt/workbuddy/loopback.py","ro"),
                      (run.HERE/"tools/clm-context","/usr/local/bin/clm-context","ro"),
                      (attempt/"options.json","/phase/options.json","ro"),
                      (attempt/"prompt.txt","/phase/prompt.txt","ro"),
                      (socket,"/gateway/responses.sock","ro"),(logs,"/logs/agent","rw"),
                      (state/"home","/serial-home","rw"),(context.directory,"/context","rw")]
            for source, target, mode in mounts:
                args.extend(["-v", f"{source}:{target}:{mode}"])
            bridge = threading.Thread(target=gateway.serve_forever, daemon=True)
            bridge.start()
            try:
                with (attempt/"docker.log").open("wb") as log:
                    subprocess.run(args+["--entrypoint","/bin/sh",IMAGE,"-c",DRIVER],
                                   stdout=log, stderr=subprocess.STDOUT, timeout=1800, check=True)
            finally:
                # Also stop our container if the docker client timed out.
                subprocess.run(["docker","rm","-f",name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                gateway.shutdown()
                bridge.join()
