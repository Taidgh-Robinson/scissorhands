import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

# Stand in for uv, npm ci, and npm's long-lived Vite child. This exercises the
# executable scripts and real process groups without requiring Node or ports.
FAKE_APP = """
import os
import signal
import subprocess
import sys
from pathlib import Path

state = Path(os.environ["TEST_ROOT"]) / ".scissorhands" / ".dev"
logs = state / (state / "session").read_text()
assert all((logs / name).exists() for name in ("backend.log", "frontend.log"))
if sys.argv[1] == "ci":
    print("install output", file=sys.stderr)
    sys.exit(0)
if sys.argv[1] == "run" and Path(sys.argv[0]).name == "npm":
    assert sys.argv[sys.argv.index("--port") + 1] == os.environ["SCISSORHANDS_FRONTEND_PORT"]
    assert os.environ["SCISSORHANDS_API_URL"] == "http://127.0.0.1:" + os.environ["SCISSORHANDS_API_PORT"]
    if os.environ.get("FAIL_FRONTEND"):
        sys.exit("frontend failed to bind")
    sys.exit(subprocess.call([sys.executable, __file__, "vite"]))

def stop(*_):
    print("shutdown output", file=sys.stderr)
    sys.exit(0)

signal.signal(signal.SIGTERM, stop)
print("first stderr", file=sys.stderr)
if sys.argv[1] == "vite":
    print("Local:   http://127.0.0.1:" + os.environ["SCISSORHANDS_FRONTEND_PORT"] + "/")
else:
    assert sys.argv[sys.argv.index("--port") + 1] == os.environ["SCISSORHANDS_API_PORT"]
    print("Uvicorn running on http://127.0.0.1:" + os.environ["SCISSORHANDS_API_PORT"])
signal.pause()
"""


@unittest.skipUnless(os.name == "posix", "dev scripts use POSIX process groups")
class DevAppsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        shutil.copytree(SCRIPTS, self.root / "scripts")
        (self.root / "frontend").mkdir()
        commands = self.root / "bin"
        commands.mkdir()
        for name in ("uv", "npm"):
            command = commands / name
            command.write_text(f"#!{sys.executable}\n{FAKE_APP}")
            command.chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": f"{commands}{os.pathsep}{os.environ['PATH']}",
            "TEST_ROOT": str(self.root),
            "SCISSORHANDS_API_PORT": "8001",
            "SCISSORHANDS_FRONTEND_PORT": "5174",
        }
        self.env.pop("SCISSORHANDS_API_URL", None)
        self.state = self.root / ".scissorhands" / ".dev"
        self.addCleanup(self.command, "down")

    def command(self, action, *, check=True):
        return subprocess.run(
            [self.root / "scripts" / f"dev-{action}"],
            cwd=self.root.parent,
            env=self.env,
            timeout=20,
            capture_output=True,
            text=True,
            check=check,
        )

    def current_logs(self):
        return self.state / (self.state / "session").read_text()

    def test_start_and_stop_preserve_output_from_both_process_groups(self):
        self.assertIn("http://127.0.0.1:5174/", self.command("up").stdout)
        logs = self.current_logs()
        self.assertIn("already active", self.command("up").stdout)
        self.assertEqual(logs, self.current_logs())
        self.command("down")
        self.assertIn("already stopped", self.command("down").stdout)
        for name in ("backend", "frontend"):
            output = (logs / f"{name}.log").read_text()
            self.assertIn("first stderr", output)
            self.assertIn("shutdown output", output)
        self.assertIn("install output", (logs / "frontend.log").read_text())

    def test_failed_start_releases_session_and_keeps_logs_across_retry(self):
        self.env["FAIL_FRONTEND"] = "1"
        self.assertNotEqual(0, self.command("up", check=False).returncode)
        logs = self.current_logs()
        self.assertIn("frontend failed to bind", (logs / "frontend.log").read_text())
        self.assertIn("frontend exited", (logs / "launcher.log").read_text())
        self.assertIn("already stopped", self.command("down").stdout)
        del self.env["FAIL_FRONTEND"]
        self.command("up")
        self.assertNotEqual(logs, self.current_logs())
        self.assertIn("frontend failed to bind", (logs / "frontend.log").read_text())
