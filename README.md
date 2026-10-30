# Group 07 Monte Carlo simulation

## Run

Requires Python 3.10 or newer; no third-party packages are needed. From this folder, run:

```text
python run_simulation.py
```

The script uses only the Python standard library. It reads `inputs/simulation_config.json` and replaces `results/simulation_output.csv` with the results from that run. The configuration's seed initializes one random-number generator for the invocation; experiments run in scenario order and then replication-count order.

## Sampling and comparison rules

- `competing_orders` is sampled from a normal distribution, rounded to an integer, and resampled until the rounded value is at least `min`.
- `required_quantity` is sampled from a lognormal distribution using `mu` and `sigma`, rounded to an integer, and resampled until the rounded value is at least `min`.
- `initial_slack` is sampled from a normal distribution and resampled until it is at least `min`. Slack remains continuous in days.
- `stock_coverage` is triangular; available stock is `floor(total demand * stock coverage)`.
- Each order independently draws a Bernoulli priority-change event. Changed orders receive a new slack sampled uniformly from `urgent_slack`; unchanged orders retain initial slack.
- `replenishment_wait` is sampled once per trial and used for every incomplete kit under both allocation rules, so the comparison uses the same sampled week and replenishment delay.
- Fixed reservations allocate stock in ascending initial slack. Reallocation allocates the same stock in ascending updated slack. Ties are broken by original order index. Each order receives as much as remains, including partial quantities.
- A kit is complete at day 0 only if it receives its full requirement; otherwise it completes after `replenishment_wait` days. Near-due misses use updated slack and the design threshold: a miss occurs when completion day is greater than `max(0, updated slack - 2)`.

The JSON's `min` key is a lower bound. For normal and lognormal inputs, the script uses rejection sampling (draw again below the bound), not clipping. Integer inputs are rounded with Python's `round` before the lower-bound check. These choices preserve the stated distributions subject to the lower bound. The two allocation policies and KPI formulas are model logic, so they live in this script rather than being repeated in the JSON.

## Assumptions and sources

Input provenance and caveats to carry into the report:

- `competing_orders`: approximate fit to `p2_simulation_input_extract.xlsx`, `component_weeks` (mean 11.97, standard deviation 6.05, 2,416 component-weeks). The lower bound of two focuses on allocation conflicts although 1.8% of observed weeks had one order; observed maximum was 41.
- `required_quantity`: approximate fit to `requirements_high_gap` in the same workbook (median 50, mean 113.3, 28,931 requirement lines). The lognormal parameters use `mu = ln(median)` and `sigma = sqrt(2 * ln(mean / median))`; observed standard deviation was 168 and the distribution has a heavy right tail.
- `stock_coverage`: stress-test assumption, triangular from 0.85 to 1.0 with mode 0.95. No stock-at-decision-time history was available; the P2 evidence was one inventory snapshot dated 31 Dec 2025. This tighter-than-observed assumption may overstate reallocation's benefit.
- `initial_slack`: assumption informed by `readiness_slack` in the same workbook (median 17.4 days, 3,894 orders). Readiness timing is only a proxy for planned release-to-due slack; standard deviation 10 simplifies the observed 18.5, and the four-day lower bound excludes orders already inside the urgent window.
- `priority_change_probability`: scenario assumptions of 10% and 30%; P2 data contained no priority-change history.
- `urgent_slack`: assumption, uniform from 0 to 3 days; no source data.
- `replenishment_wait`: lognormal supplier-lateness proxy carried over from the design (median 11 days; design cites 23% late receipts). This was not reproducible from the P2 analysis workbook/report because purchase-order and shipment-notice data were absent.

The configuration stays compact and follows the assignment's illustrated schema; the source detail is kept here instead of adding non-example fields to the JSON.

## Output

The script writes one CSV row per trial, identified by scenario, `simulation_count`, replication, and seed. It includes sampled trial-level aggregate inputs plus on-time kit percentages, average kit delays, near-due misses, number of orders whose allocation changed, and delay reduction for the fixed and reallocation policies. The configured experiments produce 12,000 rows in total.
