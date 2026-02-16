from django.shortcuts import render, redirect,get_object_or_404
from django.contrib import messages
from .forms import LessonForm, TeacherForm, StudentForm, SubjectForm,StudentImportForm
from .models import Lesson,Student,Subject,Teacher,Group
from django.core.exceptions import ValidationError
from .models import Lesson
import openpyxl

def lesson_list(request):
    lessons = Lesson.objects.all().order_by('start_time')
    return render(request, 'raspisaniya/lesson_list.html', {'lessons': lessons})


def lesson_create(request):
    if request.method == 'POST':
        form = LessonForm(request.POST)

        if form.is_valid():
            form.save()
            messages.success(request, "Dars muvaffaqiyatli qo‘shildi")
            return redirect('lesson_list')
    else:
        form = LessonForm()

    return render(request, 'raspisaniya/lesson_create.html', {'form': form})


def lesson_update(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    if request.method == 'POST':
        form = LessonForm(request.POST, instance=lesson)
        if form.is_valid():
            lesson = form.save(commit=False)
            try:
                lesson.full_clean()
                lesson.save()
                form.save_m2m()
                messages.success(request, "Dars muvaffaqiyatli yangilandi")
                return redirect('lesson_list')
            except ValidationError as e:
                messages.error(request, e)
    else:
        form = LessonForm(instance=lesson)
    return render(request, 'raspisaniya/lesson_create.html', {'form': form})

# ✅ Lesson Delete
def lesson_delete(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    if request.method == 'POST':
        lesson.delete()
        messages.success(request, "Dars muvaffaqiyatli o‘chirildi")
        return redirect('lesson_list')
    return render(request, 'raspisaniya/lesson_delete.html', {'lesson': lesson})

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




def import_students(request):
    if request.method == "POST":
        form = StudentImportForm(request.POST, request.FILES)
        if form.is_valid():
            file = request.FILES["file"]
            workbook = openpyxl.load_workbook(file)
            sheet = workbook.active

            for row in sheet.iter_rows(min_row=2, values_only=True):

                if not row[0]:
                    continue

                # 1️⃣ Talaba (Ism Familiya)
                full_name = str(row[0]).strip()
                name_parts = full_name.split()

                if len(name_parts) < 2:
                    continue

                first_name = name_parts[0]
                last_name = " ".join(name_parts[1:])

                # 2️⃣ Guruh
                group_name = str(row[1]).strip() if row[1] else None
                group = None

                if group_name:
                    group, _ = Group.objects.get_or_create(name=group_name)

                student, _ = Student.objects.get_or_create(
                    first_name=first_name,
                    last_name=last_name,
                    defaults={'group': group}
                )

                if group:
                    student.group = group
                    student.save()

                # 3️⃣ Yiqilgan fanlar
                subject_list = row[2]

                if subject_list:
                    subjects = str(subject_list).split(",")

                    for subject_name in subjects:
                        subject_name = subject_name.strip()
                        if subject_name:
                            subject, _ = Subject.objects.get_or_create(name=subject_name)
                            student.debts.add(subject)

            return redirect("student_list")

    else:
        form = StudentImportForm()

    return render(request, "raspisaniya/import_students.html", {"form": form})