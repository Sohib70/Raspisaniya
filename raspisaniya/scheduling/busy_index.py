"""
BusyIndex — muammo #3 (get_hard_busy), #6 (_slot_occurrence_dates qayta
hisoblanishi) va #7 (juda ko'p SQL query) uchun yagona yechim.

ESKI YONDASHUV:
    Har bir guruh uchun `find_schedule_for_group` chaqirilganda, HAR BIR
    sana uchun alohida `GroupSchedule.objects.filter(...)` query ishga
    tushardi (`get_hard_busy`, `get_busy_detailed`). 104 ta guruh, har
    birida ~10-20 sana bo'lsa — minglab SQL so'rovi.

    Bundan tashqari `get_hard_busy` barcha odamlarning band vaqtlarini
    BITTA `set()`ga qo'shib yuborardi:
        busy=set()
        # Ali band, Vali band, Hasan band -> hammasi shu bitta setga tushadi
    Bu — agar guruhda 15 talaba bo'lsa va faqat 1 tasi band bo'lsa ham,
    o'sha para "band" deb belgilanadi (garchi qolgan 14 talaba erkin bo'lsa
    ham). Individual band-emasligini bilish keyingi bosqichlarda (masalan
    qisman almashtirish/eviction) kerak bo'ladi, lekin eski kod buni yo'qotib
    qo'yardi.

YANGI YONDASHUV:
    1. Butun kurs davri uchun (start_date..end_date + zaxira) BARCHA
       GroupSchedule yozuvlari BITTA queryda o'qiladi va xotirada
       (teacher_id, date) -> {para_index...} hamda (student_id, date) ->
       {para_index...} lug'atlariga joylanadi.
    2. `is_busy_any` (eski `get_hard_busy` ekvivalenti, tez tekshiruv uchun)
       VA `who_is_busy` (individual — kim aynan band, muammo #3ning
       yechimi) ikkalasi ham taqdim etiladi.
    3. Pattern sanalari (`_slot_occurrence_dates` ekvivalenti) `functools.lru_cache`
       bilan memoizatsiya qilinadi — bir xil (start_date, weekday_set,
       total_lessons) uchun qayta hisoblanmaydi.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date as Date, timedelta
from functools import lru_cache
from typing import Iterable

from .constants import PARA_TIMES


def _para_index_for_time(t):
    for i, (ps, _) in enumerate(PARA_TIMES):
        if ps == t:
            return i
    return None


@dataclass
class BusyIndex:
    """
    Bitta build_schedule / lesson_create chaqiruvi davomida QAYTA
    ISHLATILADIGAN, oldindan yuklangan band-vaqtlar indeksi.

    Django modeliga bog'liqlikni ataylab shu yerga izolyatsiya qildim —
    qolgan scheduler kodi (allocator, conflict_checker) faqat shu klass
    orqali ma'lumot oladi, to'g'ridan-to'g'ri ORM query yozmaydi. Shunday
    qilib #7dagi "har joyda GroupSchedule.objects.filter(...)" muammosi
    bitta joyga markazlashadi.
    """
    # (teacher_id, date) -> set(para_index)
    teacher_busy: dict = field(default_factory=lambda: defaultdict(set))
    # (student_id, date) -> set(para_index)
    student_busy: dict = field(default_factory=lambda: defaultdict(set))
    # (subject_id, date) -> {para_index: guruhlar soni}  — "eng bo'sh parani tanlash" uchun
    subject_load: dict = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))
    # kim band ekanini bilish uchun: (date, para_index) -> [(student_id, group)]
    student_occupants: dict = field(default_factory=lambda: defaultdict(list))
    teacher_occupants: dict = field(default_factory=lambda: defaultdict(list))

    @classmethod
    def build(cls, date_from: Date, date_to: Date, *, GroupSchedule):
        """
        Bitta (yoki ikkita — teacher va student uchun `select_related`/
        `prefetch_related` bilan optimallashtirilgan) query orqali butun
        oraliqdagi band vaqtlarni xotiraga yuklaydi.

        `GroupSchedule` modelini parametr sifatida qabul qilaman — bu
        modulni Django ilova kontekstidan ajratib, unit-test qilish
        imkonini beradi (haqiqiy DB bo'lmasa ham sinash mumkin).
        """
        idx = cls()
        qs = (
            GroupSchedule.objects
            .filter(date__gte=date_from, date__lte=date_to)
            .select_related("group", "group__teacher", "group__course__subject")
            .prefetch_related("group__students")
        )
        for sc in qs:
            grp = sc.group
            st = sc.start_time or grp.start_time
            para_idx = _para_index_for_time(st) if st else None
            para_indices = [para_idx] if para_idx is not None else range(len(PARA_TIMES))

            teacher_id = grp.teacher_id
            subject_id = grp.course.subject_id if grp.course_id else None

            for pi in para_indices:
                if teacher_id:
                    idx.teacher_busy[(teacher_id, sc.date)].add(pi)
                    idx.teacher_occupants[(sc.date, pi)].append((teacher_id, grp))
                if subject_id:
                    idx.subject_load[(subject_id, sc.date)][pi] += 1

            # student_id bo'yicha M2M — group.students allaqachon prefetch qilingan,
            # shuning uchun bu yerda ORTIQCHA query BO'LMAYDI.
            for st_obj in grp.students.all():
                for pi in para_indices:
                    idx.student_busy[(st_obj.id, sc.date)].add(pi)
                    idx.student_occupants[(sc.date, pi)].append((st_obj.id, grp))

        return idx

    # ── Sorov metodlari (eski get_hard_busy o'rniga) ──────────────
    def teacher_free(self, teacher_id, date, para_idx) -> bool:
        if not teacher_id:
            return True
        return para_idx not in self.teacher_busy.get((teacher_id, date), ())

    def student_free(self, student_id, date, para_idx) -> bool:
        return para_idx not in self.student_busy.get((student_id, date), ())

    def group_free(self, student_ids: Iterable[int], date, para_idx) -> bool:
        """Guruhdagi BARCHA talabalar shu para uchun bo'shmi."""
        return all(self.student_free(sid, date, para_idx) for sid in student_ids)

    def busy_students_in(self, student_ids: Iterable[int], date, para_idx) -> list:
        """
        Muammo #3ning aynan o'zi: eski kod `busy=set()` ichiga hammani
        aralashtirib yuborardi. Bu yerda ANIQ qaysi talaba(lar) band
        ekanini qaytaramiz — masalan qisman eviction / almashtirish
        algoritmlari uchun kerak bo'ladi.
        """
        sid_set = set(student_ids)
        result = []
        for sid, grp in self.student_occupants.get((date, para_idx), []):
            if sid in sid_set:
                result.append((sid, grp))
        return result

    def subject_occupancy(self, subject_id, date, para_idx) -> int:
        return self.subject_load.get((subject_id, date), {}).get(para_idx, 0)

    # ── Xotirada yangilash (qo'shimcha query YO'Q) ──────────────────
    def record_scheduled(self, *, group, teacher_id, subject_id, student_ids,
                          dates_and_paras):
        """
        Bitta guruh DBga SAQLANGANDAN KEYIN chaqiriladi — indeksni qayta
        DBdan o'qimasdan, xotirada darhol yangilaydi.

        MUHIM: `build_schedule` bitta while-iteratsiya ichida bir nechta
        guruhni KETMA-KET saqlaydi (avval 1-guruh, keyin 2-guruh, ...).
        Agar BusyIndex faqat iteratsiya BOSHIDA bir marta qurilsa-yu,
        keyin yangilanmasa — 2-guruh 1-guruhning ENDI band bo'lgan
        vaqtini "bo'sh" deb noto'g'ri hisoblab, ikkalasi bir xil paraga
        tushib qolishi mumkin edi. Shu metod aynan shu xatoning oldini
        oladi, va buni yangi SQL query YUBORMASDAN qiladi (chunki
        qaysi (sana, para) larga yozilganini chaqiruvchi allaqachon biladi).

        `dates_and_paras` — [(date, para_idx), ...] ro'yxati.
        """
        for date, para_idx in dates_and_paras:
            if teacher_id:
                self.teacher_busy[(teacher_id, date)].add(para_idx)
                self.teacher_occupants[(date, para_idx)].append((teacher_id, group))
            if subject_id is not None:
                self.subject_load[(subject_id, date)][para_idx] += 1
            for sid in student_ids:
                self.student_busy[(sid, date)].add(para_idx)
                self.student_occupants[(date, para_idx)].append((sid, group))


@lru_cache(maxsize=4096)
def slot_occurrence_dates(start_date: Date, weekday_set: tuple, total_lessons: int) -> tuple:
    """
    Eski `_slot_occurrence_dates` ning memoizatsiya qilingan versiyasi —
    muammo #6. Argumentlar hashable (tuple/int/date) bo'lgani uchun
    `lru_cache` xavfsiz ishlaydi: bir xil (start_date, weekday_set,
    total_lessons) uchun IKKINCHI marta chaqirilganda hisoblash umuman
    ishlamaydi, keshdan qaytadi.

    Natija tuple (o'zgarmas) qilib qaytariladi — chaqiruvchi tomonda
    tasodifiy mutatsiyadan himoyalanish uchun.
    """
    dates = []
    cur_monday = start_date - timedelta(days=start_date.weekday())
    lessons_left = total_lessons
    safety = 0
    while lessons_left > 0 and safety < 60:
        for wd in weekday_set:
            if lessons_left <= 0:
                break
            d = cur_monday + timedelta(days=wd)
            if d < start_date:
                continue
            dates.append(d)
            lessons_left -= min(2, lessons_left)
        cur_monday += timedelta(weeks=1)
        safety += 1
    return tuple(dates)