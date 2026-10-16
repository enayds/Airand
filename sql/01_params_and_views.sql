-- =====================================================================
-- Airand · Phase 8 · 01  Parameters and analysis views        [SIMULATED]
-- Target: airand_SIMULATED.sqlite (SQLite 3.25+ for window functions)
-- Source of definitions: "Airand — KPI Definitions" (counting rules)
-- All times stored in UTC; '+1 hour' converts to West Africa Time (WAT).
-- =====================================================================

-- ---------------------------------------------------------------------
-- 0. Parameters  (costs not held in operational tables; from the Phase 2
--    unit-economics model, labelled [Assumption] there)
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS param;
CREATE TABLE param (name TEXT PRIMARY KEY, value REAL, note TEXT);
INSERT INTO param VALUES
 ('fixed_rate_ngn',               900,    'RUL-01 pilot rate'),
 ('messaging_ngn_per_message',     10,    'Blended WhatsApp/SMS cost (SRS OI-04)'),
 ('fixed_costs_monthly_ngn',   301667,    'Admin salary, hub, platform, marketing, CLRD licence, CAC, insurance (Phase 2 model)'),
 ('cyclist_kit_monthly_ngn',    15500,    'Per cyclist: bike depreciation, maintenance, kit, data (Phase 2 model)'),
 ('cyclists_in_pool',              10,    'Pool size (Airand plan)'),
 ('model_breakeven_per_day',       46,    'Phase 2 model, assuming 26 operating days a month');

-- Daily fixed cost: the zone opens every day, so monthly costs are spread over
-- 365/12 days, not 26.
DROP VIEW IF EXISTS v_param;
CREATE VIEW v_param AS
SELECT
  (SELECT value FROM param WHERE name='fixed_rate_ngn')            AS rate,
  (SELECT value FROM param WHERE name='messaging_ngn_per_message') AS msg_cost,
  ((SELECT value FROM param WHERE name='fixed_costs_monthly_ngn')
   + (SELECT value FROM param WHERE name='cyclist_kit_monthly_ngn')
     * (SELECT value FROM param WHERE name='cyclists_in_pool')) * 12.0 / 365 AS fixed_daily;

-- ---------------------------------------------------------------------
-- 1. v_delivery  — one row per request, every duration pre-computed
--    (feeds K01–K11, K14 and the Operations page)
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_delivery;
CREATE VIEW v_delivery AS
WITH ev AS (
  SELECT delivery_id,
         MIN(CASE WHEN event_type = 'QUEUED' THEN server_ts END)                       AS queued_ts,
         MAX(CASE WHEN event_type IN ('DELIVERED','DELIVERED_WITHOUT_CODE','FAILED',
                                      'CANCELLED','REFUSED_AT_PICKUP') THEN server_ts END) AS end_ts,
         SUM(event_type = 'CYCLIST_PROMPTED')                                           AS offers,
         SUM(event_type = 'ACK_TIMEOUT')                                                AS missed_offers,
         SUM(event_type = 'MESSAGE_SENT')                                               AS messages,
         MAX(event_type = 'MESSAGE_SENT' AND reason = 'sms_fallback')                   AS sms_fallback,
         SUM(event_type = 'CODE_FAILED')                                                AS code_failures
  FROM delivery_event
  GROUP BY delivery_id
)
SELECT
  d.delivery_id,
  d.ref,
  z.name                                            AS zone,
  v.name                                            AS vendor,
  c.name                                            AS cyclist,
  d.package_category,
  d.raised_by,
  datetime(d.created_at, '+1 hour')                 AS created_wat,
  date(d.created_at, '+1 hour')                     AS op_date,
  date(d.created_at, '+1 hour', 'weekday 0', '-6 days') AS week_start,   -- Monday
  strftime('%Y-%m', d.created_at, '+1 hour')        AS op_month,
  CAST(strftime('%H', d.created_at, '+1 hour') AS INTEGER) AS hour_wat,
  CASE CAST(strftime('%w', d.created_at, '+1 hour') AS INTEGER)
       WHEN 0 THEN '7 Sun' WHEN 1 THEN '1 Mon' WHEN 2 THEN '2 Tue' WHEN 3 THEN '3 Wed'
       WHEN 4 THEN '4 Thu' WHEN 5 THEN '5 Fri' ELSE '6 Sat' END AS weekday,
  CASE WHEN CAST(strftime('%H', d.created_at, '+1 hour') AS INTEGER) >= 18
       THEN 'Peak' ELSE 'Off-peak' END              AS period,
  d.outcome,
  d.outcome_reason,
  CASE WHEN d.outcome = 'cancelled' THEN
       CASE WHEN d.outcome_reason = 'refused_over_limits' THEN 'Refused at pickup'
            WHEN d.assigned_at IS NULL THEN 'Before assignment'
            ELSE 'After assignment' END END         AS cancel_stage,
  (d.activated_at IS NOT NULL)                      AS is_activated,
  (d.outcome IN ('delivered','failed'))             AS is_settled,
  (d.outcome = 'delivered')                         AS is_delivered,
  (ev.queued_ts IS NOT NULL)                        AS is_queued,
  d.vendor_delay                                    AS is_vendor_delay,
  d.without_code                                    AS is_without_code,
  (d.fee_ngn = 0)                                   AS is_trial,
  d.fee_ngn,
  COALESCE(p.amount_settled_ngn, 0)                 AS fee_settled_ngn,
  COALESCE(p.cancel_fee_ngn, 0)                     AS cancel_fee_ngn,
  COALESCE(p.amount_refunded_ngn, 0)                AS refunded_ngn,
  -- K01–K05 durations in minutes
  ROUND((julianday(d.assigned_at)  - julianday(d.activated_at)) * 1440, 2) AS mins_to_assign,
  ROUND((julianday(d.assigned_at)  - julianday(ev.queued_ts))   * 1440, 2) AS mins_queued,
  ROUND((julianday(d.arrived_at)   - julianday(d.assigned_at))  * 1440, 2) AS mins_to_vendor,
  ROUND((julianday(d.picked_up_at) - julianday(d.arrived_at))   * 1440, 2) AS mins_handover,
  ROUND((julianday(d.delivered_at) - julianday(d.picked_up_at)) * 1440, 2) AS mins_ride,
  ROUND((julianday(d.delivered_at) - julianday(d.activated_at)) * 1440, 2) AS mins_end_to_end,
  CASE WHEN d.assigned_at  IS NOT NULL
       THEN (julianday(d.assigned_at) - julianday(d.activated_at)) * 1440 <= 2 END  AS assigned_within_2min,
  CASE WHEN d.delivered_at IS NOT NULL
       THEN (julianday(d.delivered_at) - julianday(d.picked_up_at)) * 1440 <= 30 END AS is_on_time,
  -- cyclist busy time for this job (K21): accepted -> terminal event
  ROUND((julianday(ev.end_ts) - julianday(d.assigned_at)) * 1440, 2) AS mins_cyclist_busy,
  ev.offers,
  ev.missed_offers,
  ev.messages,
  ev.sms_fallback,
  ev.code_failures,
  d.assigned_at                                     AS assigned_at_utc,
  d.cyclist_id
FROM delivery d
JOIN zone z            ON z.zone_id = d.zone_id
JOIN vendor v          ON v.vendor_id = d.vendor_id
LEFT JOIN cyclist c    ON c.cyclist_id = d.cyclist_id
LEFT JOIN payment p    ON p.delivery_id = d.delivery_id
LEFT JOIN ev           ON ev.delivery_id = d.delivery_id;

-- ---------------------------------------------------------------------
-- 2. v_cyclist_shift — one row per shift worked (K19, K21, K22, K23)
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_cyclist_shift;
CREATE VIEW v_cyclist_shift AS
WITH jobs AS (
  SELECT s.shift_id,
         COUNT(vd.delivery_id)                              AS jobs_accepted,
         COALESCE(SUM(vd.is_settled), 0)                    AS settled,
         COALESCE(SUM(vd.mins_cyclist_busy), 0)             AS busy_mins
  FROM shift s
  LEFT JOIN v_delivery vd
         ON vd.cyclist_id = s.cyclist_id
        AND vd.assigned_at_utc BETWEEN s.actual_start AND s.actual_end
  GROUP BY s.shift_id
),
missed AS (
  SELECT s.shift_id, COUNT(a.alert_id) AS missed_offers
  FROM shift s
  LEFT JOIN alert a
         ON a.type = 'ack_timeout' AND a.cyclist_id = s.cyclist_id
        AND a.raised_at BETWEEN s.actual_start AND s.actual_end
  GROUP BY s.shift_id
)
SELECT
  s.shift_id,
  c.name                                                    AS cyclist,
  date(s.actual_start, '+1 hour')                           AS op_date,
  strftime('%Y-%m', s.actual_start, '+1 hour')              AS op_month,
  CASE WHEN strftime('%H', s.planned_start, '+1 hour') = '12' THEN 'Early 12:00–20:00'
       ELSE 'Late 15:30–23:30' END                          AS shift_pattern,
  ROUND((julianday(s.actual_end) - julianday(s.actual_start)) * 1440, 1) AS shift_mins,
  j.jobs_accepted,
  j.settled,
  ROUND(j.busy_mins, 1)                                     AS busy_mins,
  ROUND(j.busy_mins / ((julianday(s.actual_end) - julianday(s.actual_start)) * 1440), 4) AS utilisation,
  m.missed_offers,
  c.retainer_ngn,
  c.bonus_per_delivery_ngn * MAX(j.settled - c.bonus_threshold, 0) AS bonus_ngn,
  c.retainer_ngn + c.bonus_per_delivery_ngn * MAX(j.settled - c.bonus_threshold, 0) AS pay_ngn
FROM shift s
JOIN cyclist c ON c.cyclist_id = s.cyclist_id
JOIN jobs j    ON j.shift_id = s.shift_id
JOIN missed m  ON m.shift_id = s.shift_id;

-- ---------------------------------------------------------------------
-- 3. v_zone_day — one row per operating day (K12, K17–K20; Viability page)
--    Revenue is attributed to the request's operating day; in this data
--    every fee settles the same evening, so this equals settlement date.
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_zone_day;
CREATE VIEW v_zone_day AS
WITH d AS (
  SELECT op_date,
         COUNT(*)                         AS requests,
         SUM(is_activated)                AS activated,
         SUM(is_settled)                  AS settled,
         SUM(is_delivered)                AS delivered,
         SUM(outcome = 'failed')          AS failed,
         SUM(outcome = 'cancelled')       AS cancelled,
         SUM(outcome = 'expired')         AS expired,
         SUM(is_queued)                   AS queued,
         SUM(is_on_time)                  AS on_time,
         SUM(fee_settled_ngn)             AS fees_ngn,
         SUM(cancel_fee_ngn)              AS cancel_fees_ngn,
         COALESCE(SUM(messages), 0)       AS messages,
         COUNT(DISTINCT CASE WHEN is_settled THEN vendor END) AS vendors_active_today
  FROM v_delivery GROUP BY op_date
),
p AS (
  SELECT op_date, COUNT(*) AS shifts, SUM(pay_ngn) AS cyclist_pay_ngn,
         SUM(busy_mins) AS busy_mins, SUM(shift_mins) AS shift_mins
  FROM v_cyclist_shift GROUP BY op_date
)
SELECT
  d.op_date,
  strftime('%Y-%m', d.op_date)                              AS op_month,
  d.requests, d.activated, d.settled, d.delivered, d.failed, d.cancelled, d.expired, d.queued,
  d.vendors_active_today,
  ROUND(AVG(d.settled) OVER (ORDER BY d.op_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 1) AS settled_7d_avg,
  d.fees_ngn + d.cancel_fees_ngn                            AS revenue_ngn,
  p.cyclist_pay_ngn,
  ROUND(vp.fixed_daily)                                     AS fixed_costs_ngn,
  d.messages * vp.msg_cost                                  AS messaging_ngn,
  d.fees_ngn + d.cancel_fees_ngn - p.cyclist_pay_ngn - ROUND(vp.fixed_daily) - d.messages * vp.msg_cost AS profit_ngn,
  ROUND((p.cyclist_pay_ngn + vp.fixed_daily + d.messages * vp.msg_cost) / NULLIF(d.settled, 0)) AS cost_per_settled_ngn,
  -- break-even for that day's actual cost base: deliveries needed at rate minus messaging
  ROUND((p.cyclist_pay_ngn + vp.fixed_daily) / (vp.rate - vp.msg_cost), 1) AS breakeven_settled,
  ROUND(1.0 * p.busy_mins / p.shift_mins, 4)               AS utilisation,
  p.shifts
FROM d
JOIN p ON p.op_date = d.op_date
CROSS JOIN v_param vp;

-- ---------------------------------------------------------------------
-- 4. v_vendor_week — one row per vendor per Monday–Sunday week (K11, K13, K15, K16)
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_vendor_week;
CREATE VIEW v_vendor_week AS
WITH w AS (
  SELECT vendor, week_start,
         COUNT(*)                 AS requests,
         SUM(is_settled)          AS settled,
         SUM(outcome='cancelled') AS cancelled,
         SUM(outcome='failed')    AS failed,
         SUM(is_vendor_delay)     AS vendor_delays,
         SUM(CASE WHEN mins_handover IS NOT NULL THEN 1 ELSE 0 END) AS picked_up,
         SUM(fee_settled_ngn + cancel_fee_ngn) AS revenue_ngn,
         SUM(is_trial)            AS trial_deliveries,
         COUNT(DISTINCT op_date)  AS days_with_orders
  FROM v_delivery GROUP BY vendor, week_start
)
SELECT w.*,
       ROUND(1.0 * w.settled / 7, 1)                          AS settled_per_day,
       (w.settled > 0)                                        AS is_active,
       (1.0 * w.settled / 7 >= 30)                            AS is_anchor,
       ROUND(1.0 * w.vendor_delays / NULLIF(w.picked_up, 0), 3) AS vendor_delay_rate,
       COALESCE(LAG(w.settled > 0) OVER (PARTITION BY w.vendor ORDER BY w.week_start), 0) AS was_active_prev_week
FROM w;
