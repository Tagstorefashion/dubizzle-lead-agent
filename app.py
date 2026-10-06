import streamlit as st
import pandas as pd
import os
import urllib.parse
from modules.dubizzle import discover_dealers, verify_all_platforms, extract_mobile_phone

st.set_page_config(page_title="Dubizzle Lead Prospector", page_icon="🚀", layout="wide")

DISTRICT_OPTIONS = [
    "مدينة نصر",
    "مصر الجديدة",
    "المعادي",
    "التجمع الخامس",
    "المهندسين",
    "الدقي",
    "فيصل",
    "الهرم",
    "6 أكتوبر",
    "الشيخ زايد"
]

def run_prospector(district, max_results):
    # جلب المعارض من الأدلة عبر الموديول
    raw_dealers = discover_dealers(district, max_results)
    
    if not raw_dealers:
        return None, "⚠️ لم يتم العثور على معارض في هذه المنطقة حالياً."

    processed_data = []
    
    for dealer in raw_dealers:
        name = dealer.get("اسم المعرض", "")
        raw_phone = dealer.get("الهاتف", "")
        nearby_text = dealer.get("وصف المصدر", "")
        
        # 1. محاولة استخراج رقم موبايل (01x) حقيقي أولاً بدلاً من الأرضي
        mobile = extract_mobile_phone(f"{raw_phone} {nearby_text}")
        if mobile == "غير متاح" and raw_phone:
            mobile = raw_phone

        # 2. توليد رابط الخريطة المباشر
        maps_link = f"https://www.google.com/maps/search/{urllib.parse.quote(name + ' ' + district)}"

        # 3. التحقق المباشر من منصات الإعلانات باسم المعرض
        verification = verify_all_platforms(name, district)

        processed_data.append({
            "المعرض": name,
            "المنطقة": district,
            "الموبايل": mobile,
            "رابط الخريطة": maps_link,
            "Facebook": verification["facebook"],
            "Dubizzle": verification["dubizzle"],
            "Dubizzle Results": verification["dubizzle_results"],
            "ContactCars": verification["contactcars"],
            "ContactCars Results": verification["contactcars_results"],
        })

    df = pd.DataFrame(processed_data)
    df.to_excel("car_dealers_leads.xlsx", index=False)
    return df, f"✅ تم استخراج وتأهيل {len(df)} معرض بنجاح!"

# --- الواجهة ---
st.title("🚀 Dubizzle Lead Prospector & Verification Agent")

col1, col2 = st.columns(2)

with col1:
    selected_district = st.selectbox("📌 اختر المنطقة", options=DISTRICT_OPTIONS)

with col2:
    max_count = st.number_input("العدد المطلوب", min_value=5, max_value=200, value=20, step=5)

if st.button("🚀 ابدأ البحث والتأهيل الحقيقي", use_container_width=True):
    with st.spinner("جاري استخراج المعارض وفحص أرقام الموبايل والمنصات..."):
        df_res, msg = run_prospector(selected_district, max_count)
        if df_res is not None:
            st.success(msg)
            
            # كروت الإحصائيات الفعالة
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("📊 إجمالي النتائج", len(df_res))
            c2.metric("📞 أرقام محمول", len(df_res[df_res['الموبايل'].str.startswith('01', na=False)]))
            c3.metric("🔵 Facebook نشط", len(df_res[df_res['Facebook'].str.contains('موجود', na=False)]))
            c4.metric("🟣 Dubizzle مشترك", len(df_res[df_res['Dubizzle'].str.contains('مشترك', na=False)]))
            
            st.dataframe(df_res, use_container_width=True)
            
            with open("car_dealers_leads.xlsx", "rb") as file:
                st.download_button(
                    label="📥 تحميل شيت البيانات الكامل للإكسيل",
                    data=file,
                    file_name="car_dealers_leads.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.error(msg)
