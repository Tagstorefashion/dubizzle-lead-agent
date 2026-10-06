import streamlit as st
import pandas as pd
import os
import requests
import urllib.parse
from bs4 import BeautifulSoup

st.set_page_config(page_title="Dubizzle Real Lead Prospector", page_icon="🚀", layout="wide")

DISTRICT_OPTIONS = [
    "القاهرة - مدينة نصر",
    "القاهرة - التجمع الخامس والجديدة",
    "القاهرة - المعادي",
    "القاهرة - مصر الجديدة والنزهة",
    "القاهرة - شبرا ووسط البلد",
    "الجيزة - المهندسين والدقي",
    "الجيزة - فيصل والهرم",
    "الجيزة - 6 أكتوبر والشيخ زايد"
]

STREETS_SEARCH = {
    "مدينة نصر": ["شارع الطيران", "شارع عباس العقاد", "شارع مكرم عبيد", "شارع مصطفى النحاس", "طريق النصر"],
    "التجمع الخامس والجديدة": ["شارع التسعين الشمالي", "شارع التسعين الجنوبي", "منطقة البنوك التجمع"],
    "المعادي": ["شارع 9 المعادي", "شارع النصر المعادي", "كورنيش المعادي"],
    "مصر الجديدة والنزهة": ["شارع الميرغني", "شارع الأهرام مصر الجديدة", "شارع النزهة", "شارع الثورة"],
    "شبرا ووسط البلد": ["شارع شبرا الرئيسي", "شارع رمسيس", "شارع 26 يوليو"],
    "المهندسين والدقي": ["شارع جامعة الدول العربية", "شارع البطل أحمد عبد العزيز", "شارع مصدق"],
    "فيصل والهرم": ["شارع فيصل الرئيسي", "شارع الهرم الرئيسي", "شارع العريش"],
    "6 أكتوبر والشيخ زايد": ["المحور المركزي 6 أكتوبر", "وصلة دهشور", "شارع البستان الشيخ زايد"]
}

def fetch_live_google_leads(selected_districts, max_results):
    output_file = "car_dealers_leads.xlsx"
    if not selected_districts:
        return None, "⚠️ يرجى اختيار منطقة واحدة على الأقل."

    real_records = []
    seen_titles = set()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    for district in selected_districts:
        main_city = district.split(" - ")[0]
        area_name = district.split(" - ")[-1]
        
        search_terms = STREETS_SEARCH.get(area_name, [area_name])
        
        for term in search_terms:
            if len(real_records) >= max_results:
                break
                
            query = f"معرض سيارات {term} {main_city}"
            url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&tbm=lcl"

            try:
                response = requests.get(url, headers=headers, timeout=8)
                soup = BeautifulSoup(response.text, "html.parser")
                
                # كشط الكتل الحقيقية للمعارض من نتائج Google Local
                containers = soup.find_all("div", class_="VkpO2e") or soup.find_all("div", class_="uE308c")
                
                for item in containers:
                    title_elem = item.find("div", class_="dbg0pd") or item.find("span", class_="OSrJ2e")
                    phone_elem = item.find("span", class_="LrzI1b") or item.find("div", class_="rllt__details")
                    
                    if title_elem:
                        title = title_elem.text.strip()
                        if title and title not in seen_titles:
                            seen_titles.add(title)
                            
                            # أخذ رقم التليفون المباشر إن وجد أو صياغة طلب بحث هاتف دقيق
                            phone_raw = phone_elem.text.strip() if phone_elem else ""
                            phone = "".join(filter(str.isdigit, phone_raw))
                            if not phone or len(phone) < 9:
                                phone = "غير مدون على الخريطة"

                            maps_link = f"https://www.google.com/maps/search/{urllib.parse.quote(title + ' ' + area_name)}"
                            address = f"{term}، {area_name}، {main_city}"
                            
                            # حساب Lead Score حقيقي بناءً على اكتمال البيانات
                            score = 85 if phone != "غير مدون على الخريطة" else 60

                            real_records.append({
                                "title": title,
                                "city": main_city,
                                "address": address,
                                "phone": phone,
                                "link": maps_link,
                                "has_dubizzle_presence": "يحتاج مراجعة",
                                "lead_score": f"{score}/100"
                            })
                            
                            if len(real_records) >= max_results:
                                break
            except Exception:
                continue

    if not real_records:
        return None, "❌ تعذر جلب نتائج حية حالياً من جوجل، يرجى إعادة المحاولة بعد لحظات."

    final_df = pd.DataFrame(real_records)
    final_df.to_excel(output_file, index=False)
    return final_df, f"✅ تم جلب {len(final_df)} معرض حقيقي ومباشر بنجاح!"

def run_outreach_direct(msg_type):
    leads_file = "car_dealers_leads.xlsx"
    campaign_file = "ready_whatsapp_campaign.xlsx"
    
    if not os.path.exists(leads_file):
        return None, "❌ لم يتم العثور على ملف البيانات، يرجى تشغيل الجمع أولاً."

    df = pd.read_excel(leads_file)
    if df.empty:
        return None, "❌ ملف البيانات فارغ، يرجى تشغيل الجمع أولاً."

    campaign_data = []
    for _, row in df.iterrows():
        title = str(row.get("title", "")).strip()
        phone = str(row.get("phone", "")).strip()
        city = str(row.get("city", "")).strip()
        address = str(row.get("address", "")).strip()
        maps_link = str(row.get("link", "")).strip()
        score = str(row.get("lead_score", "70/100")).strip()
        
        if msg_type == "عروض رسمية (Formal Offer)":
            msg = f"تحياتنا لحضرتك {title} 👋، بنتابع مع سيادتكم من دوبيزل لتطوير باقة المتاجر وترقية المشتركين في {city}."
        else:
            msg = f"مساء الخير {title} 👋، فريق مبيعات دوبيزل معاك! حابين نعرض عليك فرصة إدراج معارضكم معنا وعرض سياراتكم لأكثر من 5 مليون زيارة شهرياً."
            
        encoded_msg = urllib.parse.quote(msg)
        
        if phone != "غير مدون على الخريطة" and len(phone) >= 10:
            wa_link = f"https://wa.me/2{phone}?text={encoded_msg}"
        else:
            wa_link = "يتطلب مراجعة الرقم"
        
        campaign_data.append({
            "اسم المعرض الحقيقي": title,
            "المدينة": city,
            "العنوان التفصيلي": address,
            "رقم الموبايل": phone,
            "تقييم الجاهزية (Lead Score)": score,
            "رابط الخريطة GPS المباشر": maps_link,
            "رسالة الواتساب": msg,
            "رابط الواتساب المباشر": wa_link
        })

    campaign_df = pd.DataFrame(campaign_data)
    campaign_df.to_excel(campaign_file, index=False)
    return campaign_df, f"✅ تم تجهيز حملة الواتساب بنجاح! عدد المعارض: {len(campaign_df)}"

# --- Streamlit UI ---
st.title("🚀 Dubizzle Live Lead Prospector (Real Data)")
st.markdown("استخراج حقيقي ومباشر للمعارض الموجودة حالياً على Google Maps.")

col1, col2 = st.columns(2)

with col1:
    cities_input = st.multiselect(
        "📌 اختر المناطق المطلوبة", 
        options=DISTRICT_OPTIONS, 
        default=["القاهرة - مصر الجديدة والنزهة"]
    )
    max_results_input = st.number_input("العدد المطلوب", min_value=5, max_value=200, value=30, step=5)

with col2:
    msg_style_input = st.radio(
        "🎯 نبرة رسالة الواتساب", 
        options=["ترويجي مباشر (Promotional)", "عروض رسمية (Formal Offer)"], 
        index=0
    )

col_btn1, col_btn2 = st.columns(2)

with col_btn1:
    btn_prospect = st.button("🚀 1. ابدأ السحب المباشر (Live Scrape)", use_container_width=True)

with col_btn2:
    btn_outreach = st.button("💬 2. تجهيز حملة الواتساب", use_container_width=True)

if btn_prospect:
    with st.spinner("جاري التواصل مع محرك الخرائط وجلب البيانات الحية..."):
        df, msg = fetch_live_google_leads(cities_input, max_results_input)
        if df is not None:
            st.success(msg)
            st.dataframe(df)
        else:
            st.error(msg)

if btn_outreach:
    with st.spinner("جاري إعداد الرسائل والروابط..."):
        df_out, msg = run_outreach_direct(msg_style_input)
        if df_out is not None:
            st.success(msg)
            st.dataframe(df_out)
            
            with open("ready_whatsapp_campaign.xlsx", "rb") as file:
                st.download_button(
                    label="📥 تحميل ملف الإكسيل للواتساب",
                    data=file,
                    file_name="ready_whatsapp_campaign.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.error(msg)
