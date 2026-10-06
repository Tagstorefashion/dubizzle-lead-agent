import re
from rapidfuzz import fuzz


# =========================================================
# NAME NORMALIZATION
# =========================================================

def normalize_dealer_name(name):
    """
    توحيد اسم المعرض قبل المقارنة.
    الهدف تقليل اختلافات الكتابة بين المصادر.
    """

    if not name:
        return ""

    name = str(name).lower().strip()

    # إزالة HTML إن وجد
    name = re.sub(r"<[^>]+>", " ", name)

    # توحيد بعض الحروف العربية
    replacements = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ى": "ي",
        "ة": "ه",
    }

    for old, new in replacements.items():
        name = name.replace(old, new)

    # كلمات عامة لا تساعد كثيراً في تحديد هوية المعرض
    generic_words = [
        "للسيارات",
        "للسيارات",
        "سيارات",
        "للعربيات",
        "عربيات",
        "معرض",
        "معارض",
        "للتجارة",
        "تجاره",
        "موتورز",
        "موتور",
        "اوتو",
        "او تو",
        "كار",
        "cars",
        "car",
        "motors",
        "motor",
        "auto",
        "automotive",
        "egypt",
        "egyptian",
        "مصر",
    ]

    for word in generic_words:
        name = name.replace(word, " ")

    # إزالة الرموز
    name = re.sub(
        r"[^a-zA-Z0-9\u0600-\u06FF\s]",
        " ",
        name
    )

    # إزالة المسافات الزائدة
    name = re.sub(r"\s+", " ", name)

    return name.strip()


# =========================================================
# NAME SIMILARITY
# =========================================================

def names_are_similar(
    name1,
    name2,
    threshold=88
):
    """
    تحديد هل الاسمين غالباً لنفس المعرض.
    """

    n1 = normalize_dealer_name(name1)
    n2 = normalize_dealer_name(name2)

    if not n1 or not n2:
        return False

    if n1 == n2:
        return True

    score_ratio = fuzz.ratio(
        n1,
        n2
    )

    token_score = fuzz.token_set_ratio(
        n1,
        n2
    )

    # نستخدم أكثر من طريقة للمقارنة
    final_score = max(
        score_ratio,
        token_score
    )

    return final_score >= threshold


# =========================================================
# DUPLICATE CHECK
# =========================================================

def is_duplicate_dealer(
    dealer,
    existing_dealers
):
    """
    فحص المعرض الجديد مقابل المعارض الموجودة بالفعل.

    نعتمد على:
    1. الاسم
    2. رقم الهاتف
    3. المنطقة
    """

    new_name = str(
        dealer.get(
            "اسم المعرض",
            dealer.get("title", "")
        )
    ).strip()

    new_phone = str(
        dealer.get(
            "الهاتف",
            dealer.get("phone", "")
        )
    ).strip()

    new_area = str(
        dealer.get(
            "المنطقة",
            dealer.get("area", "")
        )
    ).strip()

    # توحيد الهاتف
    new_phone = re.sub(
        r"\D",
        "",
        new_phone
    )

    for existing in existing_dealers:

        old_name = str(
            existing.get(
                "اسم المعرض",
                existing.get("title", "")
            )
        ).strip()

        old_phone = str(
            existing.get(
                "الهاتف",
                existing.get("phone", "")
            )
        ).strip()

        old_area = str(
            existing.get(
                "المنطقة",
                existing.get("area", "")
            )
        ).strip()

        old_phone = re.sub(
            r"\D",
            "",
            old_phone
        )

        # -------------------------------------------------
        # Exact phone match
        # -------------------------------------------------

        if (
            new_phone
            and old_phone
            and len(new_phone) >= 10
            and new_phone == old_phone
        ):
            return True

        # -------------------------------------------------
        # Similar name
        # -------------------------------------------------

        if names_are_similar(
            new_name,
            old_name
        ):

            # لو المنطقة نفسها أو غير متاحة
            if (
                not new_area
                or not old_area
                or new_area == old_area
            ):
                return True

    return False


# =========================================================
# REMOVE DUPLICATES FROM LIST
# =========================================================

def remove_duplicate_dealers(dealers):
    """
    إزالة المعارض المكررة من القائمة.
    """

    unique_dealers = []

    for dealer in dealers:

        if not is_duplicate_dealer(
            dealer,
            unique_dealers
        ):

            unique_dealers.append(
                dealer
            )

    return unique_dealers


# =========================================================
# MERGE DEALER INFORMATION
# =========================================================

def merge_dealer_data(
    existing,
    new_data
):
    """
    لو وجدنا نفس المعرض من مصدرين،
    ندمج البيانات بدلاً من إنشاء Lead جديد.
    """

    merged = dict(existing)

    for key, value in new_data.items():

        if value is None:
            continue

        value = str(value).strip()

        if not value:
            continue

        old_value = str(
            merged.get(key, "")
        ).strip()

        # لو القيمة القديمة غير موجودة
        if not old_value:
            merged[key] = value

    return merged


# =========================================================
# FIND EXISTING DEALER
# =========================================================

def find_existing_dealer(
    dealer,
    existing_dealers
):
    """
    إرجاع المعرض المطابق إن وجد.
    """

    new_name = dealer.get(
        "اسم المعرض",
        dealer.get("title", "")
    )

    new_phone = re.sub(
        r"\D",
        "",
        str(
            dealer.get(
                "الهاتف",
                dealer.get("phone", "")
            )
        )
    )

    for existing in existing_dealers:

        old_name = existing.get(
            "اسم المعرض",
            existing.get("title", "")
        )

        old_phone = re.sub(
            r"\D",
            "",
            str(
                existing.get(
                    "الهاتف",
                    existing.get("phone", "")
                )
            )
        )

        # تطابق الهاتف
        if (
            new_phone
            and old_phone
            and new_phone == old_phone
        ):
            return existing

        # تطابق الاسم
        if names_are_similar(
            new_name,
            old_name
        ):
            return existing

    return None
