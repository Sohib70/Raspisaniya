from django.urls import path
from . import views

urlpatterns = [
    # Course (Dars)
    path('lesson/list/', views.lesson_list, name='lesson_list'),
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
    path('student/<int:pk>/change-password/', views.admin_change_student_password, name='admin_change_student_password'),
    path('teacher/group/<int:group_id>/vedomost/download/', views.download_vedomost, name='download_vedomost'),


    # Subject
    path('subjects/', views.subject_list, name='subject_list'),
    path('subject/create/', views.subject_create, name='subject_create'),
    path('subject/<int:pk>/update/', views.subject_update, name='subject_update'),
    path('subject/<int:pk>/delete/', views.subject_delete, name='subject_delete'),
    path('subject/<int:pk>/students/', views.subject_students, name='subject_students'),
    path('subject/<int:pk>/students/excel/', views.subject_students_excel, name='subject_students_excel'),


    path('build-schedule/', views.build_schedule, name='build_schedule'),
    path('group/<int:group_pk>/schedule-debug/', views.group_schedule_debug, name='group_schedule_debug'),
    path('move-students/<int:from_group_pk>/<int:to_group_pk>/', views.move_students, name='move_students'),
    path('group/<int:pk>/delete-unscheduled/', views.delete_unscheduled_group, name='delete_unscheduled_group'),
    path('course/<int:pk>/update/', views.course_update, name='course_update'),

    path('weekly-schedule/', views.weekly_schedule_view, name='weekly_schedule'),
    path('weekly-schedule/excel/', views.weekly_schedule_excel, name='weekly_schedule_excel'),
    path('group/<int:group_pk>/add-student/', views.add_student_to_group, name='add_student_to_group'),
    path('group/<int:group_pk>/change-teacher/', views.change_teacher, name='change_teacher'),
    path('schedule/<int:sched_pk>/change-time/', views.change_lesson_time, name='change_lesson_time'),

    path('rooms/', views.room_list, name='room_list'),
    path('rooms/create/', views.room_create, name='room_create'),
    path('rooms/<int:pk>/delete/', views.room_delete, name='room_delete'),
    path('group/<int:group_pk>/assign-room/', views.assign_room, name='assign_room'),

    path('api/stats/', views.stats_api, name='stats_api'),
    path('change-lesson-time-ajax/<int:sched_pk>/', views.change_lesson_time_ajax, name='change_lesson_time_ajax'),
    path('toggle-teacher-edit/<int:group_pk>/', views.toggle_teacher_edit_permission, name='toggle_teacher_edit_permission'),

    path('reset-database/', views.reset_database_view, name='reset_database'),
    path('group/<int:group_pk>/grades/', views.admin_group_grades, name='admin_group_grades'),
    path('schedule/<int:sched_pk>/toggle-permission/', views.toggle_teacher_edit_permission, name='toggle_teacher_edit_permission'),
    path('group/<int:group_pk>/delete/', views.delete_course_group, name='delete_course_group'),
    path('move-one-student/', views.move_one_student, name='move_one_student'),
    path('export-database/', views.export_database_view, name='export_database'),  # Nusxa olish
    path('restore-database/', views.restore_database_view, name='restore_database'),  # Qayta tiklash

    # Statistikalar va API
    path('api/stats/', views.stats_api, name='stats_api'),
    path('change-lesson-time-ajax/<int:sched_pk>/', views.change_lesson_time_ajax, name='change_lesson_time_ajax'),
    path('toggle-teacher-edit/<int:group_pk>/', views.toggle_teacher_edit_permission, name='toggle_teacher_edit_permission'),
    path('teacher/<int:pk>/change-password/', views.admin_change_teacher_password, name='admin_change_teacher_password'),
    path('toggle-all-teacher-edit/', views.toggle_all_teacher_edit_permission, name='toggle_all_teacher_edit'),
    path('student-schedule/<int:student_pk>/', views.student_schedule_info, name='student_schedule_info'),
    path('sched-info/<int:sched_id>/', views.sched_info_ajax, name='sched_info_ajax'),

    path('teacher/group/<int:group_id>/vedomost/download/', views.download_vedomost, name='download_vedomost'),
    path('admin-password-reset/', views.admin_password_reset_request, name='admin_password_reset_request'),
    path('admin-password-verify/', views.admin_password_verify_and_change, name='admin_password_verify_and_change'),
    path('apply-teacher-suggestion/<int:group_pk>/<int:teacher_pk>/',
         views.apply_teacher_suggestion, name='apply_teacher_suggestion'),
    path('apply-swap-suggestion/',
         views.apply_swap_suggestion, name='apply_swap_suggestion'),
    path('teacher-capacity/', views.teacher_capacity_check, name='teacher_capacity_check'),
    path('assign-teachers-auto/', views.assign_teachers_auto, name='assign_teachers_auto'),
    path('course/<int:course_pk>/teacher-status/', views.teacher_assignment_status, name='teacher_assignment_status'),
    path('teacher/group/<int:group_pk>/attendance/excel/', views.export_attendance_only_excel,
         name='export_attendance_only_excel'),
    path('teacher/group/<int:group_pk>/grades/excel/', views.export_grades_only_excel, name='export_grades_only_excel'),
    path('course/<int:course_pk>/add-group/<str:language>/', views.add_group_and_redistribute, name='add_group_and_redistribute'),
]