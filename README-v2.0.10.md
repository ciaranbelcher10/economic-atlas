# v2.0.10: Compare year slider jumped when dragged to the current year

The label beside the slider grew from "2025" to "2026 so far" (v2.0.9). The slider and label share a flex row, so the track shortened under the cursor and the thumb snapped to another year (2021).
The snapshot label now has a fixed width (7.2em, enough for "2026 so far"), so the slider keeps its length whatever the label says. Measured in Chromium: 412px at 1366px wide and 229px at 390px wide, the same for "2025", "2026 so far" and "1990".

## Deploy (Claude Code)
1. Verify the sha256, run `git pull`, then unzip at the repo root.
2. Run `python3 tools/html_gate.py` (expect 0 failures).
3. `git add -u && xargs git add < FILES.txt`, commit "v2.0.10: fixed-width Compare slider label" and push.
