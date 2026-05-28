# 插件指南：OCR 引擎与知识源扩展

MINOS-CORE v3.0 在 `minos_core.plugins` 提供了一个极简扩展点，第三方可以注册自定义 OCR 引擎或零件族知识源，而无需 fork 主仓库。

> 当前版本只完成注册与发现，主流水线还没自动消费插件。宿主显式调用注册接口或 `load_entry_point_plugins()` 后才会生效。

## 协议

`minos_core.plugins.OCREnginePlugin`：

```python
class OCREnginePlugin(Protocol):
    name: str

    def analyze(
        self,
        pages: Iterable[Any],
        *,
        context: Mapping[str, Any],
    ) -> dict[str, Any]: ...
```

`minos_core.plugins.KnowledgeSourcePlugin`：

```python
class KnowledgeSourcePlugin(Protocol):
    family_key: str

    def load(self) -> dict[str, Any]: ...
```

不满足协议（缺少 `name` / `family_key` / `analyze` / `load`）会在注册时抛 `PluginError`（继承 `MinosError`，code `MINOS_PLUGIN_ERROR`）。

## 显式注册

```python
from minos_core.plugins import register_ocr_engine

class MyOCR:
    name = "my_ocr"

    def analyze(self, pages, *, context):
        return {"engine": self.name, "pages": list(pages)}

register_ocr_engine(MyOCR())
```

之后可以用：

```python
from minos_core.plugins import get_ocr_engine, iter_ocr_engines

engine = get_ocr_engine("my_ocr")
for plugin in iter_ocr_engines():
    print(plugin.name)
```

## 通过 Entry Points 发布

在你的插件包 `pyproject.toml` 里声明：

```toml
[project.entry-points."minos_core.ocr_engines"]
my_ocr = "my_pkg.ocr:MyOCR"

[project.entry-points."minos_core.knowledge_sources"]
my_family = "my_pkg.knowledge:MyFamilySource"
```

入口对象既可以是已经实现协议的 **实例**，也可以是 **零参工厂**（callable 没有 `name` / `family_key` 属性时被视为工厂）。比如：

```python
# my_pkg/ocr.py
from typing import Iterable, Mapping, Any


class MyOCR:
    name = "my_ocr"

    def analyze(self, pages: Iterable[Any], *, context: Mapping[str, Any]) -> dict[str, Any]:
        return {"engine": self.name}


def factory() -> MyOCR:
    return MyOCR()
```

入口指向类或工厂都可以。

宿主进程在启动时显式调用：

```python
from minos_core.plugins import load_entry_point_plugins

summary = load_entry_point_plugins()
# summary == {"ocr_engines": N, "knowledge_sources": M}
```

加载阶段任何异常都会写入 `minos_core.observability.logging` 的结构化警告日志，但 **不会** 中断宿主进程。

## 错误语义

- 重复注册同名插件 → `PluginError`，`context["plugin_name"]` 或 `context["family_key"]`。
- 注册一个不满足协议的对象 → `PluginError`。
- 通过 entry points 加载失败 → 该插件被跳过，记录 `plugins.entrypoints.load_failed` 警告。
- 通过 entry points 注册被拒绝 → 该插件被跳过，记录 `plugins.entrypoints.register_rejected` 警告。

## 测试

`tests/test_plugins_registry.py` 与 `tests/test_plugins_entrypoints.py` 是参考实现。建议在你的插件测试中：

1. 调用 `reset_registry()` 隔离每个测试用例。
2. 使用 `mock.patch.object(importlib.metadata, "entry_points", ...)` 注入 fake entry points。
3. 断言 `summary` 计数与 `get_ocr_engine` / `get_knowledge_source` 的查询结果。

## 相关文档

- [ADR 005: Plugin Extensibility](adr/005-extensibility.md)
- [架构总览](architecture/README.md)
- [模块地图](architecture/modules.md)
