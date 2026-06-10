from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('change-password/', views.change_password, name='change_password'),

    # Talaba kabineti
    path('student/', views.student_dashboard, name='student_dashboard'),

    # O'qituvchi kabineti
    path('teacher/', views.teacher_dashboard, name='teacher_dashboard'),
    path('teacher/group/<int:group_pk>/', views.teacher_group_detail, name='teacher_group_detail'),
    path('teacher/group/<int:group_pk>/attendance/', views.teacher_attendance_overview,
         name='teacher_attendance_overview'),

    # 1-Sahifa: Faqat kunlik Davomat olish sahifasi (Guruh orqali ham, Jadval orqali ham shunga keladi)
    path('teacher/group/<int:group_pk>/attendance/<int:sched_pk>/', views.teacher_attendance,
         name='teacher_attendance'),
    path('teacher/sched/<int:sched_pk>/attendance/', views.teacher_attendance, name='teacher_attendance_mark'),

    # Qaydnoma (Umumiy yakuniy baholar)
    path('teacher/group/<int:group_pk>/grades/', views.teacher_grades, name='teacher_grades'),
    path('teacher/group/<int:group_pk>/journal/', views.teacher_group_journal, name='teacher_group_journal'),

    # 2-Sahifa: Kunlik Baholash sahifasi (Alohida sahifa)
    path('teacher/sched/<int:sched_pk>/grade/', views.teacher_daily_grade, name='teacher_daily_grade'),
]