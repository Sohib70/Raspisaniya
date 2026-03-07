from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.utils.dateparse import parse_date
from openpyxl import load_workbook, Workbook
from django.http import HttpResponse
from datetime import timedelta, datetime, time as dtime
from .models import Student, Subject, Teacher, Group, Course, CourseGroup, GroupSchedule, LANGUAGE_CHOICES
from .forms import TeacherForm, StudentForm, SubjectForm, StudentImportForm, TeacherImportForm
from collections import defaultdict


WEEKDAYS = {0: 'Dushanba', 1: 'Seshanba', 2: 'Chorshanba',
            3: 'Payshanba', 4: 'Juma', 5: 'Shanba', 6: 'Yakshanba'}


def get_lesson_dates(start_date, total=15):
    weekday = start_date.weekday()
    if weekday == 0:    days = [0, 2, 4]
    elif weekday == 1:  days = [1, 3, 5]
    elif weekday == 2:  days = [2, 4, 0]
    elif weekday == 3:  days = [3, 5, 1]
    elif weekday == 4:  days = [4, 0, 2]
    elif weekday == 5:  days = [5, 1, 3]
    else:               days = [0, 2, 4]
    result = []
    cur = start_date
    while len(result) < total:
        if cur.weekday() in days:
            result.append(cur)
        cur += timedelta(days=1)
    return result


def split_into_groups(students, max_size=15, min_size=8):
    """
    15 ta -> [15]
    16 ta -> [8, 8]
    20 ta -> [10, 10]
    23 ta -> [12, 11]
    30 ta -> [15, 15]
    """
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


def check_conflicts(lesson_dates, start_time, teacher, students, exclude_lesson_pk=None):
    duration = timedelta(minutes=80)
    errors = {'teacher': [], 'students': {}}

    schedules = LessonSchedule.objects.filter(
        date__in=lesson_dates
    ).select_related('lesson', 'lesson__subject')

    if exclude_lesson_pk:
        schedules = schedules.exclude(lesson__pk=exclude_lesson_pk)

    teacher_conflict_added = set()
    student_conflict_added = set()

    for sched in schedules:
        ex_start = datetime.combine(sched.date, sched.lesson.start_time)
        ex_end = ex_start + duration
        new_start = datetime.combine(sched.date, start_time)
        new_end = new_start + duration

        overlap = new_start < ex_end and new_end > ex_start
        if not overlap:
            continue

        lesson_id = sched.lesson.id

        # O'qituvchi — faqat bir marta
        if lesson_id not in teacher_conflict_added:
            if sched.lesson.groups.filter(teacher=teacher).exists():
                teacher_conflict_added.add(lesson_id)
                errors['teacher'].append(
                    f"'{sched.lesson.subject}' darsi "
                    f"{sched.lesson.start_time.strftime('%H:%M')} da band"
                )

        # O'quvchi — faqat bir marta
        for st in students:
            key = (st.id, lesson_id)
            if key not in student_conflict_added:
                if sched.lesson.groups.filter(students=st).exists():
                    student_conflict_added.add(key)
                    if st not in errors['students']:
                        errors['students'][st] = []
                    errors['students'][st].append(
                        f"'{sched.lesson.subject}' darsi "
                        f"{sched.lesson.start_time.strftime('%H:%M')} da band"
                    )

    return errors


# ─────────────────────────────────────────
# LESSON LIST
# ─────────────────────────────────────────
def lesson_list(request):
    lessons = Lesson.objects.select_related('subject').prefetch_related(
        'groups__teacher', 'groups__students'
    ).all()
    return render(request, "raspisaniya/lesson_list.html", {"lessons": lessons})

# ─────────────────────────────────────────
# LESSON CREATE — 3 BOSQICH
# ─────────────────────────────────────────
def get_lesson_dates(start_date, weekdays, total):
    """
    weekdays — [0,2,4] kabi list
    total — jami necha dars
    """
    result = []
    cur = start_date
    while len(result) < total:
        if cur.weekday() in weekdays:
            result.append(cur)
        cur += timedelta(days=1)
    return result


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


def check_conflicts_new(dates, start_time, teacher, students, exclude_group_pk=None):
    from .models import CourseGroup, GroupSchedule
    duration = timedelta(minutes=80)
    errors = {'teacher': [], 'students': {}}

    schedules = GroupSchedule.objects.filter(
        date__in=dates
    ).select_related('group', 'group__course', 'group__course__subject', 'group__teacher')

    if exclude_group_pk:
        schedules = schedules.exclude(group__pk=exclude_group_pk)

    teacher_conflict_added = set()
    student_conflict_added = set()

    for sched in schedules:
        ex_start = datetime.combine(sched.date, sched.group.start_time)
        ex_end = ex_start + duration
        new_start = datetime.combine(sched.date, start_time)
        new_end = new_start + duration

        overlap = new_start < ex_end and new_end > ex_start
        if not overlap:
            continue

        group_id = sched.group.id

        if group_id not in teacher_conflict_added:
            if sched.group.teacher == teacher:
                teacher_conflict_added.add(group_id)
                errors['teacher'].append(
                    f"'{sched.group.course.subject}' darsi "
                    f"{sched.group.start_time.strftime('%H:%M')} da band"
                )

        for st in students:
            key = (st.id, group_id)
            if key not in student_conflict_added:
                if sched.group.students.filter(id=st.id).exists():
                    student_conflict_added.add(key)
                    if st not in errors['students']:
                        errors['students'][st] = []
                    errors['students'][st].append(
                        f"'{sched.group.course.subject}' darsi "
                        f"{sched.group.start_time.strftime('%H:%M')} da band"
                    )

    return errors


WEEKDAY_NAMES = {
    0: 'Dushanba', 1: 'Seshanba', 2: 'Chorshanba',
    3: 'Payshanba', 4: 'Juma', 5: 'Shanba'
}

WEEKDAY_OPTIONS = [
    (0, 'Dushanba'), (1, 'Seshanba'), (2, 'Chorshanba'),
    (3, 'Payshanba'), (4, 'Juma'), (5, 'Shanba'),
]


def lesson_list(request):
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


PARA_TIMES = [
    (dtime(8, 30),  dtime(9, 50)),
    (dtime(10, 0),  dtime(11, 20)),
    (dtime(12, 0),  dtime(13, 20)),
    (dtime(13, 30), dtime(14, 50)),
    (dtime(15, 0),  dtime(16, 20)),
    (dtime(16, 30), dtime(17, 50)),
]

def find_schedule_for_group(start_date, end_date, total_lessons, lessons_per_week, teacher, students):
    """
    Guruh uchun conflict bo'lmagan sana+para topadi.
    Qaytaradi: [(date, para_start, para_end), ...] yoki None
    """
    result = []
    cur = start_date

    while len(result) < total_lessons:
        if cur > end_date:
            return None  # sana oralig'ida yetarli kun topilmadi

        if cur.weekday() > 5:  # Yakshanba
            cur += timedelta(days=1)
            continue

        # Bu haftada nechta dars qo'yilgan
        week_start = cur - timedelta(days=cur.weekday())
        week_end = week_start + timedelta(days=6)
        week_count = sum(1 for d, _, _ in result if week_start <= d <= week_end)

        if week_count >= lessons_per_week:
            cur += timedelta(days=1)
            continue

        # Bu kunda bo'sh para topish
        para_found = False
        for para_start, para_end in PARA_TIMES:
            new_start = datetime.combine(cur, para_start)
            new_end = datetime.combine(cur, para_end)

            # O'qituvchi band emasmi?
            teacher_busy = False
            teacher_scheds = GroupSchedule.objects.filter(
                date=cur,
                group__teacher=teacher,
            ).select_related('group')

            for sched in teacher_scheds:
                if sched.group.start_time:
                    ex_start = datetime.combine(cur, sched.group.start_time)
                    ex_end = ex_start + timedelta(minutes=80)
                    if new_start < ex_end and new_end > ex_start:
                        teacher_busy = True
                        break

            if teacher_busy:
                continue

            # Talabalar band emasmi?
            student_busy = False
            student_ids = [s.id for s in students]
            student_scheds = GroupSchedule.objects.filter(
                date=cur,
                group__students__id__in=student_ids,
            ).select_related('group').distinct()

            for sched in student_scheds:
                if sched.group.start_time:
                    ex_start = datetime.combine(cur, sched.group.start_time)
                    ex_end = ex_start + timedelta(minutes=80)
                    if new_start < ex_end and new_end > ex_start:
                        student_busy = True
                        break

            if not student_busy:
                result.append((cur, para_start, para_end))
                para_found = True
                break

        cur += timedelta(days=1)

    return result if len(result) == total_lessons else None


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
        end_date_raw = request.POST.get("end_date")
        total_lessons = request.POST.get("total_lessons")
        lessons_per_week = request.POST.get("lessons_per_week")

        if not all([start_date_raw, end_date_raw, total_lessons, lessons_per_week]):
            messages.error(request, "Barcha maydonlarni to'ldiring")
            return redirect("lesson_create")

        total_lessons = int(total_lessons)
        lessons_per_week = int(lessons_per_week)
        start_date = parse_date(start_date_raw)
        end_date = parse_date(end_date_raw)

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
                })

        if not all_groups:
            messages.error(request, "Hech bir tilda yetarli o'quvchi yo'q (kamida 8 ta kerak)")
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

        group_teachers = []
        for i in range(groups_count):
            tid = request.POST.get(f"teacher_{i}")
            if not tid:
                messages.error(request, f"{i+1}-guruh uchun o'qituvchi tanlanmagan")
                return redirect("lesson_create")
            group_teachers.append(get_object_or_404(Teacher, id=tid))

        # Saqlash — jadval keyinroq tuziladi
        with transaction.atomic():
            course = Course.objects.create(
                subject=subject,
                start_date=start_date,
                end_date=end_date,
                total_lessons=total_lessons,
                lessons_per_week=lessons_per_week,
                lesson_duration=80,
            )

            for i, (gdata, teacher) in enumerate(zip(all_groups_data, group_teachers)):
                selected_ids = request.POST.getlist(f"students_{i}")
                g_students = gdata['students']
                selected_students = [s for s in g_students if str(s.id) in selected_ids] \
                                    if selected_ids else g_students

                if not selected_students:
                    continue

                cgroup = CourseGroup.objects.create(
                    course=course,
                    teacher=teacher,
                    group_number=i + 1,
                    start_time=None,
                    weekdays=[],
                    language=gdata['lang'],
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
def lesson_schedule(request, pk):
    course = get_object_or_404(Course, pk=pk)
    groups = course.groups.prefetch_related('students', 'schedule').select_related('teacher')
    duration = timedelta(minutes=80)

    # Barcha guruhlardagi talabalar ID lari
    all_group_student_ids = set()
    for grp in groups:
        for s in grp.students.all():
            all_group_student_ids.add(s.id)

    # Shu fandan qolgan, hech qaysi guruhga qo'shilmagan talabalar
    addable_students = Student.objects.filter(
        debts=course.subject
    ).exclude(id__in=all_group_student_ids)

    groups_data = []
    for grp in groups:
        schedule_list = []
        for s in grp.schedule.all():
            if grp.start_time:
                end_t = (datetime.combine(s.date, grp.start_time) + duration).time()
                end_str = end_t.strftime("%H:%M")
                start_str = grp.start_time.strftime("%H:%M")
            else:
                end_str = "—"
                start_str = "—"
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
    })



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

def lesson_schedule_excel(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    schedule = lesson.schedule.all()
    duration = timedelta(minutes=80)

    wb = Workbook()
    ws = wb.active
    ws.title = "Dars jadvali"
    ws.append(["#", "Sana", "Hafta kuni", "Boshlanish", "Tugash", "Fan"])

    for s in schedule:
        end_t = (datetime.combine(s.date, lesson.start_time) + duration).time()
        ws.append([
            s.lesson_number,
            s.date.strftime("%d.%m.%Y"),
            WEEKDAYS[s.date.weekday()],
            lesson.start_time.strftime("%H:%M"),
            end_t.strftime("%H:%M"),
            str(lesson.subject),
        ])

    # Guruhlar
    for grp in lesson.groups.prefetch_related('students').select_related('teacher'):
        ws2 = wb.create_sheet(title=f"{grp.group_number}-guruh")
        ws2.append(["#", "O'quvchi", "O'qituvchi"])
        for idx, st in enumerate(grp.students.all(), 1):
            ws2.append([idx, str(st), str(grp.teacher)])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="jadval_{lesson.pk}.xlsx"'
    wb.save(response)
    return response


def lesson_delete(request, pk):
    lesson = get_object_or_404(Course, pk=pk)
    if request.method == "POST":
        lesson.delete()
        messages.success(request, "Dars o'chirildi")
        return redirect("lesson_list")
    return render(request, "raspisaniya/lesson_delete.html", {"lesson": lesson})


# ─────────────────────────────────────────
# GURUHDAN O'QUVCHI O'CHIRISH
# ─────────────────────────────────────────
def remove_student_from_group(request, group_pk, student_pk):
    group = get_object_or_404(CourseGroup, pk=group_pk)
    student = get_object_or_404(Student, pk=student_pk)
    if request.method == "POST":
        group.students.remove(student)
        # Talabani qayta qarzlar ro'yxatiga qo'shish
        student.debts.add(group.course.subject)
        messages.success(request, f"{student} guruhdan o'chirildi va qayta ro'yxatga qo'shildi")
    return redirect("lesson_schedule", pk=group.course.pk)

# ─────────────────────────────────────────
# TEACHER
# ─────────────────────────────────────────
def teacher_list(request):
    teachers = Teacher.objects.all().order_by('last_name')
    return render(request, 'raspisaniya/teacher_list.html', {'teachers': teachers})


def teacher_create(request):
    if request.method == 'POST':
        form = TeacherForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "O'qituvchi qo'shildi")
            return redirect('teacher_list')
    else:
        form = TeacherForm()
    return render(request, 'raspisaniya/teacher_create.html', {
        'form': form,
        'subjects': Subject.objects.all(),
        'selected_subjects': [],
    })


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


def teacher_delete(request, pk):
    teacher = get_object_or_404(Teacher, pk=pk)
    if request.method == 'POST':
        teacher.delete()
        messages.success(request, "O'qituvchi o'chirildi")
        return redirect('teacher_list')
    return render(request, 'raspisaniya/teacher_delete.html', {'teacher': teacher})


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
def student_list(request):
    students = Student.objects.prefetch_related('debts').order_by('last_name')

    students_data = []
    for student in students:
        completed = list(Subject.objects.filter(
            course__groups__students=student
        ).distinct())
        students_data.append({
            'student': student,
            'completed': completed,
        })

    return render(request, 'raspisaniya/student_list.html', {
        'students_data': students_data,
    })


def student_create(request):
    if request.method == 'POST':
        form = StudentForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "O'quvchi qo'shildi")
            return redirect('student_list')
    else:
        form = StudentForm()
    return render(request, 'raspisaniya/student_create.html', {
        'form': form,
        'subjects': Subject.objects.all(),
        'groups': Group.objects.all(),
        'selected_debts': [],
    })


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


def student_delete(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        student.delete()
        messages.success(request, "O'quvchi o'chirildi")
        return redirect('student_list')
    return render(request, 'raspisaniya/student_delete.html', {'student': student})


import re

def split_subjects(raw):
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

                        # B — Talaba ismi
                        full_name = str(row[1]).strip().split()
                        if len(full_name) < 2:
                            continue
                        first_name = full_name[0]
                        last_name = " ".join(full_name[1:])

                        # E — Guruh
                        group = None
                        if len(row) > 4 and row[4]:
                            group, _ = Group.objects.get_or_create(
                                name=str(row[4]).strip()
                            )

                        # F — Ta'lim tili
                        language = 'uz'
                        if len(row) > 5 and row[5]:
                            lang_raw = str(row[5]).strip().lower()
                            if 'рус' in lang_raw or 'rus' in lang_raw:
                                language = 'ru'
                            elif 'қар' in lang_raw or 'qor' in lang_raw or 'кар' in lang_raw:
                                language = 'qq'
                            elif 'инг' in lang_raw or 'eng' in lang_raw:
                                language = 'en'
                            else:
                                language = 'uz'

                        # Talabani yaratish yoki topish
                        student, created = Student.objects.get_or_create(
                            first_name=first_name,
                            last_name=last_name,
                            defaults={
                                "group": group,
                                "language": language,
                            }
                        )
                        if not created:
                            student.group = group
                            student.language = language
                            student.save()

                        # I — Fanlar
                        if len(row) > 8 and row[8]:
                            subjects_raw = split_subjects(str(row[8]))
                            for subj_name in subjects_raw:
                                if subj_name:
                                    subj, _ = Subject.objects.get_or_create(name=subj_name)
                                    student.debts.add(subj)

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
def subject_list(request):
    subjects = Subject.objects.all().order_by('name')
    return render(request, 'raspisaniya/subject_list.html', {'subjects': subjects})


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


def subject_delete(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    if request.method == 'POST':
        subject.delete()
        messages.success(request, "Fan o'chirildi")
        return redirect('subject_list')
    return render(request, 'raspisaniya/subject_delete.html', {'subject': subject})


def subject_students(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    students = Student.objects.filter(debts=subject).order_by('last_name')
    return render(request, 'raspisaniya/subject_students.html', {
        'subject': subject,
        'students': students,
    })


def subject_students_excel(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    students = Student.objects.filter(debts=subject).order_by('last_name')

    wb = Workbook()
    ws = wb.active
    ws.title = subject.name

    ws.append(["#", "Familiya", "Ism Sharif", "Guruh"])

    for i, student in enumerate(students, 1):
        ws.append([
            i,
            student.last_name,
            student.first_name,
            str(student.group) if student.group else "—",
        ])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{subject.name}_qarzdorlar.xlsx"'
    wb.save(response)
    return response



def build_schedule(request):
    # Jadval tuzilmagan barcha guruhlar
    unscheduled_groups = CourseGroup.objects.filter(
        is_scheduled=False
    ).select_related('course', 'course__subject', 'teacher').prefetch_related('students')

    if not unscheduled_groups.exists():
        messages.info(request, "Barcha guruhlar uchun jadval allaqachon tuzilgan.")
        return redirect("lesson_list")

    errors = []
    success_count = 0

    with transaction.atomic():
        for grp in unscheduled_groups:
            course = grp.course
            students = list(grp.students.all())

            schedule = find_schedule_for_group(
                course.start_date,
                course.end_date,
                course.total_lessons,
                course.lessons_per_week,
                grp.teacher,
                students,
            )

            if schedule is None:
                errors.append({
                    'group': grp,
                    'course': course,
                })
            else:
                para_start = schedule[0][1]
                grp.start_time = para_start
                grp.weekdays = list({d.weekday() for d, _, _ in schedule})
                grp.is_scheduled = True
                grp.save()

                for idx, (ld, p_start, p_end) in enumerate(schedule, 1):
                    GroupSchedule.objects.create(
                        group=grp,
                        date=ld,
                        lesson_number=idx,
                    )
                success_count += 1

    if errors:
        # Xatolik bo'lgan guruhlar uchun boshqa guruhlarni topish
        error_details = []
        for e in errors:
            grp = e['group']
            course = e['course']
            # Shu fandan boshqa guruhlar (jadval tuzilgan)
            other_groups = CourseGroup.objects.filter(
                course=course,
                is_scheduled=True,
            ).exclude(pk=grp.pk).prefetch_related('students')

            error_details.append({
                'group': grp,
                'course': course,
                'other_groups': other_groups,
            })

        return render(request, "raspisaniya/build_schedule_errors.html", {
            "error_details": error_details,
            "success_count": success_count,
        })

    messages.success(request, f"Jadval muvaffaqiyatli tuzildi! {success_count} ta guruh.")
    return redirect("lesson_list")


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


def delete_unscheduled_group(request, pk):
    group = get_object_or_404(CourseGroup, pk=pk, is_scheduled=False)
    if request.method == "POST":
        subject = group.course.subject
        for st in group.students.all():
            st.debts.add(subject)
        group.delete()
        messages.success(request, "Guruh o'chirildi, talabalar qayta ro'yxatga qaytdi.")
    return redirect("build_schedule")


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

        # Jadval tuzilmagan guruhlarni qayta belgilash
        course.groups.update(is_scheduled=False)
        GroupSchedule.objects.filter(group__course=course).delete()

        messages.success(request, "Kurs yangilandi! Qayta jadval tuzing.")
        return redirect("lesson_list")

    return render(request, "raspisaniya/course_update.html", {"course": course})


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


def get_weekly_schedule_data():
    """Barcha scheduled guruhlardan haftalik jadval ma'lumotlarini olish."""
    groups = CourseGroup.objects.filter(
        is_scheduled=True
    ).select_related('course__subject', 'teacher').prefetch_related('schedule')

    groups_data = []
    for g_idx, grp in enumerate(groups):
        schedule_list = []
        for sched in grp.schedule.all():
            if grp.start_time:
                schedule_list.append((sched.date, grp.start_time, None))
        groups_data.append({
            'label': f"{grp.course.subject} {grp.group_number}-guruh",
            'subject': str(grp.course.subject),
            'teacher': str(grp.teacher),
            'group': grp,
            'schedule': schedule_list,
            'color': GROUP_COLORS[g_idx % len(GROUP_COLORS)],
        })
    return groups_data


def weekly_schedule_view(request):
    """Haftalik jadval HTML ko'rinishda."""
    groups_data = get_weekly_schedule_data()

    # Haftalik jadval strukturasi: {(weekday, para_idx): [group_info, ...]}
    schedule_grid = {}
    for g_idx, gdata in enumerate(groups_data):
        for (date_val, start_time, _) in gdata['schedule']:
            weekday = date_val.weekday()
            if weekday > 5:
                continue
            start_str = start_time.strftime("%H:%M")
            para_idx = next(
                (i for i, (s, e) in enumerate(PARA_TIMES_WEEKLY) if s == start_str),
                None
            )
            if para_idx is None:
                continue
            key = (weekday, para_idx)
            if key not in schedule_grid:
                schedule_grid[key] = []
            if not any(x['g_idx'] == g_idx for x in schedule_grid[key]):
                schedule_grid[key].append({
                    'g_idx': g_idx,
                    'label': gdata['label'],
                    'subject': gdata['subject'],
                    'teacher': gdata['teacher'],
                    'color': gdata['color'],
                })

    # Template uchun struktura
    table_data = []
    for day_idx, day_name in enumerate(WEEKDAY_LIST):
        for para_idx, (start, end) in enumerate(PARA_TIMES_WEEKLY):
            row = {
                'day': day_name,
                'day_idx': day_idx,
                'para_idx': para_idx,
                'time': f"{start} - {end}",
                'cells': [],
            }
            for g_idx in range(len(groups_data)):
                key = (day_idx, para_idx)
                entries = [e for e in schedule_grid.get(key, []) if e['g_idx'] == g_idx]
                if entries:
                    row['cells'].append({
                        'filled': True,
                        'subject': entries[0]['subject'],
                        'color': entries[0]['color'],
                    })
                else:
                    row['cells'].append({'filled': False, 'color': 'F8F9FA'})
            table_data.append(row)

    return render(request, "raspisaniya/weekly_schedule.html", {
        "groups_data": groups_data,
        "table_data": table_data,
        "weekdays": WEEKDAY_LIST,
        "para_times": PARA_TIMES_WEEKLY,
    })


def weekly_schedule_excel(request):
    """Haftalik jadval Excel export."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    groups_data = get_weekly_schedule_data()

    wb = Workbook()
    ws = wb.active
    ws.title = "Haftalik jadval"

    thin = Side(style='thin', color='BBBBBB')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal='center', vertical='center', wrap_text=True)
    header_font = Font(name='Arial', bold=True, color='FFFFFF', size=9)
    header_fill = PatternFill('solid', start_color='2E4053')
    time_fill = PatternFill('solid', start_color='5D6D7E')
    time_font = Font(name='Arial', bold=True, color='FFFFFF', size=8)
    day_fill = PatternFill('solid', start_color='34495E')
    day_font = Font(name='Arial', bold=True, color='FFFFFF', size=9)

    # Ustun kengliklar
    ws.column_dimensions['A'].width = 12
    ws.column_dimensions['B'].width = 13
    for i in range(len(groups_data)):
        ws.column_dimensions[get_column_letter(i + 3)].width = 20

    # 1-qator: sarlavha
    ws.row_dimensions[1].height = 35
    for col, (val, fill) in enumerate([("Kun", header_fill), ("Vaqt", header_fill)], 1):
        c = ws.cell(1, col, val)
        c.font = header_font
        c.fill = fill
        c.alignment = center
        c.border = border

    for i, gdata in enumerate(groups_data):
        c = ws.cell(1, i + 3, gdata['label'])
        c.font = header_font
        c.fill = header_fill
        c.alignment = center
        c.border = border

    # Ma'lumotlar grid
    schedule_map = {}
    for g_idx, gdata in enumerate(groups_data):
        for (date_val, start_time, _) in gdata['schedule']:
            weekday = date_val.weekday()
            if weekday > 5:
                continue
            start_str = start_time.strftime("%H:%M")
            para_idx = next(
                (i for i, (s, e) in enumerate(PARA_TIMES_WEEKLY) if s == start_str),
                None
            )
            if para_idx is None:
                continue
            key = (weekday, para_idx)
            if key not in schedule_map:
                schedule_map[key] = {}
            if g_idx not in schedule_map[key]:
                schedule_map[key][g_idx] = gdata

    row = 2
    for day_idx, day_name in enumerate(WEEKDAY_LIST):
        day_start_row = row
        for para_idx, (start, end) in enumerate(PARA_TIMES_WEEKLY):
            ws.row_dimensions[row].height = 35

            # Vaqt
            tc = ws.cell(row, 2, f"{start}\n{end}")
            tc.font = time_font
            tc.fill = time_fill
            tc.alignment = center
            tc.border = border

            # Guruhlar
            for g_idx in range(len(groups_data)):
                col = g_idx + 3
                key = (day_idx, para_idx)
                cell = ws.cell(row, col)
                if key in schedule_map and g_idx in schedule_map[key]:
                    gdata = schedule_map[key][g_idx]
                    cell.value = gdata['subject']
                    cell.fill = PatternFill('solid', start_color=gdata['color'])
                    cell.font = Font(name='Arial', size=8, bold=True)
                else:
                    cell.value = ""
                    cell.fill = PatternFill('solid', start_color='F8F9FA')
                    cell.font = Font(name='Arial', size=8)
                cell.alignment = center
                cell.border = border

            row += 1

        # Kun nomini merge
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