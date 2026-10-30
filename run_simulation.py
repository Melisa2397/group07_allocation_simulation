from pathlib import Path
import math
import random
import csv
import statistics
import json

config_ = Path("simulation_config.json")
output_ = Path("results/simulation_output.csv")
summary_ = Path("results/simulation_summary.csv")

default_near_due_threshold = 2

rules = ("fixed", "realloc")
per_rules_kpıs = ["kits_on_time_pct", "avg_kit_delay_days", "near_due_misses"]

def round_half_up(x: float):
    return int(math.floor(x + 0.5))

def sample(rng: random.random, spec: dict):
    dist = spec["distribution"]

    if dist == "normal":
        value = rng.normalvariate(spec["mean"], spec["std_dev"])
    elif dist == "lognormal":
        value = rng.lognormvariate(spec["mu"], spec["sigma"])
    elif dist == "triangular":
        return rng.triangular(spec["min"], spec["max"], spec["mode"])
    elif dist == "uniform":
        return rng.uniform(spec["min"], spec["max"])
    elif dist == "bernoulli":
        return 1 if rng.random() < spec["probability"] else 0
    else:
        print ('error: Specify at least two scenarios')

    if "min" in spec:
        value = max(value, spec["min"])
    return value

def sample_week(rng: random.random, specs: dict):
    n_orders = round_half_up(sample(rng, specs["competing_orders"]))

    orders = []
    for i in range(n_orders):
        qty = max(1, round_half_up(sample(rng, specs["required_quantity"])))
        initial_slack = sample(rng, specs["initial_slack"])
        orders.append({"id": i, "qty": qty, "initial_slack": initial_slack})

    coverage = sample(rng, specs["stock_coverage"])
    wait = sample(rng, specs["replenishment_wait"])
    total_demand = sum(o["qty"] for o in orders)
    stock = math.floor(total_demand * coverage)


    for o in orders:
        o["priority_changed"] = sample(rng, specs["priority_change_probability"]) == 1
        urgent_slack = sample(rng, specs["urgent_slack"])
        o["updated_slack"] = urgent_slack if o["priority_changed"] else o["initial_slack"]

    return {
        "orders": orders,
        "stock": stock,
        "stock_coverage": coverage,
        "replenishment_wait": wait,
        "total_demand": total_demand,
    }

def allocate(orders: list, stock: int, slack_key: str):
    alloc = [0] * len(orders)
    remaining = stock
    for o in sorted(orders, key=lambda o: (o[slack_key], o["id"])):
        give = min(o["qty"], remaining)
        alloc[o["id"]] = give
        remaining -= give
    return alloc

def fixed_reservations(orders: list, stock: int):
    return allocate(orders, stock, "initial_slack")

def reallocation(orders: list, stock: int):
    return allocate(orders, stock, "updated_slack")

def evaluate(orders: list, alloc: list, wait: float, threshold: float):
    n = len(orders)
    ontime = 0
    delaysum = 0
    nearduemisses = 0

    for o in orders:
        complete = o["qty"] == alloc[o["id"]]
        kit_day = 0 if complete else wait
        if complete:
            ontime += 1
        delaysum += kit_day
        if kit_day > max(0, o["updated_slack"] - threshold):
            nearduemisses += 1

    return {
        "kits_on_time_pct": 100 * ontime / n,
        "avg_kit_delay_days": delaysum / n,
        "near_due_misses": nearduemisses,
    }

def run_experiment(rng: random.random, seed: int, scenario: dict, n_reps: int, threshold: float):
    for rep in range(1, n_reps + 1):
        w = sample_week(rng, scenario["inputs"])
        orders = w["orders"]

        alloc_fixed = fixed_reservations(orders, w["stock"])
        alloc_real = reallocation(orders, w["stock"])
        k = {
            "fixed": evaluate(orders, alloc_fixed, w["replenishment_wait"], threshold),
            "realloc": evaluate(orders, alloc_real, w["replenishment_wait"], threshold),
        }

        n = len(orders)
        row = {
            "scenario": scenario["name"],
            "simulation_count": n_reps,
            "replication": rep,
            "seed": seed,
            "competing_orders": n,
            "total_demand": w["total_demand"],
            "mean_required_quantity": w["total_demand"] / n,
            "mean_initial_slack": sum(o["initial_slack"] for o in orders) / n,
            "stock_coverage": w["stock_coverage"],
            "available_stock": w["stock"],
            "replenishment_wait": w["replenishment_wait"],
            "orders_priority_changed": sum(o["priority_changed"] for o in orders),
        }
        for rule in rules:
            for name in per_rules_kpıs:
                row[f"{rule}_{name}"] = k[rule][name]
   
        row["orders_reallocated"] = sum(1 for a, b in zip(alloc_fixed, alloc_real) if a != b)
        row["delay_reduction_days"] = k["fixed"]["avg_kit_delay_days"] - k["realloc"]["avg_kit_delay_days"]
        row["near_due_miss_reduction"] = k["fixed"]["near_due_misses"] - k["realloc"]["near_due_misses"]
        yield row

summary_columns = (
    [f"{r}_{k}" for k in per_rules_kpıs for r in rules]
    + ["orders_reallocated", "delay_reduction_days", "near_due_miss_reduction"]
)

def summarize(rows: list):
    n = len(rows)
    out = []
    for col in summary_columns:
        vals = [r[col] for r in rows]
        mean = statistics.fmean(vals)
        std = statistics.stdev(vals) if n > 1 else 0
        half = 1.96 * std / math.sqrt(n)
        out.append({
            "scenario": rows[0]["scenario"],
            "simulation_count": rows[0]["simulation_count"],
            "kpi": col,
            "mean": mean, "std": std, "min": min(vals), "max": max(vals),
            "ci95_low": mean - half, "ci95_high": mean + half,
        })
    return out

def main():
    with config_.open(encoding="utf-8") as f:
        config = json.load(f)

    seed = config["seed"]
    threshold = config.get("near_due_threshold_days", default_near_due_threshold)
    rng = random.Random(seed)
    output_.parent.mkdir(parents=True, exist_ok=True)

    writer = None
    summary = []
    total_rows = 0
    with output_.open("w", newline="", encoding="utf-8") as f:
        for scenario in config["scenarios"]:
            for n_reps in config["simulation_counts"]:
                rows = []
                for row in run_experiment(rng, seed, scenario, n_reps, threshold):
                    if writer is None:
                        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
                        writer.writeheader()
                    writer.writerow(row)
                    rows.append(row)
                total_rows += len(rows)
                stats = summarize(rows)
                summary.extend(stats)

                d = next(s for s in stats 
                         if s["kpi"] == "near_due_miss_reduction")
                verdict = "supports re-allocation" if d["ci95_low"] > 0 else "CI includes/below 0"
                print(f"{scenario['name']:<25} n={n_reps:<6} {len(rows)} rows | "
                      f"near-due miss reduction {d['mean']:.3f} "
                      f"[{d['ci95_low']:.3f}, {d['ci95_high']:.3f}] ({verdict})")

    with summary_.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        w.writeheader()
        w.writerows(summary)

    print(f"\nDone:{total_rows} rows written to {output_}")
    print(f"Summary written to {summary_}")
    
if __name__ == "__main__":
    main()