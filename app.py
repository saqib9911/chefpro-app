import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
from datetime import datetime
import hashlib


# --- DATABASE INITIALIZATION ---
def init_db():
    conn = sqlite3.connect('chefpro_v3.db', check_same_thread=False)
    c = conn.cursor()
    # Users Table
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, kitchen_name TEXT)''')
    # Inventory Table
    c.execute(
        '''CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY, user TEXT, item TEXT, qty REAL, unit TEXT, price REAL)''')
    # Recipes Table
    c.execute(
        '''CREATE TABLE IF NOT EXISTS recipes (id INTEGER PRIMARY KEY, user TEXT, name TEXT, cost REAL, price REAL)''')
    # Sales Table
    c.execute(
        '''CREATE TABLE IF NOT EXISTS sales (id INTEGER PRIMARY KEY, user TEXT, recipe_name TEXT, profit REAL, date TEXT)''')
    conn.commit()
    return conn


conn = init_db()
c = conn.cursor()


# --- HELPER FUNCTIONS ---
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()


def check_hashes(password, hashed_text):
    if make_hashes(password) == hashed_text:
        return hashed_text
    return False


# --- UI CONFIG ---
st.set_page_config(page_title="ChefPro Enterprise", layout="wide")

# --- AUTHENTICATION SYSTEM ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    auth_mode = st.sidebar.selectbox("Login / Signup", ["Login", "Sign Up"])
    if auth_mode == "Sign Up":
        st.subheader("🆕 Create Professional Account")
        new_user = st.text_input("Username")
        new_kitchen = st.text_input("Kitchen/Bakery Name")
        new_pass = st.text_input("Password", type='password')
        if st.button("Register"):
            c.execute('INSERT INTO users VALUES (?,?,?)', (new_user, make_hashes(new_pass), new_kitchen))
            conn.commit()
            st.success("Account Created! Please Login.")
    else:
        st.subheader("🔑 Member Login")
        user = st.text_input("Username")
        password = st.text_input("Password", type='password')
        if st.button("Login"):
            c.execute('SELECT password FROM users WHERE username = ?', (user,))
            data = c.fetchone()
            if data and check_hashes(password, data[0]):
                st.session_state.logged_in = True
                st.session_state.user = user
                st.rerun()
            else:
                st.error("Invalid Username/Password")
    st.stop()

# --- LOGGED IN AREA ---
user = st.session_state.user
st.sidebar.title(f"👨‍🍳 {user.capitalize()}'s Kitchen")
menu = ["📊 Dashboard", "📦 Inventory", "🥣 Recipe Builder", "💰 Sales History", "⚙️ Settings"]
choice = st.sidebar.radio("Navigation", menu)

# --- 1. DASHBOARD ---
if choice == "📊 Dashboard":
    st.header("Business Analytics")

    # KPIs
    sales_df = pd.read_sql(f"SELECT * FROM sales WHERE user='{user}'", conn)
    total_profit = sales_df['profit'].sum() if not sales_df.empty else 0
    total_orders = len(sales_df)

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Profit", f"Rs. {total_profit}")
    col2.metric("Total Orders", total_orders)
    col3.metric("Active Inventory Items", len(pd.read_sql(f"SELECT * FROM inventory WHERE user='{user}'", conn)))

    if not sales_df.empty:
        fig = px.line(sales_df, x='date', y='profit', title="Profit Growth Over Time")
        st.plotly_chart(fig, use_container_width=True)

# --- 2. INVENTORY ---
elif choice == "📦 Inventory":
    st.header("Stock Management")
    with st.expander("➕ Add New Stock Item"):
        i_col1, i_col2, i_col3 = st.columns(3)
        item = i_col1.text_input("Item Name (e.g. Flour)")
        qty = i_col2.number_input("Quantity", min_value=0.0)
        unit = i_col3.selectbox("Unit", ["kg", "ltr", "gm", "ml", "pcs", "dozen"])
        price = st.number_input("Total Price Paid", min_value=0.0)

        if st.button("Add to Stock"):
            c.execute("INSERT INTO inventory (user, item, qty, unit, price) VALUES (?,?,?,?,?)",
                      (user, item, qty, unit, price))
            conn.commit()
            st.success(f"{item} added to inventory!")

    st.subheader("Current Stock Levels")
    inv_df = pd.read_sql(f"SELECT item, qty, unit, price FROM inventory WHERE user='{user}'", conn)
    st.dataframe(inv_df, use_container_width=True)

# --- 3. RECIPE BUILDER ---
elif choice == "🥣 Recipe Builder":
    st.header("Costing & Recipe Management")

    # Load inventory items for selection
    inv_data = pd.read_sql(f"SELECT item, price, qty, unit FROM inventory WHERE user='{user}'", conn)

    if inv_data.empty:
        st.warning("Pehle Inventory mein items add karein!")
    else:
        recipe_name = st.text_input("Recipe Name")

        # Build Recipe list
        if 'current_recipe' not in st.session_state:
            st.session_state.current_recipe = []

        c1, c2, c3 = st.columns([2, 1, 1])
        selected_item = c1.selectbox("Select Ingredient", inv_data['item'].tolist())
        used_qty = c2.number_input("Qty Used", min_value=0.0)

        if c3.button("Add"):
            # Get item's base price from DB
            row = inv_data[inv_data['item'] == selected_item].iloc[0]
            # Calculate cost (Price per unit * used_qty)
            cost_per_unit = row['price'] / row['qty']
            item_cost = cost_per_unit * used_qty
            st.session_state.current_recipe.append({"Item": selected_item, "Qty": used_qty, "Cost": item_cost})

        if st.session_state.current_recipe:
            rdf = pd.DataFrame(st.session_state.current_recipe)
            st.table(rdf)

            raw_cost = rdf['Cost'].sum()
            margin = st.slider("Profit Margin (%)", 10, 200, 40)
            selling_price = raw_cost * (1 + margin / 100)

            st.write(f"**Total Cost:** Rs. {round(raw_cost, 2)}")
            st.write(f"**Suggested Selling Price:** Rs. {round(selling_price, 2)}")

            if st.button("Confirm Order / Sale"):
                profit = selling_price - raw_cost
                date_today = datetime.now().strftime("%Y-%m-%d")
                c.execute("INSERT INTO sales (user, recipe_name, profit, date) VALUES (?,?,?,?)",
                          (user, recipe_name, profit, date_today))
                conn.commit()
                st.session_state.current_recipe = []
                st.success("Sale Recorded!")

# --- 4. SALES HISTORY ---
elif choice == "💰 Sales History":
    st.header("Past Orders & Revenue")
    sales_df = pd.read_sql(f"SELECT recipe_name, profit, date FROM sales WHERE user='{user}'", conn)
    st.dataframe(sales_df, use_container_width=True)

    if st.button("Export to CSV"):
        sales_df.to_csv(f"{user}_sales.csv", index=False)
        st.success("File saved as CSV!")

# --- LOGOUT ---
if st.sidebar.button("Logout"):
    st.session_state.logged_in = False
    st.rerun()