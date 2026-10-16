-- =====================================================================
-- Airand · Phase 8 · 02  KPI queries K01–K23                [SIMULATED]
-- Run after 01_params_and_views.sql. Each query returns one row per month.
-- Medians and 90th percentiles use ROW_NUMBER (SQLite has no PERCENTILE).
-- Each query starts with a line "-- @Kxx <name>" so a runner can split them.
-- =====================================================================

-- @K01 Request-to-assignment time (minutes; % within 2 min at peak)
WITH x AS (SELECT op_month, period, mins_to_assign v, assigned_within_2min ok
           FROM v_delivery WHERE mins_to_assign IS NOT NULL),
r AS (SELECT op_month, v, ROW_NUMBER() OVER (PARTITION BY op_month ORDER BY v) rn,
             COUNT(*) OVER (PARTITION BY op_month) n FROM x)
SELECT r.op_month,
       MAX(CASE WHEN rn = (n + 1) / 2 THEN v END)         AS median_mins,
       MAX(CASE WHEN rn = CAST(0.9 * n AS INT) THEN v END) AS p90_mins,
       (SELECT ROUND(AVG(ok), 3) FROM x WHERE x.op_month = r.op_month AND x.period = 'Peak') AS peak_within_2min
FROM r GROUP BY r.op_month;

-- @K02 Time to vendor (minutes)
WITH r AS (SELECT op_month, mins_to_vendor v,
                  ROW_NUMBER() OVER (PARTITION BY op_month ORDER BY mins_to_vendor) rn,
                  COUNT(*) OVER (PARTITION BY op_month) n
           FROM v_delivery WHERE mins_to_vendor IS NOT NULL)
SELECT op_month,
       MAX(CASE WHEN rn = (n + 1) / 2 THEN v END)         AS median_mins,
       MAX(CASE WHEN rn = CAST(0.9 * n AS INT) THEN v END) AS p90_mins,
       ROUND(AVG(v <= 8), 3)                               AS within_8min
FROM r GROUP BY op_month;

-- @K03 Vendor handover time (minutes)
WITH r AS (SELECT op_month, mins_handover v,
                  ROW_NUMBER() OVER (PARTITION BY op_month ORDER BY mins_handover) rn,
                  COUNT(*) OVER (PARTITION BY op_month) n
           FROM v_delivery WHERE mins_handover IS NOT NULL)
SELECT op_month,
       MAX(CASE WHEN rn = (n + 1) / 2 THEN v END)         AS median_mins,
       MAX(CASE WHEN rn = CAST(0.9 * n AS INT) THEN v END) AS p90_mins
FROM r GROUP BY op_month;

-- @K04 Delivery time, pickup to door (minutes)
WITH r AS (SELECT op_month, mins_ride v,
                  ROW_NUMBER() OVER (PARTITION BY op_month ORDER BY mins_ride) rn,
                  COUNT(*) OVER (PARTITION BY op_month) n
           FROM v_delivery WHERE mins_ride IS NOT NULL)
SELECT op_month,
       MAX(CASE WHEN rn = (n + 1) / 2 THEN v END)         AS median_mins,
       MAX(CASE WHEN rn = CAST(0.9 * n AS INT) THEN v END) AS p90_mins
FROM r GROUP BY op_month;

-- @K05 End-to-end time, paid to delivered (minutes)
WITH r AS (SELECT op_month, mins_end_to_end v,
                  ROW_NUMBER() OVER (PARTITION BY op_month ORDER BY mins_end_to_end) rn,
                  COUNT(*) OVER (PARTITION BY op_month) n
           FROM v_delivery WHERE mins_end_to_end IS NOT NULL)
SELECT op_month,
       MAX(CASE WHEN rn = (n + 1) / 2 THEN v END)         AS median_mins,
       MAX(CASE WHEN rn = CAST(0.9 * n AS INT) THEN v END) AS p90_mins
FROM r GROUP BY op_month;

-- @K06 On-time rate (delivered within 30 min of pickup)
SELECT op_month, ROUND(AVG(is_on_time), 3) AS on_time_rate
FROM v_delivery WHERE is_delivered GROUP BY op_month;

-- @K07 Failure rate (failed / settled) and top reason
SELECT op_month,
       ROUND(1.0 * SUM(outcome = 'failed') / SUM(is_settled), 3) AS failure_rate,
       SUM(outcome_reason = 'receiver_unreachable')              AS unreachable,
       SUM(outcome_reason = 'receiver_refused')                  AS refused,
       SUM(outcome_reason = 'wrong_address')                     AS wrong_address
FROM v_delivery GROUP BY op_month;

-- @K08 Cancellation rate (cancelled / activated) by stage
SELECT op_month,
       ROUND(1.0 * SUM(outcome = 'cancelled') / SUM(is_activated), 3)       AS cancellation_rate,
       SUM(cancel_stage = 'Before assignment')                               AS before_assignment,
       SUM(cancel_stage = 'After assignment')                                AS after_assignment,
       SUM(cancel_stage = 'Refused at pickup')                               AS refused_at_pickup
FROM v_delivery GROUP BY op_month;

-- @K09 Queue rate and median queue time; peak and the worst hour
WITH q AS (SELECT op_month, hour_wat, period, is_queued, mins_queued FROM v_delivery WHERE is_activated),
r AS (SELECT op_month, mins_queued v,
             ROW_NUMBER() OVER (PARTITION BY op_month ORDER BY mins_queued) rn,
             COUNT(*) OVER (PARTITION BY op_month) n
      FROM q WHERE mins_queued IS NOT NULL),
h AS (SELECT op_month, hour_wat, AVG(is_queued) rate,
             ROW_NUMBER() OVER (PARTITION BY op_month ORDER BY AVG(is_queued) DESC) k
      FROM q GROUP BY op_month, hour_wat)
SELECT q.op_month,
       ROUND(AVG(q.is_queued), 3)                                           AS queue_rate,
       ROUND(AVG(CASE WHEN q.period = 'Peak' THEN q.is_queued END), 3)       AS peak_queue_rate,
       (SELECT MAX(CASE WHEN rn = (n + 1) / 2 THEN v END) FROM r WHERE r.op_month = q.op_month) AS median_queue_mins,
       (SELECT hour_wat FROM h WHERE h.op_month = q.op_month AND k = 1)      AS worst_hour,
       (SELECT ROUND(rate, 3) FROM h WHERE h.op_month = q.op_month AND k = 1) AS worst_hour_rate
FROM q GROUP BY q.op_month;

-- @K10 Proof rate and without-code share
SELECT op_month,
       ROUND(1.0 * SUM(is_settled AND (is_delivered OR outcome_reason IS NOT NULL)) / SUM(is_settled), 3) AS proof_rate,
       ROUND(1.0 * SUM(is_without_code) / SUM(is_delivered), 3)                                         AS without_code_share
FROM v_delivery GROUP BY op_month;

-- @K11 Vendor delay rate (per month, all vendors; vendor detail in v_vendor_week)
SELECT op_month,
       ROUND(1.0 * SUM(is_vendor_delay) / SUM(mins_handover IS NOT NULL), 3) AS vendor_delay_rate,
       (SELECT vendor FROM v_delivery v2 WHERE v2.op_month = v1.op_month AND v2.mins_handover IS NOT NULL
        GROUP BY vendor ORDER BY AVG(is_vendor_delay) DESC LIMIT 1)            AS worst_vendor
FROM v_delivery v1 GROUP BY op_month;

-- @K12 Settled deliveries per day (north star) vs break-even
SELECT op_month,
       ROUND(AVG(settled), 1)             AS settled_per_day,
       ROUND(AVG(breakeven_settled), 1)   AS breakeven_per_day,
       SUM(settled >= breakeven_settled)  AS days_at_or_above_breakeven,
       COUNT(*)                           AS days
FROM v_zone_day GROUP BY op_month;

-- @K13 Settled deliveries per active vendor per day
SELECT op_month, ROUND(1.0 * SUM(settled) / SUM(vendors_active_today), 1) AS settled_per_active_vendor
FROM v_zone_day GROUP BY op_month;

-- @K14 Demand: peak share and payment expiry rate
SELECT op_month,
       ROUND(AVG(period = 'Peak'), 3)                AS peak_share,
       ROUND(AVG(outcome = 'expired'), 3)            AS expiry_rate
FROM v_delivery GROUP BY op_month;

-- @K15 Active vendors and anchors (last full week of the month)
WITH lw AS (SELECT strftime('%Y-%m', week_start) m, MAX(week_start) ws FROM v_vendor_week GROUP BY m)
SELECT lw.m AS op_month, SUM(vw.is_active) AS active_vendors, SUM(vw.is_anchor) AS anchor_vendors
FROM lw JOIN v_vendor_week vw ON vw.week_start = lw.ws GROUP BY lw.m;

-- @K16 Vendor retention (active this week and last ÷ active last week)
SELECT strftime('%Y-%m', week_start) AS op_month,
       ROUND(1.0 * SUM(is_active AND was_active_prev_week) / NULLIF(SUM(was_active_prev_week), 0), 3) AS weekly_retention
FROM v_vendor_week GROUP BY op_month;

-- @K17 Revenue (₦)
SELECT op_month, SUM(revenue_ngn) AS revenue_ngn, ROUND(AVG(revenue_ngn)) AS revenue_per_day_ngn
FROM v_zone_day GROUP BY op_month;

-- @K18 All-in cost per settled delivery (₦)
SELECT op_month,
       ROUND((SUM(cyclist_pay_ngn) + SUM(fixed_costs_ngn) + SUM(messaging_ngn)) / SUM(settled)) AS cost_per_settled_ngn
FROM v_zone_day GROUP BY op_month;

-- @K19 Cyclist pay (₦)
SELECT op_month, SUM(pay_ngn) AS cyclist_pay_ngn, SUM(bonus_ngn) AS of_which_bonus_ngn
FROM v_cyclist_shift GROUP BY op_month;

-- @K20 Zone operating profit and margin (₦)
SELECT op_month, SUM(profit_ngn) AS profit_ngn,
       ROUND(1.0 * SUM(profit_ngn) / SUM(revenue_ngn), 3) AS margin
FROM v_zone_day GROUP BY op_month;

-- @K21 Cyclist utilisation (busy ÷ shift time), whole day and by shift pattern
SELECT op_month,
       ROUND(SUM(busy_mins) / SUM(shift_mins), 3)                                       AS utilisation,
       ROUND(SUM(CASE WHEN shift_pattern LIKE 'Early%' THEN busy_mins END)
             / SUM(CASE WHEN shift_pattern LIKE 'Early%' THEN shift_mins END), 3)       AS early_shift,
       ROUND(SUM(CASE WHEN shift_pattern LIKE 'Late%' THEN busy_mins END)
             / SUM(CASE WHEN shift_pattern LIKE 'Late%' THEN shift_mins END), 3)        AS late_shift
FROM v_cyclist_shift GROUP BY op_month;

-- @K22 Settled deliveries per cyclist per shift
SELECT op_month, ROUND(AVG(settled), 1) AS settled_per_shift
FROM v_cyclist_shift GROUP BY op_month;

-- @K23 Cyclist unresponsive rate (missed offers ÷ offers) and worst cyclist
SELECT op_month,
       ROUND(1.0 * SUM(missed_offers) / SUM(offers), 3) AS unresponsive_rate,
       (SELECT cyclist FROM (
          SELECT c.name AS cyclist, 1.0 * COUNT(a.alert_id) /
                 (SELECT COUNT(*) FROM delivery_event e WHERE e.event_type = 'CYCLIST_PROMPTED'
                    AND e.reason = c.name AND strftime('%Y-%m', e.server_ts, '+1 hour') = v.op_month) AS r
          FROM cyclist c LEFT JOIN alert a ON a.cyclist_id = c.cyclist_id AND a.type = 'ack_timeout'
               AND strftime('%Y-%m', a.raised_at, '+1 hour') = v.op_month
          GROUP BY c.name ORDER BY r DESC LIMIT 1))           AS worst_cyclist
FROM v_delivery v GROUP BY op_month;
