import streamlit as st
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(page_title="Daily Cash Flow Forecast", layout="wide")

st.title("Daily Cash Flow Forecast")
st.write("Upload AR and AP files, enter opening cash, and calculate projected cash balance.")

ar_file = st.file_uploader("Upload AR.xlsx - receivables / należności", type=["xlsx"])
ap_file = st.file_uploader("Upload AP.xlsx - payables / zobowiązania", type=["xlsx"])

opening_cash = st.number_input("Opening cash", value=100000.00, step=1000.00)
opening_date = st.date_input("Opening cash date")
minimum_cash_buffer = st.number_input("Minimum cash buffer", value=50000.00, step=1000.00)

required_columns = ["Numer dokumentu", "Podmiot", "Wartość", "Termin płatności"]


def load_file(file, source_type):
    df = pd.read_excel(file)

    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        st.error(f"Missing columns in {source_type} file: {missing}")
        st.write("Available columns in uploaded file:")
        st.write(list(df.columns))
        st.stop()

    df = df[required_columns].copy()

    df = df.rename(columns={
        "Numer dokumentu": "Document",
        "Podmiot": "Contractor",
        "Wartość": "Amount",
        "Termin płatności": "Date"
    })

    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce")

    df = df.dropna(subset=["Date", "Amount"])

    df["Amount"] = df["Amount"].abs()
    df["Type"] = source_type

    return df


if ar_file and ap_file:
    ar = load_file(ar_file, "AR")
    ap = load_file(ap_file, "AP")

    cash_events = pd.concat([ar, ap], ignore_index=True)
    cash_events = cash_events.sort_values("Date")

    st.subheader("CashEvents")
    st.dataframe(cash_events, use_container_width=True)

    start_date = pd.to_datetime(opening_date)
    end_date = cash_events["Date"].max()

    if end_date < start_date:
        st.error("The latest payment date is earlier than the opening cash date.")
        st.stop()

    date_range = pd.date_range(start=start_date, end=end_date, freq="D")
    daily_cash = pd.DataFrame({"Date": date_range})

    daily_inflow = (
        cash_events[cash_events["Type"] == "AR"]
        .groupby("Date")["Amount"]
        .sum()
        .reset_index()
        .rename(columns={"Amount": "Daily inflow"})
    )

    daily_outflow = (
        cash_events[cash_events["Type"] == "AP"]
        .groupby("Date")["Amount"]
        .sum()
        .reset_index()
        .rename(columns={"Amount": "Daily outflow"})
    )

    daily_cash = daily_cash.merge(daily_inflow, on="Date", how="left")
    daily_cash = daily_cash.merge(daily_outflow, on="Date", how="left")

    daily_cash["Daily inflow"] = daily_cash["Daily inflow"].fillna(0)
    daily_cash["Daily outflow"] = daily_cash["Daily outflow"].fillna(0)

    daily_cash["Daily movement"] = (
        daily_cash["Daily inflow"] - daily_cash["Daily outflow"]
    )

    daily_cash["Cash balance"] = (
        opening_cash + daily_cash["Daily movement"].cumsum()
    )

    # Main KPI
    total_inflows = daily_cash["Daily inflow"].sum()
    total_outflows = daily_cash["Daily outflow"].sum()
    net_ar_ap_position = total_inflows - total_outflows
    final_cash = daily_cash["Cash balance"].iloc[-1]
    net_cash_movement = final_cash - opening_cash

    lowest_cash = daily_cash["Cash balance"].min()
    lowest_cash_date = daily_cash.loc[daily_cash["Cash balance"].idxmin(), "Date"]
    required_financing = abs(lowest_cash) if lowest_cash < 0 else 0

    highest_cash = daily_cash["Cash balance"].max()
    days_below_zero = (daily_cash["Cash balance"] < 0).sum()
    days_below_buffer = (daily_cash["Cash balance"] < minimum_cash_buffer).sum()

    biggest_daily_inflow = daily_cash["Daily inflow"].max()
    biggest_daily_inflow_date = daily_cash.loc[daily_cash["Daily inflow"].idxmax(), "Date"]

    biggest_daily_outflow = daily_cash["Daily outflow"].max()
    biggest_daily_outflow_date = daily_cash.loc[daily_cash["Daily outflow"].idxmax(), "Date"]

    st.subheader("Key liquidity KPIs")

    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric("Opening cash", f"{opening_cash:,.2f}")
    col2.metric("Final cash balance", f"{final_cash:,.2f}")
    col3.metric("Net cash movement", f"{net_cash_movement:,.2f}")
    col4.metric("Lowest cash balance", f"{lowest_cash:,.2f}")
    col5.metric("Lowest cash date", lowest_cash_date.strftime("%d.%m.%Y"))

    col6, col7, col8, col9, col10 = st.columns(5)

    col6.metric("Required financing", f"{required_financing:,.2f}")
    col7.metric("Total expected inflows", f"{total_inflows:,.2f}")
    col8.metric("Total expected outflows", f"{total_outflows:,.2f}")
    col9.metric("Net AR/AP position", f"{net_ar_ap_position:,.2f}")
    col10.metric("Highest cash balance", f"{highest_cash:,.2f}")

    col11, col12, col13, col14 = st.columns(4)

    col11.metric("Days below zero", int(days_below_zero))
    col12.metric("Days below buffer", int(days_below_buffer))
    col13.metric(
        "Biggest daily inflow",
        f"{biggest_daily_inflow:,.2f}",
        biggest_daily_inflow_date.strftime("%d.%m.%Y")
    )
    col14.metric(
        "Biggest daily outflow",
        f"{biggest_daily_outflow:,.2f}",
        biggest_daily_outflow_date.strftime("%d.%m.%Y")
    )

    st.subheader("DailyCash")
    st.dataframe(daily_cash, use_container_width=True)

    st.subheader("Cash balance chart")

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=daily_cash["Date"],
        y=daily_cash["Daily movement"],
        name="Daily movement"
    ))

    fig.add_trace(go.Scatter(
        x=daily_cash["Date"],
        y=daily_cash["Cash balance"],
        name="Cash balance",
        mode="lines"
    ))

    fig.add_trace(go.Scatter(
        x=daily_cash["Date"],
        y=[minimum_cash_buffer] * len(daily_cash),
        name="Minimum cash buffer",
        mode="lines"
    ))

    fig.update_layout(
        xaxis_title="Date",
        yaxis_title="Amount",
        hovermode="x unified"
    )

    st.plotly_chart(fig, use_container_width=True)

else:
    st.info("Upload both AR and AP files to calculate cash flow.")