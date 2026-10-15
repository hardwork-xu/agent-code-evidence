"""Owned runtime counterexamples; no resolver or upstream source is executed.

自编运行时反例；不导入 resolver，不执行上游源码，不将单元测试当自然样本。
"""

import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import threading
import types

import pytest

from benchmarks.semantic_observer import GlobalReadObserver, ObserverError, encode_primitive
from benchmarks.semantic_observer import observer as implementation


def require_runtime():
    if sys.implementation.name != "cpython" or sys.version_info[:2] != (3, 12):
        pytest.skip("Runtime observations explicitly support only CPython 3.12")


def program(tmp_path, source, *, max_observations=10_000, namespace=None):
    require_runtime()
    path = tmp_path / "owned.py"
    raw = source.encode("utf-8")
    path.write_bytes(raw)
    namespace = {"__name__": "owned_observer_fixture"} if namespace is None else namespace
    exec(compile(raw, str(path), "exec", dont_inherit=True, optimize=sys.flags.optimize), namespace)
    observer = GlobalReadObserver(source_root=tmp_path,
        source_pins={"owned.py": hashlib.sha256(raw).hexdigest()},
        max_observations=max_observations)
    return namespace, observer, path


def reads(report, name):
    return [record for record in report["observations"] if record["name"] == name]


@pytest.mark.parametrize(("value", "expected"), [
    (None, {"status": "supported", "type": "none", "value": None}),
    (True, {"status": "supported", "type": "bool", "value": True}),
    (1, {"status": "supported", "type": "int", "decimal": "1"}),
    (-7, {"status": "supported", "type": "int", "decimal": "-7"}),
    (0.0, {"status": "supported", "type": "float", "hex": "0x0.0p+0"}),
    (-0.0, {"status": "supported", "type": "float", "hex": "-0x0.0p+0"}),
    (-2.5, {"status": "supported", "type": "float", "hex": "-0x1.4000000000000p+1"}),
])
def test_exact_primitive_codec(value, expected):
    assert encode_primitive(value) == expected


def test_strings_bytes_use_only_hash_and_explicit_length():
    private = "not-a-public-path/é\ud800"
    encoded = encode_primitive(private)
    assert encoded == {"status": "supported", "type": "str", "length": len(private),
        "byte_length": len(private.encode("utf-8", "surrogatepass")),
        "sha256": hashlib.sha256(private.encode("utf-8", "surrogatepass")).hexdigest(),
        "encoding": "utf-8-surrogatepass"}
    assert private not in json.dumps(encoded)
    assert encode_primitive(b"abc") == {"status": "supported", "type": "bytes", "length": 3,
        "byte_length": 3, "sha256": hashlib.sha256(b"abc").hexdigest()}
    assert encode_primitive("abc") != encode_primitive(b"abc")


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_codec_is_explicitly_unsupported(value):
    assert encode_primitive(value) == {"status": "unsupported", "type": "float",
        "reason": "non_finite_float", "bits": struct.pack(">d", value).hex()}
    json.dumps(encode_primitive(value), allow_nan=False)


def test_value_limits_are_not_silent_coercions():
    assert encode_primitive(1 << implementation.MAX_INT_BITS)["reason"] == "integer_bit_limit"
    for value in ["x" * (implementation.MAX_VALUE_BYTES + 1),
                  b"x" * (implementation.MAX_VALUE_BYTES + 1),
                  "é" * implementation.MAX_VALUE_BYTES]:
        assert encode_primitive(value)["reason"] == "value_byte_limit"


def test_codec_never_calls_subclass_or_other_user_hooks():
    class DangerousInt(int):
        def __repr__(self):
            raise AssertionError("repr executed")

        def __str__(self):
            raise AssertionError("str executed")

        def __eq__(self, other):
            raise AssertionError("eq executed")

        def __getattribute__(self, name):
            raise AssertionError("attribute executed")

    class DangerousMeta(type):
        def __getattribute__(self, name):
            raise AssertionError("metaclass attribute executed")

        def __eq__(self, other):
            raise AssertionError("metaclass equality executed")

    class Dangerous(metaclass=DangerousMeta):
        def __repr__(self):
            raise AssertionError("object repr executed")

    for value in [DangerousInt(4), Dangerous(), [], {}, object()]:
        assert encode_primitive(value) == {"status": "unsupported", "type": "other",
                                          "reason": "non_exact_primitive"}


def test_real_global_change_aggregates_each_value_and_exact_positions(tmp_path):
    namespace, observer, path = program(tmp_path, "X = 3\ndef read():\n    return X\n")
    with observer:
        assert namespace["read"]() == 3
        namespace["X"] = -8
        assert namespace["read"]() == -8
        assert namespace["read"]() == -8
    report = observer.report()
    rows = reads(report, "X")
    assert report["measurement_valid"] and report["complete"]
    assert report["counts"]["eligible_load_global_events"] == 3
    assert report["counts"]["retained_events"] == 3
    assert report["counts"]["retained_observations"] == 2
    assert [(row["value"]["decimal"], row["count"], row["first_event"], row["last_event"])
            for row in rows] == [("3", 1, 1, 1), ("-8", 2, 2, 3)]
    for row in rows:
        assert row["binding"] == "module_global" and row["certified_code"]
        assert row["source_path"] == "owned.py"
        assert row["source_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert row["qualname"] == "read" and row["function_name"] == "read"
        assert (row["lineno"], row["end_lineno"], row["col_offset"], row["end_col_offset"]) == (
            3, 3, 11, 12)
        assert len(row["code_signature"]) == 64 and row["bytecode_offset"] >= 0
        assert row["event_kind"] == "pre_op_binding"
    assert str(tmp_path) not in json.dumps(report)
    assert report["event_semantics"] == "pre_op_binding_not_consumed_operand"


@pytest.mark.parametrize("no_debug_ranges", [False, True])
def test_first_trace_installation_in_fresh_process_emits_opcode_events(tmp_path, no_debug_ranges):
    require_runtime()
    raw = b"X = 1\ndef read():\n    return X\n"
    (tmp_path / "owned.py").write_bytes(raw)
    script = """
import hashlib, json, pathlib, sys
sys.path.insert(0, sys.argv[1])
from benchmarks.semantic_observer import GlobalReadObserver
path = pathlib.Path(sys.argv[2]) / 'owned.py'
raw = path.read_bytes()
namespace = {}
exec(compile(raw, str(path), 'exec', dont_inherit=True, optimize=sys.flags.optimize), namespace)
with GlobalReadObserver(source_root=path.parent,
        source_pins={'owned.py': hashlib.sha256(raw).hexdigest()}) as observer:
    assert namespace['read']() == 1
report = observer.report()
assert report['counts']['eligible_load_global_events'] == 1, report
assert report['measurement_valid'], report
if sys.argv[3] == 'partial':
    assert not report['complete'] and report['counts']['partial_position_events'] == 1, report
    assert not report['observations'][0]['position_complete'], report
else:
    assert report['complete'], report
assert sys.gettrace() is None
print(json.dumps({'events': report['counts']['eligible_load_global_events']}))
"""
    flags = ["-X", "no_debug_ranges"] if no_debug_ranges else []
    child = subprocess.run([sys.executable, "-I", "-B", *flags, "-c", script,
                            str(Path(__file__).resolve().parents[1]), str(tmp_path),
                            "partial" if no_debug_ranges else "full"],
                           capture_output=True, text=True, timeout=15)
    assert child.returncode == 0, child.stdout + child.stderr
    assert json.loads(child.stdout) == {"events": 1}


def test_same_line_load_sites_and_dynamic_namespace_mutation(tmp_path):
    source = "X = 1\ndef read():\n    a = X; globals()['X'] = 2; return a, X\n"
    namespace, observer, _ = program(tmp_path, source)
    with observer:
        assert namespace["read"]() == (1, 2)
    report = observer.report()
    rows = reads(report, "X")
    assert [row["value"]["decimal"] for row in rows] == ["1", "2"]
    assert len({row["bytecode_offset"] for row in rows}) == 2
    assert len({row["col_offset"] for row in rows}) == 2
    assert reads(report, "globals")[0]["status"] == "builtin_fallback"


def test_unsupported_runtime_values_are_not_filtered_out(tmp_path):
    namespace, observer, _ = program(tmp_path, "X = []\ndef read():\n    return X\n")
    with observer:
        assert namespace["read"]() is namespace["X"]
        namespace["X"] = float("nan")
        assert type(namespace["read"]()) is float
    rows = reads(observer.report(), "X")
    assert [row["status"] for row in rows] == ["unsupported_value", "unsupported_value"]
    assert [row["value"]["reason"] for row in rows] == ["non_exact_primitive", "non_finite_float"]
    assert observer.report()["counts"]["status_counts"] == {"unsupported_value": 2}


def test_deleted_global_builtin_fallback_and_missing_load_are_retained(tmp_path):
    namespace, observer, _ = program(tmp_path,
        "len = 17\nX = 5\ndef builtin():\n    return len\ndef missing():\n    return X\n")
    with observer:
        assert namespace["builtin"]() == 17
        del namespace["len"]
        assert namespace["builtin"]() is len
        del namespace["X"]
        with pytest.raises(NameError):
            namespace["missing"]()
    report = observer.report()
    assert [row["binding"] for row in reads(report, "len")] == ["module_global", "builtin"]
    assert reads(report, "X")[0]["binding"] == "missing"
    assert reads(report, "X")[0]["status"] == "missing_binding"
    assert report["counts"]["exception_events"] >= 1
    assert "pre_op_event_does_not_prove_successful_load" in report["blind_spots"]


def test_exception_propagation_and_trace_cleanup(tmp_path):
    namespace, observer, _ = program(tmp_path,
        "X = 1\ndef fail():\n    result = X\n    raise ValueError('owned failure')\n")
    before = sys.gettrace()
    with pytest.raises(ValueError, match="owned failure"):
        with observer:
            namespace["fail"]()
    assert sys.gettrace() is before
    report = observer.report()
    assert report["integrity"]["body_raised"] and report["integrity"]["trace_intact_at_exit"]
    assert reads(report, "X")[0]["value"]["decimal"] == "1"


def test_constant_only_path_reports_no_observations(tmp_path):
    namespace, observer, _ = program(tmp_path, "def read():\n    return -6\n")
    with observer:
        assert namespace["read"]() == -6
    report = observer.report()
    assert report["no_observations"]
    assert report["counts"]["eligible_load_global_events"] == 0
    assert report["observations"] == []


def test_repeated_events_do_not_exhaust_distinct_record_bound(tmp_path):
    namespace, observer, _ = program(tmp_path, "X = 1\ndef read():\n    return X\n",
                                      max_observations=1)
    with observer:
        for _ in range(1000):
            assert namespace["read"]() == 1
    report = observer.report()
    assert report["counts"]["eligible_load_global_events"] == 1000
    assert report["counts"]["retained_observations"] == 1
    assert reads(report, "X")[0]["count"] == 1000
    assert report["counts"]["dropped_observations"] == 0 and report["complete"]


def test_cap_keeps_total_and_negative_status_counts_without_overwriting(tmp_path):
    namespace, observer, _ = program(tmp_path, "X = 1\ndef read():\n    return X\n",
                                      max_observations=1)
    with observer:
        assert namespace["read"]() == 1
        namespace["X"] = []
        namespace["read"]()
        namespace["read"]()
        namespace["X"] = 1
        assert namespace["read"]() == 1
    report = observer.report()
    assert not report["complete"] and report["measurement_valid"]
    assert report["counts"]["eligible_load_global_events"] == 4
    assert report["counts"]["retained_events"] == 2
    assert report["counts"]["dropped_observations"] == 2
    assert report["counts"]["status_counts"] == {"primitive": 2, "unsupported_value": 2}
    assert reads(report, "X")[0]["value"]["decimal"] == "1"
    assert reads(report, "X")[0]["count"] == 2


def test_source_drift_invalidates_measurement_without_hiding_records(tmp_path):
    namespace, observer, path = program(tmp_path, "X = 1\ndef read():\n    return X\n")
    with observer:
        assert namespace["read"]() == 1
        path.write_text("X = 2\ndef read():\n    return X\n")
    report = observer.report()
    assert not report["measurement_valid"] and not report["complete"]
    assert report["integrity"]["source_changed"] == ["owned.py"]
    assert len(reads(report, "X")) == 1


def test_initial_source_mismatch_rejects_before_trace(tmp_path):
    _, observer, path = program(tmp_path, "X = 1\ndef read():\n    return X\n")
    path.write_text("X = 9\n")
    before = sys.gettrace()
    with pytest.raises(ObserverError, match="Initial source SHA mismatch"):
        with observer:
            pytest.fail("must not enter")
    assert sys.gettrace() is before


def test_same_filename_dynamic_code_cannot_inherit_source_certification(tmp_path):
    namespace, observer, path = program(tmp_path, "X = 1\ndef read():\n    return X\n")
    forged = {}
    exec(compile("X = 9\ndef read():\n    unused = 0\n    return X\n", str(path), "exec"), forged)
    with observer:
        assert namespace["read"]() == 1
        assert forged["read"]() == 9
    report = observer.report()
    assert [row["certified_code"] for row in reads(report, "X")] == [True, False]
    assert reads(report, "X")[1]["binding"] == "uninspected"
    assert report["counts"]["uncertified_code_events"] == 1
    assert not report["complete"]


def test_dynamic_code_constants_never_enter_dis_repr(tmp_path):
    namespace, observer, _ = program(tmp_path,
        "X = 1\ndef read():\n    ignored = 3\n    return X\n")

    class Dangerous:
        def __repr__(self):
            raise AssertionError("dynamic constant repr executed")

        def __eq__(self, other):
            raise AssertionError("dynamic constant equality executed")

    original = namespace["read"].__code__
    constants = tuple(Dangerous() if item == 3 else item for item in original.co_consts)
    altered = types.FunctionType(original.replace(co_consts=constants), namespace)
    with observer:
        assert altered() == 1
    report = observer.report()
    assert report["integrity"]["observer_errors"] == 0
    assert reads(report, "X")[0]["status"] == "uncertified_code"


def test_code_filename_subclass_never_invokes_user_hash_or_equality(tmp_path):
    namespace, observer, path = program(tmp_path, "X = 1\ndef read():\n    return X\n")
    hooks = []

    class Filename(str):
        def __hash__(self):
            hooks.append("hash")
            return str.__hash__(self)

        def __eq__(self, other):
            hooks.append("eq")
            return str.__eq__(self, other)

    revised = namespace["read"].__code__.replace(co_filename=Filename(str(path)))
    altered = types.FunctionType(revised, namespace)
    with observer:
        assert altered() == 1
    assert hooks == []
    report = observer.report()
    assert report["counts"]["unsupported_filename_events"] >= 1
    assert not report["complete"]


@pytest.mark.parametrize("field", ["co_name", "co_qualname"])
def test_code_metadata_string_subclass_is_explicitly_uncertified(tmp_path, field):
    namespace, observer, _ = program(tmp_path, "X = 1\ndef read():\n    return X\n")

    class Metadata(str):
        def __repr__(self):
            raise AssertionError("metadata repr executed")

        def __str__(self):
            raise AssertionError("metadata str executed")

    revised = namespace["read"].__code__.replace(**{field: Metadata("read")})
    altered = types.FunctionType(revised, namespace)
    with observer:
        assert altered() == 1
    report = observer.report()
    assert reads(report, "X")[0]["status"] == "uncertified_code"
    assert not report["complete"]


def test_namespace_non_string_collision_is_not_looked_up(tmp_path):
    namespace, observer, _ = program(tmp_path, "X = 1\ndef read():\n    return X\n")

    class Collision:
        def __hash__(self):
            return hash("not-a-global")

        def __eq__(self, other):
            raise AssertionError("namespace equality executed")

    namespace[Collision()] = object()
    with observer:
        assert namespace["read"]() == 1
    row = reads(observer.report(), "X")[0]
    assert row["status"] == "unsupported_namespace" and row["binding"] == "uninspected"


def test_existing_trace_is_preserved_and_nested_observers_refused(tmp_path):
    _, observer, _ = program(tmp_path, "X = 1\n")
    prior = sys.gettrace()

    def existing(frame, event, arg):
        return existing

    try:
        sys.settrace(existing)
        with pytest.raises(ObserverError, match="Existing trace"):
            with observer:
                pytest.fail("must not enter")
        assert sys.gettrace() is existing
    finally:
        sys.settrace(prior)


def test_trace_replacement_is_explicit_invalid_and_cleaned_up(tmp_path):
    namespace, observer, _ = program(tmp_path, "X = 1\ndef read():\n    return X\n")
    prior = sys.gettrace()
    with observer:
        namespace["read"]()
        sys.settrace(None)
        namespace["read"]()
    report = observer.report()
    assert sys.gettrace() is prior
    assert not report["integrity"]["trace_intact_at_exit"]
    assert not report["measurement_valid"] and not report["complete"]
    assert report["counts"]["eligible_load_global_events"] == 1


def test_threads_existing_at_entry_are_refused(tmp_path):
    _, observer, _ = program(tmp_path, "X = 1\n")
    done = threading.Event()
    child = threading.Thread(target=done.wait)
    child.start()
    try:
        with pytest.raises(ObserverError, match="Concurrent threads"):
            with observer:
                pytest.fail("must not enter")
    finally:
        done.set()
        child.join(timeout=5)
    assert not child.is_alive()


def test_thread_seen_during_body_invalidates_measurement(tmp_path):
    namespace, observer, _ = program(tmp_path, "X = 1\ndef read():\n    return X\n")
    done = threading.Event()
    child = threading.Thread(target=done.wait)
    try:
        with observer:
            child.start()
            assert namespace["read"]() == 1
            done.set()
            child.join(timeout=5)
    finally:
        done.set()
        child.join(timeout=5)
    report = observer.report()
    assert report["integrity"]["other_threads_seen"]
    assert not report["measurement_valid"] and not report["complete"]


def test_compiled_nested_functions_future_flags_and_signed_zero(tmp_path):
    namespace, observer, _ = program(tmp_path,
        'from __future__ import annotations\nX = -0.0\ndef outer():\n'
        '    def inner(x: "ignored"):\n        return X\n    return inner(1)\n')
    with observer:
        assert struct.pack(">d", namespace["outer"]()) == bytes.fromhex("8000000000000000")
    row = reads(observer.report(), "X")[0]
    assert row["qualname"] == "outer.<locals>.inner" and row["certified_code"]
    assert row["value"] == {"status": "supported", "type": "float", "hex": "-0x0.0p+0"}


def test_extended_arg_load_global_decodes_actual_name(tmp_path):
    names = [f"G{index}" for index in range(150)]
    source = "\n".join(f"{name} = {index}" for index, name in enumerate(names))
    source += "\ndef read():\n    return " + " + ".join(names) + "\n"
    namespace, observer, _ = program(tmp_path, source)
    with observer:
        assert namespace["read"]() == sum(range(150))
    report = observer.report()
    assert report["counts"]["eligible_load_global_events"] == 150
    assert {row["name"] for row in report["observations"]} == set(names)
    assert reads(report, "G149")[0]["value"]["decimal"] == "149"


@pytest.mark.parametrize("relative", ["../bad.py", "/bad.py", "a//bad.py", "./bad.py",
                                      "a\\bad.py", "a:bad.py", "bad\x00.py"])
def test_unreviewed_paths_are_refused(tmp_path, relative):
    require_runtime()
    observer = GlobalReadObserver(source_root=tmp_path, source_pins={relative: "0" * 64})
    with pytest.raises(ObserverError):
        with observer:
            pytest.fail("must not enter")


def test_symlink_source_and_source_size_limit_refused(tmp_path, monkeypatch):
    require_runtime()
    raw = b"X = 1\n"
    path = tmp_path / "real.py"
    path.write_bytes(raw)
    (tmp_path / "linked.py").symlink_to(path)
    observer = GlobalReadObserver(source_root=tmp_path,
                                  source_pins={"linked.py": hashlib.sha256(raw).hexdigest()})
    with pytest.raises(ObserverError, match="symlinks"):
        with observer:
            pytest.fail("must not enter")
    monkeypatch.setattr(implementation, "MAX_SOURCE_BYTES", 2)
    observer = GlobalReadObserver(source_root=tmp_path,
                                  source_pins={"real.py": hashlib.sha256(raw).hexdigest()})
    with pytest.raises(ObserverError, match="Source byte limit"):
        with observer:
            pytest.fail("must not enter")


def test_read_once_compiles_the_same_pinned_bytes(tmp_path, monkeypatch):
    require_runtime()
    raw = b"raise RuntimeError('compile must never execute source')\nX = 1\n"
    path = tmp_path / "owned.py"
    path.write_bytes(raw)
    reader = implementation._read_source
    calls = []

    def read_and_swap(source_path):
        found = reader(source_path)
        calls.append(found)
        if len(calls) == 1:
            source_path.write_bytes(b"invalid python !!!\n")
        return found

    monkeypatch.setattr(implementation, "_read_source", read_and_swap)
    observer = GlobalReadObserver(source_root=tmp_path,
                                  source_pins={"owned.py": hashlib.sha256(raw).hexdigest()})
    with observer:
        pass
    assert calls == [raw, b"invalid python !!!\n"]
    assert not observer.report()["measurement_valid"]


def test_observer_is_single_use_report_detached_and_runtime_refusal(tmp_path, monkeypatch):
    namespace, observer, _ = program(tmp_path, "X = 1\ndef read():\n    return X\n")
    with observer:
        namespace["read"]()
    report = observer.report()
    report["observations"][0]["count"] = 100
    assert observer.report()["observations"][0]["count"] == 1
    with pytest.raises(ObserverError, match="single-use"):
        with observer:
            pytest.fail("must not enter")
    monkeypatch.setattr(sys, "version_info", (3, 13, 0))
    other = GlobalReadObserver(source_root=tmp_path, source_pins={"owned.py": "0" * 64})
    with pytest.raises(ObserverError, match="Only CPython 3.12"):
        with other:
            pytest.fail("must not enter")


@pytest.mark.parametrize("bound", [0, -1, True, 100_001, 1.0])
def test_observation_bounds_are_validated(tmp_path, bound):
    with pytest.raises(ObserverError, match="observation bound"):
        GlobalReadObserver(source_root=Path(tmp_path), source_pins={"owned.py": "0" * 64},
                           max_observations=bound)


def test_source_file_bound_uses_declared_limit(tmp_path):
    pins = {f"file{index}.py": "0" * 64 for index in range(implementation.MAX_SOURCE_FILES)}
    observer = GlobalReadObserver(source_root=tmp_path, source_pins=pins)
    assert observer.report()["limits"]["source_files"] == implementation.MAX_SOURCE_FILES
    with pytest.raises(ObserverError, match="source pin set"):
        GlobalReadObserver(source_root=tmp_path, source_pins={**pins, "overflow.py": "0" * 64})


def test_total_source_bound_and_compiled_code_bound_are_enforced(tmp_path, monkeypatch):
    require_runtime()
    raw = b"X = 1\n"
    pins = {}
    for name in ["one.py", "two.py"]:
        (tmp_path / name).write_bytes(raw)
        pins[name] = hashlib.sha256(raw).hexdigest()
    monkeypatch.setattr(implementation, "MAX_TOTAL_SOURCE_BYTES", len(raw))
    with pytest.raises(ObserverError, match="Total source byte limit"):
        with GlobalReadObserver(source_root=tmp_path, source_pins=pins):
            pytest.fail("must not enter")
    monkeypatch.setattr(implementation, "MAX_TOTAL_SOURCE_BYTES", 16_777_216)
    monkeypatch.setattr(implementation, "MAX_CODE_OBJECTS", 1)
    with GlobalReadObserver(source_root=tmp_path, source_pins={"one.py": pins["one.py"]}):
        pass
    source = b"def read():\n    return X\n"
    (tmp_path / "one.py").write_bytes(source)
    with pytest.raises(ObserverError, match="Code object limit"):
        with GlobalReadObserver(source_root=tmp_path,
                source_pins={"one.py": hashlib.sha256(source).hexdigest()}):
            pytest.fail("must not enter")


def test_runtime_code_cache_bound_is_explicitly_uncertified(tmp_path, monkeypatch):
    namespace, observer, _ = program(tmp_path, "X = 1\ndef read():\n    return X\n")
    with observer:
        monkeypatch.setattr(implementation, "MAX_CODE_OBJECTS", 0)
        assert namespace["read"]() == 1
    report = observer.report()
    assert not report["complete"]
    assert reads(report, "X")[0]["value"]["reason"] == "code_cache_limit"
