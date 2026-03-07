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
    from .models import Course
    courses = Course.objects.select_related('subject').prefetch_related('groups').all()
    return render(request, "raspisaniya/lesson_list.html", {"courses": courses})


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

        # Barcha guruhlarga qo'shilgan talabalar ID lari
        assigned_ids = set()
        for g in all_groups:
            for s in g['students']:
                assigned_ids.add(s.id)

        # Hech qaysi guruhga tushmagan talabalar
        # assigned bo'lmagan talabalar
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
            "all_students": all_students,  # JS uchun
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

        # Har guruh uchun jadval topish
        all_errors = []
        group_schedules = []

        for i, (gdata, teacher) in enumerate(zip(all_groups_data, group_teachers)):
            selected_ids = request.POST.getlist(f"students_{i}")
            g_students = [s for s in gdata['students'] if str(s.id) in selected_ids] \
                         if selected_ids else gdata['students']

            schedule = find_schedule_for_group(
                start_date, end_date, total_lessons, lessons_per_week,
                teacher, g_students
            )

            if schedule is None:
                all_errors.append(
                    f"❌ {i+1}-guruh ({dict(LANGUAGE_CHOICES).get(gdata['lang'])}) uchun "
                    f"yetarli bo'sh vaqt topilmadi. O'qituvchini o'zgartiring yoki "
                    f"sana oralig'ini kengaytiring."
                )
            else:
                group_schedules.append(schedule)

        if all_errors:
            teachers = Teacher.objects.filter(subjects=subject)
            all_students2 = list(Student.objects.filter(debts=subject).distinct())
            students_by_lang2 = defaultdict(list)
            for st in all_students2:
                students_by_lang2[st.language].append(st)
            all_groups_display = []
            for lang, lang_students in students_by_lang2.items():
                groups = split_into_groups(lang_students)
                for g in groups:
                    if len(g) >= 8:
                        all_groups_display.append({
                            'lang': lang,
                            'lang_name': dict(LANGUAGE_CHOICES).get(lang, lang),
                            'students': g,
                        })

            # assigned bo'lmagan talabalar
            assigned_ids = set()
            for g in all_groups_display:
                for s in g['students']:
                    assigned_ids.add(s.id)
            unassigned_students2 = [s for s in all_students2 if s.id not in assigned_ids]

            return render(request, "raspisaniya/lesson_create.html", {
                "step": 2,
                "subject": subject,
                "all_groups": all_groups_display,
                "groups_count": len(all_groups_display),
                "teachers": teachers,
                "start_date": start_date_raw,
                "end_date": end_date_raw,
                "total_lessons": total_lessons,
                "lessons_per_week": lessons_per_week,
                "all_errors": all_errors,
                "selected_teachers": {i: t.id for i, t in enumerate(group_teachers)},
                "unassigned_students": unassigned_students2,
                "all_students": all_students2,
            })

        # Saqlash
        with transaction.atomic():
            course = Course.objects.create(
                subject=subject,
                start_date=start_date,
                end_date=end_date,
                total_lessons=total_lessons,
                lessons_per_week=lessons_per_week,
                lesson_duration=80,
            )

            for i, (gdata, teacher, schedule) in enumerate(
                zip(all_groups_data, group_teachers, group_schedules)
            ):
                selected_ids = request.POST.getlist(f"students_{i}")
                g_students = gdata['students']
                selected_students = [s for s in g_students if str(s.id) in selected_ids] \
                                    if selected_ids else g_students

                if not selected_students:
                    continue

                para_start = schedule[0][1]

                cgroup = CourseGroup.objects.create(
                    course=course,
                    teacher=teacher,
                    group_number=i + 1,
                    start_time=para_start,
                    weekdays=list({d.weekday() for d, _, _ in schedule}),
                    language=gdata['lang'],
                )
                cgroup.students.set(selected_students)

                for st in selected_students:
                    st.debts.remove(subject)

                for idx, (ld, p_start, p_end) in enumerate(schedule, 1):
                    GroupSchedule.objects.create(
                        group=cgroup,
                        date=ld,
                        lesson_number=idx,
                    )

        messages.success(request, f"Kurs yaratildi! {len(all_groups_data)} ta guruh.")
        return redirect("lesson_list")


# ─────────────────────────────────────────
# LESSON SCHEDULE
# ─────────────────────────────────────────
def lesson_schedule(request, pk):
    course = get_object_or_404(Course, pk=pk)
    groups = course.groups.prefetch_related('students', 'schedule').select_related('teacher')
    duration = timedelta(minutes=80)

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
        })

    return render(request, "raspisaniya/lesson_schedule.html", {
        "course": course,
        "groups_data": groups_data,
    })


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
    lesson = get_object_or_404(Lesson, pk=pk)
    if request.method == "POST":
        lesson.delete()
        messages.success(request, "Dars o'chirildi")
        return redirect("lesson_list")
    return render(request, "raspisaniya/lesson_delete.html", {"lesson": lesson})


# ─────────────────────────────────────────
# GURUHDAN O'QUVCHI O'CHIRISH
# ─────────────────────────────────────────
def remove_student_from_group(request, group_pk, student_pk):
    from .models import LessonGroup
    group = get_object_or_404(LessonGroup, pk=group_pk)
    student = get_object_or_404(Student, pk=student_pk)
    if request.method == "POST":
        group.students.remove(student)
        messages.success(request, f"{student} guruhdan o'chirildi")
    return redirect("lesson_schedule", pk=group.lesson.pk)


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