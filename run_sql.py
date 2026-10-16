"""Runs the Airand SQL against the simulated database and exports Tableau-ready CSVs. [SIMULATED]"""
import sqlite3, csv, os, re
HERE = os.path.dirname(os.path.abspath(__file__))
con = sqlite3.connect(os.path.join(HERE, 'airand_SIMULATED.sqlite'))
con.executescript(open(os.path.join(HERE, 'sql', '01_params_and_views.sql')).read())

out = os.path.join(HERE, 'tableau_SIMULATED'); os.makedirs(out, exist_ok=True)
def dump(sql, name):
    cur = con.execute(sql); cols = [c[0] for c in cur.description]; rows = cur.fetchall()
    with open(os.path.join(out, name), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f); w.writerow(cols); w.writerows(rows)
    return cols, rows

dump("SELECT * FROM v_delivery", 'fact_delivery_SIMULATED.csv')
dump("SELECT * FROM v_zone_day ORDER BY op_date", 'zone_day_SIMULATED.csv')
dump("SELECT * FROM v_cyclist_shift ORDER BY op_date, cyclist", 'cyclist_shift_SIMULATED.csv')
dump("SELECT * FROM v_vendor_week ORDER BY week_start, vendor", 'vendor_week_SIMULATED.csv')

text = open(os.path.join(HERE, 'sql', '02_kpi_queries.sql')).read()
blocks = re.split(r'\n(?=-- @K\d\d )', text)
results = []
for b in blocks:
    m = re.match(r'-- @(K\d\d) (.*)', b)
    if not m: continue
    cur = con.execute(b); cols = [c[0] for c in cur.description]
    results.append((m.group(1), m.group(2), cols, cur.fetchall()))
with open(os.path.join(out, 'kpi_results_by_month_SIMULATED.csv'), 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f); w.writerow(['kpi', 'name', 'op_month', 'measure', 'value'])
    for k, name, cols, rows in results:
        for r in rows:
            for c, val in zip(cols[1:], r[1:]):
                w.writerow([k, name, r[0], c, val])
for k, name, cols, rows in results:
    print(k, name); print('   ', cols)
    for r in rows: print('   ', r)
