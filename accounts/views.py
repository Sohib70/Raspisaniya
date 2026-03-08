from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages
from raspisaniya.models import Student, Teacher,CourseGroup
from django.contrib.auth.decorators import login_required


def login_view(request):
    if request.user.is_authenticated:
        return redirect('lesson_list')

    if request.method == "POST":
        user_id = request.POST.get("user_id", "").strip()
        password = request.POST.get("password", "").strip()

        user = authenticate(request, username=user_id, password=password)
        if user:
            login(request, user)
            # Rolga qarab yo'naltirish
            if user.is_superuser:
                return redirect('lesson_list')
            try:
                teacher = user.teacher
                return redirect('lesson_list')
            except:
                pass
            try:
                student = user.student
                return redirect('student_dashboard')
            except:
                pass
            return redirect('lesson_list')
        else:
            messages.error(request, "ID yoki parol noto'g'ri")

    return render(request, "accounts/login.html")


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def student_dashboard(request):
    try:
        student = request.user.student
    except:
        messages.error(request, "Siz o'quvchi emassiz")
        return redirect('login')

    from datetime import datetime, timedelta, date as dt_date

    my_groups = CourseGroup.objects.filter(
        students=student,
        is_scheduled=True,
    ).select_related('course__subject', 'teacher').prefetch_related('schedule')

    PARA_TIMES_WEEKLY = [
        ("08:30", "09:50"), ("10:00", "11:20"), ("12:00", "13:20"),
        ("13:30", "14:50"), ("15:00", "16:20"), ("16:30", "17:50"),
    ]
    WEEKDAY_LIST = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba"]

    # Grid: {(weekday, para_idx): [entries]}
    grid = {}
    for grp in my_groups:
        if not grp.start_time:
            continue
        start_str = grp.start_time.strftime("%H:%M")
        para_idx = next((i for i, (s, e) in enumerate(PARA_TIMES_WEEKLY) if s == start_str), None)
        if para_idx is None:
            continue
        end_dt = datetime.combine(dt_date.today(), grp.start_time) + timedelta(minutes=80)
        end_str = end_dt.strftime("%H:%M")

        for sched in grp.schedule.all():
            wd = sched.date.weekday()
            if wd > 5:
                continue
            key = (wd, para_idx)
            if key not in grid:
                grid[key] = []
            if not any(x['subject'] == str(grp.course.subject) for x in grid[key]):
                grid[key].append({
                    'subject': str(grp.course.subject),
                    'teacher': str(grp.teacher),
                    'start': start_str,
                    'end': end_str,
                })

    # Har kun uchun nechta para bor — rowspan hisoblash
    table_data = []
    for day_idx, day_name in enumerate(WEEKDAY_LIST):
        day_rows = []
        for para_idx, (start, end) in enumerate(PARA_TIMES_WEEKLY):
            key = (day_idx, para_idx)
            entries = grid.get(key, [])
            if entries:
                day_rows.append({
                    'time': f"{start} - {end}",
                    'entries': entries,
                })

        if day_rows:
            for i, row in enumerate(day_rows):
                row['show_day'] = (i == 0)
                row['day'] = day_name
                row['day_rowspan'] = len(day_rows)
                table_data.append(row)

    return render(request, "accounts/student_dashboard.html", {
        "student": student,
        "my_groups": my_groups,
        "table_data": table_data,
    })


@login_required
def teacher_dashboard(request):
    try:
        teacher = request.user.teacher
    except:
        messages.error(request, "Siz o'qituvchi emassiz")
        return redirect('login')

    my_groups = CourseGroup.objects.filter(
        teacher=teacher,
        is_scheduled=True,
    ).select_related('course__subject').prefetch_related('schedule', 'students')

    return render(request, "accounts/teacher_dashboard.html", {
        "teacher": teacher,
        "my_groups": my_groups,
    })