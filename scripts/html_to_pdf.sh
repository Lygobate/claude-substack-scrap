#!/usr/bin/env bash
# Render a local HTML file to PDF using headless Chrome.
#
#   ./html_to_pdf.sh playbook.html [out.pdf]
#
# Chrome is the pragmatic choice on macOS: pandoc, weasyprint and wkhtmltopdf
# are usually absent, while Chrome is almost always installed. It renders the
# same engine the HTML was designed against, so the PDF matches the page.
set -euo pipefail

SRC="${1:?usage: html_to_pdf.sh <input.html> [output.pdf]}"
OUT="${2:-${SRC%.*}.pdf}"

[ -f "$SRC" ] || { echo "Not found: $SRC" >&2; exit 1; }

CHROME=""
for c in \
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  "/Applications/Chromium.app/Contents/MacOS/Chromium" \
  "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser" \
  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge" \
  "$(command -v google-chrome || true)" \
  "$(command -v chromium || true)"; do
  [ -n "$c" ] && [ -x "$c" ] && CHROME="$c" && break
done
[ -n "$CHROME" ] || { echo "No Chrome/Chromium found. Install one, or ship the HTML instead." >&2; exit 1; }

# Absolute file:// URL, otherwise Chrome resolves relative to its own cwd.
ABS="$(cd "$(dirname "$SRC")" && pwd)/$(basename "$SRC")"

"$CHROME" --headless --disable-gpu --no-sandbox \
  --no-pdf-header-footer \
  --virtual-time-budget=10000 \
  --print-to-pdf="$OUT" "file://$ABS" 2>/dev/null

[ -s "$OUT" ] || { echo "Chrome produced nothing. Check the HTML." >&2; exit 1; }
echo "PDF: $OUT ($(du -h "$OUT" | cut -f1))"
