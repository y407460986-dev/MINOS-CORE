# MINOS-CORE 数据模型设计

> MINOS-CORE 以总成图纸为入口，联合 BOM、技术要求、历史模板与规则库的 APQP/PFMEA/控制计划智能生成与审核系统数据模型

## 1. 核心实体 ER 图

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#607D8B', 'primaryTextColor': '#fff', 'primaryBorderColor': '#455A64'}}}%%
erDiagram
    PROJECT ||--o{ DRAWING : "上传"
    PROJECT ||--o{ BOM : "关联"
    PROJECT ||--o| PROCESS_FLOW : "生成"
    PROJECT ||--o| PFMEA : "生成"
    PROJECT ||--o{ CONTROL_PLAN : "包含"
    PROJECT ||--o{ DOCUMENT : "产出"
    PROJECT ||--o{ WORKFLOW : "执行"

    PROCESS_FLOW ||--o{ PROCESS_STEP : "包含"
    PFMEA ||--o{ FMEA_ITEM : "包含"
    CONTROL_PLAN ||--o{ CONTROL_ITEM : "包含"

    BOM ||--|{ BOM_ITEM : "包含"
    BOM_ITEM ||--o{ BOM_ITEM : "父子"

    DRAWING ||--o{ DRAWING_PAGE : "分页"
    DOCUMENT ||--o{ DOCUMENT_VERSION : "版本"
    DOCUMENT ||--o{ REVIEW : "审核"

    CONTROL_PLAN }o--|| CONTROL_PLAN : "版本链"
    PFMEA }o--|| PFMEA : "版本链"
    PROCESS_FLOW }o--|| PROCESS_FLOW : "版本链"

    KNOWLEDGE_BASE ||--o{ KNOWLEDGE_ENTRY : "条目"
    RULE_BASE ||--o{ RULE : "规则"

    FMEA_ITEM ||--o{ ACTION : "行动措施"
    FMEA_ITEM ||--o{ CAUSE_ANALYSIS : "原因分析"
```

---

## 2. 实体详细设计

### 2.1 Project - 项目实体

```mermaid
%%{init: {'theme': 'base'}}%%
erDiagram
    PROJECT {
        string project_id PK "项目唯一标识"
        string project_code "项目编号"
        string project_name "项目名称"
        string customer "客户名称"
        string part_number "总成零件号"
        string part_name "总成零件名称"
        string status "项目状态: planning|design|process|validation|production|closed"
        string priority "优先级: high|medium|low"
        date start_date "计划开始日期"
        date end_date "计划结束日期"
        date actual_start_date "实际开始日期"
        date actual_end_date "实际完成日期"
        string project_manager "项目经理"
        string team_members "团队成员 JSON"
        string description "项目描述"
        datetime created_at "创建时间"
        datetime updated_at "更新时间"
        string created_by "创建人"
        string updated_by "更新人"
    }
```

**关键字段说明**:
- `project_id`: UUID 或自增 ID，作为所有关联表的外键
- `status`: 项目生命周期状态，遵循 APQP 五阶段
- `team_members`: JSON 数组，存储团队成员及其角色

---

### 2.2 Drawing - 图纸实体

```mermaid
%%{init: {'theme': 'base'}}%%
erDiagram
    DRAWING {
        string drawing_id PK "图纸唯一标识"
        string project_id FK "关联项目"
        string file_name "文件名"
        string file_type "文件类型: pdf|dwg|dxf"
        string file_path "存储路径"
        string file_size "文件大小"
        string hash_value "文件哈希值"
        int page_count "页数"
        string drawing_number "图纸编号"
        string drawing_version "图纸版本"
        string scale "比例尺"
        date issue_date "发行日期"
        date revision_date "修订日期"
        string material "材料"
        string surface_treatment "表面处理"
        string tolerance "公差要求"
        string special_notes "特殊说明"
        string ocr_status "OCR 状态: pending|processing|completed|failed"
        string parsed_data "解析后数据 JSON"
        datetime created_at "创建时间"
        datetime updated_at "更新时间"
    }

    DRAWING_PAGE {
        string page_id PK "页面标识"
        string drawing_id FK "关联图纸"
        int page_number "页码"
        string content_type "内容类型: assembly|detail|general"
        string parsed_content "解析内容 JSON"
        string bounding_boxes "检测区域 JSON"
        datetime created_at "创建时间"
    }
```

---

### 2.3 BOM - 物料清单实体

```mermaid
%%{init: {'theme': 'base'}}%%
erDiagram
    BOM {
        string bom_id PK "BOM唯一标识"
        string project_id FK "关联项目"
        string bom_code "BOM编码"
        string version "版本号"
        string source_system "来源系统: erp|manual|imported"
        string part_number "总成零件号"
        string part_name "总成零件名称"
        date effective_date "生效日期"
        date expiry_date "失效日期"
        int total_items "子项总数"
        int level_count "层级深度"
        string validation_status "校验状态"
        datetime created_at "创建时间"
        datetime updated_at "更新时间"
    }

    BOM_ITEM {
        string item_id PK "子项唯一标识"
        string bom_id FK "关联BOM"
        string parent_item_id FK "父项ID"
        int level "层级深度: 0=总成"
        int sequence "顺序号"
        string part_number "零件号"
        string part_name "零件名称"
        string specification "规格描述"
        string material "材料"
        string supplier "供应商"
        int quantity "用量"
        string unit "单位"
        string bom_position "BOM位置号"
        string drawing_ref "图纸参照"
        string source "来源: make|buy|custom"
        string critical_item "关键件标记"
        string special_char "特殊特性"
        string notes "备注"
        datetime created_at "创建时间"
        datetime updated_at "更新时间"
    }
```

---

### 2.4 Process Flow - 过程流程图实体

```mermaid
%%{init: {'theme': 'base'}}%%
erDiagram
    PROCESS_FLOW {
        string flow_id PK "流程图唯一标识"
        string project_id FK "关联项目"
        string flow_code "流程图编号"
        int version "版本号"
        string status "状态: draft|review|approved|published"
        string phase "阶段: prototype|pre-launch|production"
        string description "描述"
        string diagram_data "图表数据 JSON"
        string work_stations "工作站配置 JSON"
        datetime created_at "创建时间"
        datetime updated_at "更新时间"
        string created_by "创建人"
    }

    PROCESS_STEP {
        string step_id PK "步骤唯一标识"
        string flow_id FK "关联流程图"
        int sequence "顺序号"
        string step_name "步骤名称"
        string step_description "步骤描述"
        string work_station "工作站"
        string work_center "工作中心"
        string cycle_time "循环时间"
        string takt_time "节拍时间"
        string tools_required "所需工装"
        string fixtures "夹具"
        string gauges "量具"
        string parameters "工艺参数 JSON"
        string in_process_check "过程检验"
        string safety_notes "安全提示"
        string capability_data "能力数据"
        datetime created_at "创建时间"
        datetime updated_at "更新时间"
    }

    PROCESS_FLOW }o--|| PROCESS_FLOW : "previous_version"
```

---

### 2.5 PFMEA - FMEA 实体 (AIAG-VDA 七步法)

```mermaid
%%{init: {'theme': 'base'}}%%
erDiagram
    PFMEA {
        string fmea_id PK "FMEA唯一标识"
        string project_id FK "关联项目"
        string fmea_code "FMEA编号"
        string type "类型: DFMEA|PFMEA"
        int version "版本号"
        string status "状态: draft|review|approved|published"
        string method "方法: AIAG|AIAG-VDA"
        string scope "范围描述"
        string responsible "负责人"
        string team_members "团队成员 JSON"
        date start_date "开始日期"
        date target_date "目标日期"
        date completion_date "完成日期"
        string summary "概要"
        datetime created_at "创建时间"
        datetime updated_at "更新时间"
    }

    FMEA_ITEM {
        string item_id PK "条目唯一标识"
        string fmea_id FK "关联FMEA"
        string step_id FK "关联过程步骤"
        int sequence "顺序号"
        string item_number "项目编号"
        string item_name "项目名称"
        string potential_failure_mode "潜在失效模式"
        string potential_failure_effect "潜在失效影响"
        string failure_effect_severity "失效影响严重度 S"
        string potential_failure_cause "潜在失效起因"
        string occurrence_cause "起因频度 O"
        string current_prevention_control "现行预防控制"
        string current_detection_control "现行探测控制"
        string detection_detection "探测度 D"
        string rpn "风险优先数 RPN"
        string action_status "措施状态"
        string recommended_actions "建议措施"
        string responsible "责任人"
        date target_date "目标日期"
        string taken_actions "已采取的措施"
        string severity_after "措施后严重度"
        string occurrence_after "措施后频度"
        string detection_after "措施后探测度"
        string rpn_after "措施后RPN"
        string dvp_link "DVP关联"
        datetime created_at "创建时间"
        datetime updated_at "更新时间"
    }

    CAUSE_ANALYSIS {
        string cause_id PK "原因标识"
        string item_id FK "关联FMEA条目"
        string cause_description "原因描述"
        string cause_type "原因类型: machine|method|material|man|measurement|environment"
        string validation_status "验证状态"
        string comments "备注"
        datetime created_at "创建时间"
    }

    ACTION {
        string action_id PK "措施标识"
        string item_id FK "关联FMEA条目"
        string action_type "措施类型: prevention|detection|improvement"
        string description "措施描述"
        string responsible "责任人"
        date due_date "截止日期"
        string status "状态: open|in-progress|completed|verified"
        date completion_date "完成日期"
        string effectiveness "有效性评估"
        datetime created_at "创建时间"
        datetime updated_at "更新时间"
    }

    PFMEA }o--|| PFMEA : "previous_version"
    PFMEA ||--o{ FMEA_ITEM : "包含"
    FMEA_ITEM ||--o{ CAUSE_ANALYSIS : "分析"
    FMEA_ITEM ||--o{ ACTION : "行动"
```

---

### 2.6 Control Plan - 控制计划实体 (三阶段)

```mermaid
%%{init: {'theme': 'base'}}%%
erDiagram
    CONTROL_PLAN {
        string cp_id PK "控制计划唯一标识"
        string project_id FK "关联项目"
        string cp_code "控制计划编号"
        string type "类型: product|process"
        int version "版本号"
        string status "状态: draft|review|approved|published"
        string phase "阶段: Prototype|Pre-Launch|Production"
        string responsible "负责人"
        string team_members "团队成员 JSON"
        date effective_date "生效日期"
        string description "描述"
        string summary "概要"
        datetime created_at "创建时间"
        datetime updated_at "更新时间"
    }

    CONTROL_ITEM {
        string item_id PK "条目唯一标识"
        string cp_id FK "关联控制计划"
        int sequence "顺序号"
        string process_step "过程步骤"
        string process_step_description "过程步骤描述"
        string product_characteristic "产品特性"
        string product_characteristic_type "产品特性类型: SC|Special|Standard"
        string process_characteristic "过程特性"
        string process_characteristic_type "过程特性类型"
        string special_classification "特殊特性分类: SC1|SC2|SC3"
        string limits_tolerance "规格/公差"
        string measurement_method "测量方法"
        string measurement_system "测量系统"
        string sample_size "样本大小"
        string sample_frequency "样本频率"
        string control_method "控制方法: SPC|X-bar|attribute"
        string reaction_plan "反应计划"
        string responsible "责任人"
        string in_process_inspection "过程检验"
        string first_article_inspection "首件检验"
        string records "记录保存"
        string notes "备注"
        datetime created_at "创建时间"
        datetime updated_at "更新时间"
    }

    CONTROL_PLAN }o--|| CONTROL_PLAN : "previous_version"
    CONTROL_PLAN ||--o{ CONTROL_ITEM : "包含"
```

---

### 2.7 Document & Review - 文档与审核实体

```mermaid
%%{init: {'theme': 'base'}}%%
erDiagram
    DOCUMENT {
        string doc_id PK "文档唯一标识"
        string project_id FK "关联项目"
        string doc_type "文档类型: drawing|bom|process_flow|fmea|control_plan|wi|report"
        string doc_code "文档编号"
        string title "标题"
        string description "描述"
        int version "版本号"
        string status "状态: draft|pending_review|under_review|approved|rejected|published|archived"
        string file_path "文件路径"
        string content "内容 JSON/Markdown"
        string workflow_id FK "工作流ID"
        date effective_date "生效日期"
        date expiry_date "失效日期"
        datetime created_at "创建时间"
        datetime updated_at "更新时间"
        string created_by "创建人"
        string approved_by "批准人"
        datetime approved_at "批准时间"
    }

    DOCUMENT_VERSION {
        string version_id PK "版本标识"
        string doc_id FK "关联文档"
        int version_number "版本号"
        string change_summary "变更摘要"
        string file_path "文件路径"
        string content "内容"
        string created_by "创建人"
        datetime created_at "创建时间"
    }

    REVIEW {
        string review_id PK "审核标识"
        string doc_id FK "关联文档"
        string review_type "审核类型: technical|fmea|control_plan|ppap"
        string reviewer "审核人"
        string status "状态: pending|in_progress|passed|failed|conditional_pass"
        int score "评分"
        string findings "发现项 JSON"
        string comments "审核意见"
        string recommendations "建议"
        date scheduled_date "计划日期"
        date completed_date "完成日期"
        datetime created_at "创建时间"
        datetime updated_at "更新时间"
    }

    WORKFLOW {
        string workflow_id PK "工作流标识"
        string doc_id FK "关联文档"
        string workflow_type "工作流类型: review|approval|publish"
        string current_stage "当前阶段"
        string stages "阶段定义 JSON"
        string stage_history "阶段历史 JSON"
        datetime created_at "创建时间"
        datetime updated_at "更新时间"
    }

    DOCUMENT ||--o{ DOCUMENT_VERSION : "版本"
    DOCUMENT ||--o{ REVIEW : "审核"
    DOCUMENT ||--o| WORKFLOW : "工作流"
```

---

### 2.8 Knowledge Base & Rule Base - 知识库与规则库

```mermaid
%%{init: {'theme': 'base'}}%%
erDiagram
    KNOWLEDGE_BASE {
        string kb_id PK "知识库标识"
        string name "知识库名称"
        string category "分类: process|material|equipment|quality"
        string description "描述"
        string source "来源"
        string tags "标签 JSON"
        datetime created_at "创建时间"
        datetime updated_at "更新时间"
    }

    KNOWLEDGE_ENTRY {
        string entry_id PK "条目标识"
        string kb_id FK "关联知识库"
        string title "标题"
        string content "内容"
        string content_type "内容类型: text|table|image|video|document"
        string keywords "关键词"
        string related_parts "关联零件 JSON"
        string related_processes "关联工序 JSON"
        string applicability "适用范围"
        string confidence "置信度"
        string metadata "元数据 JSON"
        datetime created_at "创建时间"
        datetime updated_at "更新时间"
    }

    RULE_BASE {
        string rule_id PK "规则标识"
        string name "规则名称"
        string category "分类: fmea|control_plan|process|inspection"
        string rule_type "规则类型: calculation|validation|recommendation|generation"
        string condition "触发条件"
        string rule_content "规则内容 JSON"
        string action "执行动作"
        string priority "优先级: high|medium|low"
        boolean enabled "启用状态"
        datetime created_at "创建时间"
        datetime updated_at "更新时间"
    }

    KNOWLEDGE_BASE ||--o{ KNOWLEDGE_ENTRY : "条目"
```

---

## 3. 追溯链设计

```mermaid
%%{init: {'theme': 'base'}}%%
flowchart TB
    subgraph 追溯起点
        D1[总成图纸] --> D2[图纸解析结构]
    end

    subgraph BOM 追溯
        D2 --> B1[BOM 清单]
        B1 --> B2[BOM 子项]
        B2 --> B3[零件图纸]
        B3 --> B4[零件规格]
    end

    subgraph FMEA 追溯
        B2 --> F1[PFMEA]
        F1 --> F2[失效模式]
        F2 --> F3[失效影响]
        F3 --> F4[失效起因]
    end

    subgraph 控制计划追溯
        F1 --> C1[控制计划]
        C1 --> C2[控制项目]
        C2 --> C3[检验规格]
        C3 --> C4[测量方法]
    end

    subgraph 流程图追溯
        C1 --> P1[过程流程图]
        P1 --> P2[工序步骤]
        P2 --> P3[工艺参数]
    end

    subgraph 输出追溯
        P3 --> O1[作业指导书]
        F4 --> O2[防错方案]
        C4 --> O3[MSA 计划]
    end

    style D1 fill:#E3F2FD,stroke:#2196F3
    style B1 fill:#E8F5E9,stroke:#4CAF50
    style F1 fill:#FFF3E0,stroke:#FF9800
    style C1 fill:#F3E5F5,stroke:#9C27B0
    style P1 fill:#FFEBEE,stroke:#F44336
    style O1 fill:#E0F7FA,stroke:#00BCD4
```

---

## 4. 追溯关系表

```mermaid
%%{init: {'theme': 'base'}}%%
erDiagram
    TRACEBILITY_LINK {
        string link_id PK "追溯链标识"
        string source_entity "源实体类型"
        string source_id "源实体ID"
        string target_entity "目标实体类型"
        string target_id "目标实体ID"
        string link_type "链接类型: contains|references|affects|controlled_by|measured_by"
        string direction "方向: forward|backward"
        string metadata "元数据 JSON"
        datetime created_at "创建时间"
    }

    TRACEBILITY_LINK ||--o| PROJECT : "关联"
    TRACEBILITY_LINK ||--o| FMEA_ITEM : "追溯"
    TRACEBILITY_LINK ||--o| CONTROL_ITEM : "追溯"
    TRACEBILITY_LINK ||--o| PROCESS_STEP : "追溯"
```

---

## 5. 字段命名规范

| 类别 | 前缀/后缀 | 示例 | 说明 |
|------|-----------|------|------|
| 主键 | `_id` | `project_id` | UUID 或雪花ID |
| 外键 | `_id` | `fmea_id` | 关联到其他表 |
| 时间 | `_at` | `created_at` | 时间戳字段 |
| 日期 | `_date` | `start_date` | 日期字段 |
| 状态 | `status` | `review_status` | 枚举值 |
| 版本 | `version` | `doc_version` | 整数递增 |
| 数量 | `count` | `total_items` | 整数 |
| 布尔 | `is_`/`has_`/`can_` | `is_active` | 布尔值 |
| JSON | 无 | `team_members` | JSON 字符串 |
| 枚举 | 无 | `phase` | 固定选项 |

---

## 6. Mermaid 配置说明

```yaml
# 推荐 Mermaid ER 配置
theme: base
themeVariables:
  primaryColor: "#607D8B"
  primaryTextColor: "#fff"
  primaryBorderColor: "#455A64"
  fontFamily: "Microsoft YaHei, SimHei, Arial, sans-serif"
```

> **使用建议**: 在支持 Mermaid 的 Markdown 渲染器（如 GitHub、GitLab、Typora、VS Code Mermaid 插件）中查看此文档以获得最佳可视化效果。
