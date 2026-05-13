from django import forms
from .models import Teacher, Student, Subject


class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ['name']


class TeacherForm(forms.ModelForm):
    teacher_id = forms.CharField(
        required=False,
        label="O'qituvchi ID",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Masalan: T-3'})
    )

    class Meta:
        model = Teacher
        fields = ['first_name', 'last_name', 'teacher_id', 'subjects']
        widgets = {
            'subjects': forms.CheckboxSelectMultiple(),
        }

    def save(self, commit=True):
        teacher = super().save(commit=False)
        new_id = self.cleaned_data.get('teacher_id', '').strip()
        # Bo'sh bo'lsa — eski ID ni saqlab qolamiz
        if new_id:
            teacher.teacher_id = new_id
        if commit:
            teacher.save()
            self._save_m2m()
        return teacher


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