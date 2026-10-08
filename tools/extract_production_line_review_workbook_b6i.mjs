/** Extract only B6I REVIEW decisions and bound metadata from an XLSX workbook. */
import fs from "node:fs/promises";
const artifactTool = await import(process.env.B6I_ARTIFACT_TOOL_URL || "@oai/artifact-tool");
const { FileBlob, SpreadsheetFile } = artifactTool;

function argument(name) {
  const index = process.argv.indexOf(name);
  if (index < 0 || !process.argv[index + 1]) throw new Error(`missing ${name}`);
  return process.argv[index + 1];
}
const input = await FileBlob.load(argument("--input"));
const workbook = await SpreadsheetFile.importXlsx(input);
const readme = workbook.worksheets.getItem("README");
const review = workbook.worksheets.getItem("REVIEW");
const metadataRows = readme.getRange("A13:B16").values;
const metadata = Object.fromEntries(metadataRows);
const values = review.getUsedRange(true).values;
const headers = values[2];
const required = ["Candidate key", "Legacy Site ID", "Canonical Site ID", "Canonical line text", "Decision", "Approved display code", "Existing ProductionLine ID", "Review reason", "Reviewer", "Reviewed at"];
const index = Object.fromEntries(headers.map((header, position) => [header, position]));
if (required.some((header) => index[header] === undefined)) throw new Error("B6I workbook REVIEW headers are invalid");
const cell = (row, name) => row[index[name]] ?? null;
const rows = values.slice(3).filter((row) => cell(row, "Candidate key") !== null && cell(row, "Candidate key") !== "").map((row) => ({
  candidate_key: cell(row, "Candidate key"),
  source_site_legacy_id: cell(row, "Legacy Site ID"),
  canonical_site_id: cell(row, "Canonical Site ID"),
  canonical_line_text: cell(row, "Canonical line text"),
  review_decision: cell(row, "Decision"),
  approved_display_code: cell(row, "Approved display code"),
  existing_production_line_id: cell(row, "Existing ProductionLine ID"),
  review_reason: cell(row, "Review reason"),
  reviewer: cell(row, "Reviewer"),
  reviewed_at: cell(row, "Reviewed at"),
}));
await fs.writeFile(argument("--output"), `${JSON.stringify({ metadata, rows }, null, 2)}\n`, "utf8");
