"""Observe pre-op LOAD_GLOBAL bindings, without a static resolver.

CPython 3.12 only. An opcode trace event precedes the instruction: a record is
neither a successfully consumed operand nor proof of necessary coding context.
Only reviewed source bytes and matching compiled code are certified. Threads,
native callbacks, asynchronous signals, hostile trace/builtin replacement and
changes restored between the two source checks remain explicit blind spots.

仅支持 CPython 3.12。opcode 事件发生于指令执行前，不证明值已被成功读取，
也不证明上下文必要性。仅认证受审源码及匹配的代码签名；本模块不是安全沙箱。
"""

from __future__ import annotations

import dis
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import struct
import sys
import threading
import types


MAX_INT_BITS = 4096
MAX_VALUE_BYTES = 1_048_576
MAX_SOURCE_BYTES = 1_048_576
MAX_TOTAL_SOURCE_BYTES = 16_777_216
MAX_SOURCE_FILES = 2048
MAX_CODE_OBJECTS = 100_000
MAX_NAMESPACE_ENTRIES = 100_000


class ObserverError(RuntimeError):
    """Rejected observer configuration / 观测配置被拒绝。"""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"),
                      allow_nan=False).encode("ascii")


def encode_primitive(value: object) -> dict:
    """Encode exact primitive values without repr, user equality or attributes.

    String/byte contents are never retained. Strings use UTF-8 surrogatepass;
    hashes permit equality checks, not recovery or proof of original contents.
    只编码精确内置类型，不调用用户 repr/eq/属性；字符串和字节仅保留哈希与长度。
    """
    kind = type(value)
    if value is None:
        return {"status": "supported", "type": "none", "value": None}
    if kind is bool:
        return {"status": "supported", "type": "bool", "value": value}
    if kind is int:
        if int.bit_length(value) > MAX_INT_BITS:
            return {"status": "unsupported", "type": "int", "reason": "integer_bit_limit"}
        return {"status": "supported", "type": "int", "decimal": str(value)}
    if kind is float:
        if not math.isfinite(value):
            return {"status": "unsupported", "type": "float", "reason": "non_finite_float",
                    "bits": struct.pack(">d", value).hex()}
        return {"status": "supported", "type": "float", "hex": float.hex(value)}
    if kind is str:
        if len(value) > MAX_VALUE_BYTES:
            return {"status": "unsupported", "type": "str", "reason": "value_byte_limit"}
        raw = str.encode(value, "utf-8", "surrogatepass")
        if len(raw) > MAX_VALUE_BYTES:
            return {"status": "unsupported", "type": "str", "reason": "value_byte_limit"}
        return {"status": "supported", "type": "str", "sha256": _sha(raw),
                "length": len(value), "byte_length": len(raw), "encoding": "utf-8-surrogatepass"}
    if kind is bytes:
        if len(value) > MAX_VALUE_BYTES:
            return {"status": "unsupported", "type": "bytes", "reason": "value_byte_limit"}
        return {"status": "supported", "type": "bytes", "sha256": _sha(value),
                "length": len(value), "byte_length": len(value)}
    return {"status": "unsupported", "type": "other", "reason": "non_exact_primitive"}


def _constant_signature(value: object) -> object:
    """Canonicalize compiler constants only; arbitrary objects are refused.

    编译器常量的签名；不对用户对象做 repr、相等比较或属性访问。
    """
    kind = type(value)
    if kind is types.CodeType:
        return {"code": _code_payload(value)}
    if kind is tuple:
        return {"tuple": [_constant_signature(item) for item in value]}
    if kind is frozenset:
        items = [_constant_signature(item) for item in value]
        return {"frozenset": sorted(items, key=_canonical)}
    if value is Ellipsis:
        return {"ellipsis": True}
    if kind is complex:
        return {"complex_bits": struct.pack(">dd", value.real, value.imag).hex()}
    if kind is float:
        return {"float_bits": struct.pack(">d", value).hex()}
    encoded = encode_primitive(value)
    if encoded["status"] != "supported":
        raise ObserverError("Unsupported code constant / 不支持的代码常量")
    return encoded


def _code_payload(code: types.CodeType) -> dict:
    # co_filename is bound separately to a pinned absolute path; it is not public.
    # 文件名另与固定路径绑定；公开签名不泄露绝对路径。
    if (type(code.co_filename) is not str or type(code.co_name) is not str
            or type(code.co_qualname) is not str or any(type(name) is not str
            for names in [code.co_names, code.co_varnames, code.co_freevars, code.co_cellvars]
            for name in names)):
        raise ObserverError("Non-exact code metadata / 代码元数据不是精确内置字符串")
    return {"bytecode": code.co_code.hex(), "constants": [
                _constant_signature(item) for item in code.co_consts],
            "name": code.co_name, "qualname": code.co_qualname,
            "firstlineno": code.co_firstlineno, "linetable": code.co_linetable.hex(),
            "exceptiontable": code.co_exceptiontable.hex(), "names": list(code.co_names),
            "varnames": list(code.co_varnames), "freevars": list(code.co_freevars),
            "cellvars": list(code.co_cellvars), "argcount": code.co_argcount,
            "posonlyargcount": code.co_posonlyargcount, "kwonlyargcount": code.co_kwonlyargcount,
            "nlocals": code.co_nlocals, "stacksize": code.co_stacksize, "flags": code.co_flags}


def _code_signature(code: types.CodeType) -> str:
    return _sha(_canonical(_code_payload(code)))


def _load_sites(code: types.CodeType) -> dict:
    """Decode 3.12 wordcode without dis formatting arbitrary LOAD_CONST values.

    dis.get_instructions formats constants with repr, even when only a global
    opcode is needed. Dynamic code constants therefore must not enter that API.
    直接解码 wordcode，避免 dis 格式化动态常量时调用用户 repr。
    """
    sites, extended = {}, 0
    positions = list(code.co_positions())
    raw = code.co_code
    for offset in range(0, len(raw), 2):
        opcode, low_arg = raw[offset], raw[offset + 1]
        argument = extended | low_arg
        if opcode == dis.EXTENDED_ARG:
            extended = argument << 8
            continue
        extended = 0
        if opcode == dis.opmap["LOAD_GLOBAL"]:
            index = argument >> 1
            if index >= len(code.co_names):
                raise ObserverError("Malformed LOAD_GLOBAL / 全局加载指令格式错误")
            sites[offset] = {"name": code.co_names[index], "position": positions[offset // 2]}
    return sites


def _walk_codes(code: types.CodeType):
    yield code
    for constant in code.co_consts:
        if type(constant) is types.CodeType:
            yield from _walk_codes(constant)


def _read_source(path: Path) -> bytes:
    with path.open("rb") as handle:
        raw = handle.read(MAX_SOURCE_BYTES + 1)
    if len(raw) > MAX_SOURCE_BYTES:
        raise ObserverError("Source byte limit exceeded / 超出源码字节上限")
    return raw


def _source_path(root: Path, relative: str) -> Path:
    if (type(relative) is not str or not relative or "\\" in relative or ":" in relative
            or "\x00" in relative or relative.startswith("/")
            or PurePosixPath(relative).as_posix() != relative
            or any(part in {".", ".."} for part in relative.split("/"))):
        raise ObserverError("Unsafe source path / 不安全的源码路径")
    path = root
    for part in relative.split("/"):
        path = path / part
        if path.is_symlink():
            raise ObserverError("Source symlinks are unsupported / 不支持源码符号链接")
    if not path.is_file():
        raise ObserverError("Pinned source file absent / 固定源码文件不存在")
    return path


def _lookup(namespace: dict, name: str) -> tuple[str, object]:
    # A dict lookup can invoke a colliding non-string key's __eq__. Iterate exact
    # str keys instead, refusing the entire namespace if any other key is found.
    # 字典查找可能触发碰撞键的用户 __eq__；逐项检查精确 str，异常命名空间整体拒绝。
    if type(namespace) is not dict:
        return "unsupported_namespace", None
    found, result = False, None
    for count, (key, value) in enumerate(dict.items(namespace), 1):
        if count > MAX_NAMESPACE_ENTRIES:
            return "namespace_entry_limit", None
        if type(key) is not str:
            return "unsupported_namespace", None
        if key == name:
            found, result = True, value
    return ("found", result) if found else ("absent", None)


class GlobalReadObserver:
    """Bounded, aggregated pre-op binding observations for reviewed files.

    ``with observer: original_callable()`` leaves original assertions unchanged.
    Use ``report()`` after exit. Existing tracing/profiling or existing concurrent
    threads are refused. A report's integrity is not a semantic correctness gate.
    使用上下文管理器观测原函数，不改写断言；完整性通过不等于语义正确。
    """

    def __init__(self, *, source_root: str | Path, source_pins: dict[str, str],
                 max_observations: int = 10_000):
        if type(max_observations) is not int or not 1 <= max_observations <= 100_000:
            raise ObserverError("Invalid observation bound / 观测上限无效")
        if type(source_pins) is not dict or not 1 <= len(source_pins) <= MAX_SOURCE_FILES:
            raise ObserverError("Invalid source pin set / 固定源码集合无效")
        for key, digest in source_pins.items():
            if (type(key) is not str or type(digest) is not str or len(digest) != 64
                    or any(char not in "0123456789abcdef" for char in digest)):
                raise ObserverError("Invalid source digest / 源码摘要无效")
        self._root = Path(source_root).resolve(strict=True)
        if not self._root.is_dir():
            raise ObserverError("Source root must be a directory / 源码根必须是目录")
        self._pins = dict(source_pins)
        self._max_observations = max_observations
        self._state = "new"
        self._files = {}
        self._signatures = {}
        self._code_info = {}
        self._records = {}
        self._counts = {"eligible_load_global_events": 0, "retained_observations": 0,
                        "retained_events": 0, "dropped_observations": 0,
                        "uncertified_code_events": 0, "exception_events": 0,
                        "unsupported_filename_events": 0,
                        "partial_position_events": 0,
                        "status_counts": {}}
        self._integrity = {"source_initial_verified": False, "source_final_verified": False,
                           "source_changed": [], "trace_intact_at_exit": False,
                           "other_threads_seen": False, "observer_errors": 0,
                           "body_raised": False}
        self._active_count = threading.active_count
        self._get_ident = threading.get_ident
        self._trace_callback = self._trace
        self._previous_trace = None

    def __enter__(self):
        if self._state != "new":
            raise ObserverError("Observer is single-use / 观测器仅可使用一次")
        if sys.implementation.name != "cpython" or sys.version_info[:2] != (3, 12):
            raise ObserverError("Only CPython 3.12 is supported / 仅支持 CPython 3.12")
        if sys.gettrace() is not None or threading.gettrace() is not None:
            raise ObserverError("Existing trace is unsupported / 不支持已有跟踪器")
        if sys.getprofile() is not None:
            raise ObserverError("Existing profile is unsupported / 不支持已有分析器")
        if self._active_count() != 1:
            raise ObserverError("Concurrent threads are unsupported / 不支持并发线程")
        total, code_count = 0, 0
        for relative, expected in sorted(self._pins.items()):
            path = _source_path(self._root, relative)
            raw = _read_source(path)
            if _sha(raw) != expected:
                raise ObserverError("Initial source SHA mismatch / 初始源码摘要不匹配")
            total += len(raw)
            if total > MAX_TOTAL_SOURCE_BYTES:
                raise ObserverError("Total source byte limit exceeded / 超出源码总字节上限")
            # Compile the already-hashed bytes, never execute them.
            # 只编译同一份已核字节，不执行编译结果。
            code = compile(raw, str(path), "exec", dont_inherit=True, optimize=sys.flags.optimize)
            signatures = set()
            for nested in _walk_codes(code):
                code_count += 1
                if code_count > MAX_CODE_OBJECTS:
                    raise ObserverError("Code object limit exceeded / 超出代码对象上限")
                signatures.add(_code_signature(nested))
            self._files[str(path)] = relative
            self._signatures[relative] = signatures
        self._owner_thread = self._get_ident()
        self._integrity["source_initial_verified"] = True
        self._state = "active"
        self._previous_trace = sys.gettrace()
        # 3.12 requires an opcode-enabled frame before the first settrace call.
        # Temporarily use this observer frame, preserving its original flag.
        # 3.12 首次安装前必须已有 frame 开启 opcode；仅暂改并恢复本函数 frame。
        bootstrap_frame = sys._getframe()
        previous_opcodes = bootstrap_frame.f_trace_opcodes
        try:
            bootstrap_frame.f_trace_opcodes = True
            sys.settrace(self._trace_callback)
            if sys.gettrace() is not self._trace_callback:
                raise ObserverError("Trace installation failed / 跟踪器安装失败")
        except BaseException:
            sys.settrace(self._previous_trace)
            self._state = "failed"
            raise
        finally:
            bootstrap_frame.f_trace_opcodes = previous_opcodes
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._integrity["body_raised"] = exc_type is not None
        self._integrity["trace_intact_at_exit"] = sys.gettrace() is self._trace_callback
        self._integrity["other_threads_seen"] |= (
            self._active_count() != 1 or self._get_ident() != self._owner_thread)
        sys.settrace(self._previous_trace)
        self._state = "closed"
        for relative, expected in sorted(self._pins.items()):
            try:
                path = _source_path(self._root, relative)
                good = _sha(_read_source(path)) == expected
            except (OSError, ObserverError):
                good = False
            if not good:
                self._integrity["source_changed"].append(relative)
        self._integrity["source_final_verified"] = not self._integrity["source_changed"]
        # Original exceptions propagate; failures are evidence, not an observer pass.
        # 不吞掉原程序异常；失败作为证据保留。
        return False

    def _info(self, code: types.CodeType, relative: str) -> dict:
        identity = id(code)
        cached = self._code_info.get(identity)
        if cached is not None and cached[0] is code:
            return cached[1]
        try:
            signature = _code_signature(code)
            certified = signature in self._signatures[relative]
            reason = None if certified else "unmatched_compiled_code"
        except (ObserverError, ValueError, TypeError, RecursionError):
            signature, certified = None, False
            reason = "unsupported_code_signature"
        info = {"signature": signature, "certified": certified, "sites": _load_sites(code),
                "reason": reason}
        if len(self._code_info) < MAX_CODE_OBJECTS:
            # id keys avoid code-object equality comparing arbitrary dynamic constants.
            # 用 id 键避免代码对象相等比较触发动态常量的用户逻辑。
            self._code_info[identity] = (code, info)
        else:
            info["certified"] = False
            info["reason"] = "code_cache_limit"
        return info

    def _trace(self, frame, event, arg):
        try:
            if self._active_count() != 1:
                self._integrity["other_threads_seen"] = True
            filename = frame.f_code.co_filename
            if type(filename) is not str:
                self._counts["unsupported_filename_events"] += 1
                return None
            relative = self._files.get(filename)
            if relative is None:
                return None
            if event == "call":
                frame.f_trace_lines = False
                frame.f_trace_opcodes = True
            elif event == "exception":
                self._counts["exception_events"] += 1
            elif event == "opcode":
                info = self._info(frame.f_code, relative)
                site = info["sites"].get(frame.f_lasti)
                if site is not None:
                    self._observe(frame, relative, info, site)
            return self._trace_callback
        except Exception:
            # Never stringify an exception which could be provided by user code.
            # 不序列化可能由用户提供的异常对象。
            self._integrity["observer_errors"] += 1
            return self._trace_callback

    def _observe(self, frame, relative: str, info: dict, site: dict):
        counts = self._counts
        counts["eligible_load_global_events"] += 1
        ordinal = counts["eligible_load_global_events"]
        name = site["name"]
        certified = info["certified"]
        binding, status = "uninspected", "uncertified_code"
        value = {"status": "unsupported", "type": "other", "reason": info["reason"]}
        if not certified:
            counts["uncertified_code_events"] += 1
        elif type(name) is not str:
            status = "unsupported_name"
            value = {"status": "unsupported", "type": "other", "reason": status}
        else:
            lookup, actual = _lookup(frame.f_globals, name)
            if lookup == "found":
                binding = "module_global"
                value = encode_primitive(actual)
                status = "primitive" if value["status"] == "supported" else "unsupported_value"
            elif lookup == "absent":
                lookup, _ = _lookup(frame.f_builtins, name)
                if lookup == "found":
                    binding, status = "builtin", "builtin_fallback"
                elif lookup == "absent":
                    binding, status = "missing", "missing_binding"
                else:
                    status = lookup
                value = {"status": "unsupported", "type": "other", "reason": status}
            else:
                status = lookup
                value = {"status": "unsupported", "type": "other", "reason": status}
        counts["status_counts"][status] = counts["status_counts"].get(status, 0) + 1
        lineno, end_lineno, col_offset, end_col_offset = site["position"]
        position_complete = all(type(part) is int for part in site["position"])
        if not position_complete:
            counts["partial_position_events"] += 1
        record = {"event_kind": "pre_op_binding", "source_path": relative,
                  "source_sha256": self._pins[relative], "code_signature": info["signature"],
                  "certified_code": certified,
                  "qualname": (frame.f_code.co_qualname
                               if type(frame.f_code.co_qualname) is str else None),
                  "function_name": (frame.f_code.co_name
                                    if type(frame.f_code.co_name) is str else None),
                  "name": name if type(name) is str else None,
                  "bytecode_offset": frame.f_lasti, "lineno": lineno,
                  "end_lineno": end_lineno, "col_offset": col_offset,
                  "end_col_offset": end_col_offset, "position_complete": position_complete,
                  "binding": binding,
                  "status": status, "value": value}
        key = _canonical(record)
        retained = self._records.get(key)
        if retained is not None:
            retained["count"] += 1
            retained["last_event"] = ordinal
            counts["retained_events"] += 1
        elif len(self._records) < self._max_observations:
            self._records[key] = {**record, "count": 1, "first_event": ordinal, "last_event": ordinal}
            counts["retained_observations"] += 1
            counts["retained_events"] += 1
        else:
            counts["dropped_observations"] += 1

    def report(self) -> dict:
        """Return a detached JSON-safe report, never arbitrary runtime objects.

        ``measurement_valid`` checks source/tracing integrity, not correctness;
        ``complete`` also excludes discarded events, uncertified code, non-exact
        filenames and incomplete positions.
        No observations is explicit and provides no positive semantic evidence.
        完整性不等于正确性；零观测不提供正面语义证据。
        """
        integrity = self._integrity
        valid = (self._state == "closed" and integrity["source_initial_verified"]
                 and integrity["source_final_verified"] and integrity["trace_intact_at_exit"]
                 and not integrity["other_threads_seen"] and not integrity["observer_errors"])
        complete = (valid and not self._counts["dropped_observations"]
                    and not self._counts["uncertified_code_events"]
                    and not self._counts["unsupported_filename_events"]
                    and not self._counts["partial_position_events"])
        return json.loads(_canonical({"schema_version": 1, "state": self._state,
            "event_semantics": "pre_op_binding_not_consumed_operand",
            "runtime": {"implementation": sys.implementation.name,
                        "version": list(sys.version_info[:3]), "optimize": sys.flags.optimize},
            "source_pins": self._pins, "max_observations": self._max_observations,
            "counts": self._counts, "integrity": integrity,
            "measurement_valid": valid, "complete": complete,
            "no_observations": not self._counts["eligible_load_global_events"],
            "observations": list(self._records.values()),
            "blind_spots": ["current_thread_only", "native_execution_not_traced",
                "pre_op_event_does_not_prove_successful_load", "async_signal_mutation",
                "transient_threads_may_escape_detection", "subprocesses_not_observed",
                "source_changes_restored_between_checks", "hostile_trace_or_builtin_replacement",
                "matching_code_signature_is_not_historical_origin_attestation"],
            "limits": {"source_bytes_per_file": MAX_SOURCE_BYTES,
                       "source_bytes_total": MAX_TOTAL_SOURCE_BYTES,
                       "source_files": MAX_SOURCE_FILES, "code_objects": MAX_CODE_OBJECTS,
                       "namespace_entries": MAX_NAMESPACE_ENTRIES,
                       "primitive_bytes": MAX_VALUE_BYTES, "integer_bits": MAX_INT_BITS}}))
