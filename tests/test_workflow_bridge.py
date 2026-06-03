from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from workflow import review_packet, run_next


def _task_text(test_command: str = 'python -c "raise SystemExit(0)"') -> str:
    return f"""# Task: Bridge unit task

## Objective
Validate the local bridge without external chat UI automation.

## Files Affected
- workflow/run_next.py
- workflow/review_packet.py

## Acceptance Criteria
- Bridge writes latest result.
- Bridge updates state.

## Safety Rules
- Keep Spencer paper-only.
- Do not enable live trading.
- Do not add broker order placement.
- Do not commit `.env` files or credentials.

## Test Commands
- {test_command}

## Expected Output
- Bridge dry run passes.
"""


class WorkflowBridgeTests(unittest.TestCase):
    def make_tmp_path(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory()
        return temp, Path(temp.name)

    def test_run_next_dry_run_writes_latest_result_outbox_and_state(self) -> None:
        temp, tmp_path = self.make_tmp_path()
        with temp:
            task_path = tmp_path / "current_task.md"
            latest_path = tmp_path / "latest_result.md"
            state_path = tmp_path / "agent_state.json"
            outbox_dir = tmp_path / "outbox"
            task_path.write_text(_task_text(), encoding="utf-8")

            summary, state = run_next.run_next(
                task_path=task_path,
                latest_result_path=latest_path,
                state_path=state_path,
                outbox_dir=outbox_dir,
                dry_run=True,
            )

            self.assertEqual("passed", summary["status"])
            self.assertEqual("gpt_reviewer", state["currentOwner"])
            self.assertTrue(state["paperOnlyStatus"]["paperOnly"])
            self.assertTrue(latest_path.exists())
            self.assertIn("Latest Result: bridge-unit-task", latest_path.read_text(encoding="utf-8"))
            self.assertEqual(1, len(list(outbox_dir.glob("*.md"))))
            self.assertEqual(1, len(list(outbox_dir.glob("*.json"))))

    def test_run_next_blocks_git_commit_commands_before_pipeline(self) -> None:
        temp, tmp_path = self.make_tmp_path()
        with temp:
            task_path = tmp_path / "current_task.md"
            latest_path = tmp_path / "latest_result.md"
            state_path = tmp_path / "agent_state.json"
            outbox_dir = tmp_path / "outbox"
            task_path.write_text(_task_text("git commit -m unsafe"), encoding="utf-8")

            summary, state = run_next.run_next(
                task_path=task_path,
                latest_result_path=latest_path,
                state_path=state_path,
                outbox_dir=outbox_dir,
                dry_run=True,
            )

            self.assertEqual("failed", summary["status"])
            self.assertEqual("trading_authority", state["currentOwner"])
            self.assertTrue(any("git" in failure.lower() for failure in summary["safety_failures"]))
            self.assertIn("unsafe bridge command blocked", latest_path.read_text(encoding="utf-8"))

    def test_review_packet_summarizes_latest_result_and_gate(self) -> None:
        temp, tmp_path = self.make_tmp_path()
        with temp:
            task_path = tmp_path / "current_task.md"
            latest_path = tmp_path / "latest_result.md"
            state_path = tmp_path / "agent_state.json"
            gate_path = tmp_path / "deployment_gate.json"
            result_json = tmp_path / "result.json"
            task_path.write_text(_task_text(), encoding="utf-8")
            latest_path.write_text("# Latest Result\n\n- Status: passed\n", encoding="utf-8")
            result_json.write_text(
                json.dumps({
                    "status": "passed",
                    "files_changed": ["workflow/run_next.py"],
                    "tests_run": [{"command": "python -m pytest tests/test_workflow_bridge.py", "returnCode": 0, "skipped": False}],
                }),
                encoding="utf-8",
            )
            state_path.write_text(json.dumps({"lastResultJson": str(result_json)}), encoding="utf-8")
            gate_path.write_text(
                json.dumps({
                    "paperOnly": True,
                    "deploymentAllowed": False,
                    "deploymentBlocked": True,
                    "liveTradingAllowed": False,
                    "brokerExecutionAllowed": False,
                    "aiOrderApprovalAllowed": False,
                    "reason": "validation has not passed",
                }),
                encoding="utf-8",
            )

            packet = review_packet.create_review_packet(
                task_path=task_path,
                latest_result_path=latest_path,
                state_path=state_path,
                deployment_gate_path=gate_path,
            )

            self.assertIn("workflow/run_next.py", packet)
            self.assertIn("Passed: 1", packet)
            self.assertIn("Deployment blocked: True", packet)
            self.assertIn("Spencer stays paper-only", packet)


if __name__ == "__main__":
    unittest.main()
