"""Guard the dependency boundary needed by independent CLI and API adapters."""

import ast
import subprocess
import sys
from pathlib import Path
from unittest import TestCase


class InterfaceBoundaryTests(TestCase):
    def test_backend_does_not_depend_on_cli_or_http_frameworks(self) -> None:
        package = Path(__file__).resolve().parents[1] / "src" / "scissorhands"
        for folder in ("application", "core", "storage", "prompting"):
            for path in (package / folder).rglob("*.py"):
                tree = ast.parse(path.read_text())
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imports = [alias.name for alias in node.names]
                    elif isinstance(node, ast.ImportFrom):
                        imports = [node.module or ""]
                    else:
                        continue
                    for name in imports:
                        with self.subTest(
                            path=path.relative_to(package), dependency=name
                        ):
                            self.assertFalse(
                                name.startswith(
                                    (
                                        "scissorhands.cli",
                                        "scissorhands.api",
                                        "fastapi",
                                        "starlette",
                                    )
                                )
                            )

    def test_public_application_import_does_not_load_terminal_code(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from scissorhands.application import RunService, RunRepository; import sys; assert not any(name.startswith('scissorhands.cli') for name in sys.modules)",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
