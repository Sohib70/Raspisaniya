"""
Scheduler konstantalari — muammo #13 yechimi.

ESKI: `24`, `16`, `8`, `80`, `15`, `10`, `4` kabi sonlar views.py bo'ylab
o'nlab joyda qattiq yozilgan edi (masalan `if total_lessons >= 20:`,
`max_size=15`, `MAX_GROUPS_PER_SLOT_NO_TEACHER = 4`).

YANGI: hammasi shu yerda, nomlangan holda. Django loyihasida bu faylni
`settings.py`dan import qilib, kerak bo'lsa `override` qilish ham mumkin:

    # settings.py
    from raspisaniya.scheduling.constants import *
    SCHEDULER_MAX_GROUP_SIZE = 20   # masalan, sozlamani shu yerda o'zgartirish
"""
from datetime import time as dtime

# ── Para vaqtlari ──────────────────────────────────────────────
PARA_TIMES = [
    (dtime(8, 30), dtime(9, 50)),
    (dtime(10, 0), dtime(11, 20)),
    (dtime(12, 0), dtime(13, 20)),
    (dtime(13, 30), dtime(14, 50)),
    (dtime(15, 0), dtime(16, 20)),
    (dtime(16, 30), dtime(17, 50)),
]

# Para juftliklari (kuniga 2 para ketma-ket bloklarda)
VALID_PARA_PAIRS = [(0, 1), (2, 3), (4, 5)]

WEEKDAY_NAMES = {
    0: "Dushanba", 1: "Seshanba", 2: "Chorshanba",
    3: "Payshanba", 4: "Juma", 5: "Shanba",
}

# ── Kurs uzunligiga qarab hafta-kunlari patterni ───────────────
# ESKI koddagi `if total_lessons >= 20 ... elif 12 <= total_lessons <= 20 ...`
# shart zanjiri endi shu jadvaldan o'qiladi — yangi bosqich qo'shish uchun
# faqat shu ro'yxatga bitta qator qo'shish kifoya, kod ichidagi if/elif
# zanjirini qidirib yurish shart emas.
#   (min_lessons, preferred_weekday_sets, days_needed)
LESSON_COUNT_PATTERNS = [
    (20, [(0, 2, 4)], 3),   # 24 para va undan ko'p -> Dush/Chor/Juma
    (12, [(1, 3)], 2),      # 12-20 para -> Sesh/Pay
    (0, None, 1),           # qolganlari -> istalgan 1 kun (dinamik hisoblanadi)
]

# ── Guruh hajmi chegaralari ─────────────────────────────────────
DEFAULT_MAX_GROUP_SIZE = 15
DEFAULT_MIN_GROUP_SIZE = 10
HARD_MIN_GROUP_SIZE = 8   # bundan kam qolishiga umuman yo'l qo'yilmaydi
HARD_MAX_GROUP_SIZE = 18  # bundan ortiq qo'shilishiga yo'l qo'yilmaydi

LANG_MERGE_THRESHOLD = 8

# ── O'qituvchisiz bosqichda bitta parada zaxira sig'imi ────────
MAX_GROUPS_PER_SLOT_NO_TEACHER = 4

# ── Slot qidirish xavfsizlik chegaralari (cheksiz sikldan saqlanish) ──
MAX_WEEKS_LOOKAHEAD = 24
MAX_CONFLICT_SCAN_WEEKS = 12
