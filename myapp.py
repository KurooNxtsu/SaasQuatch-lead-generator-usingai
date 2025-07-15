import streamlit as st
import requests
import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import google.generativeai as genai

# === Gemini API Config ===
GEMINI_API_KEY = "AIzaSyBWYlnSLRZvdgB3I1dcH6IOCz6K7y6swb8"
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemma-3-27b-it")

def evaluate_lead_with_gemini(lead):
    prompt = f"""
You are a highly skilled B2B sales analyst.

Analyze the following company in detail and return a 3–5 sentence business summary highlighting:
1. What the company likely specializes in (based on its name, industry, and website).
2. What kind of problems or inefficiencies they may face.
3. Why they are a strong or weak sales lead.
4. How we could best approach them with our product/service offering.

Company: {lead['Company']}
Industry: {lead['Industry']}
Address: {lead['Address']}
BBB Rating: {lead['BBB Rating']}
Website: {lead['Website']}

Write this like a mini-profile for a sales team to quickly understand the opportunity.
"""
    try:
        response = gemini_model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"❌ Gemini API failed: {e}"

def verify_saasquatch_login(email, password):
    try:
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--log-level=3")
        options.add_argument("--window-size=1920,1080")

        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        driver.get("https://app.saasquatchleads.com/auth")

        wait = WebDriverWait(driver, 15)
        email_input = wait.until(EC.presence_of_element_located((By.XPATH, '//input[@type="email"]')))
        password_input = driver.find_element(By.XPATH, '//input[@type="password"]')

        email_input.send_keys(email)
        password_input.send_keys(password)
        password_input.send_keys(Keys.RETURN)

        wait.until(EC.url_to_be("https://app.saasquatchleads.com/"))
        time.sleep(3)

        cdp_cookies = driver.execute_cdp_cmd("Network.getAllCookies", {})["cookies"]
        session_cookie = next((c["value"] for c in cdp_cookies if c["name"] == "session"), None)
        driver.quit()

        return True, session_cookie if session_cookie else None

    except Exception as e:
        print("❌ Login error:", e)
        driver.quit()
        return False, None

def clean(value):
    return value.strip().lower() if isinstance(value, str) else ""

def fetch_leads(session_cookie, industry, location):
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://app.saasquatchleads.com",
        "Referer": "https://app.saasquatchleads.com/",
        "User-Agent": "Mozilla/5.0"
    }
    cookies = {"session": session_cookie}
    payload = {"industry": industry, "location": location, "page": 1}
    url = "https://data.saasquatchleads.com/api/lead_scrape"

    try:
        r = requests.post(url, json=payload, headers=headers, cookies=cookies)
        r.raise_for_status()
        leads_data = r.json()

        high, medium, low = [], [], []

        for lead in leads_data:
            company = lead.get("company", "").strip()
            industry = lead.get("industry", "").strip()
            address = lead.get("address", "").strip()
            bbb_rating = clean(lead.get("bbb_rating", ""))
            phone = lead.get("phone", "").strip()
            website = clean(lead.get("website", ""))

            lead_info = {
                "Company": company,
                "Industry": industry,
                "Address": address,
                "BBB Rating": bbb_rating,
                "Phone": phone,
                "Website": website
            }

            has_rating = bbb_rating not in ("", "n/a", "na", "none")
            has_website = website not in ("", "n/a", "na", "none")

            if has_rating and has_website:
                high.append(lead_info)
            elif has_website:
                medium.append(lead_info)
            else:
                low.append(lead_info)

        return high, medium, low

    except Exception as e:
        st.error(f"Failed to fetch leads: {e}")
        return [], [], []

# === STREAMLIT APP ===
st.set_page_config(page_title="Lead Evaluator", layout="wide")

if "authenticated" not in st.session_state:
    st.title("🔐 SaaSquatch Leads Login")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        with st.spinner("Logging in..."):
            success, session_cookie = verify_saasquatch_login(email, password)
            if success and session_cookie:
                st.session_state.authenticated = True
                st.session_state.session_cookie = session_cookie
                st.success("✅ Logged in successfully!")
                st.rerun()
            else:
                st.error("❌ Invalid email or password.")
    st.stop()

st.title("🔍 Find Leads")
industry = st.text_input("Business Type / Industry", "Software")
location = st.text_input("Location", "New York")

if st.button("Fetch Leads"):
    with st.spinner("Fetching leads from SaaSquatch..."):
        high_p, med_p, low_p = fetch_leads(st.session_state.session_cookie, industry, location)
        st.session_state.high_p = high_p
        st.session_state.med_p = med_p
        st.session_state.low_p = low_p
        st.success(f"✅ Found {len(high_p)} high, {len(med_p)} medium, {len(low_p)} low potential leads")

# Show leads if they exist in session_state
if "high_p" in st.session_state:
    high_p = st.session_state.high_p
    med_p = st.session_state.med_p
    low_p = st.session_state.low_p

    # === HIGH POTENTIAL ===
    if high_p:
        st.subheader("🔥 High Potential Leads")
        for i, lead in enumerate(high_p):
            company_key = lead['Company'].strip().lower().replace(" ", "_").replace(".", "_")
            key = f"reason_high_{company_key}_{i}"

            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f"**{lead['Company']}** - {lead['Industry']} - {lead['Website']}")
            with col2:
                if st.button("🔎 Why might this be a good lead?", key=key):
                    with st.spinner("Generating reasoning..."):
                        st.session_state[key + "_text"] = evaluate_lead_with_gemini(lead)

            if key + "_text" in st.session_state:
                _, center_col, _ = st.columns([1, 3, 1])
                with center_col:
                    st.info(st.session_state[key + "_text"])

    # === MEDIUM POTENTIAL ===
    with st.expander("⚖️ Medium Potential Leads"):
        for i, lead in enumerate(med_p):
            company_key = lead['Company'].strip().lower().replace(" ", "_").replace(".", "_")
            key = f"reason_med_{company_key}_{i}"

            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f"**{lead['Company']}** - {lead['Industry']} - {lead['Website']}")
            with col2:
                if st.button("🔎 Why might this be a good lead?", key=key):
                    with st.spinner("Generating reasoning..."):
                        st.session_state[key + "_text"] = evaluate_lead_with_gemini(lead)

            if key + "_text" in st.session_state:
                _, center_col, _ = st.columns([1, 3, 1])
                with center_col:
                    st.info(st.session_state[key + "_text"])

    # === LOW POTENTIAL ===
    with st.expander("❌ Low Potential Leads"):
        df_low = pd.DataFrame(low_p)
        st.dataframe(df_low)

    # === DOWNLOAD ALL LEADS ===
    all_leads_df = pd.DataFrame(high_p + med_p + low_p)
    csv = all_leads_df.to_csv(index=False).encode('utf-8')
    st.download_button("⬇️ Download All Leads as CSV", data=csv, file_name="all_leads.csv", mime="text/csv")
