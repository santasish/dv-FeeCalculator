"""Altair charts for the calculator UI.

Every chart here is built from the same numbers the tables show (the engine's
result dicts / projection rows), so a chart can never disagree with the table
beside it. Client-view variants take a ``client_view`` flag and only ever draw
client-facing quantities -- fund house earnings, house yield and CLTV never
reach a client chart, and the fee is floored to zero the same way the client
table floors it.

Design rules baked in (they matter most on a phone):
- Rupee axes are scaled to a single unit (₹ Lakh / ₹ Crore) chosen from the
  data, because a raw ``1,00,00,000`` tick does not fit an iPhone-width axis.
- Values that matter are direct-labelled; touch has no hover, so a chart that
  is only readable via tooltip is unreadable on mobile. Tooltips stay on as
  a bonus.
- Legends sit on top, horizontally -- a right-hand legend eats a third of a
  narrow screen.
- Colour follows the entity everywhere: client money is blue, fund house
  money is gold, the hurdle is teal, and gross/reference figures are grey.
  Loss years simply draw below/left of zero rather than switching to a pie
  or donut, which cannot show a negative slice.
"""

# pyrefly: ignore [missing-import]
import altair as alt
# pyrefly: ignore [missing-import]
import pandas as pd
# pyrefly: ignore [missing-import]
import streamlit as st

from engine import format_inr

# Series colours, keyed to the Datavynx brand (navy primary, gold emphasis,
# fixed light surface -- see .streamlit/config.toml). Brand navy itself is
# too dark and too grey to work as a bar fill, so the client series uses the
# nearest in-band navy-blue; the house series is the exact brand gold. The
# three were validated together as a categorical set (adjacent CVD ΔE ≥ 8,
# normal-vision ΔE ≥ 15). Gold sits below 3:1 against white, which is why
# every chart also direct-labels its values and has a table twin.
_PALETTE = {
    "client": "#2a66b3",   # client money
    "house": "#cba135",    # fund house money / performance fee (brand gold)
    "house_dark": "#8a6a12",  # cumulative house earnings line over the gold bars
    "hurdle": "#1f9d8f",   # hurdle amount, paid to the client
    "muted": "#5a6473",    # gross / reference figures (brand muted)
    "ink": "#0a1424",      # labels and rules (brand navy)
    "surface": "#ffffff",  # gaps between stacked segments, rings on points
}
# Label ink per fill: white only where it clears 4.5:1 (the blue); the
# lighter teal and gold take the navy ink instead.
_LABEL_INK = {"#2a66b3": "#ffffff", "#cba135": "#0a1424", "#1f9d8f": "#0a1424"}

# (divisor, short suffix, axis title) from largest to smallest.
_UNITS = [
    (1e7, "Cr", "₹ Crore"),
    (1e5, "L", "₹ Lakh"),
    (1e3, "K", "₹ Thousand"),
]

_LEGEND_TOP = alt.Legend(
    orient="top", direction="horizontal", title=None, symbolType="square",
    labelFontSize=12,
)


def _colors() -> dict:
    return _PALETTE


def pick_unit(values) -> tuple[float, str]:
    """(divisor, axis title) so the largest magnitude reads as a small number."""
    biggest = max((abs(v) for v in values), default=0.0)
    for divisor, _, title in _UNITS:
        if biggest >= divisor:
            return divisor, title
    return 1.0, "₹"


def fmt_short(value: float) -> str:
    """Compact rupee label for direct labels: ₹12.5L, ₹1.25Cr, ₹85K, -₹40K."""
    sign = "-" if value < 0 else ""
    magnitude = abs(value)
    for divisor, suffix, _ in _UNITS:
        if magnitude >= divisor:
            number = f"{magnitude / divisor:.2f}".rstrip("0").rstrip(".")
            return f"{sign}₹{number}{suffix}"
    return f"{sign}₹{magnitude:,.0f}"


def show(chart: alt.TopLevelMixin) -> None:
    """Renders a chart full-width, restyled to the Streamlit theme."""
    st.altair_chart(chart, width="stretch", theme="streamlit")


# ------------------------------------------------------------------ Phase 1


def allocation_chart(results: dict, client_view: bool) -> alt.LayerChart | None:
    """One horizontal stacked bar: how the year's gross profit is carved up.

    Internal: hurdle (paid to the client) → client share of the remaining →
    fund house share. Client: net gain → performance fee.

    Below the hurdle the "gross profit is the whole bar" reading breaks down
    (the remaining profit is negative and the shares come out negative), so
    that case switches to plain component bars, which stay honest with mixed
    signs. Returns None when there is nothing to draw.
    """
    if results["remaining_profit"] < 0:
        return _components_chart(results, client_view)

    c = _colors()
    if client_view:
        segments = [
            ("Net gain", results["total_client_return"], c["client"]),
            ("Performance fee", results["total_fund_house_earnings"], c["house"]),
        ]
    else:
        segments = [
            ("Hurdle → client", results["hurdle_amount"], c["hurdle"]),
            ("Client share", results["client_share_of_remaining"], c["client"]),
            ("House share", results["fund_house_share_of_remaining"], c["house"]),
        ]
    segments = [s for s in segments if s[1] > 0]
    total = sum(value for _, value, _ in segments)
    if total <= 0:
        return None

    rows, start = [], 0.0
    for label, value, color in segments:
        rows.append({
            "Segment": label,
            "x0": start,
            "x1": start + value,
            "mid": start + value / 2,
            "Amount": format_inr(value),
            "Share": f"{value / total * 100:.1f}% of gross",
            "Label": fmt_short(value),
            "label_ink": _LABEL_INK.get(color, c["ink"]),
            # A label only goes inside a segment wide enough to hold it; the
            # legend, tooltip and table carry the narrow ones.
            "show_label": value / total >= 0.14,
        })
        start += value
    df = pd.DataFrame(rows)

    base = alt.Chart(df)
    bars = base.mark_bar(
        height=42, cornerRadius=3, stroke=c["surface"], strokeWidth=2,
    ).encode(
        x=alt.X("x0:Q", axis=None, scale=alt.Scale(domain=[0, total], nice=False)),
        x2="x1:Q",
        color=alt.Color(
            "Segment:N",
            scale=alt.Scale(domain=[s[0] for s in segments], range=[s[2] for s in segments]),
            legend=_LEGEND_TOP,
        ),
        tooltip=[
            alt.Tooltip("Segment:N", title="Component"),
            alt.Tooltip("Amount:N", title="Amount"),
            alt.Tooltip("Share:N", title="Share"),
        ],
    )
    labels = base.transform_filter(alt.datum.show_label).mark_text(
        fontSize=13, fontWeight="bold",
    ).encode(
        x=alt.X("mid:Q"), text="Label:N",
        color=alt.Color("label_ink:N", scale=None, legend=None),
    )

    return (
        alt.layer(bars, labels)
        .resolve_scale(color="independent")
        .properties(height=42)
    )


def _components_chart(results: dict, client_view: bool) -> alt.LayerChart:
    """Below-hurdle fallback: gross vs what each side ends up with."""
    c = _colors()
    fee = results["total_fund_house_earnings"]
    if client_view:
        rows = [
            ("Gross gain", results["gross_profit"], c["muted"]),
            ("Net gain", results["total_client_return"], c["client"]),
            # Floored to match the "No fee" the client table shows.
            ("Performance fee", max(fee, 0.0), c["house"]),
        ]
    else:
        rows = [
            ("Gross profit", results["gross_profit"], c["muted"]),
            ("Client return", results["total_client_return"], c["client"]),
            ("House earnings", fee, c["house"]),
        ]
    df = pd.DataFrame(
        [{"Metric": m, "Amount": v, "Label": fmt_short(v), "Full": format_inr(v)}
         for m, v, _ in rows]
    )
    if client_view and fee <= 0:
        # Same wording as the client table's "No fee" cell.
        df.loc[df["Metric"] == "Performance fee", ["Label", "Full"]] = "No fee"
    return _horizontal_bars(
        df, order=[m for m, _, _ in rows], colors=[col for _, _, col in rows],
        value_field="Amount", axis=None, palette=c,
    )


def yield_chart(rates: dict, results: dict, client_view: bool) -> alt.LayerChart:
    """Bullet-style bars: gross return and the yields, against the hurdle line.

    Answers "did the year clear the hurdle, and by how much?" without reading
    a single number. The house yield is internal only.
    """
    c = _colors()
    rows = [
        ("Gross return", rates["annual_return"], c["muted"]),
        ("Net yield" if client_view else "Client yield",
         results["final_client_yield"], c["client"]),
    ]
    if not client_view:
        rows.append(("House yield", results["final_fund_house_yield"], c["house"]))
    df = pd.DataFrame(
        [{"Metric": m, "Amount": v, "Label": f"{v:,.2f}%", "Full": f"{v:,.2f}%"}
         for m, v, _ in rows]
    )
    hurdle = float(rates["hurdle_rate"])
    return _horizontal_bars(
        df, order=[m for m, _, _ in rows], colors=[col for _, _, col in rows],
        value_field="Amount", palette=c,
        axis=alt.Axis(title="% of capital", labelExpr="datum.label + '%'", tickCount=5),
        threshold=(hurdle, f"Hurdle {hurdle:,.2f}%"),
    )


def _horizontal_bars(df, order, colors, value_field, axis, palette,
                     threshold=None) -> alt.LayerChart:
    """Thin horizontal bars with end labels; optional dashed threshold rule.

    Negatives extend left of zero and are labelled on their left end. The x
    domain always includes zero and the threshold, padded so labels fit.
    """
    ink = palette["ink"]
    values = list(df[value_field]) + ([threshold[0]] if threshold else [])
    lo, hi = min(0.0, min(values)), max(0.0, max(values))
    span = (hi - lo) or 1.0
    domain = [lo - (0.28 * span if lo < 0 else 0), hi + 0.28 * span]

    base = alt.Chart(df)
    bars = base.mark_bar(height=16, cornerRadiusEnd=3).encode(
        y=alt.Y("Metric:N", sort=order, axis=alt.Axis(title=None, labelFontSize=12)),
        x=alt.X(
            f"{value_field}:Q",
            scale=alt.Scale(domain=domain, nice=False),
            axis=axis,
        ),
        color=alt.Color(
            "Metric:N", scale=alt.Scale(domain=order, range=colors), legend=None,
        ),
        tooltip=[alt.Tooltip("Metric:N"), alt.Tooltip("Full:N", title="Value")],
    )
    text_props = dict(color=ink, fontSize=12, fontWeight="bold")
    positive_labels = base.transform_filter(
        alt.datum[value_field] >= 0
    ).mark_text(align="left", dx=5, **text_props).encode(
        y=alt.Y("Metric:N", sort=order), x=f"{value_field}:Q", text="Label:N",
    )
    negative_labels = base.transform_filter(
        alt.datum[value_field] < 0
    ).mark_text(align="right", dx=-5, **text_props).encode(
        y=alt.Y("Metric:N", sort=order), x=f"{value_field}:Q", text="Label:N",
    )
    # A baseline so a bar pointing left reads unmistakably as negative.
    zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(
        color=palette["muted"], strokeWidth=1,
    ).encode(x="x:Q")
    layers = [bars, zero, positive_labels, negative_labels]

    if threshold:
        value, label = threshold
        line_df = pd.DataFrame({"x": [value], "label": [label]})
        rule = alt.Chart(line_df).mark_rule(
            color=ink, strokeDash=[4, 3], strokeWidth=1.5,
        ).encode(x="x:Q")
        # The label flips to the left of the rule once the hurdle is in the
        # right half, so it cannot run off the edge on a narrow screen.
        on_right = value > (domain[0] + domain[1]) / 2
        rule_label = alt.Chart(line_df).mark_text(
            align="right" if on_right else "left", dx=-4 if on_right else 4,
            dy=-4, baseline="bottom", color=ink, fontSize=11,
        ).encode(x="x:Q", y=alt.value(0), text="label:N")
        layers += [rule, rule_label]

    height = 30 * len(order) + (28 if threshold else 8)
    return alt.layer(*layers).properties(height=height)


# ------------------------------------------------------------------ Phase 2


def capital_chart(rows: list, client_view: bool) -> alt.LayerChart:
    """The client's capital from the start through each year's close.

    Payout years get a marker under the point so a dip reads as a withdrawal
    rather than a loss. Only the first and last values are labelled; the rest
    are one tap away in the tooltip and always in the table.
    """
    c = _colors()
    points = [{
        "Period": "Start",
        "Capital": rows[0]["Starting Capital"],
        "Payout": 0.0,
    }]
    for r in rows:
        points.append({
            "Period": f"Yr {r['Year']}",
            "Capital": r["Ending Capital"],
            "Payout": r["Payout Taken"],
        })
    divisor, unit_title = pick_unit(p["Capital"] for p in points)
    payout_word = "withdrawn" if client_view else "payout"
    for i, p in enumerate(points):
        p["Value"] = p["Capital"] / divisor
        p["Amount"] = format_inr(p["Capital"])
        p["Point label"] = fmt_short(p["Capital"]) if i in (0, len(points) - 1) else ""
        p["Payout label"] = f"−{fmt_short(p['Payout'])} {payout_word}" if p["Payout"] > 0 else ""
        p["Payout amount"] = format_inr(p["Payout"]) if p["Payout"] > 0 else "None"
    df = pd.DataFrame(points)

    x = alt.X("Period:N", sort=None, axis=alt.Axis(title=None, labelAngle=0, labelFontSize=12))
    y = alt.Y(
        "Value:Q",
        scale=alt.Scale(zero=False, nice=True, padding=24),
        axis=alt.Axis(title=unit_title, format=",.2~f"),
    )
    tooltip = [
        alt.Tooltip("Period:N"),
        alt.Tooltip("Amount:N", title="Capital"),
        alt.Tooltip("Payout amount:N", title="Payout" if not client_view else "Withdrawal"),
    ]
    base = alt.Chart(df)
    line = base.mark_line(color=c["client"], strokeWidth=2).encode(x=x, y=y)
    dots = base.mark_point(
        filled=True, size=80, color=c["client"], stroke=c["surface"], strokeWidth=2,
    ).encode(x=x, y=y, tooltip=tooltip)
    # End labels lean inwards (start label grows rightwards, end label
    # leftwards) so neither can be clipped by the plot edge on a phone.
    label_props = dict(dy=-14, color=c["ink"], fontSize=12, fontWeight="bold")
    start_label = base.transform_filter(alt.datum.Period == "Start").mark_text(
        align="left", dx=-8, **label_props,
    ).encode(x=x, y=y, text="Point label:N")
    end_label = base.transform_filter(alt.datum.Period == points[-1]["Period"]).mark_text(
        align="right", dx=8, **label_props,
    ).encode(x=x, y=y, text="Point label:N")
    payout_labels = base.transform_filter(alt.datum.Payout > 0).mark_text(
        dy=18, color=c["ink"], fontSize=11,
    ).encode(x=x, y=y, text="Payout label:N")

    return alt.layer(line, dots, start_label, end_label, payout_labels).properties(height=280)


def yearly_split_chart(rows: list, client_view: bool) -> alt.LayerChart:
    """Per-year stacked bars of who received the profit; internal adds CLTV.

    Internal: client return + house earnings (= gross profit) per year, with
    the running total of house earnings drawn over the top so the CLTV figure
    can be seen building. Client: net gain + performance fee (floored to zero
    in below-hurdle years, matching the client table).
    """
    c = _colors()
    if client_view:
        components = [
            ("Net gain", "Total Client Return", c["client"], False),
            ("Performance fee", "House Earnings", c["house"], True),
        ]
    else:
        components = [
            ("Client return", "Total Client Return", c["client"], False),
            ("House earnings", "House Earnings", c["house"], False),
        ]

    long_rows = []
    for r in rows:
        for order, (name, column, _, floor) in enumerate(components):
            amount = max(r[column], 0.0) if floor else r[column]
            long_rows.append({
                "Period": f"Yr {r['Year']}",
                "Component": name,
                "Amount": amount,
                "order": order,
            })
    cumulative = []
    if not client_view:
        running = 0.0
        for r in rows:
            running = round(running + r["House Earnings"], 2)
            cumulative.append({"Period": f"Yr {r['Year']}", "Amount": running})

    divisor, unit_title = pick_unit(
        [x["Amount"] for x in long_rows] + [x["Amount"] for x in cumulative]
    )
    for x_ in long_rows + cumulative:
        x_["Value"] = x_["Amount"] / divisor
        x_["Full"] = format_inr(x_["Amount"])
    df = pd.DataFrame(long_rows)

    x = alt.X(
        "Period:N", sort=None,
        axis=alt.Axis(title=None, labelAngle=0, labelFontSize=12),
        scale=alt.Scale(paddingInner=0.4),
    )
    bars = alt.Chart(df).mark_bar(stroke=c["surface"], strokeWidth=1).encode(
        x=x,
        y=alt.Y("Value:Q", stack="zero", axis=alt.Axis(title=unit_title, format=",.2~f")),
        color=alt.Color(
            "Component:N",
            scale=alt.Scale(
                domain=[n for n, *_ in components],
                range=[col for _, _, col, _ in components],
            ),
            legend=_LEGEND_TOP,
        ),
        order=alt.Order("order:Q"),
        tooltip=[
            alt.Tooltip("Period:N"),
            alt.Tooltip("Component:N"),
            alt.Tooltip("Full:N", title="Amount"),
        ],
    )
    zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(
        color=c["muted"], strokeWidth=1,
    ).encode(y="y:Q")
    layers = [bars, zero]

    if cumulative:
        cum_df = pd.DataFrame(cumulative)
        cum_df["Point label"] = ""
        cum_df.loc[cum_df.index[-1], "Point label"] = f"CLTV {fmt_short(cumulative[-1]['Amount'])}"
        # A darker step of the house gold: same family as the yearly bars it
        # accumulates, but separable from them where the line crosses a bar.
        cum_base = alt.Chart(cum_df)
        cum_line = cum_base.mark_line(color=c["house_dark"], strokeWidth=2).encode(
            x=x, y=alt.Y("Value:Q"),
        )
        cum_dots = cum_base.mark_point(
            filled=True, size=70, color=c["house_dark"], stroke=c["surface"], strokeWidth=2,
        ).encode(
            x=x, y="Value:Q",
            tooltip=[alt.Tooltip("Period:N"), alt.Tooltip("Full:N", title="Cumulative CLTV")],
        )
        # The label usually lands on top of a bar, so it gets a white halo
        # (a stroked copy underneath) to stay legible on any fill.
        label_props = dict(align="right", dx=-10, dy=-12, fontSize=12, fontWeight="bold")
        cum_halo = cum_base.mark_text(
            color=c["surface"], stroke=c["surface"], strokeWidth=5, **label_props,
        ).encode(x=x, y="Value:Q", text="Point label:N")
        cum_label = cum_base.mark_text(color=c["ink"], **label_props).encode(
            x=x, y="Value:Q", text="Point label:N",
        )
        layers += [cum_line, cum_dots, cum_halo, cum_label]

    return alt.layer(*layers).properties(height=280)
