import streamlit as st
import pandas as pd
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from oauth2client.service_account import ServiceAccountCredentials
import gspread
from datetime import datetime
import itertools

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


@st.cache_data(ttl=60)
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

# Use spinner only when calling the function
with st.spinner("Loading data..."):
    df = load_data()

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
            st.sidebar.success("Added! Refresh to see it on map.")
            load_data.clear()
            df = load_data()
        except Exception as e:
            st.sidebar.error(f"Error: {e}")

# -----------------------------
# REFRESH BUTTON
# -----------------------------
if st.button("Refresh data"):
    df = load_data()

# -----------------------------
# FILTERING OPTIONS
# -----------------------------
if not df.empty:
    # Category filter
    all_categories = sorted(df["Category"].dropna().unique())
    selected_categories = st.sidebar.multiselect(
        "Filter by Category", 
        options=all_categories, 
        default=all_categories
    )
    df = df[df["Category"].isin(selected_categories)]

    # Sales range filter
    min_sales, max_sales = int(df["Sales"].min()), int(df["Sales"].max())
    sales_range = st.sidebar.slider("Filter by Sales ($)", min_sales, max_sales, (min_sales, max_sales))
    df = df[(df["Sales"] >= sales_range[0]) & (df["Sales"] <= sales_range[1])]

    # Time filter
    if "Timestamp" in df.columns and df["Timestamp"].notna().any():
        min_date, max_date = df["Timestamp"].min(), df["Timestamp"].max()
        date_range = st.sidebar.date_input("Filter by Date Range", [min_date, max_date])
        if isinstance(date_range, list) and len(date_range) == 2:
            start_date, end_date = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
            df = df[(df["Timestamp"] >= start_date) & (df["Timestamp"] <= end_date)]

# -----------------------------
# BUILD MAP
# -----------------------------
m = folium.Map(
    location=[41.8781, -87.6298],
    zoom_start=11,
    tiles="CartoDB dark_matter",
    attr="CartoDB Dark Matter"
)

try:
    folium.GeoJson(
        "https://data.cityofchicago.org/resource/ewy2-6yfk.geojson",
        name="Chicago Boundary",
        style_function=lambda x: {"color": "white", "weight": 2, "fillOpacity": 0}
    ).add_to(m)
except:
    pass

try:
    folium.GeoJson(
        "https://raw.githubusercontent.com/blackmad/neighborhoods/master/chicago.geojson",
        name="Neighborhoods",
        style_function=lambda x: {"color": "lightgray", "weight": 1, "fillOpacity": 0}
    ).add_to(m)
except:
    pass

# -----------------------------
# MAP VIEW OPTIONS
# -----------------------------
view_type = st.radio("Map view:", ["Markers", "Heatmap"], horizontal=True)

category_colors = {
    "Deli": "blue",
    "Grocery": "green",
    "Hotel": "purple",
    "Restaurant": "red",
    "Other": "orange"
}
color_cycle = itertools.cycle(["cadetblue","pink","darkred","darkblue","darkgreen","lightgray","black"])
for cat in df["Category"].dropna().unique():
    if cat not in category_colors:
        category_colors[cat] = next(color_cycle)

# -----------------------------
# ADD MARKERS OR HEATMAP
# -----------------------------
if not df.empty:
    if view_type == "Markers":
        for _, r in df.iterrows():
            popup_html = f"""
            <div style="font-size:14px">
                <b>{r['Name']}</b><br>
                Sales: ${r['Sales']}<br>
                Category: {r.get('Category','Other')}<br>
                {r.get('AddedBy','')}
            </div>
            """
            folium.CircleMarker(
                location=[r["Latitude"], r["Longitude"]],
                radius=max(4, r["Sales"] / df["Sales"].max() * 15),
                color=category_colors.get(r.get("Category","Other"), "gray"),
                fill=True,
                fill_opacity=0.7,
                popup=folium.Popup(popup_html, max_width=250)
            ).add_to(m)
    else:
        heat_data = df[["Latitude","Longitude","Sales"]].values.tolist()
        HeatMap(heat_data, radius=15, blur=10, max_zoom=12).add_to(m)

# -----------------------------
# DYNAMIC LEGEND
# -----------------------------
def add_legend(map_obj, category_colors, df):
    categories_present = df["Category"].dropna().unique()
    legend_items = ""
    for cat in categories_present:
        color = category_colors.get(cat, "gray")
        legend_items += f"""
        <i style="background:{color}; width:12px; height:12px; 
        float:left; margin-right:8px; opacity:0.7;"></i>{cat}<br>"""

    legend_html = f"""
    <div style="
        position: fixed; 
        bottom: 50px; left: 50px; width: 200px; 
        background-color: rgba(0, 0, 0, 0.6);
        border-radius: 8px;
        z-index:9999; 
        font-size:14px;
        color: white;
        padding: 10px;
        line-height: 18px;
    ">
    <b>Category Legend</b><br>
    {legend_items}
    </div>
    """
    map_obj.get_root().html.add_child(folium.Element(legend_html))

if not df.empty:
    add_legend(m, category_colors, df)

folium.LayerControl(collapsed=True).add_to(m)

# -----------------------------
# STREAMLIT OUTPUT
# -----------------------------
st.markdown("### Chicago Sales Map")
st_folium(m, width=1100, height=650)

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
# -----------------------------
# REMOVE GREY FADE OVERLAY
# -----------------------------
st.markdown("""
    <style>
    .stApp > div:first-child {
        opacity: 1 !important;
    }
    .stSpinner {
        background: none !important;
    }
    </style>
    """, unsafe_allow_html=True)




