"""Owned synthetic counterexamples only / 仅自编反例，不读取真实试验结果。"""

import copy
from contextlib import redirect_stdout
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmarks.known_task_execution import analyze_sensitivity as analysis


H = "a" * 64
S = "b" * 64


def identities():
    return {
        name: {"instance_id": name, "repo": repo, "base_commit": "c" * 40}
        for name, repo in (("a1", "repo-a"), ("a2", "repo-a"), ("b1", "repo-b"), ("b2", "repo-b"))
    }


def condition(key="old", stamp="2026-01-01T00:00:00Z", qualified=True, started=True):
    return {
        "condition_key": key,
        "run_id": key,
        "protocol_frozen_utc": stamp,
        "approved": True,
        "started": started,
        "state": "closed" if started else "not_started",
        "pair_records_complete": qualified,
        "qualification_status": "finite_qualified"
        if qualified
        else "paired_unqualified_with_calls",
        "qualification_record_sha256_or_null": H if qualified else None,
        "protocol_sha256": H,
        "environment_manifest_sha256_or_null": H if qualified else None,
        "source_identity_manifest_sha256_or_null": H if qualified else None,
    }


def ledger():
    tasks = []
    for name, identity in identities().items():
        tasks.append(
            {
                **identity,
                "original_F2P": 1,
                "original_P2P": 1,
                "latest_approved_started_condition_key_or_null": "old",
                "finite_qualified": True,
                "final_status": "finite_qualified",
                "exclusion_reason_or_null": None,
                "conditions": [condition()],
            }
        )
    return {
        "snapshot_id": "synthetic",
        "snapshot_frozen_utc": "2026-01-05T00:00:00Z",
        "final_for_secondary_analysis": True,
        "all_started_conditions_closed": True,
        "all_original_tasks_included": True,
        "original_pilot_protocol_sha256": H,
        "original_pilot_scores_sha256": S,
        "original_task_execution_contract_sha256": H,
        "frozen_execution_evidence_sha256": H,
        "source_and_protocol_binding_validation_sha256": H,
        "tasks": tasks,
    }


def scores():
    tasks = []
    for name, identity in identities().items():
        cells = []
        for method in analysis.METHODS:
            for budget in analysis.BUDGETS:
                target = 0 if name == "b2" else 2
                pred = 0 if name == "a2" else 2
                hit = 0 if not pred or not target else 1 if method == "graph_expand" else 2
                cell = {"predicted": pred, "target": target, "intersection": hit}
                cell.update(
                    status="scored" if target else "no_target",
                    f1=2 * hit / (pred + target) if target else None,
                    recall=hit / target if target else None,
                    precision=hit / pred if pred and target else 0 if target else None,
                )
                cells.append({"method": method, "budget": budget, "line": cell})
        tasks.append(
            {
                "instance_id": name,
                "repo": identity["repo"],
                "prediction_status": "worker_failure" if name == "a2" else "predicted",
                "scores": cells,
            }
        )
    return {"tasks": tasks}


class EligibilityTests(unittest.TestCase):
    def check(self, data):
        return analysis.validate_eligibility(data, identities(), H, S, (4, 4))

    def test_latest_failed_never_falls_back_to_pass(self):
        data = ledger()
        row = data["tasks"][0]
        row["conditions"].append(condition("new", "2026-01-02T00:00:00Z", False))
        row.update(
            latest_approved_started_condition_key_or_null="new",
            finite_qualified=False,
            final_status="paired_unqualified_with_calls",
            exclusion_reason_or_null="later_failure",
        )
        selected, _ = self.check(data)
        self.assertNotIn("a1", selected)
        row.update(latest_approved_started_condition_key_or_null="old", finite_qualified=True)
        with self.assertRaisesRegex(ValueError, "latest condition"):
            self.check(data)

    def test_unstarted_proposal_does_not_displace_actual_attempt(self):
        data = ledger()
        data["tasks"][0]["conditions"].append(
            condition("candidate", "2026-01-04T00:00:00Z", False, False)
        )
        self.assertIn("a1", self.check(data)[0])

    def test_later_closed_partial_is_nonqualified(self):
        data = ledger()
        row = data["tasks"][0]
        row["conditions"].append(condition("partial", "2026-01-04T00:00:00Z", False))
        row.update(
            latest_approved_started_condition_key_or_null="partial",
            finite_qualified=False,
            final_status="paired_no_observed_target_calls",
            exclusion_reason_or_null="closed_abort",
        )
        self.assertNotIn("a1", self.check(data)[0])

    def test_running_condition_rejected(self):
        data = ledger()
        data["tasks"][0]["conditions"][0]["state"] = "running"
        with self.assertRaisesRegex(ValueError, "running"):
            self.check(data)

    def test_partial_cannot_claim_qualified(self):
        data = ledger()
        data["tasks"][0]["conditions"][0]["pair_records_complete"] = False
        with self.assertRaisesRegex(ValueError, "partial"):
            self.check(data)

    def test_no_actual_attempt_is_retained_nonqualified(self):
        data = ledger()
        row = data["tasks"][0]
        row.update(
            conditions=[],
            latest_approved_started_condition_key_or_null=None,
            finite_qualified=False,
            final_status="no_completed_target_pair",
            exclusion_reason_or_null="never_started",
        )
        selected, rows = self.check(data)
        self.assertEqual(len(rows), 4)
        self.assertNotIn("a1", selected)

    def test_missing_duplicate_and_extra_tasks_rejected(self):
        for mode in ("missing", "duplicate", "extra"):
            with self.subTest(mode=mode):
                data = ledger()
                if mode == "missing":
                    data["tasks"].pop()
                elif mode == "duplicate":
                    data["tasks"].append(copy.deepcopy(data["tasks"][0]))
                else:
                    row = copy.deepcopy(data["tasks"][0])
                    row["instance_id"] = "extra"
                    data["tasks"].append(row)
                with self.assertRaises(ValueError):
                    self.check(data)

    def test_all_finality_flags_required(self):
        for key in (
            "final_for_secondary_analysis",
            "all_started_conditions_closed",
            "all_original_tasks_included",
        ):
            data = ledger()
            data[key] = False
            with self.assertRaisesRegex(ValueError, "not sealed"):
                self.check(data)

    def test_snapshot_cannot_precede_condition(self):
        data = ledger()
        data["tasks"][0]["conditions"][0]["protocol_frozen_utc"] = "2026-01-06T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "newer"):
            self.check(data)

    def test_task_identity_counts_status_and_hash_bindings(self):
        for field, value in (
            ("base_commit", "d" * 40),
            ("original_P2P", 2),
            ("final_status", "paired_unqualified_with_calls"),
        ):
            data = ledger()
            data["tasks"][0][field] = value
            with self.assertRaises(ValueError):
                self.check(data)
        data = ledger()
        data["original_pilot_scores_sha256"] = H
        with self.assertRaisesRegex(ValueError, "binding"):
            self.check(data)


class ScoreTests(unittest.TestCase):
    def check(self, data):
        return analysis.validate_scores(data, identities())

    def test_undefined_labels_are_not_zero(self):
        tasks = self.check(scores())
        self.assertIsNone(tasks["b2"]["cells"]["graph_expand", 16000])
        data = scores()
        data["tasks"][3]["scores"][0]["line"]["f1"] = 0
        with self.assertRaisesRegex(ValueError, "undefined"):
            self.check(data)

    def test_pred_failure_retained_as_original_zero(self):
        tasks = self.check(scores())
        self.assertEqual(tasks["a2"]["cells"]["graph_expand", 16000]["f1"], Fraction(0))
        result = analysis.view(tasks, set(tasks), ["repo-a", "repo-b"])
        focus = next(
            r
            for r in result["method_budget_cells"]
            if r["method"] == "graph_expand" and r["budget"] == 16000
        )
        self.assertEqual(focus["repo_macro"]["f1"], 0.375)

    def test_missing_duplicate_unknown_cells_rejected(self):
        for mode in ("missing", "duplicate", "unknown"):
            data = scores()
            cells = data["tasks"][0]["scores"]
            if mode == "missing":
                cells.pop()
            elif mode == "duplicate":
                cells.append(copy.deepcopy(cells[0]))
            else:
                cells[0]["method"] = "new_tuned_method"
            with self.assertRaises(ValueError):
                self.check(data)

    def test_metric_nonfinite_bad_counts_and_inconsistency_rejected(self):
        for key, value in (
            ("f1", float("nan")),
            ("recall", float("inf")),
            ("target", True),
            ("intersection", 3),
            ("predicted", -1),
            ("f1", 0.125),
        ):
            data = scores()
            data["tasks"][0]["scores"][0]["line"][key] = value
            with self.assertRaises(ValueError):
                self.check(data)

    def test_empty_repository_and_empty_subset_stay_undefined(self):
        tasks = self.check(scores())
        result = analysis.view(tasks, {"a1"}, ["repo-a", "repo-b"])
        focus = next(
            r
            for r in result["method_budget_cells"]
            if r["method"] == "graph_expand" and r["budget"] == 16000
        )
        self.assertEqual(focus["repo_macro"]["f1"], 0.5)
        self.assertIsNone(focus["per_repo"][1]["f1"])
        empty = analysis.view(tasks, set(), ["repo-a", "repo-b"])
        self.assertIsNone(empty["focus_16000"][0]["f1_difference"])
        self.assertIsNone(empty["joint_strict_negative_F1_and_recall_both_baselines"])

    def test_all_methods_budgets_and_negative_components_retained(self):
        tasks = self.check(scores())
        result = analysis.view(tasks, set(tasks), ["repo-a", "repo-b"])
        self.assertEqual(len(result["method_budget_cells"]), 18)
        self.assertEqual(len(result["comparisons_all_budgets"]), 6)
        self.assertTrue(result["joint_strict_negative_F1_and_recall_both_baselines"])
        for row in result["focus_16000"]:
            self.assertEqual(row["f1_sign"], "negative")
            self.assertEqual(row["recall_sign"], "negative")

    def test_exact_tie_not_negative(self):
        data = scores()
        for task in data["tasks"]:
            by_budget = {
                cell["budget"]: cell for cell in task["scores"] if cell["method"] == "bm25_windows"
            }
            for cell in task["scores"]:
                if cell["method"] == "graph_expand":
                    cell["line"] = copy.deepcopy(by_budget[cell["budget"]]["line"])
        result = analysis.view(self.check(data), set(identities()), ["repo-a", "repo-b"])
        self.assertEqual(result["focus_16000"][0]["f1_sign"], "tie")
        self.assertFalse(result["joint_strict_negative_F1_and_recall_both_baselines"])

    def test_membership_keeps_all_tasks_and_repo_composition_companion(self):
        tasks = self.check(scores())
        records = {r["instance_id"]: r for r in ledger()["tasks"]}
        records["b1"].update(exclusion_reason_or_null="synthetic_failure")
        result = analysis.summarize(tasks, {"a1", "a2", "b2"}, records)
        self.assertEqual(len(result["membership"]), 4)
        self.assertEqual(result["per_repository_denominators"][1]["qualified_no_target_tasks"], 1)
        cell = result["all39_common_repository_composition_diagnostic"]["method_budget_cells"][0]
        self.assertEqual(cell["contributing_repositories"], ["repo-a"])
        self.assertFalse(result["new_holdout"])


class JsonTests(unittest.TestCase):
    def test_duplicate_nonfinite_and_checksum_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.json"
            for content in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{"x":1e400}'):
                path.write_text(content)
                with self.assertRaises(ValueError):
                    analysis.read_json(path)
            path.write_text(json.dumps({"x": 1}))
            with self.assertRaisesRegex(ValueError, "SHA256"):
                analysis.read_json(path, H)


class CommandGateTests(unittest.TestCase):
    def attempt(self, mode):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            protocol = root / "protocol.json"
            protocol.write_text("{}")
            approval = root / "approval.json"
            data = {
                "action": "authorize_one_final_secondary_calculation",
                "allow_real_inputs": True,
                "protocol_sha256": analysis.digest(protocol),
                "eligibility_ledger_sha256": S,
                "analysis_program_sha256": analysis.digest(analysis.__file__),
            }
            if mode == "unauthorized":
                data["action"] = "not_authorized"
            if mode == "wrong_program":
                data["analysis_program_sha256"] = H
            approval.write_text(json.dumps(data))
            ledger_name = (
                "ELIGIBILITY_CURRENT.json" if mode == "current" else "not-created-ledger.json"
            )
            argv = [
                "analyze_sensitivity.py",
                "--protocol",
                str(protocol),
                "--protocol-sha256",
                analysis.digest(protocol),
                "--pilot-repository-root",
                str(root / "absent"),
                "--eligibility-ledger",
                str(root / ledger_name),
                "--eligibility-sha256",
                S,
                "--approval",
                str(approval),
                "--approval-sha256",
                analysis.digest(approval),
                "--run-id",
                "owned-synthetic-gate",
                "--output",
                str(root / "must-not-exist.json"),
            ]
            with patch("sys.argv", argv):
                with self.assertRaises(ValueError):
                    analysis.main()
            self.assertFalse((root / "must-not-exist.json").exists())

    def test_real_calculation_requires_final_authorization(self):
        self.attempt("unauthorized")

    def test_changed_program_rejected_before_any_scores_read(self):
        self.attempt("wrong_program")

    def test_mutable_current_snapshot_rejected(self):
        self.attempt("current")


class VerifiedReadTests(unittest.TestCase):
    def test_read_requests_only_limit_plus_one(self):
        requests = []

        class Reader(io.BytesIO):
            def read(self, size=-1):
                requests.append(size)
                return super().read(size)

        with patch.object(Path, "open", return_value=Reader(b"x" * 1000)):
            with self.assertRaisesRegex(ValueError, "bounded byte limit"):
                analysis.read_verified("owned-synthetic-input", limit=32)
        self.assertEqual(requests, [33])

    def test_exact_boundary_and_default_limit_plus_one(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "owned-input.json"
            raw = b"{}" + b" " * 30
            path.write_bytes(raw)
            value = analysis.read_verified(path, hashlib.sha256(raw).hexdigest(), 32, limit=32)
            self.assertEqual(analysis.parse_verified_json(value), {})
            with path.open("wb") as handle:
                handle.seek(analysis.INPUT_LIMIT)
                handle.write(b"x")
            with self.assertRaisesRegex(ValueError, "bounded byte limit"):
                analysis.read_verified(path)

    def test_verified_replaced_file_cannot_change_parsing_or_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "input.json"
            raw = b'{"owned_value":1}'
            path.write_bytes(raw)
            digest = hashlib.sha256(raw).hexdigest()
            bound = analysis.read_bindings(
                root, [{"relative_path": "input.json", "sha256": digest, "bytes": len(raw)}]
            )
            path.write_bytes(b'{"owned_value":999}')
            with patch.object(
                analysis, "read_verified", side_effect=AssertionError("unexpected second read")
            ):
                self.assertEqual(
                    analysis.parse_verified_json(bound["input.json"]), {"owned_value": 1}
                )
                self.assertEqual(bound["input.json"].sha256, digest)
                self.assertEqual(bound["input.json"].raw, raw)

    def test_duplicate_binding_basename_cannot_overwrite_verified_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bindings = []
            for directory in ("one", "two"):
                (root / directory).mkdir()
                raw = json.dumps({"owned": directory}).encode()
                (root / directory / "input.json").write_bytes(raw)
                bindings.append(
                    {
                        "relative_path": directory + "/input.json",
                        "bytes": len(raw),
                        "sha256": hashlib.sha256(raw).hexdigest(),
                    }
                )
            with self.assertRaisesRegex(ValueError, "duplicate.*basename"):
                analysis.read_bindings(root, bindings)

    def test_explicit_utc_zero_offset_required(self):
        self.assertEqual(
            analysis.utc("2026-01-01T00:00:00Z"), analysis.utc("2026-01-01T00:00:00+00:00")
        )
        for text in ("2026-01-01T08:00:00+08:00", "2026-01-01T00:00:00"):
            with self.assertRaises(ValueError):
                analysis.utc(text)

    def test_owned_synthetic_full_cli_keeps_same_verified_bytes_after_replacement(self):
        """All39 identities/scores below are self-created, never real pilot inputs."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pilot = root / "owned-pilot"
            pilot.mkdir()
            ids, score_rows, execution_rows = {}, [], []
            score_prototypes = scores()["tasks"]
            execution_prototype = ledger()["tasks"][0]
            for index in range(39):
                name = "owned-synthetic-task-" + str(index)
                identity = {
                    "instance_id": name,
                    "repo": "owned-repo-" + str(index % 2),
                    "base_commit": "c" * 40,
                }
                ids[name] = identity
                row = copy.deepcopy(score_prototypes[index % len(score_prototypes)])
                row.update(instance_id=name, repo=identity["repo"])
                score_rows.append(row)
                execution = copy.deepcopy(execution_prototype)
                execution.update(
                    **identity,
                    original_F2P=49 if index == 0 else 1,
                    original_P2P=5804 if index == 0 else 1,
                )
                execution_rows.append(execution)
            original_protocol = {
                "selection": {"tasks": list(ids.values())},
                "methods": list(analysis.METHODS),
                "budgets": list(analysis.BUDGETS),
            }
            frozen_scores = {"tasks": score_rows}
            validated = analysis.validate_scores(frozen_scores, ids)
            reference = analysis.view(
                validated, set(ids), sorted({r["repo"] for r in ids.values()})
            )
            frozen_summary = {
                "macro": [
                    {"method": c["method"], "budget": c["budget"], "line": c["repo_macro"]}
                    for c in reference["method_budget_cells"]
                ]
            }
            original_inputs = {
                "protocol.json": original_protocol,
                "scores.json": frozen_scores,
                "summary.json": frozen_summary,
            }
            bindings, original_hashes = [], {}
            for name, value in original_inputs.items():
                raw = json.dumps(value).encode()
                (pilot / name).write_bytes(raw)
                original_hashes[name] = hashlib.sha256(raw).hexdigest()
                bindings.append(
                    {"relative_path": name, "sha256": original_hashes[name], "bytes": len(raw)}
                )
            protocol = root / "secondary.json"
            protocol.write_text(
                json.dumps({"original_primary_immutable": {"source_bindings": bindings}})
            )
            final = ledger()
            final.update(
                tasks=execution_rows,
                original_pilot_protocol_sha256=original_hashes["protocol.json"],
                original_pilot_scores_sha256=original_hashes["scores.json"],
            )
            ledger_path = root / "owned-final-ledger.json"
            ledger_path.write_text(json.dumps(final))
            approval = root / "owned-approval.json"
            approval.write_text(
                json.dumps(
                    {
                        "action": "authorize_one_final_secondary_calculation",
                        "allow_real_inputs": True,
                        "protocol_sha256": analysis.digest(protocol),
                        "eligibility_ledger_sha256": analysis.digest(ledger_path),
                        "analysis_program_sha256": analysis.digest(analysis.__file__),
                    }
                )
            )
            output = root / "owned-result.json"
            argv = [
                "analyze_sensitivity.py",
                "--protocol",
                str(protocol),
                "--protocol-sha256",
                analysis.digest(protocol),
                "--pilot-repository-root",
                str(pilot),
                "--eligibility-ledger",
                str(ledger_path),
                "--eligibility-sha256",
                analysis.digest(ledger_path),
                "--approval",
                str(approval),
                "--approval-sha256",
                analysis.digest(approval),
                "--run-id",
                "owned-synthetic-read-race",
                "--output",
                str(output),
            ]
            original_reader = analysis.read_verified
            original_bindings_reader = analysis.read_bindings
            replaced = False

            def checked_reader(path, *args, **kwargs):
                if replaced and Path(path) in {pilot / name for name in original_inputs}:
                    raise AssertionError("reopened replaced measurement input")
                return original_reader(path, *args, **kwargs)

            def replace_after_verification(*args, **kwargs):
                nonlocal replaced
                values = original_bindings_reader(*args, **kwargs)
                for name in original_inputs:
                    (pilot / name).write_text('{"unverified_replacement":true}')
                replaced = True
                return values

            with (
                patch("sys.argv", argv),
                patch.object(analysis, "read_verified", side_effect=checked_reader),
                patch.object(analysis, "read_bindings", side_effect=replace_after_verification),
                redirect_stdout(io.StringIO()),
            ):
                analysis.main()
            result = json.loads(output.read_text())
            self.assertEqual(result["original_tasks"], 39)
            self.assertEqual(
                result["provenance"]["original_scores_sha256"], original_hashes["scores.json"]
            )
            self.assertEqual(
                result["provenance"]["original_summary_sha256"], original_hashes["summary.json"]
            )
            self.assertEqual(
                {
                    n: r["sha256"]
                    for n, r in result["provenance"]["verified_original_inputs"].items()
                },
                original_hashes,
            )


if __name__ == "__main__":
    unittest.main()
