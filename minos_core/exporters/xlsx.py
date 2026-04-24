"""Small OpenXML workbook writer used by MINOS exports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Sequence
from zipfile import ZIP_DEFLATED, ZipFile
import html
import re

INVALID_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")
MAX_SHEET_NAME_LEN = 31


@dataclass(frozen=True)
class CellStyle:
    """Named style understood by :class:`WorkbookWriter`."""

    name: str = "default"


@dataclass
class Worksheet:
    title: str
    rows: list[list[object]] = field(default_factory=list)
    freeze_panes: str | None = None
    auto_filter: bool = False
    column_widths: dict[int, float] = field(default_factory=dict)


class WorkbookWriter:
    """Write a minimal .xlsx workbook without third-party dependencies."""

    def __init__(self) -> None:
        self._sheets: list[Worksheet] = []
        self._sheet_names: set[str] = set()

    def add_sheet(
        self,
        title: str,
        rows: Iterable[Sequence[object]],
        *,
        freeze_panes: str | None = "A2",
        auto_filter: bool = True,
        column_widths: dict[int, float] | None = None,
    ) -> Worksheet:
        sheet = Worksheet(
            title=self._unique_sheet_name(title),
            rows=[list(row) for row in rows],
            freeze_panes=freeze_panes,
            auto_filter=auto_filter,
            column_widths=column_widths or {},
        )
        self._sheets.append(sheet)
        return sheet

    def save(self, path: str | Path) -> Path:
        if not self._sheets:
            raise ValueError("workbook must contain at least one sheet")

        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(output, "w", ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", self._content_types())
            archive.writestr("_rels/.rels", self._root_rels())
            archive.writestr("xl/workbook.xml", self._workbook_xml())
            archive.writestr("xl/_rels/workbook.xml.rels", self._workbook_rels())
            archive.writestr("xl/styles.xml", self._styles_xml())
            for index, sheet in enumerate(self._sheets, start=1):
                archive.writestr(
                    f"xl/worksheets/sheet{index}.xml",
                    self._worksheet_xml(sheet),
                )
        return output

    def _unique_sheet_name(self, title: str) -> str:
        base = sanitize_sheet_name(title)
        candidate = base
        counter = 2
        used_key = candidate.lower()
        while used_key in self._sheet_names:
            suffix = f" ({counter})"
            candidate = f"{base[: MAX_SHEET_NAME_LEN - len(suffix)]}{suffix}"
            used_key = candidate.lower()
            counter += 1
        self._sheet_names.add(used_key)
        return candidate

    def _content_types(self) -> str:
        sheet_overrides = "".join(
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for index in range(1, len(self._sheets) + 1)
        )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            f"{sheet_overrides}</Types>"
        )

    def _root_rels(self) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/></Relationships>'
        )

    def _workbook_xml(self) -> str:
        sheets = "".join(
            f'<sheet name="{escape_xml(sheet.title)}" sheetId="{index}" r:id="rId{index}"/>'
            for index, sheet in enumerate(self._sheets, start=1)
        )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f"<sheets>{sheets}</sheets></workbook>"
        )

    def _workbook_rels(self) -> str:
        rels = [
            f'<Relationship Id="rId{index}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{index}.xml"/>'
            for index in range(1, len(self._sheets) + 1)
        ]
        rels.append(
            f'<Relationship Id="rId{len(self._sheets) + 1}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
            'Target="styles.xml"/>'
        )
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f"{''.join(rels)}</Relationships>"
        )

    def _styles_xml(self) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
            '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="3"><fill><patternFill patternType="none"/></fill>'
            '<fill><patternFill patternType="gray125"/></fill>'
            '<fill><patternFill patternType="solid"><fgColor rgb="FFE2F0D9"/><bgColor indexed="64"/></patternFill></fill></fills>'
            '<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border>'
            '<border><left style="thin"><color auto="1"/></left><right style="thin"><color auto="1"/></right>'
            '<top style="thin"><color auto="1"/></top><bottom style="thin"><color auto="1"/></bottom><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="1" borderId="1" xfId="0" applyBorder="1"/>'
            '<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>'
            '<xf numFmtId="0" fontId="0" fillId="1" borderId="1" xfId="0" applyAlignment="1" applyBorder="1">'
            '<alignment wrapText="1" vertical="top"/></xf></cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            '</styleSheet>'
        )

    def _worksheet_xml(self, sheet: Worksheet) -> str:
        max_col = max((len(row) for row in sheet.rows), default=1)
        max_row = max(len(sheet.rows), 1)
        dimension = f"A1:{column_name(max_col)}{max_row}"
        cols = self._cols_xml(sheet, max_col)
        views = self._views_xml(sheet.freeze_panes)
        rows = "".join(self._row_xml(index, row) for index, row in enumerate(sheet.rows, start=1))
        auto_filter = f'<autoFilter ref="{dimension}"/>' if sheet.auto_filter and sheet.rows else ""
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<dimension ref="{dimension}"/>{views}{cols}<sheetData>{rows}</sheetData>{auto_filter}'
            '<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>'
            '</worksheet>'
        )

    def _cols_xml(self, sheet: Worksheet, max_col: int) -> str:
        if not sheet.column_widths and max_col == 0:
            return ""
        cols = []
        for col in range(1, max_col + 1):
            width = sheet.column_widths.get(col, 18.0)
            cols.append(f'<col min="{col}" max="{col}" width="{width}" customWidth="1"/>')
        return f"<cols>{''.join(cols)}</cols>"

    def _views_xml(self, freeze_panes: str | None) -> str:
        if not freeze_panes:
            return "<sheetViews><sheetView workbookViewId=\"0\"/></sheetViews>"
        col_letters, row_text = split_cell_ref(freeze_panes)
        x_split = column_index(col_letters) - 1
        y_split = int(row_text) - 1
        top_left = freeze_panes.upper()
        pane_parts = [f'topLeftCell="{top_left}"', 'activePane="bottomLeft"', 'state="frozen"']
        if x_split:
            pane_parts.insert(0, f'xSplit="{x_split}"')
            pane_parts[2] = 'activePane="bottomRight"'
        if y_split:
            pane_parts.insert(0, f'ySplit="{y_split}"')
        return (
            '<sheetViews><sheetView workbookViewId="0">'
            f"<pane {' '.join(pane_parts)}/>"
            '<selection pane="bottomLeft"/>'
            '</sheetView></sheetViews>'
        )

    def _row_xml(self, row_index: int, row: Sequence[object]) -> str:
        cells = []
        for col_index, value in enumerate(row, start=1):
            style = 1 if row_index == 1 else 2
            cells.append(self._cell_xml(row_index, col_index, value, style))
        return f'<row r="{row_index}">{"".join(cells)}</row>'

    def _cell_xml(self, row_index: int, col_index: int, value: object, style: int) -> str:
        ref = f"{column_name(col_index)}{row_index}"
        if value is None:
            return f'<c r="{ref}" s="{style}"/>'
        if isinstance(value, bool):
            return f'<c r="{ref}" s="{style}" t="b"><v>{int(value)}</v></c>'
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return f'<c r="{ref}" s="{style}"><v>{value}</v></c>'
        if isinstance(value, (datetime, date)):
            value = value.isoformat()
        return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t>{escape_xml(str(value))}</t></is></c>'


def sanitize_sheet_name(title: str) -> str:
    cleaned = INVALID_SHEET_CHARS.sub(" ", str(title)).strip().strip("'")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        cleaned = "Sheet"
    return cleaned[:MAX_SHEET_NAME_LEN]


def column_name(index: int) -> str:
    if index < 1:
        raise ValueError("column index must be >= 1")
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def column_index(name: str) -> int:
    value = 0
    for char in name.upper():
        if not "A" <= char <= "Z":
            raise ValueError(f"invalid column name: {name!r}")
        value = value * 26 + ord(char) - 64
    return value


def split_cell_ref(ref: str) -> tuple[str, str]:
    match = re.fullmatch(r"([A-Za-z]+)([1-9][0-9]*)", ref.strip())
    if not match:
        raise ValueError(f"invalid cell reference: {ref!r}")
    return match.group(1), match.group(2)


def escape_xml(value: str) -> str:
    return html.escape(value, quote=True)


def write_xlsx(path: str | Path, sheets: Iterable[dict[str, object] | Worksheet]) -> Path:
    """Compatibility wrapper around ``WorkbookWriter``.

    Accepts simple sheet mappings with ``name``, ``headers`` and ``rows`` keys.
    """

    workbook = WorkbookWriter()
    for sheet in sheets:
        if isinstance(sheet, Worksheet):
            workbook.add_sheet(
                sheet.title,
                sheet.rows,
                freeze_panes=sheet.freeze_panes,
                auto_filter=sheet.auto_filter,
                column_widths=sheet.column_widths,
            )
            continue
        title = str(sheet.get("name", "Sheet"))
        headers = sheet.get("headers", [])
        data_rows = sheet.get("rows", [])
        rows = []
        if isinstance(headers, Sequence) and not isinstance(headers, (str, bytes)):
            rows.append(list(headers))
        if isinstance(data_rows, Iterable):
            for row in data_rows:
                if isinstance(row, Sequence) and not isinstance(row, (str, bytes)):
                    rows.append(list(row))
                else:
                    rows.append([row])
        workbook.add_sheet(title, rows)
    return workbook.save(path)


def write_workbook(path: str | Path, sheets: Iterable[dict[str, object] | Worksheet]) -> Path:
    return write_xlsx(path, sheets)
