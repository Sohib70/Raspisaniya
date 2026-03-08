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

@login_required
def change_password(request):
    if request.method == "POST":
        old_password = request.POST.get("old_password")
        new_password = request.POST.get("new_password")
        confirm_password = request.POST.get("confirm_password")

        if not request.user.check_password(old_password):
            messages.error(request, "Eski parol noto'g'ri")
        elif new_password != confirm_password:
            messages.error(request, "Yangi parollar mos kelmadi")
        elif len(new_password) < 4:
            messages.error(request, "Parol kamida 4 ta belgi bo'lishi kerak")
        else:
            request.user.set_password(new_password)
            request.user.save()
            messages.success(request, "Parol muvaffaqiyatli o'zgartirildi! Qayta kiring.")
            return redirect('login')

    return render(request, "accounts/change_password.html")


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

    week_str = request.GET.get('week')
    if week_str:
        try:
            week_start = dt_date.fromisoformat(week_str)
            week_start = week_start - timedelta(days=week_start.weekday())
        except:
            week_start = dt_date.today() - timedelta(days=dt_date.today().weekday())
    else:
        week_start = dt_date.today() - timedelta(days=dt_date.today().weekday())
    week_end = week_start + timedelta(days=5)

    PARA_TIMES_LIST = [
        ("08:30", "09:50"), ("10:00", "11:20"), ("12:00", "13:20"),
        ("13:30", "14:50"), ("15:00", "16:20"), ("16:30", "17:50"),
    ]
    WEEKDAY_LIST = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba"]

    my_groups = CourseGroup.objects.filter(
        students=student,
        is_scheduled=True,
    ).select_related('course__subject', 'teacher').prefetch_related('schedule')

    # Grid: {(weekday, para_idx): {'subject', 'teacher'}}
    grid = {}
    for grp in my_groups:
        for sched in grp.schedule.filter(date__gte=week_start, date__lte=week_end):
            wd = sched.date.weekday()
            if wd > 5:
                continue
            st = sched.start_time or grp.start_time
            if not st:
                continue
            start_str = st.strftime("%H:%M")
            para_idx = next((i for i, (s, e) in enumerate(PARA_TIMES_LIST) if s == start_str), None)
            if para_idx is None:
                continue
            key = (wd, para_idx)
            if key not in grid:
                grid[key] = {'subject': str(grp.course.subject), 'teacher': str(grp.teacher)}

    # Table data — haftalik jadval formatida
    table_data = []
    for day_idx, day_name in enumerate(WEEKDAY_LIST):
        for para_idx, (start, end) in enumerate(PARA_TIMES_LIST):
            key = (day_idx, para_idx)
            info = grid.get(key)
            table_data.append({
                'day': day_name,
                'time': f"{start} - {end}",
                'info': info,
                'show_day': para_idx == 0,
                'para_count': len(PARA_TIMES_LIST),
            })

    prev_week = (week_start - timedelta(weeks=1)).isoformat()
    next_week = (week_start + timedelta(weeks=1)).isoformat()

    return render(request, "accounts/student_dashboard.html", {
        "student": student,
        "my_groups": my_groups,
        "table_data": table_data,
        "week_start_str": week_start.strftime("%d.%m.%Y"),
        "week_end_str": week_end.strftime("%d.%m.%Y"),
        "prev_week": prev_week,
        "next_week": next_week,
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