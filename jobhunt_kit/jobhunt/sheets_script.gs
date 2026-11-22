// Job tracker for the jobhunt tool. Paste this whole file into Extensions > Apps Script in your
// Google Sheet, then deploy it as a web app (steps are in jobhunt/README.md).
// It only works with the token below, and it only reads and writes the "Applications" tab.

const TOKEN = '__PUT_A_LONG_RANDOM_TOKEN_HERE__';
const TAB = 'Applications';
const HEADERS = ['found_on', 'posted_on', 'applied_on', 'status', 'score', 'company', 'title', 'location', 'years_required', 'matched_skills', 'missing_skills', 'job_url', 'resume', 'applied', 'interested for referral', 'source', 'job_key', 'notes'];
const TEXT_COLS = ['found_on', 'applied_on', 'posted_on', 'job_key'];  // keep dates as plain text

function doGet() {
  return out({ ok: true, message: 'The job tracker script is running.' });
}

function doPost(e) {
  try {
    const req = JSON.parse(e.postData.contents);
    if (req.token !== TOKEN) return out({ ok: false, error: 'wrong token' });
    const sheet = ensureSheet();
    if (req.action === 'read') return out(Object.assign({ ok: true }, readAll(sheet)));
    if (req.action === 'write') return out(Object.assign({ ok: true }, writeAll(sheet, req)));
    return out({ ok: false, error: 'unknown action' });
  } catch (err) {
    return out({ ok: false, error: String(err) });
  }
}

function out(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function headerRow(sheet) {
  const n = Math.max(sheet.getLastColumn(), 1);
  return sheet.getRange(1, 1, 1, n).getValues()[0].map(function (v) { return String(v).trim(); });
}

function ensureSheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(TAB);
  if (!sheet) {
    sheet = ss.insertSheet(TAB);
    sheet.setFrozenRows(1);
  }
  let header = headerRow(sheet);
  HEADERS.forEach(function (name) {
    if (header.indexOf(name) === -1) {
      let last = header.length;
      while (last > 0 && header[last - 1] === '') last--;
      if (last + 1 > sheet.getMaxColumns()) sheet.insertColumnsAfter(sheet.getMaxColumns(), 1);
      sheet.getRange(1, last + 1).setValue(name).setFontWeight('bold');
      header = headerRow(sheet);
    }
  });
  TEXT_COLS.forEach(function (name) {
    const col = header.indexOf(name) + 1;
    if (col > 0) sheet.getRange(1, col, sheet.getMaxRows(), 1).setNumberFormat('@');
  });
  return sheet;
}

function readAll(sheet) {
  const header = headerRow(sheet);
  const last = sheet.getLastRow();
  const rows = [];
  if (last >= 2) {
    const values = sheet.getRange(2, 1, last - 1, header.length).getDisplayValues();
    values.forEach(function (r, i) {
      const row = { _row: i + 2 };
      header.forEach(function (name, j) { if (name) row[name] = r[j]; });
      rows.push(row);
    });
  }
  return { header: header, rows: rows };
}

// Text that starts with = + - @ would be run as a formula, so it is stored as plain text.
function safe(value) {
  if (typeof value === 'string' && /^[=+\-@]/.test(value)) return "'" + value;
  return value;
}

function writeAll(sheet, req) {
  const header = headerRow(sheet);
  let updated = 0;
  (req.updates || []).forEach(function (u) {
    Object.keys(u.cells).forEach(function (name) {
      const col = header.indexOf(name) + 1;
      if (col > 0) {
        sheet.getRange(u.row, col).setValue(safe(u.cells[name]));
        updated++;
      }
    });
  });
  const appends = req.appends || [];
  if (appends.length) {
    const start = Math.max(sheet.getLastRow(), 1) + 1;
    const missing = start + appends.length - 1 - sheet.getMaxRows();
    if (missing > 0) sheet.insertRowsAfter(sheet.getMaxRows(), missing);
    const table = appends.map(function (a) {
      return header.map(function (name) { return name && a[name] !== undefined ? safe(a[name]) : ''; });
    });
    sheet.getRange(start, 1, table.length, header.length).setValues(table);
  }
  return { updated: updated, appended: appends.length };
}
