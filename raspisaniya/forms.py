from django import forms
from .models import Lesson, Teacher, Student, Subject
from datetime import timedelta
from django.core.exceptions import ValidationError

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


# class LessonForm(forms.ModelForm):
#     teachers = forms.ModelMultipleChoiceField(
#         queryset=Teacher.objects.all(),
#         widget=forms.SelectMultiple(attrs={'class': 'form-select'})
#     )
#     students = forms.ModelMultipleChoiceField(
#         queryset=Student.objects.all(),
#         widget=forms.SelectMultiple(attrs={'class': 'form-select'})
#     )
#
#     class Meta:
#         model = Lesson
#         fields = ['subject', 'teachers', 'students', 'start_time', 'duration_minutes']
#         widgets = {
#             'subject': forms.Select(attrs={'class': 'form-select'}),
#             'start_time': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
#             'duration_minutes': forms.NumberInput(attrs={'class': 'form-control'}),
#         }

class LessonForm(forms.ModelForm):

    class Meta:
        model = Lesson
        fields = '__all__'
        widgets = {
            'teachers': forms.CheckboxSelectMultiple(),
            'students': forms.CheckboxSelectMultiple(),
            'start_time': forms.DateTimeInput(
                attrs={
                    'type': 'datetime-local',
                    'class': 'form-control'
                }
            ),
        }
    def clean(self):
        cleaned_data = super().clean()

        teachers = cleaned_data.get("teachers")
        students = cleaned_data.get("students")
        start_time = cleaned_data.get("start_time")
        duration = cleaned_data.get("duration_minutes")

        if not start_time or not duration:
            return cleaned_data

        end_time = start_time + timedelta(minutes=duration)

        # O‘qituvchi tekshiruv
        if teachers:
            for teacher in teachers:
                lessons = Lesson.objects.filter(
                    teachers=teacher,
                    start_time__lt=end_time
                )

                if self.instance.pk:
                    lessons = lessons.exclude(pk=self.instance.pk)

                for lesson in lessons:
                    existing_end = lesson.start_time + timedelta(minutes=lesson.duration_minutes)

                    if existing_end > start_time:
                        raise ValidationError(
                            f"{teacher} bu vaqtda boshqa darsda"
                        )

        # O‘quvchi tekshiruv
        if students:
            for student in students:
                lessons = Lesson.objects.filter(
                    students=student,
                    start_time__lt=end_time
                )

                if self.instance.pk:
                    lessons = lessons.exclude(pk=self.instance.pk)

                for lesson in lessons:
                    existing_end = lesson.start_time + timedelta(minutes=lesson.duration_minutes)

                    if existing_end > start_time:
                        raise ValidationError(
                            f"{student} bu vaqtda boshqa darsda"
                        )

        return cleaned_data