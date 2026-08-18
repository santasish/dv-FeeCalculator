import json
from pathlib import Path

from charts import (
    allocation_chart,
    capital_chart,
    sensitivity_chart,
    show as show_chart,
    waterfall_chart,
    yearly_split_chart,
    yield_chart,
)
from engine import (
    calculate_single_year,
    format_inr,
    parse_number,
    simulate_five_years,
)

# pyrefly: ignore [missing-import]
import pandas as pd
# pyrefly: ignore [missing-import]
import streamlit as st
# pyrefly: ignore [missing-import]
import streamlit.components.v1 as components

# --------------------------- Datavynx branding ---------------------------
# Palette sampled from the supplied brand assets. The guidelines make navy
# primary, white secondary and restrict gold to structure, emphasis and
# hierarchy -- so gold marks the column that matters, never a whole surface.
BRAND_NAVY = "#0A1424"
BRAND_GOLD = "#CBA135"
BRAND_MUTED = "#5A6473"
BRAND_NEGATIVE = "#C0392B"

ASSETS_DIR = Path(__file__).parent / "assets"
BRAND_LOGO = ASSETS_DIR / "datavynx-logo.png"
BRAND_ICON = ASSETS_DIR / "datavynx-icon.png"

# Paths are resolved from this file rather than the working directory so the
# app can be launched from anywhere.
st.set_page_config(
    page_title="Datavynx | Fund Management Service Charge Calculator",
    page_icon=str(BRAND_ICON) if BRAND_ICON.exists() else "📊",
    layout="wide",
)

_BRAND_CSS = f"""
<style>
  h1, h2, h3, h4 {{ color: {BRAND_NAVY}; letter-spacing: -0.01em; }}
  /* Gold rule under the page title -- the brand's "structure" cue. */
  .dv-titlebar {{
      border-bottom: 3px solid {BRAND_GOLD};
      padding-bottom: 0.35rem;
      margin-bottom: 0.35rem;
  }}
  .dv-eyebrow {{
      color: {BRAND_MUTED};
      font-size: 0.78rem;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      margin-bottom: 0.15rem;
  }}
  .dv-footer {{
      color: {BRAND_MUTED};
      font-size: 0.78rem;
      border-top: 1px solid rgba(10, 20, 36, 0.12);
      margin-top: 2.5rem;
      padding-top: 0.75rem;
  }}
  [data-testid="stMetricValue"] {{ color: {BRAND_NAVY}; }}
</style>
"""
st.markdown(_BRAND_CSS, unsafe_allow_html=True)

def format_input_callback(key: str, group: bool = True):
    """Callback to format the input field automatically after the user hits Enter/blur

    group=True applies INR (lakh/crore) comma grouping -- only meaningful for
    currency amounts. Percentage fields pass group=False so that e.g. 1234 stays
    1234 instead of becoming 1,234, matching what the live formatter shows.
    """
    val = st.session_state[key]
    num = parse_number(val)
    if num is not None:
        # Format the number, remove ₹ symbol and .00 if it's a whole number
        formatted = format_inr(num).replace('₹', '') if group else f"{num:.2f}"
        if formatted.endswith('.00'):
            formatted = formatted[:-3]
        st.session_state[key] = formatted

_LIVE_NUMBER_JS = """
<script>
(function () {
  // { "<input aria-label>": true|false } -- true means apply INR comma grouping.
  var FIELDS = __FIELDS__;
  // Same labels in form order, used to decide where Enter moves focus next.
  var ORDER = __ORDER__;
  // Text of the button clicked by Enter on the last field (null to disable).
  var SUBMIT_LABEL = __SUBMIT_LABEL__;
  // Labels whose values must add up to 100 before Enter will submit.
  var MUST_TOTAL_100 = __MUST_TOTAL_100__;

  function groupIndian(digits) {
    if (digits.length <= 3) return digits;
    var last3 = digits.slice(-3);
    var rest = digits.slice(0, -3);
    var parts = [];
    while (rest.length > 2) {
      parts.unshift(rest.slice(-2));
      rest = rest.slice(0, -2);
    }
    if (rest) parts.unshift(rest);
    return parts.join(",") + "," + last3;
  }

  function formatValue(raw, group) {
    var negative = raw.trim().charAt(0) === "-";
    var cleaned = raw.replace(/[^0-9.]/g, "");
    var dot = cleaned.indexOf(".");
    var intPart = dot >= 0 ? cleaned.slice(0, dot) : cleaned;
    // Extra dots are dropped, but the digits are kept as typed -- rounding to 2
    // decimals is left to format_input_callback on Enter/blur so that nothing
    // silently disappears from under the caret mid-edit.
    var decPart = dot >= 0 ? cleaned.slice(dot + 1).replace(/\\./g, "") : null;
    intPart = intPart.replace(/^0+(?=\\d)/, "");
    // Percentage fields only get the stray-character stripping above, no grouping.
    var out = group ? groupIndian(intPart) : intPart;
    if (decPart !== null) out += "." + decPart;
    if (negative && out) out = "-" + out;
    return out;
  }

  // Number of digits/decimal-point chars to the left of the caret.
  function significantBefore(str, caret) {
    var n = 0;
    for (var i = 0; i < caret && i < str.length; i++) {
      if (/[0-9.]/.test(str.charAt(i))) n++;
    }
    return n;
  }

  function caretForCount(str, count) {
    if (count <= 0) return str.charAt(0) === "-" ? 1 : 0;
    var seen = 0;
    for (var i = 0; i < str.length; i++) {
      if (/[0-9.]/.test(str.charAt(i))) {
        seen++;
        if (seen === count) return i + 1;
      }
    }
    return str.length;
  }

  var doc = window.parent.document;
  var nativeSetter = Object.getOwnPropertyDescriptor(
    window.parent.HTMLInputElement.prototype, "value"
  ).set;

  // Streamlit only commits a text_input on Enter/blur, which is why it shows a
  // "Press Enter to apply" hint and why clicking Calculate can miss the value
  // still sitting in a focused field. Synthesising the Enter key once the user
  // pauses commits it for them.
  var COMMIT_DELAY_MS = 150;
  var commitTimers = new WeakMap();

  function commit(el) {
    var opts = {
      key: "Enter", code: "Enter", keyCode: 13, which: 13,
      bubbles: true, cancelable: true
    };
    el.dispatchEvent(new KeyboardEvent("keydown", opts));
    el.dispatchEvent(new KeyboardEvent("keypress", opts));
  }

  function scheduleCommit(el) {
    clearTimeout(commitTimers.get(el));
    commitTimers.set(el, setTimeout(function () { commit(el); }, COMMIT_DELAY_MS));
  }

  function findInput(label) {
    var inputs = doc.querySelectorAll("input[aria-label]");
    for (var i = 0; i < inputs.length; i++) {
      if (inputs[i].getAttribute("aria-label") === label) return inputs[i];
    }
    return null;
  }

  function findButton(text) {
    // Exactly one button carries this label, so a page-wide search is
    // unambiguous. Keep it that way: a second same-labelled button would make
    // Enter-to-submit depend on DOM order.
    var buttons = doc.querySelectorAll("button");
    for (var i = 0; i < buttons.length; i++) {
      if (buttons[i].textContent.trim() === text) return buttons[i];
    }
    return null;
  }

  // Enter on the last field submits rather than moving on. Deferred a little
  // longer than a plain focus move: Streamlit ignores a widget's value until it
  // is committed, so the click has to land after the Enter's commit, not with it.
  var SUBMIT_DELAY_MS = 120;

  function everyFieldFilled() {
    for (var i = 0; i < ORDER.length; i++) {
      var el = findInput(ORDER[i]);
      if (!el || el.value.trim() === "") return false;
    }
    return true;
  }

  function totalsAreValid() {
    if (!MUST_TOTAL_100.length) return true;
    var sum = 0;
    for (var i = 0; i < MUST_TOTAL_100.length; i++) {
      var el = findInput(MUST_TOTAL_100[i]);
      var value = el ? parseFloat(el.value.replace(/,/g, "")) : NaN;
      if (isNaN(value)) return false;
      sum += value;
    }
    // Rounded to 2dp to match the check the Python side performs.
    return Math.round(sum * 100) / 100 === 100;
  }

  // Enter only submits a form that would actually calculate. Anything short of
  // that -- blank fields, splits that do not total 100 -- leaves it silent,
  // because arriving at the end of the last field is not a request for
  // validation feedback. Clicking the button still reports every problem.
  function readyToSubmit() {
    return everyFieldFilled() && totalsAreValid();
  }

  function onKeyDown(e) {
    // Our own commit() Enter is untrusted; only a real keypress advances focus.
    if (!e.isTrusted || e.key !== "Enter") return;
    var el = e.target;
    // The real Enter commits by itself, so drop any commit we had queued.
    clearTimeout(commitTimers.get(el));
    var idx = ORDER.indexOf(el.getAttribute("aria-label"));
    // Formatting-only fields (payout amounts) are not part of the Enter chain:
    // without this guard, indexOf's -1 would wrap to ORDER[0] and Enter in a
    // payout field would teleport focus back to the first sidebar input.
    if (idx === -1) return;
    var next = ORDER[idx + 1];
    // Both branches look the target up by label rather than holding a node
    // reference: the commit triggers a rerun that can replace these elements.
    if (next) {
      setTimeout(function () {
        var target = findInput(next);
        if (target) target.focus();
      }, 0);
    } else if (SUBMIT_LABEL) {
      setTimeout(function () {
        if (!readyToSubmit()) return;
        var button = findButton(SUBMIT_LABEL);
        if (button) button.click();
      }, SUBMIT_DELAY_MS);
    }
  }

  function onInput(e) {
    var el = e.target;
    // Scheduled before the early return below: a keystroke that needs no
    // reformatting (e.g. "5" in a percentage field) still has to be committed.
    scheduleCommit(el);
    var before = el.value;
    var count = significantBefore(before, el.selectionStart);
    var after = formatValue(before, el.dataset.inrGroup === "1");
    if (after === before) return;
    // Native setter + input event so React (and therefore Streamlit) sees the change.
    nativeSetter.call(el, after);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    var pos = caretForCount(after, count);
    el.setSelectionRange(pos, pos);
  }

  var attachedCount = 0;

  function attach() {
    // Matching on the label in JS rather than in a CSS selector avoids having to
    // escape labels containing quotes, slashes or parentheses.
    var inputs = doc.querySelectorAll("input[aria-label]");
    for (var i = 0; i < inputs.length; i++) {
      var el = inputs[i];
      var label = el.getAttribute("aria-label");
      if (!Object.prototype.hasOwnProperty.call(FIELDS, label)) continue;
      if (el.dataset.inrLive === "1") continue;
      el.dataset.inrLive = "1";
      el.dataset.inrGroup = FIELDS[label] ? "1" : "0";
      el.setAttribute("inputmode", "decimal");
      el.addEventListener("input", onInput);
      el.addEventListener("keydown", onKeyDown);
      // Marks this field as auto-committed, which is what licenses hiding its
      // "Press Enter to apply" hint. Set only after the listeners are on.
      var container = el.closest('[data-testid="stTextInput"]');
      if (container) container.dataset.inrManaged = "1";
      attachedCount++;
    }
  }

  // Scoped to fields this script actually took control of, via the marker
  // attach() sets on their container. A blanket rule would hide the hint even
  // when attachment failed -- leaving a field that neither auto-commits nor
  // tells the user to press Enter, so a filled-looking form reports itself
  // empty. The hint must survive wherever the script is not managing input.
  function installScopedHintRule() {
    if (doc.getElementById("inr-hide-enter-hint")) return;
    var style = doc.createElement("style");
    style.id = "inr-hide-enter-hint";
    style.textContent =
      '[data-inr-managed="1"] [data-testid="InputInstructions"] ' +
      '{ display: none !important; }';
    doc.head.appendChild(style);
  }

  installScopedHintRule();
  attach();
  // Streamlit re-renders the DOM on every rerun, so keep re-attaching.
  setInterval(attach, 500);

  // If the DOM contract ever changes under us, say so in the console rather
  // than degrading in silence.
  setTimeout(function () {
    if (attachedCount === 0 && doc.querySelectorAll("input[aria-label]").length) {
      console.warn(
        "[inr-formatter] No inputs matched the expected labels. Live formatting, " +
        "auto-commit and Enter navigation are inactive; fields now rely on " +
        "Streamlit's own Enter/blur commit."
      );
    }
  }, 3000);
})();
</script>
"""


def enable_live_number_formatting(
    fields: dict,
    submit_label: str | None = None,
    must_total_100: list[str] | None = None,
    extra_fields: dict | None = None,
):
    """Cleans up the given text_inputs while the user types.

    ``fields`` maps a text_input's label to whether it should get INR
    (lakh/crore) comma grouping -- True for currency amounts, False for
    percentages, which only get stray characters stripped. Its iteration order
    is the order Enter walks the fields in.

    ``submit_label`` is the text of the button Enter presses once it reaches the
    end of the last field; pass None to leave focus where it is. Enter only
    presses it when the form would actually calculate: every field filled, and
    the values in ``must_total_100`` adding up to 100. Clicking the button
    directly still surfaces whatever is wrong.

    ``extra_fields`` (same label -> group mapping) get the live formatting but
    stay out of the Enter chain and the readiness checks. Meant for inputs that
    appear conditionally, like the per-year payout amounts; the attach() poll
    picks them up whenever they materialise.

    Purely cosmetic: format_input_callback still normalises the values on
    Enter/blur, so the fields stay correct even if this script fails to attach.
    """
    html = (
        _LIVE_NUMBER_JS
        .replace("__FIELDS__", json.dumps({**fields, **(extra_fields or {})}))
        .replace("__ORDER__", json.dumps(list(fields)))
        .replace("__SUBMIT_LABEL__", json.dumps(submit_label))
        .replace("__MUST_TOTAL_100__", json.dumps(must_total_100 or []))
    )
    # st.iframe supersedes st.components.v1.html, which is deprecated.
    if hasattr(st, "iframe"):
        # height must be a positive int or "content" -- 0 raises
        # StreamlitInvalidHeightError and "content" reserves ~150px of blank space.
        st.iframe(html, height=1)
    else:
        components.html(html, height=0)


def render_phase1_charts(rates: dict, results: dict, client_view: bool):
    """The two single-year charts, side by side on desktop, stacked on a phone.

    Left: how the gross profit is carved up. Right: gross return and yields
    against the hurdle line. Both are drawn from the same result dict as the
    metrics above them, so they cannot disagree with the numbers.
    """
    left, right = st.columns(2)
    with left:
        st.markdown(
            "**Where the gross gain goes**" if client_view
            else "**Where the gross profit goes**"
        )
        chart = allocation_chart(results, client_view)
        if chart is not None:
            show_chart(chart)
        else:
            st.caption("No profit to allocate this year.")
    with right:
        st.markdown("**Yields vs hurdle**")
        show_chart(yield_chart(rates, results, client_view))

    if not client_view:
        # Internal only: it plots house earnings. Full width, because the
        # crossings it exists to show need the horizontal room.
        st.markdown("**How the year changes with the return**")
        st.caption(
            "Everything else held fixed. The house earns nothing up to the "
            "hurdle and its share of the excess beyond it; below the hurdle "
            "the whole result, profit or loss, is the client's."
        )
        show_chart(sensitivity_chart(rates))


def render_projection_charts(rows: list, client_view: bool):
    """The projection charts: two side by side, then the capital bridge.

    Columns stack on a phone, so this reads as one column there.
    """
    left, right = st.columns(2)
    with left:
        st.markdown(
            "**Your portfolio value over 5 years**" if client_view
            else "**Client capital over 5 years**"
        )
        show_chart(capital_chart(rows, client_view))
    with right:
        st.markdown(
            "**Yearly net gain and fee**" if client_view
            else "**Yearly profit split and cumulative CLTV**"
        )
        show_chart(yearly_split_chart(rows, client_view))

    # Half width on desktop: with only three or four bars a full-width
    # waterfall spreads them too far apart to read as one bridge.
    bridge, _ = st.columns(2)
    with bridge:
        st.markdown(
            "**From starting capital to final value**" if client_view
            else "**Capital bridge: start to final**"
        )
        show_chart(waterfall_chart(rows, client_view))


def _audit_steps_3_to_6(results: dict, client_split, fund_house_split) -> str:
    """Steps 3-6 of the audit trail, narrating the branch the engine took.

    Above the hurdle the excess is split; at or below it nothing is split and
    the whole gross result is the client's. Writing the split formulas out
    for a year that had nothing to split would show a chain of zeros that
    explains nothing, so that branch says why instead.
    """
    gross = format_inr(results["gross_profit"])
    hurdle = format_inr(results["hurdle_amount"])
    if results.get("hurdle_cleared", results["remaining_profit"] > 0):
        remaining = format_inr(results["remaining_profit"])
        return f"""
        **3. Remaining Profit** (the excess above the hurdle)
        - *Formula:* Gross Profit - Hurdle Amount
        - *Calculation:* {gross} - {hurdle} = **{remaining}**

        **4. Client Share of Remaining**
        - *Formula:* Remaining Profit * (Client Split % / 100)
        - *Calculation:* {remaining} * ({client_split} / 100) = **{format_inr(results['client_share_of_remaining'])}**

        **5. Fund House Share of Remaining**
        - *Formula:* Remaining Profit * (Fund House Split % / 100)
        - *Calculation:* {remaining} * ({fund_house_split} / 100) = **{format_inr(results['fund_house_share_of_remaining'])}**

        **6. Total Client Return Amount**
        - *Formula:* Hurdle Amount + Client Share of Remaining
        - *Calculation:* {hurdle} + {format_inr(results['client_share_of_remaining'])} = **{format_inr(results['total_client_return'])}**
        """
    outcome = "a loss" if results["gross_profit"] < 0 else "at or below the hurdle"
    return f"""
        **3-5. Remaining Profit / Shares** — nothing to split
        - Gross Profit {gross} is {outcome} (Hurdle Amount {hurdle}), so there is
          no excess above the hurdle. Remaining Profit, Client Share and Fund
          House Share are all **₹0.00**: no shortfall is ever charged to or
          shared with the fund house.

        **6. Total Client Return Amount**
        - *Formula:* Gross Profit (the whole result is the client's)
        - *Calculation:* **{format_inr(results['total_client_return'])}**
        """


def render_phase1(snapshot: dict):
    """Renders the Phase 1 single-year results from a stored snapshot."""
    rates = snapshot["rates"]
    results = snapshot["results"]

    st.subheader("Calculation Results")

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Total Client Return Amount", format_inr(results['total_client_return']))
        st.metric("Final Client Yield", f"{results['final_client_yield']:,.2f}%")
    with col2:
        st.metric("Total Fund House Earnings", format_inr(results['total_fund_house_earnings']))
        st.metric("Final Fund House Yield", f"{results['final_fund_house_yield']:,.2f}%")

    render_phase1_charts(rates, results, client_view=False)

    capital_employed = rates["capital"]
    hurdle_rate = rates["hurdle_rate"]
    client_split = rates["client_split"]
    fund_house_split = rates["fund_house_split"]
    predicted_annual_return = rates["annual_return"]

    with st.expander("View Calculation Breakdown"):
        st.markdown("### Formula Audit Trail")
        st.markdown(f"""
        **1. Gross Profit**
        - *Formula:* Capital Employed * (Annual Return % / 100)
        - *Calculation:* {format_inr(capital_employed)} * ({predicted_annual_return} / 100) = **{format_inr(results['gross_profit'])}**

        **2. Hurdle Amount**
        - *Formula:* Capital Employed * (Hurdle Rate % / 100)
        - *Calculation:* {format_inr(capital_employed)} * ({hurdle_rate} / 100) = **{format_inr(results['hurdle_amount'])}**

        {_audit_steps_3_to_6(results, client_split, fund_house_split)}

        **7. Total Fund House Earnings**
        - *Formula:* Fund House Share of Remaining
        - *Calculation:* **{format_inr(results['total_fund_house_earnings'])}**

        **8. Final Client Yield %**
        - *Formula:* (Total Client Return Amount / Capital Employed) * 100
        - *Calculation:* ({format_inr(results['total_client_return'])} / {format_inr(capital_employed)}) * 100 = **{results['final_client_yield']:,.2f}%**

        **9. Final Fund House Yield %**
        - *Formula:* (Total Fund House Earnings / Capital Employed) * 100
        - *Calculation:* ({format_inr(results['total_fund_house_earnings'])} / {format_inr(capital_employed)}) * 100 = **{results['final_fund_house_yield']:,.2f}%**
        """)


def render_projection(snapshot: dict):
    """Renders the Phase 2 projection table from a stored snapshot."""
    rows = snapshot["projection_rows"]
    payout_warnings = snapshot["payout_warnings"]

    df = pd.DataFrame(rows).set_index("Year")
    df.index = [f"Year {y}" for y in df.index]

    st.markdown("---")
    st.subheader("Phase 2: 5-Year Projection & CLTV")

    for warning_msg in payout_warnings:
        st.warning(warning_msg)

    # Two prominent metrics only: a third column makes the big
    # rupee figures truncate at moderate window widths.
    cltv = round(float(df["House Earnings"].sum()), 2)
    total_payouts = round(float(df["Payout Taken"].sum()), 2)
    m1, m2 = st.columns(2)
    with m1:
        st.metric(
            "5-Year Client Lifetime Value (CLTV)",
            format_inr(cltv),
            help="Total fund house earnings accumulated across all 5 years.",
        )
    with m2:
        st.metric(
            "Final Client Portfolio Value",
            format_inr(float(df["Ending Capital"].iloc[-1])),
            help="The client's ending capital at the end of Year 5, after all payouts.",
        )
    if total_payouts > 0:
        st.caption(f"Total payouts taken across the 5 years: {format_inr(total_payouts)}")

    # Charts first, table one tap away: on a phone the wide table is a long
    # horizontal scroll, so it should not be what greets the reader.
    charts_tab, table_tab = st.tabs(["Charts", "Table"])
    with charts_tab:
        render_projection_charts(rows, client_view=False)

    # A totals row for the flow columns only -- point-in-time
    # columns (capital, yields) have no meaningful 5-year sum
    # and are left blank.
    flow_columns = [
        "Gross Profit", "Hurdle Amount", "Remaining Profit",
        "Client Share", "House Earnings", "Total Client Return",
        "Payout Taken",
    ]
    totals = {col: round(float(df[col].sum()), 2) for col in flow_columns}
    table_df = pd.concat([df, pd.DataFrame(totals, index=["5-Year Total"])])

    currency_columns = [
        "Starting Capital", "Gross Profit", "Hurdle Amount",
        "Remaining Profit", "Client Share", "House Earnings",
        "Total Client Return", "Payout Taken", "Ending Capital",
    ]
    percent_columns = ["Return %", "Client Yield %", "House Yield %"]

    # Pre-formatted to strings rather than via Styler.format:
    # st.dataframe renders NaN as a literal "None" regardless of
    # the Styler, and mixed number/string columns fail Arrow
    # serialization. An all-string table avoids both. The CSV
    # download below keeps raw numbers for spreadsheets.
    display = table_df.copy()
    for col in currency_columns:
        display[col] = table_df[col].map(
            lambda v: format_inr(v) if pd.notna(v) else "–")
    for col in percent_columns:
        display[col] = table_df[col].map(
            lambda v: f"{v:.2f}%" if pd.notna(v) else "–")

    def negative_red(value):
        # Formatted negatives all start with "-" (-₹1,000.00, -1.60%)
        return f"color: {BRAND_NEGATIVE}" if str(value).startswith("-") else ""

    styled = (
        display.style
        .map(negative_red, subset=currency_columns + percent_columns)
        .set_properties(
            subset=["Ending Capital"],
            **{"background-color": "rgba(203, 161, 53, 0.18)"},
        )
        .set_properties(
            subset=pd.IndexSlice[["5-Year Total"], :],
            **{"background-color": "rgba(10, 20, 36, 0.06)"},
        )
    )
    with table_tab:
        st.dataframe(styled)
        st.download_button(
            "Download 5-Year Projection (CSV)",
            data=df.reset_index(names="Year").to_csv(index=False).encode("utf-8"),
            file_name="5_year_projection.csv",
            mime="text/csv",
        )


# Internal column -> client-facing column. Anything absent is withheld:
# Hurdle Amount, Remaining Profit and Client Share are internal mechanics,
# and House Yield % is a fund-house metric with no client meaning.
#
# This order deliberately differs from the internal table: the client sequence
# reads gross -> fee -> net, so the fee lands where it is actually deducted
# rather than after the net figure it produced. Do not "re-align" it with the
# internal column order -- the divergence is the point.
CLIENT_COLUMN_LABELS = {
    "Starting Capital": "Opening Balance",
    "Return %": "Return %",
    "Gross Profit": "Gross Gain",
    # Hurdle Amount, Remaining Profit, Client Share -- withheld
    "House Earnings": "Performance Fee",
    "Total Client Return": "Net Gain",
    "Client Yield %": "Net Yield %",
    # House Yield % -- withheld
    "Payout Taken": "Withdrawal",
    "Ending Capital": "Closing Balance",
}

PROJECTION_DISCLAIMER = (
    "These figures are illustrative projections based on the assumed rates shown, "
    "not a forecast or guarantee of future returns. Actual results will vary."
)


def render_phase1_client(snapshot: dict):
    """Phase 1 results as the client sees them: gains and charges, no house metrics."""
    results = snapshot["results"]
    fee = results["total_fund_house_earnings"]

    st.subheader("Your Projected Year")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Net Gain", format_inr(results["total_client_return"]))
    with col2:
        st.metric("Net Yield", f"{results['final_client_yield']:,.2f}%")
    with col3:
        # The engine charges nothing at or below the hurdle; "No fee" just
        # says so in words instead of ₹0.00.
        st.metric("Performance Fee", format_inr(fee) if fee > 0 else "No fee")

    if fee <= 0:
        st.caption(
            "No performance fee applies this year because the return did not clear "
            "the hurdle rate."
        )

    render_phase1_charts(snapshot["rates"], results, client_view=True)

    with st.expander("How your return is calculated"):
        st.markdown(f"""
        - **Gross Gain on your capital:** {format_inr(results['gross_profit'])}
        - **Performance fee charged:** {format_inr(fee) if fee > 0 else 'No fee'}
        - **Your net gain:** {format_inr(results['total_client_return'])}
        - **Your net yield:** {results['final_client_yield']:,.2f}%
        """)

    st.caption(PROJECTION_DISCLAIMER)


def render_projection_client(snapshot: dict):
    """Phase 2 projection as the client sees it."""
    rows = snapshot["projection_rows"]

    df = pd.DataFrame(rows).set_index("Year")
    df.index = [f"Year {y}" for y in df.index]

    # Every figure comes straight from the engine, so the client view and
    # the internal view can never disagree about the client's money.
    client_df = df[list(CLIENT_COLUMN_LABELS)].rename(columns=CLIENT_COLUMN_LABELS)

    st.markdown("---")
    st.subheader("Your 5-Year Projection")

    initial_capital = float(df["Starting Capital"].iloc[0])
    final_capital = float(df["Ending Capital"].iloc[-1])
    total_withdrawn = round(float(df["Payout Taken"].sum()), 2)
    total_net_gain = round(float(df["Total Client Return"].sum()), 2)
    # The engine never charges a fee at or below the hurdle, so this sum is
    # exactly the fees actually charged.
    total_fees = round(float(df["House Earnings"].sum()), 2)

    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("Final Portfolio Value", format_inr(final_capital))
    with m2:
        st.metric("Total Net Gains (5 yr)", format_inr(total_net_gain))
    with m3:
        st.metric("Total Fees Paid", format_inr(total_fees))

    # Withdrawals counted as value received, otherwise taking money out
    # would read as underperformance.
    value_created = final_capital + total_withdrawn
    if initial_capital > 0 and value_created > 0:
        cagr = ((value_created / initial_capital) ** (1 / len(df)) - 1) * 100
        st.caption(
            f"Effective annual growth: **{cagr:,.2f}%** "
            "(withdrawals counted as value received)"
        )
    if total_withdrawn > 0:
        st.caption(f"Total withdrawn across the 5 years: {format_inr(total_withdrawn)}")

    charts_tab, table_tab = st.tabs(["Charts", "Table"])
    with charts_tab:
        render_projection_charts(rows, client_view=True)

    fee_waived_years = [
        year for year, value in df["House Earnings"].items() if value <= 0
    ]

    totals = {
        "Gross Gain": round(float(df["Gross Profit"].sum()), 2),
        "Performance Fee": total_fees,
        "Net Gain": total_net_gain,
        "Withdrawal": total_withdrawn,
    }
    table_df = pd.concat([client_df, pd.DataFrame(totals, index=["5-Year Total"])])

    currency_columns = [
        "Opening Balance", "Gross Gain", "Performance Fee",
        "Net Gain", "Withdrawal", "Closing Balance",
    ]
    percent_columns = ["Return %", "Net Yield %"]

    display = table_df.copy()
    for col in currency_columns:
        if col == "Performance Fee":
            display[col] = table_df[col].map(
                lambda v: "–" if pd.isna(v) else (format_inr(v) if v > 0 else "No fee"))
        else:
            display[col] = table_df[col].map(
                lambda v: format_inr(v) if pd.notna(v) else "–")
    for col in percent_columns:
        display[col] = table_df[col].map(
            lambda v: f"{v:.2f}%" if pd.notna(v) else "–")

    def negative_red(value):
        return f"color: {BRAND_NEGATIVE}" if str(value).startswith("-") else ""

    styled = (
        display.style
        .map(negative_red, subset=currency_columns + percent_columns)
        .set_properties(
            subset=["Closing Balance"],
            **{"background-color": "rgba(203, 161, 53, 0.18)"},
        )
        .set_properties(
            subset=pd.IndexSlice[["5-Year Total"], :],
            **{"background-color": "rgba(10, 20, 36, 0.06)"},
        )
    )
    with table_tab:
        st.dataframe(styled)

        # Built from the client frame so internal columns cannot leak via
        # export. A "No fee" year exports as 0.0, which is what it is.
        export_df = client_df.reset_index(names="Year")
        st.download_button(
            "Download Your Projection (CSV)",
            data=export_df.to_csv(index=False).encode("utf-8"),
            file_name="your_5_year_projection.csv",
            mime="text/csv",
        )

    if fee_waived_years:
        # Outside the tabs so it is read alongside the charts as well as the
        # table.
        st.caption(
            f"No performance fee was charged in {', '.join(fee_waived_years)} "
            "because the return did not clear the hurdle rate; the whole gross "
            "gain (or loss) for those years is yours."
        )

    st.caption(PROJECTION_DISCLAIMER)


GRID_COLUMNS = ["Return %", "Hurdle %", "Client Split %", "Payout (₹)"]


def calculation_signature(inputs: dict, enable_projection: bool, year_grid) -> tuple:
    """Everything the stored results depend on, in a comparable form.

    Comparing only the sidebar inputs was not enough: enabling the projection
    or editing the grid changes what Calculate would produce without touching
    a single sidebar field, so results looked current when they were not.
    """
    grid_state = None
    if enable_projection and year_grid is not None:
        grid_state = tuple(
            tuple(round(float(value), 6) for value in row)
            for row in year_grid[GRID_COLUMNS].itertuples(index=False)
        )
    return (tuple(sorted(inputs.items())), enable_projection, grid_state)


def build_base_grid(annual_return, hurdle_rate, client_split) -> pd.DataFrame:
    """The projection grid as it looks with no per-year overrides applied."""
    return pd.DataFrame(
        {
            "Return %": [float(annual_return or 0.0)] * 5,
            "Hurdle %": [float(hurdle_rate or 0.0)] * 5,
            "Client Split %": [float(client_split or 0.0)] * 5,
            "Payout (₹)": [0.0] * 5,
        },
        index=[f"Year {y}" for y in range(1, 6)],
    )


def projection_settings_grid(annual_return, hurdle_rate, client_split) -> pd.DataFrame:
    """Editable per-year grid whose edits survive the section being collapsed.

    Streamlit drops the state of any widget it did not render, so the editor's
    own edits vanish the moment the projection checkbox is unticked. Overrides
    are therefore mirrored into a plain session_state dict and replayed onto a
    grid rebuilt from the sidebar each run -- which also gives the tracking
    behaviour we want: an untouched cell follows the sidebar, an edited one
    stays put.
    """
    overrides = st.session_state.setdefault("year_overrides", {})

    base = build_base_grid(annual_return, hurdle_rate, client_split)
    seeded = base.copy()
    for (row_label, column), value in overrides.items():
        if row_label in seeded.index and column in seeded.columns:
            seeded.loc[row_label, column] = value

    edited = st.data_editor(
        seeded,
        key="year_grid",
        num_rows="fixed",
        column_config={
            "Return %": st.column_config.NumberColumn(
                "Return %", step=0.5, format="%.2f",
                help="May be negative for a loss year.",
            ),
            "Hurdle %": st.column_config.NumberColumn(
                "Hurdle %", min_value=0.0, step=0.5, format="%.2f",
            ),
            "Client Split %": st.column_config.NumberColumn(
                "Client Split %", min_value=0.0, max_value=100.0, step=1.0,
                format="%.2f",
                help="The fund house share is derived as 100 minus this, so the "
                     "split always totals 100%.",
            ),
            "Payout (₹)": st.column_config.NumberColumn(
                "Payout (₹)", min_value=0.0, step=100000.0, format="localized",
                help="Amount withdrawn at the end of that year. Leave at 0 for none.",
            ),
        },
    )

    # Re-derive the override set from what is on screen: any cell differing
    # from the sidebar-derived base is an override, anything matching it goes
    # back to tracking the sidebar.
    for row_label in edited.index:
        for column in GRID_COLUMNS:
            if edited.loc[row_label, column] != base.loc[row_label, column]:
                overrides[(row_label, column)] = edited.loc[row_label, column]
            else:
                overrides.pop((row_label, column), None)

    return edited


def main():
    # st.logo's dual-image mode served the icon in both slots here, so the
    # full lockup is placed explicitly at the top of the sidebar instead,
    # while st.logo supplies only the small mark in the app header.
    if BRAND_ICON.exists():
        st.logo(str(BRAND_ICON), size="large")
    if BRAND_LOGO.exists():
        st.sidebar.image(str(BRAND_LOGO), use_container_width=True)

    # Chosen before anything renders so every section below can branch on it.
    view = st.sidebar.radio(
        "View", ["Internal", "Client"], horizontal=True, key="view_mode",
        help="Client view hides fund house earnings, house yield and CLTV, and "
             "presents the fee from the client's side. Sidebar only -- never "
             "rendered in the client-facing main area.",
    )
    client_view = view == "Client"
    st.sidebar.markdown("---")

    st.markdown(
        '<div class="dv-titlebar">'
        '<div class="dv-eyebrow">Datavynx Analytics</div>'
        '<h1 style="margin:0">Fund Management Service Charge Calculator</h1>'
        "</div>",
        unsafe_allow_html=True,
    )
    if client_view:
        # Deliberately loud: the main risk with this feature is screen-sharing
        # the wrong view, so the active mode must be unmissable. The banner
        # names no withheld metric -- it is on screen while sharing.
        st.success("**CLIENT VIEW** — safe to share.")
    else:
        st.markdown("### Phase 1: Single-Year Predictive Calculator")

    st.sidebar.header("Input Parameters")
    
    # Initialize session states for inputs so we can format them on blur
    for key in ['cap_emp', 'hurdle', 'client_split', 'fund_split', 'annual_ret']:
        if key not in st.session_state:
            st.session_state[key] = ""
            
    # Using text_input instead of number_input to allow digit separators and remove +/- buttons
    CAPITAL_LABEL = "Capital Employed (₹)"
    HURDLE_LABEL = "Hurdle Rate (%)"
    CLIENT_SPLIT_LABEL = "Revenue Split: Client (%)"
    FUND_SPLIT_LABEL = "Revenue Split: Fund House (%)"
    ANNUAL_RETURN_LABEL = "Predicted Annual Return / Profit Generated (%)"

    capital_employed_str = st.sidebar.text_input(CAPITAL_LABEL, key="cap_emp", on_change=format_input_callback, args=("cap_emp", True))
    hurdle_rate_str = st.sidebar.text_input(HURDLE_LABEL, key="hurdle", on_change=format_input_callback, args=("hurdle", False))
    client_split_str = st.sidebar.text_input(CLIENT_SPLIT_LABEL, key="client_split", on_change=format_input_callback, args=("client_split", False))
    fund_house_split_str = st.sidebar.text_input(FUND_SPLIT_LABEL, key="fund_split", on_change=format_input_callback, args=("fund_split", False))
    predicted_annual_return_str = st.sidebar.text_input(ANNUAL_RETURN_LABEL, key="annual_ret", on_change=format_input_callback, args=("annual_ret", False))

    # Live cleanup while typing. Only the currency field gets comma grouping --
    # lakh/crore separators would be meaningless on a percentage. Declaration
    # order here is also the order Enter tabs through the fields. Per-year
    # payouts moved into the projection grid, which brings its own numeric
    # editing, so they no longer need registering here.
    enable_live_number_formatting({
        CAPITAL_LABEL: True,
        HURDLE_LABEL: False,
        CLIENT_SPLIT_LABEL: False,
        FUND_SPLIT_LABEL: False,
        ANNUAL_RETURN_LABEL: False,
    }, submit_label="Calculate", must_total_100=[CLIENT_SPLIT_LABEL, FUND_SPLIT_LABEL])

    capital_employed = parse_number(capital_employed_str)
    hurdle_rate = parse_number(hurdle_rate_str)
    client_split = parse_number(client_split_str)
    fund_house_split = parse_number(fund_house_split_str)
    predicted_annual_return = parse_number(predicted_annual_return_str)

    # Validate inputs
    invalid_inputs = []
    if capital_employed_str and capital_employed is None: invalid_inputs.append("Capital Employed")
    if hurdle_rate_str and hurdle_rate is None: invalid_inputs.append("Hurdle Rate")
    if client_split_str and client_split is None: invalid_inputs.append("Revenue Split: Client")
    if fund_house_split_str and fund_house_split is None: invalid_inputs.append("Revenue Split: Fund House")
    if predicted_annual_return_str and predicted_annual_return is None: invalid_inputs.append("Predicted Annual Return")
    
    if invalid_inputs:
        st.sidebar.error(f"Invalid number format in: {', '.join(invalid_inputs)}. Please use only numbers and commas.")

    inputs = {
        "Capital Employed": capital_employed,
        "Hurdle Rate": hurdle_rate,
        "Client Split": client_split,
        "Fund House Split": fund_house_split,
        "Predicted Annual Return": predicted_annual_return
    }

    # ---------------- Phase 2: 5-Year Projection & CLTV ----------------
    st.markdown("---")
    # "CLTV" is internal vocabulary that should never reach a client screen.
    projection_label = (
        "Show 5-Year Projection" if client_view
        else "Enable 5-Year Projection & CLTV Analysis"
    )
    enable_projection = st.checkbox(projection_label, key="enable_projection")

    year_grid = None
    if enable_projection:
        st.markdown("#### 5-Year Projection Settings")
        st.caption(
            "Each year's rates default to the Year 1 values from the sidebar — edit any "
            "cell to override just that year. Untouched cells keep following the sidebar, "
            "so changing a rate there updates every year you have not overridden. "
            "A payout is deducted at the end of its year and reduces the capital that "
            "compounds into the next one."
        )

        year_grid = projection_settings_grid(
            predicted_annual_return, hurdle_rate, client_split
        )

    # ------------------------- Calculate -------------------------
    # One button for both phases, in the main column rather than the sidebar:
    # it sits after every input it consumes -- under the projection grid when
    # that is open, under the enable checkbox when it is not -- and directly
    # above the results it produces, so the flow reads inputs -> action ->
    # output instead of splitting the action off into another panel.
    calculate_clicked = st.button("Calculate", key="calculate_main", type="primary")

    # Compute on click and store; render below from the stored snapshot so
    # results survive later widget interaction instead of vanishing on the
    # next rerun (st.button is only True for the run it was clicked on).
    if calculate_clicked:
        empty_fields = [name for name, val in inputs.items() if val is None]

        errors = []
        if invalid_inputs:
            pass  # Already reported next to the offending sidebar field.
        elif empty_fields:
            errors.append(
                "Please fill in all the required input fields before calculating. "
                f"Missing: {', '.join(empty_fields)}"
            )
        elif round(client_split + fund_house_split, 2) != 100.00:
            errors.append(
                "Revenue Split must add up to 100%. "
                f"Currently it is {client_split + fund_house_split}%."
            )

        if errors or invalid_inputs:
            # Drop any previous results: leaving them on screen next to a
            # fresh error would invite reading stale numbers as current.
            st.session_state.pop("calc", None)
            for message in errors:
                st.error(message)
        else:
            snapshot = {
                "inputs": dict(inputs),
                "signature": calculation_signature(inputs, enable_projection, year_grid),
                "projection_rows": None,
                "payout_warnings": [],
            }

            if enable_projection:
                # One row of the grid per year; the fund house share is derived
                # so a per-year split can never fail to total 100.
                yearly_params = []
                for _, row in year_grid.iterrows():
                    row_client_split = float(row["Client Split %"])
                    yearly_params.append({
                        "annual_return": float(row["Return %"]),
                        "hurdle_rate": float(row["Hurdle %"]),
                        "client_split": row_client_split,
                        "fund_house_split": round(100.0 - row_client_split, 2),
                        "payout": max(float(row["Payout (₹)"] or 0.0), 0.0),
                    })

                rows, payout_warnings = simulate_five_years(capital_employed, yearly_params)
                snapshot["projection_rows"] = rows
                snapshot["payout_warnings"] = payout_warnings

                # Phase 1 IS year 1 of the projection. Deriving it from the same
                # parameters means the two sections can never contradict each
                # other when a Year 1 cell is edited in the grid.
                first = yearly_params[0]
                snapshot["rates"] = {
                    "capital": capital_employed,
                    "hurdle_rate": first["hurdle_rate"],
                    "client_split": first["client_split"],
                    "fund_house_split": first["fund_house_split"],
                    "annual_return": first["annual_return"],
                }
            else:
                snapshot["rates"] = {
                    "capital": capital_employed,
                    "hurdle_rate": hurdle_rate,
                    "client_split": client_split,
                    "fund_house_split": fund_house_split,
                    "annual_return": predicted_annual_return,
                }

            # Computed from the rates actually used, so the audit trail below
            # always narrates the same numbers the metrics show.
            rates = snapshot["rates"]
            snapshot["results"] = calculate_single_year(
                rates["capital"],
                rates["hurdle_rate"],
                rates["client_split"],
                rates["fund_house_split"],
                rates["annual_return"],
            )

            st.session_state.calc = snapshot

    # --------------------- Render stored results ---------------------
    snapshot = st.session_state.get("calc")
    if snapshot:
        # Persisting results means they can now outlive the settings that
        # produced them, so say so rather than letting stale figures be
        # read as current. Covers the projection toggle and the grid too:
        # switching the projection on after calculating otherwise left the
        # old results sitting there with no projection and no explanation.
        if snapshot.get("signature") != calculation_signature(
            inputs, enable_projection, year_grid
        ):
            st.info(
                "Settings have changed since these results were calculated. "
                "Press **Calculate** to refresh."
            )
        if client_view:
            render_phase1_client(snapshot)
            if snapshot["projection_rows"]:
                render_projection_client(snapshot)
        else:
            render_phase1(snapshot)
            if snapshot["projection_rows"]:
                render_projection(snapshot)

    st.markdown(
        '<div class="dv-footer">Datavynx Analytics &middot; '
        "Fund Management Service Charge Calculator</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
