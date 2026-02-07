from django.urls import path
from . import views

urlpatterns = [
    path('subject/create/', views.subject_create, name='subject_create'),
    path('subject/', views.subject_list, name='subject_list'),  # bu qo‘shish juda muhim
    path('student/create/', views.student_create, name='student_create'),
    path('student/', views.student_list, name='student_list'),
    path('teacher/create/', views.teacher_create, name='teacher_create'),
    path('teacher/', views.teacher_list, name='teacher_list'),
    path('lesson/create/', views.lesson_create, name='lesson_create'),
    path('', views.lesson_list, name='lesson_list'),
]
