from django.contrib import admin
from .models import Student, Teacher, Subject, Course, CourseGroup, GroupSchedule

admin.site.register(Student)
admin.site.register(Teacher)
admin.site.register(Subject)
admin.site.register(Course)
admin.site.register(CourseGroup)
admin.site.register(GroupSchedule)