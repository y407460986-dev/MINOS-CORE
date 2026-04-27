"""PySide6 desktop shell for MINOS three-table generation."""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

from .app_state import DESKTOP_PAGES, DesktopProjectState, summarize_generation_result
from .services import (
    DEFAULT_DESKTOP_DB_PATH,
    DesktopKnowledgeStore,
    DesktopProjectStore,
    DesktopRunService,
    DesktopRunRecord,
    DesktopSettingsStore,
)
from .table_editor import (
    META_CONFIRMED,
    META_IS_NEW,
    META_ORIGINAL,
    META_SOFT_DELETED,
    action_management_model,
    automation_review_model,
    build_edit_patch,
    change_impact_model,
    change_impact_patch_item,
    confirm_filtered_table_rows,
    filter_pfmea_rows,
    filter_table_rows,
    filtered_table_row_indexes,
    new_table_row,
    knowledge_recommendation_model,
    manual_review_text,
    navigation_target_from_ref,
    recommendation_action_patch_item,
    refresh_table_row_status,
    ROW_STATUS_FILTERS,
    row_to_display_text,
    restore_soft_delete_table_row,
    soft_delete_table_row,
    confirm_table_row,
    table_rows_to_edit_patch,
    three_table_to_table_model,
)


DRAWING_FILE_FILTER = "图纸文件 (*.pdf *.png *.jpg *.jpeg)"
EXPORT_MODE_LABELS = {"draft": "草案", "final": "正式"}
PFMEA_FILTERS = (
    "全部",
    "AP 高",
    "AP 中",
    "逾期",
    "待措施",
    "待措施后评价",
    "待确认",
    "知识库推荐待处理",
    "变更影响待处理",
)


def build_failure_report(message: str) -> str:
    """Return the transparent failure text required by the desktop workflow."""

    reason = _guess_failure_reason(message)
    return "\n".join(
        [
            "原始错误：",
            message,
            "",
            "原因判断：",
            reason,
            "",
            "建议的 3 种处理方案：",
            "1. 检查图纸路径、文件格式、AI 配置和网络后重试。",
            "2. 保留当前输出目录与错误信息，交给开发人员排查服务层或模型调用。",
            "3. 放弃任务。",
        ]
    )


def build_settings_status() -> dict[str, Any]:
    """Expose AI config state without returning or persisting any plaintext key."""

    state = DesktopSettingsStore(":memory:").get_ai_config_state()
    return {
        "服务商": state.provider,
        "模型": state.model,
        "模型已配置": state.model_configured,
        "模型来源": state.model_source,
        "接口地址": state.base_url,
        "接口地址已配置": state.base_url_configured,
        "接口地址来源": state.base_url_source,
        "API Key 已配置": state.api_key_configured,
        "API Key 来源": state.api_key_source,
        "API Key 环境变量": state.api_key_env_name,
        "接口协议": state.wire_api,
    }


def build_export_summary(result: dict[str, Any]) -> dict[str, Any]:
    summary = summarize_generation_result(result)
    manifest = result.get("manifest") if isinstance(result, dict) else {}
    artifact_hashes = manifest.get("artifact_hashes", {}) if isinstance(manifest, dict) else {}
    exports = summary.exports
    quality_gate = result.get("quality_gate", {}) if isinstance(result, dict) else {}
    quality_gate = quality_gate if isinstance(quality_gate, dict) else {}
    final_allowed = quality_gate.get(
        "final_export_allowed",
        quality_gate.get("allow_final_export", quality_gate.get("allow_user_export", False)),
    )
    return {
        "内部状态": summary.status,
        "状态": summary.status_display,
        "阻断阶段": summary.blocked_stage,
        "三表总工作簿": exports.get("unified_workbook", ""),
        "三表独立文件": {
            "PFD": exports.get("process_flow", ""),
            "PFMEA": exports.get("pfmea", ""),
            "控制计划": exports.get("control_plan", ""),
        },
        "运行清单路径": summary.manifest_path,
        "文件哈希": artifact_hashes if isinstance(artifact_hashes, dict) else {},
        "需要人工复核": summary.manual_review_required,
        "人工复核摘要项数": summary.manual_review_count,
        "内部明细复核项数": summary.manual_review_raw_count,
        "质量门": _display_quality_gate(quality_gate),
        "正式导出允许": bool(final_allowed),
    }


def build_export_action_summary(result: dict[str, Any]) -> dict[str, Any]:
    quality_gate = result.get("quality_gate", {}) if isinstance(result, dict) else {}
    quality_gate = quality_gate if isinstance(quality_gate, dict) else {}
    exports = result.get("exports", {}) if isinstance(result, dict) else {}
    exports = exports if isinstance(exports, dict) else {}
    return {
        "运行记录编号": result.get("run_id", "") if isinstance(result, dict) else "",
        "导出模式": EXPORT_MODE_LABELS.get(str(result.get("export_mode", "")), result.get("export_mode", ""))
        if isinstance(result, dict)
        else "",
        "输出目录": result.get("output_dir", "") if isinstance(result, dict) else "",
        "导出文件": exports,
        "质量门": _display_quality_gate(quality_gate),
    }


def _guess_failure_reason(message: str) -> str:
    lowered = message.lower()
    if "references unknown evidence" in lowered or "unknown evidence" in lowered:
        return "AI 引用了不存在的图纸页面证据，通常是模型页码引用和实际渲染页数不一致。"
    if "no such file" in lowered or "not found" in lowered or "找不到" in message:
        return "输入图纸路径不存在或当前进程无法读取该文件。"
    if "api_key" in lowered or "api key" in lowered or "401" in lowered:
        return "AI API key 可能未配置、已失效或无权限。"
    if "timeout" in lowered or "connection" in lowered or "dns" in lowered:
        return "网络连接、DNS 或 AI 服务响应可能异常。"
    if "pdf" in lowered or "png" in lowered or "jpg" in lowered or "jpeg" in lowered:
        return "图纸文件可能格式不受支持、损坏，或渲染/读取失败。"
    return "不确定；需要结合完整堆栈、输入文件和服务层日志继续排查。"


def run_desktop_app() -> int:
    try:
        from PySide6.QtCore import QUrl, Qt, QThread, Signal
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtWidgets import (
            QApplication,
            QFileDialog,
            QFormLayout,
            QComboBox,
            QGridLayout,
            QHBoxLayout,
            QInputDialog,
            QLabel,
            QListWidget,
            QListWidgetItem,
            QLineEdit,
            QMainWindow,
            QMessageBox,
            QPushButton,
            QPlainTextEdit,
            QStackedWidget,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
            QWidget,
        )
    except ModuleNotFoundError as exc:
        if exc.name == "PySide6":
            print(
                "PySide6 is not installed. Install the desktop extra with: "
                'pip install -e ".[desktop]"'
            )
            return 2
        raise

    class GenerationWorker(QThread):
        completed = Signal(dict)
        failed = Signal(str)

        def __init__(self, db_path: str, project: Any) -> None:
            super().__init__()
            self.db_path = db_path
            self.project = project

        def run(self) -> None:
            try:
                record = DesktopRunService(self.db_path).run_project(self.project)
            except Exception:  # noqa: BLE001 - desktop must show the exact failure
                self.failed.emit(traceback.format_exc())
                return
            if record.state.status == "failed":
                self.failed.emit(record.failure_message)
                return
            payload = dict(record.raw_result)
            payload["_desktop_run_record_id"] = record.id
            self.completed.emit(payload)

    class MainWindow(QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("MINOS AI 三表生成工具")
            self.resize(1100, 720)
            self.db_path = str(DEFAULT_DESKTOP_DB_PATH)
            self.settings_store = DesktopSettingsStore(self.db_path)
            self.project_store = DesktopProjectStore(self.db_path)
            self.current_project_id: int | None = None
            self.state = DesktopProjectState(
                output_dir=self.settings_store.get_default_output_dir()
            )
            self.worker: GenerationWorker | None = None
            self.last_result: dict[str, Any] | None = None
            self.current_run_id: int | None = None
            self.table_models: dict[str, dict[str, Any]] = {}
            self.table_widgets: dict[str, QTableWidget] = {}
            self.table_row_indexes: dict[str, list[int]] = {}
            self.table_status_filters: dict[str, QComboBox] = {}

            root = QWidget()
            layout = QHBoxLayout(root)
            self.nav = QListWidget()
            self.nav.setFixedWidth(180)
            self.stack = QStackedWidget()
            layout.addWidget(self.nav)
            layout.addWidget(self.stack, 1)
            self.setCentralWidget(root)

            self._build_pages()
            self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
            self.nav.setCurrentRow(0)

        def _build_pages(self) -> None:
            page_builders = {
                "project": self._project_page,
                "drawing_import": self._drawing_import_page,
                "drawing_analysis": lambda: self._json_page("drawing_analysis"),
                "pfd": lambda: self._table_page("process_flow"),
                "pfmea": lambda: self._table_page("pfmea"),
                "control_plan": lambda: self._table_page("control_plan"),
                "actions": self._actions_page,
                "change_impacts": self._change_impacts_page,
                "knowledge": self._knowledge_page,
                "automation_review": self._automation_review_page,
                "review": self._review_page,
                "export": self._export_page,
                "settings": self._settings_page,
            }
            self.page_views: dict[str, Any] = {}
            for page in DESKTOP_PAGES:
                item = QListWidgetItem(page.title)
                item.setData(Qt.UserRole, page.key)
                self.nav.addItem(item)
                self.stack.addWidget(page_builders[page.key]())

        def _project_page(self) -> QWidget:
            widget = QWidget()
            layout = QVBoxLayout(widget)
            form = QFormLayout()
            self.project_name = QLineEdit(self.state.project_name)
            form.addRow("项目名称", self.project_name)
            layout.addLayout(form)
            self.status_label = QLabel("就绪")
            layout.addWidget(self.status_label)
            layout.addWidget(QLabel("最近运行记录"))
            self.recent_runs = QListWidget()
            self.recent_runs.itemDoubleClicked.connect(self._restore_selected_run)
            layout.addWidget(self.recent_runs, 1)
            restore_button = QPushButton("恢复选中运行")
            restore_button.clicked.connect(self._restore_selected_run)
            layout.addWidget(restore_button)
            self._refresh_recent_runs()
            layout.addStretch()
            return widget

        def _drawing_import_page(self) -> QWidget:
            widget = QWidget()
            layout = QVBoxLayout(widget)
            form = QFormLayout()
            self.drawing_path = QLineEdit()
            self.output_dir = QLineEdit(self.state.output_dir)
            form.addRow("图纸文件", self._with_button(self.drawing_path, "选择", self._select_drawing))
            form.addRow("输出目录", self._with_button(self.output_dir, "选择", self._select_output_dir))
            layout.addLayout(form)
            self.run_button = QPushButton("生成三表草案")
            self.run_button.clicked.connect(self._run_generation)
            layout.addWidget(self.run_button)
            layout.addStretch()
            return widget

        def _json_page(self, key: str) -> QWidget:
            editor = QPlainTextEdit()
            editor.setReadOnly(True)
            self.page_views[key] = editor
            return editor

        def _table_page(self, table_key: str) -> QWidget:
            widget = QWidget()
            layout = QVBoxLayout(widget)
            if table_key == "pfmea":
                filter_bar = QHBoxLayout()
                filter_bar.addWidget(QLabel("筛选"))
                self.pfmea_filter = QComboBox()
                self.pfmea_filter.addItems(PFMEA_FILTERS)
                self.pfmea_filter.currentTextChanged.connect(self._apply_pfmea_filter)
                filter_bar.addWidget(self.pfmea_filter)
                filter_bar.addWidget(QLabel("行状态"))
                status_filter = QComboBox()
                status_filter.addItems(ROW_STATUS_FILTERS)
                status_filter.currentTextChanged.connect(lambda text, key=table_key: self._render_table_model(key))
                self.table_status_filters[table_key] = status_filter
                filter_bar.addWidget(status_filter)
                filter_bar.addStretch()
                layout.addLayout(filter_bar)
            else:
                filter_bar = QHBoxLayout()
                filter_bar.addWidget(QLabel("行状态"))
                status_filter = QComboBox()
                status_filter.addItems(ROW_STATUS_FILTERS)
                status_filter.currentTextChanged.connect(lambda text, key=table_key: self._render_table_model(key))
                self.table_status_filters[table_key] = status_filter
                filter_bar.addWidget(status_filter)
                filter_bar.addStretch()
                layout.addLayout(filter_bar)
            table = QTableWidget()
            table.setAlternatingRowColors(True)
            table.setSelectionBehavior(QTableWidget.SelectRows)
            table.setSelectionMode(QTableWidget.SingleSelection)
            self.page_views[table_key] = table
            self.table_widgets[table_key] = table
            layout.addWidget(table, 1)
            buttons = QHBoxLayout()
            add_button = QPushButton("添加行")
            delete_button = QPushButton("软删除")
            restore_button = QPushButton("取消软删除")
            confirm_button = QPushButton("确认行")
            confirm_filtered_button = QPushButton("确认当前筛选")
            save_button = QPushButton("保存修改")
            add_button.clicked.connect(lambda checked=False, key=table_key: self._add_table_row(key))
            delete_button.clicked.connect(lambda checked=False, key=table_key: self._soft_delete_selected_row(key))
            restore_button.clicked.connect(lambda checked=False, key=table_key: self._restore_soft_delete_selected_row(key))
            confirm_button.clicked.connect(lambda checked=False, key=table_key: self._confirm_selected_row(key))
            confirm_filtered_button.clicked.connect(lambda checked=False, key=table_key: self._confirm_filtered_rows(key))
            save_button.clicked.connect(self._save_table_edits)
            for button in (add_button, delete_button, restore_button, confirm_button, confirm_filtered_button, save_button):
                buttons.addWidget(button)
            buttons.addStretch()
            layout.addLayout(buttons)
            return widget

        def _actions_page(self) -> QWidget:
            return self._readonly_table_page("actions")

        def _change_impacts_page(self) -> QWidget:
            widget = QWidget()
            layout = QVBoxLayout(widget)
            table = self._readonly_table("change_impacts")
            layout.addWidget(table, 1)
            buttons = QHBoxLayout()
            resolve_button = QPushButton("标记已处理")
            ignore_button = QPushButton("忽略影响")
            resolve_button.clicked.connect(lambda checked=False: self._resolve_selected_change("已处理"))
            ignore_button.clicked.connect(lambda checked=False: self._resolve_selected_change("已忽略"))
            buttons.addWidget(resolve_button)
            buttons.addWidget(ignore_button)
            buttons.addStretch()
            layout.addLayout(buttons)
            return widget

        def _knowledge_page(self) -> QWidget:
            widget = QWidget()
            layout = QVBoxLayout(widget)
            table = self._readonly_table("knowledge")
            layout.addWidget(table, 1)
            buttons = QHBoxLayout()
            accept_button = QPushButton("采纳推荐")
            ignore_button = QPushButton("忽略推荐")
            save_rule_button = QPushButton("沉淀为知识库")
            accept_button.clicked.connect(lambda checked=False: self._handle_selected_recommendation(True))
            ignore_button.clicked.connect(lambda checked=False: self._handle_selected_recommendation(False))
            save_rule_button.clicked.connect(self._save_selected_recommendation_as_rule)
            buttons.addWidget(accept_button)
            buttons.addWidget(ignore_button)
            buttons.addWidget(save_rule_button)
            buttons.addStretch()
            layout.addLayout(buttons)
            return widget

        def _automation_review_page(self) -> QWidget:
            widget = QWidget()
            layout = QVBoxLayout(widget)
            summary = QGridLayout()
            self.automation_batch_confirm_count = QLabel("0")
            self.automation_manual_count = QLabel("0")
            self.automation_blocker_count = QLabel("0")
            summary.addWidget(QLabel("可批量确认"), 0, 0)
            summary.addWidget(self.automation_batch_confirm_count, 0, 1)
            summary.addWidget(QLabel("需要人工判断"), 0, 2)
            summary.addWidget(self.automation_manual_count, 0, 3)
            summary.addWidget(QLabel("阻断问题"), 0, 4)
            summary.addWidget(self.automation_blocker_count, 0, 5)
            layout.addLayout(summary)
            table = self._readonly_table("automation_review")
            layout.addWidget(table, 1)
            buttons = QHBoxLayout()
            batch_button = QPushButton("批量确认 AI 低风险项")
            accept_fix_button = QPushButton("采纳选中 AI 建议")
            detail_button = QPushButton("查看详细问题")
            batch_button.clicked.connect(self._batch_confirm_automation_review)
            accept_fix_button.clicked.connect(self._accept_selected_automation_fix)
            detail_button.clicked.connect(self._show_selected_automation_detail)
            buttons.addWidget(batch_button)
            buttons.addWidget(accept_fix_button)
            buttons.addWidget(detail_button)
            buttons.addStretch()
            layout.addLayout(buttons)
            return widget

        def _readonly_table_page(self, key: str) -> QWidget:
            widget = QWidget()
            layout = QVBoxLayout(widget)
            layout.addWidget(self._readonly_table(key), 1)
            return widget

        def _readonly_table(self, key: str) -> QTableWidget:
            table = QTableWidget()
            table.setAlternatingRowColors(True)
            table.setSelectionBehavior(QTableWidget.SelectRows)
            table.setSelectionMode(QTableWidget.SingleSelection)
            self.page_views[key] = table
            return table

        def _review_page(self) -> QWidget:
            editor = QPlainTextEdit()
            editor.setReadOnly(True)
            self.page_views["review"] = editor
            return editor

        def _export_page(self) -> QWidget:
            widget = QWidget()
            layout = QVBoxLayout(widget)
            self.export_summary = QPlainTextEdit()
            self.export_summary.setReadOnly(True)
            layout.addWidget(self.export_summary)
            open_button = QPushButton("打开输出目录")
            open_button.clicked.connect(self._open_output_dir)
            draft_button = QPushButton("导出草案")
            draft_button.clicked.connect(lambda checked=False: self._export_current_run("draft"))
            final_button = QPushButton("导出正式")
            final_button.clicked.connect(lambda checked=False: self._export_current_run("final"))
            layout.addWidget(open_button)
            layout.addWidget(draft_button)
            layout.addWidget(final_button)
            return widget

        def _settings_page(self) -> QWidget:
            widget = QWidget()
            layout = QVBoxLayout(widget)
            form = QFormLayout()
            self.default_output_dir = QLineEdit(self.settings_store.get_default_output_dir())
            form.addRow(
                "默认输出目录",
                self._with_button(self.default_output_dir, "保存", self._save_default_output_dir),
            )
            layout.addLayout(form)
            self.settings_status = QPlainTextEdit()
            self.settings_status.setReadOnly(True)
            layout.addWidget(self.settings_status)
            self._refresh_settings_status()
            return widget

        def _with_button(self, line_edit: QLineEdit, text: str, callback: Any) -> QWidget:
            widget = QWidget()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(line_edit, 1)
            button = QPushButton(text)
            button.clicked.connect(callback)
            layout.addWidget(button)
            return widget

        def _select_drawing(self) -> None:
            path, _ = QFileDialog.getOpenFileName(
                self,
                "选择图纸",
                "",
                DRAWING_FILE_FILTER,
            )
            if path:
                self.drawing_path.setText(path)

        def _select_output_dir(self) -> None:
            path = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output_dir.text())
            if path:
                self.output_dir.setText(path)

        def _run_generation(self) -> None:
            drawing = self.drawing_path.text().strip()
            output = self.output_dir.text().strip() or str(Path("out/desktop"))
            if not drawing:
                QMessageBox.warning(self, "缺少图纸", "请选择 PDF/PNG/JPG 图纸文件。")
                return
            self.state.drawing_path = drawing
            self.state.output_dir = output
            self.state.context = {"project_name": self.project_name.text()}
            self.settings_store.set_default_output_dir(output)
            if self.current_project_id is None:
                project = self.project_store.create_project(
                    DesktopProjectState(
                        project_name=self.project_name.text(),
                        drawing_path=drawing,
                        output_dir=output,
                        context=self.state.context,
                    )
                )
                self.current_project_id = project.id
            else:
                project = self.project_store.update_project(
                    self.current_project_id,
                    project_name=self.project_name.text(),
                    drawing_path=drawing,
                    output_dir=output,
                    context=self.state.context,
                )
            self.run_button.setEnabled(False)
            self.status_label.setText("正在调用 AI 并生成三表...")
            self.worker = GenerationWorker(self.db_path, project)
            self.worker.completed.connect(self._generation_completed)
            self.worker.failed.connect(self._generation_failed)
            self.worker.finished.connect(self._generation_finished)
            self.worker.start()

        def _generation_completed(self, result: dict[str, Any]) -> None:
            self.last_result = result
            self.current_run_id = result.get("_desktop_run_record_id")
            self._load_result_into_pages(result)
            self._refresh_recent_runs()
            self.nav.setCurrentRow(9)

        def _load_result_into_pages(self, result: dict[str, Any]) -> None:
            self.last_result = result
            self.current_run_id = result.get("_desktop_run_record_id", self.current_run_id)
            summary = summarize_generation_result(result)
            self.status_label.setText(f"完成：{summary.status_display}")
            self.page_views["drawing_analysis"].setPlainText(
                json.dumps(result.get("drawing_analysis", {}), ensure_ascii=False, indent=2)
            )
            self._load_table_models(result)
            self._refresh_professional_pages(result)
            self.page_views["review"].setPlainText(manual_review_text(result))
            self.export_summary.setPlainText(
                json.dumps(build_export_summary(result), ensure_ascii=False, indent=2)
            )

        def _load_table_models(self, result: dict[str, Any]) -> None:
            for table_key in ("process_flow", "pfmea", "control_plan"):
                model = three_table_to_table_model(result, table_key)
                self.table_models[table_key] = model
                self._render_table_model(table_key)
            self._apply_pfmea_filter()

        def _apply_pfmea_filter(self) -> None:
            if not self.last_result or "pfmea" not in self.table_models:
                return
            filter_key = self.pfmea_filter.currentText() if hasattr(self, "pfmea_filter") else "全部"
            if filter_key == "全部":
                model = three_table_to_table_model(self.last_result, "pfmea")
            else:
                filtered_result = dict(self.last_result)
                filtered_result["pfmea"] = dict(self.last_result.get("pfmea", {}))
                filtered_result["pfmea"]["rows"] = filter_pfmea_rows(self.last_result, filter_key)
                model = three_table_to_table_model(filtered_result, "pfmea")
            self.table_models["pfmea"] = model
            self._render_table_model("pfmea")

        def _render_table_model(self, table_key: str) -> None:
            model = self.table_models.get(table_key, {})
            table = self.table_widgets[table_key]
            columns = list(model.get("columns", []))
            column_labels = list(model.get("column_labels", columns))
            rows = list(model.get("rows", []))
            status_filter = self.table_status_filters.get(table_key)
            filter_key = status_filter.currentText() if status_filter is not None else "全部"
            visible_indexes = filtered_table_row_indexes(table_key, rows, filter_key)
            visible_rows = filter_table_rows(table_key, rows, filter_key)
            self.table_row_indexes[table_key] = visible_indexes
            table.setColumnCount(len(columns))
            table.setHorizontalHeaderLabels(column_labels)
            table.setRowCount(len(visible_rows))
            for row_index, row in enumerate(visible_rows):
                for column_index, column in enumerate(columns):
                    item = QTableWidgetItem(row_to_display_text(row.get(column, "")))
                    if row.get(META_SOFT_DELETED):
                        item.setBackground(Qt.lightGray)
                    elif row.get(META_CONFIRMED):
                        item.setBackground(Qt.green)
                    elif row.get(META_IS_NEW):
                        item.setBackground(Qt.yellow)
                    table.setItem(row_index, column_index, item)
            table.resizeColumnsToContents()

        def _refresh_professional_pages(self, result: dict[str, Any]) -> None:
            self._render_readonly_model("actions", action_management_model(result))
            self._render_readonly_model("change_impacts", change_impact_model(result))
            self._render_readonly_model("knowledge", knowledge_recommendation_model(result))
            automation_model = automation_review_model(result)
            summary = automation_model.get("summary", {})
            if hasattr(self, "automation_batch_confirm_count"):
                self.automation_batch_confirm_count.setText(str(summary.get("可批量确认数量", 0)))
                self.automation_manual_count.setText(str(summary.get("需要人工判断数量", 0)))
                self.automation_blocker_count.setText(str(summary.get("阻断数量", 0)))
            self._render_readonly_model("automation_review", automation_model)

        def _render_readonly_model(self, key: str, model: dict[str, Any]) -> None:
            table = self.page_views.get(key)
            if table is None:
                return
            columns = list(model.get("columns", []))
            labels = list(model.get("column_labels", columns))
            rows = list(model.get("rows", []))
            table.setColumnCount(len(columns))
            table.setHorizontalHeaderLabels(labels)
            table.setRowCount(len(rows))
            for row_index, row in enumerate(rows):
                for column_index, column in enumerate(columns):
                    table.setItem(row_index, column_index, QTableWidgetItem(row_to_display_text(row.get(column, ""))))
            table.resizeColumnsToContents()
            table.cellDoubleClicked.connect(lambda row, column, key=key: self._jump_from_readonly_cell(key, row))

        def _selected_readonly_row(self, key: str) -> dict[str, Any] | None:
            if not self.last_result:
                return None
            table = self.page_views.get(key)
            if table is None or not table.selectedItems():
                return None
            row_index = table.selectedItems()[0].row()
            model = {
                "change_impacts": change_impact_model,
                "knowledge": knowledge_recommendation_model,
                "actions": action_management_model,
                "automation_review": automation_review_model,
            }[key](self.last_result)
            rows = list(model.get("rows", []))
            if row_index < 0 or row_index >= len(rows):
                return None
            row = rows[row_index]
            return row if isinstance(row, dict) else None

        def _sync_table_model_from_widget(self, table_key: str) -> None:
            model = self.table_models.get(table_key)
            if not model:
                return
            table = self.table_widgets[table_key]
            columns = list(model.get("columns", []))
            rows = list(model.get("rows", []))
            visible_indexes = self.table_row_indexes.get(table_key, list(range(len(rows))))
            for visible_row_index, row_index in enumerate(visible_indexes):
                if row_index < 0 or row_index >= len(rows):
                    continue
                row = rows[row_index]
                for column_index, column in enumerate(columns):
                    item = table.item(visible_row_index, column_index)
                    row[column] = item.text() if item is not None else ""
                rows[row_index] = refresh_table_row_status(table_key, row)

        def _selected_table_row_index(self, table_key: str) -> int | None:
            table = self.table_widgets[table_key]
            selected = table.selectedItems()
            if not selected:
                return None
            visible_row = int(selected[0].row())
            indexes = self.table_row_indexes.get(table_key, [])
            if visible_row < 0 or visible_row >= len(indexes):
                return None
            return indexes[visible_row]

        def _add_table_row(self, table_key: str) -> None:
            self._sync_table_model_from_widget(table_key)
            model = self.table_models.get(table_key)
            if not model:
                return
            model["rows"].append(new_table_row(table_key, model.get("rows", [])))
            self._render_table_model(table_key)

        def _soft_delete_selected_row(self, table_key: str) -> None:
            self._sync_table_model_from_widget(table_key)
            row_index = self._selected_table_row_index(table_key)
            if row_index is None:
                return
            rows = self.table_models[table_key]["rows"]
            rows[row_index] = soft_delete_table_row(rows[row_index])
            self._render_table_model(table_key)
            self._save_table_edits(
                show_no_changes=False,
                success_message="软删除已保存，下游影响已刷新。",
            )

        def _restore_soft_delete_selected_row(self, table_key: str) -> None:
            self._sync_table_model_from_widget(table_key)
            row_index = self._selected_table_row_index(table_key)
            if row_index is None:
                return
            rows = self.table_models[table_key]["rows"]
            rows[row_index] = restore_soft_delete_table_row(rows[row_index])
            self._render_table_model(table_key)
            self._save_table_edits(
                show_no_changes=False,
                success_message="软删除已取消，下游表格已刷新。",
            )

        def _confirm_selected_row(self, table_key: str) -> None:
            self._sync_table_model_from_widget(table_key)
            row_index = self._selected_table_row_index(table_key)
            if row_index is None:
                return
            rows = self.table_models[table_key]["rows"]
            rows[row_index] = confirm_table_row(rows[row_index])
            self._render_table_model(table_key)
            self._save_table_edits(
                show_no_changes=False,
                success_message="确认记录已保存，下游状态已刷新。",
            )

        def _confirm_filtered_rows(self, table_key: str) -> None:
            self._sync_table_model_from_widget(table_key)
            model = self.table_models.get(table_key)
            if not model:
                return
            status_filter = self.table_status_filters.get(table_key)
            filter_key = status_filter.currentText() if status_filter is not None else "全部"
            model["rows"] = confirm_filtered_table_rows(table_key, model.get("rows", []), filter_key)
            self._render_table_model(table_key)
            self._save_table_edits(
                show_no_changes=False,
                success_message="当前筛选结果已逐行确认并保存。",
            )

        def _save_table_edits(
            self,
            checked: bool = False,
            *,
            show_no_changes: bool = True,
            success_message: str = "三表修改已保存。",
        ) -> None:
            if self.current_run_id is None:
                QMessageBox.warning(self, "暂无运行记录", "请先生成三表草案。")
                return
            for table_key in ("process_flow", "pfmea", "control_plan"):
                self._sync_table_model_from_widget(table_key)
            patch = table_rows_to_edit_patch(
                {
                    table_key: self.table_models.get(table_key, {}).get("rows", [])
                    for table_key in ("process_flow", "pfmea", "control_plan")
                }
            )
            if not patch.get("items"):
                if show_no_changes:
                    QMessageBox.information(self, "无需保存", "当前没有新增、修改、软删除或确认记录。")
                return
            record = DesktopRunService(self.db_path).apply_edit_patch_to_run(
                self.current_run_id,
                patch,
            )
            self.last_result = dict(record.raw_result)
            self.last_result["_desktop_run_record_id"] = record.id
            self._load_result_into_pages(self.last_result)
            self._refresh_recent_runs()
            QMessageBox.information(self, "已保存", success_message)

        def _handle_selected_recommendation(self, accept: bool) -> None:
            if self.current_run_id is None:
                QMessageBox.warning(self, "暂无运行记录", "请先生成三表草案。")
                return
            row = self._selected_readonly_row("knowledge")
            if not row:
                return
            reason = ""
            if not accept:
                reason, ok = QInputDialog.getText(self, "忽略原因", "请输入忽略该推荐的原因：")
                if not ok or not reason.strip():
                    QMessageBox.warning(self, "缺少原因", "忽略推荐必须填写原因。")
                    return
            item = recommendation_action_patch_item(
                str(row.get("recommendation_id", "")),
                "accept_recommendation" if accept else "ignore_recommendation",
                reason=reason,
            )
            self._apply_metadata_patch([item], "推荐处理已保存。")

        def _resolve_selected_change(self, status: str) -> None:
            if self.current_run_id is None:
                QMessageBox.warning(self, "暂无运行记录", "请先生成三表草案。")
                return
            row = self._selected_readonly_row("change_impacts")
            if not row:
                return
            reason = ""
            if status == "已忽略":
                reason, ok = QInputDialog.getText(self, "忽略原因", "请输入忽略该变更影响的原因：")
                if not ok or not reason.strip():
                    QMessageBox.warning(self, "缺少原因", "忽略变更影响必须填写原因。")
                    return
            item = change_impact_patch_item(str(row.get("item_id", "")), status=status, reason=reason)
            self._apply_metadata_patch([item], "变更影响处理已保存。")

        def _apply_metadata_patch(self, items: list[dict[str, Any]], message: str) -> None:
            if self.current_run_id is None:
                return
            record = DesktopRunService(self.db_path).apply_edit_patch_to_run(
                self.current_run_id,
                build_edit_patch(items),
            )
            self.last_result = dict(record.raw_result)
            self.last_result["_desktop_run_record_id"] = record.id
            self._load_result_into_pages(self.last_result)
            self._refresh_recent_runs()
            QMessageBox.information(self, "已保存", message)

        def _batch_confirm_automation_review(self) -> None:
            if self.current_run_id is None:
                QMessageBox.warning(self, "暂无运行记录", "请先生成三表草案。")
                return
            record = DesktopRunService(self.db_path).batch_confirm_automation_review(self.current_run_id)
            self.last_result = dict(record.raw_result)
            self.last_result["_desktop_run_record_id"] = record.id
            self._load_result_into_pages(self.last_result)
            self._refresh_recent_runs()
            QMessageBox.information(self, "已保存", "AI 低风险项已批量确认。")

        def _accept_selected_automation_fix(self) -> None:
            if self.current_run_id is None:
                QMessageBox.warning(self, "暂无运行记录", "请先生成三表草案。")
                return
            row = self._selected_readonly_row("automation_review")
            if not row:
                return
            record = DesktopRunService(self.db_path).accept_automation_fix_suggestion(
                self.current_run_id,
                row,
            )
            self.last_result = dict(record.raw_result)
            self.last_result["_desktop_run_record_id"] = record.id
            self._load_result_into_pages(self.last_result)
            self._refresh_recent_runs()
            QMessageBox.information(self, "已保存", "选中的 AI 修复建议已采纳。")

        def _show_selected_automation_detail(self) -> None:
            row = self._selected_readonly_row("automation_review")
            if not row:
                return
            QMessageBox.information(
                self,
                "详细问题",
                json.dumps(row, ensure_ascii=False, indent=2),
            )

        def _jump_from_readonly_cell(self, key: str, row_index: int) -> None:
            if not self.last_result:
                return
            model = {
                "change_impacts": change_impact_model,
                "knowledge": knowledge_recommendation_model,
                "actions": action_management_model,
                "automation_review": automation_review_model,
            }[key](self.last_result)
            rows = list(model.get("rows", []))
            if row_index < 0 or row_index >= len(rows):
                return
            target = str(rows[row_index].get("jump_target") or "")
            self._jump_to_target(target)

        def _jump_to_target(self, target: str) -> None:
            if not target:
                return
            table_key, row_id = target.split(":", 1) if ":" in target else ("", "")
            page_key = {"process_flow": "pfd", "pfmea": "pfmea", "control_plan": "control_plan"}.get(table_key)
            if not page_key or table_key not in self.table_models:
                return
            for index in range(self.nav.count()):
                item = self.nav.item(index)
                if item.data(Qt.UserRole) == page_key:
                    self.nav.setCurrentRow(index)
                    break
            model = self.table_models[table_key]
            rows = list(model.get("rows", []))
            visible_indexes = self.table_row_indexes.get(table_key, list(range(len(rows))))
            for visible_row, source_row in enumerate(visible_indexes):
                if source_row < len(rows) and str(rows[source_row].get(META_ROW_ID, "")) == row_id:
                    self.table_widgets[table_key].selectRow(visible_row)
                    return

        def _refresh_recent_runs(self) -> None:
            if not hasattr(self, "recent_runs"):
                return
            self.recent_runs.clear()
            for record in DesktopRunService(self.db_path).list_recent_runs(10):
                item = QListWidgetItem(_recent_run_label(record))
                item.setData(Qt.UserRole, record.id)
                self.recent_runs.addItem(item)

        def _restore_selected_run(self) -> None:
            if not hasattr(self, "recent_runs"):
                return
            item = self.recent_runs.currentItem()
            if item is None:
                return
            run_id = int(item.data(Qt.UserRole))
            record = DesktopRunService(self.db_path).restore_run(run_id)
            result = dict(record.raw_result)
            result["_desktop_run_record_id"] = record.id
            self.current_run_id = record.id
            self.output_dir.setText(record.output_dir)
            self._load_result_into_pages(result)

        def _save_selected_recommendation_as_rule(self) -> None:
            row = self._selected_readonly_row("knowledge")
            if not row:
                return
            DesktopKnowledgeStore(self.db_path).add_rule_from_recommendation(row)
            QMessageBox.information(self, "已沉淀", "该推荐已保存到本地知识库。")

        def _generation_failed(self, message: str) -> None:
            self.status_label.setText("失败")
            report = message if "原始错误" in message and "原因判断" in message else build_failure_report(message)
            QMessageBox.critical(self, "生成失败", report)

        def _generation_finished(self) -> None:
            self.run_button.setEnabled(True)
            self.worker = None

        def _open_output_dir(self) -> None:
            path = Path(self.output_dir.text().strip() or "out/desktop")
            path.mkdir(parents=True, exist_ok=True)
            if sys.platform.startswith("win"):
                os.startfile(path)  # type: ignore[attr-defined]
                return
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

        def _export_current_run(self, export_mode: str) -> None:
            if self.current_run_id is None:
                QMessageBox.warning(self, "暂无运行记录", "请先生成三表草案。")
                return
            output = Path(self.output_dir.text().strip() or "out/desktop") / export_mode
            export_mode_label = EXPORT_MODE_LABELS.get(export_mode, export_mode)
            try:
                result = DesktopRunService(self.db_path).export_run(
                    self.current_run_id,
                    output,
                    export_mode=export_mode,
                )
            except Exception:  # noqa: BLE001 - desktop must show transparent export failure
                QMessageBox.critical(self, "导出失败", build_failure_report(traceback.format_exc()))
                return
            self.export_summary.setPlainText(
                json.dumps(build_export_action_summary(result), ensure_ascii=False, indent=2)
            )
            QMessageBox.information(self, "导出完成", f"{export_mode_label}导出已完成。")

        def _save_default_output_dir(self) -> None:
            path = self.default_output_dir.text().strip() or str(Path("out/desktop"))
            saved = self.settings_store.set_default_output_dir(path)
            self.output_dir.setText(saved)
            self._refresh_settings_status()
            QMessageBox.information(self, "设置已保存", "默认输出目录已保存。")

        def _refresh_settings_status(self) -> None:
            payload = build_settings_status()
            payload["默认输出目录"] = self.settings_store.get_default_output_dir()
            payload["桌面数据库路径"] = self.db_path
            self.settings_status.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2))

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return int(app.exec())


def _display_manual_review(result: dict[str, Any]) -> dict[str, Any]:
    from .table_editor import manual_review_model

    return manual_review_model(result)


def _display_quality_gate(quality_gate: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(quality_gate, dict):
        return {}
    final_allowed = quality_gate.get(
        "final_export_allowed",
        quality_gate.get("allow_final_export", quality_gate.get("allow_user_export", False)),
    )
    return {
        "允许正式导出": bool(final_allowed),
        "待确认项": quality_gate.get("needs_confirmation_items", []),
        "问题列表": quality_gate.get("issues", []),
        "原始质量门": quality_gate,
    }


def _recent_run_label(record: DesktopRunRecord) -> str:
    return (
        f"#{record.id} {record.state.status_display} | "
        f"{record.created_at} | {record.output_dir or '未设置输出目录'}"
    )
