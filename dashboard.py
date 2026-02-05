import pandas as pd
import plotly.express as px
import streamlit as st
import os
import glob

# 1. Page Configuration
st.set_page_config(layout="wide", page_title="Logistics Operations Dashboard")

# --- 2. DATA AUTOMATION & LOGIC ENGINE ---
FOLDER_PATH = r'C:\Users\ext-swastik.nautiyal\LineHaul_analysis\Raw_data'

def get_latest_file(path):
    files = glob.glob(os.path.join(path, "*.csv"))
    return max(files, key=os.path.getctime) if files else None

@st.cache_data
def load_and_process_data(path):
    latest_csv = get_latest_file(path)
    if not latest_csv: return None
    df = pd.read_csv(latest_csv)
    df['trip_date'] = pd.to_datetime(df['trip_date']).dt.date
    
    # LOGIC: Attribution for Adhocs
    def get_adhoc_owner(row):
        if row['actual_billing_basis'] != 'Adhoc': return 'N/A'
        reason = str(row.get('adhoc_trip_creation_reason', ''))
        return 'Vendor Issue' if 'VENDOR' in reason else 'Zepto Issue'

    # LOGIC: Attribution for Cancellations
    vendor_cancel_codes = [
        'PLANNED_VEHICLE_NOT_PROVIDED_BY_VENDOR', 'VEHICLE_UNAVAILABILITY', 
        'PLANNED_VEHICLE_BREAKDOWN', 'TRANSPORT_VENDOR_ISSUE'
    ]
    def get_cancel_owner(row):
        if row['trip_status'] != 'CANCELLED': return 'N/A'
        code = str(row.get('cancellation_reason_code', ''))
        return 'Vendor Issue' if code in vendor_cancel_codes else 'Zepto Issue'

    # LOGIC: Vehicle Compliance (Did we get the truck we planned?)
    df['vehicle_match'] = (df['planned_vehicle_type'] == df['actual_vehicle_type']).astype(int)
    
    # Apply Attribution
    df['adhoc_owner'] = df.apply(get_adhoc_owner, axis=1)
    df['cancel_owner'] = df.apply(get_cancel_owner, axis=1)
    
    return df

df_raw = load_and_process_data(FOLDER_PATH)

if df_raw is None:
    st.error("No CSV found. Please drop your latest report in the Raw_data folder.")
    st.stop()

# --- 3. SIDEBAR FILTERS ---
st.sidebar.header("🕹️ Controls")

# Date Dropdown (Dropdown instead of Slicer)
available_dates = sorted(df_raw['trip_date'].unique(), reverse=True)
selected_date = st.sidebar.selectbox("Select Trip Date", available_dates)

# Mother Hub Slicer
all_hubs = sorted(df_raw['source_mh_name'].unique())
selected_hubs = st.sidebar.multiselect("Select Mother Hubs", all_hubs, default=all_hubs)

# Filter Data
df = df_raw[(df_raw['trip_date'] == selected_date) & (df_raw['source_mh_name'].isin(selected_hubs))].copy()

# --- 4. EXECUTIVE KPI SCORECARDS ---
st.title(f"📊 Logistics Intelligence: {selected_date}")

k1, k2, k3, k4, k5 = st.columns(5)
total = len(df)
planned = len(df[df['actual_billing_basis'] == 'Planned'])
exec_planned = len(df[(df['actual_billing_basis'] == 'Planned') & (df['trip_status'] == 'COMPLETED')])
adhocs = len(df[df['actual_billing_basis'] == 'Adhoc'])
cancels = len(df[df['trip_status'] == 'CANCELLED'])

k1.metric("Total Trips", total)
k2.metric("Plan Execution", f"{(exec_planned/planned*100 if planned > 0 else 0):.1f}%")
k3.metric("Adhoc Rate", f"{(adhocs/total*100 if total > 0 else 0):.1f}%")
k4.metric("Cancel Rate", f"{(cancels/total*100 if total > 0 else 0):.1f}%")
k5.metric("Vehicle Compliance", f"{(df['vehicle_match'].mean()*100):.1f}%")

st.divider()

# --- 5. THE MASTER PERFORMANCE TABLE ---
st.subheader("📍 Mother Hub Performance & Root Cause Table")

summary_table = df.groupby('source_mh_name').agg(
    Total=('master_trip_code', 'count'),
    Plan_Success_Rate=('trip_status', lambda x: f"{( ((df.loc[x.index, 'actual_billing_basis'] == 'Planned') & (x == 'COMPLETED')).sum() / (df.loc[x.index, 'actual_billing_basis'] == 'Planned').sum() * 100):.1f}%"),
    Adhoc_Zepto=('adhoc_owner', lambda x: (x == 'Zepto Issue').sum()),
    Adhoc_Vendor=('adhoc_owner', lambda x: (x == 'Vendor Issue').sum()),
    Cancel_Zepto=('cancel_owner', lambda x: (x == 'Zepto Issue').sum()),
    Cancel_Vendor=('cancel_owner', lambda x: (x == 'Vendor Issue').sum()),
    Vehicle_Compliance=('vehicle_match', lambda x: f"{(x.mean()*100):.1f}%")
).reset_index()

st.dataframe(summary_table.sort_values('Total', ascending=False), use_container_width=True, hide_index=True)

st.divider()

# --- 6. CRITICAL ANALYSIS CHARTS ---
c1, c2, c3 = st.columns(3)

with c1:
    # Logic: Planned vs Executed
    success_data = pd.DataFrame({
        'Status': ['Executed (On Plan)', 'Plan Failed'],
        'Count': [exec_planned, planned - exec_planned]
    })
    fig1 = px.pie(success_data, names='Status', values='Count', hole=0.5,
                  title="<b>Planned vs Executed</b>",
                  color_discrete_map={'Executed (On Plan)':'#27AE60', 'Plan Failed':'#E74C3C'})
    st.plotly_chart(fig1, use_container_width=True)

with c2:
    # Logic: Adhoc Ownership
    adhoc_df = df[df['actual_billing_basis'] == 'Adhoc']
    if not adhoc_df.empty:
        fig2 = px.pie(adhoc_df, names='adhoc_owner', hole=0.5,
                      title="<b>Adhoc Responsibility</b>",
                      color_discrete_map={'Zepto Issue':'#F39C12', 'Vendor Issue':'#3498DB'})
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No Adhoc trips.")

with c3:
    # Logic: Cancellation Ownership
    cancel_df = df[df['trip_status'] == 'CANCELLED']
    if not cancel_df.empty:
        fig3 = px.pie(cancel_df, names='cancel_owner', hole=0.5,
                      title="<b>Cancellation Responsibility</b>",
                      color_discrete_map={'Zepto Issue':'#D35400', 'Vendor Issue':'#7F8C8D'})
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("No Cancelled trips.")

# --- 7. EXTRA ANALYSIS: VENDOR PERFORMANCE ---
st.subheader("🚛 Vendor Performance (Failure Contribution)")
vendor_stats = df.groupby('actual_vendor').agg(
    Adhocs=('actual_billing_basis', lambda x: (x == 'Adhoc').sum()),
    Cancellations=('trip_status', lambda x: (x == 'CANCELLED').sum())
).reset_index()
vendor_stats['Total_Failures'] = vendor_stats['Adhocs'] + vendor_stats['Cancellations']

fig_vendor = px.bar(vendor_stats.sort_values('Total_Failures', ascending=False).head(10), 
                    x='actual_vendor', y=['Adhocs', 'Cancellations'],
                    title="Top 10 Vendors by Adhocs & Cancellations",
                    barmode='group', color_discrete_sequence=['#F39C12', '#7F8C8D'])
st.plotly_chart(fig_vendor, use_container_width=True)