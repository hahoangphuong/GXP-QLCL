/** Build the B6I human-editing workbook. This script has no database access. */
import fs from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";
const artifactToolUrl = process.env.B6I_ARTIFACT_TOOL_URL || "@oai/artifact-tool";
const artifactTool = await import(artifactToolUrl);
const { SpreadsheetFile, Workbook } = artifactTool;
const require = createRequire(import.meta.url);
const nodeModulesMarker = `${path.sep}node_modules${path.sep}`;
const artifactToolPath = artifactToolUrl.startsWith("file:") ? fileURLToPath(artifactToolUrl) : null;
const nodeModulesRoot = artifactToolPath && artifactToolPath.slice(0, artifactToolPath.indexOf(nodeModulesMarker) + nodeModulesMarker.length);
if (!nodeModulesRoot) throw new Error("B6I artifact-tool URL must identify its bundled node_modules root");
const JSZip = require(path.join(nodeModulesRoot, "jszip"));

function argument(name) {
  const index = process.argv.indexOf(name);
  if (index < 0 || !process.argv[index + 1]) throw new Error(`missing ${name}`);
  return process.argv[index + 1];
}

const roster = JSON.parse(await fs.readFile(argument("--roster"), "utf8"));
const evidence = JSON.parse(await fs.readFile(argument("--evidence"), "utf8"));
const outputPath = argument("--output");
const workbook = Workbook.create();
const headerStyle = { fill: "#0F766E", font: { bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true };
const metadata = [
  ["legacy_snapshot_sha256", roster.legacy_snapshot_sha256],
  ["canonical_state_sha256", roster.canonical_state_sha256],
  ["planner_version", roster.planner_version],
  ["candidate_set_sha256", roster.candidate_set_sha256],
];

function setup(sheet, title) {
  sheet.showGridLines = false;
  sheet.getRange("A1").values = [[title]];
  sheet.getRange("A1").format = { font: { bold: true, size: 16, color: "#0F172A" } };
}

async function requireReviewTableAutoFilter(outputPath, rangeAddress) {
  const zip = await JSZip.loadAsync(await fs.readFile(outputPath));
  const tables = Object.values(zip.files).filter((file) => /^xl\/tables\/table\d+\.xml$/.test(file.name));
  const table = await (async () => {
    for (const file of tables) {
      const xml = await file.async("string");
      if (xml.includes('name="ProductionLineReviewCandidates"')) return { file, xml };
    }
    return null;
  })();
  if (!table || !table.xml.includes(`ref="${rangeAddress}"`)) {
    throw new Error("REVIEW table export is missing or has an unexpected range");
  }
  const filter = `<x:autoFilter ref="${rangeAddress}" />`;
  if (!table.xml.includes(filter)) {
    if (table.xml.includes("<x:autoFilter")) {
      throw new Error("REVIEW table export has an unexpected autoFilter range");
    }
    const patched = table.xml.replace(/(<x:table\b[^>]*>)/, `$1${filter}`);
    if (patched === table.xml) throw new Error("REVIEW table export cannot be patched with an autoFilter");
    zip.file(table.file.name, patched);
    await fs.writeFile(outputPath, await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" }));
  }
}

const readme = workbook.worksheets.add("README");
setup(readme, "ProductionLine physical identity review workspace");
readme.getRange("A3:B10").values = [
  ["Purpose", "Human review only. This workbook cannot create or update ProductionLine, Case, or Certificate records."],
  ["Physical identity", "A reviewed Site-scoped physical production line. Legacy MÃ DC is compatibility text and does not prove identity."],
  ["Review workflow", "Review A_MULTI_SOURCE_HIGH_INFORMATION, then B_CASE_ONLY, C_SPECIAL_EXCEPTION, and D_LOW_INFORMATION. Exceptions require documented human review and never approve a physical identity automatically."],
  ["Approve new", "Requires an approved display/business code. Technical UUID allocation belongs to a future apply phase."],
  ["Map existing", "Unavailable in this workbook because the bound canonical state has no ProductionLine rows."],
  ["No write", "The XLSX-to-JSON importer validates review decisions; it never writes a database."],
  ["Provenance", "The metadata below is validated against the authoritative roster template; hiding/protection is not a security boundary."],
  ["Evidence", "EVIDENCE is compact and excludes irrelevant personal information."],
];
readme.getRange("A13:B16").values = metadata;
readme.getRange("A13:A16").format = headerStyle;
readme.getRange("A:B").format.columnWidth = 55;
readme.getRange("B3:B16").format.wrapText = true;

const review = workbook.worksheets.add("REVIEW");
setup(review, "Review decisions");
const headers = ["Review order", "Primary batch", "Candidate key", "Site", "Legacy Site ID", "Canonical Site ID", "Canonical line text", "Observed raw texts", "Case/Certificate agreement", "Case count", "Certificate count", "GxP contexts", "Cross-site reuse", "Special exception", "Review tags", "Decision", "Approved display code", "Existing ProductionLine ID", "Review reason", "Reviewer", "Reviewed at"];
review.getRangeByIndexes(2, 0, 1, headers.length).values = [headers];
review.getRangeByIndexes(2, 0, 1, headers.length).format = headerStyle;
const reviewRows = roster.items.map((item) => [
  item.review_order, item.primary_review_batch, item.candidate_key, item.site_display_name || "", item.source_site_legacy_id,
  item.canonical_site_id, item.canonical_line_text, item.observed_line_texts_raw.join(" | "), item.case_certificate_agreement ? "YES" : "NO", item.case_count,
  item.certificate_count, item.gxp_contexts.join(", "), item.cross_site_same_text ? "YES" : "NO", item.primary_review_batch === "C_SPECIAL_EXCEPTION" ? "YES" : "NO", item.review_tags.join(", "), item.review_decision,
  item.approved_display_code || "", item.existing_production_line_id || "", item.review_reason || "", item.reviewer || "", item.reviewed_at || "",
]);
review.getRangeByIndexes(3, 0, reviewRows.length, headers.length).values = reviewRows;
review.getRange(`P4:P${reviewRows.length + 3}`).dataValidation = { rule: { type: "list", values: ["PENDING_HUMAN_REVIEW", "APPROVE_NEW_PHYSICAL_LINE", "REJECT_NOT_PHYSICAL_LINE", "DEFER_INSUFFICIENT_EVIDENCE", "SPLIT_REQUIRED", "CONFLICT"] } };
review.freezePanes.freezeRows(3);
// A table supplies Excel's column filters without changing the review data contract.
review.tables.add(`A3:U${reviewRows.length + 3}`, true, "ProductionLineReviewCandidates");
review.getRangeByIndexes(2, 0, reviewRows.length + 1, headers.length).format.borders = { preset: "all", style: "thin", color: "#D7E3E8" };
review.getRange("A:U").format.columnWidth = 18;
review.getRange("C:C").format.columnWidth = 35;
review.getRange("D:D").format.columnWidth = 32;
review.getRange("G:H").format.columnWidth = 28;
review.getRange("L:O").format.columnWidth = 30;
review.getRange("S:S").format.columnWidth = 38;
review.getRange(`A4:U${reviewRows.length + 3}`).format.wrapText = true;

const sites = workbook.worksheets.add("SITES");
setup(sites, "Site index");
sites.getRange("A3:D3").values = [["Legacy Site ID", "Canonical Site ID", "Site display/name", "Candidate count"]];
sites.getRange("A3:D3").format = headerStyle;
const siteRows = Object.values(roster.items.reduce((acc, item) => {
  const key = item.source_site_legacy_id;
  if (!acc[key]) acc[key] = [key, item.canonical_site_id, item.site_display_name || "", 0];
  acc[key][3] += 1;
  return acc;
}, {})).sort((a, b) => a[0] - b[0]);
sites.getRangeByIndexes(3, 0, siteRows.length, 4).values = siteRows;
sites.freezePanes.freezeRows(3);
sites.getRange("A:D").format.columnWidth = 32;

const evidenceSheet = workbook.worksheets.add("EVIDENCE");
setup(evidenceSheet, "Compact source evidence");
const evidenceHeaders = ["Candidate key", "Case samples", "Certificate samples"];
evidenceSheet.getRange("A3:C3").values = [evidenceHeaders];
evidenceSheet.getRange("A3:C3").format = headerStyle;
const evidenceRows = evidence.records.map((record) => [
  record.candidate_key,
  record.case_samples.map((sample) => `ID ${sample.legacy_inspection_id}; scope ${sample.scope_code || ""}; ${sample.source_ref.source_sheet} row ${sample.source_ref.source_row_number}`).join("\n"),
  record.certificate_samples.map((sample) => `ID ${sample.legacy_certificate_id}; line ${sample.line_code_raw || ""}; ref ${sample.certificate_reference || ""}; ${sample.source_ref.source_sheet} row ${sample.source_ref.source_row_number}`).join("\n"),
]);
evidenceSheet.getRangeByIndexes(3, 0, evidenceRows.length, 3).values = evidenceRows;
evidenceSheet.freezePanes.freezeRows(3);
evidenceSheet.getRange("A:C").format.columnWidth = 48;
evidenceSheet.getRange(`A4:C${evidenceRows.length + 3}`).format.wrapText = true;

const summary = workbook.worksheets.add("SUMMARY");
setup(summary, "Review summary");
const count = (selector) => roster.items.filter(selector).length;
const summaryRows = [
  ["Metric", "Count"],
  ["Candidates", roster.items.length],
  ["Site resolved", count((item) => item.canonical_site_id)],
  ["Pending", count((item) => item.review_decision === "PENDING_HUMAN_REVIEW")],
  ...Object.entries(roster.items.flatMap((item) => item.review_tags).reduce((acc, tag) => ({ ...acc, [tag]: (acc[tag] || 0) + 1 }), {})).sort().map(([tag, value]) => [tag, value]),
];
summary.getRangeByIndexes(2, 0, summaryRows.length, 2).values = summaryRows;
summary.getRange("A3:B3").format = headerStyle;
summary.getRange("A:B").format.columnWidth = 44;

workbook.recalculate();
await fs.mkdir(new URL(".", `file:///${outputPath.replaceAll("\\", "/")}`).pathname, { recursive: true }).catch(() => {});
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
await requireReviewTableAutoFilter(outputPath, `A3:U${reviewRows.length + 3}`);
