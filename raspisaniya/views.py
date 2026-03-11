from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.utils.dateparse import parse_date
from openpyxl import load_workbook, Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from django.http import HttpResponse
from datetime import timedelta, datetime, time as dtime
from .models import Student, Subject, Teacher, Group, Course, CourseGroup, GroupSchedule, LANGUAGE_CHOICES
from .forms import TeacherForm, StudentForm, SubjectForm, StudentImportForm, TeacherImportForm
from collections import defaultdict
import re

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
    ("08:30", "09:50"),
    ("10:00", "11:20"),
    ("12:00", "13:20"),
    ("13:30", "14:50"),
    ("15:00", "16:20"),
    ("16:30", "17:50"),
]

WEEKDAY_LIST = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba"]

GROUP_COLORS = [
    "D6E4BC", "B8D4E8", "FCE4A8", "E8C8D4",
    "CCE8CC", "FFD8B0", "D8D0E8", "E8E8C8",
    "BCE4E4", "FFC8C8", "D4E4F4", "E4D4BC",
    "C8D8F4", "F4D4C8", "D4F4D4", "F4F4C8",
]

# ─────────────────────────────────────────
# YORDAMCHI FUNKSIYALAR (login_required YO'Q)
# ─────────────────────────────────────────
def is_admin(user):
    return user.is_superuser

def is_teacher(user):
    return hasattr(user, 'teacher')

def is_student(user):
    return hasattr(user, 'student')

def split_into_groups(students, max_size=15, min_size=8):
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

def find_schedule_for_group(start_date, end_date, total_lessons, lessons_per_week, teacher, students, group_number=1):
    """
    1-haftada qaysi kunlar va paralar belgilansa — keyingi haftalar ham xuddi shunday.
    Dars soatlari tugagach to'xtaydi.
    """
    student_ids = [s.id for s in students]
    teacher_id = teacher.id

    def get_busy_para_indices(date):
        busy = set()
        # O'qituvchi band paralar
        for sched in GroupSchedule.objects.filter(
            date=date,
            group__teacher_id=teacher_id,
        ).select_related('group'):
            st = sched.start_time or sched.group.start_time
            if st:
                for i, (ps, pe) in enumerate(PARA_TIMES):
                    if ps == st:
                        busy.add(i)
            else:
                for i in range(len(PARA_TIMES)):
                    busy.add(i)

        # Talabalar band paralar
        if student_ids:
            for sched in GroupSchedule.objects.filter(
                date=date,
                group__students__id__in=student_ids,
            ).select_related('group').distinct():
                st = sched.start_time or sched.group.start_time
                if st:
                    for i, (ps, pe) in enumerate(PARA_TIMES):
                        if ps == st:
                            busy.add(i)

        # Joriy guruh raqami bilan bir xil kun+parada boshqa fan bo'lmasin
        for sched in GroupSchedule.objects.filter(
            date=date,
            group__group_number=group_number,
        ).select_related('group'):
            st = sched.start_time or sched.group.start_time
            if st:
                for i, (ps, pe) in enumerate(PARA_TIMES):
                    if ps == st:
                        busy.add(i)

        return busy

    def find_free_para(date, exclude_paras=None):
        busy = get_busy_para_indices(date)
        if exclude_paras:
            busy = busy | set(exclude_paras)
        for i in range(len(PARA_TIMES)):
            if i not in busy:
                return i
        return None

    # ── 1-HAFTA: qaysi weekday va para tanlash ──
    # start_date dan boshlab dushanba topamiz
    first_monday = start_date - timedelta(days=start_date.weekday())
    if first_monday < start_date:
        first_monday = start_date

    import random
    WEEKDAYS = list(range(6))
    random.shuffle(WEEKDAYS)
    chosen_slots = []  # [(weekday, para_idx), ...]

    # 1-haftadagi kunlarni topish
    first_week_dates = {}
    for wd in WEEKDAYS:
        d = first_monday + timedelta(days=wd)
        if d >= start_date:
            first_week_dates[wd] = d

    for wd in WEEKDAYS:
        if len(chosen_slots) >= lessons_per_week:
            break
        if wd not in first_week_dates:
            continue
        d = first_week_dates[wd]
        # Bu kunda allaqachon tanlangan paralarni ham busy qilish
        already_used = [p for (w, p) in chosen_slots if w == wd]
        para_idx = find_free_para(d, exclude_paras=already_used)
        if para_idx is not None:
            chosen_slots.append((wd, para_idx))

    if not chosen_slots:
        return None

    # Agar yetarli slot topilmagan bo'lsa — keyingi haftalardan qo'shimcha kun qidirish
    if len(chosen_slots) < lessons_per_week:
        second_monday = first_monday + timedelta(weeks=1)
        second_week_dates = {}
        for wd in WEEKDAYS:
            d = second_monday + timedelta(days=wd)
            if d <= end_date:
                second_week_dates[wd] = d

        already_used_wds = {w for w, p in chosen_slots}
        for wd in WEEKDAYS:
            if len(chosen_slots) >= lessons_per_week:
                break
            if wd in already_used_wds or wd not in second_week_dates:
                continue
            d = second_week_dates[wd]
            already_used = [p for (w, p) in chosen_slots if w == wd]
            para_idx = find_free_para(d, exclude_paras=already_used)
            if para_idx is not None:
                chosen_slots.append((wd, para_idx))

    if not chosen_slots:
        return None

    # ── BARCHA HAFTALAR: chosen_slots bo'yicha sanalarni yaratish ──
    result = []
    cur_monday = first_monday

    while len(result) < total_lessons:
        cur_monday_end = cur_monday + timedelta(days=5)
        if cur_monday > end_date:
            break

        for wd, para_idx in chosen_slots:
            if len(result) >= total_lessons:
                break
            d = cur_monday + timedelta(days=wd)
            if d < start_date or d > end_date:
                continue
            p_start, p_end = PARA_TIMES[para_idx]
            result.append((d, p_start, p_end))

        cur_monday += timedelta(weeks=1)

    return result if len(result) >= total_lessons else None


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
    from datetime import date as dt_date
    today = dt_date.today()
    if week_start is None:
        week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=5)

    groups = CourseGroup.objects.filter(
        is_scheduled=True
    ).select_related('course__subject', 'teacher').prefetch_related('schedule')

    grid = {}
    max_group = 0

    for grp in groups:
        gnum = grp.group_number
        if gnum > max_group:
            max_group = gnum

        subject_name = str(grp.course.subject)
        teacher_name = str(grp.teacher)

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
            # Agar bu kun+para+guruh band bo'lsa — guruh raqamini oshirib yangi slot top
            slot_gnum = gnum
            while (weekday, para_idx, slot_gnum) in grid:
                slot_gnum += 1
            key = (weekday, para_idx, slot_gnum)
            if slot_gnum > max_group:
                max_group = slot_gnum
            grid[key] = {'subject': subject_name, 'teacher': teacher_name}

    return {
        'max_group': max_group,
        'grid': grid,
        'columns': [],
        'column_pks': [],
        'week_start': week_start,
        'week_end': week_end,
    }


    results = []
    current = ""
    depth = 0
    for char in raw:
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


# ─────────────────────────────────────────
# LESSON LIST
# ─────────────────────────────────────────
@login_required
def lesson_list(request):
    if is_student(request.user):
        return redirect('student_dashboard')
    if is_teacher(request.user) and not is_admin(request.user):
        return redirect('teacher_dashboard')

    courses = Course.objects.select_related('subject').prefetch_related('groups').all()
    courses_data = []
    for course in courses:
        total = course.groups.count()
        scheduled = course.groups.filter(is_scheduled=True).count()
        courses_data.append({
            'course': course,
            'total_groups': total,
            'scheduled_groups': scheduled,
        })
    return render(request, "raspisaniya/lesson_list.html", {"courses_data": courses_data})


# ─────────────────────────────────────────
# LESSON CREATE — 3 BOSQICH
# ─────────────────────────────────────────
@login_required
def lesson_create(request):

    # ── STEP 1 ──
    if request.method == "GET":
        subjects = Subject.objects.all()
        return render(request, "raspisaniya/lesson_create.html", {
            "step": 1,
            "subjects": subjects,
        })

    # ── STEP 2 ──
    if request.method == "POST" and request.POST.get("step") == "2":
        subject_id = request.POST.get("subject")
        subject = get_object_or_404(Subject, id=subject_id)

        start_date_raw = request.POST.get("start_date")
        total_lessons = request.POST.get("total_lessons")
        lessons_per_week = request.POST.get("lessons_per_week")

        if not all([start_date_raw, total_lessons, lessons_per_week]):
            messages.error(request, "Barcha maydonlarni to'ldiring")
            return redirect("lesson_create")

        total_lessons = int(total_lessons)
        lessons_per_week = int(lessons_per_week)
        start_date = parse_date(start_date_raw)

        # Tugash sanasini avtomatik hisoblash
        # total_lessons / lessons_per_week = haftalar soni
        import math
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
            valid_groups = [g for g in groups if len(g) >= 8]
            invalid_groups = [g for g in groups if len(g) < 8]

            if invalid_groups:
                lang_name = dict(LANGUAGE_CHOICES).get(lang, lang)
                skipped_langs.append(
                    f"{lang_name} tili: {sum(len(g) for g in invalid_groups)} ta o'quvchi "
                    f"(8 tadan kam, guruh shakillantirilmadi)"
                )

            for g in valid_groups:
                all_groups.append({
                    'lang': lang,
                    'lang_name': dict(LANGUAGE_CHOICES).get(lang, lang),
                    'students': g,
                    'is_small': False,
                })
            # 8 dan kam bo'lsa ham ko'rsatish — qizil
            for g in invalid_groups:
                all_groups.append({
                    'lang': lang,
                    'lang_name': dict(LANGUAGE_CHOICES).get(lang, lang),
                    'students': g,
                    'is_small': True,
                })

        # Faqat to'liq guruhlarni saqlash — kichik guruhlar unassigned ga tushadi
        all_groups = [g for g in all_groups if not g['is_small']]

        if not all_groups:
            messages.error(request, "Hech bir tilda yetarli o'quvchi yo'q (kamida 8 ta kerak)")
            return redirect("lesson_create")

        teachers = Teacher.objects.filter(subjects=subject)

        assigned_ids = set()
        for g in all_groups:
            if not g['is_small']:
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
                if len(g) >= 8:
                    all_groups_data.append({'lang': lang, 'students': g})

        group_teachers = []  # endi ishlatilmaydi — teacher har guruh uchun alohida olinadi

        with transaction.atomic():
            course = Course.objects.create(
                subject=subject,
                start_date=start_date,
                end_date=end_date,
                total_lessons=total_lessons,
                lessons_per_week=lessons_per_week,
                lesson_duration=80,
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

                # Guruh tilini birinchi talabadan olish
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
                "weekday": WEEKDAY_NAMES.get(s.date.weekday(), ""),
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
        from datetime import time as dtime
        from django.utils.dateparse import parse_date as pd

        new_date_val = pd(new_date) if new_date else sched.date
        if new_time:
            h, m = map(int, new_time.split(":"))
            new_time_val = dtime(h, m)
        else:
            new_time_val = sched.start_time

        group_number = sched.group.group_number
        teacher_id = sched.group.teacher_id
        student_ids = list(sched.group.students.values_list('id', flat=True))

        # Guruh raqami conflict
        conflict = GroupSchedule.objects.filter(
            date=new_date_val, start_time=new_time_val,
            group__group_number=group_number,
        ).exclude(pk=sched_pk).select_related('group__course__subject').first()
        if conflict:
            messages.error(request,
                f"{new_date_val} kuni {new_time} parada {group_number}-guruhda "
                f"'{conflict.group.course.subject}' darsi bor!")
            return redirect("lesson_schedule", pk=sched.group.course.pk)

        # O'qituvchi conflict
        conflict = GroupSchedule.objects.filter(
            date=new_date_val, start_time=new_time_val,
            group__teacher_id=teacher_id,
        ).exclude(pk=sched_pk).select_related('group__course__subject').first()
        if conflict:
            messages.error(request,
                f"O'qituvchi {new_date_val} kuni {new_time} parada "
                f"'{conflict.group.course.subject}' darsida band!")
            return redirect("lesson_schedule", pk=sched.group.course.pk)

        # Talabalar conflict
        if student_ids:
            conflict = GroupSchedule.objects.filter(
                date=new_date_val, start_time=new_time_val,
                group__students__id__in=student_ids,
            ).exclude(pk=sched_pk).select_related('group__course__subject').first()
            if conflict:
                messages.error(request,
                    f"Ba'zi talabalar {new_date_val} kuni {new_time} parada "
                    f"'{conflict.group.course.subject}' darsida band!")
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


@login_required
def lesson_delete(request, pk):
    lesson = get_object_or_404(Course, pk=pk)
    if request.method == "POST":
        lesson.delete()
        messages.success(request, "Dars o'chirildi")
        return redirect("lesson_list")
    return render(request, "raspisaniya/lesson_delete.html", {"lesson": lesson})


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
    teachers = Teacher.objects.all().order_by('last_name')
    return render(request, 'raspisaniya/teacher_list.html', {'teachers': teachers})


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

            messages.success(request, f"O'qituvchi qo'shildi. ID: {teacher_id}, Parol: {password if password else teacher_id}")
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
        form = TeacherForm(request.POST, instance=teacher)
        if form.is_valid():
            form.save()
            messages.success(request, "O'qituvchi yangilandi")
            return redirect('teacher_list')
    else:
        form = TeacherForm(instance=teacher)
    return render(request, 'raspisaniya/teacher_create.html', {
        'form': form,
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
                with transaction.atomic():
                    for row in ws.iter_rows(min_row=2, values_only=True):
                        if not row or not row[0]:
                            continue
                        parts = str(row[0]).strip().split()
                        if len(parts) < 2:
                            continue
                        teacher, _ = Teacher.objects.get_or_create(
                            first_name=parts[0],
                            last_name=" ".join(parts[1:])
                        )
                        if len(row) > 1 and row[1]:
                            for sname in str(row[1]).split(","):
                                sname = sname.strip()
                                if sname:
                                    subj, _ = Subject.objects.get_or_create(name=sname)
                                    teacher.subjects.add(subj)

                        # User avtomatik yaratish
                        if not teacher.user:
                            tid = teacher.teacher_id or f"T-{teacher.pk}"
                            teacher.teacher_id = tid
                            if not User.objects.filter(username=tid).exists():
                                user = User.objects.create_user(
                                    username=tid,
                                    password=tid,
                                )
                                teacher.user = user
                                teacher.save()
                messages.success(request, "O'qituvchilar import qilindi ✅")
                return redirect("teacher_list")
            except Exception as e:
                messages.error(request, f"Xatolik: {e}")
    else:
        form = TeacherImportForm()
    return render(request, "raspisaniya/teacher_import.html", {"form": form})


# ─────────────────────────────────────────
# STUDENT
# ─────────────────────────────────────────
@login_required
def student_list(request):
    students = Student.objects.prefetch_related('debts').order_by('last_name')
    students_data = []
    for student in students:
        completed = list(Subject.objects.filter(course__groups__students=student).distinct())
        students_data.append({'student': student, 'completed': completed})
    return render(request, 'raspisaniya/student_list.html', {'students_data': students_data})


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

            messages.success(request, f"O'quvchi qo'shildi. ID: {student_id}, Parol: {password if password else student_id}")
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
        form = StudentForm(request.POST, instance=student)
        if form.is_valid():
            form.save()
            messages.success(request, "O'quvchi yangilandi")
            return redirect('student_list')
    else:
        form = StudentForm(instance=student)
    return render(request, 'raspisaniya/student_create.html', {
        'form': form,
        'subjects': Subject.objects.all(),
        'groups': Group.objects.all(),
        'selected_debts': list(student.debts.values_list('id', flat=True)),
    })


@login_required
def student_delete(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        student.delete()
        messages.success(request, "O'quvchi o'chirildi")
        return redirect('student_list')
    return render(request, 'raspisaniya/student_delete.html', {'student': student})


@login_required
def import_students(request):
    if request.method == "POST":
        form = StudentImportForm(request.POST, request.FILES)
        if form.is_valid():
            file = request.FILES["file"]
            try:
                wb = load_workbook(file)
                ws = wb.active
                with transaction.atomic():
                    for row in ws.iter_rows(min_row=2, values_only=True):
                        if not row or not row[1]:
                            continue
                        full_name = str(row[1]).strip().split()
                        if len(full_name) < 2:
                            continue
                        first_name = full_name[0]
                        last_name = " ".join(full_name[1:])

                        group = None
                        if len(row) > 4 and row[4]:
                            group, _ = Group.objects.get_or_create(name=str(row[4]).strip())

                        language = 'uz'
                        if len(row) > 5 and row[5]:
                            lang_raw = str(row[5]).strip().lower()
                            if 'рус' in lang_raw or 'rus' in lang_raw:
                                language = 'ru'
                            elif 'қар' in lang_raw or 'qor' in lang_raw or 'кар' in lang_raw:
                                language = 'qq'
                            elif 'инг' in lang_raw or 'eng' in lang_raw:
                                language = 'en'

                        student, created = Student.objects.get_or_create(
                            first_name=first_name,
                            last_name=last_name,
                            defaults={"group": group, "language": language}
                        )
                        if not created:
                            student.group = group
                            student.language = language
                            student.save()

                        if len(row) > 8 and row[8]:
                            subjects_raw = split_subjects(str(row[8]))
                            for subj_name in subjects_raw:
                                if subj_name:
                                    subj, _ = Subject.objects.get_or_create(name=subj_name)
                                    student.debts.add(subj)

                        # User avtomatik yaratish
                        if not student.user:
                            sid = student.student_id or f"S-{student.pk}"
                            student.student_id = sid
                            if not User.objects.filter(username=sid).exists():
                                user = User.objects.create_user(
                                    username=sid,
                                    password=sid,
                                )
                                student.user = user
                                student.save()

                messages.success(request, "O'quvchilar import qilindi ✅")
                return redirect("student_list")
            except Exception as e:
                messages.error(request, f"Xatolik: {e}")
    else:
        form = StudentImportForm()
    return render(request, "raspisaniya/import_students.html", {"form": form})


# ─────────────────────────────────────────
# SUBJECT
# ─────────────────────────────────────────
@login_required
def subject_list(request):
    subjects = Subject.objects.all().order_by('name')
    return render(request, 'raspisaniya/subject_list.html', {'subjects': subjects})


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

    unscheduled_list = list(
        unscheduled_groups.prefetch_related('students').select_related('course', 'teacher')
        .order_by('group_number', 'pk')
    )

    for grp in unscheduled_list:
        course = grp.course
        students = list(grp.students.all())

        schedule = find_schedule_for_group(
            course.start_date, course.end_date,
            course.total_lessons, course.lessons_per_week,
            grp.teacher, students,
            group_number=grp.group_number,
        )

        if schedule is None:
            errors.append({'group': grp, 'course': course})
        else:
            from collections import Counter
            para_counter = Counter(p_start for _, p_start, _ in schedule)
            most_common_para = para_counter.most_common(1)[0][0]
            grp.start_time = most_common_para
            grp.weekdays = list({d.weekday() for d, _, _ in schedule})
            grp.is_scheduled = True

            # Bitta transaction ichida saqlash
            import time
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
            error_details.append({
                'group': grp, 'course': course, 'other_groups': other_groups,
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
    from datetime import date as dt_date
    # Hafta boshini GET parametridan olish
    week_str = request.GET.get('week')
    if week_str:
        try:
            week_start = dt_date.fromisoformat(week_str)
            # Dushanbaga moslashtirish
            week_start = week_start - timedelta(days=week_start.weekday())
        except:
            week_start = None
    else:
        week_start = None

    data = get_weekly_schedule_data(week_start)
    columns = data['columns']
    column_pks = data['column_pks']
    grid = data['grid']
    week_start = data['week_start']
    week_end = data['week_end']
    max_group = data['max_group']

    prev_week = (week_start - timedelta(weeks=1)).isoformat()
    next_week = (week_start + timedelta(weeks=1)).isoformat()

    group_numbers = list(range(1, max_group + 1))

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
                    cells.append({'filled': True, 'subject': info['subject'], 'teacher': info['teacher']})
                else:
                    cells.append({'filled': False})
            table_data.append({
                'day': day_name,
                'time': f"{start} - {end}",
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
    from datetime import date as dt_date
    week_str = request.GET.get('week')
    if week_str:
        try:
            week_start = dt_date.fromisoformat(week_str)
            week_start = week_start - timedelta(days=week_start.weekday())
        except:
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
                    cell.value = f"{info['subject']}\n{info['teacher']}"
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