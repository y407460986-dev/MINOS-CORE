# 装配件多图纸导入方案

## 需求

门铰链是由多个零部件组成的装配件。当前系统只支持单张图纸输入，用户希望：

1. **总成图**上传到一个位置（必填，包含 BOM）
2. **子零件图纸**上传到另一个位置（可选，支持多张）
3. 没有子零件图纸时不报错，正常走现有流程

目标：让 AI 在生成装配件 PFMEA 时，能同时看到总成图的 BOM 和各子件的详细特性（公差、材料、特殊特性等），从而生成更准确的失效模式分析。

---

## 当前系统现状

| 层 | 现状 | 需要改动 |
|----|------|----------|
| 前端 UI | 单个"图纸文件"输入框 | 拆成两个区域 |
| API schema | `drawing_path: str`（单值） | 新增 `component_drawings: list[str]` |
| 数据库 | `projects.drawing_path TEXT` | 新增列或用 JSON 存 |
| Pipeline 入口 | `analyze_drawing_for_three_table_chain(drawing_path)` | 接受额外图纸列表 |
| 图纸渲染 | 单文件 → 多页 | 多文件 → 合并页面列表 |
| AI 分析 | 所有页面一起发给 AI | 不变，但 prompt 需增强 |
| PFMEA 生成 | 依赖 drawing_analysis + confirmed_pfd | 不变，drawing_analysis 自然包含子件信息 |

---

## 实施计划

### 阶段 1：数据层（后端）

#### 1.1 数据库 schema 扩展

`minos_desktop/services/sqlite_store.py`

在 `projects` 表新增一列：

```sql
ALTER TABLE projects ADD COLUMN component_drawings_json TEXT NOT NULL DEFAULT '[]';
```

存储格式：`["D:/path/to/pin.pdf", "D:/path/to/bushing.png"]`

> 为什么不建新表：子件图纸和项目是 1:1 关系，没必要多一张表。JSON 列足够。

#### 1.2 状态对象扩展

`minos_desktop/app_state.py`

```python
@dataclass
class DesktopProjectState:
    project_name: str = "MINOS 三表项目"
    drawing_path: str = ""              # 总成图（必填）
    component_drawings: list[str] = field(default_factory=list)  # 子件图纸（可选）
    output_dir: str = ""
    context: dict[str, Any] = field(default_factory=dict)
```

同步修改 `DesktopProjectRecord`。

#### 1.3 API schema 扩展

`minos_desktop/api/schemas.py`

```python
class CreateProjectRequest(BaseModel):
    project_name: str = Field(..., min_length=1, max_length=256)
    drawing_path: str = ""
    component_drawings: list[str] = Field(default_factory=list)  # 新增
    output_dir: str = ""
    analysis_mode: str = Field(default="hybrid", pattern="^(ocr_only|vision_only|hybrid)$")
    ocr_engine: str = Field(default="mineru", pattern="^(auto|pdf_text|rapidocr|mineru)$")
    context: dict[str, Any] = Field(default_factory=dict)
```

#### 1.4 项目存储层

`minos_desktop/services/project_store.py`

- `create()` 时写入 `component_drawings_json`
- `_row_to_record()` 时解析 JSON 列表
- 验证：每个路径必须是存在的文件，格式为 PDF/PNG/JPG/JPEG

---

### 阶段 2：Pipeline 层（核心）

#### 2.1 图纸渲染扩展

`minos_core/pipeline/drawing_analysis.py`

```python
def analyze_drawing_for_three_table_chain(
    drawing_path: str | Path,
    output_dir: str | Path,
    context: dict[str, Any] | None = None,
    analysis_mode: str = "hybrid",
    ocr_engine: str = "auto",
    ocr_adapter: Any | None = None,
    *,
    component_drawings: list[str | Path] | None = None,  # 新增
    analyzer: Any | None = None,
) -> dict[str, Any]:
```

改动逻辑：

```python
# 1. 渲染总成图
source = load_drawing_source(drawing_path)
pages = render_drawing_pages(source, target_dir / "pages")

# 2. 渲染子件图纸（如果有）
component_pages = []
if component_drawings:
    for comp_path in component_drawings:
        comp_source = load_drawing_source(comp_path)
        comp_rendered = render_drawing_pages(comp_source, target_dir / "pages")
        component_pages.extend(comp_rendered)

# 3. 合并所有页面，一起发给 AI
all_pages = pages + component_pages
```

#### 2.2 AI Prompt 增强

`minos_core/adapters/multimodal.py` 的 `_drawing_analysis_prompt()`

当存在子件图纸时，在 prompt 中追加：

```
本次分析包含装配件总成图和子零件图纸。
- 第 1-N 页为总成图（含 BOM 表），请从中识别装配关系和整件要求。
- 第 N+1 页起为各子零件的详细图纸，请从中提取子件的关键特性（尺寸公差、材料、表面处理、特殊特性）。
- 在 manufacturing_clues 中，请标注每道装配工序涉及的子件及其关键配合特性。
- 如果 BOM 中某个子件没有对应的详细图纸，仍然基于总成图中的信息推断。
```

#### 2.3 Run Service 调用

`minos_desktop/services/run_service.py`

```python
analysis_result = analyze_drawing_for_three_table_chain(
    project.drawing_path,
    project.output_dir,
    context=project.context,
    component_drawings=project.component_drawings,  # 传递子件图纸
    ...
)
```

---

### 阶段 3：前端 UI

#### 3.1 DrawingImportPage 改造

`apps/desktop-tauri/src/pages/DrawingImportPage.tsx`

将当前的单一图纸输入区域拆分为两个区域：

```
┌─────────────────────────────────────────────────────┐
│  导入命令                              [开始导入]    │
├─────────────────────────────────────────────────────┤
│                                                     │
│  总成图（必填）                                      │
│  ┌─────────────────────────────┐  ┌──────────┐     │
│  │ D:/drawings/hinge_assy.pdf  │  │ 选择图纸  │     │
│  └─────────────────────────────┘  └──────────┘     │
│                                                     │
│  子零件图纸（可选，可多选）                           │
│  ┌─────────────────────────────┐  ┌──────────┐     │
│  │ 已选择 3 个文件              │  │ 选择图纸  │     │
│  └─────────────────────────────┘  └──────────┘     │
│  · pin_shaft.pdf                          [×]       │
│  · bushing.pdf                            [×]       │
│  · spring_clip.png                        [×]       │
│                                                     │
│  输出目录                                            │
│  ┌─────────────────────────────┐  ┌──────────┐     │
│  │ D:/output/hinge_project     │  │ 选择目录  │     │
│  └─────────────────────────────┘  └──────────┘     │
│                                                     │
└─────────────────────────────────────────────────────┘
```

#### 3.2 文件选择对话框

`apps/desktop-tauri/src/api/client.ts`

新增多文件选择函数：

```typescript
export async function selectComponentDrawings(): Promise<string[]> {
  // Tauri 文件对话框，multipleSelection: true
}
```

#### 3.3 API 调用

```typescript
const project = await createProject({
  project_name: autoProjectName,
  drawing_path: drawingPath,
  component_drawings: componentDrawings,  // 新增
  output_dir: outputDir,
  context: { ... }
})
```

---

## 关键设计决策

### 为什么不强制要求子件图纸？

- 很多场景下只有总成图，没有子件图纸
- 总成图的 BOM + 技术要求已经包含了基本信息
- 子件图纸是"锦上添花"，让结果更准确，但不是必须的

### 为什么合并成一次 AI 调用而不是分开分析？

- 当前 AI 分析已经支持多页图片一起发送
- 一次调用让 AI 能看到全局关系（BOM ↔ 子件特性）
- 分开分析再合并会丢失关联上下文

### 为什么在 prompt 中区分总成图和子件图？

- 让 AI 明确知道哪些是总成图（看装配关系），哪些是子件图（看详细特性）
- 避免 AI 把子件图当作独立零件来分析

### 对 PFMEA 生成的影响

不需要改 PFMEA 生成逻辑。因为：
- PFMEA 依赖 `drawing_analysis` + `confirmed_pfd`
- `drawing_analysis` 在图纸分析阶段已经包含了子件特性信息
- AI 在分析阶段会把子件特性写入 `manufacturing_clues` 和 `special_characteristics`
- 这些信息会自然流入 PFD → PFMEA 的推断链

---

## 改动文件清单

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `minos_desktop/services/sqlite_store.py` | 修改 | 新增 `component_drawings_json` 列 |
| `minos_desktop/app_state.py` | 修改 | 状态对象新增 `component_drawings` 字段 |
| `minos_desktop/api/schemas.py` | 修改 | 请求 schema 新增字段 |
| `minos_desktop/api/routes_projects.py` | 修改 | 传递新字段 |
| `minos_desktop/services/project_store.py` | 修改 | 存取 JSON 列 |
| `minos_desktop/services/run_service.py` | 修改 | 传递 `component_drawings` 到 pipeline |
| `minos_core/pipeline/drawing_analysis.py` | 修改 | 接受并渲染子件图纸 |
| `minos_core/adapters/multimodal.py` | 修改 | prompt 增强（装配件场景） |
| `apps/desktop-tauri/src/pages/DrawingImportPage.tsx` | 修改 | UI 拆分两个上传区域 |
| `apps/desktop-tauri/src/api/client.ts` | 修改 | 新增多文件选择函数 |
| `apps/desktop-tauri/src/api/types.ts` | 修改 | 类型定义新增字段 |

---

## 验证标准

1. ✅ 只上传总成图（不选子件图纸）→ 正常生成，不报错
2. ✅ 上传总成图 + 3 张子件图纸 → AI 能识别到子件特性
3. ✅ 生成的 PFMEA 中，装配工序的失效原因能关联到子件特性
4. ✅ 子件图纸路径不存在时 → 创建项目时报错提示
5. ✅ 数据库迁移兼容旧数据（旧项目 `component_drawings_json` 默认为 `[]`）

---

## 时间估算

| 阶段 | 预计时间 |
|------|----------|
| 阶段 1：数据层 | 2-3 小时 |
| 阶段 2：Pipeline 层 | 3-4 小时 |
| 阶段 3：前端 UI | 3-4 小时 |
| 测试验证 | 2-3 小时 |
| **总计** | **10-14 小时** |
