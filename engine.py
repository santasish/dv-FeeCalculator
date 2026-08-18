"""Calculation engine for the fund management service charge calculator.

Deliberately free of any Streamlit import so the maths can be exercised
directly by the test suite without standing up an app context.
"""


def format_inr(number: float) -> str:
    """Formats a number into INR currency format (e.g. 10,00,000.00)"""
    if number is None:
        return "₹0.00"
    is_negative = number < 0
    number = abs(number)
    num_str = f"{number:.2f}"
    parts = num_str.split('.')
    integer_part = parts[0]
    decimal_part = parts[1]

    if len(integer_part) > 3:
        last_three = integer_part[-3:]
        remaining = integer_part[:-3]
        chunks = []
        while remaining:
            chunks.append(remaining[-2:])
            remaining = remaining[:-2]
        chunks.reverse()
        integer_part = ",".join(chunks) + "," + last_three

    result = f"₹{integer_part}.{decimal_part}"
    if is_negative:
        result = "-" + result
    return result


def parse_number(val_str: str):
    """Parses a string with commas into a float"""
    if not val_str:
        return None
    try:
        return float(val_str.replace(",", ""))
    except ValueError:
        return None


def calculate_single_year(
    capital_employed: float,
    hurdle_rate: float,
    client_split: float,
    fund_house_split: float,
    predicted_annual_return: float
) -> dict:
    """
    Core Calculation Engine (Pure Python Function)

    The fund house is paid only out of profit above the hurdle. Business rules
    (confirmed 2026-08-18):

    1. Loss year -- the client bears the whole loss; the house charges nothing.
    2. Profit at or below the hurdle -- the client keeps all of it; the house
       charges nothing.
    3. Profit above the hurdle -- the client receives the hurdle amount plus
       its split of the excess; the house receives its split of the excess.

    So ``hurdle_cleared`` decides which of two shapes the year takes, and in
    every case ``total_client_return + total_fund_house_earnings == gross_profit``.
    """
    # 1. Gross Profit = Capital Employed * (Annual Return % / 100)
    gross_profit = round(capital_employed * (predicted_annual_return / 100), 2)

    # 2. Hurdle Amount = Capital Employed * (Hurdle Rate % / 100)
    hurdle_amount = round(capital_employed * (hurdle_rate / 100), 2)

    # Exactly at the hurdle there is no excess to share, so both branches
    # agree; the strict comparison just picks the simpler one.
    hurdle_cleared = gross_profit > hurdle_amount

    if hurdle_cleared:
        # 3. Remaining Profit = Gross Profit - Hurdle Amount
        remaining_profit = round(gross_profit - hurdle_amount, 2)

        # 4. Client Share of Remaining = Remaining Profit * (Client Split % / 100)
        client_share_of_remaining = round(remaining_profit * (client_split / 100), 2)

        # 5. Fund House Share of Remaining = Remaining Profit * (Fund House Split % / 100)
        fund_house_share_of_remaining = round(remaining_profit * (fund_house_split / 100), 2)

        # 6. Total Client Return Amount = Hurdle Amount + Client Share of Remaining
        total_client_return = round(hurdle_amount + client_share_of_remaining, 2)
    else:
        # 3-5. Nothing above the hurdle, so nothing is split: no shortfall is
        # ever shared with the house, in a loss year or a sub-hurdle one.
        remaining_profit = 0.0
        client_share_of_remaining = 0.0
        fund_house_share_of_remaining = 0.0

        # 6. The whole gross result -- profit or loss -- is the client's.
        total_client_return = gross_profit

    # 7. Total Fund House Earnings = Fund House Share of Remaining (never negative)
    total_fund_house_earnings = fund_house_share_of_remaining

    # 8. Final Client Yield % = (Total Client Return Amount / Capital Employed) * 100
    final_client_yield = round((total_client_return / capital_employed) * 100, 2) if capital_employed != 0 else 0.0

    # 9. Final Fund House Yield % = (Total Fund House Earnings / Capital Employed) * 100
    final_fund_house_yield = round((total_fund_house_earnings / capital_employed) * 100, 2) if capital_employed != 0 else 0.0

    return {
        "hurdle_cleared": hurdle_cleared,
        "gross_profit": gross_profit,
        "hurdle_amount": hurdle_amount,
        "remaining_profit": remaining_profit,
        "client_share_of_remaining": client_share_of_remaining,
        "fund_house_share_of_remaining": fund_house_share_of_remaining,
        "total_client_return": total_client_return,
        "total_fund_house_earnings": total_fund_house_earnings,
        "final_client_yield": final_client_yield,
        "final_fund_house_yield": final_fund_house_yield
    }


def simulate_five_years(initial_capital: float, yearly_params: list) -> tuple:
    """
    5-Year Compounding Simulation (Pure Python Function)

    ``yearly_params`` is a list of five dicts, each carrying that year's
    ``hurdle_rate``, ``client_split``, ``fund_house_split``, ``annual_return``
    and requested ``payout``.

    Each year:
        Ending Capital = (Starting Capital + Total Client Return) - Payout
    and the Ending Capital rolls over as the next year's Starting Capital.
    Fund house earnings are collected by the house, so they never compound
    into the client's capital.

    In a loss year or a year at/below the hurdle the house earns nothing and
    the whole gross result is the client's (see ``calculate_single_year``), so
    House Earnings and CLTV are never reduced by a bad year -- they simply do
    not grow in it.

    Returns (rows, warnings): one row dict per year for the projection table,
    plus human-readable warnings for any payout that had to be capped at the
    funds available.
    """
    rows = []
    warnings = []
    capital = initial_capital

    for year, p in enumerate(yearly_params, start=1):
        results = calculate_single_year(
            capital,
            p["hurdle_rate"],
            p["client_split"],
            p["fund_house_split"],
            p["annual_return"],
        )
        available = round(capital + results["total_client_return"], 2)

        payout_taken = p["payout"]
        if payout_taken > available:
            warnings.append(
                f"Year {year}: requested payout of {format_inr(p['payout'])} exceeds "
                f"the available funds of {format_inr(available)}. "
                f"The payout has been capped at the available amount."
            )
            payout_taken = available

        ending_capital = round(available - payout_taken, 2)

        # Column order mirrors the Phase 1 audit trail (steps 1-9), followed by
        # the simulation-specific payout and roll-over columns.
        rows.append({
            "Year": year,
            "Starting Capital": capital,
            "Return %": p["annual_return"],
            "Gross Profit": results["gross_profit"],
            "Hurdle Amount": results["hurdle_amount"],
            "Remaining Profit": results["remaining_profit"],
            "Client Share": results["client_share_of_remaining"],
            "Total Client Return": results["total_client_return"],
            "Client Yield %": results["final_client_yield"],
            "House Earnings": results["total_fund_house_earnings"],
            "House Yield %": results["final_fund_house_yield"],
            "Payout Taken": payout_taken,
            "Ending Capital": ending_capital,
        })
        capital = ending_capital

    return rows, warnings
