from django.shortcuts import render, redirect,get_object_or_404,get_object_or_404
from django.contrib import messages
from .forms import LessonForm, TeacherForm, StudentForm, SubjectForm,StudentImportForm
from .models import Lesson,Student,Subject,Teacher,LessonGroup,Group
from django.core.exceptions import ValidationError
from django import forms
from django.utils import timezone
from .models import Lesson
from openpyxl import load_workbook
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

def lesson_list(request):
    groups = LessonGroup.objects.select_related("lesson", "teacher").order_by("start_time")

    return render(request, "raspisaniya/lesson_list.html", {
        "groups": groups
    })

from django import forms
from django.core.exceptions import ValidationError
from .models import Lesson
from datetime import timedelta

from django.utils.dateparse import parse_datetime
from django.db import transaction
from django.contrib import messages


def chunk_students(students, size=30):
    for i in range(0, len(students), size):
        yield students[i:i + size]


@transaction.atomic
def lesson_create(request):

    # ================= STEP 1 =================
    if request.method == "GET":
        subjects = Subject.objects.all()
        return render(request, "raspisaniya/lesson_create.html", {
            "subjects": subjects
        })

    # ================= STEP 2 =================
    if request.method == "POST" and "final_submit" not in request.POST:

        subject_id = request.POST.get("subject")
        subject = Subject.objects.get(id=subject_id)

        failed_students = Student.objects.filter(
            debts=subject
        ).distinct()

        students = list(failed_students)

        if not students:
            messages.error(request, "Yiqilgan student yo‘q")
            return redirect("lesson_create")

        groups = list(chunk_students(students, 30))

        teachers = Teacher.objects.filter(subjects=subject)

        return render(request, "raspisaniya/lesson_create.html", {
            "subject": subject,
            "groups": groups,
            "teachers": teachers,
            "step2": True
        })

    # ================= FINAL SAVE =================
    if request.method == "POST" and "final_submit" in request.POST:

        try:
            subject_id = request.POST.get("subject_id")
            subject = Subject.objects.get(id=subject_id)

            failed_students = Student.objects.filter(
                debts=subject
            ).distinct()

            students = list(failed_students)

            lesson = Lesson.objects.create(subject=subject)

            groups = list(chunk_students(students, 30))

            for index, group_students in enumerate(groups):

                teacher_id = request.POST.get(f"teacher_{index}")
                start_time_raw = request.POST.get(f"start_time_{index}")

                if not teacher_id or not start_time_raw:
                    messages.error(request, "Teacher yoki vaqt tanlanmagan")
                    return redirect("lesson_create")

                teacher = Teacher.objects.get(id=teacher_id)

                if subject not in teacher.subjects.all():
                    messages.error(request, f"{teacher} bu fanni o‘qita olmaydi")
                    return redirect("lesson_create")

                start_time = parse_datetime(start_time_raw)
                if not start_time:
                    messages.error(request, "Vaqt noto‘g‘ri formatda")
                    return redirect("lesson_create")

                if timezone.is_naive(start_time):
                    start_time = timezone.make_aware(start_time)

                # ================= TEACHER CONFLICT =================
                new_end = start_time + timezone.timedelta(minutes=80)
                teacher_conflicts = LessonGroup.objects.filter(
                    teacher=teacher,
                    start_time__lt=new_end
                ).exclude(lesson=lesson)

                conflict_found = False
                for conflict in teacher_conflicts:
                    if conflict.end_time() > start_time:
                        conflict_found = True
                        break

                if conflict_found:
                    messages.error(request, f"{teacher} shu vaqtda boshqa guruhda band")
                    return redirect("lesson_create")

                # ================= GROUP YARATISH =================
                group = LessonGroup.objects.create(
                    lesson=lesson,
                    teacher=teacher,
                    start_time=start_time,
                    duration_minutes=80
                )

                # ================= STUDENT KONFLIKT =================
                for student in group_students:

                    conflict = LessonGroup.objects.filter(
                        students=student,
                        start_time__lt=group.end_time()
                    ).exclude(id=group.id)

                    if not any(l.end_time() > group.start_time for l in conflict):
                        group.students.add(student)
                        student.debts.remove(subject)

            messages.success(request, "Darslar muvaffaqiyatli yaratildi")
            return redirect("lesson_list")

        except ValidationError as e:
            for msg in e.messages:  # e.messages list sifatida keladi
                messages.error(request, msg)
            return redirect("lesson_create")



def lesson_update(request, pk):
    group = get_object_or_404(LessonGroup, pk=pk)

    if request.method == "POST":
        teacher_id = request.POST.get("teacher")
        start_time_raw = request.POST.get("start_time")

        from django.utils import timezone
        from django.utils.dateparse import parse_datetime

        start_time = parse_datetime(start_time_raw)

        if timezone.is_naive(start_time):
            start_time = timezone.make_aware(start_time)

        teacher = Teacher.objects.get(id=teacher_id)

        group.teacher = teacher
        group.start_time = start_time
        group.save()

        messages.success(request, "Dars yangilandi")
        return redirect("lesson_list")

    teachers = Teacher.objects.filter(subjects=group.lesson.subject)

    return render(request, "raspisaniya/lesson_update.html", {
        "group": group,
        "teachers": teachers
    })

# ✅ Lesson Delete
def lesson_delete(request, pk):
    group = get_object_or_404(LessonGroup, pk=pk)

    if request.method == "POST":
        group.delete()
        messages.success(request, "Dars o‘chirildi")
        return redirect("lesson_list")

    return render(request, "raspisaniya/lesson_delete.html", {
        "group": group
    })

def teacher_create(request):
    if request.method == 'POST':
        form = TeacherForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "O‘qituvchi qo‘shildi")
            return redirect('teacher_list')
    else:
        form = TeacherForm()
    return render(request, 'raspisaniya/teacher_create.html', {'form': form})



def teacher_list(request):
    teachers = Teacher.objects.all().order_by('last_name')
    return render(request, 'raspisaniya/teacher_list.html', {'teachers': teachers})

def teacher_update(request, pk):
    teacher = get_object_or_404(Teacher, pk=pk)
    if request.method == 'POST':
        form = TeacherForm(request.POST, instance=teacher)
        if form.is_valid():
            form.save()
            messages.success(request, "O‘qituvchi muvaffaqiyatli yangilandi")
            return redirect('teacher_list')
    else:
        form = TeacherForm(instance=teacher)
    return render(request, 'raspisaniya/teacher_create.html', {'form': form})

def teacher_delete(request, pk):
    teacher = get_object_or_404(Teacher, pk=pk)
    if request.method == 'POST':
        teacher.delete()
        messages.success(request, "O‘qituvchi muvaffaqiyatli o‘chirildi")
        return redirect('teacher_list')
    return render(request, 'raspisaniya/teacher_delete.html', {'teacher': teacher})

def student_create(request):
    if request.method == 'POST':
        form = StudentForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "O‘quvchi qo‘shildi")
            return redirect('student_list')
    else:
        form = StudentForm()
    return render(request, 'raspisaniya/student_create.html', {'form': form})

def student_list(request):
    students = Student.objects.all().order_by('last_name')
    return render(request, 'raspisaniya/student_list.html', {'students': students})

def student_update(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        form = StudentForm(request.POST, instance=student)
        if form.is_valid():
            form.save()
            messages.success(request, "O‘quvchi muvaffaqiyatli yangilandi")
            return redirect('student_list')
    else:
        form = StudentForm(instance=student)
    return render(request, 'raspisaniya/student_create.html', {'form': form})

# ✅ Student Delete
def student_delete(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        student.delete()
        messages.success(request, "O‘quvchi muvaffaqiyatli o‘chirildi")
        return redirect('student_list')
    return render(request, 'raspisaniya/student_delete.html', {'student': student})

# Subject qo‘shish
def subject_create(request):
    if request.method == 'POST':
        form = SubjectForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Fan qo‘shildi")
            return redirect('lesson_create')
    else:
        form = SubjectForm()
    return render(request, 'raspisaniya/subject_create.html', {'form': form})

def subject_list(request):
    subjects = Subject.objects.all().order_by('name')
    return render(request, 'raspisaniya/subject_list.html', {'subjects': subjects})


def subject_update(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    if request.method == 'POST':
        form = SubjectForm(request.POST, instance=subject)
        if form.is_valid():
            form.save()
            messages.success(request, "Fan muvaffaqiyatli yangilandi")
            return redirect('subject_list')
    else:
        form = SubjectForm(instance=subject)
    return render(request, 'raspisaniya/subject_create.html', {'form': form})

def subject_delete(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    if request.method == 'POST':
        subject.delete()
        messages.success(request, "Fan muvaffaqiyatli o‘chirildi")
        return redirect('subject_list')
    return render(request, 'raspisaniya/subject_delete.html', {'subject': subject})



from django.shortcuts import render, redirect
from django.db import transaction
from django.contrib import messages
from openpyxl import load_workbook

from .forms import StudentImportForm



def import_students(request):
    if request.method == "POST":
        form = StudentImportForm(request.POST, request.FILES)

        if form.is_valid():
            file = request.FILES["file"]

            try:
                workbook = load_workbook(file)
                sheet = workbook.active

                with transaction.atomic():

                    for row in sheet.iter_rows(min_row=2, values_only=True):

                        if not row or not row[0]:
                            continue

                        # =========================
                        # 1️⃣ ISM FAMILIYA
                        # =========================
                        full_name = str(row[0]).strip()
                        name_parts = full_name.split()

                        if len(name_parts) < 2:
                            continue

                        first_name = name_parts[0]
                        last_name = " ".join(name_parts[1:])

                        # =========================
                        # 2️⃣ GURUH
                        # =========================
                        group = None
                        if len(row) > 1 and row[1]:
                            group_name = str(row[1]).strip()
                            group, _ = Group.objects.get_or_create(
                                name=group_name
                            )

                        # =========================
                        # 3️⃣ STUDENT YARATISH
                        # =========================
                        student, created = Student.objects.get_or_create(
                            first_name=first_name,
                            last_name=last_name,
                            defaults={"group": group}
                        )

                        # Agar student bor bo‘lsa group ni yangilaymiz
                        if not created and group:
                            student.group = group
                            student.save()

                        # =========================
                        # 4️⃣ FANLAR (DEBTS)
                        # =========================
                        if len(row) > 2 and row[2]:
                            subject_list = str(row[2]).split(",")

                            for subject_name in subject_list:
                                subject_name = subject_name.strip()

                                if subject_name:
                                    subject, _ = Subject.objects.get_or_create(
                                        name=subject_name
                                    )
                                    student.debts.add(subject)

                messages.success(request, "Studentlar muvaffaqiyatli import qilindi ✅")
                return redirect("student_list")

            except Exception as e:
                messages.error(request, f"Xatolik yuz berdi: {e}")

    else:
        form = StudentImportForm()

    return render(request, "raspisaniya/import_students.html", {"form": form})