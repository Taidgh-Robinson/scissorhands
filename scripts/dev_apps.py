"""Start and stop this checkout's local reporting services on macOS or Linux."""

import fcntl
import os
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack, suppress
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".scissorhands" / ".dev"
API_PORT = os.environ.get("SCISSORHANDS_API_PORT", "8000")
FRONTEND_PORT = os.environ.get("SCISSORHANDS_FRONTEND_PORT", "5173")
API_URL = f"http://127.0.0.1:{API_PORT}"
FRONTEND_URL = f"http://127.0.0.1:{FRONTEND_PORT}"
SERVICES = {
    "backend": (
        ROOT,
        [
            "uv",
            "run",
            "--locked",
            "--extra",
            "api",
            "scissorhands-api",
            "--port",
            API_PORT,
        ],
        b"Uvicorn running on ",
    ),
    "frontend": (
        ROOT / "frontend",
        [
            "sh",
            "-ec",
            'test -x node_modules/.bin/vite || npm ci\nexec "$@"',
            "sh",
            "npm",
            "run",
            "dev",
            "--",
            "--host",
            "127.0.0.1",
            "--port",
            FRONTEND_PORT,
            "--strictPort",
        ],
        b"Local:",
    ),
}


def stop_children(children):
    # uv and npm can have server processes beneath them in the same group.
    for child in children:
        with suppress(ProcessLookupError):
            os.killpg(child.pid, signal.SIGTERM)
    deadline = time.monotonic() + 5
    for child in children:
        while True:
            child.poll()
            try:
                os.killpg(child.pid, 0)
            except ProcessLookupError:
                break
            if time.monotonic() >= deadline:
                with suppress(ProcessLookupError):
                    os.killpg(child.pid, signal.SIGKILL)
                break
            time.sleep(0.05)
        child.wait()


def supervise(logs):
    stop = logs / "stop"
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.touch())

    children = {}
    with ExitStack() as files:
        outputs = {
            name: files.enter_context((logs / f"{name}.log").open("ab"))
            for name in SERVICES
        }
        try:
            for name, (cwd, command, _) in SERVICES.items():
                print(f"Starting {name} in {cwd}")
                children[name] = subprocess.Popen(
                    command,
                    cwd=cwd,
                    env={
                        "SCISSORHANDS_API_URL": API_URL,
                        **os.environ,
                        "PYTHONUNBUFFERED": "1",
                        "NO_COLOR": "1",
                    },
                    stdout=outputs[name],
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            # Each pinned server announces readiness after binding its own port.
            pending = set(SERVICES)
            deadline = time.monotonic() + 120
            while not stop.exists():
                for name, child in children.items():
                    if child.poll() is not None:
                        raise SystemExit(
                            f"{name} exited with status {child.returncode}"
                        )
                if pending:
                    for name in pending.copy():
                        if SERVICES[name][2] in (logs / f"{name}.log").read_bytes():
                            pending.remove(name)
                    if not pending:
                        print("Both services are ready")
                        (logs / "ready").touch()
                    elif time.monotonic() >= deadline:
                        raise SystemExit(
                            f"Timed out starting {', '.join(sorted(pending))}"
                        )
                time.sleep(0.2)
        finally:
            stop_children(children.values())
            print("Services stopped")


def manage(action):
    STATE.mkdir(parents=True, exist_ok=True)
    # Serialize commands. The supervisor inherits the separate lifetime lock so
    # down can wait for cleanup without looking up or signalling a saved PID.
    with (
        (STATE / "command.lock").open("a") as gate,
        (STATE / "session").open("a+") as session,
    ):
        fcntl.flock(gate, fcntl.LOCK_EX)
        try:
            fcntl.flock(session, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            session.seek(0)
            logs = STATE / session.read()
            if action == "down":
                (logs / "stop").touch()
                fcntl.flock(session, fcntl.LOCK_EX)
                print(f"Stopped. Logs saved in {logs}")
            else:
                print(f"A dev session is already active. Logs in {logs}")
            return
        if action == "down":
            print("The dev apps are already stopped.")
            return

        for port in (API_PORT, FRONTEND_PORT):
            if (
                not port.isascii()
                or not port.isdecimal()
                or not 1 <= int(port) <= 65535
            ):
                raise SystemExit(f"Expected a port between 1 and 65535, got {port!r}")
        prefix = datetime.now().strftime("%Y%m%d-%H%M%S-")
        logs = Path(tempfile.mkdtemp(prefix=prefix, dir=STATE))
        session.seek(0)
        session.truncate()
        session.write(logs.name)
        session.flush()
        print(f"Logs in {logs}", flush=True)
        with (logs / "launcher.log").open("ab") as launcher:
            supervisor = subprocess.Popen(
                [sys.executable, "-u", __file__, "serve", str(logs)],
                stdin=subprocess.DEVNULL,
                stdout=launcher,
                stderr=subprocess.STDOUT,
                pass_fds=(session.fileno(),),
                start_new_session=True,
            )

    try:
        while not (logs / "ready").exists():
            if supervisor.poll() is not None:
                raise SystemExit(f"Startup stopped. See the logs in {logs}")
            time.sleep(0.1)
    except KeyboardInterrupt:
        (logs / "stop").touch()
        supervisor.wait()
        raise SystemExit(130) from None
    print(f"Frontend {FRONTEND_URL}/\nBackend  {API_URL}/docs")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "serve":
        supervise(Path(sys.argv[2]))
    elif sys.argv[1:] in (["up"], ["down"]):
        manage(sys.argv[1])
    else:
        raise SystemExit("Use scripts/dev-up or scripts/dev-down")
