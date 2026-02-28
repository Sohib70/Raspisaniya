from django.urls import path
from . import views

urlpatterns = [
    # Lesson
    path('', views.lesson_list, name='lesson_list'),
    path('lesson/create/', views.lesson_create, name='lesson_create'),
    path('lesson/<int:pk>/schedule/', views.lesson_schedule, name='lesson_schedule'),
    path('lesson/<int:pk>/schedule/excel/', views.lesson_schedule_excel, name='lesson_schedule_excel'),
    path('lesson/<int:pk>/delete/', views.lesson_delete, name='lesson_delete'),
    path('group/<int:group_pk>/remove-student/<int:student_pk>/', views.remove_student_from_group, name='remove_student_from_group'),

    # Teacher
    path('teachers/', views.teacher_list, name='teacher_list'),
    path('teacher/create/', views.teacher_create, name='teacher_create'),
    path('teacher/<int:pk>/update/', views.teacher_update, name='teacher_update'),
    path('teacher/<int:pk>/delete/', views.teacher_delete, name='teacher_delete'),
    path('teacher/import/', views.teacher_import, name='teacher_import'),

    # Student
    path('students/', views.student_list, name='student_list'),
    path('student/create/', views.student_create, name='student_create'),
    path('student/<int:pk>/update/', views.student_update, name='student_update'),
    path('student/<int:pk>/delete/', views.student_delete, name='student_delete'),
    path('student/import/', views.import_students, name='import_students'),

    # Subject
    path('subjects/', views.subject_list, name='subject_list'),
    path('subject/create/', views.subject_create, name='subject_create'),
    path('subject/<int:pk>/update/', views.subject_update, name='subject_update'),
    path('subject/<int:pk>/delete/', views.subject_delete, name='subject_delete'),
]