from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.utils.dateparse import parse_date
from openpyxl import load_workbook, Workbook
from django.http import HttpResponse
from datetime import timedelta, datetime, time as dtime

from .forms import TeacherForm, StudentForm, SubjectForm, StudentImportForm, TeacherImportForm
from .models import Lesson, LessonSchedule, Student, Subject, Teacher, Group


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


def split_into_groups(students, max_size=30):
    """
    70 ta -> [24, 23, 23]
    30 ta -> [30]
    31 ta -> [16, 15]
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

    for sched in schedules:
        ex_start = datetime.combine(sched.date, sched.lesson.start_time)
        ex_end = ex_start + duration
        new_start = datetime.combine(sched.date, start_time)
        new_end = new_start + duration

        overlap = new_start < ex_end and new_end > ex_start
        if not overlap:
            continue

        day_str = f"{sched.date.strftime('%d.%m.%Y')} ({WEEKDAYS[sched.date.weekday()]})"

        # O'qituvchi conflict — LessonGroup orqali
        if sched.lesson.groups.filter(teacher=teacher).exists():
            errors['teacher'].append(
                f"{day_str} — '{sched.lesson.subject}' darsi "
                f"{sched.lesson.start_time.strftime('%H:%M')} da band"
            )

        # O'quvchi conflict — LessonGroup orqali
        for st in students:
            if sched.lesson.groups.filter(students=st).exists():
                if st not in errors['students']:
                    errors['students'][st] = []
                errors['students'][st].append(
                    f"{day_str} — '{sched.lesson.subject}' darsi "
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
def lesson_create(request):

    # ── STEP 1: Fan tanlash ──
    if request.method == "GET":
        subjects = Subject.objects.all()
        return render(request, "raspisaniya/lesson_create.html", {
            "step": 1,
            "subjects": subjects,
        })

    # ── STEP 2: Fan tanlandi, guruhlar va vaqt ko'rsatish ──
    if request.method == "POST" and request.POST.get("step") == "2":
        subject_id = request.POST.get("subject")
        subject = get_object_or_404(Subject, id=subject_id)

        students = list(Student.objects.filter(debts=subject).distinct())

        if not students:
            messages.error(request, "Bu fandan yiqilgan o'quvchi yo'q")
            return redirect("lesson_create")

        groups = split_into_groups(students)
        teachers = Teacher.objects.filter(subjects=subject)

        return render(request, "raspisaniya/lesson_create.html", {
            "step": 2,
            "subject": subject,
            "groups": groups,
            "teachers": teachers,
            "groups_count": len(groups),
            "enumerate": enumerate,
        })

    # ── STEP 3: Saqlash ──
    if request.method == "POST" and request.POST.get("step") == "3":
        subject_id = request.POST.get("subject_id")
        subject = get_object_or_404(Subject, id=subject_id)

        start_date_raw = request.POST.get("start_date")
        start_time_raw = request.POST.get("start_time")
        groups_count = int(request.POST.get("groups_count", 1))

        if not start_date_raw or not start_time_raw:
            messages.error(request, "Sana va vaqtni kiriting")
            return redirect("lesson_create")

        start_date = parse_date(start_date_raw)
        h, m = start_time_raw.split(":")
        start_time = dtime(int(h), int(m))
        lesson_dates = get_lesson_dates(start_date, 15)

        students_all = list(Student.objects.filter(debts=subject).distinct())
        groups_data = split_into_groups(students_all)

        # ── Har bir guruh uchun o'qituvchi olish ──
        group_teachers = []
        for i in range(groups_count):
            tid = request.POST.get(f"teacher_{i}")
            if not tid:
                messages.error(request, f"{i+1}-guruh uchun o'qituvchi tanlanmagan")
                return redirect("lesson_create")
            group_teachers.append(get_object_or_404(Teacher, id=tid))

        # ── Conflict tekshiruvi (barcha guruhlar uchun) ──
        all_errors = []
        # Bir xil dars ichida o'qituvchi qayta ishlatilganmi tekshirish
        seen_teachers = {}
        for i, teacher in enumerate(group_teachers):
            if teacher.id in seen_teachers:
                all_errors.append(
                    f"❌ O'qituvchi {teacher} {seen_teachers[teacher.id] + 1}-guruh va "
                    f"{i + 1}-guruhga bir vaqtda tayinlangan!"
                )
            else:
                seen_teachers[teacher.id] = i

        for i, (g_students, teacher) in enumerate(zip(groups_data, group_teachers)):
            conflicts = check_conflicts(lesson_dates, start_time, teacher, g_students)

            if conflicts['teacher']:
                for msg in conflicts['teacher']:
                    all_errors.append(f"❌ O'qituvchi {teacher} ({i+1}-guruh): {msg}")

            for st, msgs in conflicts['students'].items():
                for msg in msgs:
                    all_errors.append(f"❌ O'quvchi {st} ({i+1}-guruh): {msg}")

        if all_errors:
            # Xatoliklar bilan step2 ga qaytish
            teachers = Teacher.objects.filter(subjects=subject)
            for err in all_errors:
                messages.error(request, err)
            return render(request, "raspisaniya/lesson_create.html", {
                "step": 2,
                "subject": subject,
                "groups": groups_data,
                "teachers": teachers,
                "groups_count": len(groups_data),
                "start_date": start_date_raw,
                "start_time": start_time_raw,
                "selected_teachers": {i: t.id for i, t in enumerate(group_teachers)},
                "enumerate": enumerate,
            })

        # ── Saqlash ──
        with transaction.atomic():
            lesson = Lesson.objects.create(
                subject=subject,
                start_date=start_date,
                start_time=start_time,
            )

            for i, (g_students, teacher) in enumerate(zip(groups_data, group_teachers)):
                from .models import LessonGroup
                group = LessonGroup.objects.create(
                    lesson=lesson,
                    teacher=teacher,
                    group_number=i + 1,
                )
                group.students.set(g_students)

                # Qarzni o'chirish
                for st in g_students:
                    st.debts.remove(subject)

            for idx, ld in enumerate(lesson_dates, 1):
                LessonSchedule.objects.create(lesson=lesson, date=ld, lesson_number=idx)

        messages.success(request, f"Dars yaratildi! {len(groups_data)} ta guruh, 15 ta jadval.")
        return redirect("lesson_schedule", pk=lesson.pk)


# ─────────────────────────────────────────
# LESSON SCHEDULE
# ─────────────────────────────────────────
def lesson_schedule(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    schedule = lesson.schedule.all()
    duration = timedelta(minutes=80)

    schedule_list = []
    for s in schedule:
        end_t = (datetime.combine(s.date, lesson.start_time) + duration).time()
        schedule_list.append({
            "sched": s,
            "weekday": WEEKDAYS[s.date.weekday()],
            "end_time": end_t.strftime("%H:%M"),
        })

    groups = lesson.groups.prefetch_related('students').select_related('teacher')

    return render(request, "raspisaniya/lesson_schedule.html", {
        "lesson": lesson,
        "schedule_list": schedule_list,
        "groups": groups,
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
    students = Student.objects.all().order_by('last_name')
    return render(request, 'raspisaniya/student_list.html', {'students': students})


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
                        if not row or not row[0]:
                            continue
                        parts = str(row[0]).strip().split()
                        if len(parts) < 2:
                            continue
                        group = None
                        if len(row) > 1 and row[1]:
                            group, _ = Group.objects.get_or_create(name=str(row[1]).strip())
                        student, created = Student.objects.get_or_create(
                            first_name=parts[0],
                            last_name=" ".join(parts[1:]),
                            defaults={"group": group}
                        )
                        if not created and group:
                            student.group = group
                            student.save()
                        if len(row) > 2 and row[2]:
                            for sname in str(row[2]).split(","):
                                sname = sname.strip()
                                if sname:
                                    subj, _ = Subject.objects.get_or_create(name=sname)
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