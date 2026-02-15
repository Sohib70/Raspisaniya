from django.shortcuts import render, redirect,get_object_or_404
from django.contrib import messages
from .forms import LessonForm, TeacherForm, StudentForm, SubjectForm
from .models import Lesson,Student,Subject,Teacher
from django.core.exceptions import ValidationError
from django import forms

from .models import Lesson


def lesson_list(request):
    lessons = Lesson.objects.all().order_by('start_time')
    return render(request, 'raspisaniya/lesson_list.html', {'lessons': lessons})

from django import forms
from django.core.exceptions import ValidationError
from .models import Lesson
from datetime import timedelta

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