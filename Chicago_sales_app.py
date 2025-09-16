import streamlit as st
import pandas as pd
import pydeck as pdk
from oauth2client.service_account import ServiceAccountCredentials
import gspread
from datetime import datetime

st.set_page_config(page_title="Chicago Sales Map", layout="wide")

SHEET_NAME = "Chicago_Heatmap_Data"

# -----------------------------
# PASSWORD PROTECTION
# -----------------------------
st.sidebar.header("Login")
password = st.sidebar.text_input("Enter password", type="password")

if password != st.secrets["app_password"]:
    st.error("Unauthorized. Please enter the correct password.")
    st.stop()

# -----------------------------
# GOOGLE SHEETS CONNECTION
# -----------------------------
@st.cache_resource
def connect_gsheet():
    scope = ["https://spreadsheets.google.com/feeds",
             "https://www.googleapis.com/auth/drive"]

    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        dict(st.secrets["gcp_service_account"]), scope
    )
    client = gspread.authorize(creds)
    return client.open(SHEET_NAME).sheet1

sheet = connect_gsheet()

# -----------------------------
# DATA LOADING
# -----------------------------
@st.cache_data(ttl=300)
def load_data():
    vals = sheet.get_all_values()
    if not vals:
        return pd.DataFrame(columns=["Name","Latitude","Longitude","Sales","Category","AddedBy","Timestamp"])
    df = pd.DataFrame(vals[1:], columns=vals[0])
    df["Sales"] = pd.to_numeric(df["Sales"], errors="coerce")
    df["Latitude"] = pd.to_numeric(df["Latitude"], errors="coerce")
    df["Longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")
    if "Timestamp" in df.columns:
        df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    return df.dropna(subset=["Latitude","Longitude"])

def append_row(name, lat, lng, sales, category, added_by):
    sheet.append_row([name, float(lat), float(lng), float(sales), category, added_by, datetime.utcnow().isoformat()])

# Load once into session state
if "df" not in st.session_state:
    with st.spinner("Loading data..."):
        st.session_state.df = load_data()

df = st.session_state.df

# -----------------------------
# SIDEBAR: ADD LOCATION
# -----------------------------
st.sidebar.header("Add a Location")
with st.sidebar.form("add_form", clear_on_submit=True):
    name = st.text_input("Name*", placeholder="Business or location")
    lat = st.text_input("Latitude*")
    lng = st.text_input("Longitude*")
    sales = st.number_input("Sales ($)", min_value=0.0, step=10.0)
    category = st.selectbox("Category*", ["Deli", "Grocery", "Hotel", "Restaurant", "Other"])
    you = st.text_input("Your name", placeholder="optional")
    submit = st.form_submit_button("Add to sheet")

if submit:
    if not name or not lat or not lng or sales <= 0:
        st.sidebar.error("Please enter name, lat, lng, category, and positive sales.")
    else:
        try:
            append_row(name, lat, lng, sales, category, you)
            st.sidebar.success("Added! Press 'Refresh data' to see it.")
        except Exception as e:
            st.sidebar.error(f"Error: {e}")

# -----------------------------
# REFRESH BUTTON
# -----------------------------
if st.sidebar.button("Refresh data"):
    load_data.clear()
    with st.spinner("Refreshing data..."):
        st.session_state.df = load_data()
    df = st.session_state.df

# -----------------------------
# FILTERING OPTIONS
# -----------------------------
if not df.empty:
    all_categories = sorted(df["Category"].dropna().unique())
    selected_categories = st.sidebar.multiselect(
        "Filter by Category", 
        options=all_categories, 
        default=all_categories
    )
    df = df[df["Category"].isin(selected_categories)]

    min_sales, max_sales = int(df["Sales"].min()), int(df["Sales"].max())
    sales_range = st.sidebar.slider("Filter by Sales ($)", min_sales, max_sales, (min_sales, max_sales))
    df = df[(df["Sales"] >= sales_range[0]) & (df["Sales"] <= sales_range[1])]

    if "Timestamp" in df.columns and df["Timestamp"].notna().any():
        min_date, max_date = df["Timestamp"].min(), df["Timestamp"].max()
        date_range = st.sidebar.date_input("Filter by Date Range", [min_date, max_date])
        if isinstance(date_range, list) and len(date_range) == 2:
            start_date, end_date = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
            df = df[(df["Timestamp"] >= start_date) & (df["Timestamp"] <= end_date)]

# -----------------------------
# CATEGORY COLORS
# -----------------------------
category_colors = {
    "Deli": [0, 0, 255],       # Blue
    "Grocery": [0, 200, 0],    # Green
    "Hotel": [128, 0, 128],    # Purple
    "Restaurant": [255, 0, 0], # Red
    "Other": [255, 165, 0]     # Orange
}

df["color"] = df["Category"].map(category_colors)
df["color"] = df["color"].apply(lambda x: x if isinstance(x, list) else [200, 200, 200])

# -----------------------------
# BUILD PYDECK MAP
# -----------------------------
if not df.empty:
    st.markdown("### Chicago Sales Map")

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=df,
        get_position=["Longitude", "Latitude"],
        get_radius="Sales",
        radius_scale=20,
        get_fill_color="color",
        pickable=True
    )

    view_state = pdk.ViewState(
        latitude=41.8781,
        longitude=-87.6298,
        zoom=11,
        pitch=0,
    )

    tooltip = {"html": "<b>{Name}</b><br>Sales: ${Sales}<br>Category: {Category}<br>Added by: {AddedBy}", "style": {"color": "white"}}

    r = pdk.Deck(layers=[layer], initial_view_state=view_state, map_style="mapbox://styles/mapbox/dark-v10", tooltip=tooltip)

    st.pydeck_chart(r)

# -----------------------------
# SUMMARY
# -----------------------------
if not df.empty:
    st.markdown("### Summary by Category")
    summary = df.groupby("Category").agg(
        Locations=("Name", "count"),
        Total_Sales=("Sales", "sum")
    ).reset_index()
    st.dataframe(summary)

st.markdown("### Current Data")
st.dataframe(df)

st.download_button(
    "Download CSV",
    data=df.to_csv(index=False).encode("utf-8"),
    file_name="chicago_sales.csv",
    mime="text/csv"
)













