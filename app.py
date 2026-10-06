import streamlit as st
import pandas as pd
import os
import requests
import urllib.parse
import re

st.set_page_config(page_title="Dubizzle Lead Prospector", page_icon="🚀", layout="wide")

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

def fetch_real_leads_ddg(selected_districts, max_results):
    output_file = "car_dealers_leads.xlsx"
    if not selected_districts:
        return None, "⚠️ يرجى اختيار منطقة واحدة على الأقل."

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    real_records = []
    seen_titles = set()
    target_per_district = max(5, int(max_results // len(selected_districts)))

    for district in selected_districts:
        main_city = district.split(" - ")[0]
        area_name = district.split(" - ")[-1]

        # استعلامات بحث واقعية ومباشرة
        queries = [
            f"معرض سيارات {area_name} {main_city}",
            f"معارض سيارات في {area_name}",
            f"أوتو {area_name} سيارات"
        ]

        district_count = 0
        for q in queries:
            if district_count >= target_per_district or len(real_records) >= max_results:
                break

            url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(q)}"
            
            try:
                res = requests.get(url, headers=headers, timeout=10)
                if res.status_code == 200:
                    # البحث عن العناوين المباشرة والنصوص
                    snippets = re.findall(r'<a class="result__url"[^>]*>(.*?)</a>.*?<a class="result__snippet"[^>]*>(.*?)</a>', res.text, re.DOTALL)
                    titles = re.findall(r'<a class="result__a"[^>]*>(.*?)</a>', res.text, re.DOTALL)

                    for idx, raw_title in enumerate(titles):
                        clean_title = re.sub(r'<[^>]+>', '', raw_title).strip()
                        clean_title = clean_title.replace("...": "", "").replace("-", " ").strip()

                        if ("معرض" in clean_title or "سيارات" in clean_title or "أوتو" in clean_title or "Motors" in clean_title):
                            if clean_title not in seen_titles and len(clean_title) < 60:
                                seen_titles.add(clean_title)

                                # استخراج أرقام الهواتف إن وجدت في النص المرفق
                                snippet_text = re.sub(r'<[^>]+>', '', snippets[idx][1]) if idx < len(snippets) else ""
                                phone_match = re.search(r'(01[0125]\d{8})', snippet_text)
                                phone = phone_match.group(1) if phone_match else "غير مدون برقم مباشر"

                                maps_url = f"https://www.google.com/maps/search/{urllib.parse.quote(clean_title + ' ' + area_name)}"
                                address = f"{area_name}، {main_city}"

                                score = 85 if phone != "غير مدون برقم مباشر" else 65

                                real_records.append({
                                    "title": clean_title,
                                    "city": main_city,
                                    "address": address,
                                    "phone": phone,
                                    "link": maps_url,
                                    "has_dubizzle_presence": "يحتاج مراجعة",
                                    "lead_score": f"{score}/100"
                                })
                                district_count += 1
                                if district_count >= target_per_district or len(real_records) >= max_results:
                                    break
            except Exception:
                continue

    if not real_records:
        return None, "❌ تعذر جلب البيانات حالياً، يرجى المحاولة مرة أخرى."

    final_df = pd.DataFrame(real_records)
    final_df.to_excel(output_file, index=False)
    return final_df, f"✅ تم استخراج {len(final_df)} معرض حقيقي ومباشر بنجاح!"

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
        
        if phone.startswith("01") and len(phone) == 11:
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
st.title("🚀 Dubizzle Lead Prospector")
st.markdown("استخراج المعارض الحقيقية مباشرة وتجهيز حملة التواصل عبر الواتساب.")

col1, col2 = st.columns(2)

with col1:
    cities_input = st.multiselect(
        "📌 اختر المناطق المطلوبة", 
        options=DISTRICT_OPTIONS, 
        default=["القاهرة - مصر الجديدة والنزهة"]
    )
    max_results_input = st.number_input("العدد المطلوب", min_value=5, max_value=200, value=20, step=5)

with col2:
    msg_style_input = st.radio(
        "🎯 نبرة رسالة الواتساب", 
        options=["ترويجي مباشر (Promotional)", "عروض رسمية (Formal Offer)"], 
        index=0
    )

col_btn1, col_btn2 = st.columns(2)

with col_btn1:
    btn_prospect = st.button("🚀 1. ابدأ الجمع الحقيقي (Start Prospecting)", use_container_width=True)

with col_btn2:
    btn_outreach = st.button("💬 2. تجهيز حملة الواتساب", use_container_width=True)

if btn_prospect:
    with st.spinner("جاري السحب الحقيقي لجلب المعارض..."):
        df, msg = fetch_real_leads_ddg(cities_input, max_results_input)
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
