"""
Synthetic source data for NorthGrid Telecom (fictional).

Plays the role of the client's operational systems: it writes the CSV exports
(customers, circuits, incidents, improvement actions) that database/load_source_data.ps1
loads into the ops schema. Everything is simulated; the same seed always produces
the same data.

The data follows a few deliberate patterns so the KPIs have something to find:
- failure rates differ by technology and from circuit to circuit (some circuits are chronic);
- a failure makes another failure more likely in the following weeks (repeat incidents);
- fixed wireless and the Northwest region suffer more in winter;
- the South region restores more slowly, and improves during 2025;
- improvement actions lower the failure rate of the circuit after completion,
  by an amount that depends on the action type.

It also includes the imperfections real exports have, so the data quality checks
have something to catch: unmarked duplicate tickets, tickets restored before they
were opened, tickets on unknown circuits and circuits without a region.

Usage: python generator/generate_source_data.py [--seed 42] [--out data/generated]
Standard library only.
"""
import argparse
import csv
import math
import random
from collections import defaultdict, deque
from datetime import date, datetime, timedelta
from pathlib import Path

START = date(2024, 1, 1)
END = date(2025, 12, 31)
SNAPSHOT = datetime(2026, 1, 1)  # data extracted at midnight after the last day

N_CUSTOMERS = 4000

REGIONS = {
    # code: (name, share of customers, restoration speed factor, provinces)
    "CEN": ("Center", 0.25, 0.90, ["Madrid", "Toledo", "Valladolid", "Salamanca", "Badajoz"]),
    "NEA": ("Northeast", 0.22, 0.95, ["Barcelona", "Tarragona", "Girona", "Lleida", "Zaragoza", "Illes Balears"]),
    "SUR": ("South", 0.17, 1.00, ["Sevilla", "Málaga", "Cádiz", "Granada", "Las Palmas", "Santa Cruz de Tenerife"]),
    "EST": ("East", 0.14, 1.05, ["Valencia", "Alicante", "Castellón", "Murcia"]),
    "NOR": ("North", 0.12, 1.00, ["Bizkaia", "Gipuzkoa", "Álava", "Cantabria", "Navarra", "La Rioja"]),
    "NWE": ("Northwest", 0.10, 1.15, ["A Coruña", "Pontevedra", "Lugo", "Asturias"]),
}

SEGMENTS = {
    # segment: (share, average extra circuits, tier weights Gold/Silver/Bronze)
    "SME": (0.60, 0.15, (0.10, 0.40, 0.50)),
    "Corporate": (0.30, 1.40, (0.40, 0.45, 0.15)),
    "Public sector": (0.10, 1.00, (0.25, 0.50, 0.25)),
}
TIERS = ("GOLD", "SILVER", "BRONZE")
TIER_RESTORE_FACTOR = {"GOLD": 0.80, "SILVER": 1.00, "BRONZE": 1.20}

TECHNOLOGIES = {
    # code: (share, incidents per circuit per month)
    "FIB": (0.65, 0.08),
    "FWA": (0.20, 0.15),
    "COP": (0.15, 0.22),
}

PRIORITIES = (("P1", 0.10, 3.0), ("P2", 0.25, 5.0), ("P3", 0.45, 18.0), ("P4", 0.20, 45.0))  # code, share, median hours

ROOT_CAUSES = {
    # technology: weights for LM, BB, CPE, PWR, TPY, UNK
    "FIB": (0.35, 0.20, 0.15, 0.10, 0.12, 0.08),
    "FWA": (0.45, 0.10, 0.12, 0.15, 0.08, 0.10),
    "COP": (0.55, 0.08, 0.12, 0.08, 0.07, 0.10),
}
ROOT_CAUSE_CODES = ("LM", "BB", "CPE", "PWR", "TPY", "UNK")
ROOT_CAUSE_RESTORE_FACTOR = {"LM": 1.0, "BB": 0.8, "CPE": 1.3, "PWR": 1.1, "TPY": 1.6, "UNK": 1.2}

ACTIONS = {
    # action type: (rate reduction after completion, min days, max days)
    "SITE_SURVEY": (0.10, 3, 10),
    "EQUIP_REPLACE": (0.40, 7, 30),
    "REROUTE": (0.30, 15, 45),
    "TECH_MIGRATION": (0.65, 30, 90),
}
ACTION_MIX = {
    "FIB": {"SITE_SURVEY": 0.35, "EQUIP_REPLACE": 0.30, "REROUTE": 0.30, "TECH_MIGRATION": 0.05},
    "FWA": {"SITE_SURVEY": 0.30, "EQUIP_REPLACE": 0.40, "REROUTE": 0.20, "TECH_MIGRATION": 0.10},
    "COP": {"SITE_SURVEY": 0.15, "EQUIP_REPLACE": 0.25, "REROUTE": 0.10, "TECH_MIGRATION": 0.50},
}
ACTIONS_PER_MONTH = 25

FRAILTY_SHAPE = 2.0       # gamma shape for circuit-to-circuit variation (mean 1); lower = more extreme circuits
REPEAT_BOOST = 0.8        # extra hazard multiplier right after a failure
REPEAT_DECAY_DAYS = 10.0  # how fast that extra hazard fades

# Source-data imperfections (shares of tickets or circuits)
CANCELLED_SHARE = 0.03
MARKED_DUPLICATE_SHARE = 0.02
UNMARKED_DUPLICATE_SHARE = 0.004
RESTORED_BEFORE_OPENED_SHARE = 0.002
UNKNOWN_CIRCUIT_SHARE = 0.0015
MISSING_REGION_SHARE = 0.01
STUCK_TICKET_SHARE = 0.03  # tickets that wait weeks (parts, permits, access)
ACTION_MIN_INCIDENTS_90D = 3  # committee only looks at circuits with at least this many incidents in 90 days


def weighted(rng, options, weights):
    return rng.choices(options, weights=weights, k=1)[0]


def fmt(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def write_csv(path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            writer.writerow([fmt(v) for v in row])


def make_customers(rng):
    customers = []
    region_codes = list(REGIONS)
    region_weights = [REGIONS[r][1] for r in region_codes]
    segments = list(SEGMENTS)
    for customer_id in range(1, N_CUSTOMERS + 1):
        segment = weighted(rng, segments, [SEGMENTS[s][0] for s in segments])
        tier = weighted(rng, TIERS, SEGMENTS[segment][2])
        customers.append({
            "CustomerId": customer_id,
            "CustomerName": f"Client {customer_id:04d}",
            "Segment": segment,
            "TierCode": tier,
            "AccountManager": f"AM-{rng.randint(1, 25):02d}",
            "CreatedDate": date(2015, 1, 1) + timedelta(days=rng.randint(0, 3286)),
            "home_region": weighted(rng, region_codes, region_weights),
        })
    return customers


def make_circuits(rng, customers):
    circuits = []
    techs = list(TECHNOLOGIES)
    region_codes = list(REGIONS)
    counter = 0
    for customer in customers:
        extra = SEGMENTS[customer["Segment"]][1]
        n_circuits = 1 + sum(rng.random() < extra / 4 for _ in range(4))  # 1 to 5, mean 1 + extra
        for _ in range(n_circuits):
            counter += 1
            tech = weighted(rng, techs, [TECHNOLOGIES[t][0] for t in techs])
            region = customer["home_region"] if rng.random() < 0.8 else rng.choice(region_codes)
            oldest = date(2008, 1, 1) if tech == "COP" else date(2014, 1, 1)
            install = oldest + timedelta(days=rng.randint(0, (date(2025, 11, 30) - oldest).days))
            decommission = None
            if tech == "COP" and rng.random() < 0.10:
                decommission = max(install + timedelta(days=30), date(2024, 3, 1) + timedelta(days=rng.randint(0, 640)))
                decommission = min(decommission, END)
            circuits.append({
                "CircuitId": f"NG-{tech}-{counter:06d}",
                "CustomerId": customer["CustomerId"],
                "TechnologyCode": tech,
                "RegionCode": region,
                "Province": rng.choice(REGIONS[region][3]),
                "InstallDate": install,
                "DecommissionDate": decommission,
                "tier": customer["TierCode"],
                # circuit-to-circuit variation: most circuits are stable, a few fail a lot
                "frailty": rng.gammavariate(FRAILTY_SHAPE, 1 / FRAILTY_SHAPE),
                "rate_reduction": 0.0,
            })
    return circuits


def daily_hazard(circuit, day, boost):
    monthly = TECHNOLOGIES[circuit["TechnologyCode"]][1] * circuit["frailty"]
    winter = day.month in (11, 12, 1, 2)
    if winter and (circuit["TechnologyCode"] == "FWA" or circuit["RegionCode"] == "NWE"):
        monthly *= 1.5
    if day.month in (7, 8):  # heat waves stress power and equipment
        monthly *= 1.2
    monthly *= 1 - circuit["rate_reduction"]
    return monthly / 30.4 * (1 + boost)


def restore_hours(rng, circuit, priority_median, root_cause, opened):
    region = circuit["RegionCode"]
    region_factor = REGIONS[region][2]
    if region == "SUR":  # slow in 2024, improves across 2025
        region_factor = 1.40 if opened.year == 2024 else 1.40 - 0.03 * opened.month
    median = priority_median * region_factor * TIER_RESTORE_FACTOR[circuit["tier"]] * ROOT_CAUSE_RESTORE_FACTOR[root_cause]
    hours = rng.lognormvariate(math.log(median), 0.7)
    if rng.random() < STUCK_TICKET_SHARE:
        hours *= rng.uniform(5, 20)
    return hours


def responsible_team(circuit, root_cause):
    if root_cause == "BB":
        return "Backbone Engineering"
    if root_cause == "CPE":
        return "Customer Support"
    if root_cause == "TPY":
        return "Partner Network"
    return f"Field Ops {REGIONS[circuit['RegionCode']][0]}"


def simulate(rng, circuits):
    incidents = []
    actions = []
    boost = defaultdict(float)
    recent = defaultdict(deque)  # circuit -> dates of incidents in the last 90 days
    last_action_start = {}
    pending_effects = []  # (completion date, circuit, reduction)
    priorities = [p[0] for p in PRIORITIES]
    priority_weights = [p[1] for p in PRIORITIES]
    priority_median = {p[0]: p[2] for p in PRIORITIES}

    day = START
    while day <= END:
        for completion, circuit, reduction in [e for e in pending_effects if e[0] == day]:
            circuit["rate_reduction"] = 1 - (1 - circuit["rate_reduction"]) * (1 - reduction)

        for circuit in circuits:
            cid = circuit["CircuitId"]
            if circuit["InstallDate"] > day or (circuit["DecommissionDate"] and circuit["DecommissionDate"] <= day):
                continue
            boost[cid] *= math.exp(-1 / REPEAT_DECAY_DAYS)
            if rng.random() >= daily_hazard(circuit, day, boost[cid]):
                continue

            opened = datetime.combine(day, datetime.min.time()) + timedelta(seconds=rng.randint(0, 86399))
            priority = weighted(rng, priorities, priority_weights)
            root_cause = weighted(rng, ROOT_CAUSE_CODES, ROOT_CAUSES[circuit["TechnologyCode"]])
            restored = opened + timedelta(hours=restore_hours(rng, circuit, priority_median[priority], root_cause, opened))
            incidents.append({"circuit": circuit, "priority": priority, "opened": opened,
                              "restored": restored, "root_cause": root_cause})
            boost[cid] += REPEAT_BOOST
            recent[cid].append(day)

        # once a month the improvement committee picks the worst circuits of the last 90 days
        if (day + timedelta(days=1)).day == 1 and day < date(2025, 12, 1):
            for dates in recent.values():
                while dates and (day - dates[0]).days >= 90:
                    dates.popleft()
            candidates = [c for c in circuits
                          if len(recent[c["CircuitId"]]) >= ACTION_MIN_INCIDENTS_90D
                          and (c["CircuitId"] not in last_action_start
                               or (day - last_action_start[c["CircuitId"]]).days > 180)]
            candidates.sort(key=lambda c: len(recent[c["CircuitId"]]) + rng.random(), reverse=True)
            for circuit in candidates[:ACTIONS_PER_MONTH]:
                mix = ACTION_MIX[circuit["TechnologyCode"]]
                action_type = weighted(rng, list(mix), list(mix.values()))
                reduction, min_days, max_days = ACTIONS[action_type]
                start = day + timedelta(days=rng.randint(1, 20))
                completion = start + timedelta(days=rng.randint(min_days, max_days))
                cancelled = rng.random() < 0.05
                actions.append({"circuit": circuit, "type": action_type, "start": start,
                                "completion": completion, "cancelled": cancelled})
                last_action_start[circuit["CircuitId"]] = start
                if not cancelled and completion <= END:
                    pending_effects.append((completion, circuit, reduction))
        day += timedelta(days=1)
    return incidents, actions


def build_ticket_rows(rng, incidents):
    tickets = []
    for inc in incidents:
        circuit = inc["circuit"]
        restored = inc["restored"] if inc["restored"] < SNAPSHOT else None
        cancelled = rng.random() < CANCELLED_SHARE
        if cancelled:  # opened by mistake and cancelled shortly after
            restored = inc["opened"] + timedelta(minutes=rng.randint(10, 240))
        root_cause = None if (restored is None or cancelled) else inc["root_cause"]
        closed = None
        if restored is not None:
            closed = restored + timedelta(hours=rng.uniform(0.5, 72))
            if closed >= SNAPSHOT:
                closed = None
        if rng.random() < RESTORED_BEFORE_OPENED_SHARE and restored is not None and not cancelled:
            restored = inc["opened"] - timedelta(minutes=rng.randint(1, 120))
        circuit_id = circuit["CircuitId"]
        if rng.random() < UNKNOWN_CIRCUIT_SHARE:
            circuit_id = f"NG-{circuit['TechnologyCode']}-9{rng.randint(0, 99999):05d}"
        ticket = {
            "CircuitId": circuit_id,
            "PriorityCode": inc["priority"],
            "OpenedAt": inc["opened"],
            "RestoredAt": restored,
            "ClosedAt": closed,
            "Status": "Open" if restored is None else ("Closed" if closed else "Restored"),
            "RootCauseCode": root_cause,
            "ResponsibleTeam": responsible_team(circuit, inc["root_cause"]) if root_cause else f"Field Ops {REGIONS[circuit['RegionCode']][0]}",
            "IsCancelled": cancelled,
            "duplicate_of": None,
        }
        tickets.append(ticket)

        if rng.random() < MARKED_DUPLICATE_SHARE:  # second call about the same failure, marked by the agent
            opened = ticket["OpenedAt"] + timedelta(minutes=rng.randint(2, 60))
            tickets.append({**ticket, "OpenedAt": opened, "RestoredAt": opened + timedelta(minutes=5),
                            "ClosedAt": opened + timedelta(minutes=5), "Status": "Closed",
                            "RootCauseCode": None, "IsCancelled": False, "duplicate_of": ticket})
        elif rng.random() < UNMARKED_DUPLICATE_SHARE:  # same failure registered twice, nobody noticed
            tickets.append({**ticket, "OpenedAt": ticket["OpenedAt"] + timedelta(minutes=rng.randint(1, 10))})

    tickets.sort(key=lambda t: t["OpenedAt"])
    for number, ticket in enumerate(tickets, start=1):
        ticket["TicketId"] = f"INC{number:08d}"
    return tickets


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "data" / "generated"))
    args = parser.parse_args()
    rng = random.Random(args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    customers = make_customers(rng)
    circuits = make_circuits(rng, customers)
    incidents, actions = simulate(rng, circuits)
    tickets = build_ticket_rows(rng, incidents)

    write_csv(out / "customers.csv",
              ["CustomerId", "CustomerName", "Segment", "TierCode", "AccountManager", "CreatedDate"],
              ([c["CustomerId"], c["CustomerName"], c["Segment"], c["TierCode"], c["AccountManager"], c["CreatedDate"]]
               for c in customers))

    # source imperfection: a few circuits exported without region (province still filled)
    write_csv(out / "circuits.csv",
              ["CircuitId", "CustomerId", "TechnologyCode", "RegionCode", "Province", "InstallDate", "DecommissionDate"],
              ([c["CircuitId"], c["CustomerId"], c["TechnologyCode"],
                None if rng.random() < MISSING_REGION_SHARE else c["RegionCode"],
                c["Province"], c["InstallDate"], c["DecommissionDate"]] for c in circuits))

    write_csv(out / "incidents.csv",
              ["TicketId", "CircuitId", "PriorityCode", "OpenedAt", "RestoredAt", "ClosedAt", "Status",
               "RootCauseCode", "ResponsibleTeam", "IsCancelled", "DuplicateOfTicketId"],
              ([t["TicketId"], t["CircuitId"], t["PriorityCode"], t["OpenedAt"], t["RestoredAt"], t["ClosedAt"],
                t["Status"], t["RootCauseCode"], t["ResponsibleTeam"], t["IsCancelled"],
                t["duplicate_of"]["TicketId"] if t["duplicate_of"] else None] for t in tickets))

    action_rows = []
    for action_id, a in enumerate(sorted(actions, key=lambda a: a["start"]), start=1):
        if a["cancelled"]:
            status, completion = "Cancelled", None
        elif a["start"] > END:
            status, completion = "Planned", None
        elif a["completion"] > END:
            status, completion = "In progress", None
        else:
            status, completion = "Completed", a["completion"]
        action_rows.append([action_id, a["circuit"]["CircuitId"], a["type"], a["start"], completion, status])
    write_csv(out / "improvement_actions.csv",
              ["ActionId", "CircuitId", "ActionTypeCode", "StartDate", "CompletionDate", "Status"], action_rows)

    print(f"seed {args.seed} -> {out}")
    print(f"customers {len(customers)}, circuits {len(circuits)}, tickets {len(tickets)}, actions {len(action_rows)}")


if __name__ == "__main__":
    main()
