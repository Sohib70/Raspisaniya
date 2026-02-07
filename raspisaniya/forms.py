from django import forms
from .models import Lesson, Teacher, Student, Subject

class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ['name']

class TeacherForm(forms.ModelForm):
    class Meta:
        model = Teacher
        fields = ['first_name', 'last_name', 'subjects']

class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ['first_name', 'last_name', 'debts']


class LessonForm(forms.ModelForm):
    teachers = forms.ModelMultipleChoiceField(
        queryset=Teacher.objects.all(),
        widget=forms.SelectMultiple(attrs={'class': 'form-select'})
    )
    students = forms.ModelMultipleChoiceField(
        queryset=Student.objects.all(),
        widget=forms.SelectMultiple(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Lesson
        fields = ['subject', 'teachers', 'students', 'start_time', 'duration_minutes']
        widgets = {
            'subject': forms.Select(attrs={'class': 'form-select'}),
            'start_time': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'duration_minutes': forms.NumberInput(attrs={'class': 'form-control'}),
        }