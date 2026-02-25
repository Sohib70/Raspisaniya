from django.db import models
from django.core.exceptions import ValidationError
from datetime import timedelta


class Subject(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

class Group(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

class Student(models.Model):
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)

    group = models.ForeignKey(
        Group,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    debts = models.ManyToManyField(Subject, related_name='debt_students')


class Teacher(models.Model):
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    subjects = models.ManyToManyField(Subject,related_name='students')

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Lesson(models.Model):
    subject = models.ForeignKey('Subject', on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.subject} darsi"


class LessonGroup(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='groups')
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE)
    students = models.ManyToManyField(Student)

    start_time = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField(default=80)

    def end_time(self):
        return self.start_time + timedelta(minutes=self.duration_minutes)

    def clean(self):
        new_start = self.start_time
        new_end = self.end_time()

        teacher_conflict = LessonGroup.objects.filter(
            teacher=self.teacher,
            start_time__lt=new_end
        ).exclude(id=self.id)

        for lesson in teacher_conflict:
            if lesson.end_time() > new_start:
                raise ValidationError("O‘qituvchi bu vaqtda band")

