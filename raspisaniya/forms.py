from django import forms
from .models import Teacher, Student, Subject


class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ['name']


class TeacherForm(forms.ModelForm):
    class Meta:
        model = Teacher
        fields = ['first_name', 'last_name', 'subjects']
        widgets = {
            'subjects': forms.CheckboxSelectMultiple(),
        }


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ['first_name', 'last_name', 'group', 'language', 'debts']
        widgets = {
            'debts': forms.CheckboxSelectMultiple(),
        }


class StudentImportForm(forms.Form):
    file = forms.FileField(label="Excel fayl (o'quvchilar)")


class TeacherImportForm(forms.Form):
    file = forms.FileField(label="Excel fayl (o'qituvchilar)")