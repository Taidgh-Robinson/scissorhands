from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from scissorhands.agents import ClaudeCodeAdapter, CodexAdapter, OpenCodeAdapter


class AgentAdapterTests(TestCase):
    def test_claude_command_uses_configured_permissions_by_default(self) -> None:
        command = ClaudeCodeAdapter().command(
            executable="claude",
            root=Path("/project"),
            final_message=Path("final.txt"),
            model="example-model",
            auto_approve=False,
            prompt="task",
        )

        self.assertEqual(
            command,
            [
                "claude",
                "--print",
                "--output-format",
                "text",
                "--model",
                "example-model",
            ],
        )
        self.assertTrue(ClaudeCodeAdapter().uses_stdin)

    def test_claude_command_maps_auto_approval_to_auto_permission_mode(self) -> None:
        command = ClaudeCodeAdapter().command(
            executable="claude",
            root=Path("/project"),
            final_message=Path("final.txt"),
            model=None,
            auto_approve=True,
            prompt="task",
        )

        self.assertEqual(command[-2:], ["--permission-mode", "auto"])
        self.assertNotIn("--dangerously-skip-permissions", command)
        self.assertNotIn("bypassPermissions", command)

    def test_codex_command_is_workspace_sandboxed(self) -> None:
        root = Path("/project")
        command = CodexAdapter().command(
            executable="codex",
            root=root,
            final_message=root / "final.txt",
            model="example-model",
            auto_approve=False,
            prompt="task",
        )

        self.assertEqual(command[:2], ["codex", "exec"])
        self.assertIn("workspace-write", command)
        self.assertIn("example-model", command)
        self.assertNotIn("--approve-for-me", command)
        self.assertEqual(command[-1], "-")

    def test_opencode_command_supports_explicit_auto_approval(self) -> None:
        command = OpenCodeAdapter().command(
            executable="opencode",
            root=Path("/project"),
            final_message=Path("final.txt"),
            model=None,
            auto_approve=True,
            prompt="do the task",
        )

        self.assertEqual(command, ["opencode", "run", "--auto", "do the task"])
        self.assertFalse(OpenCodeAdapter().uses_stdin)

    def test_codex_prefers_final_message_for_completion(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "run.log"
            final = root / "final.txt"
            log.write_text("stream", encoding="utf-8")
            final.write_text("final", encoding="utf-8")

            self.assertEqual(
                CodexAdapter().completion_output(log=log, final_message=final), "final"
            )
