"""Independent observer counterexamples / 独立观测反例。

These execute only authored fixed fixtures, never upstream or evaluator tasks.
只执行自编固定夹具；不执行上游，也不读取 evaluator 未见任务。
"""
import hashlib
from pathlib import Path
import sys
import threading

import pytest

from benchmarks.semantic_observer import GlobalReadObserver, ObserverError, encode_primitive
from benchmarks.semantic_observer.methods import evaluate_pair


runtime_only = pytest.mark.skipif(
    sys.implementation.name != "cpython" or sys.version_info[:2] != (3, 12),
    reason="Runtime observer is explicitly CPython3.12-only; not a passing semantic result")


def prepared(tmp_path, source):
    path = tmp_path / "observed.py"
    raw = source.encode()
    path.write_bytes(raw)
    namespace = {"__name__": "owned_observer_fixture"}
    exec(compile(raw, str(path.resolve()), "exec", dont_inherit=True,
                 optimize=sys.flags.optimize), namespace)
    observer = GlobalReadObserver(source_root=tmp_path,
                                  source_pins={path.name: hashlib.sha256(raw).hexdigest()})
    return observer, namespace, path


def x_reads(report, qualname="read"):
    return [row for row in report["observations"] if row["qualname"] == qualname and row["name"] == "X"]


@runtime_only
def test_same_line_repeated_reads_keep_changed_values_and_real_offsets(tmp_path):
    source = ("X=1\ndef change():\n    globals()['X']=2\n    return 0\n"
              "def read():\n    return X + change() + X\n")
    observer, namespace, _ = prepared(tmp_path, source)
    with observer:
        assert namespace["read"]() == 3
    report = observer.report()
    reads = x_reads(report)
    assert len(reads) == 2
    assert {row["value"]["decimal"] for row in reads} == {"1", "2"}
    assert len({row["bytecode_offset"] for row in reads}) == 2
    assert len({row["lineno"] for row in reads}) == 1
    assert all(row["certified_code"] and row["event_kind"] == "pre_op_binding" for row in reads)
    # The real graph's one collapsed read fact does not erase the counterexample.
    # 真实图按名字折叠的单条事实，不得抹去第二次读取的不同状态。
    method = evaluate_pair({"observed.py": source}, {"observed.py": source}, repeats=1)
    facts = method["methods"]["currentfresh"]["runs"][0]["versions"]["after"]["facts"]
    expected, = [f["expected"] for f in facts if f["qualname"] == "read" and f["name"] == "X"]
    assert expected == encode_primitive(1)
    assert sum(row["value"] != expected for row in reads) == 1


@runtime_only
def test_builtin_fallback_is_not_a_module_binding(tmp_path):
    observer, namespace, _ = prepared(tmp_path, "X=1\ndef read():\n    return X\n")
    namespace.pop("X")
    namespace["__builtins__"] = {"X": 7}
    # Recompile/exec defines a function using this actual builtin mapping.
    # 函数创建时绑定其 builtin 字典，不将后改 __builtins__ 猜成已生效。
    path = tmp_path / "observed.py"
    exec(compile(path.read_bytes(), str(path.resolve()), "exec", dont_inherit=True), namespace)
    namespace.pop("X")
    with observer:
        assert namespace["read"]() == 7
    read, = x_reads(observer.report())
    assert read["binding"] == "builtin" and read["status"] == "builtin_fallback"
    assert read["value"]["status"] == "unsupported"


@runtime_only
def test_name_error_still_has_pre_op_missing_state_not_a_successful_read(tmp_path):
    observer, namespace, _ = prepared(tmp_path, "def read():\n    return X\n")
    with observer:
        with pytest.raises(NameError):
            namespace["read"]()
    report = observer.report()
    read, = x_reads(report)
    assert read["binding"] == "missing" and read["status"] == "missing_binding"
    assert report["counts"]["exception_events"] >= 1
    assert report["event_semantics"] == "pre_op_binding_not_consumed_operand"


@runtime_only
def test_same_filename_with_changed_code_is_uncertified(tmp_path):
    observer, namespace, path = prepared(tmp_path, "X=1\ndef read():\n    return X\n")
    forged = compile("def read():\n    return X + 9\n", str(path.resolve()), "exec", dont_inherit=True)
    exec(forged, namespace)
    with observer:
        assert namespace["read"]() == 10
    report = observer.report()
    read, = x_reads(report)
    assert not read["certified_code"] and read["binding"] == "uninspected"
    assert read["status"] == "uncertified_code"
    assert not report["complete"]


@runtime_only
def test_dynamic_code_with_hostile_unused_constant_is_never_formatted(tmp_path):
    observer, namespace, _ = prepared(tmp_path, "X=1\ndef read():\n    return X\n")

    class Hostile:
        def __repr__(self):
            raise AssertionError("observer must never repr this value")

        def __eq__(self, other):
            raise AssertionError("observer must never compare this value")

    old = namespace["read"].__code__
    namespace["read"].__code__ = old.replace(co_consts=(*old.co_consts, Hostile()))
    with observer:
        assert namespace["read"]() == 1
    read, = x_reads(observer.report())
    assert not read["certified_code"]
    assert read["status"] == "uncertified_code"


@runtime_only
def test_capacity_counts_dropped_states_but_retains_repeated_existing_state(tmp_path):
    original, namespace, path = prepared(tmp_path, "X=1\ndef read():\n    return X\n")
    observer = GlobalReadObserver(source_root=tmp_path, source_pins=original.report()["source_pins"],
                                  max_observations=1)
    with observer:
        for value in [1, 2, 3, 1, 1]:
            namespace["X"] = value
            assert namespace["read"]() == value
    report = observer.report()
    read, = x_reads(report)
    assert read["count"] == 3
    assert report["counts"]["eligible_load_global_events"] == 5
    assert report["counts"]["retained_events"] == 3
    assert report["counts"]["dropped_observations"] == 2
    assert report["measurement_valid"] and not report["complete"]
    assert path.is_file()


@runtime_only
def test_no_load_global_observation_is_explicit_not_positive_evidence(tmp_path):
    observer, namespace, _ = prepared(tmp_path, "def read():\n    return 42\n")
    with observer:
        assert namespace["read"]() == 42
    report = observer.report()
    assert report["no_observations"]
    assert report["counts"]["eligible_load_global_events"] == 0
    assert report["observations"] == []


@runtime_only
def test_original_failure_propagates_and_source_change_invalidates_measurement(tmp_path):
    observer, namespace, path = prepared(tmp_path, "X=1\ndef read():\n    raise ValueError(X)\n")
    with pytest.raises(ValueError):
        with observer:
            namespace["read"]()
    assert observer.report()["integrity"]["body_raised"]
    second, namespace, path = prepared(tmp_path, "X=1\ndef read():\n    return X\n")
    with second:
        namespace["read"]()
        path.write_text("X=2\ndef read():\n    return X\n")
    report = second.report()
    assert not report["measurement_valid"]
    assert report["integrity"]["source_changed"] == [path.name]


@runtime_only
def test_target_disabling_trace_is_retained_as_measurement_failure(tmp_path):
    observer, namespace, _ = prepared(tmp_path, "import sys\nX=1\ndef read():\n    sys.settrace(None)\n    return X\n")
    previous = sys.gettrace()
    with observer:
        assert namespace["read"]() == 1
    report = observer.report()
    assert not report["measurement_valid"]
    assert not report["integrity"]["trace_intact_at_exit"]
    assert sys.gettrace() is previous


@runtime_only
def test_prior_trace_and_concurrent_thread_are_rejected_without_replacement(tmp_path):
    observer, _, _ = prepared(tmp_path, "X=1\ndef read():\n    return X\n")
    previous = sys.gettrace()
    def tracer(frame, event, arg):
        return None
    try:
        sys.settrace(tracer)
        with pytest.raises(ObserverError):
            observer.__enter__()
        assert sys.gettrace() is tracer
    finally:
        sys.settrace(previous)
    ready, stop = threading.Event(), threading.Event()

    def wait():
        ready.set()
        stop.wait(5)

    child = threading.Thread(target=wait)
    child.start()
    assert ready.wait(5)
    try:
        with pytest.raises(ObserverError):
            observer.__enter__()
    finally:
        stop.set()
        child.join(5)
    assert not child.is_alive()


@runtime_only
def test_non_string_namespace_key_is_explicitly_unsupported(tmp_path):
    observer, namespace, _ = prepared(tmp_path, "X=1\ndef read():\n    return X\n")
    namespace[object()] = "non-string namespace key"
    with observer:
        assert namespace["read"]() == 1
    read, = x_reads(observer.report())
    assert read["status"] == "unsupported_namespace"
    assert read["binding"] == "uninspected"


@runtime_only
def test_detached_report_does_not_allow_mutation_of_retained_evidence(tmp_path):
    observer, namespace, _ = prepared(tmp_path, "X=1\ndef read():\n    return X\n")
    with observer:
        namespace["read"]()
    report = observer.report()
    report["observations"][0]["count"] = 999
    report["source_pins"].clear()
    assert observer.report()["observations"][0]["count"] == 1
    assert observer.report()["source_pins"]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), 1 << 4097,
                                   [1], {"x": 1}, (1,), object()])
def test_unsupported_values_are_explicit(value):
    assert encode_primitive(value)["status"] == "unsupported"


def test_exact_types_signed_zero_and_opaque_string_bytes_codec():
    assert encode_primitive(True) != encode_primitive(1)
    assert encode_primitive(0.0) != encode_primitive(-0.0)
    assert encode_primitive(1) != encode_primitive(1.0)
    assert encode_primitive("private literal") != encode_primitive(b"private literal")
    assert "private literal" not in str(encode_primitive("private literal"))

    class IntSubclass(int):
        def __repr__(self):
            raise AssertionError("not an exact primitive")

    assert encode_primitive(IntSubclass(1))["status"] == "unsupported"


@runtime_only
def test_pinned_path_symlink_and_wrong_digest_fail_before_execution(tmp_path):
    _, _, path = prepared(tmp_path, "X=1\ndef read():\n    return X\n")
    observer = GlobalReadObserver(source_root=tmp_path, source_pins={path.name: "0" * 64})
    with pytest.raises(ObserverError):
        observer.__enter__()
    alias = Path(tmp_path) / "alias.py"
    alias.symlink_to(path)
    observer = GlobalReadObserver(source_root=tmp_path,
                                  source_pins={alias.name: hashlib.sha256(path.read_bytes()).hexdigest()})
    with pytest.raises(ObserverError):
        observer.__enter__()
