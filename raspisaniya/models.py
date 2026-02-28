from django.db import models
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
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True)
    debts = models.ManyToManyField(Subject, related_name='debt_students', blank=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Teacher(models.Model):
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    subjects = models.ManyToManyField(Subject, related_name='teachers', blank=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Lesson(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    start_date = models.DateField(default='2025-01-01')
    start_time = models.TimeField(default='09:00')
    DURATION_MINUTES = 80

    def __str__(self):
        return f"{self.subject} ({self.start_date})"


class LessonGroup(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='groups')
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE)
    students = models.ManyToManyField(Student, blank=True)
    group_number = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.lesson} — {self.group_number}-guruh"


class LessonSchedule(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='schedule')
    date = models.DateField()
    lesson_number = models.PositiveIntegerField()

    class Meta:
        ordering = ['date']

    def __str__(self):
        return f"{self.lesson} — {self.date}"