# 固定上游执行输入

[English](README.md)

本目录包含来源与许可固定信息、真实上游测试选择及经过审查的**开发期资源预飞**记录。
这里没有上游源码包或候选图预测。基线结果在后续图实验之前已经被观察，因此这些材料是
外部可执行验证输入，**不是未见过的 holdout、必要上下文真值或成熟科研成果**。

| 官方上游 | 修复提交 | 直接父提交 | 参数化用例 | 修复版通过 | 父版失败 |
|---|---|---|---:|---:|---:|
| [Marshmallow](https://github.com/marshmallow-code/marshmallow) | `7dff08fcb7fb` | `2d30a962a0a1` | 7 | 7 | 1 |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | `0b2880591780` | `791414804eff` | 1 | 1 | 1 |
| [TOML Kit](https://github.com/python-poetry/tomlkit) | `6b5f079099d4` | `229ee8660872` | 18 | 18 | 17 |
| [Python Semver](https://github.com/python-semver/python-semver) | `37ae009c7cac` | `1d515915d50b` | 17 | 17 | 9 |

**43 个参数化用例属于四次上游变更**。相同的修复版上游测试与夹具分别运行在两个生产源码
版本上，断言保持原样。父版的 28 个失败是历史上游行为差异，不是 ContextProof 引擎失败。
测试覆盖 NaN 异常类型、用户路径展开、清空表数组后的 TOML 渲染及预发布版本令牌。
需要 IPython 交互框架的一项 dotenv 回归在运行前被排除，排除理由仍保留在 `inputs.json`。

额外的 [Pyparsing](https://github.com/pyparsing/pyparsing) 固定于
`f803ae834288032a700331977639fc49c62fcd7f`，包含 `Test02_WithoutPackrat` 中上游名称
含 `ParseAction` 或 `TrimArity` 的**全部 23 个方法**，实际全部通过。
200 次真实 `_trim_arity` 调用/返回观察包含导入期间 `_trim_arity_call_line` 从
`NoneType` 变为 `FrameSummary`、`pa_call_line_synth` 从空元组变为长度 2 的记录。
其中两个异常测试仅在 `except` 内断言，通过本身不能证明异常必定发生。
之前的三方法 arity 诊断单独保留，不能当作三个独立新增用例加到这个面板中。

## 复现命令

参考执行使用 Python **3.12**、pytest **8.4.2**、macOS arm64。
标准库运行程序支持 macOS/Linux，Windows 尚未验证。资源耗时包含 Python 跟踪开销，
属于可行性观察，不是延迟对照。四组版本进程原始峰值 RSS 为 41.97–72.12 MiB，
完整 Pyparsing 面板为 92.22 MiB。无需商业密钥。

在仓库根目录执行，并使用所有 Git 工作树之外的目录：

```bash
python3.12 scripts/prepare_global_execution_sources.py \
  --source-root /tmp/contextproof-global-inputs --with-dependencies
python3.12 benchmarks/global_bindings/upstream_execution/run.py \
  --source-root /tmp/contextproof-global-inputs \
  --output /tmp/contextproof-global-execution-new
python3.12 benchmarks/global_bindings/upstream_execution/check.py
python3.12 -m pytest -q tests/test_global_execution_inputs.py
```

`--output` 必须是新目录。已有固定下载文件时，可为准备程序添加
`--offline --cache ARCHIVE_CACHE --dependency-cache WHEEL_CACHE`。
源码目录按 `owner--repo-commitprefix` 命名，`prepared.json` 使用相对路径。
15 个独立源码包支持八个当前 HEAD 扫描及四组修复/父版本。
准备程序核验 TLS、源码包与轮包哈希、每个普通文件、版本角色和资源上限；
链接被记录并跳过，不创建或跟随链接。依赖为固定的纯 Python 轮包，在 Git 外解压，
不执行 setup 或构建脚本。执行程序启用 Python 隔离、清理环境、核对真实导入，
关闭 pytest 插件自动发现；这些措施不等同操作系统沙箱。

## 记录与边界

- `inputs.json`：固定源码、文件哈希、测试角色、选择规则与排除项。
- `dependencies.json`：七个轮包的固定 URL、版本、哈希与许可字节。
- `results/upstream-preflight.json`：八个版本运行的全部记录，包含 28 个父版失败。
- `results/global-whole-panel.json`：完整 23 方法面板和 200 条绑定观察。
- `results/global-arity-diagnostic.json`：更早、已经知晓结果的三方法诊断。
- `results/preflight-failures.json`：错误仓库地址、轮包选择歧义及已修复的导出路径失败。
- `licenses/`：原始上游 LICENSE/NOTICE 与依赖许可字节。

行轨迹只描述这些输入实际执行的 Python 路径，不能证明因果必要性、完整动态依赖，
或所有合法输入上的正确性。八个 HEAD 中七个未发现显式函数 `global` 声明，
不代表不存在经属性、别名或动态代码发生的状态变更。来源和测试已经在图实验前审阅，
后续候选结果必须保留这一开发期暴露事实。仅读核验器会拒绝丢失失败、替换版本角色、
改变实际导入身份或删除观察的记录；通过仅证明记录一致性。
完整本地堆栈、配置与下载源码一直在 Git 外。不得将复现目录或 `.private-logs` 上传为发布附件。

上游源码继续适用原有许可，包括 Marshmallow 的 Django 来源 BSD NOTICE。
执行与记录核验程序属于本项目的 MIT 实现，这是非官方验证基础设施。
