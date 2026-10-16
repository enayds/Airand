"""
Airand synthetic pilot dataset generator  [SIMULATED]
------------------------------------------------------
Builds 90 days of operations for Zone 1 (World Bank Road, New Owerri) to the
schema in "Airand — Data Model & Data Dictionary". Every row is invented for a
portfolio case study. No real people, phone numbers or businesses.

Output: airand_SIMULATED.sqlite and one CSV per table in ./csv_SIMULATED/
Deterministic: same seed -> same data.
"""
import random, math, sqlite3, csv, os, uuid, hashlib
from datetime import datetime, timedelta, timezone, date

SEED = 20261006
rng = random.Random(SEED)
WAT = timezone(timedelta(hours=1))
START = date(2026, 7, 6)          # a Monday
DAYS = 90
OUT = os.path.dirname(os.path.abspath(__file__))

def uid():
    return str(uuid.UUID(int=rng.getrandbits(128)))

def iso(dt):
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ') if dt else None

def lognorm(median_min, spread):
    return median_min * math.exp(rng.gauss(0, spread))

# ---------------- reference data ----------------
ZONE = dict(zone_id=uid(), name='Zone 1 · World Bank Road', hub_lat=5.4836, hub_lng=7.0333,
            open_from='12:00', open_to='23:30', fixed_rate_ngn=900, cancel_fee_pct=0.20,
            ack_timeout_s=60, queue_alert_s=180, handover_grace_s=300, pickup_alert_s=600,
            delivery_alert_s=1800, payment_expiry_s=600, max_weight_kg=8, max_value_ngn=50000)

ADMINS = [dict(admin_id=uid(), zone_id=ZONE['zone_id'], name='Chinedu', role='system_admin'),
          dict(admin_id=uid(), zone_id=None, name='Founder', role='founder')]
CHINEDU = ADMINS[0]['admin_id']

# name, category, base settled/day at full ramp, join day, handover median (min), delay propensity
VENDOR_SPEC = [
    ("Suya Republic",          "food",   19, 0,  2.0, 0.06),
    ("Grillz & Pepper Soup",   "food",   17, 0,  3.2, 0.22),
    ("Mama Chi's Kitchen",     "food",   9,  0,  2.2, 0.08),
    ("Ada's Home Kitchen",     "food",   6,  0,  2.5, 0.10),
    ("Kopy Corner",            "print",  4,  10, 1.5, 0.03),
    ("Bella Fabrics",          "retail", 3,  17, 1.8, 0.05),
    ("Uncle T's Shawarma",     "food",   8,  24, 2.4, 0.12),
    ("Zobo & Small Chops",     "food",   5,  38, 2.0, 0.07),
]
PKG = {"food": "food", "print": "documents", "retail": "parcel"}

vendors = []
for i, (name, cat, base, join, hand, delay) in enumerate(VENDOR_SPEC):
    vendors.append(dict(vendor_id=uid(), zone_id=ZONE['zone_id'], name=name, category=cat,
        contact_name=f"Contact {i+1}", phone=f"+234000000{1000+i}",
        pickup_address=f"Plot {10+i*3}, World Bank Road area",
        pickup_lat=round(5.4836 + rng.uniform(-0.012, 0.012), 6),
        pickup_lng=round(7.0333 + rng.uniform(-0.012, 0.012), 6),
        trial_start=(START + timedelta(days=join)).isoformat(), status='active',
        onboarded_by=CHINEDU, _base=base, _join=join, _hand=hand, _delay=delay))

CYCLIST_NAMES = ["Emeka O.", "Somto I.", "Chidi A.", "Ngozi E.", "Tobe N.", "Ifeanyi K.",
                 "Uche M.", "Kelechi D.", "Amaka C.", "Obinna U."]
cyclists = []
for i, n in enumerate(CYCLIST_NAMES):
    cyclists.append(dict(cyclist_id=uid(), zone_id=ZONE['zone_id'], name=n, phone=f"+234000000{2000+i}",
        state='off_shift', retainer_ngn=2310, bonus_threshold=6, bonus_per_delivery_ngn=150,
        trained_at=(START - timedelta(days=4)).isoformat(), status='active',
        _unresponsive=0.08 if n == "Amaka C." else 0.025, _speed=rng.uniform(0.9, 1.1)))

# ---------------- roster ----------------
# 3 early (12:00-20:00), 7 late (15:30-23:30) — capacity weighted to the evening peak (RUL-09); each cyclist off one rotating weekday (never Fri/Sat)
def wat(d, hh, mm=0):
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=WAT)

shifts = []
for di in range(DAYS):
    d = START + timedelta(days=di)
    for ci, c in enumerate(cyclists):
        off_day = ci % 5  # Mon-Fri index pattern, skip Fri via mapping below
        off_wd = [0, 1, 2, 3, 6][off_day]  # Mon,Tue,Wed,Thu,Sun
        if d.weekday() == off_wd:
            continue
        early = ci < 3
        ps, pe = (wat(d, 12), wat(d, 20)) if early else (wat(d, 15, 30), wat(d, 23, 30))
        a_s = ps + timedelta(minutes=rng.randint(-5, 8))
        a_e = pe + timedelta(minutes=rng.randint(-4, 6))
        shifts.append(dict(shift_id=uid(), cyclist_id=c['cyclist_id'], zone_id=ZONE['zone_id'],
            planned_start=ps, planned_end=pe, actual_start=a_s, actual_end=a_e, _ci=ci))

# ---------------- demand ----------------
def hour_weight(h):
    # 12:00-23:30, peak after 18:00
    table = {12: 0.55, 13: 0.75, 14: 0.55, 15: 0.45, 16: 0.5, 17: 0.7, 18: 1.2, 19: 1.65,
             20: 1.85, 21: 1.7, 22: 1.25, 23: 0.55}
    return table[h]

def ramp(day_index):
    # pilot ramp: 0.55 -> 1.0 over ~70 days, then flat
    return 0.55 + 0.40 * min(1.0, day_index / 70)

REQUEST_INFLATION = 1.04  # requests that later expire / cancel

requests = []
rain_days = set(rng.sample(range(DAYS), 14))
for di in range(DAYS):
    d = START + timedelta(days=di)
    wk = {4: 1.3, 5: 1.25, 6: 0.9}.get(d.weekday(), 1.0)
    for v in vendors:
        if di < v['_join']:
            continue
        tenure = min(1.0, 0.6 + (di - v['_join']) / 30 * 0.4)
        lam = v['_base'] * ramp(di) * tenure * wk * REQUEST_INFLATION
        n = max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
        hours = list(range(12, 24))
        weights = [hour_weight(h) for h in hours]
        for _ in range(n):
            h = rng.choices(hours, weights)[0]
            m = rng.randint(0, 29 if h == 23 else 59)
            t = wat(d, h, m) + timedelta(seconds=rng.randint(0, 59))
            requests.append(dict(t=t, vendor=v, day=di, rain=di in rain_days))
requests.sort(key=lambda r: r['t'])

# ---------------- simulation ----------------
deliveries, events, payments, alerts, wtx = [], [], [], [], []
wallets = {v['vendor_id']: dict(wallet_id=uid(), vendor_id=v['vendor_id'],
           account_number=f"9012{448300 + i}", _bal=0) for i, v in enumerate(vendors)}
cyc_busy_until = {c['cyclist_id']: None for c in cyclists}
cyc_last_job = {c['cyclist_id']: None for c in cyclists}
shift_index = {}
for s in shifts:
    shift_index.setdefault(s['actual_start'].date(), []).append(s)

def on_shift(cid, t):
    for s in shift_index.get(t.date(), []):
        if s['cyclist_id'] == cid and s['actual_start'] <= t <= s['actual_end']:
            return s
    return None

def topup(v, t):
    w = wallets[v['vendor_id']]
    amt = rng.choice([10000, 15000, 20000, 30000])
    wtx.append(dict(txn_id=uid(), wallet_id=w['wallet_id'], payment_id=None, type='topup',
                    amount_ngn=amt, provider_ref=f"PH-{rng.randint(10000, 99999)}",
                    created_at=t - timedelta(minutes=rng.randint(2, 50))))
    w['_bal'] += amt

ref_no = 1000
for r in requests:
    v, t0 = r['vendor'], r['t']
    ref_no += 1
    did = uid()
    trial = (date.fromisoformat(v['trial_start']) + timedelta(days=7)) > t0.date()
    fee = 0 if trial else ZONE['fixed_rate_ngn']
    seq = [0]
    def ev(etype, ts, frm=None, to=None, actor='system', actor_id=None, reason=None, device_ts=None):
        seq[0] += 1
        events.append(dict(event_id=uid(), delivery_id=did, seq=seq[0], event_type=etype,
            from_state=frm, to_state=to, actor_type=actor, actor_id=actor_id,
            server_ts=ts, device_ts=device_ts, reason=reason))
    D = dict(delivery_id=did, ref=f"AR-{ref_no}", zone_id=ZONE['zone_id'], vendor_id=v['vendor_id'],
             cyclist_id=None, raised_by='admin' if rng.random() < 0.04 else 'vendor',
             package_category=PKG[v['category']] if v['category'] != 'food' else 'food',
             limits_confirmed=1, dropoff_address='[SIMULATED address]',
             dropoff_lat=round(5.4836 + rng.uniform(-0.02, 0.02), 6),
             dropoff_lng=round(7.0333 + rng.uniform(-0.02, 0.02), 6),
             receiver_phone_enc='enc:SIMULATED', note=None, fee_ngn=fee, state=None,
             code_hash=None, tracking_token=hashlib.sha256(did.encode()).hexdigest()[:32],
             created_at=t0, paid_at=None, activated_at=None, assigned_at=None, arrived_at=None,
             picked_up_at=None, delivered_at=None, closed_at=None, vendor_delay=0,
             without_code=0, outcome=None, outcome_reason=None)
    actor_v = ('vendor', v['vendor_id']) if D['raised_by'] == 'vendor' else ('admin', CHINEDU)
    ev('REQUEST_CREATED', t0, None, 'pending_payment', *actor_v)
    P = dict(payment_id=uid(), delivery_id=did, method='wallet', amount_held_ngn=fee,
             amount_settled_ngn=0, amount_refunded_ngn=0, cancel_fee_ngn=0, status='pending',
             held_at=None, settled_at=None)
    payments.append(P); deliveries.append(D)

    # payment
    if rng.random() < 0.018:
        te = t0 + timedelta(minutes=10)
        ev('PAYMENT_EXPIRED', te, 'pending_payment', 'expired')
        D.update(state='expired', outcome='expired', outcome_reason='payment_timeout', closed_at=te)
        P.update(status='expired', amount_held_ngn=0)
        continue
    w = wallets[v['vendor_id']]
    if fee and w['_bal'] < fee:
        topup(v, t0)
    tp = t0 + timedelta(seconds=rng.randint(4, 40) if fee == 0 or rng.random() < 0.9 else rng.randint(60, 400))
    if fee:
        w['_bal'] -= fee
        wtx.append(dict(txn_id=uid(), wallet_id=w['wallet_id'], payment_id=P['payment_id'], type='hold',
                        amount_ngn=-fee, provider_ref=None, created_at=tp))
    ev('PAYMENT_HELD', tp, 'pending_payment', 'active')
    D.update(paid_at=tp, activated_at=tp, state='active'); P.update(status='held', held_at=tp)

    def refund(amount, ts):
        if amount > 0:
            w['_bal'] += amount
            wtx.append(dict(txn_id=uid(), wallet_id=w['wallet_id'], payment_id=P['payment_id'],
                            type='refund', amount_ngn=amount, provider_ref=None, created_at=ts))

    # early cancel (before assignment)
    if rng.random() < 0.015:
        tc = tp + timedelta(seconds=rng.randint(40, 200))
        ev('CANCELLED', tc, 'active', 'cancelled', 'vendor', v['vendor_id'], 'customer_cancelled')
        refund(fee, tc)
        D.update(state='cancelled', outcome='cancelled', outcome_reason='customer_cancelled', closed_at=tc)
        P.update(status='refunded' if fee else 'settled', amount_refunded_ngn=fee, settled_at=tc)
        continue

    # assignment
    t = tp
    excluded = set()
    queued = False
    assigned_cid = None
    while assigned_cid is None:
        avail = [c for c in cyclists if c['cyclist_id'] not in excluded and on_shift(c['cyclist_id'], t)
                 and (cyc_busy_until[c['cyclist_id']] is None or cyc_busy_until[c['cyclist_id']] <= t)]
        if not avail:
            if not queued:
                ev('QUEUED', t, 'active', 'awaiting_cyclist'); queued = True; D['state'] = 'awaiting_cyclist'
            frees = [cyc_busy_until[c['cyclist_id']] for c in cyclists
                     if on_shift(c['cyclist_id'], t) and cyc_busy_until[c['cyclist_id']] and cyc_busy_until[c['cyclist_id']] > t]
            if frees:
                t = min(frees) + timedelta(seconds=5)
            else:
                t = t + timedelta(minutes=5)
            if (t - tp) > timedelta(minutes=45):
                break
            excluded = set()
            continue
        avail.sort(key=lambda c: (cyc_last_job[c['cyclist_id']] or datetime(2000, 1, 1, tzinfo=WAT)))
        c = avail[0]
        ev('CYCLIST_PROMPTED', t, None, None, 'system', None, c['name'])
        if rng.random() < c['_unresponsive']:
            t = t + timedelta(seconds=60)
            ev('ACK_TIMEOUT', t, None, None, 'system', c['cyclist_id'])
            excluded.add(c['cyclist_id'])
            continue
        t = t + timedelta(seconds=rng.randint(4, 35))
        assigned_cid = c['cyclist_id']
        frm = 'awaiting_cyclist' if queued else 'active'
        ev('CYCLIST_ACCEPTED', t, frm, 'assigned', 'cyclist', assigned_cid)
    if assigned_cid is None:
        tc = t
        ev('CANCELLED', tc, D['state'], 'cancelled', 'admin', CHINEDU, 'no_capacity')
        refund(fee, tc)
        D.update(state='cancelled', outcome='cancelled', outcome_reason='no_capacity', closed_at=tc)
        P.update(status='refunded' if fee else 'settled', amount_refunded_ngn=fee, settled_at=tc)
        continue
    cyc = next(c for c in cyclists if c['cyclist_id'] == assigned_cid)
    D.update(cyclist_id=assigned_cid, assigned_at=t, state='assigned',
             code_hash=hashlib.sha256((did + 'code').encode()).hexdigest())
    ev('MESSAGE_SENT', t + timedelta(seconds=rng.randint(2, 8)), None, None, 'system', None,
       'sms_fallback' if rng.random() < 0.07 else 'whatsapp')
    cyc_last_job[assigned_cid] = t

    peak = t.hour >= 18
    rain = 1.25 if r['rain'] else 1.0
    # cancel after assignment
    if rng.random() < 0.015:
        tc = t + timedelta(minutes=rng.uniform(1, 5))
        keep = round(fee * ZONE['cancel_fee_pct'])
        ev('CANCELLED', tc, 'assigned', 'cancelled', 'vendor', v['vendor_id'], 'customer_cancelled')
        refund(fee - keep, tc)
        D.update(state='cancelled', outcome='cancelled', outcome_reason='customer_cancelled', closed_at=tc)
        P.update(status='part_refunded' if fee else 'settled', amount_refunded_ngn=fee - keep,
                 cancel_fee_ngn=keep, amount_settled_ngn=0, settled_at=tc)
        cyc_busy_until[assigned_cid] = tc + timedelta(minutes=4)
        continue
    # travel to vendor
    ta = t + timedelta(minutes=lognorm(4.0 * cyc['_speed'] * rain, 0.35))
    ev('ARRIVED_AT_VENDOR', ta, None, None, 'cyclist', assigned_cid)
    # handover
    hand = lognorm(v['_hand'], 0.45)
    if rng.random() < v['_delay']:
        hand = rng.uniform(6, 22)
    tpk = ta + timedelta(minutes=hand)
    if hand > 5:
        ev('VENDOR_DELAY_FLAGGED', ta + timedelta(minutes=5), None, None, 'system')
        D['vendor_delay'] = 1
        if hand > 15:
            alerts.append(dict(alert_id=uid(), zone_id=ZONE['zone_id'], delivery_id=did, cyclist_id=None,
                type='vendor_delay', raised_at=ta + timedelta(minutes=15),
                resolved_at=tpk, resolved_by=CHINEDU, action='called_vendor'))
    if rng.random() < 0.004:
        ev('REFUSED_AT_PICKUP', ta + timedelta(minutes=2), 'assigned', 'cancelled', 'cyclist', assigned_cid, 'over_limits')
        keep = round(fee * ZONE['cancel_fee_pct'])
        refund(fee - keep, ta + timedelta(minutes=2))
        D.update(state='cancelled', outcome='cancelled', outcome_reason='refused_over_limits', arrived_at=ta,
                 closed_at=ta + timedelta(minutes=2))
        P.update(status='part_refunded' if fee else 'settled', amount_refunded_ngn=fee - keep, cancel_fee_ngn=keep,
                 settled_at=ta + timedelta(minutes=2))
        cyc_busy_until[assigned_cid] = ta + timedelta(minutes=8)
        continue
    if (tpk - t) > timedelta(minutes=10):
        alerts.append(dict(alert_id=uid(), zone_id=ZONE['zone_id'], delivery_id=did, cyclist_id=None,
            type='not_picked_up', raised_at=t + timedelta(minutes=10), resolved_at=tpk,
            resolved_by=CHINEDU, action='monitored'))
    ev('PICKED_UP', tpk, 'assigned', 'picked_up', 'cyclist', assigned_cid)
    D.update(arrived_at=ta, picked_up_at=tpk, state='picked_up')
    # ride
    ride = lognorm(10.0 * cyc['_speed'] * rain * (1.08 if peak else 1.0), 0.32)
    if rng.random() < (0.06 if r['rain'] else 0.035):
        ride += rng.uniform(12, 26)   # lost, wrong turn, rain shelter
    tdoor = tpk + timedelta(minutes=ride)
    ev('ARRIVED_AT_DROPOFF', tdoor, None, None, 'cyclist', assigned_cid)
    roll = rng.random()
    if roll < 0.028:
        tf = tdoor + timedelta(minutes=rng.uniform(11, 16))
        reason = rng.choices(['receiver_unreachable', 'receiver_refused', 'wrong_address'], [0.7, 0.15, 0.15])[0]
        ev('FAILED', tf, 'picked_up', 'failed', 'cyclist', assigned_cid, reason)
        D.update(state='failed', outcome='failed', outcome_reason=reason)
        tend = tf
    else:
        if rng.random() < 0.06:
            ev('CODE_FAILED', tdoor + timedelta(seconds=40), None, None, 'cyclist', assigned_cid)
        tend = tdoor + timedelta(minutes=rng.uniform(0.6, 3))
        if roll < 0.028 + 0.022:
            ev('DELIVERED_WITHOUT_CODE', tend, 'picked_up', 'delivered', 'cyclist', assigned_cid, 'receiver_lost_message')
            D['without_code'] = 1
        else:
            ev('DELIVERED', tend, 'picked_up', 'delivered', 'cyclist', assigned_cid)
        D.update(state='delivered', outcome='delivered', delivered_at=tend)
    if (tend - tpk) > timedelta(minutes=30):
        alerts.append(dict(alert_id=uid(), zone_id=ZONE['zone_id'], delivery_id=did, cyclist_id=assigned_cid,
            type='late_delivery', raised_at=tpk + timedelta(minutes=30), resolved_at=tend,
            resolved_by=CHINEDU, action='called_cyclist'))
    tclose = tend + timedelta(hours=24) if D['outcome'] == 'delivered' and not D['without_code'] else tend.replace(hour=23, minute=40)
    if tclose < tend:
        tclose = tend + timedelta(minutes=10)
    ev('CLOSED', tclose, D['state'], 'closed', 'system' if tclose - tend >= timedelta(hours=24) else 'admin',
       None if tclose - tend >= timedelta(hours=24) else CHINEDU)
    D.update(closed_at=tclose, state='closed')
    P.update(status='settled', amount_settled_ngn=fee, settled_at=tend)
    cyc_busy_until[assigned_cid] = tend + timedelta(minutes=lognorm(3.5, 0.3))
    if queued:
        qev = [e for e in events if e['delivery_id'] == did and e['event_type'] == 'QUEUED'][0]
        if (D['assigned_at'] - qev['server_ts']) > timedelta(minutes=3):
            alerts.append(dict(alert_id=uid(), zone_id=ZONE['zone_id'], delivery_id=did, cyclist_id=None,
                type='queued', raised_at=qev['server_ts'] + timedelta(minutes=3), resolved_at=D['assigned_at'],
                resolved_by=None, action='auto_assigned'))

# ack-timeout alerts
for e in events:
    if e['event_type'] == 'ACK_TIMEOUT':
        alerts.append(dict(alert_id=uid(), zone_id=ZONE['zone_id'], delivery_id=e['delivery_id'], cyclist_id=e['actor_id'],
            type='ack_timeout', raised_at=e['server_ts'], resolved_at=e['server_ts'] + timedelta(seconds=30),
            resolved_by=None, action='auto_reassigned'))
for e in events:
    if e['event_type'] == 'ACK_TIMEOUT':
        e['actor_id'] = None  # system event; the cyclist is recorded on the alert

# ---------------- statements ----------------
statements = []
del_by_vendor = {}
for D in deliveries:
    del_by_vendor.setdefault(D['vendor_id'], []).append(D)
pay_by_del = {p['delivery_id']: p for p in payments}
for v in vendors:
    w = wallets[v['vendor_id']]
    txs = sorted([x for x in wtx if x['wallet_id'] == w['wallet_id']], key=lambda x: x['created_at'])
    for wk in range(DAYS // 7):
        ws = START + timedelta(days=7 * wk); we = ws + timedelta(days=6)
        if we < date.fromisoformat(v['trial_start']):
            continue
        ds = [D for D in del_by_vendor.get(v['vendor_id'], []) if ws <= D['created_at'].astimezone(WAT).date() <= we]
        opening = sum(x['amount_ngn'] for x in txs if x['created_at'].astimezone(WAT).date() < ws)
        closing = sum(x['amount_ngn'] for x in txs if x['created_at'].astimezone(WAT).date() <= we)
        statements.append(dict(statement_id=uid(), vendor_id=v['vendor_id'], week_start=ws.isoformat(), week_end=we.isoformat(),
            delivered=sum(1 for D in ds if D['outcome'] == 'delivered'),
            failed=sum(1 for D in ds if D['outcome'] == 'failed'),
            cancelled=sum(1 for D in ds if D['outcome'] == 'cancelled'),
            fees_ngn=sum(pay_by_del[D['delivery_id']]['amount_settled_ngn'] for D in ds),
            cancel_fees_ngn=sum(pay_by_del[D['delivery_id']]['cancel_fee_ngn'] for D in ds),
            topups_ngn=sum(x['amount_ngn'] for x in txs if x['type'] == 'topup' and ws <= x['created_at'].astimezone(WAT).date() <= we),
            opening_ngn=opening, closing_ngn=closing,
            vendor_delays=sum(D['vendor_delay'] for D in ds),
            generated_at=wat(we + timedelta(days=1), 6)))

# ---------------- write ----------------
SCHEMA = {
 'zone': ['zone_id','name','hub_lat','hub_lng','open_from','open_to','fixed_rate_ngn','cancel_fee_pct','ack_timeout_s','queue_alert_s','handover_grace_s','pickup_alert_s','delivery_alert_s','payment_expiry_s','max_weight_kg','max_value_ngn'],
 'admin_user': ['admin_id','zone_id','name','role'],
 'vendor': ['vendor_id','zone_id','name','category','contact_name','phone','pickup_address','pickup_lat','pickup_lng','trial_start','status','onboarded_by'],
 'wallet': ['wallet_id','vendor_id','account_number'],
 'wallet_transaction': ['txn_id','wallet_id','payment_id','type','amount_ngn','provider_ref','created_at'],
 'cyclist': ['cyclist_id','zone_id','name','phone','state','retainer_ngn','bonus_threshold','bonus_per_delivery_ngn','trained_at','status'],
 'shift': ['shift_id','cyclist_id','zone_id','planned_start','planned_end','actual_start','actual_end'],
 'delivery': ['delivery_id','ref','zone_id','vendor_id','cyclist_id','raised_by','package_category','limits_confirmed','dropoff_address','dropoff_lat','dropoff_lng','receiver_phone_enc','note','fee_ngn','state','code_hash','tracking_token','created_at','paid_at','activated_at','assigned_at','arrived_at','picked_up_at','delivered_at','closed_at','vendor_delay','without_code','outcome','outcome_reason'],
 'delivery_event': ['event_id','delivery_id','seq','event_type','from_state','to_state','actor_type','actor_id','server_ts','device_ts','reason'],
 'payment': ['payment_id','delivery_id','method','amount_held_ngn','amount_settled_ngn','amount_refunded_ngn','cancel_fee_ngn','status','held_at','settled_at'],
 'alert': ['alert_id','zone_id','delivery_id','cyclist_id','type','raised_at','resolved_at','resolved_by','action'],
 'statement': ['statement_id','vendor_id','week_start','week_end','delivered','failed','cancelled','fees_ngn','cancel_fees_ngn','topups_ngn','opening_ngn','closing_ngn','vendor_delays','generated_at'],
}
TABLES = {'zone': [ZONE], 'admin_user': ADMINS, 'vendor': vendors, 'wallet': list(wallets.values()),
          'wallet_transaction': wtx, 'cyclist': cyclists, 'shift': shifts, 'delivery': deliveries,
          'delivery_event': events, 'payment': payments, 'alert': alerts, 'statement': statements}

def norm(x):
    return iso(x) if isinstance(x, datetime) else x

db_path = os.path.join(OUT, 'airand_SIMULATED.sqlite')
if os.path.exists(db_path):
    os.remove(db_path)
con = sqlite3.connect(db_path)
csv_dir = os.path.join(OUT, 'csv_SIMULATED'); os.makedirs(csv_dir, exist_ok=True)
for t, cols in SCHEMA.items():
    con.execute(f"CREATE TABLE {t} ({', '.join(cols)})")
    rows = [[norm(r.get(c)) for c in cols] for r in TABLES[t]]
    con.executemany(f"INSERT INTO {t} VALUES ({','.join('?'*len(cols))})", rows)
    with open(os.path.join(csv_dir, f"{t}_SIMULATED.csv"), 'w', newline='', encoding='utf-8') as f:
        wr = csv.writer(f); wr.writerow(cols); wr.writerows(rows)
con.execute("CREATE TABLE _about (note)")
con.execute("INSERT INTO _about VALUES ('[SIMULATED] Airand portfolio dataset, 90 days from 2026-07-06, seed 20261006. Not real data.')")
con.commit()
print({t: len(TABLES[t]) for t in SCHEMA})
