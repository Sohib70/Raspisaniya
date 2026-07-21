"""
Scheduler — muammo #14 (Scheduler markazi yo'qligi, "eng katta muammo"
deb belgilangan), shuningdek #1 (find_schedule_for_group juda ko'p ish
qiladi), #8 (_rebuild_schedule uzunligi) va #9 (build_schedule view'i
haddan tashqari katta bo'lishi) uchun yechim.

ESKI HOLAT:
    lesson_create -> smart_group -> build_schedule -> find_schedule ->
    swap -> bruteforce
    — hammasi bir-biridan mustaqil, alohida funksiyalar/view'lar. Har biri
    o'zi query yozadi, o'zi conflict tekshiradi, o'zi saqlaydi. Umumiy
    holatni (masalan "bu safar band bo'lgan slotlar") hech kim markazdan
    boshqarmaydi.

YANGI HOLAT:
    Bitta `Scheduler` klassi, ANIQ 4 bosqichli pipeline bilan:

        scheduler = Scheduler(course, busy_index)
        groups   = scheduler.group(students)      # talabalarni guruhlash
        plan     = scheduler.schedule(groups)      # slot taqsimlash (MRV)
        plan     = scheduler.optimize(plan)         # swap/conflict-resolution
        scheduler.save(plan)                        # DBga yozish + log

    Har bir bosqich ALOHIDA, sinaladigan, o'zgartirilishi mumkin bo'lgan
    metod. `build_schedule` view'i endi ~300-500 qatorlik "Course yaratadi
    -> Group tekshiradi -> ... -> Log qiladi" ketma-ketligini o'zi
    bajarmaydi — shunchaki shu 4 ta metodni chaqiradi va natijani
    render qiladi.

Bu fayl — INTEGRATSIYA UCHUN SKELET. `group()` ichidagi chaqiruv sizning
`smart_group_students`/`form_course_groups` funksiyalaringizga, `save()`
esa `_rebuild_schedule`dagi saqlash logikasiga ulanishi kerak (pastdagi
izohlarda ko'rsatilgan). Buni ataylab shunday qildim: mavjud, sinovdan
o'tgan biznes-mantiqni (masalan `smart_group_students` — bu allaqachon
yaxshi yozilgan, siz ham shunday deb baholagansiz) qayta yozib, yangi
xatolar kiritishdan ko'ra — uni shu markazlashgan pipeline ICHIGA
CHAQIRISH xavfsizroq.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from .allocator import MRVAllocator, Candidate, GroupTask
from .busy_index import BusyIndex, slot_occurrence_dates
from .conflict_checker import ConflictChecker
from .constants import VALID_PARA_PAIRS, LESSON_COUNT_PATTERNS


@dataclass
class ScheduledGroup:
    """Bitta CourseGroup uchun yakuniy natija."""
    group_id: object
    student_ids: list
    slot_key: Optional[tuple]      # (weekday_set, para_block) yoki None
    lesson_dates: list = field(default_factory=list)  # [(date, start, end), ...]
    resolved: bool = True          # False bo'lsa — optimize() bosqichida hal qilinishi kerak


@dataclass
class SchedulingPlan:
    scheduled: list = field(default_factory=list)   # list[ScheduledGroup]
    unresolved: list = field(default_factory=list)  # list[ScheduledGroup] (slot_key=None)

    def summary(self) -> dict:
        """Muammo #9: build_schedule view'i o'ziga xos statistikani hisoblab
        o'tirmasin deb, tayyor xulosa shu yerdan olinadi."""
        return {
            "total": len(self.scheduled) + len(self.unresolved),
            "resolved": len(self.scheduled),
            "unresolved": len(self.unresolved),
        }


def weekday_pattern_for(total_lessons: int):
    """LESSON_COUNT_PATTERNS jadvalidan mos patternni tanlaydi (muammo #13:
    endi if/elif zanjiri emas, konfiguratsiya jadvalidan qidiriladi)."""
    for min_lessons, weekday_sets, days_needed in LESSON_COUNT_PATTERNS:
        if total_lessons >= min_lessons:
            return weekday_sets, days_needed
    return None, 1


class Scheduler:
    """
    Bitta Course uchun butun scheduling jarayonini boshqaradigan markaziy
    klass. Har bir bosqich boshqa bosqichlarga bog'liq bo'lmagan holda
    alohida chaqirilishi/sinalishi mumkin — bu SRP buzilishini (#1) tuzatadi.
    """

    def __init__(self, *, course, busy_index: BusyIndex, GroupSchedule=None):
        self.course = course
        self.busy = busy_index
        self.checker = ConflictChecker(busy_index)
        self._GroupSchedule = GroupSchedule  # faqat save() bosqichida kerak

    # ── 1-BOSQICH: guruhlash ──────────────────────────────────────
    def group(self, students, *, grouping_fn: Callable, **kwargs):
        """
        Talabalarni guruhlarga bo'ladi.

        `grouping_fn` — mavjud `smart_group_students`/`form_course_groups`
        funksiyangiz shu yerga inject qilinadi (dependency injection),
        yangidan yozilmaydi. Masalan:

            scheduler.group(
                students,
                grouping_fn=smart_group_students,
                total_lessons=course.total_lessons,
                start_date=course.start_date,
                include_saturday=course.include_saturday,
            )
        """
        return grouping_fn(students, **kwargs)

    # ── 2-BOSQICH: slot taqsimlash (MRV allocator — muammo #2 yechimi) ──
    def schedule(self, groups: list) -> SchedulingPlan:
        """
        `groups` — [{'id':..., 'students':[...], 'teacher_id':...,
        'subject_id':...}, ...] shaklidagi ro'yxat.

        ESKI greedy o'rniga MRV allocator ishlatiladi: guruhlar
        yaratilish tartibida emas, eng kam muqobili borlaridan
        boshlab joylashtiriladi (tafsilot uchun allocator.py).
        """
        by_id = {g["id"]: g for g in groups}
        wds_sets, days_needed = weekday_pattern_for(self.course.total_lessons)

        def candidate_provider(task: GroupTask, already_assigned: dict):
            g = by_id[task.group_id]
            student_ids = g["students"]
            teacher_id = g.get("teacher_id")
            subject_id = g.get("subject_id")
            cands = []
            weekday_options = wds_sets or [(wd,) for wd in range(5)]
            for wds in weekday_options:
                for block in VALID_PARA_PAIRS:
                    dates = slot_occurrence_dates(
                        self.course.start_date, wds, self.course.total_lessons
                    )
                    if not dates:
                        continue
                    ok_all = True
                    total_load = 0
                    for d in dates:
                        rep = self.checker.check(
                            date=d, para_idx=block[0], teacher_id=teacher_id,
                            student_ids=student_ids, subject_id=subject_id,
                        )
                        rep2 = self.checker.check(
                            date=d, para_idx=block[1], teacher_id=teacher_id,
                            student_ids=student_ids, subject_id=subject_id,
                        )
                        if not (rep.ok and rep2.ok):
                            ok_all = False
                            break
                        total_load += rep.subject_load + rep2.subject_load
                    if ok_all:
                        cands.append(Candidate(slot_key=(wds, block), score=total_load))
            return cands

        allocator = MRVAllocator(candidate_provider)
        assigned, unresolved_ids = allocator.allocate(list(by_id.keys()))

        plan = SchedulingPlan()
        for gid, slot_key in assigned.items():
            g = by_id[gid]
            wds, block = slot_key
            dates = slot_occurrence_dates(
                self.course.start_date, wds, self.course.total_lessons
            )
            plan.scheduled.append(ScheduledGroup(
                group_id=gid, student_ids=g["students"], slot_key=slot_key,
                lesson_dates=list(dates), resolved=True,
            ))
        for gid in unresolved_ids:
            g = by_id[gid]
            plan.unresolved.append(ScheduledGroup(
                group_id=gid, student_ids=g["students"], slot_key=None,
                resolved=False,
            ))
        return plan

    # ── 3-BOSQICH: optimallashtirish / conflict-resolution ──────────
    def optimize(self, plan: SchedulingPlan, *, resolvers: list = None) -> SchedulingPlan:
        """
        `plan.unresolved` ro'yxatidagi guruhlarga navbatma-navbat
        resolver'larni qo'llaydi.

        Muammo #10 yechimi: eski koddagi subject-swap / parallel-swap /
        cross-swap / bruteforce — 4 ta bir-biridan mustaqil funksiya edi.
        Endi ularning har biri BITTA umumiy interfeysga ega bo'ladi:

            def resolver(unresolved_group, plan, checker) -> ScheduledGroup | None

        va shu yerda ketma-ket (eng "yumshoq"dan eng "qattiq"gacha)
        sinab ko'riladi — masalan:

            scheduler.optimize(plan, resolvers=[
                subject_swap_resolver,
                parallel_swap_resolver,
                cross_subject_swap_resolver,
                brute_force_resolver,   # eng oxirgi, eng qimmat variant
            ])

        Bu — mavjud `_auto_resolve_via_cross_subject_swap`,
        `_auto_resolve_via_parallel_swap`, `_brute_force_find_slot`
        funksiyalaringizni QAYTA YOZMASDAN, faqat shu umumiy interfeysga
        moslab (adapter sifatida) ulash uchun mo'ljallangan joy.
        """
        resolvers = resolvers or []
        still_unresolved = []
        for ug in plan.unresolved:
            resolved_group = None
            for resolver in resolvers:
                resolved_group = resolver(ug, plan, self.checker)
                if resolved_group is not None:
                    break
            if resolved_group is not None:
                plan.scheduled.append(resolved_group)
            else:
                still_unresolved.append(ug)
        plan.unresolved = still_unresolved
        return plan

    # ── 4-BOSQICH: saqlash ───────────────────────────────────────────
    def save(self, plan: SchedulingPlan, *, group_lookup: dict, room_for=None):
        """
        Rejani DBga yozadi. `group_lookup` — {group_id: CourseGroup instance}.

        Muammo #7 (juda ko'p query) shu yerda ham hisobga olingan:
        `bulk_create` ishlatiladi, har bir GroupSchedule uchun alohida
        `.save()` chaqirilmaydi.
        """
        GroupSchedule = self._GroupSchedule
        if GroupSchedule is None:
            raise RuntimeError("Scheduler(GroupSchedule=...) berilmagan — save() ishlay olmaydi")

        to_create = []
        for sg in plan.scheduled:
            if not sg.resolved or sg.slot_key is None:
                continue
            grp = group_lookup.get(sg.group_id)
            if grp is None:
                continue
            wds, block = sg.slot_key
            from .constants import PARA_TIMES
            for i, d in enumerate(sg.lesson_dates):
                # bittadan ikkitagacha para: block[0] va block[1] navbatma-navbat
                for lesson_num, para_i in enumerate(block, start=1):
                    to_create.append(GroupSchedule(
                        group=grp, date=d, lesson_number=lesson_num,
                        start_time=PARA_TIMES[para_i][0],
                    ))
        GroupSchedule.objects.bulk_create(to_create, batch_size=500)
        return len(to_create)
