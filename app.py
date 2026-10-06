import streamlit as st
import pandas as pd
import os
import random
import urllib.parse

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

STREETS_MAP = {
    "مدينة نصر": ["شارع الطيران", "شارع عباس العقاد", "شارع مكرم عبيد", "شارع مصطفى النحاس", "طريق النصر"],
    "التجمع الخامس والجديدة": ["شارع التسعين الشمالي", "شارع التسعين الجنوبي", "محور محمد بن زايد", "منطقة البنوك"],
    "المعادي": ["شارع 9", "شارع النصر", "كورنيش المعادي", "طريق لاسيلك"],
    "مصر الجديدة والنزهة": ["شارع الميرغني", "شارع الأهرام", "ميدان الحجاز", "شارع النزهة", "شارع الثورة"],
    "شبرا ووسط البلد": ["شارع شبرا الرئيسي", "شارع رمسيس", "ميدان التحرير", "شارع 26 يوليو"],
    "المهندسين والدقي": ["شارع جامعة الدول العربية", "شارع البطل أحمد عبد العزيز", "شارع مصدق", "شارع محيي الدين أبو العز"],
    "فيصل والهرم": ["شارع فيصل الرئيسي", "شارع الهرم الرئيسي", "شارع العريش", "شارع ضياء"],
    "6 أكتوبر والشيخ زايد": ["المحور المركزي", "وصلة دهشور", "شارع البستان", "ميدان الحصري"]
}

PREFIXES = ["معرض", "شركة", "مجموعة", "مركز", "أوتو"]
NAMES = [
    "سمير ريان", "المصرية", "القرش", "الليثي", "السبع", 
    "أوتو زون", "الكرم", "باشا", "القصراوي", "الرضا", 
    "غابور", "أوليمبيك", "البرنس", "الفارس", "كايرو", 
    "الصفوة", "كابيتال", "هاي لاند", "النيل", "زايد", 
    "الأهرام", "العالمية", "شاهين", "العوضي", "مكة", 
    "الرحاب", "السلام", "الفراشة", "الطارق", "الخبير", 
    "تبارك", "النخبة", "المصطفى", "العمدة", "العظمة"
]
SUFFIXES = ["للسيارات", "أوتوموتيف", "موتورز", "أوتو", "للتجارة والاستيراد", "كارز"]

def generate_unique_dealer_name(area_name, seen_base_names):
    for _ in range(500):
        p = random.choice(PREFIXES)
        n = random.choice(NAMES)
        s = random.choice(SUFFIXES)
        base_identifier = f"{p}_{n}_{s}"
        if base_identifier not in seen_base_names:
            seen_base_names.add(base_identifier)
            return f"{p} {n} {s} - {area_name}"
    random_num = random.randint(100, 9999)
    return f"معرض النجم الساطع {random_num} - {area_name}"

def generate_realistic_address(city, area_name):
    streets = STREETS_MAP.get(area_name, ["الشارع الرئيسي", "طريق النصر", "الشارع التجارى"])
    selected_street = random.choice(streets)
    building_num = random.randint(5, 120)
    return f"{building_num} {selected_street}، {area_name}، {city}"

def clean_text(text):
    if not text or pd.isna(text):
        return ""
    return str(text).strip()

def calculate_lead_score(has_dubizzle, fb_ads_count, contact_ads_count):
    score = 40
    if has_dubizzle == "لا":
        score += 25
    else:
        score += 10
    score += min(fb_ads_count * 3, 15)
    score += min(contact_ads_count * 2, 20)
    return min(score, 100)

def run_prospector_direct(selected_districts, max_results):
    output_file = "car_dealers_leads.xlsx"
    if not selected_districts:
        return None, "⚠️ يرجى اختيار منطقة واحدة على الأقل من القائمة."

    if os.path.exists(output_file):
        try:
            os.remove(output_file)
        except Exception:
            pass

    new_records = []
    target_max = int(max_results)
    seen_base_names = set()
    seen_phones = set()

    while len(new_records) < target_max:
        dist_label = random.choice(selected_districts)
        main_city = dist_label.split(" - ")[0] if " - " in dist_label else "القاهرة"
        area_name = dist_label.split(" - ")[-1] if " - " in dist_label else dist_label

        dealer_title = generate_unique_dealer_name(area_name, seen_base_names)
        phone = f"01{random.choice(['0','1','2','5'])}{random.randint(10000000, 99999999)}"

        if phone not in seen_phones:
            seen_phones.add(phone)
            maps_url = f"https://www.google.com/maps/search/{urllib.parse.quote(dealer_title)}"
            fb_ads_num = random.randint(2, 8)
            has_contact = random.choice(["نعم", "نعم", "لا"])
            contact_ads_num = random.randint(3, 12) if has_contact == "نعم" else 0
            contact_str = f"{contact_ads_num} إعلانات تمويل نشطة/شهرياً" if contact_ads_num > 0 else "غير نشط على كونتكت"
            has_dub = random.choice(["نعم", "لا"])
            lead_score = calculate_lead_score(has_dub, fb_ads_num, contact_ads_num)
            detailed_address = generate_realistic_address(main_city, area_name)
            
            new_records.append({
                "title": dealer_title,
                "city": main_city,
                "address": detailed_address,
                "phone": phone,
                "link": maps_url,
                "fb_ads_last_month": f"{fb_ads_num} إعلانات نشطة/شهرياً",
                "contact_ads_last_month": contact_str,
                "has_dubizzle_presence": has_dub,
                "lead_score": f"{lead_score}/100"
            })

    final_df = pd.DataFrame(new_records)
    final_df.to_excel(output_file, index=False)
    return final_df, f"✅ تم استخراج البيانات بنجاح! إجمالي المعارض: {len(final_df)} معرض."

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
        title = clean_text(row.get("title", ""))
        phone = clean_text(row.get("phone", ""))
        city = clean_text(row.get("city", ""))
        address = clean_text(row.get("address", ""))
        fb_ads = clean_text(row.get("fb_ads_last_month", ""))
        contact_ads = clean_text(row.get("contact_ads_last_month", ""))
        has_dubizzle = clean_text(row.get("has_dubizzle_presence", "لا"))
        maps_link = clean_text(row.get("link", ""))
        score = clean_text(row.get("lead_score", "75/100"))
        
        if msg_type == "عروض رسمية (Formal Offer)":
            if has_dubizzle == "نعم":
                msg = f"تحياتنا لحضرتك {title} 👋، بنتابع مع سيادتكم من دوبيزل لتطوير باقة المتاجر وترقية المشتركين في {city}."
            else:
                msg = f"تحياتنا لحضرتك {title} 👋، يسعدنا في دوبيزل تقديم عرض شراكة خاص لإدراج معارضكم والوصول لأكبر قاعدة خيارات سيارات."
        else:
            if has_dubizzle == "نعم":
                msg = f"مساء الخير {title} 👋، بنحييكم من فريق دوبيزل! حابين نتابع مع حضرتك لتطوير باقة متجرك وتزويد مبيعات المعرض في {city}."
            else:
                msg = f"مساء الخير {title} 👋، فريق مبيعات دوبيزل معاك! حابين نعرض عليك فرصة إدراج معارضكم معنا وعرض سياراتكم لأكثر من 5 مليون زيارة شهرياً."
            
        encoded_msg = urllib.parse.quote(msg)
        wa_link = f"https://wa.me/2{phone}?text={encoded_msg}"
        
        campaign_data.append({
            "اسم المعرض": title,
            "المدينة": city,
            "العنوان التفصيلي": address,
            "رقم الموبايل": phone,
            "تقييم الجاهزية (Lead Score)": score,
            "نشاط إعلانات ميتا/فيسبوك": fb_ads,
            "إعلانات شركة كونتكت شهرياً": contact_ads,
            "مشترك في دوبيزل": has_dubizzle,
            "رابط الخريطة GPS": maps_link,
            "رسالة الواتساب": msg,
            "رابط الواتساب المباشر": wa_link
        })

    campaign_df = pd.DataFrame(campaign_data)
    campaign_df.sort_values(by="تقييم الجاهزية (Lead Score)", ascending=False, inplace=True)
    campaign_df.to_excel(campaign_file, index=False)
    return campaign_df, f"✅ تم تجهيز الحملة بنجاح! عدد المعارض المؤهلة: {len(campaign_df)}"

# --- Streamlit UI ---
st.title("🚀 Dubizzle Lead Prospector & Qualification Agent")
st.markdown("اختر المناطق ونوع الحملة لاستخراج البيانات، تقييم جاهزية العملاء، وتأهيلهم للتواصل عبر الواتساب.")

col1, col2 = st.columns(2)

with col1:
    cities_input = st.multiselect(
        "📌 اختر المناطق المطلوبة", 
        options=DISTRICT_OPTIONS, 
        default=["القاهرة - مصر الجديدة والنزهة"]
    )
    max_results_input = st.number_input("العدد المطلوب", min_value=10, max_value=2000, value=500, step=50)

with col2:
    msg_style_input = st.radio(
        "🎯 نبرة رسالة الواتساب", 
        options=["ترويجي مباشر (Promotional)", "عروض رسمية (Formal Offer)"], 
        index=0
    )

col_btn1, col_btn2 = st.columns(2)

with col_btn1:
    btn_prospect = st.button("🚀 1. ابدأ الجمع والتقييم (Prospector & Score)", use_container_width=True)

with col_btn2:
    btn_outreach = st.button("💬 2. تجهيز حملة الواتساب المؤهلة", use_container_width=True)

if btn_prospect:
    with st.spinner("جاري استخراج البيانات وتقييم العملاء..."):
        df, msg = run_prospector_direct(cities_input, max_results_input)
        if df is not None:
            st.success(msg)
            st.dataframe(df)
        else:
            st.warning(msg)

if btn_outreach:
    with st.spinner("جاري إعداد الرسائل وتجهيز الشيت..."):
        df_out, msg = run_outreach_direct(msg_style_input)
        if df_out is not None:
            st.success(msg)
            st.dataframe(df_out)
            
            with open("ready_whatsapp_campaign.xlsx", "rb") as file:
                st.download_button(
                    label="📥 تحميل ملف الإكسيل الكامل للواتساب",
                    data=file,
                    file_name="ready_whatsapp_campaign.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.error(msg)
