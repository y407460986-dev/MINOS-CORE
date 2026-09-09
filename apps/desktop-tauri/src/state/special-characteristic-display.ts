import type { WorkbenchRow } from "../api/types";

const legacySpecialCandidateLabel = "特殊特性候选";

function text(value: unknown, fallback = ""): string {
  if (Array.isArray(value)) return value.map((item) => text(item)).filter(Boolean).join(", ");
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function firstRaw(row: Pick<WorkbenchRow, "raw">, fields: string[]): unknown {
  for (const field of fields) {
    const value = row.raw[field];
    if (Array.isArray(value) && value.length === 0) continue;
    if (value !== null && value !== undefined && value !== "") return value;
  }
  return undefined;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function isEmptySpecialCharacteristicText(value: string): boolean {
  const normalized = value.trim().toLowerCase();
  return !normalized || normalized === "-" || normalized === "无" || normalized === "none" || normalized === "n/a" || normalized === "na";
}

export function specialCharacteristicCount(value: unknown): number {
  const count = Number(value ?? 0);
  if (!Number.isFinite(count) || count <= 0) return 0;
  return Math.trunc(count);
}

export function sanitizeSpecialCharacteristicDisplay(value: unknown): string {
  const raw = text(value);
  if (!raw) return "";
  return raw
    .split(",")
    .map((item) => {
      const trimmed = item.trim();
      if (isEmptySpecialCharacteristicText(trimmed)) return "";
      if (/^PTC候选(?=[:：]|$)/i.test(trimmed)) {
        return "";
      }
      if (/^PTC(?:$|-|:|\uFF1A)/i.test(trimmed)) {
        return "";
      }
      if (/^SPCC(?:$|-|:|\uFF1A)/i.test(trimmed)) {
        return "";
      }
      if (new RegExp(`^${legacySpecialCandidateLabel}(?=[:：]|$)`, "i").test(trimmed)) {
        return "";
      }
      return trimmed;
    })
    .filter(Boolean)
    .join(", ");
}

function specialCharacteristicClassification(value: unknown): "SC" | "CC" | "" {
  const classification = sanitizeSpecialCharacteristicDisplay(value).trim().toUpperCase();
  return classification === "SC" || classification === "CC" ? classification : "";
}

function cleanSpecialCharacteristicFeature(value: unknown, classification: "SC" | "CC"): string {
  const cleaned = text(value)
    .replace(new RegExp(`[，,;；]?\\s*(?:图纸)?声明\\s*${classification}\\s*(?:=|:|：)?\\s*\\d+\\s*个?`, "gi"), "")
    .replace(/^[\s:：/]+/, "")
    .replace(/[，,;；\s]+$/, "")
    .trim();
  return sanitizeSpecialCharacteristicDisplay(cleaned);
}

function formatSpecialCharacteristicText(value: unknown): string {
  const raw = text(value).trim();
  if (!raw || /^候选待确认\s*[:：]?/i.test(raw) || /^(?:SC|CC)候选(?=[:：]|$)/i.test(raw)) return "";
  const match = raw.match(/^(SC|CC)(?:$|[\s:：/])/i);
  if (!match) return "";
  const classification = match[1].toUpperCase() as "SC" | "CC";
  const feature = cleanSpecialCharacteristicFeature(raw.slice(match[0].length), classification);
  return [classification, feature].filter(Boolean).join(" / ");
}

function formatFormalSpecialCharacteristic(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map((item) => formatFormalSpecialCharacteristic(item)).filter(Boolean).join(", ");
  }
  const record = asRecord(value);
  if (record) {
    const rawClassification = text(record.classification) || text(record.special_characteristic_class) || text(record.type);
    const classification = specialCharacteristicClassification(rawClassification);
    if (rawClassification && !classification) return "";
    const label = classification
      ? cleanSpecialCharacteristicFeature(
          text(record.name) || text(record.label) || text(record.linked_feature) || text(record.value),
          classification
        )
      : "";
    return [classification, label].filter(Boolean).join(" / ");
  }
  return formatSpecialCharacteristicText(value);
}

function formatConfirmedAiJudgment(value: unknown): string {
  if (!Array.isArray(value)) return "";
  return value
    .map((item) => {
      const record = asRecord(item);
      if (!record || text(record.verdict).toLowerCase() !== "confirmed") return "";
      const classification = text(record.classification).toUpperCase();
      if (classification !== "SC" && classification !== "CC") return "";
      const feature = cleanSpecialCharacteristicFeature(text(record.linked_feature) || text(record.name), classification);
      const label = [classification, feature].filter(Boolean).join(" / ");
      return label;
    })
    .filter(Boolean)
    .join(", ");
}

export function formatDeclaredSpecialDiscovery(raw: Record<string, unknown>): string {
  const specialCharacteristicDiscovery = asRecord(raw.special_characteristic_discovery);
  const declaredTotals = asRecord(raw.declared_totals) ?? asRecord(specialCharacteristicDiscovery?.declared_totals);
  const missingCounts = asRecord(specialCharacteristicDiscovery?.missing_counts);
  if (!declaredTotals) return "";
  const declaredCc = specialCharacteristicCount(declaredTotals?.CC);
  const declaredSc = specialCharacteristicCount(declaredTotals?.SC);
  if (declaredCc <= 0 && declaredSc <= 0) return "";
  const missingCc = specialCharacteristicCount(missingCounts?.CC);
  const missingSc = specialCharacteristicCount(missingCounts?.SC);
  const parts: string[] = [];
  const declaredParts: string[] = [];
  if (declaredCc > 0) declaredParts.push(`声明CC=${declaredCc}`);
  if (declaredSc > 0) declaredParts.push(`声明SC=${declaredSc}`);
  parts.push(declaredParts.join("/"));
  if (declaredCc > 0 && missingCc > 0) parts.push(`缺少CC=${missingCc}`);
  if (declaredSc > 0 && missingSc > 0) parts.push(`缺少SC=${missingSc}`);
  return parts.join(", ");
}

export function specialCharacteristicColumnText(row: Pick<WorkbenchRow, "raw">): string {
  const formal = formatFormalSpecialCharacteristic(firstRaw(row, ["special_characteristics", "special_characteristic", "special_characteristic_class"]));
  if (formal) return formal;
  const aiJudgment = formatConfirmedAiJudgment(row.raw.special_characteristic_judgments);
  if (aiJudgment) return aiJudgment;
  return specialCharacteristicClassification(row.raw.classification) || "-";
}
