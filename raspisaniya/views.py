from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import LessonForm, TeacherForm, StudentForm, SubjectForm
from .models import Lesson
from django.core.exceptions import ValidationError

def lesson_list(request):
    lessons = Lesson.objects.all().order_by('start_time')
    return render(request, 'raspisaniya/lesson_list.html', {'lessons': lessons})

def lesson_create(request):
    if request.method == 'POST':
        form = LessonForm(request.POST)
        if form.is_valid():
            lesson = form.save(commit=False)
            lesson.save()           # id hosil bo‘ladi
            form.save_m2m()         # Many-to-Many qo‘shiladi

            # Endi clean() chaqiriladi va bandlik tekshiriladi
            try:
                lesson.full_clean()
                lesson.save()
                messages.success(request, "Dars muvaffaqiyatli qo‘shildi")
                return redirect('lesson_list')
            except ValidationError as e:
                messages.error(request, e)
    else:
        form = LessonForm()

    return render(request, 'raspisaniya/lesson_create.html', {'form': form})

# Teacher qo‘shish
def teacher_create(request):
    if request.method == 'POST':
        form = TeacherForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "O‘qituvchi qo‘shildi")
            return redirect('lesson_create')
    else:
        form = TeacherForm()
    return render(request, 'raspisaniya/teacher_create.html', {'form': form})

def teacher_list(request):
    teachers = Teacher.objects.all().order_by('last_name')
    return render(request, 'raspisaniya/teacher_list.html', {'teachers': teachers})

# Student qo‘shish
def student_create(request):
    if request.method == 'POST':
        form = StudentForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "O‘quvchi qo‘shildi")
            return redirect('lesson_create')
    else:
        form = StudentForm()
    return render(request, 'raspisaniya/student_create.html', {'form': form})

def student_list(request):
    students = Student.objects.all().order_by('last_name')
    return render(request, 'raspisaniya/student_list.html', {'students': students})

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
