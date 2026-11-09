import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipIf
from unittest.mock import patch

HAS_API = importlib.util.find_spec("fastapi") is not None


@skipIf(not HAS_API, "Install the api extra to run HTTP tests")
class ReportingApiTests(TestCase):
    def setUp(self) -> None:
        from fastapi.testclient import TestClient

        from scissorhands.api.app import create_app

        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
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
            [(run["project_id"], run["outcome"]) for run in all_runs.json()["runs"]],
            [(first["id"], "completed"), (second["id"], "agent_failed")],
        )
        self.assertEqual(all_runs.json()["errors"], [])
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
        self.assertEqual(
            (log["data"], log["total_bytes"], log["truncated"]), ("cd", 6, True)
        )
        self.assertEqual(self.client.get("/openapi.json").status_code, 200)

    def test_registration_errors_and_unavailable_folder(self) -> None:
        response = self.client.post("/api/projects", json={"path": "relative"})
        self.assertEqual(response.status_code, 400)
        response = self.client.post(
            "/api/projects", json={"path": str(self.root / "missing")}
        )
        self.assertEqual(response.status_code, 400)
        project = self.register(self.first)
        self.assertEqual(
            self.client.post(
                "/api/projects", json={"path": str(self.first)}
            ).status_code,
            409,
        )
        self.first.rename(self.root / "moved")
        self.assertFalse(self.client.get("/api/projects").json()[0]["available"])
        self.assertEqual(
            self.client.get(f"/api/projects/{project['id']}/runs").status_code, 409
        )
        second = self.register(self.second)
        result = self.client.get("/api/runs").json()
        self.assertEqual(result["runs"][0]["project_id"], second["id"])
        self.assertEqual(
            result["errors"],
            [
                {
                    "project_id": project["id"],
                    "status_code": 409,
                    "detail": "Project folder is unavailable",
                }
            ],
        )

    def test_missing_invalid_artifacts_and_deletion_leave_run_files(self) -> None:
        project = self.register(self.first)
        prefix = f"/api/projects/{project['id']}/work-items/TASK/runs/run-0001"
        self.assertEqual(
            self.client.get(prefix + "/artifacts/report").json()["state"], "missing"
        )
        self.assertEqual(
            self.client.get(prefix + "/artifacts/unknown").status_code, 422
        )
        self.assertEqual(
            self.client.get(
                prefix + "/artifacts/manifest", params={"tail": True}
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.get(prefix.replace("run-0001", "run-9999")).status_code, 404
        )
        self.assertEqual(
            self.client.delete(f"/api/projects/{project['id']}").status_code, 204
        )
        self.assertTrue((self.first / ".scissorhands" / "TASK" / "run-0001").is_dir())
        self.assertEqual(
            self.client.get("/api/runs").json(), {"runs": [], "errors": []}
        )

    def test_replaced_ancestor_cannot_redirect_registered_project(self) -> None:
        parent = self.root / "parent"
        project_root = parent / "project"
        project_root.mkdir(parents=True)
        project = self.register(project_root)
        parent.rename(self.root / "original-parent")
        replacement = self.root / "replacement"
        foreign_run = replacement / "project/.scissorhands/FOREIGN/run-0001"
        foreign_run.mkdir(parents=True)
        (foreign_run / "report.json").write_text(
            '{"state":"finished"}', encoding="utf-8"
        )
        parent.symlink_to(replacement, target_is_directory=True)

        prefix = f"/api/projects/{project['id']}"
        self.assertFalse(self.client.get(prefix).json()["available"])
        for suffix in (
            "/work-items",
            "/runs",
            "/work-items/TASK/runs/run-0001",
            "/work-items/TASK/runs/run-0001/artifacts/manifest",
        ):
            with self.subTest(route=suffix):
                self.assertEqual(self.client.get(prefix + suffix).status_code, 409)
        result = self.client.get("/api/runs").json()
        self.assertEqual(result["runs"], [])
        self.assertEqual(result["errors"][0]["project_id"], project["id"])

    def test_project_discovery_failure_preserves_healthy_results(self) -> None:
        first = self.register(self.first)
        second = self.register(self.second)
        original_iterdir = Path.iterdir
        # Inject at the filesystem boundary, so this also works under root in CI.
        for error, status_code in (
            (PermissionError("denied"), 409),
            (FileNotFoundError("removed during discovery"), 404),
        ):

            def iterdir(path, error=error):
                if path == self.first / ".scissorhands":
                    raise error
                return original_iterdir(path)

            with (
                self.subTest(error=type(error).__name__),
                patch.object(Path, "iterdir", iterdir),
            ):
                response = self.client.get("/api/runs")
                self.assertEqual(response.status_code, 200)
                result = response.json()
                self.assertEqual(
                    [run["project_id"] for run in result["runs"]], [second["id"]]
                )
                self.assertEqual(result["errors"][0]["project_id"], first["id"])
                self.assertEqual(result["errors"][0]["status_code"], status_code)
                direct = self.client.get(f"/api/projects/{first['id']}/runs")
                self.assertEqual(direct.status_code, status_code)
                self.assertEqual(direct.json()["detail"], result["errors"][0]["detail"])

    def test_artifact_windows_and_verification_output(self) -> None:
        project = self.register(self.first)
        prefix = f"/api/projects/{project['id']}/work-items/TASK/runs/run-0001"
        log = prefix + "/loops/1/artifacts/agent_output"
        for params, expected in (
            ({"offset": -1}, 422),
            ({"limit": 0}, 422),
            ({"limit": 1048577}, 422),
            ({"offset": 1, "tail": True}, 400),
        ):
            with self.subTest(params=params):
                self.assertEqual(
                    self.client.get(log, params=params).status_code, expected
                )
        tail = self.client.get(log, params={"tail": True, "limit": 2}).json()
        self.assertEqual(
            (tail["data"], tail["offset"], tail["bytes_read"]), ("ef", 4, 2)
        )
        verification = (
            self.first / ".scissorhands/TASK/run-0001/loop-0001/verification-1.log"
        )
        verification.write_text("verification passed", encoding="utf-8")
        url = prefix + "/loops/1/artifacts/verification_output"
        self.assertEqual(self.client.get(url).status_code, 400)
        self.assertEqual(
            self.client.get(url, params={"verification": 0}).status_code, 422
        )
        self.assertEqual(
            self.client.get(url, params={"verification": 1}).json()["data"],
            "verification passed",
        )
        self.assertEqual(
            self.client.get(log, params={"verification": 1}).status_code, 400
        )

    def test_artifact_containment_and_damaged_json_over_http(self) -> None:
        project = self.register(self.first)
        prefix = f"/api/projects/{project['id']}/work-items/TASK/runs/run-0001"
        run = self.first / ".scissorhands/TASK/run-0001"
        outside = self.root / "outside.txt"
        outside.write_text("must not be served", encoding="utf-8")
        (run / "changes.patch").symlink_to(outside)
        response = self.client.get(prefix + "/artifacts/patch")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], "unsafe")
        self.assertIsNone(response.json()["data"])
        (run / "report.json").write_text("{unfinished", encoding="utf-8")
        detail = self.client.get(prefix).json()
        self.assertEqual(detail["manifest"]["state"], "invalid")
        self.assertEqual(detail["summary"]["state"], "unknown")
        traversal = self.client.get(
            f"/api/projects/{project['id']}/runs", params={"work_item_id": "../outside"}
        )
        self.assertEqual(traversal.status_code, 400)
        alias = self.first / ".scissorhands/ALIAS"
        alias.symlink_to(run.parent, target_is_directory=True)
        self.assertEqual(
            self.client.get(prefix.replace("/TASK/", "/ALIAS/")).status_code, 400
        )

    def test_openapi_describes_artifact_kinds_states_and_errors(self) -> None:
        schema = self.client.get("/openapi.json").json()
        prefix = "/api/projects/{project_id}/work-items/{work_item_id}/runs/{run_id}"
        route = schema["paths"][prefix + "/artifacts/{kind}"]["get"]
        kind = next(
            parameter
            for parameter in route["parameters"]
            if parameter["name"] == "kind"
        )
        self.assertIn("manifest", kind["schema"]["enum"])
        self.assertNotIn("agent_output", kind["schema"]["enum"])
        for code in ("400", "404", "409", "422"):
            self.assertIn(code, route["responses"])
        models = schema["components"]["schemas"]
        self.assertIn(
            "unsafe", models["ArtifactResponse"]["properties"]["state"]["enum"]
        )
        self.assertIn(
            "unknown", models["RunSummaryResponse"]["properties"]["state"]["enum"]
        )
