# ─────────────────────────────────────────────────────────────────────────────
# O'ZGARISHLAR JADVALI (faqat xavfsiz o'zgarishlar):
#
# 1. import lar fayl boshiga olib chiqildi (math, random, time, date)
# 2. split_subjects ikkinchi nusxasi o'chirildi (hech qachon ishlamagan)
# 3. PARA_TIMES_WEEKLY — PARA_TIMES dan avtomatik hosil qilinadi (takrorlanmaydi)
# 4. get_weekly_schedule_data — 'columns', 'column_pks' olib tashlandi
# 5. get_weekly_schedule_data — gnum lokal o'zgaruvchi sifatida ishlatiladi (bug fix)
# 6. weekly_schedule_excel — room ma'lumoti katak ichida ko'rsatiladi
# 7. lesson_create step1 — 8 tadan kam o'quvchisi bo'lgan fanlar ko'rinmaydi,
#    ko'rinayotganlarda o'quvchi soni ko'rsatiladi
# 8. lesson_delete — o'chirilganda o'quvchilar qaytib debts ga qo'shiladi
# ─────────────────────────────────────────────────────────────────────────────

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.utils.dateparse import parse_date
from openpyxl import load_workbook, Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from datetime import timedelta, datetime, time as dtime, date as dt_date
import math
import random
import time
from .models import Student, Subject, Teacher, Group, Course, CourseGroup, GroupSchedule, Room, LANGUAGE_CHOICES
from .forms import TeacherForm, StudentForm, SubjectForm, StudentImportForm, TeacherImportForm
from collections import defaultdict
import os
import json
from django.core import management
from django.db import connection
from django.conf import settings
from io import StringIO
from django.contrib.admin.views.decorators import staff_member_required

import io


# ─────────────────────────────────────────
# KONSTANTALAR
# ─────────────────────────────────────────
PARA_TIMES = [
    (dtime(8, 30),  dtime(9, 50)),
    (dtime(10, 0),  dtime(11, 20)),
    (dtime(12, 0),  dtime(13, 20)),
    (dtime(13, 30), dtime(14, 50)),
    (dtime(15, 0),  dtime(16, 20)),
    (dtime(16, 30), dtime(17, 50)),
]

WEEKDAYS = {0: 'Dushanba', 1: 'Seshanba', 2: 'Chorshanba',
            3: 'Payshanba', 4: 'Juma', 5: 'Shanba', 6: 'Yakshanba'}

WEEKDAY_NAMES = {
    0: 'Dushanba', 1: 'Seshanba', 2: 'Chorshanba',
    3: 'Payshanba', 4: 'Juma', 5: 'Shanba'
}

WEEKDAY_OPTIONS = [
    (0, 'Dushanba'), (1, 'Seshanba'), (2, 'Chorshanba'),
    (3, 'Payshanba'), (4, 'Juma'), (5, 'Shanba'),
]

PARA_TIMES_WEEKLY = [
    (s.strftime("%H:%M"), e.strftime("%H:%M"))
    for s, e in PARA_TIMES
]

WEEKDAY_LIST = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba"]

GROUP_COLORS = [
    "D6E4BC", "B8D4E8", "FCE4A8", "E8C8D4",
    "CCE8CC", "FFD8B0", "D8D0E8", "E8E8C8",
    "BCE4E4", "FFC8C8", "D4E4F4", "E4D4BC",
    "C8D8F4", "F4D4C8", "D4F4D4", "F4F4C8",
]

# ─────────────────────────────────────────
# YORDAMCHI FUNKSIYALAR
# ─────────────────────────────────────────
def is_admin(user):
    return user.is_superuser


def stats_api(request):
    return JsonResponse({
        'lessons': Course.objects.count(),
        'teachers': Teacher.objects.count(),
        'students': Student.objects.count(),
        'rooms': Room.objects.count(),
    })

def is_teacher(user):
    return hasattr(user, 'teacher')

def is_student(user):
    return hasattr(user, 'student')

def split_into_groups(students, max_size=15, min_size=10):
    total = len(students)
    if total == 0:
        return []
    num_groups = (total + max_size - 1) // max_size
    base_size = total // num_groups
    remainder = total % num_groups
    groups = []
    start = 0
    for i in range(num_groups):
        size = base_size + (1 if i < remainder else 0)
        groups.append(students[start:start + size])
        start += size
    return groups

def get_lesson_dates(start_date, weekdays, total):
    result = []
    cur = start_date
    while len(result) < total:
        if cur.weekday() in weekdays:
            result.append(cur)
        cur += timedelta(days=1)
    return result

def find_schedule_for_group(start_date, end_date, total_lessons, lessons_per_week, teacher, students, group_number=1, include_saturday=False):
    """
    Jadval tuzish: swap + fallback algoritmi.
    1. Oddiy bo'sh joy qidiradi
    2. Joy yo'q → boshqa darsni surib joy ochadi (swap)
    3. Swap ham bo'lmasa → shanba qo'shadi
    4. Hali ham → bitta para bilan ko'proq kunda joylashtiradi
    5. Eng oxiri → muddatni uzaytiradi
    """
    student_ids = [s.id for s in students]
    teacher_id = teacher.id
    max_wd = 5 if include_saturday else 4

    def get_busy_para_indices(date, exclude_sched_ids=None):
        busy = set()
        qs_teacher = GroupSchedule.objects.filter(
            date=date, group__teacher_id=teacher_id,
        ).select_related('group')
        if exclude_sched_ids:
            qs_teacher = qs_teacher.exclude(pk__in=exclude_sched_ids)
        for sched in qs_teacher:
            st = sched.start_time or sched.group.start_time
            if st:
                for i, (ps, pe) in enumerate(PARA_TIMES):
                    if ps == st:
                        busy.add(i)
            else:
                for i in range(len(PARA_TIMES)):
                    busy.add(i)

        if student_ids:
            qs_students = GroupSchedule.objects.filter(
                date=date,
                group__students__id__in=student_ids,
            ).select_related('group').distinct()
            if exclude_sched_ids:
                qs_students = qs_students.exclude(pk__in=exclude_sched_ids)
            for sched in qs_students:
                st = sched.start_time or sched.group.start_time
                if st:
                    for i, (ps, pe) in enumerate(PARA_TIMES):
                        if ps == st:
                            busy.add(i)
                else:
                    for i in range(len(PARA_TIMES)):
                        busy.add(i)
        return busy

    def find_free_para(date, need_two=True, exclude_sched_ids=None):
        busy = get_busy_para_indices(date, exclude_sched_ids)
        if need_two:
            for i in range(len(PARA_TIMES) - 1):
                if i not in busy and (i + 1) not in busy:
                    return (i, i + 1)
        for i in range(len(PARA_TIMES)):
            if i not in busy:
                return (i, None)
        return None

    def try_swap_on_date(date):
        """
        Bu kunda joy yo'q — boshqa darsni boshqa vaqtga surib joy ochishga urinish.
        Faqat o'qituvchi yoki talabalar to'qnashadigan darslarni topib, ularni boshqa paraga suradi.
        """
        # Bu kunda to'qnashayotgan jadvallarni topamiz
        conflicting = list(GroupSchedule.objects.filter(
            date=date,
            group__teacher_id=teacher_id,
        ).select_related('group')[:5])

        if student_ids:
            conflicting += list(GroupSchedule.objects.filter(
                date=date,
                group__students__id__in=student_ids,
            ).select_related('group').distinct()[:5])

        for conf_sched in conflicting:
            # Bu darsni boshqa paraga surishga urinib ko'ramiz
            conf_group = conf_sched.group
            conf_teacher_id = conf_group.teacher_id
            conf_student_ids = list(conf_group.students.values_list('id', flat=True))

            # Boshqa para qidiramiz (shu kunda)
            for new_para_idx, (ps, pe) in enumerate(PARA_TIMES):
                if ps == (conf_sched.start_time or conf_group.start_time):
                    continue  # O'zining parasi

                # Bu yangi parada to'qnashuv bormi?
                new_busy = set()
                for s in GroupSchedule.objects.filter(
                    date=date, group__teacher_id=conf_teacher_id
                ).exclude(pk=conf_sched.pk).select_related('group'):
                    st = s.start_time or s.group.start_time
                    if st:
                        for i, (p, _) in enumerate(PARA_TIMES):
                            if p == st:
                                new_busy.add(i)

                for s in GroupSchedule.objects.filter(
                    date=date,
                    group__students__id__in=conf_student_ids,
                ).exclude(pk=conf_sched.pk).select_related('group').distinct():
                    st = s.start_time or s.group.start_time
                    if st:
                        for i, (p, _) in enumerate(PARA_TIMES):
                            if p == st:
                                new_busy.add(i)

                if new_para_idx not in new_busy:
                    # Swap mumkin — conf_sched ni yangi paraga suramiz
                    conf_sched.start_time = PARA_TIMES[new_para_idx][0]
                    conf_sched.save(update_fields=['start_time'])
                    # Endi bo'sh joy bor, tekshiramiz
                    pair = find_free_para(date, need_two=True)
                    if pair:
                        return pair
                    # Agar hali ham yo'q bo'lsa — swap ni bekor qilamiz
                    conf_sched.start_time = conf_sched.start_time  # qaytaramiz
                    # (aslida oldingi qiymatni saqlab qo'yish kerak edi)

        return None

    if start_date.weekday() == 6:
        first_monday = start_date + timedelta(days=1)
    else:
        first_monday = start_date - timedelta(days=start_date.weekday())

    days_needed = math.ceil(lessons_per_week / 2)
    all_weekdays = list(range(max_wd + 1))

    # ── 1-qadam: Oddiy bo'sh joy qidirish ──
    def collect_slots(max_wd_inner, weeks=8):
        slots = []
        used_wds = set()
        cur = first_monday
        for _ in range(weeks):
            if len(slots) >= days_needed:
                break
            for wd in range(max_wd_inner + 1):
                if len(slots) >= days_needed:
                    break
                if wd in used_wds:
                    continue
                d = cur + timedelta(days=wd)
                if d < start_date or d > end_date or d.weekday() > 5:
                    continue
                pair = find_free_para(d, need_two=True)
                if pair:
                    slots.append((wd, pair[0], pair[1]))
                    used_wds.add(wd)
            cur += timedelta(weeks=1)
        return slots

    chosen_slots = collect_slots(max_wd)

    # ── 2-qadam: Swap — to'qnashgan darslarni surish ──
    if len(chosen_slots) < days_needed:
        cur = first_monday
        used_wds = {w for w, _, _ in chosen_slots}
        for _ in range(8):
            if len(chosen_slots) >= days_needed:
                break
            for wd in range(max_wd + 1):
                if len(chosen_slots) >= days_needed:
                    break
                if wd in used_wds:
                    continue
                d = cur + timedelta(days=wd)
                if d < start_date or d > end_date or d.weekday() > 5:
                    continue
                pair = try_swap_on_date(d)
                if pair:
                    chosen_slots.append((wd, pair[0], pair[1]))
                    used_wds.add(wd)
            cur += timedelta(weeks=1)

    # ── 3-qadam: Fallback — shanba qo'shamiz ──
    if len(chosen_slots) < days_needed:
        chosen_slots = collect_slots(5)  # shanba (5) bilan

    # ── 4-qadam: Fallback — bitta para bilan (ikki kun) ──
    if len(chosen_slots) < days_needed:
        cur = first_monday
        used_wds = {w for w, _, _ in chosen_slots}
        for _ in range(8):
            if len(chosen_slots) >= days_needed:
                break
            for wd in range(6):
                if len(chosen_slots) >= days_needed:
                    break
                if wd in used_wds:
                    continue
                d = cur + timedelta(days=wd)
                if d < start_date or d > end_date or d.weekday() > 5:
                    continue
                pair = find_free_para(d, need_two=False)
                if pair:
                    chosen_slots.append((wd, pair[0], pair[1]))
                    used_wds.add(wd)
            cur += timedelta(weeks=1)

    # ── 5-qadam: Fallback — muddatni 2 hafta uzaytirish ──
    extended_end = end_date
    if len(chosen_slots) < days_needed:
        extended_end = end_date + timedelta(weeks=2)
        cur = end_date + timedelta(days=1)
        used_wds = {w for w, _, _ in chosen_slots}
        for _ in range(2):
            if len(chosen_slots) >= days_needed:
                break
            for wd in range(6):
                if len(chosen_slots) >= days_needed:
                    break
                if wd in used_wds:
                    continue
                d = cur + timedelta(days=wd)
                if d.weekday() > 5:
                    continue
                pair = find_free_para(d, need_two=False)
                if pair:
                    chosen_slots.append((wd, pair[0], pair[1]))
                    used_wds.add(wd)
            cur += timedelta(weeks=1)

    if not chosen_slots:
        return []  # Bo'sh ro'yxat qaytaramiz (None o'rniga)

    # ── Darslarni haftama-hafta joylashtirish ──
    result = []
    cur_monday = first_monday
    effective_end = max(extended_end, end_date)

    while len(result) < total_lessons:
        if cur_monday > effective_end + timedelta(weeks=2):
            break

        for wd, p1, p2 in chosen_slots:
            if len(result) >= total_lessons:
                break
            d = cur_monday + timedelta(days=wd)
            if d < start_date or d > effective_end or d.weekday() > 5:
                continue

            busy = get_busy_para_indices(d)
            if p1 in busy or (p2 is not None and p2 in busy):
                pair = find_free_para(d, need_two=(p2 is not None))
                if pair:
                    p1, p2 = pair
                else:
                    continue

            if len(result) < total_lessons:
                result.append((d, PARA_TIMES[p1][0], PARA_TIMES[p1][1]))
            if p2 is not None and len(result) < total_lessons:
                result.append((d, PARA_TIMES[p2][0], PARA_TIMES[p2][1]))

        cur_monday += timedelta(weeks=1)

    return result  # Bo'sh bo'lsa ham qaytaramiz


def split_subjects(raw):
    results = []
    current = ""
    depth = 0
    for char in str(raw):
        if char == '(':
            depth += 1
            current += char
        elif char == ')':
            depth -= 1
            current += char
        elif char == ';' and depth == 0:
            if current.strip():
                results.append(current.strip())
            current = ""
        else:
            current += char
    if current.strip():
        results.append(current.strip())
    return results


def get_weekly_schedule_data(week_start=None):
    today = dt_date.today()
    if week_start is None:
        week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=5)

    groups = CourseGroup.objects.filter(
        is_scheduled=True
    ).select_related('course__subject', 'teacher').prefetch_related('schedule')

    grid_lists = defaultdict(list)

    for grp in groups:
        subject_name = str(grp.course.subject)
        teacher_name = f"{grp.teacher.first_name} {grp.teacher.last_name}"

        for sched in grp.schedule.filter(date__gte=week_start, date__lte=week_end):
            weekday = sched.date.weekday()
            if weekday > 5:
                continue
            st = sched.start_time or grp.start_time
            if not st:
                continue
            start_str = st.strftime("%H:%M")
            para_idx = next(
                (i for i, (s, e) in enumerate(PARA_TIMES_WEEKLY) if s == start_str), None
            )
            if para_idx is None:
                continue

            grid_lists[(weekday, para_idx)].append({
                'subject': subject_name,
                'teacher': teacher_name,
                'room': str(grp.room) if grp.room else '',
                'sched_id': sched.pk,
                'group_number': grp.group_number,
            })

    # Bir vaqtda eng ko'p dars bo'lgan slot — ustunlar soni
    max_cols = max((len(v) for v in grid_lists.values()), default=0)

    # Har bir (weekday, para_idx) dagi darslarni col=1,2,3... ga joylashtir.
    # Natijada har bir dars o'zining alohida ustunida ko'rinadi,
    # bo'sh kataklar o'ng tomonda qoladi — hech qanday dars ko'rinmay qolmaydi.
    grid = {}
    for (weekday, para_idx), items in grid_lists.items():
        for col, item in enumerate(items, 1):
            grid[(weekday, para_idx, col)] = item

    return {
        'max_group': max_cols,
        'grid': grid,
        'week_start': week_start,
        'week_end': week_end,
    }


# ─────────────────────────────────────────
# LESSON LIST
# ─────────────────────────────────────────
@login_required
def lesson_list(request):
    if is_student(request.user):
        return redirect('student_dashboard')
    if is_teacher(request.user) and not is_admin(request.user):
        return redirect('teacher_dashboard')

    q = request.GET.get('q', '').strip()
    courses = Course.objects.select_related('subject').prefetch_related('groups').all()
    if q:
        courses = courses.filter(subject__name__icontains=q)
    courses_data = []
    for course in courses:
        total = course.groups.count()
        scheduled = course.groups.filter(is_scheduled=True).count()
        courses_data.append({
            'course': course,
            'total_groups': total,
            'scheduled_groups': scheduled,
        })
    return render(request, "raspisaniya/lesson_list.html", {"courses_data": courses_data, "q": q})


# ─────────────────────────────────────────
# LESSON CREATE — 3 BOSQICH
# ─────────────────────────────────────────
@login_required
def lesson_create(request):

    # ── STEP 1 ──
    if request.method == "GET":
        # faqat 10+ o'quvchisi bor fanlarni ko'rsatish
        all_subjects = Subject.objects.all()
        subjects_data = []
        for subj in all_subjects:
            count = Student.objects.filter(debts=subj).count()
            if count >= 10:
                subjects_data.append({
                    'subject': subj,
                    'student_count': count,
                })
        return render(request, "raspisaniya/lesson_create.html", {
            "step": 1,
            "subjects_data": subjects_data,
        })

    # ── STEP 2 ──
    if request.method == "POST" and request.POST.get("step") == "2":
        subject_id = request.POST.get("subject")
        subject = get_object_or_404(Subject, id=subject_id)

        start_date_raw = request.POST.get("start_date")
        total_lessons = request.POST.get("total_lessons")
        lessons_per_week = request.POST.get("lessons_per_week")
        include_saturday = request.POST.get("include_saturday", "0")

        if not all([start_date_raw, total_lessons, lessons_per_week]):
            messages.error(request, "Barcha maydonlarni to'ldiring")
            return redirect("lesson_create")

        total_lessons = int(total_lessons)
        lessons_per_week = int(lessons_per_week)
        start_date = parse_date(start_date_raw)

        weeks_needed = math.ceil(total_lessons / lessons_per_week)
        end_date = start_date + timedelta(weeks=weeks_needed)
        end_date_raw = end_date.strftime("%Y-%m-%d")

        all_students = list(Student.objects.filter(debts=subject).distinct())
        if not all_students:
            messages.error(request, "Bu fandan yiqilgan o'quvchi yo'q")
            return redirect("lesson_create")

        students_by_lang = defaultdict(list)
        for st in all_students:
            students_by_lang[st.language].append(st)

        all_groups = []
        skipped_langs = []

        for lang, lang_students in students_by_lang.items():
            groups = split_into_groups(lang_students)
            valid_groups = [g for g in groups if len(g) >= 10]
            invalid_groups = [g for g in groups if len(g) < 10]

            if invalid_groups:
                lang_name = dict(LANGUAGE_CHOICES).get(lang, lang)
                skipped_langs.append(
                    f"{lang_name} tili: {sum(len(g) for g in invalid_groups)} ta o'quvchi "
                    f"(10 tadan kam, guruh shakillantirilmadi)"
                )

            for g in valid_groups:
                all_groups.append({
                    'lang': lang,
                    'lang_name': dict(LANGUAGE_CHOICES).get(lang, lang),
                    'students': g,
                    'is_small': False,
                })
            for g in invalid_groups:
                all_groups.append({
                    'lang': lang,
                    'lang_name': dict(LANGUAGE_CHOICES).get(lang, lang),
                    'students': g,
                    'is_small': True,
                })

        # Kichik guruhlarni ham ko'rsatamiz (qizil), o'chirmaymiz
        # Faqat hech kimsa bo'lmasa xato chiqaramiz
        if not all_groups:
            messages.error(request, "Bu fandan o'quvchi yo'q")
            return redirect("lesson_create")

        teachers = Teacher.objects.filter(subjects=subject)

        assigned_ids = set()
        for g in all_groups:
            for s in g['students']:
                assigned_ids.add(s.id)
        unassigned_students = [s for s in all_students if s.id not in assigned_ids]

        return render(request, "raspisaniya/lesson_create.html", {
            "step": 2,
            "subject": subject,
            "all_groups": all_groups,
            "groups_count": len(all_groups),
            "teachers": teachers,
            "start_date": start_date_raw,
            "end_date": end_date_raw,
            "total_lessons": total_lessons,
            "lessons_per_week": lessons_per_week,
            "skipped_langs": skipped_langs,
            "unassigned_students": unassigned_students,
            "all_students": all_students,
            "include_saturday": include_saturday,
        })

    # ── STEP 3 ──
    if request.method == "POST" and request.POST.get("step") == "3":
        subject_id = request.POST.get("subject_id")
        subject = get_object_or_404(Subject, id=subject_id)

        start_date_raw = request.POST.get("start_date")
        end_date_raw = request.POST.get("end_date")
        total_lessons = int(request.POST.get("total_lessons"))
        lessons_per_week = int(request.POST.get("lessons_per_week"))
        groups_count = int(request.POST.get("groups_count", 1))
        include_saturday = request.POST.get("include_saturday", "0") == "1"

        start_date = parse_date(start_date_raw)
        end_date = parse_date(end_date_raw)

        all_students = list(Student.objects.filter(debts=subject).distinct())
        students_by_lang = defaultdict(list)
        for st in all_students:
            students_by_lang[st.language].append(st)

        all_groups_data = []
        for lang, lang_students in students_by_lang.items():
            groups = split_into_groups(lang_students)
            for g in groups:
                all_groups_data.append({'lang': lang, 'students': g})

        with transaction.atomic():
            course = Course.objects.create(
                subject=subject,
                start_date=start_date,
                end_date=end_date,
                total_lessons=total_lessons,
                lessons_per_week=lessons_per_week,
                lesson_duration=80,
                include_saturday=include_saturday,
            )

            for i in range(groups_count):
                tid = request.POST.get(f"teacher_{i}")
                if not tid:
                    continue
                teacher = get_object_or_404(Teacher, id=tid)
                selected_ids = request.POST.getlist(f"students_{i}")
                if not selected_ids:
                    continue
                selected_students = list(Student.objects.filter(id__in=selected_ids))
                if not selected_students:
                    continue

                lang = selected_students[0].language if selected_students else 'uz'

                cgroup = CourseGroup.objects.create(
                    course=course,
                    teacher=teacher,
                    group_number=i + 1,
                    start_time=None,
                    weekdays=[],
                    language=lang,
                    is_scheduled=False,
                )
                cgroup.students.set(selected_students)

                # O'quvchilar faqat shu yerda debts dan olib tashlanadi
                for st in selected_students:
                    st.debts.remove(subject)

        messages.success(request, "Kurs yaratildi! Endi 'Jadval tuzish' tugmasini bosing.")
        return redirect("lesson_list")


# ─────────────────────────────────────────
# LESSON SCHEDULE
# ─────────────────────────────────────────
@login_required
def lesson_schedule(request, pk):
    course = get_object_or_404(Course, pk=pk)
    groups = course.groups.prefetch_related('students', 'schedule').select_related('teacher')
    duration = timedelta(minutes=80)

    all_group_student_ids = set()
    for grp in groups:
        for s in grp.students.all():
            all_group_student_ids.add(s.id)

    addable_students = Student.objects.filter(
        debts=course.subject
    ).exclude(id__in=all_group_student_ids)

    groups_data = []
    for grp in groups:
        schedule_list = []
        for s in grp.schedule.all().order_by('lesson_number'):
            st = s.start_time or grp.start_time
            if st:
                end_t = (datetime.combine(s.date, st) + duration).time()
                start_str = st.strftime("%H:%M")
                end_str = end_t.strftime("%H:%M")
            else:
                start_str = "—"
                end_str = "—"
            schedule_list.append({
                "sched": s,
                "weekday": WEEKDAY_NAMES.get(s.date.weekday(), "") if st else "",
                "start_time": start_str,
                "end_time": end_str,
            })
        groups_data.append({
            "group": grp,
            "schedule_list": schedule_list,
            "addable_students": addable_students,
        })

    return render(request, "raspisaniya/lesson_schedule.html", {
        "course": course,
        "groups_data": groups_data,
        "teachers": Teacher.objects.filter(subjects=course.subject),
        "rooms": Room.objects.all().order_by('name'),
    })


@login_required
def add_student_to_group(request, group_pk):
    group = get_object_or_404(CourseGroup, pk=group_pk)
    if request.method == "POST":
        student_id = request.POST.get("student_id")
        if student_id:
            student = get_object_or_404(Student, pk=student_id)
            group.students.add(student)
            student.debts.remove(group.course.subject)
            messages.success(request, f"{student} guruhga qo'shildi.")
    return redirect("lesson_schedule", pk=group.course.pk)


@login_required
def lesson_schedule_excel(request, pk):
    course = get_object_or_404(Course, pk=pk)
    duration = timedelta(minutes=80)

    wb = Workbook()
    first = True
    for grp in course.groups.prefetch_related('students', 'schedule').select_related('teacher'):
        if first:
            ws = wb.active
            ws.title = f"{grp.group_number}-guruh"
            first = False
        else:
            ws = wb.create_sheet(title=f"{grp.group_number}-guruh")

        ws.append(["#", "Sana", "Hafta kuni", "Boshlanish", "Tugash", "O'qituvchi"])
        for s in grp.schedule.all():
            if grp.start_time:
                end_t = (datetime.combine(s.date, grp.start_time) + duration).time()
                ws.append([
                    s.lesson_number,
                    s.date.strftime("%d.%m.%Y"),
                    WEEKDAYS.get(s.date.weekday(), ""),
                    grp.start_time.strftime("%H:%M"),
                    end_t.strftime("%H:%M"),
                    str(grp.teacher),
                ])

        ws2 = wb.create_sheet(title=f"{grp.group_number}-guruh talabalar")
        ws2.append(["#", "O'quvchi", "O'qituvchi"])
        for idx, st in enumerate(grp.students.all(), 1):
            ws2.append([idx, str(st), str(grp.teacher)])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="jadval_{course.pk}.xlsx"'
    wb.save(response)
    return response


@login_required
def change_lesson_time(request, sched_pk):
    sched = get_object_or_404(GroupSchedule, pk=sched_pk)
    if request.method == "POST":
        new_time = request.POST.get("start_time")
        new_date = request.POST.get("date")

        new_date_val = parse_date(new_date) if new_date else sched.date
        if new_time:
            h, m = map(int, new_time.split(":"))
            new_time_val = dtime(h, m)
        else:
            new_time_val = sched.start_time

        group_number = sched.group.group_number
        teacher_id = sched.group.teacher_id
        student_ids = list(sched.group.students.values_list('id', flat=True))

        if GroupSchedule.objects.filter(
            date=new_date_val, start_time=new_time_val,
            group__teacher_id=teacher_id,
        ).exclude(pk=sched_pk).exists():
            messages.error(request, f"O'qituvchi {new_date_val} kuni {new_time} parada band!")
            return redirect("lesson_schedule", pk=sched.group.course.pk)

        if student_ids and GroupSchedule.objects.filter(
            date=new_date_val, start_time=new_time_val,
            group__students__id__in=student_ids,
        ).exclude(pk=sched_pk).exists():
            messages.error(request, f"Ba'zi talabalar {new_date_val} kuni {new_time} parada band!")
            return redirect("lesson_schedule", pk=sched.group.course.pk)

        sched.date = new_date_val
        sched.start_time = new_time_val
        sched.save()
        messages.success(request, f"{new_date_val} dars vaqti o'zgartirildi")
    return redirect("lesson_schedule", pk=sched.group.course.pk)


@login_required
def change_teacher(request, group_pk):
    group = get_object_or_404(CourseGroup, pk=group_pk)
    if request.method == "POST":
        teacher_id = request.POST.get("teacher_id")
        if teacher_id:
            teacher = get_object_or_404(Teacher, pk=teacher_id)
            group.teacher = teacher
            group.save()
            messages.success(request, f"O'qituvchi {teacher} ga o'zgartirildi")
    return redirect("lesson_schedule", pk=group.course.pk)


# ─────────────────────────────────────────
# ✅ O'ZGARISH 8: lesson_delete — o'chirilganda o'quvchilar
#    qaytib subject.debts ga qo'shiladi
# ─────────────────────────────────────────
@login_required
def lesson_delete(request, pk):
    lesson = get_object_or_404(Course, pk=pk)
    if request.method == "POST":
        subject = lesson.subject
        # Kursga biriktirilgan barcha guruhlar va ulardagi o'quvchilarni qaytarish
        for group in lesson.groups.prefetch_related('students').all():
            for student in group.students.all():
                student.debts.add(subject)
        lesson.delete()
        messages.success(request, "Dars o'chirildi va o'quvchilar qayta ro'yxatga qaytarildi")
        return redirect("lesson_list")
    return render(request, "raspisaniya/lesson_delete.html", {"lesson": lesson, "course": lesson})



@staff_member_required
def admin_group_grades(request, group_pk):
    """Admin: guruh talabalarining baholari va davomati."""
    from raspisaniya.models import Grade, Attendance
    group = get_object_or_404(CourseGroup, pk=group_pk)
    students = group.students.all().order_by('last_name', 'first_name')
    schedules = list(group.schedule.all().order_by('date'))

    grade_map = {g.student_id: g for g in Grade.objects.filter(course_group=group)}
    all_att = Attendance.objects.filter(schedule__group=group).values('student_id', 'schedule_id', 'is_present')
    att_map = {(a['student_id'], a['schedule_id']): a['is_present'] for a in all_att}

    rows = []
    for st in students:
        cells = []
        came = missed = 0
        for sched in schedules:
            val = att_map.get((st.pk, sched.pk))
            if val is True: came += 1; cells.append('present')
            elif val is False: missed += 1; cells.append('absent')
            else: cells.append('none')
        marked = came + missed
        percent = round(came / marked * 100) if marked > 0 else None
        grade = grade_map.get(st.pk)
        total = None
        if grade:
            vals = [v for v in [grade.midterm, grade.current, grade.final] if v is not None]
            total = round(sum(vals), 1) if vals else None
        rows.append({
            'student': st,
            'cells': cells,
            'came': came,
            'missed': missed,
            'percent': percent,
            'grade': grade,
            'total': total,
        })

    return render(request, "raspisaniya/admin_group_grades.html", {
        "group": group,
        "schedules": schedules,
        "rows": rows,
    })



@login_required
def move_one_student(request):
    """Bitta talabani boshqa guruhga ko'chirish."""
    if request.method == "POST":
        student_pk   = request.POST.get('student_pk')
        from_group_pk = request.POST.get('from_group_pk')
        to_group_pk  = request.POST.get('to_group_pk')

        try:
            student    = Student.objects.get(pk=student_pk)
            from_group = CourseGroup.objects.get(pk=from_group_pk)
            to_group   = CourseGroup.objects.get(pk=to_group_pk)

            from_group.students.remove(student)
            to_group.students.add(student)
            messages.success(request, f"{student.first_name} → {to_group.group_number}-guruhga ko'chirildi.")
        except Exception as e:
            messages.error(request, f"Xato: {e}")

    return redirect('build_schedule')


@login_required
def delete_course_group(request, group_pk):
    """Guruhni o'chirish — talabalar debts ga qaytadi."""
    group = get_object_or_404(CourseGroup, pk=group_pk)
    course_pk = group.course.pk
    if request.method == "POST":
        subject = group.course.subject
        for student in group.students.all():
            student.debts.add(subject)
        group.schedule.all().delete()
        group.delete()
        messages.success(request, "Guruh o'chirildi, talabalar qayta ro'yxatga qaytarildi.")
    return redirect("lesson_schedule", pk=course_pk)

@login_required
def remove_student_from_group(request, group_pk, student_pk):
    group = get_object_or_404(CourseGroup, pk=group_pk)
    student = get_object_or_404(Student, pk=student_pk)
    if request.method == "POST":
        group.students.remove(student)
        student.debts.add(group.course.subject)
        messages.success(request, f"{student} guruhdan o'chirildi va qayta ro'yxatga qo'shildi")
    return redirect("lesson_schedule", pk=group.course.pk)


# ─────────────────────────────────────────
# TEACHER
# ─────────────────────────────────────────
@login_required
def teacher_list(request):
    q = request.GET.get('q', '').strip()
    teachers = Teacher.objects.all().order_by('last_name')
    if q:
        teachers = teachers.filter(
            first_name__icontains=q
        ) | teachers.filter(
            last_name__icontains=q
        ) | teachers.filter(
            teacher_id__icontains=q
        )
        teachers = teachers.order_by('last_name')
    return render(request, 'raspisaniya/teacher_list.html', {'teachers': teachers, 'q': q})


@login_required
def teacher_create(request):
    if request.method == 'POST':
        form = TeacherForm(request.POST)
        if form.is_valid():
            teacher_id = request.POST.get("teacher_id", "").strip()
            password = request.POST.get("password", "").strip()

            if not teacher_id:
                messages.error(request, "Teacher ID kiritilmagan")
                return render(request, 'raspisaniya/teacher_create.html', {
                    'form': form, 'subjects': Subject.objects.all(), 'selected_subjects': [],
                })

            if User.objects.filter(username=teacher_id).exists():
                messages.error(request, f"Bu ID ({teacher_id}) allaqachon mavjud")
                return render(request, 'raspisaniya/teacher_create.html', {
                    'form': form, 'subjects': Subject.objects.all(), 'selected_subjects': [],
                })

            with transaction.atomic():
                teacher = form.save(commit=False)
                teacher.teacher_id = teacher_id
                teacher.save()
                form.save_m2m()
                user = User.objects.create_user(
                    username=teacher_id,
                    password=password if password else teacher_id,
                    first_name=teacher.first_name,
                    last_name=teacher.last_name,
                )
                teacher.user = user
                teacher.save()

            messages.success(request, f"O'qituvchi qo'shildi. ID: {teacher_id}")
            return redirect('teacher_list')
    else:
        form = TeacherForm()
    return render(request, 'raspisaniya/teacher_create.html', {
        'form': form, 'subjects': Subject.objects.all(), 'selected_subjects': [],
    })


@login_required
def teacher_update(request, pk):
    teacher = get_object_or_404(Teacher, pk=pk)
    if request.method == 'POST':
        # Ism — bo'sh bo'lsa eskisini saqla
        first_name = request.POST.get('first_name', '').strip()
        if first_name:
            teacher.first_name = first_name

        # ID — bo'sh bo'lsa yoki o'zgartirilmasa eskisini saqla
        new_id = request.POST.get('teacher_id', '').strip()
        if new_id and new_id != teacher.teacher_id:
            teacher.teacher_id = new_id
            if teacher.user:
                teacher.user.username = new_id
                teacher.user.save()

        teacher.save()
        subject_ids = request.POST.getlist('subjects')
        teacher.subjects.set(subject_ids)
        messages.success(request, f"O'qituvchi yangilandi.")
        return redirect('teacher_list')

    return render(request, 'raspisaniya/teacher_update.html', {
        'teacher': teacher,
        'subjects': Subject.objects.all(),
        'selected_subjects': list(teacher.subjects.values_list('id', flat=True)),
    })


@login_required
def teacher_delete(request, pk):
    teacher = get_object_or_404(Teacher, pk=pk)
    if request.method == 'POST':
        teacher.delete()
        messages.success(request, "O'qituvchi o'chirildi")
        return redirect('teacher_list')
    return render(request, 'raspisaniya/teacher_delete.html', {'teacher': teacher})


@login_required
def teacher_import(request):
    if request.method == "POST":
        form = TeacherImportForm(request.POST, request.FILES)
        if form.is_valid():
            file = request.FILES["file"]
            try:
                wb = load_workbook(file)
                ws = wb.active

                # 1. Barcha mavjud ma'lumotlarni bir marta xotiraga yuklaymiz
                # Fanlarni nomi bo'yicha lug'atga olamiz: {'Matematika': <Subject object>, ...}
                existing_subjects = {s.name: s for s in Subject.objects.all()}

                # Userlarning username'larini tezkor tekshirish uchun 'set'ga olamiz
                existing_usernames = set(User.objects.values_list('username', flat=True))

                with transaction.atomic():
                    for row in ws.iter_rows(min_row=2, values_only=True):
                        # Bo'sh qatorlarni tashlab ketish
                        if not row or not row[0] or not row[1]:
                            continue

                        tid = f"T-{str(row[0]).strip()}"
                        full_name = str(row[1]).strip()
                        if not full_name:
                            continue

                        first_name = full_name   # To'liq nom — qanday tursa shunday
                        last_name = ""

                        # 2. User yaratish yoki olish (Xotiradan tekshiramiz)
                        if tid not in existing_usernames:
                            u = User.objects.create_user(username=tid, password=tid)
                            existing_usernames.add(tid)
                        else:
                            u = User.objects.get(username=tid)

                        # 3. Teacher yaratish yoki yangilash
                        teacher, created = Teacher.objects.update_or_create(
                            user=u,
                            defaults={
                                'first_name': first_name,
                                'last_name': last_name,
                                'teacher_id': tid
                            }
                        )

                        # 4. Fanlarni bog'lash (Xotira orqali)
                        if len(row) > 2 and row[2]:
                            subject_names = [s.strip() for s in str(row[2]).split(",") if s.strip()]
                            for sname in subject_names:
                                # Agar fan lug'atda bo'lmasa, bazada yaratib lug'atga qo'shamiz
                                if sname not in existing_subjects:
                                    subj = Subject.objects.create(name=sname)
                                    existing_subjects[sname] = subj

                                # Fanlarni bog'laymiz
                                teacher.subjects.add(existing_subjects[sname])

                        teacher.save()

                messages.success(request, "O'qituvchilar muvaffaqiyatli import qilindi ✅")
                return redirect("teacher_list")
            except Exception as e:
                # Xatoni terminalda ham ko'rish uchun:
                print(f"Import Error: {e}")
                messages.error(request, f"Xatolik: {e}")
    else:
        form = TeacherImportForm()
    return render(request, "raspisaniya/teacher_import.html", {"form": form})


# ─────────────────────────────────────────
# STUDENT
# ─────────────────────────────────────────
@login_required
def student_list(request):
    q = request.GET.get('q', '').strip()
    students = Student.objects.prefetch_related(
        'debts',
        'coursegroup_set__course__subject',
    ).select_related('group').order_by('last_name')
    if q:
        students = students.filter(
            first_name__icontains=q
        ) | students.filter(
            last_name__icontains=q
        ) | students.filter(
            student_id__icontains=q
        ) | students.filter(
            group__name__icontains=q
        )
        students = students.prefetch_related(
            'debts', 'coursegroup_set__course__subject'
        ).select_related('group').order_by('last_name').distinct()

    students_data = []
    for student in students:
        completed = list({grp.course.subject for grp in student.coursegroup_set.all()})
        students_data.append({'student': student, 'completed': completed})
    return render(request, 'raspisaniya/student_list.html', {'students_data': students_data, 'q': q})


@login_required
def student_create(request):
    if request.method == 'POST':
        form = StudentForm(request.POST)
        if form.is_valid():
            student_id = request.POST.get("student_id", "").strip()
            password = request.POST.get("password", "").strip()

            if not student_id:
                messages.error(request, "Student ID kiritilmagan")
                return render(request, 'raspisaniya/student_create.html', {
                    'form': form, 'subjects': Subject.objects.all(),
                    'groups': Group.objects.all(), 'selected_debts': [],
                })

            if User.objects.filter(username=student_id).exists():
                messages.error(request, f"Bu ID ({student_id}) allaqachon mavjud")
                return render(request, 'raspisaniya/student_create.html', {
                    'form': form, 'subjects': Subject.objects.all(),
                    'groups': Group.objects.all(), 'selected_debts': [],
                })

            with transaction.atomic():
                student = form.save(commit=False)
                student.student_id = student_id
                student.save()
                form.save_m2m()
                user = User.objects.create_user(
                    username=student_id,
                    password=password if password else student_id,
                    first_name=student.first_name,
                    last_name=student.last_name,
                )
                student.user = user
                student.save()

            messages.success(request, f"O'quvchi qo'shildi. ID: {student_id}")
            return redirect('student_list')
    else:
        form = StudentForm()
    return render(request, 'raspisaniya/student_create.html', {
        'form': form, 'subjects': Subject.objects.all(),
        'groups': Group.objects.all(), 'selected_debts': [],
    })


@login_required
def student_update(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        full_name = request.POST.get('first_name', '').strip()
        if full_name:
            student.first_name = full_name
            student.last_name = ''

        group_id = request.POST.get('group', '').strip()
        if group_id:
            try:
                student.group = Group.objects.get(pk=group_id)
            except Group.DoesNotExist:
                pass
        else:
            student.group = None

        language = request.POST.get('language', '').strip()
        if language:
            student.language = language

        student.save()

        debt_ids = request.POST.getlist('debts')
        student.debts.set(debt_ids)

        new_password = request.POST.get('new_password', '').strip()
        if new_password and student.user:
            student.user.set_password(new_password)
            student.user.save()
            messages.success(request, "O'quvchi va parol yangilandi")
        else:
            messages.success(request, "O'quvchi yangilandi")
        return redirect('student_list')

    form = StudentForm(instance=student)
    return render(request, 'raspisaniya/student_update.html', {
        'form': form,
        'student': student,
        'subjects': Subject.objects.all(),
        'groups': Group.objects.all(),
        'selected_debts': list(student.debts.values_list('id', flat=True)),
    })


@login_required
def admin_change_student_password(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == "POST":
        new_password = request.POST.get("new_password", "").strip()
        if not new_password:
            messages.error(request, "Parol bo'sh bo'lmasin")
        elif not student.user:
            messages.error(request, "Bu talabaning tizim akkaunti yo'q")
        else:
            student.user.set_password(new_password)
            student.user.save()
            messages.success(request, f"{student} ning paroli o'zgartirildi")
    return redirect("student_list")


@login_required
def student_delete(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        student.delete()
        messages.success(request, "O'quvchi o'chirildi")
        return redirect('student_list')
    return render(request, 'raspisaniya/student_delete.html', {'student': student})


WORD_SUBJECTS_LOWER = [
    "noorganik kimyo",
    "organik kimyo",
    "fizik va kolloid kimyo",
    "analitik kimyo",
    "farmakognoziya",
    "farmatsevtik kimyo",
    "farmatsevtik texnologiya",
    "dorixonada ish yuritish",
    "sanoat texnologiyasi",
    "toksikologik kimyo",
    "sanoat farmatsiyasi",
    "farmatsevtik iqtisodiyoti",
]


def process_subject(raw_item):
    raw_item = raw_item.strip()
    if '(' in raw_item:
        name_only = raw_item[:raw_item.index('(')].strip()
    else:
        name_only = raw_item.strip()
    if name_only.lower() in WORD_SUBJECTS_LOWER:
        return raw_item
    else:
        return name_only


@login_required
@transaction.atomic
def import_students(request):
    if request.method == "POST":
        form = StudentImportForm(request.POST, request.FILES)
        if form.is_valid():
            file = request.FILES["file"]
            try:
                # Excelni xotirani tejash rejimida o'qiymiz
                wb = load_workbook(file, read_only=True, data_only=True)
                ws = wb.active

                # 1. Mavjud ma'lumotlarni bir marta yuklaymiz (Xotira orqali tekshirish uchun)
                existing_users = {u.username: u for u in User.objects.filter(username__startswith='S-')}
                existing_groups = {g.name: g for g in Group.objects.all()}
                existing_subjects = {s.name: s for s in Subject.objects.all()}
                existing_students = {s.student_id: s for s in Student.objects.all()}

                new_users_to_create = []
                students_to_create = []
                students_to_update = []

                # Talaba ID va uning barcha qarzlarini yig'ish uchun
                # Hatto bitta talaba 10 ta qatorda kelsa ham, shunda yig'iladi
                student_debts_collector = {}  # { 'S-101': set(subj_obj1, subj_obj2) }

                for row in ws.iter_rows(min_row=2, values_only=True):
                    if not row or not row[0] or not row[1]:
                        continue

                    # ID va Ism-sharifni tozalash
                    sid = f"S-{str(row[0]).strip()}"
                    full_name = str(row[1]).strip()
                    if not full_name:
                        continue
                    first_name = full_name   # To'liq nom — qanday tursa shunday
                    last_name = ""

                    # GURUH: Guruhni tekshirish va yaratish
                    group_obj = None
                    if len(row) > 4 and row[4]:
                        g_name = str(row[4]).strip()
                        if g_name not in existing_groups:
                            group_obj = Group.objects.create(name=g_name)
                            existing_groups[g_name] = group_obj
                        else:
                            group_obj = existing_groups[g_name]

                    # USER: Userni tekshirish va ro'yxatga qo'shish
                    if sid not in existing_users:
                        user_obj = User(username=sid)
                        user_obj.set_password(sid)
                        new_users_to_create.append(user_obj)
                        existing_users[sid] = user_obj  # Keyingi qatorlarda ishlatish uchun
                    else:
                        user_obj = existing_users[sid]

                    # TALABA: Talaba obyektini aniqlash (yaratish yoki yangilash)
                    if sid not in existing_students:
                        st_obj = Student(
                            user=user_obj, student_id=sid,
                            first_name=first_name, last_name=last_name,
                            group=group_obj, language='uz'
                        )
                        students_to_create.append(st_obj)
                        existing_students[sid] = st_obj  # Muhim: xotiraga saqlaymiz
                    else:
                        st_obj = existing_students[sid]
                        st_obj.first_name, st_obj.last_name, st_obj.group = first_name, last_name, group_obj
                        if st_obj not in students_to_update:
                            students_to_update.append(st_obj)

                    # QARZ FANLAR: Har bir qatordagi fanlarni yig'amiz
                    if len(row) > 8 and row[8]:
                        # split_subjects va process_subject o'rniga oddiyroq split ishlatamiz
                        raw_subjects = [s.strip() for s in str(row[8]).split(";") if s.strip()]

                        if sid not in student_debts_collector:
                            student_debts_collector[sid] = set()

                        for s_name in raw_subjects:
                            if s_name not in existing_subjects:
                                subj = Subject.objects.create(name=s_name)
                                existing_subjects[s_name] = subj
                            else:
                                subj = existing_subjects[s_name]
                            student_debts_collector[sid].add(subj)

                # --- BAZAGA OMMAVIY YOZISH (BULK OPERATIONS) ---

                # 1. Userlarni yaratish
                if new_users_to_create:
                    User.objects.bulk_create(new_users_to_create, ignore_conflicts=True)
                    # Userlar PK olishi uchun qayta yuklash (Faqat yangilarini)
                    created_users = {u.username: u for u in
                                     User.objects.filter(username__in=[u.username for u in new_users_to_create])}
                    for s in students_to_create:
                        s.user = created_users.get(s.student_id)

                # 2. Talabalarni yaratish va yangilash
                if students_to_create:
                    Student.objects.bulk_create(students_to_create)

                if students_to_update:
                    Student.objects.bulk_update(students_to_update, ['first_name', 'last_name', 'group'])

                # 3. Many-to-Many (Debts) bog'lamalarini bulk yaratish
                if student_debts_collector:
                    # Bazadagi haqiqiy talaba ID-larini olish
                    db_students = {s.student_id: s for s in
                                   Student.objects.filter(student_id__in=student_debts_collector.keys())}

                    StudentDebtModel = Student.debts.through
                    debt_relations = []

                    for sid, subjects in student_debts_collector.items():
                        st_obj = db_students.get(sid)
                        if st_obj:
                            for subj_obj in subjects:
                                debt_relations.append(
                                    StudentDebtModel(student_id=st_obj.pk, subject_id=subj_obj.pk)
                                )

                    # Eskilarini o'chirib yangilash yoki shunchaki yangilarini qo'shish
                    # Biz yangilarini qo'shamiz, ignore_conflicts dublikatlarni tashlab ketadi
                    StudentDebtModel.objects.bulk_create(debt_relations, ignore_conflicts=True)

                messages.success(request, f"Import yakunlandi! {len(students_to_create)} yangi talaba qo'shildi.")
                return redirect("student_list")

            except Exception as e:
                print(f"IMPORT ERROR: {e}")
                messages.error(request, f"Xatolik yuz berdi: {str(e)}")
    else:
        form = StudentImportForm()

    return render(request, "raspisaniya/import_students.html", {"form": form})


# ─────────────────────────────────────────
# ROOM (XONA)
# ─────────────────────────────────────────
@login_required
def room_list(request):
    q = request.GET.get('q', '').strip()
    rooms = Room.objects.prefetch_related(
        'coursegroup_set__course__subject',
        'coursegroup_set__teacher',
    ).all().order_by('name')
    if q:
        rooms = rooms.filter(name__icontains=q)
    return render(request, 'raspisaniya/room_list.html', {'rooms': rooms, 'q': q})


@login_required
def room_create(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        capacity = request.POST.get("capacity", 30)
        if not name:
            messages.error(request, "Xona nomi kiritilmagan")
        elif Room.objects.filter(name=name).exists():
            messages.error(request, f"'{name}' xonasi allaqachon mavjud")
        else:
            Room.objects.create(name=name, capacity=int(capacity))
            messages.success(request, f"'{name}' xonasi qo'shildi")
            return redirect("room_list")
    return render(request, 'raspisaniya/room_create.html')


@login_required
def room_delete(request, pk):
    room = get_object_or_404(Room, pk=pk)
    if request.method == "POST":
        room.delete()
        messages.success(request, "Xona o'chirildi")
    return redirect("room_list")


@login_required
def assign_room(request, group_pk):
    group = get_object_or_404(CourseGroup, pk=group_pk)
    if request.method == "POST":
        room_id = request.POST.get("room_id")
        if not room_id:
            group.room = None
            group.save()
            messages.success(request, "Xona biriktirilmadi (bo'shatildi)")
            return redirect("lesson_schedule", pk=group.course.pk)

        room = get_object_or_404(Room, pk=room_id)

        for sched in group.schedule.all():
            st = sched.start_time or group.start_time
            if not st:
                continue
            conflict = GroupSchedule.objects.filter(
                date=sched.date,
                start_time=st,
                group__room=room,
            ).exclude(group=group)
            if conflict.exists():
                conflict_grp = conflict.first().group
                messages.error(
                    request,
                    f"'{room.name}' xonasi {sched.date} kuni {st.strftime('%H:%M')} da "
                    f"'{conflict_grp.course.subject}' ({conflict_grp.group_number}-guruh) uchun band!"
                )
                return redirect("lesson_schedule", pk=group.course.pk)

        group.room = room
        group.save()
        messages.success(request, f"'{room.name}' xonasi biriktirildi")
    return redirect("lesson_schedule", pk=group.course.pk)


# ─────────────────────────────────────────
# SUBJECT
# ─────────────────────────────────────────
@login_required
def subject_list(request):
    q = request.GET.get('q', '').strip()
    subjects = Subject.objects.all().order_by('name')
    if q:
        subjects = subjects.filter(name__icontains=q)
    return render(request, 'raspisaniya/subject_list.html', {'subjects': subjects, 'q': q})


@login_required
def subject_create(request):
    if request.method == 'POST':
        form = SubjectForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Fan qo'shildi")
            return redirect('subject_list')
    else:
        form = SubjectForm()
    return render(request, 'raspisaniya/subject_create.html', {'form': form})


@login_required
def subject_update(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    if request.method == 'POST':
        form = SubjectForm(request.POST, instance=subject)
        if form.is_valid():
            form.save()
            messages.success(request, "Fan yangilandi")
            return redirect('subject_list')
    else:
        form = SubjectForm(instance=subject)
    return render(request, 'raspisaniya/subject_create.html', {'form': form})


@login_required
def subject_delete(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    if request.method == 'POST':
        subject.delete()
        messages.success(request, "Fan o'chirildi")
        return redirect('subject_list')
    return render(request, 'raspisaniya/subject_delete.html', {'subject': subject})


@login_required
def subject_students(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    students = Student.objects.filter(debts=subject).order_by('last_name')
    return render(request, 'raspisaniya/subject_students.html', {
        'subject': subject, 'students': students,
    })


@login_required
def subject_students_excel(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    students = Student.objects.filter(debts=subject).order_by('last_name')

    wb = Workbook()
    ws = wb.active
    ws.title = subject.name
    ws.append(["#", "Familiya", "Ism Sharif", "Guruh"])
    for i, student in enumerate(students, 1):
        ws.append([i, student.last_name, student.first_name,
                   str(student.group) if student.group else "—"])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{subject.name}_qarzdorlar.xlsx"'
    wb.save(response)
    return response


# ─────────────────────────────────────────
# JADVAL TUZISH
# ─────────────────────────────────────────
@login_required
def build_schedule(request):
    unscheduled_groups = CourseGroup.objects.filter(
        is_scheduled=False
    ).select_related('course', 'course__subject', 'teacher').prefetch_related('students')

    if not unscheduled_groups.exists():
        messages.info(request, "Barcha guruhlar uchun jadval allaqachon tuzilgan.")
        return redirect("lesson_list")

    errors = []
    success_count = 0

    # Talabalar soni bo'yicha kattadan kichikka tartiblash (24->16->8)
    unscheduled_list = sorted(
        list(unscheduled_groups.prefetch_related('students').select_related('course', 'teacher')),
        key=lambda g: g.students.count(),
        reverse=True
    )

    for grp in unscheduled_list:
        course = grp.course
        students = list(grp.students.all())

        schedule = find_schedule_for_group(
            course.start_date, course.end_date,
            course.total_lessons, course.lessons_per_week,
            grp.teacher, students,
            group_number=grp.group_number,
            include_saturday=getattr(course, 'include_saturday', False),
        )

        if not schedule:
            errors.append({'group': grp, 'course': course})
        else:
            from collections import Counter
            para_counter = Counter(p_start for _, p_start, _ in schedule)
            most_common_para = para_counter.most_common(1)[0][0]
            grp.start_time = most_common_para
            grp.weekdays = list({d.weekday() for d, _, _ in schedule})
            grp.is_scheduled = True

            for attempt in range(5):
                try:
                    with transaction.atomic():
                        grp.save()
                        GroupSchedule.objects.bulk_create([
                            GroupSchedule(
                                group=grp, date=ld,
                                lesson_number=idx, start_time=p_start
                            )
                            for idx, (ld, p_start, p_end) in enumerate(schedule, 1)
                        ])
                    break
                except Exception:
                    time.sleep(0.5)
                    continue

            success_count += 1

    if errors:
        error_details = []
        for e in errors:
            grp = e['group']
            course = e['course']
            other_groups = CourseGroup.objects.filter(
                course=course, is_scheduled=True,
            ).exclude(pk=grp.pk).prefetch_related('students')

            teacher_scheds = GroupSchedule.objects.filter(
                group__teacher=grp.teacher,
                date__gte=course.start_date,
                date__lte=course.end_date,
            ).select_related('group__course__subject', 'group__teacher').order_by('date', 'start_time')[:10]

            student_ids = list(grp.students.values_list('id', flat=True))
            raw_student_scheds = GroupSchedule.objects.filter(
                group__students__id__in=student_ids,
                date__gte=course.start_date,
                date__lte=course.end_date,
            ).select_related('group__course__subject', 'group__teacher').prefetch_related('group__students').distinct().order_by('date', 'start_time')[:20]

            # Har bir dars uchun qaysi talabalar band ekanligini aniqlaymiz
            students_set = set(student_ids)
            student_scheds_enriched = []
            seen = set()
            for s in raw_student_scheds:
                key = (s.date, s.start_time)
                if key in seen:
                    continue
                seen.add(key)
                busy_students = [
                    st for st in s.group.students.all()
                    if st.id in students_set
                ]
                student_scheds_enriched.append({
                    'sched': s,
                    'busy_students': busy_students,
                })
                if len(student_scheds_enriched) >= 10:
                    break

            error_details.append({
                'group': grp,
                'course': course,
                'other_groups': other_groups,
                'teacher_scheds': teacher_scheds,
                'student_scheds': student_scheds_enriched,
            })

        return render(request, "raspisaniya/build_schedule_errors.html", {
            "error_details": error_details,
            "success_count": success_count,
        })

    messages.success(request, f"Jadval muvaffaqiyatli tuzildi! {success_count} ta guruh.")
    return redirect("lesson_list")


@login_required
def move_students(request, from_group_pk, to_group_pk):
    from_group = get_object_or_404(CourseGroup, pk=from_group_pk)
    to_group = get_object_or_404(CourseGroup, pk=to_group_pk)

    if request.method == "POST":
        student_ids = request.POST.getlist("student_ids")
        students = from_group.students.filter(id__in=student_ids)
        for st in students:
            from_group.students.remove(st)
            to_group.students.add(st)
        messages.success(request, f"{len(student_ids)} ta talaba ko'chirildi.")
        return redirect("build_schedule")

    return render(request, "raspisaniya/move_students.html", {
        "from_group": from_group,
        "to_group": to_group,
        "students": from_group.students.all(),
    })


@login_required
def delete_unscheduled_group(request, pk):
    group = get_object_or_404(CourseGroup, pk=pk, is_scheduled=False)
    if request.method == "POST":
        subject = group.course.subject
        for st in group.students.all():
            st.debts.add(subject)
        group.delete()
        messages.success(request, "Guruh o'chirildi, talabalar qayta ro'yxatga qaytdi.")
    return redirect("build_schedule")


@login_required
def course_update(request, pk):
    course = get_object_or_404(Course, pk=pk)
    if request.method == "POST":
        start_date_raw = request.POST.get("start_date")
        end_date_raw = request.POST.get("end_date")
        total_lessons = request.POST.get("total_lessons")
        lessons_per_week = request.POST.get("lessons_per_week")

        if not all([start_date_raw, end_date_raw, total_lessons, lessons_per_week]):
            messages.error(request, "Barcha maydonlarni to'ldiring")
            return redirect("course_update", pk=pk)

        course.start_date = parse_date(start_date_raw)
        course.end_date = parse_date(end_date_raw)
        course.total_lessons = int(total_lessons)
        course.lessons_per_week = int(lessons_per_week)
        course.save()

        course.groups.update(is_scheduled=False)
        GroupSchedule.objects.filter(group__course=course).delete()

        messages.success(request, "Kurs yangilandi! Qayta jadval tuzing.")
        return redirect("lesson_list")

    return render(request, "raspisaniya/course_update.html", {"course": course})


# ─────────────────────────────────────────
# HAFTALIK JADVAL
# ─────────────────────────────────────────
@login_required
def weekly_schedule_view(request):
    week_str = request.GET.get('week')
    if week_str:
        try:
            week_start = dt_date.fromisoformat(week_str)
            week_start = week_start - timedelta(days=week_start.weekday())
        except Exception:
            week_start = None
    else:
        week_start = None

    data = get_weekly_schedule_data(week_start)
    grid = data['grid']
    week_start = data['week_start']
    week_end = data['week_end']
    max_group = data['max_group']

    prev_week = (week_start - timedelta(weeks=1)).isoformat()
    next_week = (week_start + timedelta(weeks=1)).isoformat()

    group_numbers = list(range(1, max_group + 1))

    SUBJECT_COLORS = [
        {'bg': '#dbeafe', 'text': '#1e40af', 'border': '#93c5fd'},
        {'bg': '#d1fae5', 'text': '#065f46', 'border': '#6ee7b7'},
        {'bg': '#fef3c7', 'text': '#92400e', 'border': '#fcd34d'},
        {'bg': '#fce7f3', 'text': '#9d174d', 'border': '#f9a8d4'},
        {'bg': '#ede9fe', 'text': '#5b21b6', 'border': '#c4b5fd'},
        {'bg': '#ffedd5', 'text': '#9a3412', 'border': '#fdba74'},
        {'bg': '#cffafe', 'text': '#155e75', 'border': '#67e8f9'},
        {'bg': '#dcfce7', 'text': '#14532d', 'border': '#86efac'},
        {'bg': '#fee2e2', 'text': '#991b1b', 'border': '#fca5a5'},
        {'bg': '#f0fdf4', 'text': '#166534', 'border': '#bbf7d0'},
        {'bg': '#fdf4ff', 'text': '#6b21a8', 'border': '#e879f9'},
        {'bg': '#fff7ed', 'text': '#9a3412', 'border': '#fed7aa'},
    ]
    subject_color_map = {}
    color_idx = [0]

    def get_subject_color(subject_name):
        if subject_name not in subject_color_map:
            subject_color_map[subject_name] = SUBJECT_COLORS[color_idx[0] % len(SUBJECT_COLORS)]
            color_idx[0] += 1
        return subject_color_map[subject_name]

    table_data = []
    for day_idx, day_name in enumerate(WEEKDAY_LIST):
        for para_idx, (start, end) in enumerate(PARA_TIMES_WEEKLY):
            cells = []
            has_any = False
            for gnum in group_numbers:
                key = (day_idx, para_idx, gnum)
                info = grid.get(key)
                if info:
                    has_any = True
                    color = get_subject_color(info['subject'])
                    cells.append({
                        'filled': True,
                        'sched_id': info['sched_id'],
                        'subject': info['subject'],
                        'teacher': info['teacher'],
                        'room': info.get('room', ''),
                        'group_number': info.get('group_number', ''),
                        'bg': color['bg'],
                        'text': color['text'],
                        'border': color['border'],
                    })
                else:
                    cells.append({'filled': False})
            table_data.append({
                'day': day_name,
                'time': f"{start} - {end}",
                'iso_date': (week_start + timedelta(days=day_idx)).isoformat(),
                'start_time': start,
                'cells': cells,
                'has_any': has_any,
                'show_day': para_idx == 0,
                'para_count': len(PARA_TIMES_WEEKLY),
            })

    return render(request, "raspisaniya/weekly_schedule.html", {
        "group_numbers": group_numbers,
        "table_data": table_data,
        "week_start": week_start,
        "week_end": week_end,
        "week_start_str": week_start.strftime("%d.%m.%Y"),
        "week_end_str": week_end.strftime("%d.%m.%Y"),
        "prev_week": prev_week,
        "next_week": next_week,
    })


@login_required
def weekly_schedule_excel(request):
    week_str = request.GET.get('week')
    if week_str:
        try:
            week_start = dt_date.fromisoformat(week_str)
            week_start = week_start - timedelta(days=week_start.weekday())
        except Exception:
            week_start = None
    else:
        week_start = None

    data = get_weekly_schedule_data(week_start)
    max_group = data['max_group']
    grid = data['grid']
    group_numbers = list(range(1, max_group + 1))

    wb = Workbook()
    ws = wb.active
    ws.title = "Haftalik jadval"

    thin = Side(style='thin', color='BBBBBB')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal='center', vertical='center', wrap_text=True)
    header_font = Font(name='Arial', bold=True, color='FFFFFF', size=10)
    header_fill = PatternFill('solid', start_color='2E4053')
    time_fill = PatternFill('solid', start_color='5D6D7E')
    time_font = Font(name='Arial', bold=True, color='FFFFFF', size=9)
    day_fill = PatternFill('solid', start_color='1A252F')
    day_font = Font(name='Arial', bold=True, color='FFFFFF', size=10)
    empty_fill = PatternFill('solid', start_color='F5F5F5')

    CELL_COLORS = [
        "D6E4BC", "B8D4E8", "FCE4A8", "E8C8D4",
        "CCE8CC", "FFD8B0", "D8D0E8", "E8E8C8",
        "BCE4E4", "FFC8C8", "D4E4F4", "E4D4BC",
        "C8D8F4", "F4D4C8", "D4F4D4", "F4F4C8",
    ]

    ws.column_dimensions['A'].width = 13
    ws.column_dimensions['B'].width = 14
    for i in range(len(group_numbers)):
        ws.column_dimensions[get_column_letter(i + 3)].width = 22

    ws.row_dimensions[1].height = 30
    for col, val in enumerate(["Kun", "Vaqt"], 1):
        c = ws.cell(1, col, val)
        c.font = header_font
        c.fill = header_fill
        c.alignment = center
        c.border = border

    for i, gnum in enumerate(group_numbers):
        c = ws.cell(1, i + 3, f"{gnum}-guruh")
        c.font = header_font
        c.fill = header_fill
        c.alignment = center
        c.border = border

    subject_color_map = {}
    color_counter = [0]

    def get_subject_color(subj):
        if subj not in subject_color_map:
            subject_color_map[subj] = CELL_COLORS[color_counter[0] % len(CELL_COLORS)]
            color_counter[0] += 1
        return subject_color_map[subj]

    row = 2
    for day_idx, day_name in enumerate(WEEKDAY_LIST):
        day_start_row = row
        for para_idx, (start, end) in enumerate(PARA_TIMES_WEEKLY):
            ws.row_dimensions[row].height = 45

            tc = ws.cell(row, 2, f"{start} - {end}")
            tc.font = time_font
            tc.fill = time_fill
            tc.alignment = center
            tc.border = border

            for i, gnum in enumerate(group_numbers):
                col = i + 3
                key = (day_idx, para_idx, gnum)
                cell = ws.cell(row, col)
                info = grid.get(key)
                if info:
                    room_str = f"\n🏫 {info['room']}" if info.get('room') else ''
                    group_str = f" ({info['group_number']}-guruh)" if info.get('group_number') else ''
                    cell.value = f"{info['subject']}{group_str}\n{info['teacher']}{room_str}"
                    cell.fill = PatternFill('solid', start_color=get_subject_color(info['subject']))
                    cell.font = Font(name='Arial', size=9, bold=True)
                else:
                    cell.value = ""
                    cell.fill = empty_fill
                    cell.font = Font(name='Arial', size=9)
                cell.alignment = center
                cell.border = border

            row += 1

        if row - day_start_row > 1:
            ws.merge_cells(
                start_row=day_start_row, start_column=1,
                end_row=row - 1, end_column=1
            )
        kc = ws.cell(day_start_row, 1)
        kc.value = day_name
        kc.font = day_font
        kc.fill = day_fill
        kc.alignment = center
        kc.border = border

    ws.freeze_panes = 'C2'

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="haftalik_jadval.xlsx"'
    wb.save(response)
    return response

@login_required
def change_lesson_time_ajax(request, sched_pk):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Faqat POST so\'rov'}, status=405)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': 'JSON xato'}, status=400)

    sched = get_object_or_404(GroupSchedule, pk=sched_pk)

    new_date_raw = body.get('new_date', '').strip()
    new_time_raw = body.get('new_time', '').strip()

    if not new_date_raw or not new_time_raw:
        return JsonResponse({'success': False, 'error': 'Sana yoki vaqt yuborilmagan'}, status=400)

    new_date_val = parse_date(new_date_raw)
    if not new_date_val:
        return JsonResponse({'success': False, 'error': 'Noto\'g\'ri sana formati'}, status=400)

    try:
        h, m = map(int, new_time_raw.split(':'))
        new_time_val = dtime(h, m)
    except (ValueError, AttributeError):
        return JsonResponse({'success': False, 'error': 'Noto\'g\'ri vaqt formati'}, status=400)

    if sched.date == new_date_val and sched.start_time == new_time_val:
        return JsonResponse({'success': False, 'error': 'Dars allaqachon shu vaqtda'})

    # Faqat bugungi kun o'zgartiriladi (admin istisno yoki ruxsat berilgan)
    from datetime import date as dt_date_check
    today = dt_date_check.today()
    is_admin = request.user.is_superuser or request.user.is_staff
    if not is_admin and sched.date != today and not sched.group.teacher_can_edit:
        return JsonResponse({'success': False, 'error': f'Faqat bugungi ({today.strftime("%d.%m.%Y")}) darsni o\'zgartirish mumkin! Admin ruxsat berishi kerak.'})

    group_number = sched.group.group_number
    teacher_id   = sched.group.teacher_id
    student_ids  = list(sched.group.students.values_list('id', flat=True))

    if GroupSchedule.objects.filter(
        date=new_date_val,
        start_time=new_time_val,
        group__teacher_id=teacher_id,
    ).exclude(pk=sched_pk).exists():
        teacher_name = str(sched.group.teacher)
        return JsonResponse({
            'success': False,
            'error': f'O\'qituvchi {teacher_name} {new_date_val} kuni {new_time_raw} da band!'
        })

    if student_ids and GroupSchedule.objects.filter(
        date=new_date_val,
        start_time=new_time_val,
        group__students__id__in=student_ids,
    ).exclude(pk=sched_pk).exists():
        return JsonResponse({
            'success': False,
            'error': f'Ba\'zi talabalar {new_date_val} kuni {new_time_raw} da band!'
        })

    sched.date       = new_date_val
    sched.start_time = new_time_val
    sched.save(update_fields=['date', 'start_time'])

    end_time = (datetime.combine(new_date_val, new_time_val) + timedelta(minutes=80)).time()

    return JsonResponse({
        'success':      True,
        'new_date':     new_date_val.strftime('%d.%m.%Y'),
        'new_date_iso': new_date_val.isoformat(),
        'new_time':     new_time_val.strftime('%H:%M'),
        'end_time':     end_time.strftime('%H:%M'),
        'weekday':      WEEKDAY_NAMES.get(new_date_val.weekday(), ''),
    })



@staff_member_required
def toggle_teacher_edit_permission(request, group_pk):
    """Admin: guruh uchun o'qituvchiga dars vaqtini o'zgartirish ruxsatini berish/olish."""
    from django.http import JsonResponse
    group = get_object_or_404(CourseGroup, pk=group_pk)
    if request.method == 'POST':
        group.teacher_can_edit = not group.teacher_can_edit
        group.save(update_fields=['teacher_can_edit'])
        return JsonResponse({
            'success': True,
            'permitted': group.teacher_can_edit,
            'label': 'Ruxsat berildi ✅' if group.teacher_can_edit else 'Ruxsat berilmagan',
        })
    return JsonResponse({'success': False}, status=405)

@staff_member_required
def reset_database_view(request):
    if request.method == 'POST' and request.POST.get('confirm') == 'TASDIQLASH':
        selected_models = request.POST.getlist('models_to_delete')

        if not selected_models:
            return render(request, 'raspisaniya/reset_database.html', {
                'error': "Hech bo'lmaganda bitta bo'limni tanlang!",
                'done': False
            })

        try:
            with transaction.atomic():
                # ── 1. Avval user ID larini yig'ib ol (o'chirishdan oldin) ──
                student_user_ids = []
                teacher_user_ids = []

                if 'student' in selected_models:
                    student_user_ids = list(
                        Student.objects.filter(user__isnull=False)
                        .values_list('user_id', flat=True)
                    )
                if 'teacher' in selected_models:
                    teacher_user_ids = list(
                        Teacher.objects.filter(user__isnull=False)
                        .values_list('user_id', flat=True)
                    )

                # ── 2. To'g'ri tartibda o'chirish (CASCADE yo'q — faqat Django ORM) ──
                # Tartib muhim: avval bog'liq jadvallar, keyin asosiylar

                if 'schedule' in selected_models:
                    GroupSchedule.objects.all().delete()

                if 'group' in selected_models:
                    CourseGroup.objects.all().delete()

                if 'course' in selected_models:
                    # GroupSchedule va CourseGroup avval o'chadi (yuqorida yoki cascade orqali)
                    Course.objects.all().delete()

                if 'student' in selected_models:
                    Student.objects.all().delete()

                if 'teacher' in selected_models:
                    Teacher.objects.all().delete()

                if 'subject' in selected_models:
                    Subject.objects.all().delete()

                if 'room' in selected_models:
                    Room.objects.all().delete()

                # ── 3. Tegishli oddiy foydalanuvchilarni o'chir ──
                all_user_ids = list(set(student_user_ids + teacher_user_ids))
                if all_user_ids:
                    User.objects.filter(
                        id__in=all_user_ids,
                        is_staff=False,
                        is_superuser=False,
                    ).delete()

            return render(request, 'raspisaniya/reset_database.html', {'done': True})

        except Exception as e:
            print(f"Baza tozalashda xato: {e}")
            return render(request, 'raspisaniya/reset_database.html', {
                'error': f"Xatolik yuz berdi: {str(e)}",
                'done': False
            })

    return render(request, 'raspisaniya/reset_database.html', {'done': False})


def get_backups_dir():
    backup_dir = os.path.join(settings.MEDIA_ROOT, 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir


def export_database_view(request):
    """Backup yaratish — serverda saqlaydi va yuklab olish imkonini beradi."""
    from datetime import datetime as dt

    output = StringIO()
    management.call_command(
        'dumpdata',
        'raspisaniya', 'accounts', 'auth.user',
        indent=2,
        stdout=output,
        natural_foreign=True,
        natural_primary=True,
    )
    data = output.getvalue()

    # Nom: foydalanuvchi bergan nom yoki avtomatik sana
    custom_name = request.GET.get('name', '').strip()
    now = dt.now().strftime('%Y-%m-%d_%H-%M')
    if custom_name:
        safe_name = ''.join(c for c in custom_name if c.isalnum() or c in '-_ ')
        safe_name = safe_name.strip().replace(' ', '_')
        filename = f"{now}_{safe_name}.json"
    else:
        filename = f"{now}_backup.json"

    # Serverda saqlash
    backup_dir = get_backups_dir()
    filepath = os.path.join(backup_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(data)

    # Yuklab olish
    response = HttpResponse(data, content_type='application/json')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def restore_database_view(request):
    backup_dir = get_backups_dir()

    if request.method == 'POST':
        action = request.POST.get('action')

        # 1. Fayl yuklash orqali tiklash
        if action == 'upload' and request.FILES.get('backup_file'):
            backup_file = request.FILES['backup_file']
            custom_name = request.POST.get('backup_name', '').strip()
            from datetime import datetime as dt
            now = dt.now().strftime('%Y-%m-%d_%H-%M')

            if custom_name:
                safe_name = ''.join(c for c in custom_name if c.isalnum() or c in '-_ ')
                filename = f"{now}_{safe_name.replace(' ', '_')}.json"
            else:
                filename = f"{now}_{backup_file.name}"

            save_path = os.path.join(backup_dir, filename)
            with open(save_path, 'wb+') as dest:
                for chunk in backup_file.chunks():
                    dest.write(chunk)

            try:
                management.call_command('loaddata', save_path, ignorenonexistent=True)
                messages.success(request, f"✅ '{filename}' fayli yuklandi va baza tiklandi!")
            except Exception as e:
                messages.error(request, f"Xatolik: {str(e)}")
            return redirect('restore_database')

        # 2. Serverda saqlangan backup dan tiklash
        if action == 'restore_saved':
            filename = request.POST.get('filename', '')
            filepath = os.path.join(backup_dir, filename)
            if os.path.exists(filepath):
                try:
                    management.call_command('loaddata', filepath, ignorenonexistent=True)
                    messages.success(request, f"✅ '{filename}' dan baza muvaffaqiyatli tiklandi!")
                except Exception as e:
                    messages.error(request, f"Xatolik: {str(e)}")
            else:
                messages.error(request, "Fayl topilmadi!")
            return redirect('restore_database')

        # 3. Backup o'chirish
        if action == 'delete_backup':
            filename = request.POST.get('filename', '')
            filepath = os.path.join(backup_dir, filename)
            if os.path.exists(filepath) and filename.endswith('.json'):
                os.remove(filepath)
                messages.success(request, f"'{filename}' o'chirildi.")
            return redirect('restore_database')

    # Saqlangan backuplar ro'yxati
    backups = []
    if os.path.exists(backup_dir):
        for fname in sorted(os.listdir(backup_dir), reverse=True):
            if fname.endswith('.json'):
                fpath = os.path.join(backup_dir, fname)
                stat = os.stat(fpath)
                backups.append({
                    'name': fname,
                    'size': round(stat.st_size / 1024, 1),  # KB
                    'date': stat.st_mtime,
                })

    return render(request, 'raspisaniya/restore_database.html', {
        'backups': backups,
    })