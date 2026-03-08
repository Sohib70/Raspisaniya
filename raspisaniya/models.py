from django.db import models
from django.contrib.auth.models import User

LANGUAGE_CHOICES = [
    ('uz', "O'zbek"),
    ('ru', 'Rus'),
    ('qq', 'Qoraqalpoq'),
    ('en', 'Ingliz'),
]

WEEKDAY_CHOICES = [
    (0, 'Dushanba'), (1, 'Seshanba'), (2, 'Chorshanba'),
    (3, 'Payshanba'), (4, 'Juma'), (5, 'Shanba'),
]


class Subject(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Group(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Student(models.Model):
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True)
    student_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True)
    language = models.CharField(max_length=10, choices=LANGUAGE_CHOICES, default='uz')
    debts = models.ManyToManyField(Subject, related_name='debt_students', blank=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Teacher(models.Model):
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True)
    teacher_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    subjects = models.ManyToManyField(Subject, related_name='teachers', blank=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Course(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField()
    total_lessons = models.PositiveIntegerField()
    lessons_per_week = models.PositiveIntegerField()
    lesson_duration = models.PositiveIntegerField(default=80)

    def __str__(self):
        return f"{self.subject} ({self.start_date} — {self.end_date})"


class CourseGroup(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='groups')
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE)
    students = models.ManyToManyField(Student, blank=True)
    group_number = models.PositiveIntegerField(default=1)
    start_time = models.TimeField(null=True, blank=True)
    weekdays = models.JSONField(default=list, blank=True)
    language = models.CharField(max_length=10, choices=LANGUAGE_CHOICES, default='uz')
    is_scheduled = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.course.subject} — {self.group_number}-guruh"


class GroupSchedule(models.Model):
    group = models.ForeignKey(CourseGroup, on_delete=models.CASCADE, related_name='schedule')
    date = models.DateField()
    lesson_number = models.IntegerField(default=1)
    start_time = models.TimeField(null=True, blank=True)  # ← QO'SHING

    class Meta:
        ordering = ['date']

    def __str__(self):
        return f"{self.group} — {self.date}"