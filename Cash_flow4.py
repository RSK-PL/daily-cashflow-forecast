import streamlit as st
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(page_title="Daily Cash Flow Forecast", layout="wide")

st.title("Daily Cash Flow Forecast")
st.write("Upload AR and AP files, add manual planned cash events, and calculate projected cash balance.")

if "manual_events" not in st.session_state:
    st.session_state.manual_events = pd.DataFrame(
        columns=["Document", "Contractor", "Amount", "Date", "Type", "Category"]
    )

ar_file = st.file_uploader("Upload AR.xlsx - receivables / należności", type=["xlsx"], key="ar_uploader")
ap_file = st.file_uploader("Upload AP.xlsx - payables / zobowiązania", type=["xlsx"], key="ap_uploader")

opening_cash = st.number_input("Opening cash", value=100000.00, step=1000.00)
opening_date = st.date_input("Opening cash date")
minimum_cash_buffer = st.number_input("Minimum cash buffer", value=50000.00, step=1000.00)

required_columns = ["Numer dokumentu", "Podmiot", "Wartość", "Termin płatności"]


def clean_amount(series):
    return (
        series.astype(str)
        .str.replace(" ", "", regex=False)
        .str.replace("\u00a0", "", regex=False)
        .str.replace(",", ".", regex=False)
        .str.replace("(", "-", regex=False)
        .str.replace(")", "", regex=False)
        .pipe(pd.to_numeric, errors="coerce")
    )


def load_file(file, source_type):
    df_raw = pd.read_excel(file)

    missing = [col for col in required_columns if col not in df_raw.columns]
    if missing:
        st.error(f"Missing columns in {source_type} file: {missing}")
        st.write("Available columns in uploaded file:")
        st.write(list(df_raw.columns))
        st.stop()

    df = df_raw[required_columns].copy()

    df = df.rename(columns={
        "Numer dokumentu": "Document",
        "Podmiot": "Contractor",
        "Wartość": "Amount",
        "Termin płatności": "Date"
    })

    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    df["Amount"] = clean_amount(df["Amount"])

    df = df.dropna(subset=["Date", "Amount"])
    df["Amount"] = df["Amount"].abs()
    df["Type"] = source_type
    df["Category"] = source_type

    return df


st.subheader("Manual planned cash events")

with st.form("manual_event_form"):
    col_a, col_b, col_c, col_d, col_e = st.columns(5)

    with col_a:
        manual_date = st.date_input("Event date")

    with col_b:
        manual_direction = st.selectbox("Direction", ["Inflow", "Outflow"])

    with col_c:
        manual_category = st.selectbox(
            "Category",
            ["Payroll", "Tax", "Leasing", "Loan", "Other income", "Other expense"]
        )

    with col_d:
        manual_amount = st.number_input("Amount", min_value=0.0, step=1000.0)

    with col_e:
        manual_description = st.text_input("Description", value="Manual event")

    submitted = st.form_submit_button("Add planned event")

    if submitted:
        if manual_amount <= 0:
            st.warning("Amount must be greater than zero.")
        else:
            manual_type = "AR" if manual_direction == "Inflow" else "AP"

            new_event = pd.DataFrame([{
                "Document": "Manual",
                "Contractor": manual_description,
                "Amount": abs(manual_amount),
                "Date": pd.to_datetime(manual_date),
                "Type": manual_type,
                "Category": manual_category
            }])

            st.session_state.manual_events = pd.concat(
                [st.session_state.manual_events, new_event],
                ignore_index=True
            )

            st.success("Manual planned event added.")


if not st.session_state.manual_events.empty:
    with st.expander("Show manual planned events", expanded=False):
        st.dataframe(st.session_state.manual_events, use_container_width=True)

        if st.button("Clear manual planned events"):
            st.session_state.manual_events = pd.DataFrame(
                columns=["Document", "Contractor", "Amount", "Date", "Type", "Category"]
            )
            st.rerun()


if ar_file and ap_file:
    ar = load_file(ar_file, "AR")
    ap = load_file(ap_file, "AP")

    cash_events = pd.concat(
        [ar, ap, st.session_state.manual_events],
        ignore_index=True
    )

    cash_events["Date"] = pd.to_datetime(cash_events["Date"], errors="coerce")
    cash_events["Amount"] = pd.to_numeric(cash_events["Amount"], errors="coerce")
    cash_events = cash_events.dropna(subset=["Date", "Amount"])
    cash_events = cash_events.sort_values("Date")

    if "AP" not in cash_events["Type"].unique():
        st.error("No AP records found in CashEvents. Payables are not included in the forecast.")
        st.stop()

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
    daily_cash["Daily movement"] = daily_cash["Daily inflow"] - daily_cash["Daily outflow"]
    daily_cash["Cash balance"] = opening_cash + daily_cash["Daily movement"].cumsum()

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

    st.subheader("Documents for selected date")

    selected_date = st.date_input(
        "Select date",
        value=daily_cash["Date"].min().date(),
        min_value=daily_cash["Date"].min().date(),
        max_value=daily_cash["Date"].max().date(),
        key="selected_document_date"
    )

    selected_date_ts = pd.to_datetime(selected_date)

    selected_events = cash_events[
        cash_events["Date"].dt.date == selected_date_ts.date()
    ].copy()

    selected_daily = daily_cash[
        daily_cash["Date"].dt.date == selected_date_ts.date()
    ].iloc[0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Daily inflow", f"{selected_daily['Daily inflow']:,.2f}")
    c2.metric("Daily outflow", f"{selected_daily['Daily outflow']:,.2f}")
    c3.metric("Daily movement", f"{selected_daily['Daily movement']:,.2f}")
    c4.metric("Cash balance", f"{selected_daily['Cash balance']:,.2f}")

    if selected_events.empty:
        st.info("No documents for selected date.")
    else:
        inflow_docs = selected_events[selected_events["Type"] == "AR"]
        outflow_docs = selected_events[selected_events["Type"] == "AP"]

        if not inflow_docs.empty:
            st.markdown("### Inflows / AR")
            st.dataframe(
                inflow_docs[["Document", "Contractor", "Amount", "Category"]],
                use_container_width=True
            )

        if not outflow_docs.empty:
            st.markdown("### Outflows / AP")
            st.dataframe(
                outflow_docs[["Document", "Contractor", "Amount", "Category"]],
                use_container_width=True
            )

    with st.expander("Show DailyCash table", expanded=False):
        st.dataframe(daily_cash, use_container_width=True)

    with st.expander("Show CashEvents table", expanded=False):
        st.dataframe(cash_events, use_container_width=True)

else:
    st.info("Upload both AR and AP files to calculate cash flow.")