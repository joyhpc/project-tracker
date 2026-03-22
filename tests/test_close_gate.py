from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tracker import close_gate


class CloseGateTests(unittest.TestCase):
    def test_close_gate_requires_full_formal_metadata(self):
        repo = Path(tempfile.mkdtemp(prefix="pt-close-gate-"))
        project = {
            "id": "A57",
            "name": "A57",
            "repo": str(repo),
            "nodes": [
                {
                    "id": "edp_bringup",
                    "name": "eDP 跑通",
                    "close_required": True,
                    "closure": {
                        "formal_object": "DCURX_MAIN",
                        "scope": "DCURX eDP 底层链路",
                        "sample_id": "",
                        "docs_anchor": "A57.DCURX.EDP_OLDI.EXEC_V1_V2",
                    },
                }
            ],
        }

        result = close_gate.check_close_gate(project, "edp_bringup")

        self.assertFalse(result["valid"])
        self.assertTrue(any(issue["type"] == "missing_close_field" for issue in result["issues"]))

    def test_close_gate_accepts_valid_metadata(self):
        repo = Path(tempfile.mkdtemp(prefix="pt-close-gate-"))
        evidence = repo / "evidence.md"
        evidence.write_text("# ok\n", encoding="utf-8")
        backwrite = repo / "docs_backwrite.md"
        backwrite.write_text("# doc\n", encoding="utf-8")
        project = {
            "id": "A57",
            "name": "A57",
            "repo": str(repo),
            "nodes": [
                {
                    "id": "oldi_bringup",
                    "name": "OLDI 跑通",
                    "close_required": True,
                    "closure": {
                        "formal_object_id": "DCURX_MAIN",
                        "borrowed_object_id": "AU15P_CORE + TI988/TI984 decoder",
                        "borrowed_purpose": "旧链路能力对照",
                        "scope": "DCURX OLDI 底层显示链路",
                        "sample_entity_id": "SN-001",
                        "protocol_object_id": "DCURX_TI988",
                        "firmware_version": "STM32_v0.9.1",
                        "fpga_version": "KU3P_bit_2026_03_22",
                        "docs_anchor": "A57.DCURX.EDP_OLDI.EXEC_V1_V2",
                        "docs_backwrite_path": "docs_backwrite.md",
                        "close_mode": "merged_fix",
                        "evidence_paths": ["evidence.md"],
                    },
                }
            ],
        }

        result = close_gate.check_close_gate(project, "oldi_bringup")

        self.assertTrue(result["valid"])
        self.assertEqual(result["counts"]["error"], 0)

    def test_validate_closure_schema_rejects_invalid_types_and_unknown_fields(self):
        node = {
            "id": "bad_close",
            "name": "bad",
            "phase": "P1",
            "status": "pending",
            "close_required": True,
            "closure": {
                "formal_object_id": "DCURX_MAIN",
                "scope": "scope",
                "sample_entity_id": "SN-01",
                "protocol_object_id": "PROTO",
                "firmware_version": "fw",
                "fpga_version": "fpga",
                "docs_anchor": "A57.DCURX.EDP_OLDI.EXEC_V1_V2",
                "docs_backwrite_path": "doc.md",
                "close_mode": "bad_mode",
                "evidence_paths": "not-a-list",
                "mystery": "value",
            },
        }

        issues = close_gate.validate_closure_schema(node)
        issue_types = {issue["type"] for issue in issues}

        self.assertIn("unknown_closure_field", issue_types)
        self.assertIn("invalid_closure_list_type", issue_types)
        self.assertIn("invalid_close_mode", issue_types)

    def test_summarize_close_gates_reports_invalid_count(self):
        repo = Path(tempfile.mkdtemp(prefix="pt-close-gate-"))
        evidence = repo / "evidence.md"
        evidence.write_text("# ok\n", encoding="utf-8")
        project = {
            "id": "A57",
            "name": "A57",
            "repo": str(repo),
            "nodes": [
                {
                    "id": "camrx",
                    "name": "CAMRX close",
                    "close_required": True,
                    "closure": {
                        "formal_object_id": "CAMRX_MAIN",
                        "scope": "CAMRX",
                        "sample_entity_id": "CAM-01",
                        "protocol_object_id": "A39_BRG",
                        "firmware_version": "NA",
                        "fpga_version": "KU3P_CAMRX_001",
                        "docs_anchor": "A57.CAMRX.HS_3P5G.EXEC_V1_V2",
                        "docs_backwrite_path": "missing.md",
                        "close_mode": "merged_fix",
                        "evidence_paths": ["evidence.md"],
                    },
                },
                {
                    "id": "note_only",
                    "name": "普通任务",
                    "phase": "P1",
                    "status": "pending",
                },
            ],
        }

        summary = close_gate.summarize_close_gates(project)

        self.assertEqual(summary["required_count"], 1)
        self.assertEqual(summary["invalid_count"], 1)
        self.assertEqual(summary["entries"][0]["task_id"], "camrx")
        self.assertEqual(summary["entries"][0]["formal_object_id"], "CAMRX_MAIN")

    def test_close_gate_requires_docs_anchor(self):
        repo = Path(tempfile.mkdtemp(prefix="pt-close-gate-"))
        evidence = repo / "evidence.md"
        evidence.write_text("# ok\n", encoding="utf-8")
        backwrite = repo / "docs_backwrite.md"
        backwrite.write_text("# doc\n", encoding="utf-8")
        project = {
            "id": "A57",
            "name": "A57",
            "repo": str(repo),
            "nodes": [
                {
                    "id": "edp_bringup",
                    "name": "eDP 跑通",
                    "close_required": True,
                    "closure": {
                        "formal_object_id": "DCURX_MAIN",
                        "scope": "DCURX eDP 底层链路",
                        "sample_entity_id": "SN-01",
                        "protocol_object_id": "DCURX_TI984_DECODER",
                        "firmware_version": "STM32_v0.9.1",
                        "fpga_version": "KU3P_v1",
                        "docs_backwrite_path": "docs_backwrite.md",
                        "close_mode": "merged_fix",
                        "evidence_paths": ["evidence.md"],
                    },
                }
            ],
        }

        result = close_gate.check_close_gate(project, "edp_bringup")

        self.assertFalse(result["valid"])
        self.assertTrue(any(issue["field"] == "docs_anchor" for issue in result["issues"]))

    def test_need_human_check_requires_field_enumeration(self):
        node = {
            "id": "human_check",
            "name": "human_check",
            "phase": "P1",
            "status": "pending",
            "close_required": True,
            "closure": {
                "formal_object_id": "DCURX_MAIN",
                "scope": "scope",
                "sample_entity_id": "NEED_HUMAN_CHECK",
                "protocol_object_id": "PROTO",
                "firmware_version": "fw",
                "fpga_version": "fpga",
                "docs_anchor": "A57.DCURX.EDP_OLDI.EXEC_V1_V2",
                "docs_backwrite_path": "doc.md",
                "close_mode": "merged_fix",
                "evidence_paths": ["evidence.md"],
            },
        }

        issues = close_gate.validate_closure_schema(node)

        self.assertTrue(any(issue["type"] == "missing_need_human_check_field" for issue in issues))
