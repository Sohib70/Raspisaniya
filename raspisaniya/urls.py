from django.urls import path
from . import views

urlpatterns = [
    path('subject/create/', views.subject_create, name='subject_create'),
    path('subjects/', views.subject_list, name='subject_list'),
    path('subject/<int:pk>/update/', views.subject_update, name='subject_update'),
    path('subject/<int:pk>/delete/', views.subject_delete, name='subject_delete'),


    path('student/create/', views.student_create, name='student_create'),
    path('students/', views.student_list, name='student_list'),
    path('student/<int:pk>/update/', views.student_update, name='student_update'),
    path('student/<int:pk>/delete/', views.student_delete, name='student_delete'),


    path('teacher/create/', views.teacher_create, name='teacher_create'),
    path('teachers/', views.teacher_list, name='teacher_list'),
    path('teacher/<int:pk>/update/', views.teacher_update, name='teacher_update'),
    path('teacher/<int:pk>/delete/', views.teacher_delete, name='teacher_delete'),


    path('lesson/create/', views.lesson_create, name='lesson_create'),
    path('', views.lesson_list, name='lesson_list'),
    path('lesson/<int:pk>/update/', views.lesson_update, name='lesson_update'),
    path('lesson/<int:pk>/delete/', views.lesson_delete, name='lesson_delete'),
]
