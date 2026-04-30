from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('student/', views.student_dashboard, name='student_dashboard'),
    path('teacher/', views.teacher_dashboard, name='teacher_dashboard'),
    path('change-password/', views.change_password, name='change_password'),

    # O'qituvchi kabineti — yangi sahifalar
    path('teacher/group/<int:group_pk>/', views.teacher_group_detail, name='teacher_group_detail'),
    path('teacher/group/<int:group_pk>/attendance/', views.teacher_attendance_overview, name='teacher_attendance_overview'),
    path('teacher/group/<int:group_pk>/attendance/<int:sched_pk>/', views.teacher_attendance, name='teacher_attendance'),
    path('teacher/group/<int:group_pk>/grades/', views.teacher_grades, name='teacher_grades'),
]