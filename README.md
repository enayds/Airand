# Airand: can a bicycle delivery zone for small vendors pay for itself?

**A business analysis case study, from business problem to tested solution.**

- **Read the case study:** [enayds.github.io/projects/airand](https://enayds.github.io/projects/airand/)
- **Explore the dashboard:** [Airand on Tableau Public](https://public.tableau.com/shared/RG58NCYT6)
- **Author:** Chinedu Egbuna, business analyst and data analyst ([portfolio](https://enayds.github.io) · [LinkedIn](https://www.linkedin.com/in/enayds/))

> **Important:** Airand is a portfolio case study, not an operating company. The original business idea is real; the stakeholder interviews and the 90-day operating dataset are **simulated** and labelled as such throughout. No figure here is a real business result.

---

## In one minute

Small food vendors in New Owerri, Nigeria take orders by phone and WhatsApp, then phone around for a rider. Fees are negotiated per trip, food waits for the rider, and nobody keeps a record.

I took an unfinished business plan for **Airand**, a bicycle delivery service, and ran it through a full business analysis: research, stakeholder analysis, requirements, process redesign, wireframes, a data model, SQL, a Tableau dashboard and a user acceptance testing pack.

**What the analysis found**

- **Research changed the problem.** Chowdeck, Bolt Send and local start-ups already serve Owerri, so "small vendors have no delivery option" was no longer true. The defensible gap is narrower: dedicated cyclists **in the neighbourhood, at a flat price, through the 7–11 PM peak**.
- **The model pays.** In the simulated pilot, Zone 1 lost ₦374k in its first month, passed break-even on **30 July** and earned ₦706k in September, at ₦558 cost per delivery against a ₦900 fee.
- **Service holds:** 96% of deliveries arrive within 30 minutes of pickup.
- **The risk is the roster, not the headcount.** One request in five waits for a cyclist, almost all before 15:30 or after 20:00, when only one shift is on. Recommendation (to test): add a 14:00–22:00 shift with the same ten cyclists.

---

## How the work was done

| Phase | What I did | Output |
| --- | --- | --- |
| 1. Discovery | Took apart the original plan; separated facts from assumptions | Business Understanding Document |
| 2. Validation | Researched competitors, pricing and courier licensing; built a unit-economics model | Market research, break-even model (≈ 46 deliveries/day) |
| 3. Current state | Mapped 11 stakeholders, simulated interviews, drew today's process | AS-IS process, journey maps, 12 pain points, 4 root causes |
| 4. Business requirements | Turned root causes into requirements and rules | **BRD**: 23 requirements, 24 business rules |
| 5. Future state | Redesigned the delivery process and operating model | 11-state delivery lifecycle, assignment logic, 6 exception flows |
| 6. Solution requirements | Specified the system and wrote user stories | **SRS**: 53 functional and 14 non-functional requirements, 38 user stories |
| 7. Design | Wireframed four products | 9 screens traced to requirements |
| 8. Data and BI | Designed the data model, defined KPIs, generated data, wrote SQL, built dashboards | 12-table model, 23 KPIs, 90-day dataset, SQL, 4 Tableau dashboards |
| 8b. Testing | Wrote the acceptance tests | **UAT pack**: 49 tests, full traceability |

Every claim in the documents carries a label: **[Source]** (cited), **[Assumption]** (unvalidated), **[Simulated]** (created for the case study) or **[Decision]** (a sponsor decision).

---

## Documents

| Document | Contents |
| --- | --- |
| [Business Requirements Document](docs/Airand_BRD.pdf) | Objectives, gap analysis, 23 business requirements, 24 business rules, scope, risks |
| [Software Requirements Specification](docs/Airand_SRS.pdf) | Functional and non-functional requirements, user stories with acceptance criteria, traceability matrix |
| [Wireframes](docs/Airand_Wireframes.pdf) | Admin console, vendor app, cyclist app and receiver page |
| [Data model](docs/Airand_Data_Model.pdf) | ERD, data dictionary, event taxonomy |
| [KPI definitions](docs/Airand_KPI_Definitions.pdf) | 23 KPIs, driver tree, counting rules, targets |
| [UAT pack](docs/Airand_UAT_Pack.pdf) | Test plan, 49 tests, defect template, requirement-to-test traceability |

---

## What's in this repository

```
.
├── README.md
├── generate_airand_simulated.py   Builds the 90-day synthetic dataset (fixed seed, reproducible)
├── run_sql.py                     Runs the SQL and exports Tableau-ready CSVs
├── airand_SIMULATED.sqlite        The dataset as one SQLite database (12 tables)
├── csv_SIMULATED/                 The same 12 tables as CSV
├── sql/
│   ├── 01_params_and_views.sql    Cost parameters and four analysis views
│   └── 02_kpi_queries.sql         One query per KPI (K01–K23), by month
├── tableau_SIMULATED/             Flat tables used by the Tableau dashboards
│   ├── fact_delivery_SIMULATED.csv     one row per delivery, durations pre-computed
│   ├── zone_day_SIMULATED.csv          one row per day: volume, revenue, costs, profit, break-even
│   ├── cyclist_shift_SIMULATED.csv     one row per shift: utilisation, pay, missed offers
│   ├── vendor_week_SIMULATED.csv       one row per vendor per week
│   └── kpi_results_by_month_SIMULATED.csv
└── docs/                          PDFs of the documents above (BRD, SRS, wireframes, data model, KPIs, UAT) and the unit-economics model
```

### The dataset at a glance

- **Period:** 6 July – 3 October 2026 (90 days), one zone in New Owerri
- **Size:** 4,932 deliveries, 50,132 events; 8 vendors, 10 cyclists
- **Tables:** zone, vendor, wallet, wallet_transaction, cyclist, shift, admin_user, delivery, delivery_event, payment, alert, statement
- **Design choice:** `delivery_event` is append-only and is the source of truth, so every KPI is computed from recorded events rather than counters
- **Times:** stored in UTC; the SQL converts to West Africa Time (UTC+1)

---

## Reproduce the analysis

Needs **Python 3.10+** and nothing else (standard library only).

```bash
# 1. Rebuild the dataset (same seed, identical output)
python3 generate_airand_simulated.py

# 2. Build the analysis views, export Tableau CSVs and print every KPI by month
python3 run_sql.py
```

To explore the data yourself, open `airand_SIMULATED.sqlite` in [DB Browser for SQLite](https://sqlitebrowser.org/) or DBeaver, run `sql/01_params_and_views.sql`, then try any query from `sql/02_kpi_queries.sql`.

**Assumptions built into the simulation** (all editable at the top of the generator): demand ramps over 70 days with Friday and Saturday peaks and ~60% of requests after 18:00; three cyclists work 12:00–20:00 and seven work 15:30–23:30; cost parameters (fee ₦900, messaging ₦10, fixed costs, cyclist kit) come from the Phase 2 unit-economics model and sit in the `param` table.

---

## Tools

Requirements and process work in structured documents; wireframes as interactive prototypes; **Python** (data generation), **SQLite / SQL** (views and KPIs), **Tableau Public** (dashboards and Story), Excel (unit-economics model).

---

## What I'd do next

- Validate the simulated findings with real vendor interviews and a mystery-shop of competitor prices.
- Test the three-shift roster in the simulation before recommending it for a real pilot.
- Revise the "anchor vendor" threshold from 30 to 15 deliveries a day, which better matches small-vendor volumes.

---

*© Chinedu Egbuna. The Airand concept belongs to its founder; this repository is an independent analysis created for a portfolio. All operating data is simulated.*
