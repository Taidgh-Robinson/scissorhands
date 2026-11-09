import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipIf

HAS_API = importlib.util.find_spec("fastapi") is not None


@skipIf(not HAS_API, "Install the api extra to run HTTP tests")
class ReportingApiTests(TestCase):
    def setUp(self) -> None:
        from fastapi.testclient import TestClient

        from scissorhands.api.app import create_app

        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.client = TestClient(create_app(self.root / "registry.sqlite3"))
        self.first = self.root / "first"
        self.second = self.root / "second"
        for root, outcome in ((self.first, "completed"), (self.second, "agent_failed")):
            run = root / ".scissorhands" / "TASK" / "run-0001"
            loop = run / "loop-0001"
            loop.mkdir(parents=True)
            (run / "report.json").write_text(
                json.dumps({"state": "finished", "outcome": outcome}), encoding="utf-8"
            )
            (run / "run.json").write_text('{"agent":"codex"}', encoding="utf-8")
            (loop / "iteration-1.json").write_text(
                '{"outcome":"completed"}', encoding="utf-8"
            )
            (loop / "iteration-1.log").write_text("abcdef", encoding="utf-8")

    def register(self, root: Path) -> dict:
        response = self.client.post("/api/projects", json={"path": str(root)})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_reports_two_projects_with_same_work_item_and_run_id(self) -> None:
        first = self.register(self.first)
        second = self.register(self.second)
        self.assertNotEqual(first["id"], second["id"])

        all_runs = self.client.get("/api/runs")
        self.assertEqual(all_runs.status_code, 200)
        self.assertEqual(
            [(run["project_id"], run["outcome"]) for run in all_runs.json()],
            [(first["id"], "completed"), (second["id"], "agent_failed")],
        )
        prefix = f"/api/projects/{second['id']}/work-items/TASK/runs/run-0001"
        detail = self.client.get(prefix)
        self.assertEqual(detail.json()["summary"]["outcome"], "agent_failed")
        self.assertEqual(detail.json()["settings"]["data"]["agent"], "codex")
        self.assertEqual(detail.json()["loops"], [1])
        self.assertEqual(
            self.client.get(prefix + "/loops/1").json()["receipt"]["data"],
            {"outcome": "completed"},
        )
        log = self.client.get(
            prefix + "/loops/1/artifacts/agent_output", params={"offset": 2, "limit": 2}
        ).json()
        self.assertEqual((log["data"], log["total_bytes"], log["truncated"]), ("cd", 6, True))
        self.assertEqual(self.client.get("/openapi.json").status_code, 200)

    def test_registration_errors_and_unavailable_folder(self) -> None:
        response = self.client.post("/api/projects", json={"path": "relative"})
        self.assertEqual(response.status_code, 400)
        response = self.client.post("/api/projects", json={"path": str(self.root / "missing")})
        self.assertEqual(response.status_code, 400)
        project = self.register(self.first)
        self.assertEqual(
            self.client.post("/api/projects", json={"path": str(self.first)}).status_code,
            409,
        )
        self.first.rename(self.root / "moved")
        self.assertFalse(self.client.get("/api/projects").json()[0]["available"])
        self.assertEqual(self.client.get(f"/api/projects/{project['id']}/runs").status_code, 409)
        second = self.register(self.second)
        self.assertEqual(self.client.get("/api/runs").json()[0]["project_id"], second["id"])

    def test_missing_invalid_artifacts_and_deletion_leave_run_files(self) -> None:
        project = self.register(self.first)
        prefix = f"/api/projects/{project['id']}/work-items/TASK/runs/run-0001"
        self.assertEqual(
            self.client.get(prefix + "/artifacts/report").json()["state"], "missing"
        )
        self.assertEqual(
            self.client.get(prefix + "/artifacts/unknown").status_code, 400
        )
        self.assertEqual(
            self.client.get(prefix + "/artifacts/manifest", params={"tail": True}).status_code,
            400,
        )
        self.assertEqual(self.client.get(prefix.replace("run-0001", "run-9999")).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/projects/{project['id']}").status_code, 204)
        self.assertTrue((self.first / ".scissorhands" / "TASK" / "run-0001").is_dir())
        self.assertEqual(self.client.get("/api/runs").json(), [])
