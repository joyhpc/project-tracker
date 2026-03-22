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
                        "formal_object": "DCURX_MAIN",
                        "borrowed_object": "AU15P_CORE + TI988/TI984 decoder",
                        "borrowed_purpose": "旧链路能力对照",
                        "scope": "DCURX OLDI 底层显示链路",
                        "sample_id": "SN-001",
                        "protocol_object": "DCURX_TI988",
                        "firmware_version": "STM32_v0.9.1",
                        "fpga_version": "KU3P_bit_2026_03_22",
                        "docs_backwrite": "docs_backwrite.md",
                        "close_mode": "merged_fix",
                        "evidence": ["evidence.md"],
                    },
                }
            ],
        }

        result = close_gate.check_close_gate(project, "oldi_bringup")

        self.assertTrue(result["valid"])
        self.assertEqual(result["counts"]["error"], 0)
