from django.db import models
from django.core.exceptions import ValidationError
from datetime import timedelta

class Group(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name

class Subject(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Student(models.Model):
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True)
    debts = models.ManyToManyField(Subject, related_name='debt_students')

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Teacher(models.Model):
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    subjects = models.ManyToManyField(Subject,related_name='students')

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Lesson(models.Model):
    subject = models.ForeignKey('Subject', on_delete=models.CASCADE)
    teachers = models.ManyToManyField('Teacher')
    students = models.ManyToManyField('Student')
    start_time = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField(default=80)

    def end_time(self):
        return self.start_time + timedelta(minutes=self.duration_minutes)

    def clean(self):
        if not self.id:
            return

        if self.teachers.count() > 2:
            raise ValidationError("Bitta darsga 2 tadan ortiq o‘qituvchi bo‘lmaydi")

        for teacher in self.teachers.all():
            qs = Lesson.objects.filter(
                teachers=teacher,
                start_time__lt=self.end_time(),
                start_time__gt=self.start_time - timedelta(minutes=80)
            ).exclude(id=self.id)
            if qs.exists():
                raise ValidationError(f"{teacher} bu vaqtda band")

        for student in self.students.all():
            qs = Lesson.objects.filter(
                students=student,
                start_time__lt=self.end_time(),
                start_time__gt=self.start_time - timedelta(minutes=80)
            ).exclude(id=self.id)
            if qs.exists():
                raise ValidationError(f"{student} bu vaqtda boshqa darsda")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.full_clean()
        super().save(*args, **kwargs)

