<p align="center">
  <img src="assets/datavynx-logo.png" alt="Datavynx Analytics" width="480">
</p>

<h1 align="center">Fund Management Service Charge Calculator</h1>

<p align="center">
  <img src="https://img.shields.io/badge/tests-38%20passing-CBA135?style=flat-square" alt="tests">
  <img src="https://img.shields.io/badge/python-3.14-0A1424?style=flat-square" alt="python">
  <img src="https://img.shields.io/badge/streamlit-1.61-0A1424?style=flat-square" alt="streamlit">
  <img src="https://img.shields.io/badge/internal%20use-only-C0392B?style=flat-square" alt="internal use only">
</p>

An internal Streamlit tool for modelling fund management fees under a
hurdle-rate-plus-profit-share arrangement.

- **Phase 1** — single-year calculation with a full formula audit trail.
- **Phase 2** — five-year compounding projection with per-year rate overrides,
  payouts, and a Client Lifetime Value figure.
- **Client view** — a toggle that presents the same numbers from the client's
  side, withholding fund house earnings, house yield and CLTV.

> **Internal tool.** The default (Internal) view shows what the fund house
> earns. Switch to **Client** view before sharing a screen or exporting
> anything a client will see.

---

## Quick start

```bash
pip install -r requirements.txt
streamlit run app.py
```

```bash
python -m pytest -q
```

Tested against Python 3.14, Streamlit 1.61.1, pandas 3.0.5.

`.claude/launch.json` pins the dev server to port 8502.

---

## Project layout

| File | Contents |
|---|---|
| `engine.py` | All calculation logic. **No Streamlit import** — importable and testable on its own. |
| `app.py` | Everything UI: views, renderers, the projection grid, the input formatter. |
| `test_engine.py` | 38 tests covering the maths and its edge cases. |
| `assets/` | Datavynx brand marks used by the app and this README. |
| `.streamlit/config.toml` | Brand theme (navy text, gold accent). |
| `requirements.txt` | `streamlit`, `pandas`, `pytest`. |

The split exists so the maths can be exercised directly:

```python
from engine import calculate_single_year, simulate_five_years
```

---

## The calculation

### Single year

Given capital `C`, annual return `r%`, hurdle `h%`, and a client/house split
that totals 100%:

```
1. Gross Profit        = C × r/100
2. Hurdle Amount       = C × h/100
3. Remaining Profit    = Gross Profit − Hurdle Amount
4. Client Share        = Remaining Profit × client_split/100
5. House Share         = Remaining Profit × house_split/100
6. Total Client Return = Hurdle Amount + Client Share
7. House Earnings      = House Share
8. Client Yield %      = Total Client Return / C × 100
9. House Yield %       = House Earnings / C × 100
```

A useful identity holds by construction, and the client view depends on it:

```
Total Client Return + House Earnings == Gross Profit
```

Every figure is rounded to 2 decimals at each step, which keeps rounding error
bounded rather than accumulating across the projection.

### Five-year projection

Each year runs the chain above, then:

```
Ending Capital = (Starting Capital + Total Client Return) − Payout
```

The Ending Capital rolls over as the next year's Starting Capital. **House
earnings never compound into client capital** — they are collected by the
house.

If a requested payout exceeds `Starting Capital + Total Client Return`, it is
capped at the funds available and an `st.warning` explains the cap. The cap
triggers on strictly greater than, so a payout exactly equal to the available
amount is taken in full without a warning.

**CLTV** is the sum of House Earnings across the five years.

---

## Loss years (deliberate behaviour)

When a year's return falls short of the hurdle, Remaining Profit is negative,
so both the client's and the house's shares come out negative. **The house
absorbs its split of the underperformance.** This is intentional, not a bug —
`test_below_hurdle_year_gives_house_a_negative_share` pins it.

The client view handles this differently: a below-hurdle year displays
**"No fee"** rather than a negative fee, and the CSV export writes `0.0` to
match. Because the fee is floored for display but balances come straight from
the engine, Net Gain can exceed Gross Gain in such a year; a footnote under
the table explains that the shortfall was absorbed rather than passed on.

If the commercial rule ever changes, the place to intervene is
`calculate_single_year` / `simulate_five_years` in `engine.py`.

---

## Internal vs Client view

Selected by the **View** radio at the top of the sidebar. Client view shows a
green *"CLIENT VIEW — safe to share"* banner.

| Internal column | Client column |
|---|---|
| Starting Capital | Opening Balance |
| Return % | Return % |
| Gross Profit | Gross Gain |
| Hurdle Amount | *withheld* |
| Remaining Profit | *withheld* |
| Client Share | *withheld* |
| Total Client Return | Net Gain |
| Client Yield % | Net Yield % |
| House Earnings | Performance Fee |
| House Yield % | *withheld* |
| Payout Taken | Withdrawal |
| Ending Capital | Closing Balance |

The client table is deliberately ordered **gross → fee → net**, so the fee
appears where it is deducted rather than after the net figure it produced.
This intentionally differs from the internal column order — don't "re-align"
them.

Client view also swaps the summary metrics: CLTV is removed entirely, and
Final Portfolio Value, Total Net Gains, Total Fees Paid and an effective
annual growth rate (CAGR, counting withdrawals as value received) take its
place. A projection disclaimer is shown.

Its CSV export is built from the client frame, so internal columns cannot leak
through the download.

---

## The projection grid

Per-year rates live in one editable table: `Return % · Hurdle % · Client
Split % · Payout (₹)`.

- Cells default to the Year 1 values from the sidebar.
- **Untouched cells keep following the sidebar** — change a sidebar rate and
  every year you have not overridden updates with it.
- **Edited cells hold their value.**
- Overrides survive the projection section being collapsed and reopened.

Streamlit discards state for widgets it does not render, so overrides are
mirrored into a plain `session_state` dict (`year_overrides`) and replayed onto
a grid rebuilt from the sidebar each run. Relying on the editor's own widget
state alone loses every override the moment the section is unticked.

The fund house split is derived as `100 − client split`, so a per-year split
can never fail to total 100.

Phase 1 results are computed from **Year 1 of the projection** when the
projection is on, so the two sections can never contradict each other.

---

## Results and staleness

Results are computed on **Calculate** and stored in `session_state`, so they
survive later widget interaction instead of vanishing on the next rerun.

Because they can now outlive the settings that produced them,
`calculation_signature()` captures the sidebar inputs, the projection toggle
and the full grid contents. When the current settings differ from the stored
ones, a prompt appears:

> Settings have changed since these results were calculated. Press **Calculate**
> to refresh.

A failed validation clears stored results, so an error never sits beside stale
figures.

There is a single **Calculate** button in the main column, positioned after
every input it consumes and directly above the results it produces.

---

## Input handling

Inputs are `st.text_input` rather than `st.number_input` so values can carry
Indian digit grouping and so the +/− steppers are absent.

`app.py` injects a small script (`_LIVE_NUMBER_JS`) that, for the sidebar
fields:

- applies live lakh/crore grouping to the currency field and strips stray
  characters from the percentage fields, preserving the caret position;
- auto-commits a field ~150 ms after typing stops, so a value never sits
  uncommitted when Calculate is pressed;
- moves focus to the next field on Enter, and submits from the last one — but
  only when the form would actually calculate, so a half-filled form stays
  silent.

### Maintenance warning

That script reaches into Streamlit's rendered DOM, matching inputs by
`aria-label` and the hint element by `data-testid="InputInstructions"`. **Both
are private Streamlit surface and can change on upgrade.**

It is built to degrade safely rather than silently:

- the "Press Enter to apply" hint is hidden only for fields the script has
  actually taken control of (marked `data-inr-managed="1"`), so a field it
  cannot manage keeps its hint and Streamlit's own Enter/blur commit;
- if nothing matches within 3 seconds, it logs an `[inr-formatter]` console
  warning.

If Streamlit is upgraded and input behaves oddly, check the browser console
for that warning first.

---

## Testing

```bash
python -m pytest -q      # 38 tests
```

Coverage includes the INR formatter at each magnitude boundary, the
`Net Gain + Fee == Gross Gain` identity, return-equals-hurdle, below-hurdle and
negative-return years, 100/0 and 0/100 splits, zero hurdle, zero capital, the
roll-over recurrence, the payout cap boundary either side of exact equality,
exhausted-capital cascades, per-year override isolation, and the row schema
that both CSV exports depend on.

Two tests lock the baseline figures (₹1cr, 20% return, 12% hurdle, 60/40):
CLTV **₹22,35,758.32** and final capital **₹2,17,37,731.18**.

The suite has been mutation-tested — six deliberate engine bugs (cap
comparison flipped, payout not deducted, house earnings compounding into
client capital, hurdle dropped from the client return, wrong digit grouping,
shares swapped) were all caught.

---

## Branding

| Token | Value | Use |
|---|---|---|
| Navy | `#0A1424` | Primary — headings, metric values, body text |
| White | `#FFFFFF` | Secondary — surfaces |
| Gold | `#CBA135` | Accent — **restricted** to structure, emphasis and hierarchy |

Per the brand guidelines gold is an accent, not a surface, so it is used for
the rule under the page title, interactive accents, and the tint on the
Ending Capital / Closing Balance column — the one figure a reader should land
on. It is never used as a background fill.

| Asset | Purpose |
|---|---|
| `assets/datavynx-logo.png` | Sidebar mark (`st.logo`) and this README's header |
| `assets/datavynx-icon.png` | Browser favicon, and the sidebar mark when collapsed |
| `assets/datavynx-logo-transparent.png` | Spare, for light or coloured backgrounds |

Colours are defined once as `BRAND_*` constants at the top of `app.py` and in
`.streamlit/config.toml`; change them in those two places rather than inline.

---

## Known limitations

- **Rounding is half-even** (Python's `round`), not the half-up convention used
  in finance. Tested across five compounding years with awkward rates and no
  drift was found, so this is not currently a live issue — but if these figures
  ever go onto an invoice, move `engine.py` to `decimal.Decimal` with
  `ROUND_HALF_UP`.
- **No scenario persistence.** Everything is lost on refresh; there is no way
  to save or compare scenarios.
- **No charts** — the projection is table-only.
- **Invalid values in the grid** rely on the editor's own `min`/`max`
  constraints; there is no separate validation pass over grid contents.
