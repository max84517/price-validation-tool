"""Quick smoke test for cartesian best-match logic in compare()."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pandas as pd
from price_validation.validation.compare import compare

PT_FEAT  = {"HP/ODM Part#": "A", "Color": "", "Product": "", "Size": "",
            "ODM (Regional Site)": "", "GTK Suppliers": "", "Platforms/Project": ""}
SHP_FEAT = {"HP/ODM Part#": "A", "Color": "", "Product": "", "Size": "",
            "ODM": "", "GTK Suppliers": "", "Platforms": ""}

def make_pt(*rows, months=("Jan",)):
    data = []
    for idx, *rebates in rows:
        row = {"__index__": idx, **PT_FEAT}
        for m, v in zip(months, rebates):
            row[f"Rebate_{m}"] = v
        data.append(row)
    return pd.DataFrame(data)

def make_shp(*rows, months=("Jan",)):
    data = []
    for idx, *rebates in rows:
        row = {"__index__": idx, **SHP_FEAT}
        for m, v in zip(months, rebates):
            row[f"Rebate_{m}"] = v
        data.append(row)
    return pd.DataFrame(data)

def run(name, result, expected_count):
    actual = len(result)
    status = "PASS" if actual == expected_count else "FAIL"
    print(f"[{status}] {name}: expected {expected_count}, got {actual}")
    if actual != expected_count:
        for r in result:
            print(f"       {r.month} | {r.index_value} | {r.comment}")

# ── Test 1: PT duplicate, SHP matches SECOND row → 0 mismatches with allow_pt_only=True ──
pt = make_pt(("A-X", 1.0), ("A-X", 2.0))
shp = make_shp(("A-X", 2.0))
run("PT dup, SHP matches 2nd row, pt_only=True  → 0",  compare(pt, shp, ["Jan"], "S", allow_pt_only=True),  0)
# With pt_only=False: index IS in SHP → extra PT row not flagged as PT-only → still 0
run("PT dup, SHP matches 2nd row, pt_only=False → 0",  compare(pt, shp, ["Jan"], "S", allow_pt_only=False), 0)

# ── Test 2: PT duplicate, SHP matches FIRST row → 0 mismatches with allow_pt_only=True ──
shp2 = make_shp(("A-X", 1.0))
run("PT dup, SHP matches 1st row, pt_only=True  → 0",  compare(pt, shp2, ["Jan"], "S", allow_pt_only=True),  0)

# ── Test 3: Real mismatch – SHP price doesn't match ANY PT row ───────────────
shp3 = make_shp(("A-X", 3.0))
run("PT dup, SHP no match, pt_only=True  → 1",         compare(pt, shp3, ["Jan"], "S", allow_pt_only=True),  1)
# Only 1 mismatch (best PT row vs SHP); extra PT row not flagged since index IS in SHP
run("PT dup, SHP no match, pt_only=False → 1",         compare(pt, shp3, ["Jan"], "S", allow_pt_only=False), 1)

# ── Test 4: PT single, SHP single, prices equal → 0 ─────────────────────────
pt4  = make_pt(("B-Y", 5.0))
shp4 = make_shp(("B-Y", 5.0))
run("Simple match, equal prices → 0",           compare(pt4, shp4, ["Jan"], "S"), 0)

# ── Test 5: PT single, SHP single, prices differ → 1 ────────────────────────
shp5 = make_shp(("B-Y", 6.0))
run("Simple match, diff prices → 1",            compare(pt4, shp5, ["Jan"], "S"), 1)

# ── Test 6: PT 2 rows (same price), SHP 2 rows (same price) → 0 ─────────────
pt6  = make_pt(("C-Z", 3.0), ("C-Z", 3.0))
shp6 = make_shp(("C-Z", 3.0), ("C-Z", 3.0))
run("Both dup, all same price → 0",             compare(pt6, shp6, ["Jan"], "S"), 0)

# ── Test 7: allow_pt_only – unmatched PT row should be skipped ───────────────
pt7  = make_pt(("D-W", 1.0), ("D-W", 2.0))
shp7 = make_shp(("D-W", 1.0))
run("PT dup, 1 consumed, allow_pt_only=True → 0", compare(pt7, shp7, ["Jan"], "S", allow_pt_only=True), 0)
# Extra PT row not PT-only when index IS in SHP
run("PT dup, 1 consumed, allow_pt_only=False→ 0", compare(pt7, shp7, ["Jan"], "S", allow_pt_only=False), 0)

# ── Test 8: Multi-month scenario ─────────────────────────────────────────────
pt8  = make_pt(("E-V", 1.0, 2.0), ("E-V", 3.0, 4.0), months=("Jan","Feb"))
shp8 = make_shp(("E-V", 3.0, 4.0), months=("Jan","Feb"))
run("Multi-month, SHP matches 2nd row, pt_only=True  → 0", compare(pt8, shp8, ["Jan","Feb"], "S", allow_pt_only=True),  0)
# Extra PT row not flagged when index IS in SHP
run("Multi-month, SHP matches 2nd row, pt_only=False → 0", compare(pt8, shp8, ["Jan","Feb"], "S", allow_pt_only=False), 0)

print("Done.")
