<p align="center">
  <img src="assets/datavynx-logo.png" alt="Datavynx Analytics" width="480">
</p>

<h1 align="center">Fund Management Service Charge Calculator</h1>

<p align="center">
  <img src="https://img.shields.io/badge/tests-41%20passing-CBA135?style=flat-square" alt="tests">
  <img src="https://img.shields.io/badge/python-3.14-0A1424?style=flat-square" alt="python">
  <img src="https://img.shields.io/badge/streamlit-1.61-0A1424?style=flat-square" alt="streamlit">
  <img src="https://img.shields.io/badge/charts-8%20Altair-CBA135?style=flat-square" alt="charts">
  <img src="https://img.shields.io/badge/internal%20use-only-C0392B?style=flat-square" alt="internal use only">
</p>

An internal Streamlit tool for modelling fund management fees under a
hurdle-rate-plus-profit-share arrangement.

- **Phase 1** — single-year calculation with a full formula audit trail.
- **Phase 2** — five-year compounding projection with per-year rate overrides,
  payouts, and a Client Lifetime Value figure.
- **Charts** — eight Altair charts alongside the tables (profit allocation,
  yields vs hurdle, sensitivity, capital over time, yearly split with CLTV,
  capital waterfall, a five-year allocation bar, and a slider-driven
  market-shock explorer), sized to read on a phone as well as a desktop.
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

Tested against Python 3.14, Streamlit 1.61.1, pandas 3.0.5, Altair 6.2.2.

`.claude/launch.json` pins the dev server to port 8502.

---

## Project layout

| File | Contents |
|---|---|
| `engine.py` | All calculation logic. **No Streamlit import** — importable and testable on its own. |
| `app.py` | Everything UI: views, renderers, the projection grid, the input formatter. |
| `charts.py` | The Altair charts (Phase 1 allocation, yield and sensitivity charts; Phase 2 capital, profit-split, waterfall, 5-year allocation and market-shock charts), built from the engine's own result dicts. |
| `test_engine.py` | 41 tests covering the maths and its edge cases. |
| `assets/` | Datavynx brand marks used by the app and this README. |
| `.streamlit/config.toml` | Brand theme (navy text, gold accent). |
| `.claude/launch.json` | Dev-server definition: `streamlit run app.py` on port 8502, headless. |
| `requirements.txt` | `streamlit`, `altair`, `pandas`, `pytest`. |

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

   if Gross Profit > Hurdle Amount          (hurdle cleared)
3.   Remaining Profit    = Gross Profit − Hurdle Amount
4.   Client Share        = Remaining Profit × client_split/100
5.   House Share         = Remaining Profit × house_split/100
6.   Total Client Return = Hurdle Amount + Client Share
   else                                     (loss, or profit at/below hurdle)
3-5. Remaining Profit = Client Share = House Share = 0
6.   Total Client Return = Gross Profit     (the whole result is the client's)

7. House Earnings      = House Share        (never negative)
8. Client Yield %      = Total Client Return / C × 100
9. House Yield %       = House Earnings / C × 100
```

The result dict also carries `hurdle_cleared` so the UI can narrate the branch
that was taken. A useful identity holds by construction in both branches, and
the client view depends on it:

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

## Loss years and sub-hurdle years

The fund house is paid only out of profit **above** the hurdle. Three rules
follow from that, and the test suite pins each of them:

| Year's result | Client receives | House receives |
|---|---|---|
| **Loss** | the whole loss | nothing |
| **Profit at or below the hurdle** | the whole profit | nothing |
| **Profit above the hurdle** | hurdle amount + its split of the excess | its split of the excess |

On ₹1 crore with a 12 % hurdle and a 60/40 split:

| Return | Gross | Client return | House earnings |
|---|---|---|---|
| −10 % | −₹10,00,000 | −₹10,00,000 | ₹0 |
| 8 % | ₹8,00,000 | ₹8,00,000 | ₹0 |
| 12 % | ₹12,00,000 | ₹12,00,000 | ₹0 |
| 20 % | ₹20,00,000 | ₹16,80,000 | ₹3,20,000 |

Consequences worth knowing:

- **House Earnings is never negative** and **CLTV is never reduced by a bad
  year** — it simply does not grow in one. The house does not share in a
  shortfall, and no fee from a good year is clawed back by a bad one.
- The projection carries a loss straight into the next year's Starting
  Capital, so a loss year shrinks the base that every later year compounds
  from — even though it costs the client nothing in fees.
- The Internal audit trail collapses steps 3–6 into a "nothing to split" note
  for such a year. The Client view shows **"No fee"** and its CSV writes
  `0.0`; both come straight from the engine, not from any display rounding.
  Net Gain equals Gross Gain in those years.
- In the charts, the profit-allocation bar gives way to plain component bars
  (there is nothing being carved up), the yearly-split bars have no house
  segment, and the sensitivity curve shows the house line flat at zero up to
  the hurdle.

If this rule ever changes, the one place to change it is `calculate_single_year`
in `engine.py` — every table, chart, CSV and caption derives from its result.

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
python -m pytest -q      # 41 tests
```

Coverage includes the INR formatter at each magnitude boundary, the
`Net Gain + Fee == Gross Gain` identity, return-equals-hurdle, below-hurdle and
loss years (house earns nothing, client keeps the whole result, house earnings
never negative across a sweep of returns), 100/0 and 0/100 splits, zero hurdle, zero capital, the
roll-over recurrence, the payout cap boundary either side of exact equality,
exhausted-capital cascades, per-year override isolation, and the row schema
that both CSV exports depend on.

Two tests lock the baseline figures (₹1cr, 20% return, 12% hurdle, 60/40):
CLTV **₹22,35,758.32** and final capital **₹2,17,37,731.18**.

The suite has been mutation-tested — six deliberate engine bugs (cap
comparison flipped, payout not deducted, house earnings compounding into
client capital, hurdle dropped from the client return, wrong digit grouping,
shares swapped) were all caught.

**The tests cover `engine.py` only.** Charts and layout are not unit-tested —
several of the bugs fixed in this file's history (bars overlapping under
Streamlit's `autosize`, a hover layer resolving one series instead of two,
chart pairs not stacking on an iPad) were invisible to pytest and only
appeared in a browser. After changing `charts.py` or the layout, restart the
dev server and check at the widths in the table under
[Layout and responsiveness](#layout-and-responsiveness), in **both** views:
no exception, no horizontal overflow, no clipped labels, complete legends,
and the loss-year fallback branch. Values shown should be cross-checked
against `engine.py` directly rather than trusted from the chart.

---

## Charts

Every results section pairs its numbers with a chart, drawn from the same
result dict / projection rows as the table beside it so the two can never
disagree. Altair is used because it ships with Streamlit (no extra
dependency), follows the Streamlit theme, and has no pan/zoom by default —
so swiping across a chart on a phone scrolls the page instead of the chart.

| Where | Internal view | Client view |
|---|---|---|
| Phase 1 | **Where the gross profit goes** — one stacked bar: hurdle → client · client share · house share | Net gain · performance fee |
| Phase 1 | **Yields vs hurdle** — gross return, client yield and house yield as bars against a dashed hurdle line | Gross return and net yield only |
| Phase 1 | **How the year changes with the return** — client return and house earnings swept across a range of annual returns, hurdle marked, current year marked. House earnings are flat at zero up to the hurdle and rise beyond it; the client line is the full gross result up to the hurdle, then the hurdle plus its split — both kink at the hurdle. Hovering or tapping anywhere snaps a crosshair to the nearest return and reads both lines at once: a dot on each with "Client ₹…" / "House ₹…" beside it, the return at the top, and a three-line tooltip. | Not shown (it plots house earnings) |
| Phase 2 | **Client capital over 5 years** — line with the start/end values labelled and payout years marked | Same, worded as "portfolio value" / "withdrawn" |
| Phase 2 | **Yearly profit split** — client return + house earnings per year, with the cumulative CLTV line over the top | Net gain + performance fee (no fee segment in a sub-hurdle year); no CLTV |
| Phase 2 | **Capital bridge** — waterfall: start capital + net gains − payouts = final value. Exact, because house earnings never enter the client's capital. | Same, worded "withdrawn" |
| Phase 2 | **Five-year allocation** — one stacked bar, the same hurdle → client / client share / house share carve-up as Phase 1's allocation chart but summed across the plan, with no time axis. It is the only view that separates the hurdle-guaranteed portion from the client's share of the upside at the aggregate level — the yearly-split chart lumps both into one "Client return" segment each year. If every year cleared its hurdle the bar is exact and stacked; if any year did not, a stacked carve-up would misstate that year, so it falls back to Phase 1's plain component bars (gross vs. client return vs. house earnings, net of the bad year). | "Net gain" / "Performance fee", same fallback |
| Phase 2 | **The plan under a market shock** — a slider (rendered by Vega, no rerun) adds Δ points, −20 to +20, to *every year's* planned return; the client-capital path and the cumulative house earnings redraw instantly against dashed ghosts of the plan. Each Δ is a real run of `simulate_five_years` on the grid's own parameters, so Δ = 0 matches the table exactly. End labels state the difference vs plan; years the house earns nothing are tagged "no fee"; hover reads any year. Shows the asymmetry the hurdle creates: a −5 pt shock costs the client ~12 % of final capital but the house ~65 % of CLTV. | Portfolio line only, worded "If markets do better or worse than assumed" |

An earlier version of the fourth chart was a per-year "effective fee rate vs
headline split" — house earnings ÷ that year's gross, against the headline
split. It required a paragraph of explanation to read (a ratio of a ratio)
and didn't earn that cost, so it was replaced 2026-08-18 with the five-year
allocation bar above: the same idea, but concrete rupees instead of a
derived percentage.

### Layout and responsiveness

Phase 2 charts sit in a **Charts / Table** tab pair so the wide table is one
tap away rather than the first thing a phone shows. They are laid out as a
2×2 grid — path (capital, yearly split) over end-state (bridge, five-year
allocation) — with the shock explorer full width beneath, since it is the
one what-if view and its slider needs the room.

Chart pairs use `st.columns(2)`, but Streamlit only stacks columns below a
640 px *viewport*. That left an iPad in portrait with the sidebar open
(768 px viewport, ~430 px of content) drawing two 205 px charts — clipped
labels, truncated legends, dropped axis ticks. `_BRAND_CSS` therefore adds a
container query on the main block: any two-column block holding a chart
stacks when the *content area* is under 600 px. Metric pairs are excluded
and stay side by side. Verified:

| Width | Chart pairs | Notes |
|---|---|---|
| Desktop 1280 | 2×2 | 397 px columns |
| iPad landscape 1024, sidebar collapsed | 2×2 | 419 px columns |
| iPad landscape 1024, sidebar open | stacked | only ~554 px of content |
| iPad portrait 768 | stacked | metrics stay 2-up |
| iPhone 375 | stacked | no horizontal overflow |

**Place charts with CSS; size plot areas with Vega.** The five-year
allocation bar is short and sits beside the much taller capital bridge. It is
drawn compact (`_ALLOC_5YR_HEIGHT`) and centred by CSS in a bridge-height box
(the `alloc_5yr` keyed container → `.st-key-alloc_5yr`), and that min-height
is dropped inside the same container query that stacks the pair. Padding the
Vega canvas to the bridge's height instead is the obvious alternative and is
wrong: the canvas follows the chart everywhere, so the padding reappears as a
blank band once the layout stacks on a phone. Note the bridge measures 307 px
on the page despite `height=260` in its `.properties()` — legend and axis
chrome — so match a neighbour by measuring it in the browser, not by reusing
its Python constant.

### Mobile-first details worth keeping when editing `charts.py`

- Rupee axes are scaled to one unit (₹ Lakh / ₹ Crore) picked from the data;
  raw `1,00,00,000` ticks do not fit a phone-width axis.
- Values that matter are direct-labelled (`₹12.5L`), because touch has no
  hover. Tooltips stay on as a bonus.
- Legends are on top, horizontal.
- Colour follows the entity: client money blue, house money / fee gold, hurdle
  teal, gross/reference grey. Loss years draw below or left of zero rather than
  switching chart type; at or below the hurdle, the allocation bar gives way to
  plain component bars because there is nothing being carved up.
- Client-view charts are separate code paths that only ever receive client
  quantities — house earnings, house yield and CLTV cannot leak into them.

### Streamlit and Vega gotchas

- `show()` sets a spec-level `autosize: fit-x`. Streamlit's Vega theme uses
  `fit`, under which a chart's `height` is the budget for the *whole* figure
  and the axes eat into the plot — a three-bar chart ends up with its bars
  overlapping. With `fit-x`, `height` means the plot area, as it does offline.
  Rendering a spec to PNG offline will *not* reproduce this: vl-convert pads
  instead, so the bug only appears in the browser.
- The shock explorer's slider is a Vega `binding_range` param: every scenario
  is precomputed in Python and the slider only filters, so dragging it never
  triggers a Streamlit rerun and it works with a thumb. Its label and range
  input are styled by the `.vega-bindings` rules in `_BRAND_CSS`.
- A hover layer built from an invisible `mark_rule` over long-format data
  stacks one rule per series at each x, so the tooltip can only ever show one
  of them. The sensitivity and shock charts instead use a nearest-x
  `selection_point` over a wide (one row per x) frame, which resolves every
  series from a single hit.
- Streamlit's file watcher does not reliably pick up edits to `charts.py` in
  this folder — restart the dev server after editing a module, or you will
  verify the previous spec.

The three series colours were validated together as a colourblind-safe set
against the white surface; brand navy itself is too dark and too grey to
work as a bar fill, so the client series uses the nearest in-band navy-blue
(`#2a66b3`) while the house series is the exact brand gold.

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
| `assets/social-preview.png` | GitHub social preview card, 1280×640 |
| `assets/make_social_preview.py` | Regenerates the card (`python assets/make_social_preview.py`); edit its `TAGLINE` when the feature list changes, then re-upload |

GitHub's social preview is a **repository setting, not a file** — there is no
REST or GraphQL write path for it (`openGraphImageUrl` is read-only), so it
cannot be set from code. Upload it by hand once:

> **Settings → General → Social preview → Edit → Upload an image**, choosing
> `assets/social-preview.png`.

It is sized to GitHub's recommended 1280×640 so the card is not letterboxed;
the raw logo is 4:1 and would be cropped.

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
- **Invalid values in the grid** rely on the editor's own `min`/`max`
  constraints; there is no separate validation pass over grid contents.
