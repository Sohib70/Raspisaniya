from django.contrib import admin
from .models import (
    Student, Teacher, Subject, Group, Room,
    Course, CourseGroup, GroupSchedule,
    Attendance, Grade, DailyGrade
)

admin.site.register(Student)
admin.site.register(Teacher)
admin.site.register(Subject)
admin.site.register(Group)
admin.site.register(Room)
admin.site.register(Course)
admin.site.register(CourseGroup)
admin.site.register(GroupSchedule)
admin.site.register(Attendance)
admin.site.register(Grade)
admin.site.register(DailyGrade)