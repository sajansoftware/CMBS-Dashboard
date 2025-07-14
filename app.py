import streamlit as st
import json
import pandas as pd
from datetime import datetime
from dateutil import parser
from dateutil.parser import parse
import re
import os
os.environ["STREAMLIT_WATCH_DIRECTORIES"] = "false"


st.set_page_config(page_title="Loan Summary Table", layout="wide")

st.markdown("""
<style>
/* Stretch table full width */
.ag-theme-streamlit {
    width: 100% !important;
}

/* Minimum height: half viewport height */
.ag-root-wrapper {
    min-height: 50vh !important;
    max-height: none !important;
}

/* Increase row height & vertical spacing */
.ag-row {
    line-height: 1.8 !important;
    font-size: 15px !important;
    padding-top: 8px !important;
    padding-bottom: 8px !important;
}

/* Better spacing between rows visually */
.ag-row:not(:last-child) {
    border-bottom: 1px solid #eee !important;
}

/* Header styling */
.ag-header-cell-label {
    font-size: 14px !important;
    font-weight: 600 !important;
}

/* Streamlit padding override */
.block-container {
    padding-top: 2rem;
    padding-bottom: 2rem;
    padding-left: 1.5rem;
    padding-right: 1.5rem;
}
</style>
""", unsafe_allow_html=True)





with open("data/master_combined_loans.json", "r", encoding="utf-8") as f:
    raw_data = json.load(f)

# ------------------ Helper Functions ------------------

def find_nested(data, paths):
    for path in paths:
        keys = path.split(".")
        ref = data
        for key in keys:
            if isinstance(ref, list):
                try:
                    key = int(key)
                    ref = ref[key]
                except:
                    ref = None
            elif isinstance(ref, dict):
                ref = ref.get(key)
            else:
                ref = None
            if ref is None:
                break
        if ref:
            return ref
    return ""

def extract_numeric(val):
    if isinstance(val, str):
        cleaned = val.replace("$", "").replace(",", "").replace("%", "").strip()
        cleaned = cleaned.split(" ")[0]
        if cleaned == "":
            return None
        return float(cleaned)
    return float(val) if val is not None else None

def extract_dscr_value(dscr_str):
    try:
        if isinstance(dscr_str, dict):
            return float(dscr_str.get("whole_loan", None))
        if isinstance(dscr_str, str):
            parts = dscr_str.lower().replace("x", "").split("/")
            return float(parts[-1].strip())
        return float(dscr_str)
    except:
        return None

def extract_debt_yield_value(dy_str):
    try:
        if isinstance(dy_str, str):
            parts = dy_str.lower().replace("%", "").split("/")
            return float(parts[-1].strip())
        return float(dy_str)
    except:
        return None

def get_top_tenant(data):
    sources = [
        ("top_largest_tenants_by_ubr.tenants", "percent_of_total_base_rent", "tenant"),
        ("largest_tenants_based_on_uw_base_rent.tenants", "percent_of_uw_base_rent", "tenant_name"),
        ("major_tenant.tenants", "percent_of_total_annual_uw_base_rent", "name"),
        ("tenant_summary.tenants", "percent_of_total_uw_base_rent", "name"),
        ("tenant_summary.ten_largest_tenants", "percent_of_total_uw_base_rent", "tenant"),
        ("top_tenant_summary.tenants", "percent_uw_base_rent", "name"),
    ]
    for path, pct_field, name_field in sources:
        tenants = find_nested(data, [path])
        if isinstance(tenants, list) and tenants:
            tenants_sorted = sorted(
                tenants,
                key=lambda t: float(str(t.get(pct_field, "0")).replace("%", "").strip()),
                reverse=True
            )
            top_name = tenants_sorted[0].get(name_field, "")
            if top_name:
                return top_name
    return ""

manual_ratings = {
    "n2405-x1": "S&P: A- / Moody's: Baa1 / Fitch: BBB",
    "n2450-x2": "S&P: B / Moody's: Caa1",
    "n3021-x3": "DBRS: BBB(sf)",
    "n3791_x3": "S&P: BBB+ / Moody's: Baa1 / Fitch: A-"
}

def fmt_currency(val):
    try:
        return f"${float(val):,.0f}" if pd.notna(val) else ""
    except:
        return ""

def fmt_percent(val):
    try:
        return f"{float(val):.2f}%" if pd.notna(val) else ""
    except:
        return ""

def fmt_number(val):
    try:
        return f"{float(val):.2f}" if pd.notna(val) else ""
    except:
        return ""

def fmt_date(val):
    try:
        dt = parse(val, dayfirst=False, fuzzy=True)
        return dt.strftime("%-m/%-d/%Y")
    except:
        try:
            dt = parse(val, dayfirst=False)
            return dt.strftime("%#m/%#d/%Y")
        except:
            return val or ""

def strip_zip(location):
    if isinstance(location, str):
        return re.sub(r",?\s*\d{5}(-\d{4})?$", "", location.strip())
    return location

def compute_loan_term(data):
    raw_term = (
        data.get("mortgage_loan_information", {}).get("original_term_months")
        or data.get("mortgage_loan_information", {}).get("original_term_to_maturity_months")
        or data.get("loan_summary", {}).get("original_term")
        or data.get("loan_term_original")
    )
    if raw_term:
        try:
            cleaned = str(raw_term).lower().replace("months", "").replace("month", "").strip()
            months = int(cleaned)
            return f"{months // 12} Years"
        except:
            pass
    start = data.get("mortgage_loan_information", {}).get("first_payment_date")
    end = data.get("mortgage_loan_information", {}).get("maturity_date") or data.get("maturity_date")
    try:
        if start and end:
            start_date = parser.parse(start)
            end_date = parser.parse(end)
            diff_months = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
            return f"{diff_months // 12} Years"
    except:
        return ""
    return ""

# ------------------ Build Records ------------------

records = []

deal_names = {
    "n1967-x4": "Series 2020-BNK25",
    "n2405-x1": "BENCHMARK 2021-B23",
    "n2450-x2": "BENCHMARK 2021-B24",
    "n2711_x3": "BANK 2021-BNK36",
    "n3021-x3": "BENCHMARK 2022-B34",
    "n3791_x3": "Series 2023-C22",
}



for loan_id, data in raw_data.items():

    deal_name = deal_names.get(loan_id, "")

    purpose = find_nested(data, [
        "loan_purpose", "loan_summary.loan_purpose", "mortgage_loan_information.loan_purpose",
        "loan_metadata.loan_purpose", "mortgaged_property_information.loan_purpose", "details.loan_purpose"
    ])
    borrower = find_nested(data, [
        "borrower", "mortgage_loan_information.borrower", "borrower_sponsor",
        "mortgaged_property_information.borrower_sponsor"
    ])
    tenant = get_top_tenant(data)

    tenant_lists = [
        find_nested(data, ["major_tenant.tenants"]),
        find_nested(data, ["tenant_summary.tenants"]),
        find_nested(data, ["largest_tenants_based_on_uw_base_rent.tenants"])
    ]
    tenant_lists = [lst if isinstance(lst, list) else [] for lst in tenant_lists]
    combined_tenants = tenant_lists[0] + tenant_lists[1] + tenant_lists[2]
    tenant_rating = manual_ratings.get(loan_id, "")
    if not tenant_rating:
        for t in combined_tenants:
            name = t.get("name") or t.get("tenant") or t.get("tenant_name")
            cr = t.get("credit_rating", {})
            if name == tenant and isinstance(cr, dict):
                parts = []
                for agency in ["S&P", "Moody's", "Fitch"]:
                    val = cr.get(agency) or cr.get(agency.lower()) or cr.get(agency.upper())
                    if val and val.upper() != "NR":
                        parts.append(f"{agency}: {val}")
                tenant_rating = " / ".join(parts)
                break

    original_balance = extract_numeric(find_nested(data, [
        "original_principal_balance", "loan_summary.original_principal_balance",
        "mortgage_loan_information.original_balance", "mortgage_loan_information.cut_off_date_principal_balance"
    ]))
    interest_rate_raw = find_nested(data, [
        "interest_rate", "mortgage_loan_information.interest_rate",
        "mortgage_loan_information.interest_rate_percent", "mortgage_loan_information.mortgage_rate", "mortgage_rate"
    ])
    try:
        interest_rate = float(str(interest_rate_raw).replace("%", "").strip())
    except:
        interest_rate = None

    dscr = extract_dscr_value(find_nested(data, [
        "underwriting_and_financial_information.uw_ncf_dscr",
        "underwriting_financial_info.uw_dscr_based_on_noi_ncf",
        "cash_flow_analysis.uw.ncf_dscr",
        "cash_flow_analysis.ttm_09302019.ncf_dscr",
        "mortgaged_property_information.dscr_based_on_underwritten_noi_ncf",
        "financial_information.uw_ncf_dscr.whole_loan",
        "financial_information.whole_loan.uw_dscr.ncf",
        "financial_information.uw_ncf_dscr"
    ]))

    debt_yield = extract_debt_yield_value(find_nested(data, [
        "underwriting_and_financial_information.uw_noi_debt_yield",
        "underwriting_financial_info.uw_debt_yield_based_on_noi_ncf",
        "cash_flow_analysis.uw.ncf_debt_yield",
        "cash_flow_analysis.ttm_09302019.ncf_debt_yield",
        "financial_information.uw_noi_debt_yield",
        "financial_information.uw_noi_debt_yield_percent.whole_loan",
        "financial_information.uw_debt_yield_percent.whole_loan",
        "financial_information.whole_loan.uw_debt_yield.cut_off.ncf",
        "financial_information.uw_ncf_debt_yield",
        "mortgaged_property_information.debt_yield_based_on_underwritten_noi_ncf"
    ]))

    ltv = extract_numeric(find_nested(data, [
        "underwriting_financial_info.cut_off_date_ltv_ratio",
        "mortgaged_property_information.cut_off_date_ltv_ratio",
        "financial_information.cut_off_date_ltv_percent.whole_loan",
        "financial_information.cut_off_date_ltv",
        "underwriting_and_financial_information.ltv_ratios.cut_off_date",
        "financial_information.whole_loan.ltv.cut_off",
        "loan_summary.cut_off_ltv"
    ]))

    maturity_ltv = extract_numeric(find_nested(data, [
        "underwriting_financial_info.ltv_ratio_at_maturity",
        "underwriting_financial_information.ltv_ratios.maturity_date",
        "underwriting_and_financial_information.ltv_ratios.maturity_date",
        "financial_information.maturity_date_ltv",
        "mortgaged_property_information.maturity_date_ltv_ratio",
        "financial_information.maturity_date_ltv_percent.whole_loan",
        "financial_information.whole_loan.ltv.balloon"
    ]))

    occupancy = extract_numeric(find_nested(data, [
        "property_information.occupancy",
        "mortgaged_property_info.current_occupancy_as_of",
        "mortgaged_property_information.current_occupancy_as_of",
        "mortgaged_property_information.total_occupancy_as_of_12_30_2020",
        "occupancy_history.2023.current",
        "underwriting_and_financial_information.occupancy_history.0.occupancy",
        "historical_occupancy.most_recent.percent",
        "financial_information.occupancy",
        "property_information.occupancy_percent",
        "property_information.occupancy_rate"
    ]))

    location = strip_zip(find_nested(data, [
        "property_information.location",
        "mortgaged_property_info.location",
        "mortgaged_property_information.location",
        "location"
    ]))

    sqft = find_nested(data, [
        "property_information.size_sqft",
        "property_information.total_sq_ft",
        "mortgaged_property_info.size",
        "mortgaged_property_information.size_sqft",
        "mortgaged_property_information.size",
        "property_information.net_rentable_area_sf"
    ])
    sqft = extract_numeric(sqft)

    maturity_date = find_nested(data, [
        "maturity_date", "loan_summary.maturity_date", "mortgage_loan_information.maturity_date"
    ])

    issuer_map = {
    "GACC": "Goldman Sachs",
    "MSMCH": "Morgan Stanley Mortgage Capital Holdings",
    "GSMC": "Goldman Sachs Mortgage Company",
    "JPMCB": "J.P. Morgan Chase Bank"
    
}

    issuer_raw = find_nested(data, [
    "issuer",
    "loan_summary.issuer",
    "deal.issuer",
    "collateral.issuer",
    "offering.issuer",
    "mortgage_loan_information.loan_seller",
    "mortgage_loan_information.mortgage_loan_seller",
    "loan_seller"
])

    issuer = issuer_map.get(issuer_raw, issuer_raw) if issuer_raw else ""




    loan_term = compute_loan_term(data)

    records.append({
        "Loan ID": loan_id,
        "Deal Name": deal_name,
        "Purpose": purpose,
        "Issuer": issuer,
        "Borrower": borrower,
        "Top Tenant": tenant,
        "Tenant Credit Rating": tenant_rating,
        "Original Balance": fmt_currency(original_balance),
        "Interest Rate": fmt_percent(interest_rate),
        "DSCR": fmt_number(dscr),
        "Debt Yield": fmt_percent(debt_yield),
        "Cut-off LTV": fmt_percent(ltv),
        "Maturity LTV": fmt_percent(maturity_ltv),
        "Occupancy Rate": fmt_percent(occupancy),
        "Location": location,
        "SQFT": f"{int(sqft):,}" if pd.notna(sqft) else "",
        "Loan Term": loan_term,
        "Maturity Date": fmt_date(maturity_date),
    })

df = pd.DataFrame(records)

# ------------------ UI Tabs ------------------

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📋 Loan Summary Table",
    "📄 N1967 Loan",
    "📄 N2405 Loan",
    "📄 N2450 Loan",
    "📄 N2711 Loan",
    "📄 N3021 Loan",
    "📄 N3791 Loan"
])

with tab1:
    st.title("📋 Loan Summary Table")

    st.markdown("""
    <style>
    .custom-table-container {
        overflow-x: auto;
        margin-top: 20px;
        margin-bottom: 40px;
    }
    .custom-table {
        width: 100%;
        border-collapse: collapse;
        font-family: Arial, sans-serif;
        font-size: 15px;
    }
    .custom-table th {
        background-color: #1F3B57;
        color: white;
        padding: 12px;
        text-align: center;
        border: 1px solid #ddd;
        font-weight: bold;
    }
    .custom-table td {
        padding: 10px 12px;
        border: 1px solid #ddd;
        text-align: center;
        vertical-align: middle;
    }
    .custom-table tr:nth-child(even) {
        background-color: #f9f9f9;
    }
    .custom-table tr:hover {
        background-color: #f1f1f1;
    }
    .custom-table td:first-child, .custom-table th:first-child {
        text-align: left;
    }
    </style>
    """, unsafe_allow_html=True)

    # Convert the DataFrame to HTML
    def render_html_table(df):
        return f"""
        <div class="custom-table-container">
            {df.to_html(classes="custom-table", index=False, escape=False)}
        </div>
        """

    st.markdown(render_html_table(df), unsafe_allow_html=True)


with tab2:
    st.title("📄N1967 Loan")

    html_summary = """
    <style>
    table {
        width: 100%;
        border-collapse: collapse;
        font-family: Arial, sans-serif;
        margin-bottom: 40px;
    }
    td {
        padding: 14px 16px;
        border: 1px solid #ddd;
        vertical-align: top;
        line-height: 1.7;
    }
    td:first-child {
    background-color: #2C3E50;
    color: white;
    font-weight: bold;
    padding: 10px 12px;
    white-space: nowrap;
    border-right: 2px solid white;
    width: 1%; /* 💥 forces fit-to-content */
    }

    h3 {
        margin-top: 40px;
        margin-bottom: 12px;
        color: #1F3B57;
        font-family: Arial, sans-serif;
    }
    </style>

    <!-- LOAN SUMMARY -->
    <h3>📄 Loan Information</h3>
    <table>
        <tr><td>Deal Name</td><td>Series 2020-BNK25</td></tr>
        <tr><td>Loan ID</td><td>n1967-x4</td></tr>
        <tr><td>Loan Seller</td><td>Bank of America, National Association</td></tr>
        <tr><td>Borrower Sponsor</td><td>BREIT Operating Partnership L.P.</td></tr>
        <tr><td>Guarantor</td><td>BREIT Operating Partnership L.P.</td></tr>
        <tr><td>Loan Purpose</td><td>Acquisition</td></tr>
        <tr><td>Loan Term</td><td>10 years</td></tr>
        <tr><td>Amortization Type</td><td>Interest-only, Balloon</td></tr>
        <tr><td>Interest Rate</td><td>3.2678%</td></tr>
        <tr><td>Original Balance</td><td>$48,900,000</td></tr>
        <tr><td>Maturity Date</td><td>January 6, 2030</td></tr>
        <tr><td>IO Period</td><td>10 years</td></tr>
        <tr><td>Call Protection</td><td>GRTR 0.5% or YM(25), GRTR 0.5% or YM or D(89), O(6)</td></tr>
        <tr><td>Lockbox Type</td><td>Hard/Springing Cash Management</td></tr>
        <tr><td>Additional Debt</td><td>None</td></tr>
    </table>

    <!-- PROPERTY -->
    <h3>🏢 Property Information</h3>
    <table>
        <tr><td>Type</td><td>Other – Data Center</td></tr>
        <tr><td>Location</td><td>Sterling, VA</td></tr>
        <tr><td>Size</td><td>271,160 SF</td></tr>
        <tr><td>Occupancy (2/1/2020)</td><td>100.0%</td></tr>
        <tr><td>Year Built / Renovated</td><td>2016 / NAP</td></tr>
        <tr><td>Title Vesting</td><td>Fee</td></tr>
        <tr><td>Property Manager</td><td>Self-managed</td></tr>
        <tr><td>Appraised Value</td><td>$81,000,000</td></tr>
        <tr><td>Appraised Value/SF</td><td>$272.58</td></tr>
        <tr><td>Appraisal Date</td><td>November 20, 2019</td></tr>
    </table>

    <!-- UNDERWRITING -->
    <!-- SECTION: Underwriting Financial Info -->
    <h3>📊 Underwriting Financial Information</h3>
    <table>
     <tr><td>TTM NOI (9/30/2019)</td><td>$3,865,694</td></tr>
    <tr><td>UW Revenues</td><td>$5,240,380</td></tr>
     <tr><td>UW Expenses</td><td>$588,137</td></tr>
    <tr><td>UW NCF</td><td>$4,815,024</td></tr>
    <tr><td>UW DSCR (NOI)</td><td>2.85x</td></tr>
     <tr><td>UW DSCR (NCF)</td><td>2.73x</td></tr>
    <tr><td>UW Debt Yield (NOI)</td><td>9.4%</td></tr>
    <tr><td>UW Debt Yield (NCF)</td><td>9.0%</td></tr>
    <tr><td>Debt Yield at Maturity (NOI)</td><td>9.4%</td></tr>
    <tr><td>Debt Yield at Maturity (NCF)</td><td>9.0%</td></tr>
    <tr><td>Cut-off LTV</td><td>60.4%</td></tr>
    <tr><td>Maturity LTV</td><td>60.4%</td></tr>
    </table>


    <!-- ESCROWS -->
    <h3>💼 Escrows & Reserves</h3>
    <table>
        <tr><td>Taxes (Initial)</td><td>$0</td></tr>
        <tr><td>Taxes (Monthly)</td><td>Springing</td></tr>
        <tr><td>Insurance (Initial)</td><td>$0</td></tr>
        <tr><td>Insurance (Monthly)</td><td>Springing</td></tr>
        <tr><td>Cap</td><td>N/A</td></tr>
    </table>

    <!-- SOURCES & USES -->
    <h3>💵 Sources & Uses</h3>
    <table>
        <tr><td>Loan Amount</td><td>$48,900,000 (62.8%)</td></tr>
        <tr><td>Borrower Equity</td><td>$28,991,897 (37.2%)</td></tr>
        <tr><td>Total Sources</td><td>$77,891,897</td></tr>
        <tr><td>Purchase Price</td><td>$76,927,388</td></tr>
        <tr><td>Closing Costs</td><td>$960,509</td></tr>
        <tr><td>Total Uses</td><td>$77,891,897</td></tr>
    </table>

    <!-- TENANTS -->
    <h3>🧾 Major Tenants</h3>
    <table>
        <tr><td>Tenant 1</td><td>Vadata, Inc. (DC-21)</td></tr>
        <tr><td>Credit Rating</td><td>Fitch: AA / Moody’s: A3 / S&P: AA-</td></tr>
        <tr><td>Rent PSF</td><td>$14.42</td></tr>
        <tr><td>Annual Rent</td><td>$2,142,123</td></tr>
        <tr><td>Tenant 2</td><td>Vadata, Inc. (DC-22)</td></tr>
        <tr><td>Credit Rating</td><td>Fitch: A+ / Moody’s: A3 / S&P: AA-</td></tr>
        <tr><td>Rent PSF</td><td>$14.63</td></tr>
        <tr><td>Annual Rent</td><td>$2,173,719</td></tr>
        <tr><td>Total Rent</td><td>$4,315,842</td></tr>
        <tr><td>Avg Rent PSF</td><td>$14.52</td></tr>
    </table>

    <!-- LEASE EXPIRATION -->
    <h3>📆 Lease Expiration Schedule</h3>
    <table>
      <tr>
        <td class="label">Year</td>
        <td>Number of Leases</td>
        <td>SF Rolling</td>
        <td>% of NRA</td>
        <td>Rent PSF</td>
        <td>Total Rent Rolling</td>
        <td>% of Total Rent</td>
      </tr>
      <tr>
        <td>2029</td>
        <td>2</td>
        <td>297,160</td>
        <td>100.0%</td>
        <td>$14.52</td>
        <td>$4,315,842</td>
        <td>100.0%</td>
      </tr>
    </table>


    <!-- OCCUPANCY -->
    <h3>📉 Historical Occupancy</h3>
    <table>
        <tr><td>2015</td><td>NAV</td></tr>
        <tr><td>2016</td><td>NAV</td></tr>
        <tr><td>2017</td><td>NAV</td></tr>
        <tr><td>2018</td><td>100%</td></tr>
        <tr><td>2020</td><td>100%</td></tr>
        <tr><td>Notes</td><td>Built in 2016; leases began Oct–Nov 2017</td></tr>
    </table>

    <!-- CASH FLOW -->
    <h3>📊 Cash Flow Analysis</h3>
    <table>
      <tr>
        <td class="label">Metric</td>
        <td>2020</td>
        <td>2021</td>
        <td>2022</td>
        <td>TTM (6/30/2023)</td>
        <td>Underwritten</td>
      </tr>
      <tr>
        <td>Gross Potential Rent</td>
        <td>$80,020,378</td>
        <td>$81,473,151</td>
        <td>$79,777,070</td>
        <td>$80,757,027</td>
        <td>$126,042,403</td>
      </tr>
      <tr>
        <td>Other Income</td>
        <td>$22,431,718</td>
        <td>$29,816,289</td>
        <td>$36,206,142</td>
        <td>$37,551,734</td>
        <td>$31,900,000</td>
      </tr>
      <tr>
        <td>Total Reimbursements</td>
        <td>$8,869,569</td>
        <td>$7,503,851</td>
        <td>$6,687,304</td>
        <td>$7,800,073</td>
        <td>$6,405,196</td>
      </tr>
      <tr>
        <td>Effective Gross Income</td>
        <td>$111,351,756</td>
        <td>$118,744,290</td>
        <td>$112,940,516</td>
        <td>$124,308,174</td>
        <td>$120,188,204</td>
      </tr>
      <tr>
        <td>Total Operating Expenses</td>
        <td>$43,807,455</td>
        <td>$24,128,540</td>
        <td>$27,094,174</td>
        <td>$30,675,994</td>
        <td>$52,681,331</td>
      </tr>
      <tr>
        <td>Net Operating Income (NOI)</td>
        <td>$67,543,911</td>
        <td>$77,460,400</td>
        <td>$65,651,820</td>
        <td>$73,525,984</td>
        <td>$57,833,753</td>
      </tr>
      <tr>
        <td>Capital Expenditures</td>
        <td>$0</td>
        <td>$0</td>
        <td>$0</td>
        <td>$0</td>
        <td>$229,924</td>
      </tr>
      <tr>
        <td>TI/LC</td>
        <td>$0</td>
        <td>$0</td>
        <td>$0</td>
        <td>$0</td>
        <td>$2,110,526</td>
      </tr>
      <tr>
        <td>Net Cash Flow (NCF)</td>
        <td>$67,543,911</td>
        <td>$77,460,400</td>
        <td>$65,651,820</td>
        <td>$73,525,984</td>
        <td>$65,493,494</td>
      </tr>
    </table>


    <!-- SALES COMPARABLES -->
    <h3>🏢 Sales Comparables</h3>
    <table>
        <tr><td>Powered Shell (Sterling, VA)</td><td>$76,927,388 • $272.58/SF</td></tr>
        <tr><td>Chandler, AZ</td><td>$72,750,000 • $380.77/SF</td></tr>
        <tr><td>SunGuard (Hopkins, MN)</td><td>$4,750,000 • $160.15/SF</td></tr>
        <tr><td>Confidential East Coast</td><td>$256,000,000 • $218.02/SF</td></tr>
        <tr><td>Amazon AWS (Hayward, CA)</td><td>$34,975,000 • $239.80/SF</td></tr>
        <tr><td>Secure Data 365 (OH)</td><td>$9,425,000 • $134.59/SF</td></tr>
        <tr><td>AT&T Data Center (San Jose)</td><td>$49,000,000 • $641.28/SF</td></tr>
        <tr><td>Powered Shell (Albany, NY)</td><td>$9,200,000 • $126.03/SF</td></tr>
        <tr><td>Skybox Legacy (Plano, TX)</td><td>$55,000,000 • $368.63/SF</td></tr>
        <tr><td>Pathfinder Plaza</td><td>$111,577,310 • $249.72/SF</td></tr>
        <tr><td>InfoCrossing (Omaha, NE)</td><td>$16,400,000 • $192.49/SF</td></tr>
    </table>

    <h3>🏢 Appraisal Summary</h3>
    <table>
      <tr>
        <td class="label">Appraised Value</td>
        <td>$1,596,000,000</td>
      </tr>
      <tr>
        <td class="label">Appraised Value per SF</td>
        <td>$1,388</td>
      </tr>
      <tr>
        <td class="label">Appraisal Date</td>
        <td>May 8, 2023</td>
      </tr>
    </table>

    <h3>🧾 Loan Combination Summary</h3>
    <table>
      <tr>
        <td class="label">Total Whole Loan Balance</td>
        <td>$280,000,000</td>
      </tr>
      <tr>
        <td class="label">Note A-1 Balance</td>
        <td>$50,000,000</td>
      </tr>
      <tr>
        <td class="label">Note A-2 Balance</td>
        <td>$50,000,000</td>
      </tr>
      <tr>
        <td class="label">Note A-3 Balance</td>
        <td>$40,000,000</td>
      </tr>
      <tr>
        <td class="label">Note A-4 Balance</td>
        <td>$30,000,000</td>
      </tr>
      <tr>
        <td class="label">Note A-5 Balance</td>
        <td>$30,000,000</td>
      </tr>
      <tr>
        <td class="label">Note A-6 Balance</td>
        <td>$20,000,000</td>
      </tr>
      <tr>
        <td class="label">Note A-7 Balance</td>
        <td>$20,000,000</td>
      </tr>
      <tr>
        <td class="label">Note A-8 Balance</td>
        <td>$10,000,000</td>
      </tr>
      <tr>
        <td class="label">Note A-9 Balance</td>
        <td>$10,000,000</td>
      </tr>
      <tr>
        <td class="label">Note A-10 Balance</td>
        <td>$10,000,000</td>
      </tr>
      <tr>
        <td class="label">Controlling Class</td>
        <td>MSBNA (Note A-1)</td>
      </tr>
      <tr>
        <td class="label">Pari Passu / Participation</td>
        <td>Yes – Notes A-1 through A-10</td>
      </tr>
      <tr>
        <td class="label">Co-Lender Agreement</td>
        <td>Implied via Pari Passu Structure</td>
      </tr>
    </table>



    """

    st.markdown(html_summary, unsafe_allow_html=True)

with tab3:
    st.title("📄 N2405 Loan")

    html_n2405 = """
    <style>
    table {
        width: 100%;
        border-collapse: collapse;
        font-family: Arial, sans-serif;
        margin-bottom: 40px;
    }
    td {
        padding: 10px 14px;
        border: 1px solid #ddd;
        vertical-align: top;
        line-height: 1.6;
    }
    td:first-child {
        background-color: #2C3E50;
        color: white;
        font-weight: bold;
        padding: 10px 14px;
        white-space: nowrap;
        border-right: 2px solid white;
        width: 1%;
    }
    h3 {
        margin-top: 36px;
        margin-bottom: 10px;
        color: #1F3B57;
        font-family: Arial, sans-serif;
    }
    </style>

    <h3>📄 Loan Information</h3>
    <table>
      <tr><td>Deal Name</td><td>BENCHMARK 2021-B23</td></tr>
      <tr><td>Loan ID</td><td>n2405-x1</td></tr>
      <tr><td>Loan Seller</td><td>GACC</td></tr>
      <tr><td>Borrower Sponsor</td><td>John R. Wither</td></tr>
      <tr><td>Loan Purpose</td><td>Acquisition</td></tr>
      <tr><td>Loan Term</td><td>10 years</td></tr>
      <tr><td>Amortization Term</td><td>30 years</td></tr>
      <tr><td>Interest-Only Period</td><td>5 years</td></tr>
      <tr><td>Amortization Type</td><td>Interest-only followed by amortizing</td></tr>
      <tr><td>Interest Rate</td><td>2.786025%</td></tr>
      <tr><td>Original Balance</td><td>$104,726,660</td></tr>
      <tr><td>Principal Balance per SF</td><td>$584.16</td></tr>
      <tr><td>Percentage of Initial Pool</td><td>6.8%</td></tr>
      <tr><td>Number of Properties</td><td>1</td></tr>
      <tr><td>Number of Related Loans</td><td>One</td></tr>
      <tr><td>Type of Security</td><td>Fee Simple</td></tr>
      <tr><td>First Payment Date</td><td>February 6, 2021</td></tr>
      <tr><td>Maturity Date</td><td>January 6, 2031</td></tr>
    </table>
    <h3>🏢 Property Information</h3>
    <table>
        <tr><td>Type</td><td>Office / Data Center</td></tr>
        <tr><td>Location</td><td>San Francisco, California</td></tr>
        <tr><td>Size</td><td>179,277 SF</td></tr>
        <tr><td>Occupancy (12/30/2020)</td><td>100.0%</td></tr>
        <tr><td>Year Built / Renovated</td><td>1924 / 2000</td></tr>
        <tr><td>Appraised Value</td><td>$260,000,000</td></tr>
        <tr><td>Appraisal Date</td><td>May 1, 2022</td></tr>
        <tr><td>Property Manager</td><td>Harvest Properties Inc.</td></tr>
    </table>

    <h3>📊 Underwriting Financial Information</h3>
    <table>
        <tr><td>Underwritten Revenues</td><td>$18,490,906</td></tr>
        <tr><td>Underwritten Expenses</td><td>$4,757,608</td></tr>
        <tr><td>Underwritten NOI</td><td>$13,773,298</td></tr>
        <tr><td>Underwritten NCF</td><td>$13,464,326</td></tr>
        <tr><td>UW DSCR (NOI)</td><td>2.18x</td></tr>
        <tr><td>UW DSCR (NCF)</td><td>2.13x</td></tr>
        <tr><td>UW Debt Yield (NOI)</td><td>13.1%</td></tr>
        <tr><td>UW Debt Yield (NCF)</td><td>12.9%</td></tr>
        <tr><td>Cut-off LTV</td><td>40.3%</td></tr>
        <tr><td>Maturity LTV</td><td>33.4%</td></tr>
    </table>

    <h3>💼 Escrows & Reserves</h3>
    <table>
        <tr><td>Taxes (Upfront)</td><td>$382,011</td></tr>
        <tr><td>Taxes (Monthly)</td><td>$95,503</td></tr>
        <tr><td>Insurance (Upfront)</td><td>$0</td></tr>
        <tr><td>Insurance (Monthly)</td><td>$0</td></tr>
        <tr><td>Replacement Reserves (Upfront)</td><td>$0</td></tr>
        <tr><td>Replacement Reserves (Monthly)</td><td>$3,735</td></tr>
        <tr><td>TI/LC Reserves (Upfront)</td><td>$0</td></tr>
        <tr><td>TI/LC Reserves (Monthly)</td><td>$18,675</td></tr>
        <tr><td>Other Reserves (Upfront)</td><td>$23,354,784</td></tr>
        <tr><td>Other Reserves (Monthly)</td><td>$0</td></tr>
    </table>

    <h3>💵 Sources & Uses</h3>
    <table>
        <tr><td>Senior Loan Amount</td><td>$105,000,000 (54.8%)</td></tr>
        <tr><td>Subordinate Loan Amount</td><td>$55,000,000 (28.7%)</td></tr>
        <tr><td>Mezzanine Loan Amount</td><td>$25,000,000 (13.1%)</td></tr>
        <tr><td>Sponsor Equity</td><td>$6,447,299 (3.4%)</td></tr>
        <tr><td>Total Sources</td><td>$191,447,299 (100.0%)</td></tr>
        <tr><td>Purchase Price</td><td>$165,468,922 (86.4%)</td></tr>
        <tr><td>Reserves</td><td>$23,736,795 (12.4%)</td></tr>
        <tr><td>Origination Costs</td><td>$2,241,582 (1.2%)</td></tr>
        <tr><td>Total Uses</td><td>$191,447,299 (100.0%)</td></tr>
    </table>

    <h3>🧾 Major Tenants</h3>
    <table>
        <tr><td>Tenant Name</td><td>Verizon</td><td>Antic</td><td>Vitalant</td><td>T&amp;T</td></tr>
        <tr><td>Credit Rating</td><td>A- / Baa1 / BBB</td><td>NR / NR / NR</td><td>NR / NR / NR</td><td>A- / Baa2 / BBB</td></tr>
        <tr><td>GLA (SF)</td><td>89,237</td><td>39,786</td><td>33,137</td><td>16,837</td></tr>
        <tr><td>% of Total GLA</td><td>49.8%</td><td>22.2%</td><td>18.6%</td><td>9.4%</td></tr>
        <tr><td>Annual UW Base Rent</td><td>$7,504,909</td><td>$3,797,670</td><td>$2,498,775</td><td>$1,213,367</td></tr>
        <tr><td>% of Total Rent</td><td>50.0%</td><td>25.2%</td><td>16.7%</td><td>8.1%</td></tr>
        <tr><td>Rent PSF</td><td>$84.10</td><td>$95.00</td><td>$75.00</td><td>$71.64</td></tr>
        <tr><td>Lease Expiration</td><td>12/31/2040</td><td>5/31/2028</td><td>5/31/2030</td><td>12/31/2026</td></tr>
        <tr><td>Extension Options</td><td>Various</td><td>1, 5-year option</td><td>2, 5-year options</td><td>None</td></tr>
    </table>

    <table>
        <h3>🗓️ Lease Expiration Schedule</h3>
        <tr><td>Year</td><td>2025</td><td>2028</td><td>2030</td><td>2032+</td></tr>
        <tr><td>Expiring GLA (SF)</td><td>16,937</td><td>39,786</td><td>33,317</td><td>89,237</td></tr>
        <tr><td>% of Owned GLA</td><td>9.4%</td><td>22.2%</td><td>18.6%</td><td>49.8%</td></tr>
        <tr><td>Cumulative % of GLA</td><td>9.4%</td><td>31.6%</td><td>50.2%</td><td>100.0%</td></tr>
        <tr><td>Annual Rent</td><td>$1,213,367</td><td>$3,779,670</td><td>$2,498,775</td><td>$7,504,909</td></tr>
        <tr><td>% of Total Rent</td><td>8.1%</td><td>25.2%</td><td>16.7%</td><td>50.0%</td></tr>
        <tr><td>Rent PSF</td><td>$71.64</td><td>$95.00</td><td>$75.00</td><td>$84.10</td></tr>
    </table>

    <h3>📉 Historical Occupancy</h3>
    <table>
        <tr><td>2017</td><td>69.9%</td></tr>
        <tr><td>2018</td><td>71.3%</td></tr>
        <tr><td>2019</td><td>54.3%</td></tr>
        <tr><td>2020 (as of 12/30)</td><td>100.0%</td></tr>
    </table>

        
    <table>
        <h3>📈 Cash Flow Analysis</h3>
        <tr><td></td><td>2019</td><td>TTM (10/31/2020)</td><td>Underwritten</td><td>UW PSF</td></tr>
        <tr><td>Base Rent</td><td>$3,766,448</td><td>$3,860,517</td><td>$14,996,721</td><td>$83.65</td></tr>
        <tr><td>Rent Steps</td><td>$0</td><td>$0</td><td>$1,353,802</td><td>$7.44</td></tr>
        <tr><td>Reimbursements</td><td>$165,588</td><td>$248,643</td><td>$3,119,278</td><td>$17.40</td></tr>
        <tr><td>Other Income</td><td>($24,037)</td><td>$164,444</td><td>$24,060</td><td>$0.13</td></tr>
        <tr><td>Gross Revenue</td><td>$3,907,979</td><td>$4,273,604</td><td>$19,474,000</td><td>$108.74</td></tr>
        <tr><td>Vacancy Loss</td><td>$0</td><td>$0</td><td>($482,888)</td><td>($2.69)</td></tr>
        <tr><td>Effective Gross Revenue</td><td>$3,907,979</td><td>$4,273,604</td><td>$18,990,000</td><td>$106.04</td></tr>
        <tr><td>Real Estate Taxes</td><td>$1,352,711</td><td>$1,389,391</td><td>$2,421,892</td><td>$13.51</td></tr>
        <tr><td>Insurance</td><td>$48,489</td><td>$144,499</td><td>$612,000</td><td>$3.41</td></tr>
        <tr><td>Management Fee</td><td>$150,000</td><td>$147,803</td><td>$551,727</td><td>$3.08</td></tr>
        <tr><td>Other Operating Expenses</td><td>$669,407</td><td>$648,720</td><td>$2,166,823</td><td>$12.09</td></tr>
        <tr><td>Total Operating Expenses</td><td>$2,189,027</td><td>$2,330,414</td><td>$4,757,608</td><td>$26.54</td></tr>
        <tr><td>Net Operating Income</td><td>$1,709,952</td><td>$1,933,188</td><td>$13,733,298</td><td>$76.60</td></tr>
        <tr><td>Replacement Reserves</td><td>$0</td><td>$0</td><td>$268,916</td><td>$1.50</td></tr>
        <tr><td>Net Cash Flow</td><td>$1,709,952</td><td>$1,933,188</td><td>$13,464,382</td><td>$75.10</td></tr>
        <tr><td>Occupancy</td><td>54.3%</td><td>100.0%</td><td>100.0%</td><td>-</td></tr>
        <tr><td>NOI Debt Yield</td><td>1.6%</td><td>1.8%</td><td>12.9%</td><td>-</td></tr>
        <tr><td>NCF DSCR</td><td>0.27x</td><td>0.31x</td><td>2.13x</td><td>-</td></tr>
    </table>

        
    <table>
    <h3>🏢 Appraisal Summary</h3>
        <tr><td>Appraised Value</td><td>$260,000,000</td></tr>
        <tr><td>Appraisal Date</td><td>May 1, 2022</td></tr>
        <tr><td>Appraisal Basis</td><td>As Stabilized</td></tr>
        <tr><td>As-Is Value</td><td>$236,600,000</td></tr>
        <tr><td>Appraisal-Based LTV at Maturity</td><td>33.4%</td></tr>
        <tr><td>Key Assumptions</td>
            <td>
                <ul style="margin: 0; padding-left: 20px;">
                    <li>All contractual tenant improvement and leasing commission (TI/LC) obligations fulfilled</li>
                    <li>All tenants paying unabated rent</li>
                    <li>Includes Vitalant lease (18.6% of NRA), though not yet commenced</li>
                    <li>Holdback reserve for Vitalant: $8,042,501</li>
                    <li>Upfront reserves include $6,703,964 for gap and free rent</li>
                </ul>
            </td>
        </tr>
    </table>
        
    
    <table>
    <h3>🏢 Comparable Data Center Sales</h3>
    <tr>
        <td><b>Property</b></td>
        <td>Confidential (1914/2001)</td>
        <td>Confidential (1923/Various)</td>
        <td>Confidential (1881/2013)</td>
        <td>Dallas Infomart</td>
        <td>KOMO Plaza</td>
    </tr>
    <tr>
        <td>Location</td>
        <td>Confidential</td>
        <td>Confidential</td>
        <td>Confidential</td>
        <td>Dallas, TX</td>
        <td>Seattle, WA</td>
    </tr>
    <tr>
        <td>Year Built / Renovated</td>
        <td>1914 / 2001</td>
        <td>1923 / Various</td>
        <td>1881 / 2013</td>
        <td>1985 / Various</td>
        <td>2000 / 2007</td>
    </tr>
    <tr>
        <td>Transaction Date</td>
        <td>Dec-20</td>
        <td>Apr-20</td>
        <td>Jan-20</td>
        <td>Feb-18</td>
        <td>Dec-16</td>
    </tr>
    <tr>
        <td>Rentable Area (SF)</td>
        <td>300,000</td>
        <td>110,000</td>
        <td>400,000</td>
        <td>1,600,000</td>
        <td>297,327</td>
    </tr>
    <tr>
        <td>Occupancy</td>
        <td>72%</td>
        <td>94%</td>
        <td>90%</td>
        <td>90%</td>
        <td>91%</td>
    </tr>
    <tr>
        <td>Sales Price</td>
        <td>$360,000,000</td>
        <td>$100,000,000</td>
        <td>$750,000,000</td>
        <td>$800,000,000</td>
        <td>$276,000,000</td>
    </tr>
    <tr>
        <td>Price PSF</td>
        <td>$1,200</td>
        <td>$909</td>
        <td>$1,875</td>
        <td>$500</td>
        <td>$928</td>
    </tr>
    </table>

         
    <table>
        <h3>🧾 Loan Combination Summary</h3>
        <tr>
            <td><b>Note</b></td>
            <td><b>Original Balance</b></td>
            <td><b>Cut-off Balance</b></td>
            <td><b>Note Holder</b></td>
            <td><b>Controlling Piece</b></td>
        </tr>
        <tr>
            <td>A-1</td>
            <td>$75,000,000</td>
            <td>$74,804,757</td>
            <td>Benchmark 2021-B23</td>
            <td>No</td>
        </tr>
        <tr>
            <td>A-2</td>
            <td>$25,000,000</td>
            <td>$24,934,919</td>
            <td>Benchmark 2021-B23</td>
            <td>No</td>
        </tr>
        <tr>
            <td>A-3</td>
            <td>$5,000,000</td>
            <td>$4,986,984</td>
            <td>Benchmark 2021-B23</td>
            <td>No</td>
        </tr>
        <tr>
            <td><b>Total Senior Notes</b></td>
            <td>$105,000,000</td>
            <td>$104,726,660</td>
            <td>Benchmark 2021-B23 Loan Specific Certificates</td>
            <td><b>Yes</b></td>
        </tr>
        <tr>
            <td><b>Total Loan</b></td>
            <td>$160,000,000</td>
            <td>$159,725,832</td>
            <td colspan="2">—</td>
        </tr>
    </table>

    """
    st.markdown(html_n2405, unsafe_allow_html=True)



with tab4:
    st.title("📄 N2450 Loan")

    html_n2450 = """
    <table>
    <h3>📄 Loan Information</h3>
        <tr><td>Deal Name</td><td>BENCHMARK 2021-B24</td></tr>
        <tr><td>Loan ID</td><td>n2450-x2</td></tr>
        <tr><td>File Name</td><td>n2450-x2_prets.png</td></tr>
        <tr><td>Mortgage Loan Seller</td><td>JPMCB</td></tr>
        <tr><td>Original Principal Balance</td><td>$66,000,000</td></tr>
        <tr><td>Cut-Off Date Principal Balance</td><td>$66,000,000</td></tr>
        <tr><td>Percent of Pool by IPB</td><td>5.7%</td></tr>
        <tr><td>Loan Purpose</td><td>Acquisition</td></tr>
        <tr><td>Borrower</td><td>1547 CSR - Pittock Block, LLC</td></tr>
        <tr><td>Loan Sponsor</td><td>1547 Data Center Real Estate Fund II, L.P.</td></tr>
        <tr><td>Interest Rate</td><td>3.299404%</td></tr>
        <tr><td>Note Date</td><td>December 30, 2020</td></tr>
        <tr><td>Maturity Date</td><td>January 1, 2031</td></tr>
        <tr><td>Interest Only Period</td><td>10 years</td></tr>
        <tr><td>Original Term</td><td>10 years</td></tr>
        <tr><td>Amortization Type</td><td>Interest Only</td></tr>
        <tr><td>Original Amortization</td><td>None</td></tr>
        <tr><td>Call Protection</td><td>L(4), Gtr1YorYM(112), Q(4)</td></tr>
        <tr><td>Lockbox / Cash Management</td><td>Hard / Springing</td></tr>
        <tr><td class="label">Additional Debt – Total</td><td>$97,470,000</td></tr>
        <tr><td class="label">Additional Debt – Type</td><td>Pari Passu / Subordinate</td></tr>

    </table>

    
    <table>
    <h3>🏢 Property Information</h3>
      <tr>
        <td class="label">Top Tenant</td>
        <td>Zayo / Integra Telecom Holdings, Inc</td>
      </tr>
      <tr>
        <td class="label">Single Asset Portfolio</td>
        <td>Yes (Single Asset)</td>
      </tr>
      <tr>
        <td class="label">Title</td>
        <td>Fee</td>
      </tr>
      <tr>
        <td class="label">Property Type / Subtype</td>
        <td>Mixed Use</td>
      </tr>
      <tr>
        <td class="label">Net Rentable Area (SF)</td>
        <td>297,698 SF</td>
      </tr>
      <tr>
        <td class="label">Location</td>
        <td>Portland, OR</td>
      </tr>
      <tr>
        <td class="label">Year Built / Renovated</td>
        <td>1913 / 2001</td>
      </tr>
      <tr>
        <td class="label">Occupancy (%)</td>
        <td>71.4%</td>
      </tr>
      <tr>
        <td class="label">Occupancy Date</td>
        <td>2020-12-21</td>
      </tr>
      <tr>
        <td class="label">Number of Tenants</td>
        <td>51</td>
      </tr>
      <tr>
        <td class="label">UW Economic Occupancy (%)</td>
        <td>72.5%</td>
      </tr>
      <tr>
        <td class="label">UW Revenues</td>
        <td>$18,158,626</td>
      </tr>
      <tr>
        <td class="label">UW Expenses</td>
        <td>$5,574,346</td>
      </tr>
      <tr>
        <td class="label">UW NOI</td>
        <td>$12,584,281</td>
      </tr>
      <tr>
        <td class="label">UW NCF</td>
        <td>$11,780,493</td>
      </tr>
      <tr>
        <td class="label">Appraised Value</td>
        <td>$329,000,000</td>
      </tr>
      <tr>
        <td class="label">Appraised Value per SF</td>
        <td>$1,105</td>
      </tr>
      <tr>
        <td class="label">Appraisal Date</td>
        <td>2020-12-07</td>
      </tr>
    </table>

    
    <table>
    <h3>📊 Underwriting Financial Information</h3>
      <tr>
        <td class="label">Loan Per SF at Cut-Off Date (Senior Notes)</td>
        <td>$474</td>
      </tr>
      <tr>
        <td class="label">Loan Per SF at Cut-Off Date (Whole Loan)</td>
        <td>$549</td>
      </tr>
      <tr>
        <td class="label">Loan Per SF at Maturity Date (Senior Notes)</td>
        <td>$474</td>
      </tr>
      <tr>
        <td class="label">Loan Per SF at Maturity Date (Whole Loan)</td>
        <td>$549</td>
      </tr>
      <tr>
        <td class="label">LTV at Cut-Off Date (Senior Notes)</td>
        <td>42.9%</td>
      </tr>
      <tr>
        <td class="label">LTV at Cut-Off Date (Whole Loan)</td>
        <td>49.7%</td>
      </tr>
      <tr>
        <td class="label">LTV at Maturity Date (Senior Notes)</td>
        <td>42.9%</td>
      </tr>
      <tr>
        <td class="label">LTV at Maturity Date (Whole Loan)</td>
        <td>49.7%</td>
      </tr>
      <tr>
        <td class="label">UW NCF DSCR (Senior Notes)</td>
        <td>2.50x</td>
      </tr>
      <tr>
        <td class="label">UW NCF DSCR (Whole Loan)</td>
        <td>1.95x</td>
      </tr>
      <tr>
        <td class="label">UW NOI Debt Yield (Senior Notes)</td>
        <td>8.9%</td>
      </tr>
      <tr>
        <td class="label">UW NOI Debt Yield (Whole Loan)</td>
        <td>7.7%</td>
      </tr>
    </table>

    <h3>🏦 Escrows & Reserves</h3>
    <table>
      <tr>
        <td class="label">Taxes – Initial</td>
        <td>$0</td>
      </tr>
      <tr>
        <td class="label">Taxes – Monthly</td>
        <td>Springing</td>
      </tr>

      <tr>
        <td class="label">Insurance – Initial</td>
        <td>$0</td>
      </tr>
      <tr>
        <td class="label">Insurance – Monthly</td>
        <td>Springing</td>
      </tr>

      <tr>
        <td class="label">Replacement Reserves – Initial</td>
        <td>$0</td>
      </tr>
      <tr>
        <td class="label">Replacement Reserves – Monthly</td>
        <td>Springing</td>
      </tr>

      <tr>
        <td class="label">TILC – Initial</td>
        <td>$0</td>
      </tr>
      <tr>
        <td class="label">TILC – Monthly</td>
        <td>Springing</td>
      </tr>

      <tr>
        <td class="label">Other – Initial</td>
        <td>$9,012,030</td>
      </tr>
      <tr>
        <td class="label">Other – Monthly</td>
        <td>$0</td>
      </tr>
    </table>

    
    <table>
    <h3>💸 Sources & Uses</h3>
      <tr>
        <td class="label">Source – Senior Notes</td>
        <td>$141,000,000 (41.6%)</td>
      </tr>
      <tr>
        <td class="label">Source – Subordinate Debt Amount</td>
        <td>$22,470,000 (6.6%)</td>
      </tr>
      <tr>
        <td class="label">Source – Principal / New Cash Contribution</td>
        <td>$175,849,656 (51.8%)</td>
      </tr>
      <tr>
        <td class="label">Total Sources</td>
        <td>$339,319,656 (100%)</td>
      </tr>
      <tr>
        <td class="label">Use – Purchase Price</td>
        <td>$326,000,000 (96.1%)</td>
      </tr>
      <tr>
        <td class="label">Use – Holdback / Reserve</td>
        <td>$7,500,000 (2.2%)</td>
      </tr>
      <tr>
        <td class="label">Use – Closing Costs</td>
        <td>$4,507,636 (1.3%)</td>
      </tr>
      <tr>
        <td class="label">Use – Upfront Reserves</td>
        <td>$1,512,030 (0.4%)</td>
      </tr>
      <tr>
        <td class="label">Total Uses</td>
        <td>$339,319,656 (100%)</td>
      </tr>
    </table>

    
    <table>
    <h3>🧑‍💼 Major Tenants</h3>
      <tr>
        <td class="label">Tenant Name</td>
        <td>Zayo / Integra Telecom</td>
        <td>Hennebery Eddy Architects</td>
        <td>LS Networks</td>
        <td>Spectra Symbol</td>
      </tr>
      <tr>
        <td class="label">Credit Rating</td>
        <td>Caa1 / NR / B</td>
        <td>NR / NR / NR</td>
        <td>NR / NR / NR</td>
        <td>NR / NR / NR</td>
      </tr>
      <tr>
        <td class="label">GLA (SF)</td>
        <td>5,616</td>
        <td>16,366</td>
        <td>15,385</td>
        <td>11,136</td>
      </tr>
      <tr>
        <td class="label">% of Total GLA</td>
        <td>2.6%</td>
        <td>7.6%</td>
        <td>7.1%</td>
        <td>5.2%</td>
      </tr>
      <tr>
        <td class="label">Annual UW Base Rent</td>
        <td>$404,434</td>
        <td>$472,285</td>
        <td>$343,597</td>
        <td>$273,832</td>
      </tr>
      <tr>
        <td class="label">% of Total Rent</td>
        <td>9.6%</td>
        <td>8.1%</td>
        <td>8.0%</td>
        <td>4.6%</td>
      </tr>
      <tr>
        <td class="label">Rent PSF</td>
        <td>$72.10</td>
        <td>$28.87</td>
        <td>$22.34</td>
        <td>$24.50</td>
      </tr>
      <tr>
        <td class="label">Lease Expiration</td>
        <td>8/31/2030</td>
        <td>7/31/2027</td>
        <td>7/31/2021</td>
        <td>10/31/2023</td>
      </tr>
      <tr>
        <td class="label">Extension Options</td>
        <td>None</td>
        <td>1-year option</td>
        <td>None</td>
        <td>None</td>
      </tr>
    </table>

    <h3>📆 Lease Expiration Schedule</h3>
    <table>
      <tr>
        <td class="label">Year</td>
        <td>Expiring NRA (SF)</td>
        <td>% of NRA</td>
        <td>Cumulative % of NRA</td>
        <td>Cumulative Base Rent</td>
        <td>Cumulative % of Rent</td>
      </tr>
      <tr>
        <td>2021 & MTM</td>
        <td>48,624</td>
        <td>22.5%</td>
        <td>51.2%</td>
        <td>$1,160,927</td>
        <td>27.1%</td>
      </tr>
      <tr>
        <td>2022</td>
        <td>24,301</td>
        <td>11.3%</td>
        <td>62.4%</td>
        <td>$1,776,133</td>
        <td>40.1%</td>
      </tr>
      <tr>
        <td>2023</td>
        <td>30,575</td>
        <td>14.4%</td>
        <td>76.8%</td>
        <td>$2,573,592</td>
        <td>60.2%</td>
      </tr>
      <tr>
        <td>2024</td>
        <td>553</td>
        <td>0.3%</td>
        <td>77.1%</td>
        <td>$2,588,800</td>
        <td>60.5%</td>
      </tr>
      <tr>
        <td>2025</td>
        <td>17,017</td>
        <td>7.9%</td>
        <td>84.9%</td>
        <td>$3,046,711</td>
        <td>71.2%</td>
      </tr>
      <tr>
        <td>2026</td>
        <td>8,481</td>
        <td>3.9%</td>
        <td>88.9%</td>
        <td>$3,374,471</td>
        <td>78.6%</td>
      </tr>
      <tr>
        <td>2027</td>
        <td>13,222</td>
        <td>6.3%</td>
        <td>95.1%</td>
        <td>$3,737,445</td>
        <td>87.3%</td>
      </tr>
      <tr>
        <td>2028</td>
        <td>0</td>
        <td>0.0%</td>
        <td>95.1%</td>
        <td>$3,737,445</td>
        <td>87.3%</td>
      </tr>
      <tr>
        <td>2029</td>
        <td>2,850</td>
        <td>1.3%</td>
        <td>96.4%</td>
        <td>$3,882,445</td>
        <td>90.8%</td>
      </tr>
      <tr>
        <td>2030</td>
        <td>5,896</td>
        <td>2.6%</td>
        <td>99.1%</td>
        <td>$4,278,732</td>
        <td>100.0%</td>
      </tr>
      <tr>
        <td>2031</td>
        <td>0</td>
        <td>0.0%</td>
        <td>99.1%</td>
        <td>$4,278,732</td>
        <td>100.0%</td>
      </tr>
      <tr>
        <td>2032 and Thereafter</td>
        <td>2,000</td>
        <td>0.9%</td>
        <td>100.0%</td>
        <td>$4,278,732</td>
        <td>100.0%</td>
      </tr>
    </table>

    <h3>🏢 Occupancy History</h3>
    <table>
      <tr>
        <td class="label">2017</td>
        <td>82.8%</td>
      </tr>
      <tr>
        <td class="label">2018</td>
        <td>85.7%</td>
      </tr>
      <tr>
        <td class="label">2019</td>
        <td>88.7%</td>
      </tr>
      <tr>
        <td class="label">Current (as of 2020-12-21)</td>
        <td>71.4%</td>
      </tr>
      <tr>
        <td class="label">Footnote</td>
        <td>Drop in occupancy from 2019 to 2020 primarily due to a ~19,228 SF office tenant vacating in November 2020. Excludes Portland NAP.</td>
      </tr>
    </table>

    <h3>📊 Cash Flow Analysis</h3>
    <table>
      <tr>
        <td class="label">Metric</td>
        <td>2017</td>
        <td>2018</td>
        <td>2019</td>
        <td>TTM (11/30/2020)</td>
        <td>Underwritten (12/21/2020)</td>
      </tr>
      <tr>
        <td class="label">Base Rent</td>
        <td>$3,431,224</td>
        <td>$4,027,867</td>
        <td>$4,359,091</td>
        <td>$4,368,598</td>
        <td>$4,278,732</td>
      </tr>
      <tr>
        <td class="label">Total Reimbursements</td>
        <td>$3,113,064</td>
        <td>$3,963,948</td>
        <td>$4,167,474</td>
        <td>$4,168,598</td>
        <td>$5,431,254</td>
      </tr>
      <tr>
        <td class="label">Colocation Income</td>
        <td>$6,311,688</td>
        <td>$9,622,944</td>
        <td>$9,568,974</td>
        <td>$10,209,580</td>
        <td>$12,215,118</td>
      </tr>
      <tr>
        <td class="label">Cross Connect Income</td>
        <td>$1,833,833</td>
        <td>$2,004,128</td>
        <td>$2,215,568</td>
        <td>$2,328,786</td>
        <td>$2,577,500</td>
      </tr>
      <tr>
        <td class="label">Connection Income</td>
        <td>$477,927</td>
        <td>$328,161</td>
        <td>$396,262</td>
        <td>$1,162,438</td>
        <td>$1,352,950</td>
      </tr>
      <tr>
        <td class="label">Circuit Fee Income</td>
        <td>–</td>
        <td>–</td>
        <td>$91,475</td>
        <td>$151,225</td>
        <td>$95,348</td>
      </tr>
      <tr>
        <td class="label">Vacancy Credit Loss</td>
        <td>–</td>
        <td>–</td>
        <td>–</td>
        <td>($689,809)</td>
        <td>($1,906,512)</td>
      </tr>
      <tr>
        <td class="label">Effective Gross Income</td>
        <td>$13,166,409</td>
        <td>$14,107,319</td>
        <td>$15,557,144</td>
        <td>$16,674,000</td>
        <td>$18,158,626</td>
      </tr>
      <tr>
        <td class="label">Operating Expenses</td>
        <td>$3,543,176</td>
        <td>$5,034,876</td>
        <td>$5,337,239</td>
        <td>$5,651,726</td>
        <td>$5,574,346</td>
      </tr>
      <tr>
        <td class="label">Net Operating Income</td>
        <td>$9,628,702</td>
        <td>$9,072,443</td>
        <td>$10,019,815</td>
        <td>$11,047,438</td>
        <td>$12,584,281</td>
      </tr>
      <tr>
        <td class="label">TILC</td>
        <td>–</td>
        <td>–</td>
        <td>–</td>
        <td>–</td>
        <td>$702,171</td>
      </tr>
      <tr>
        <td class="label">Replacement Reserves</td>
        <td>–</td>
        <td>–</td>
        <td>–</td>
        <td>–</td>
        <td>$100,000</td>
      </tr>
      <tr>
        <td class="label">Net Cash Flow</td>
        <td>$9,628,702</td>
        <td>$9,072,443</td>
        <td>$10,019,815</td>
        <td>$11,047,438</td>
        <td>$11,780,493</td>
      </tr>
    </table>

    <h3>🏢 Appraisal Summary</h3>
    <table>
      <tr>
        <td class="label">Appraised Value</td>
        <td>$329,000,000</td>
      </tr>
      <tr>
        <td class="label">Appraised Value per SF</td>
        <td>$1,105</td>
      </tr>
      <tr>
        <td class="label">Appraisal Date</td>
        <td>December 7, 2020</td>
      </tr>
      <tr>
        <td class="label">Appraisal Source</td>
        <td>Third-party appraisal (included in origination package)</td>
      </tr>
    </table>

    <h3>🏢 Comparable Data Center Sales</h3>
    <table>
      <tr>
        <td class="label">Property</td>
        <td>Pathfinder Plaza</td>
        <td>AT&T Data Center</td>
        <td>Skybox Legacy</td>
        <td>InfoCrossing</td>
        <td>Pittock Block (Subject)</td>
      </tr>
      <tr>
        <td class="label">Location</td>
        <td>Sterling, VA</td>
        <td>San Jose, CA</td>
        <td>Plano, TX</td>
        <td>Omaha, NE</td>
        <td>Portland, OR</td>
      </tr>
      <tr>
        <td class="label">Year Built / Renovated</td>
        <td>2017</td>
        <td>1999</td>
        <td>2017</td>
        <td>1988 / 1995</td>
        <td>1913 / 2001</td>
      </tr>
      <tr>
        <td class="label">Transaction Date</td>
        <td>Mar-18</td>
        <td>Jun-18</td>
        <td>Mar-18</td>
        <td>Mar-18</td>
        <td>N/A</td>
      </tr>
      <tr>
        <td class="label">Rentable Area (SF)</td>
        <td>446,811</td>
        <td>76,410</td>
        <td>149,200</td>
        <td>85,200</td>
        <td>297,698</td>
      </tr>
      <tr>
        <td class="label">Occupancy</td>
        <td>100%</td>
        <td>100%</td>
        <td>100%</td>
        <td>100%</td>
        <td>71.4%</td>
      </tr>
      <tr>
        <td class="label">Sales Price</td>
        <td>$111,577,310</td>
        <td>$49,000,000</td>
        <td>$55,000,000</td>
        <td>$16,400,000</td>
        <td>$329,000,000</td>
      </tr>
      <tr>
        <td class="label">Price PSF</td>
        <td>$249.72</td>
        <td>$641.28</td>
        <td>$368.63</td>
        <td>$192.49</td>
        <td>$1,105</td>
      </tr>
    </table>


    <h3>🧾 Loan Combination Summary</h3>
    <table>
      <tr>
        <td class="label">Note A-1 – Original Balance</td>
        <td>$75,000,000</td>
      </tr>
      <tr>
        <td class="label">Note A-1 – Holder</td>
        <td>Benchmark 2021-B23</td>
      </tr>
      <tr>
        <td class="label">Note A-1 – Controlling Piece</td>
        <td>No</td>
      </tr>

      <tr>
        <td class="label">Note A-2 / A-3 – Original Balance</td>
        <td>$66,000,000</td>
      </tr>
      <tr>
        <td class="label">Note A-2 / A-3 – Holder</td>
        <td>Benchmark 2021-B24</td>
      </tr>
      <tr>
        <td class="label">Note A-2 / A-3 – Controlling Piece</td>
        <td>No</td>
      </tr>

      <tr>
        <td class="label">Note B – Original Balance</td>
        <td>$22,470,000</td>
      </tr>
      <tr>
        <td class="label">Note B – Holder</td>
        <td>Unaffiliated Third-Party Investor</td>
      </tr>
      <tr>
        <td class="label">Note B – Controlling Piece</td>
        <td>Yes*</td>
      </tr>

      <tr>
        <td class="label">Total Senior Notes</td>
        <td>$141,000,000</td>
      </tr>
      <tr>
        <td class="label">Total Whole Loan Balance</td>
        <td>$163,470,000</td>
      </tr>
    </table>

    <p style="font-size: 0.9em; padding-left: 2em;">
      *Per the co-lender agreement, the holder of the Pittock Block Junior Note (Note B) has the right to appoint the special servicer and direct certain decisions unless a control appraisal event occurs. After such event, control shifts to the Note A-1 holder.
    </p>



    """
    st.markdown(html_n2450, unsafe_allow_html=True)  # ✅ Corrected

with tab5:
    st.title("📄 N2711 Loan")

    html_n2711 = """

    <h3>🏦 Loan Information</h3>
    <table>
     <tr>
        <td class="label">Deal Name</td>
        <td>BANK 2021-BNK36</td>
      </tr>
      <tr>
        <td class="label">Loan ID</td>
        <td>n2711_x3</td>
      </tr>
      <tr>
        <td class="label">Loan Seller</td>
        <td>MSMCH</td>
      </tr>
      <tr>
        <td class="label">Original Balance</td>
        <td>$44,500,000</td>
      </tr>
      <tr>
        <td class="label">Cut-Off Balance</td>
        <td>$44,500,000</td>
      </tr>
      <tr>
        <td class="label">% of Initial Pool Balance</td>
        <td>3.5%</td>
      </tr>
      <tr>
        <td class="label">Loan Purpose</td>
        <td>Refinance</td>
      </tr>
      <tr>
        <td class="label">Borrower</td>
        <td>DataCore Fund L.P.</td>
      </tr>
      <tr>
        <td class="label">Guarantor</td>
        <td>DataCore Fund L.P.</td>
      </tr>
      <tr>
        <td class="label">Mortgage Rate</td>
        <td>2.54%</td>
      </tr>
      <tr>
        <td class="label">Note Date</td>
        <td>September 16, 2021</td>
      </tr>
      <tr>
        <td class="label">First Payment Date</td>
        <td>November 1, 2021</td>
      </tr>
      <tr>
        <td class="label">Maturity Date</td>
        <td>October 1, 2031</td>
      </tr>
      <tr>
        <td class="label">Original Term to Maturity</td>
        <td>120 months</td>
      </tr>
      <tr>
        <td class="label">Original Amortization Term</td>
        <td>120 months</td>
      </tr>
      <tr>
        <td class="label">Interest-Only Period</td>
        <td>0 months</td>
      </tr>
      <tr>
        <td class="label">Seasoning</td>
        <td>0 months</td>
      </tr>
      <tr>
        <td class="label">Prepayment Provisions</td>
        <td>L(2/3), Y1(90), Q(7)</td>
      </tr>
      <tr>
        <td class="label">Lockbox / Cash Management</td>
        <td>Hard / Springing</td>
      </tr>
      <tr>
        <td class="label">Additional Debt Type</td>
        <td>NAP</td>
      </tr>
      <tr>
        <td class="label">Additional Debt Balance</td>
        <td>NAP</td>
      </tr>
      <tr>
        <td class="label">Future Debt Permitted</td>
        <td>No (NAP)</td>
      </tr>
      <tr>
        <td class="label">Credit Ratings (Fitch / KBRA / S&P)</td>
        <td>NR / NR / NR</td>
      </tr>
    </table>

    <h3>🏢 Property Information</h3>
    <table>
      <tr>
        <td class="label">Asset Type</td>
        <td>Single Asset</td>
      </tr>
      <tr>
        <td class="label">Location</td>
        <td>Hayward, CA 94545</td>
      </tr>
      <tr>
        <td class="label">General Property Type</td>
        <td>Mixed Use</td>
      </tr>
      <tr>
        <td class="label">Detailed Property Type</td>
        <td>Industrial / Office</td>
      </tr>
      <tr>
        <td class="label">Title / Vesting</td>
        <td>Fee</td>
      </tr>
      <tr>
        <td class="label">Year Built / Renovated</td>
        <td>1974 – 2006 / NAP</td>
      </tr>
      <tr>
        <td class="label">Size (SF)</td>
        <td>293,292 SF</td>
      </tr>
      <tr>
        <td class="label">Cut-Off Balance PSF</td>
        <td>$152</td>
      </tr>
      <tr>
        <td class="label">Maturity Balance PSF</td>
        <td>$152</td>
      </tr>
      <tr>
        <td class="label">Property Manager</td>
        <td>G&E Real Estate Management Services, Inc.</td>
      </tr>
    </table>

    <h3>📊 Underwriting Financial Information</h3>
    <table>
      <tr>
        <td class="label">Underwritten Net Operating Income (NOI)</td>
        <td>$4,933,237</td>
      </tr>
      <tr>
        <td class="label">Underwritten NOI Debt Yield</td>
        <td>11.1%</td>
      </tr>
      <tr>
        <td class="label">Underwritten NOI Debt Yield at Maturity</td>
        <td>11.1%</td>
      </tr>
      <tr>
        <td class="label">Underwritten Net Cash Flow (NCF)</td>
        <td>$4,452,239</td>
      </tr>
      <tr>
        <td class="label">Underwritten NCF DSCR</td>
        <td>3.89x</td>
      </tr>
      <tr>
        <td class="label">Cut-Off Date LTV</td>
        <td>46.8%</td>
      </tr>
      <tr>
        <td class="label">Maturity Date LTV</td>
        <td>46.8%</td>
      </tr>
      <tr>
        <td class="label">Appraised Value</td>
        <td>$95,000,000</td>
      </tr>
      <tr>
        <td class="label">Appraised Value PSF</td>
        <td>$324</td>
      </tr>
      <tr>
        <td class="label">Appraisal Date</td>
        <td>July 13, 2021</td>
      </tr>
    </table>

    
    <table>
      <h3>🏦 Escrows & Reserves</h3>
      <tr>
        <td class="label">Real Estate Taxes – Initial</td>
        <td>$0</td>
      </tr>
      <tr>
        <td class="label">Real Estate Taxes – Monthly</td>
        <td>Springing</td>
      </tr>
      <tr>
        <td class="label">Insurance – Initial</td>
        <td>$0</td>
      </tr>
      <tr>
        <td class="label">Insurance – Monthly</td>
        <td>Springing</td>
      </tr>
    </table>

    <h3>💸 Sources & Uses</h3>
    <table>
      <tr>
        <td class="label">Source – Loan Amount</td>
        <td>$44,500,000 (100.0%)</td>
      </tr>
      <tr>
        <td class="label">Total Sources</td>
        <td>$44,500,000</td>
      </tr>
      <tr>
        <td class="label">Use – Loan Payoff</td>
        <td>$20,216,491 (45.4%)</td>
      </tr>
      <tr>
        <td class="label">Use – Return of Equity</td>
        <td>$17,731,384 (39.8%)</td>
      </tr>
      <tr>
        <td class="label">Use – Closing Costs</td>
        <td>$6,542,135 (14.7%)</td>
      </tr>
      <tr>
        <td class="label">Total Uses</td>
        <td>$44,500,000</td>
      </tr>
    </table>

    <h3>👥 Major Tenants</h3>
    <table>
      <tr>
        <td class="label">Tenant Name</td>
        <td>AT00 US</td>
        <td>Ultra Clean Technology</td>
        <td>Vary Bio LLC</td>
        <td>Delta Information Systems</td>
        <td>Kaeno</td>
      </tr>
      <tr>
        <td class="label">Credit Rating (Fitch / KBRA / S&P)</td>
        <td>AA / A1 / A</td>
        <td>–</td>
        <td>–</td>
        <td>–</td>
        <td>–</td>
      </tr>
      <tr>
        <td class="label">Leased SF</td>
        <td>131,896</td>
        <td>103,771</td>
        <td>26,362</td>
        <td>16,132</td>
        <td>13,132</td>
      </tr>
      <tr>
        <td class="label">% of Total NRA</td>
        <td>45.0%</td>
        <td>35.4%</td>
        <td>9.4%</td>
        <td>5.5%</td>
        <td>4.5%</td>
      </tr>
      <tr>
        <td class="label">Annual UW Base Rent</td>
        <td>$2,502,592</td>
        <td>$1,820,592</td>
        <td>$537,091</td>
        <td>$250,695</td>
        <td>$238,996</td>
      </tr>
      <tr>
        <td class="label">UW Rent PSF</td>
        <td>$18.98</td>
        <td>$17.54</td>
        <td>$17.01</td>
        <td>$15.54</td>
        <td>$18.08</td>
      </tr>
      <tr>
        <td class="label">% of Total Base Rent</td>
        <td>46.3%</td>
        <td>33.7%</td>
        <td>9.9%</td>
        <td>4.6%</td>
        <td>4.4%</td>
      </tr>
      <tr>
        <td class="label">Lease Expiration</td>
        <td>2026-02-28</td>
        <td>2027-12-01</td>
        <td>2025-08-18</td>
        <td>2026-07-13</td>
        <td>2027-05-31</td>
      </tr>
    </table>

    <h3>📆 Lease Expiration Schedule</h3>
    <table>
      <tr>
        <td class="label">Year</td>
        <td>Number of Leases</td>
        <td>SF Rolling</td>
        <td>% of NRA</td>
        <td>Rent PSF</td>
        <td>Total Rent Rolling</td>
        <td>% of Total Rent</td>
      </tr>
      <tr>
        <td>2026</td>
        <td>3</td>
        <td>176,449</td>
        <td>60.2%</td>
        <td>$18.82</td>
        <td>$3,321,454</td>
        <td>61.5%</td>
      </tr>
      <tr>
        <td>2027</td>
        <td>2</td>
        <td>116,843</td>
        <td>39.8%</td>
        <td>$17.80</td>
        <td>$2,079,532</td>
        <td>38.5%</td>
      </tr>
    </table>

    <h3>🏢 Occupancy History</h3>
    <table>
      <tr>
        <td class="label">2019</td>
        <td>85.7%</td>
      </tr>
      <tr>
        <td class="label">2020</td>
        <td>90.1%</td>
      </tr>
      <tr>
        <td class="label">2021</td>
        <td>100.0%</td>
      </tr>
    </table>


    <h3>📊 Cash Flow Analysis</h3>
  <table>
    <tr>
      <td class="label">Metric</td>
      <td>2019</td>
      <td>2020</td>
      <td>TTM (6/30/2021)</td>
      <td>Underwritten</td>
    </tr>
    <tr>
      <td>Gross Potential Rent</td>
      <td>$4,151,525</td>
      <td>$4,503,939</td>
      <td>$4,653,966</td>
      <td>$5,400,986</td>
    </tr>
    <tr>
      <td>Reimbursements</td>
      <td>$1,372,842</td>
      <td>$1,258,333</td>
      <td>$1,454,634</td>
      <td>$1,840,379</td>
    </tr>
    <tr>
      <td>Vacancy/Credit Loss</td>
      <td>$0</td>
      <td>($59,604)</td>
      <td>($86,676)</td>
      <td>($352,068)</td>
    </tr>
    <tr>
      <td>Effective Gross Income</td>
      <td>$5,524,366</td>
      <td>$5,703,179</td>
      <td>$6,021,924</td>
      <td>$6,688,297</td>
    </tr>
    <tr>
      <td>Real Estate Taxes</td>
      <td>$807,342</td>
      <td>$830,273</td>
      <td>$826,197</td>
      <td>$826,197</td>
    </tr>
    <tr>
      <td>Insurance</td>
      <td>$344,223</td>
      <td>$299,343</td>
      <td>$306,544</td>
      <td>$340,000</td>
    </tr>
    <tr>
      <td>Other Operating Expenses</td>
      <td>$466,703</td>
      <td>$522,525</td>
      <td>$533,264</td>
      <td>$589,866</td>
    </tr>
    <tr>
      <td>Total Operating Expenses</td>
      <td>$1,618,268</td>
      <td>$1,652,141</td>
      <td>$1,664,064</td>
      <td>$1,756,062</td>
    </tr>
    <tr>
      <td>Net Operating Income</td>
      <td>$3,906,098</td>
      <td>$4,051,037</td>
      <td>$4,357,418</td>
      <td>$4,933,237</td>
    </tr>
    <tr>
      <td>Capital Expenditures</td>
      <td>$0</td>
      <td>$0</td>
      <td>$0</td>
      <td>$405,998</td>
    </tr>
    <tr>
      <td>TI/LC</td>
      <td>$0</td>
      <td>$0</td>
      <td>$0</td>
      <td>$452,340</td>
    </tr>
    <tr>
      <td>Net Cash Flow</td>
      <td>$3,906,098</td>
      <td>$4,051,037</td>
      <td>$4,357,418</td>
      <td>$4,452,239</td>
    </tr>
  </table>

    <h3>🏢 Appraisal Summary</h3>
  <table>
    <tr>
      <td class="label">Appraised Value</td>
      <td>$95,000,000</td>
    </tr>
    <tr>
      <td class="label">Appraised Value per SF</td>
      <td>$324</td>
    </tr>
    <tr>
      <td class="label">Appraisal Date</td>
      <td>July 13, 2021</td>
    </tr>
  </table>

  <h3>🧾 Loan Combination Summary</h3>
  <table>
    <tr>
      <td class="label">Total Whole Loan Balance</td>
      <td>$44,500,000</td>
    </tr>
    <tr>
      <td class="label">Note Structure</td>
      <td>Single Note (No A/B or Pari Passu)</td>
    </tr>
    <tr>
      <td class="label">Controlling Class</td>
      <td>N/A</td>
    </tr>
    <tr>
      <td class="label">Participation / Pari Passu</td>
      <td>None</td>
    </tr>
    <tr>
      <td class="label">Co-Lender Agreement</td>
      <td>Not Applicable</td>
    </tr>
  </table>


"""

    st.markdown(html_n2711, unsafe_allow_html=True)  # ✅ Corrected

  
with tab6:
    st.title("📄 N3021 Loan")

    html_n3021 = """
     <h3>🏦 Loan Information</h3>
    <table>
    <tr>
        <td class="label">Deal Name</td>
        <td>BENCHMARK 2022-B34</td>
      </tr>
      <tr>
        <td class="label">Loan ID</td>
        <td>n3021-x3</td>
      </tr>
      <tr>
        <td class="label">Loan Seller</td>
        <td>GSMC</td>
      </tr>
      <tr>
        <td class="label">Original Balance</td>
        <td>$85,000,000</td>
      </tr>
      <tr>
        <td class="label">Cut-Off Balance</td>
        <td>$85,000,000</td>
      </tr>
      <tr>
        <td class="label">% of Initial Pool Balance</td>
        <td>9.3%</td>
      </tr>
      <tr>
        <td class="label">Loan Purpose</td>
        <td>Refinance</td>
      </tr>
      <tr>
        <td class="label">Borrower</td>
        <td>GI TC One Wilshire, LLC</td>
      </tr>
      <tr>
        <td class="label">Sponsor</td>
        <td>TechCore, LLC</td>
      </tr>
      <tr>
        <td class="label">Mortgage Rate</td>
        <td>2.7760%</td>
      </tr>
      <tr>
        <td class="label">First Payment Date</td>
        <td>February 6, 2022</td>
      </tr>
      <tr>
        <td class="label">Monthly Payment Date</td>
        <td>6th of each month</td>
      </tr>
      <tr>
        <td class="label">Anticipated Repayment Date (ARD)</td>
        <td>January 6, 2032</td>
      </tr>
      <tr>
        <td class="label">Maturity Date</td>
        <td>January 6, 2035</td>
      </tr>
      <tr>
        <td class="label">Amortization Type</td>
        <td>Interest Only - ARD</td>
      </tr>
      <tr>
        <td class="label">Prepayment Provisions</td>
        <td>L(27), B(6), 0(7)</td>
      </tr>
      <tr>
        <td class="label">Lockbox / Cash Management</td>
        <td>Hard / Springing</td>
      </tr>
      <tr>
        <td class="label">Additional Debt Type</td>
        <td>Pari Passu</td>
      </tr>
      <tr>
        <td class="label">Additional Debt Balance</td>
        <td>$304,250,000</td>
      </tr>
      <tr>
        <td class="label">Credit Ratings (Fitch / DBRS)</td>
        <td>NR / BBB(sf)</td>
      </tr>
    </table>

    <h3>🏢 Property Information</h3>
  <table>
    <tr>
      <td class="label">Asset Type</td>
      <td>Single Asset</td>
    </tr>
    <tr>
      <td class="label">Location</td>
      <td>Los Angeles, CA</td>
    </tr>
    <tr>
      <td class="label">General Property Type</td>
      <td>CBD / Data Center Office</td>
    </tr>
    <tr>
      <td class="label">Title / Vesting</td>
      <td>Fee Simple</td>
    </tr>
    <tr>
      <td class="label">Year Built / Renovated</td>
      <td>1967 / 1992</td>
    </tr>
    <tr>
      <td class="label">Size (SF)</td>
      <td>681,553 SF</td>
    </tr>
    <tr>
      <td class="label">Cut-Off Balance PSF</td>
      <td>$588</td>
    </tr>
    <tr>
      <td class="label">Maturity Balance PSF</td>
      <td>$588</td>
    </tr>
    <tr>
      <td class="label">Property Manager</td>
      <td>GI Property Manager (CA) Inc.</td>
    </tr>
    <tr>
      <td class="label">Appraised Value</td>
      <td>$913,000,000</td>
    </tr>
    <tr>
      <td class="label">Appraisal Date</td>
      <td>November 5, 2021</td>
    </tr>
  </table>

  <h3>📊 Underwriting Financial Information</h3>
  <table>
    <tr>
      <td class="label">Underwritten Net Operating Income (NOI)</td>
      <td>$37,510,389</td>
    </tr>
    <tr>
      <td class="label">Underwritten Net Cash Flow (NCF)</td>
      <td>$36,919,391</td>
    </tr>
    <tr>
      <td class="label">Underwritten NOI DSCR</td>
      <td>3.42x</td>
    </tr>
    <tr>
      <td class="label">Underwritten NCF DSCR</td>
      <td>3.37x</td>
    </tr>
    <tr>
      <td class="label">Underwritten NOI Debt Yield</td>
      <td>9.6%</td>
    </tr>
    <tr>
      <td class="label">Underwritten NCF Debt Yield</td>
      <td>9.5%</td>
    </tr>
    <tr>
      <td class="label">Cut-Off Date LTV</td>
      <td>42.6%</td>
    </tr>
    <tr>
      <td class="label">Maturity Date LTV</td>
      <td>42.6%</td>
    </tr>
    <tr>
      <td class="label">UW PSF</td>
      <td>$55.81</td>
    </tr>
  </table>


  <h3>🏦 Escrows & Reserves</h3>
  <table>
    <tr>
      <td class="label">Real Estate Taxes – Initial</td>
      <td>$0</td>
    </tr>
    <tr>
      <td class="label">Real Estate Taxes – Monthly</td>
      <td>Springing</td>
    </tr>
    <tr>
      <td class="label">Insurance – Initial</td>
      <td>$0</td>
    </tr>
    <tr>
      <td class="label">Insurance – Monthly</td>
      <td>Springing</td>
    </tr>
    <tr>
      <td class="label">Replacement CapEx – Initial</td>
      <td>$0</td>
    </tr>
    <tr>
      <td class="label">Replacement CapEx – Monthly</td>
      <td>Springing</td>
    </tr>
    <tr>
      <td class="label">TI/LC – Initial</td>
      <td>$0</td>
    </tr>
    <tr>
      <td class="label">TI/LC – Monthly</td>
      <td>Springing</td>
    </tr>
  </table>

  <h3>💸 Sources & Uses</h3>
  <table>
    <tr>
      <td class="label">Source – Whole Loan Proceeds</td>
      <td>$389,250,000 (100.0%)</td>
    </tr>
    <tr>
      <td class="label">Total Sources</td>
      <td>$389,250,000</td>
    </tr>
    <tr>
      <td class="label">Use – Return of Equity</td>
      <td>$197,559,597 (50.8%)</td>
    </tr>
    <tr>
      <td class="label">Use – Loan Payoff</td>
      <td>$190,981,809 (49.0%)</td>
    </tr>
    <tr>
      <td class="label">Use – Closing Costs</td>
      <td>$708,168 (0.2%)</td>
    </tr>
    <tr>
      <td class="label">Total Uses</td>
      <td>$389,250,000</td>
    </tr>
  </table>

  <h3>👥 Major Tenants</h3>
  <table>
    <tr>
      <td class="label">Tenant Name</td>
      <td>CoreSite</td>
      <td>Musick Peeler</td>
      <td>Verizon Global Networks</td>
      <td>CenturyLink</td>
      <td>Cervalis</td>
    </tr>
    <tr>
      <td class="label">Leased SF</td>
      <td>176,685</td>
      <td>106,475</td>
      <td>94,381</td>
      <td>66,251</td>
      <td>43,201</td>
    </tr>
    <tr>
      <td class="label">% of Total NRA</td>
      <td>26.7%</td>
      <td>16.1%</td>
      <td>14.3%</td>
      <td>9.6%</td>
      <td>6.3%</td>
    </tr>
    <tr>
      <td class="label">Annual UW Base Rent</td>
      <td>$17,283,122</td>
      <td>$3,249,488</td>
      <td>$8,742,143</td>
      <td>$6,402,569</td>
      <td>$3,539,713</td>
    </tr>
    <tr>
      <td class="label">UW Rent PSF</td>
      <td>$97.78</td>
      <td>$30.50</td>
      <td>$92.67</td>
      <td>$96.64</td>
      <td>$81.95</td>
    </tr>
    <tr>
      <td class="label">% of Total Base Rent</td>
      <td>40.5%</td>
      <td>11.7%</td>
      <td>13.4%</td>
      <td>12.7%</td>
      <td>7.4%</td>
    </tr>
    <tr>
      <td class="label">Lease Expiration</td>
      <td>7/31/2026</td>
      <td>10/31/2025</td>
      <td>Various</td>
      <td>Various</td>
      <td>7/31/2024</td>
    </tr>
  </table>

  <br/>

  <table>
    <tr>
      <td class="label">Tenant Name</td>
      <td>Zayo</td>
      <td>Crown Castle</td>
      <td>China Telecom</td>
      <td>GI TC One Wilshire Services</td>
      <td>East-West Bank</td>
    </tr>
    <tr>
      <td class="label">Leased SF</td>
      <td>36,397</td>
      <td>26,061</td>
      <td>14,184</td>
      <td>14,000</td>
      <td>7,504</td>
    </tr>
    <tr>
      <td class="label">% of Total NRA</td>
      <td>5.4%</td>
      <td>4.0%</td>
      <td>2.1%</td>
      <td>2.1%</td>
      <td>1.1%</td>
    </tr>
    <tr>
      <td class="label">Annual UW Base Rent</td>
      <td>$1,835,777</td>
      <td>$1,522,620</td>
      <td>$1,686,084</td>
      <td>$2,100,000</td>
      <td>$458,887</td>
    </tr>
    <tr>
      <td class="label">UW Rent PSF</td>
      <td>$50.45</td>
      <td>$58.45</td>
      <td>$119.01</td>
      <td>$150.00</td>
      <td>$61.12</td>
    </tr>
    <tr>
      <td class="label">% of Total Base Rent</td>
      <td>3.8%</td>
      <td>3.7%</td>
      <td>3.1%</td>
      <td>4.0%</td>
      <td>0.2%</td>
    </tr>
    <tr>
      <td class="label">Lease Expiration</td>
      <td>7/31/2026</td>
      <td>Various</td>
      <td>9/30/2026</td>
      <td>7/31/2026</td>
      <td>10/17/2024</td>
    </tr>
  </table>


  <h3>📆 Lease Expiration Schedule</h3>
  <table>
    <tr>
      <td class="label">Year</td>
      <td>Number of Leases</td>
      <td>SF Rolling</td>
      <td>% of NRA</td>
      <td>Rent PSF</td>
      <td>Total Rent Rolling</td>
      <td>% of Total Rent</td>
    </tr>
    <tr>
      <td>2024</td>
      <td>10</td>
      <td>137,041</td>
      <td>20.7%</td>
      <td>$65.47</td>
      <td>$8,969,400</td>
      <td>14.6%</td>
    </tr>
    <tr>
      <td>2025</td>
      <td>16</td>
      <td>43,663</td>
      <td>6.6%</td>
      <td>$35.65</td>
      <td>$1,556,249</td>
      <td>3.9%</td>
    </tr>
    <tr>
      <td>2026</td>
      <td>8</td>
      <td>63,063</td>
      <td>9.5%</td>
      <td>$91.84</td>
      <td>$5,792,187</td>
      <td>18.5%</td>
    </tr>
    <tr>
      <td>2028</td>
      <td>1</td>
      <td>200,686</td>
      <td>30.3%</td>
      <td>$97.00</td>
      <td>$19,466,542</td>
      <td>39.6%</td>
    </tr>
    <tr>
      <td>2032</td>
      <td>1</td>
      <td>32,071</td>
      <td>4.9%</td>
      <td>$55.85</td>
      <td>$1,790,066</td>
      <td>4.2%</td>
    </tr>
  </table>

  <h3>🏢 Occupancy History</h3>
  <table>
    <tr>
      <td class="label">Year</td>
      <td>Occupancy</td>
    </tr>
    <tr>
      <td>2018</td>
      <td>86.6%</td>
    </tr>
    <tr>
      <td>2019</td>
      <td>90.3%</td>
    </tr>
    <tr>
      <td>2020</td>
      <td>89.4%</td>
    </tr>
    <tr>
      <td>T-12 (Nov 2021)</td>
      <td>87.3%</td>
    </tr>
  </table>


  <h3>📊 Cash Flow Analysis</h3>
  <table>
    <tr>
      <td class="label">Metric</td>
      <td>2018</td>
      <td>2019</td>
      <td>2020</td>
      <td>T-12 (9/30/2021)</td>
      <td>Underwritten</td>
    </tr>
    <tr>
      <td>Base Rent</td>
      <td>$35,250,894</td>
      <td>$38,070,245</td>
      <td>$40,022,711</td>
      <td>$40,900,005</td>
      <td>$42,702,032</td>
    </tr>
    <tr>
      <td>Reimbursements</td>
      <td>$1,687,084</td>
      <td>$2,542,778</td>
      <td>$3,202,205</td>
      <td>$3,868,783</td>
      <td>$3,725,129</td>
    </tr>
    <tr>
      <td>Other Income</td>
      <td>$6,780,919</td>
      <td>$7,007,780</td>
      <td>$7,317,265</td>
      <td>$7,284,263</td>
      <td>$8,182,721</td>
    </tr>
    <tr>
      <td>Gross Potential Income</td>
      <td>$43,668,997</td>
      <td>$46,610,800</td>
      <td>$50,552,181</td>
      <td>$52,053,051</td>
      <td>$60,730,302</td>
    </tr>
    <tr>
      <td>Less Vacancy/Credit Loss</td>
      <td>($4,381,452)</td>
      <td>($4,741,580)</td>
      <td>($5,116,626)</td>
      <td>($6,484,800)</td>
      <td>($6,117,900)</td>
    </tr>
    <tr>
      <td>Effective Gross Income</td>
      <td>$39,287,545</td>
      <td>$41,869,220</td>
      <td>$45,435,555</td>
      <td>$45,568,251</td>
      <td>$54,612,402</td>
    </tr>
    <tr>
      <td>Total Operating Expenses</td>
      <td>$14,410,170</td>
      <td>$15,321,713</td>
      <td>$16,852,366</td>
      <td>$15,637,487</td>
      <td>$17,705,013</td>
    </tr>
    <tr>
      <td>Net Operating Income (NOI)</td>
      <td>$24,771,375</td>
      <td>$26,547,507</td>
      <td>$28,583,189</td>
      <td>$29,930,764</td>
      <td>$37,510,389</td>
    </tr>
    <tr>
      <td>Capital Expenditures</td>
      <td>$0</td>
      <td>$0</td>
      <td>$0</td>
      <td>$0</td>
      <td>$491,000</td>
    </tr>
    <tr>
      <td>Net Cash Flow (NCF)</td>
      <td>$24,771,312</td>
      <td>$31,610,306</td>
      <td>$34,570,190</td>
      <td>$35,857,157</td>
      <td>$36,919,391</td>
    </tr>
  </table>


  <h3>🏢 Appraisal Summary</h3>
  <table>
    <tr>
      <td class="label">Appraised Value</td>
      <td>$913,000,000</td>
    </tr>
    <tr>
      <td class="label">Appraisal Date</td>
      <td>November 5, 2021</td>
    </tr>
  </table>


  <h3>🧾 Loan Combination Summary</h3>
  <table>
    <tr>
      <td class="label">Total Whole Loan Balance</td>
      <td>$389,250,000</td>
    </tr>
    <tr>
      <td class="label">Note A-1 Balance</td>
      <td>$90,000,000</td>
    </tr>
    <tr>
      <td class="label">Note A-2 Balance</td>
      <td>$80,000,000</td>
    </tr>
    <tr>
      <td class="label">Note A-3 Balance</td>
      <td>$85,000,000</td>
    </tr>
    <tr>
      <td class="label">Note A-4 Balance</td>
      <td>$94,250,000</td>
    </tr>
    <tr>
      <td class="label">Note A-5 Balance</td>
      <td>$40,000,000</td>
    </tr>
    <tr>
      <td class="label">Controlling Class</td>
      <td>Benchmark 2022-B32 (Note A-1)</td>
    </tr>
    <tr>
      <td class="label">Pari Passu / Participation</td>
      <td>Yes – Notes A-1 through A-5</td>
    </tr>
    <tr>
      <td class="label">Co-Lender Agreement</td>
      <td>Implied via Pari Passu Structure</td>
    </tr>
  </table>



    
    """
    st.markdown(html_n3021, unsafe_allow_html=True)

with tab7:
  
  st.title("📄 N3791 Loan")

  html_n3791 = """

    <h3>🏦 Loan Information</h3>
  <table>
  <tr>
      <td class="label">Deal Name</td>
      <td>Series 2023-C22</td>
    </tr>
    <tr>
      <td class="label">Loan ID</td>
      <td>n3791_x3</td>
    </tr>
    <tr>
      <td class="label">Loan Seller</td>
      <td>Barclays</td>
    </tr>
    <tr>
      <td class="label">Original Balance</td>
      <td>$40,000,000</td>
    </tr>
    <tr>
      <td class="label">Cut-Off Balance</td>
      <td>$40,000,000</td>
    </tr>
    <tr>
      <td class="label">% of Initial Pool Balance</td>
      <td>5.8%</td>
    </tr>
    <tr>
      <td class="label">Loan Purpose</td>
      <td>Refinance</td>
    </tr>
    <tr>
      <td class="label">Borrower</td>
      <td>60 Hudson Owner, LLC</td>
    </tr>
    <tr>
      <td class="label">Sponsor</td>
      <td>The Stahl Organization</td>
    </tr>
    <tr>
      <td class="label">Mortgage Rate</td>
      <td>5.88505%</td>
    </tr>
    <tr>
      <td class="label">Note Date</td>
      <td>September 6, 2023</td>
    </tr>
    <tr>
      <td class="label">Maturity Date</td>
      <td>October 1, 2033</td>
    </tr>
    <tr>
      <td class="label">Original Term to Maturity</td>
      <td>120 months</td>
    </tr>
    <tr>
      <td class="label">Original Amortization Term</td>
      <td>None</td>
    </tr>
    <tr>
      <td class="label">Amortization Type</td>
      <td>Interest Only</td>
    </tr>
    <tr>
      <td class="label">Interest-Only Period</td>
      <td>120 months</td>
    </tr>
    <tr>
      <td class="label">Prepayment Provisions</td>
      <td>LI(2.5)/D(90)/O(5)</td>
    </tr>
    <tr>
      <td class="label">Lockbox / Cash Management</td>
      <td>Hard / In Place</td>
    </tr>
    <tr>
      <td class="label">Additional Debt Type</td>
      <td>Pari Passu</td>
    </tr>
    <tr>
      <td class="label">Additional Debt Balance</td>
      <td>$240,000,000</td>
    </tr>
  </table>

  <h3>🏢 Property Information</h3>
  <table>
    <tr>
      <td class="label">Asset Type</td>
      <td>Single Asset</td>
    </tr>
    <tr>
      <td class="label">Location</td>
      <td>New York, NY</td>
    </tr>
    <tr>
      <td class="label">General Property Type</td>
      <td>Other – Data Center</td>
    </tr>
    <tr>
      <td class="label">Title / Vesting</td>
      <td>Fee</td>
    </tr>
    <tr>
      <td class="label">Year Built / Renovated</td>
      <td>1930 / 2013</td>
    </tr>
    <tr>
      <td class="label">Size (SF)</td>
      <td>1,149,619 SF</td>
    </tr>
    <tr>
      <td class="label">Occupancy</td>
      <td>86.2% (as of 2023-06-05)</td>
    </tr>
    <tr>
      <td class="label">Cut-Off Balance PSF</td>
      <td>$244</td>
    </tr>
    <tr>
      <td class="label">Maturity Balance PSF</td>
      <td>$244</td>
    </tr>
    <tr>
      <td class="label">Appraised Value</td>
      <td>$1,596,000,000</td>
    </tr>
    <tr>
      <td class="label">Appraised Value PSF</td>
      <td>$1,388</td>
    </tr>
    <tr>
      <td class="label">Appraisal Date</td>
      <td>May 8, 2023</td>
    </tr>
  </table>

  <h3>📊 Underwriting Financial Information</h3>
  <table>
    <tr>
      <td class="label">Underwritten Net Operating Income (NOI)</td>
      <td>$57,833,753</td>
    </tr>
    <tr>
      <td class="label">Underwritten Net Cash Flow (NCF)</td>
      <td>$65,493,494</td>
    </tr>
    <tr>
      <td class="label">Underwritten NCF DSCR</td>
      <td>3.92x</td>
    </tr>
    <tr>
      <td class="label">Underwritten NOI Debt Yield</td>
      <td>24.2%</td>
    </tr>
    <tr>
      <td class="label">Cut-Off Date LTV</td>
      <td>17.5%</td>
    </tr>
    <tr>
      <td class="label">Maturity Date LTV</td>
      <td>17.5%</td>
    </tr>
  </table>

  <h3>🏦 Escrows & Reserves</h3>
  <table>
    <tr>
      <td class="label">Real Estate Taxes – Initial</td>
      <td>$7,089,987</td>
    </tr>
    <tr>
      <td class="label">Real Estate Taxes – Monthly</td>
      <td>$1,772,497</td>
    </tr>
    <tr>
      <td class="label">Insurance – Initial</td>
      <td>$0</td>
    </tr>
    <tr>
      <td class="label">Insurance – Monthly</td>
      <td>Springing</td>
    </tr>
    <tr>
      <td class="label">Replacement Reserves – Initial</td>
      <td>$0</td>
    </tr>
    <tr>
      <td class="label">Replacement Reserves – Monthly</td>
      <td>Springing</td>
    </tr>
    <tr>
      <td class="label">TI/LC – Initial</td>
      <td>$0</td>
    </tr>
    <tr>
      <td class="label">TI/LC – Monthly</td>
      <td>Springing</td>
    </tr>
  </table>


  <h3>💸 Sources & Uses</h3>
  <table>
    <tr>
      <td class="label">Source – Whole Loan</td>
      <td>$280,000,000 (98.7%)</td>
    </tr>
    <tr>
      <td class="label">Source – Borrower Sponsor Equity</td>
      <td>$3,678,608 (1.3%)</td>
    </tr>
    <tr>
      <td class="label">Total Sources</td>
      <td>$283,678,608</td>
    </tr>
    <tr>
      <td class="label">Use – Loan Payoff</td>
      <td>$274,771,150 (96.9%)</td>
    </tr>
    <tr>
      <td class="label">Use – Reserves</td>
      <td>$7,089,987 (2.5%)</td>
    </tr>
    <tr>
      <td class="label">Use – Closing Costs</td>
      <td>$1,817,471 (0.6%)</td>
    </tr>
    <tr>
      <td class="label">Total Uses</td>
      <td>$283,678,608</td>
    </tr>
  </table>

  <h3>👥 Major Tenants</h3>
  <table>
    <tr>
      <td class="label">Tenant Name</td>
      <td>Verizon</td>
      <td>Hudson Interchange</td>
      <td>Telx</td>
      <td>DataBank</td>
      <td>CenturyLink</td>
    </tr>
    <tr>
      <td class="label">Credit Rating (Moody’s/S&P/Fitch)</td>
      <td>Baa1 / BBB+ / A-</td>
      <td>NR / NR / NR</td>
      <td>Baa2 / BBB / BBB</td>
      <td>NR / NR / NR</td>
      <td>Ca / CCC / CCC+</td>
    </tr>
    <tr>
      <td class="label">Leased SF</td>
      <td>184,420</td>
      <td>172,775</td>
      <td>95,494</td>
      <td>57,840</td>
      <td>37,427</td>
    </tr>
    <tr>
      <td class="label">% of Total NRA</td>
      <td>16.0%</td>
      <td>15.0%</td>
      <td>8.3%</td>
      <td>5.0%</td>
      <td>3.3%</td>
    </tr>
    <tr>
      <td class="label">Annual UW Base Rent</td>
      <td>$23,222,921</td>
      <td>$18,133,772</td>
      <td>$10,684,472</td>
      <td>$8,693,993</td>
      <td>$3,795,715</td>
    </tr>
    <tr>
      <td class="label">UW Rent PSF</td>
      <td>$126.96</td>
      <td>$104.95</td>
      <td>$111.26</td>
      <td>$150.18</td>
      <td>$101.29</td>
    </tr>
    <tr>
      <td class="label">% of Total Base Rent</td>
      <td>28.3%</td>
      <td>22.1%</td>
      <td>12.9%</td>
      <td>10.6%</td>
      <td>4.6%</td>
    </tr>
    <tr>
      <td class="label">Lease Expiration</td>
      <td>Various</td>
      <td>9/30/2032</td>
      <td>10/31/2027</td>
      <td>7/31/2028</td>
      <td>9/30/2033</td>
    </tr>
    <tr>
      <td class="label">Renewal Options</td>
      <td>Various (6)</td>
      <td>5-year</td>
      <td>1, 5-year</td>
      <td>1, 10-year</td>
      <td>1, 10-year</td>
    </tr>
  </table>

  <br/>

  <table>
    <tr>
      <td class="label">Tenant Name</td>
      <td>Level 3 Comm.</td>
      <td>NYI-Sirius, LLC</td>
    </tr>
    <tr>
      <td class="label">Credit Rating (Moody’s/S&P/Fitch)</td>
      <td>NR / NR / NR</td>
      <td>NR / NR / NR</td>
    </tr>
    <tr>
      <td class="label">Leased SF</td>
      <td>35,389</td>
      <td>21,708</td>
    </tr>
    <tr>
      <td class="label">% of Total NRA</td>
      <td>3.1%</td>
      <td>1.9%</td>
    </tr>
    <tr>
      <td class="label">Annual UW Base Rent</td>
      <td>$4,322,052</td>
      <td>$2,505,625</td>
    </tr>
    <tr>
      <td class="label">UW Rent PSF</td>
      <td>$119.59</td>
      <td>$115.42</td>
    </tr>
    <tr>
      <td class="label">% of Total Base Rent</td>
      <td>5.2%</td>
      <td>3.1%</td>
    </tr>
    <tr>
      <td class="label">Lease Expiration</td>
      <td>Various (5)</td>
      <td>7/31/2026 (6)</td>
    </tr>
    <tr>
      <td class="label">Renewal Options</td>
      <td>1, 10-year</td>
      <td>1, 10-year</td>
    </tr>
  </table>

  <h3>📆 Lease Expiration Schedule</h3>
  <table>
    <tr>
      <td class="label">Year</td>
      <td>Number of Leases</td>
      <td>SF Rolling</td>
      <td>% of NRA</td>
      <td>Rent PSF</td>
      <td>Total Rent Rolling</td>
      <td>% of Total Rent</td>
    </tr>
    <tr>
      <td>2023 & MTM</td>
      <td>1</td>
      <td>7,886</td>
      <td>0.7%</td>
      <td>$30.80</td>
      <td>$242,871</td>
      <td>0.3%</td>
    </tr>
    <tr>
      <td>2024</td>
      <td>1</td>
      <td>10,876</td>
      <td>0.9%</td>
      <td>$92.79</td>
      <td>$1,009,229</td>
      <td>1.3%</td>
    </tr>
    <tr>
      <td>2025</td>
      <td>2</td>
      <td>16,071</td>
      <td>1.5%</td>
      <td>$120.65</td>
      <td>$1,938,922</td>
      <td>2.4%</td>
    </tr>
    <tr>
      <td>2026</td>
      <td>1</td>
      <td>5,522</td>
      <td>0.5%</td>
      <td>$317.86</td>
      <td>$1,754,960</td>
      <td>2.1%</td>
    </tr>
    <tr>
      <td>2027</td>
      <td>4</td>
      <td>132,121</td>
      <td>11.5%</td>
      <td>$108.74</td>
      <td>$14,371,895</td>
      <td>17.5%</td>
    </tr>
    <tr>
      <td>2028</td>
      <td>3</td>
      <td>40,719</td>
      <td>3.5%</td>
      <td>$117.29</td>
      <td>$4,776,223</td>
      <td>5.8%</td>
    </tr>
    <tr>
      <td>2029</td>
      <td>1</td>
      <td>61,121</td>
      <td>5.3%</td>
      <td>$106.28</td>
      <td>$6,496,629</td>
      <td>7.9%</td>
    </tr>
    <tr>
      <td>2030</td>
      <td>1</td>
      <td>6,121</td>
      <td>0.5%</td>
      <td>$106.09</td>
      <td>$649,679</td>
      <td>0.8%</td>
    </tr>
    <tr>
      <td>2031</td>
      <td>2</td>
      <td>12,976</td>
      <td>1.1%</td>
      <td>$121.86</td>
      <td>$1,581,091</td>
      <td>1.9%</td>
    </tr>
    <tr>
      <td>2032</td>
      <td>1</td>
      <td>242,627</td>
      <td>21.1%</td>
      <td>$117.23</td>
      <td>$28,439,918</td>
      <td>34.2%</td>
    </tr>
    <tr>
      <td>2033</td>
      <td>2</td>
      <td>48,307</td>
      <td>4.2%</td>
      <td>$97.56</td>
      <td>$4,712,245</td>
      <td>5.7%</td>
    </tr>
    <tr>
      <td>2034 & Beyond</td>
      <td>2</td>
      <td>145,967</td>
      <td>17.0%</td>
      <td>$166.59</td>
      <td>$24,314,458</td>
      <td>29.6%</td>
    </tr>
    <tr>
      <td>Vacant</td>
      <td>–</td>
      <td>434,885</td>
      <td>37.8%</td>
      <td>–</td>
      <td>–</td>
      <td>–</td>
    </tr>
  </table>


  <h3>🏢 Occupancy History</h3>
  <table>
    <tr>
      <td class="label">Year</td>
      <td>Occupancy</td>
    </tr>
    <tr>
      <td>2020</td>
      <td>72.6%</td>
    </tr>
    <tr>
      <td>2021</td>
      <td>64.1%</td>
    </tr>
    <tr>
      <td>2022</td>
      <td>63.2%</td>
    </tr>
    <tr>
      <td>2023 (as of June 5)</td>
      <td>62.2%</td>
    </tr>
  </table>

  <h3>📊 Cash Flow Analysis</h3>
  <table>
    <tr>
      <td class="label">Metric</td>
      <td>2020</td>
      <td>2021</td>
      <td>2022</td>
      <td>TTM (6/30/2023)</td>
      <td>Underwritten</td>
    </tr>
    <tr>
      <td>Gross Potential Rent</td>
      <td>$80,020,378</td>
      <td>$81,473,151</td>
      <td>$79,777,070</td>
      <td>$80,757,027</td>
      <td>$126,042,403</td>
    </tr>
    <tr>
      <td>Other Income</td>
      <td>$22,431,718</td>
      <td>$29,816,289</td>
      <td>$36,206,142</td>
      <td>$37,551,734</td>
      <td>$31,900,000</td>
    </tr>
    <tr>
      <td>Total Reimbursements</td>
      <td>$8,869,569</td>
      <td>$7,503,851</td>
      <td>$6,687,304</td>
      <td>$7,800,073</td>
      <td>$6,405,196</td>
    </tr>
    <tr>
      <td>Effective Gross Income</td>
      <td>$111,351,756</td>
      <td>$118,744,290</td>
      <td>$112,940,516</td>
      <td>$124,308,174</td>
      <td>$120,188,204</td>
    </tr>
    <tr>
      <td>Total Operating Expenses</td>
      <td>$43,807,455</td>
      <td>$24,128,540</td>
      <td>$27,094,174</td>
      <td>$30,675,994</td>
      <td>$52,681,331</td>
    </tr>
    <tr>
      <td>Net Operating Income (NOI)</td>
      <td>$67,543,911</td>
      <td>$77,460,400</td>
      <td>$65,651,820</td>
      <td>$73,525,984</td>
      <td>$57,833,753</td>
    </tr>
    <tr>
      <td>Capital Expenditures</td>
      <td>$0</td>
      <td>$0</td>
      <td>$0</td>
      <td>$0</td>
      <td>$229,924</td>
    </tr>
    <tr>
      <td>TI/LC</td>
      <td>$0</td>
      <td>$0</td>
      <td>$0</td>
      <td>$0</td>
      <td>$2,110,526</td>
    </tr>
    <tr>
      <td>Net Cash Flow (NCF)</td>
      <td>$67,543,911</td>
      <td>$77,460,400</td>
      <td>$65,651,820</td>
      <td>$73,525,984</td>
      <td>$65,493,494</td>
    </tr>
  </table>


  <h3>🏢 Appraisal Summary</h3>
  <table>
    <tr>
      <td class="label">Appraised Value</td>
      <td>$1,596,000,000</td>
    </tr>
    <tr>
      <td class="label">Appraised Value per SF</td>
      <td>$1,388</td>
    </tr>
    <tr>
      <td class="label">Appraisal Date</td>
      <td>May 8, 2023</td>
    </tr>
  </table>

  <h3>🧾 Loan Combination Summary</h3>
  <table>
    <tr>
      <td class="label">Total Whole Loan Balance</td>
      <td>$280,000,000</td>
    </tr>
    <tr>
      <td class="label">Note A-1 Balance</td>
      <td>$50,000,000</td>
    </tr>
    <tr>
      <td class="label">Note A-2 Balance</td>
      <td>$50,000,000</td>
    </tr>
    <tr>
      <td class="label">Note A-3 Balance</td>
      <td>$40,000,000</td>
    </tr>
    <tr>
      <td class="label">Note A-4 Balance</td>
      <td>$30,000,000</td>
    </tr>
    <tr>
      <td class="label">Note A-5 Balance</td>
      <td>$30,000,000</td>
    </tr>
    <tr>
      <td class="label">Note A-6 Balance</td>
      <td>$20,000,000</td>
    </tr>
    <tr>
      <td class="label">Note A-7 Balance</td>
      <td>$20,000,000</td>
    </tr>
    <tr>
      <td class="label">Note A-8 Balance</td>
      <td>$10,000,000</td>
    </tr>
    <tr>
      <td class="label">Note A-9 Balance</td>
      <td>$10,000,000</td>
    </tr>
    <tr>
      <td class="label">Note A-10 Balance</td>
      <td>$10,000,000</td>
    </tr>
    <tr>
      <td class="label">Controlling Class</td>
      <td>MSBNA (Note A-1)</td>
    </tr>
    <tr>
      <td class="label">Pari Passu / Participation</td>
      <td>Yes – Notes A-1 through A-10</td>
    </tr>
    <tr>
      <td class="label">Co-Lender Agreement</td>
      <td>Implied via Pari Passu Structure</td>
    </tr>
  </table>



  """
  st.markdown(html_n3791, unsafe_allow_html=True)