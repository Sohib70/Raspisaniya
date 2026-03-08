from django.urls import path
from . import views
from .views import student_dashboard, teacher_dashboard,change_password

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('student/', student_dashboard, name='student_dashboard'),
    path('teacher/', teacher_dashboard, name='teacher_dashboard'),
    path('change-password/', change_password, name='change_password'),
]