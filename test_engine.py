"""Tests for the calculation engine.

Run with:  python -m pytest -q
"""

import pytest

from engine import (
    calculate_single_year,
    format_inr,
    parse_number,
    simulate_five_years,
)

CAPITAL = 10_000_000.0
BASE = dict(
    hurdle_rate=12.0,
    client_split=60.0,
    fund_house_split=40.0,
    annual_return=20.0,
    payout=0.0,
)


def years(overrides_by_year=None):
    """Five base years, with ``{year_number: {...}}`` merged over them."""
    overrides_by_year = overrides_by_year or {}
    plan = []
    for y in range(1, 6):
        params = dict(BASE)
        params.update(overrides_by_year.get(y, {}))
        plan.append(params)
    return plan


# --------------------------------------------------------------------------
# format_inr -- Indian lakh/crore grouping
# --------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    (0, "₹0.00"),
    (999, "₹999.00"),
    (1000, "₹1,000.00"),
    (100000, "₹1,00,000.00"),
    (10000000, "₹1,00,00,000.00"),
    (250000000, "₹25,00,00,000.00"),
    (1234.5, "₹1,234.50"),
    (-1234.5, "-₹1,234.50"),
    (None, "₹0.00"),
])
def test_format_inr(value, expected):
    assert format_inr(value) == expected


@pytest.mark.parametrize("text,expected", [
    ("1,00,00,000", 10000000.0),
    ("1000", 1000.0),
    ("12.5", 12.5),
    ("", None),
    (None, None),
    ("abc", None),
    ("12abc", None),
])
def test_parse_number(text, expected):
    assert parse_number(text) == expected


def test_format_and_parse_round_trip():
    for value in (0.0, 1234.5, 10000000.0, 250000000.0):
        assert parse_number(format_inr(value).replace("₹", "")) == value


# --------------------------------------------------------------------------
# calculate_single_year
# --------------------------------------------------------------------------

def test_single_year_known_figures():
    r = calculate_single_year(CAPITAL, 12.0, 60.0, 40.0, 20.0)
    assert r["gross_profit"] == 2_000_000.0
    assert r["hurdle_amount"] == 1_200_000.0
    assert r["remaining_profit"] == 800_000.0
    assert r["client_share_of_remaining"] == 480_000.0
    assert r["total_client_return"] == 1_680_000.0
    assert r["total_fund_house_earnings"] == 320_000.0
    assert r["final_client_yield"] == 16.80
    assert r["final_fund_house_yield"] == 3.20


def test_client_return_plus_house_earnings_equals_gross():
    """The identity the client-facing view depends on."""
    for annual_return in (-15.0, 0.0, 12.0, 20.0, 45.0):
        r = calculate_single_year(CAPITAL, 12.0, 60.0, 40.0, annual_return)
        assert (
            round(r["total_client_return"] + r["total_fund_house_earnings"], 2)
            == r["gross_profit"]
        )


def test_return_equal_to_hurdle_leaves_nothing_to_split():
    r = calculate_single_year(CAPITAL, 12.0, 60.0, 40.0, 12.0)
    assert r["remaining_profit"] == 0.0
    assert r["client_share_of_remaining"] == 0.0
    assert r["total_fund_house_earnings"] == 0.0
    assert r["total_client_return"] == r["hurdle_amount"]


def test_below_hurdle_year_client_keeps_all_profit_and_house_earns_nothing():
    """Business rule 2: profit under the hurdle is entirely the client's."""
    r = calculate_single_year(CAPITAL, 12.0, 60.0, 40.0, 8.0)
    assert r["hurdle_cleared"] is False
    assert r["gross_profit"] == 800_000.0
    assert r["total_client_return"] == 800_000.0
    assert r["total_fund_house_earnings"] == 0.0
    assert r["remaining_profit"] == 0.0
    assert r["client_share_of_remaining"] == 0.0
    assert r["final_client_yield"] == 8.0
    assert r["final_fund_house_yield"] == 0.0


def test_loss_year_client_bears_whole_loss_and_house_earns_nothing():
    """Business rule 1: a loss is entirely the client's; the fee is never negative."""
    r = calculate_single_year(CAPITAL, 12.0, 60.0, 40.0, -10.0)
    assert r["hurdle_cleared"] is False
    assert r["gross_profit"] == -1_000_000.0
    assert r["total_client_return"] == -1_000_000.0
    assert r["total_fund_house_earnings"] == 0.0
    assert r["final_client_yield"] == -10.0


def test_house_earnings_are_never_negative_across_the_range():
    for annual_return in (-50.0, -15.0, 0.0, 5.0, 11.99, 12.0, 12.01, 20.0, 45.0):
        r = calculate_single_year(CAPITAL, 12.0, 60.0, 40.0, annual_return)
        assert r["total_fund_house_earnings"] >= 0.0
        assert r["hurdle_cleared"] == (annual_return > 12.0)


def test_above_hurdle_still_credits_hurdle_plus_split():
    """Business rule 3 -- unchanged shape above the hurdle."""
    r = calculate_single_year(CAPITAL, 12.0, 60.0, 40.0, 20.0)
    assert r["hurdle_cleared"] is True
    assert r["total_client_return"] == r["hurdle_amount"] + r["client_share_of_remaining"]
    assert r["total_fund_house_earnings"] == r["fund_house_share_of_remaining"] > 0


def test_full_client_split_leaves_house_with_nothing():
    r = calculate_single_year(CAPITAL, 12.0, 100.0, 0.0, 20.0)
    assert r["total_fund_house_earnings"] == 0.0
    assert r["total_client_return"] == r["gross_profit"]


def test_full_house_split_leaves_client_the_hurdle_only():
    r = calculate_single_year(CAPITAL, 12.0, 0.0, 100.0, 20.0)
    assert r["client_share_of_remaining"] == 0.0
    assert r["total_client_return"] == r["hurdle_amount"]


def test_zero_hurdle_makes_return_pure_profit_share():
    r = calculate_single_year(CAPITAL, 0.0, 60.0, 40.0, 20.0)
    assert r["hurdle_amount"] == 0.0
    assert r["total_client_return"] == r["client_share_of_remaining"]


def test_zero_capital_does_not_divide_by_zero():
    r = calculate_single_year(0.0, 12.0, 60.0, 40.0, 20.0)
    assert r["final_client_yield"] == 0.0
    assert r["final_fund_house_yield"] == 0.0


# --------------------------------------------------------------------------
# simulate_five_years -- roll-over, payouts, capping
# --------------------------------------------------------------------------

def test_capital_rolls_over_between_years():
    rows, warnings = simulate_five_years(CAPITAL, years())
    assert warnings == []
    assert len(rows) == 5
    for previous, following in zip(rows, rows[1:]):
        assert following["Starting Capital"] == previous["Ending Capital"]


def test_ending_capital_formula():
    rows, _ = simulate_five_years(CAPITAL, years({2: {"payout": 500_000.0}}))
    for row in rows:
        expected = round(
            row["Starting Capital"] + row["Total Client Return"] - row["Payout Taken"], 2
        )
        assert row["Ending Capital"] == expected


def test_house_earnings_never_compound_into_client_capital():
    rows, _ = simulate_five_years(CAPITAL, years())
    first = rows[0]
    assert first["Ending Capital"] == round(
        first["Starting Capital"] + first["Total Client Return"], 2
    )


def test_payout_reduces_the_capital_that_compounds():
    without, _ = simulate_five_years(CAPITAL, years())
    with_payout, _ = simulate_five_years(CAPITAL, years({2: {"payout": 500_000.0}}))
    assert with_payout[2]["Starting Capital"] < without[2]["Starting Capital"]


def test_payout_exactly_equal_to_available_is_not_capped():
    """Boundary: the cap triggers on strictly greater, not equal."""
    baseline, _ = simulate_five_years(CAPITAL, years())
    available = round(
        baseline[0]["Starting Capital"] + baseline[0]["Total Client Return"], 2
    )
    rows, warnings = simulate_five_years(CAPITAL, years({1: {"payout": available}}))
    assert warnings == []
    assert rows[0]["Payout Taken"] == available
    assert rows[0]["Ending Capital"] == 0.0


def test_payout_one_paisa_over_available_is_capped_and_warned():
    baseline, _ = simulate_five_years(CAPITAL, years())
    available = round(
        baseline[0]["Starting Capital"] + baseline[0]["Total Client Return"], 2
    )
    rows, warnings = simulate_five_years(CAPITAL, years({1: {"payout": available + 0.01}}))
    assert len(warnings) == 1
    assert "Year 1" in warnings[0] and "capped" in warnings[0]
    assert rows[0]["Payout Taken"] == available
    assert rows[0]["Ending Capital"] == 0.0


def test_exhausted_capital_cascades_as_zeros():
    rows, warnings = simulate_five_years(CAPITAL, years({1: {"payout": 9e9}}))
    assert len(warnings) == 1
    for row in rows[1:]:
        assert row["Starting Capital"] == 0.0
        assert row["Gross Profit"] == 0.0
        assert row["Total Client Return"] == 0.0
        assert row["House Earnings"] == 0.0
        assert row["Ending Capital"] == 0.0


def test_two_capped_payouts_warn_independently():
    rows, warnings = simulate_five_years(
        CAPITAL, years({2: {"payout": 9e9}, 4: {"payout": 9e9}})
    )
    assert len(warnings) == 2
    assert "Year 2" in warnings[0]
    assert "Year 4" in warnings[1]
    assert rows[1]["Ending Capital"] == 0.0
    assert rows[3]["Payout Taken"] == 0.0


def test_per_year_override_affects_only_that_year():
    override = {"annual_return": 8.0, "hurdle_rate": 10.0,
                "client_split": 75.0, "fund_house_split": 25.0}
    baseline, _ = simulate_five_years(CAPITAL, years())
    rows, _ = simulate_five_years(CAPITAL, years({4: override}))
    assert rows[:3] == baseline[:3]
    assert rows[3]["Return %"] == 8.0
    assert rows[4]["Return %"] == BASE["annual_return"]
    assert rows[4]["Starting Capital"] == rows[3]["Ending Capital"]


def test_negative_return_year_shrinks_capital():
    rows, _ = simulate_five_years(CAPITAL, years({3: {"annual_return": -15.0}}))
    assert rows[2]["Ending Capital"] < rows[2]["Starting Capital"]
    assert rows[2]["Gross Profit"] < 0


def test_row_schema_is_stable():
    """The projection table and both CSV exports are built from these keys."""
    rows, _ = simulate_five_years(CAPITAL, years())
    assert list(rows[0]) == [
        "Year", "Starting Capital", "Return %", "Gross Profit", "Hurdle Amount",
        "Remaining Profit", "Client Share", "Total Client Return",
        "Client Yield %", "House Earnings", "House Yield %",
        "Payout Taken", "Ending Capital",
    ]


def test_baseline_five_year_figures_are_locked():
    """Regression lock on the headline numbers: ₹1cr, 20% return, 12% hurdle, 60/40."""
    rows, _ = simulate_five_years(CAPITAL, years())
    cltv = round(sum(r["House Earnings"] for r in rows), 2)
    assert cltv == 2_235_758.32
    assert rows[-1]["Ending Capital"] == 21_737_731.18


def test_compounding_matches_a_hand_rolled_loop():
    """Independent re-derivation of the whole roll-over, not just the sum."""
    plan = years({2: {"payout": 500_000.0}, 4: {"annual_return": 8.0}})
    rows, _ = simulate_five_years(CAPITAL, plan)

    capital = CAPITAL
    for params, row in zip(plan, rows):
        expected = calculate_single_year(
            capital, params["hurdle_rate"], params["client_split"],
            params["fund_house_split"], params["annual_return"],
        )
        assert row["Starting Capital"] == capital
        assert row["Total Client Return"] == expected["total_client_return"]
        assert row["House Earnings"] == expected["total_fund_house_earnings"]
        capital = round(capital + expected["total_client_return"] - params["payout"], 2)
        assert row["Ending Capital"] == capital
