from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from raspisaniya.models import Student, Teacher, CourseGroup, GroupSchedule, Attendance, Grade, DailyGrade
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum
import json
from datetime import timedelta, date as dt_date


def login_view(request):
    if request.user.is_authenticated:
        if request.user.is_superuser:
            return redirect('lesson_list')
        elif hasattr(request.user, 'teacher'):
            return redirect('teacher_dashboard')
        elif hasattr(request.user, 'student'):
            return redirect('student_dashboard')

    if request.method == "POST":
        user_id = request.POST.get("user_id", "").strip()
        password = request.POST.get("password", "").strip()
        user = authenticate(request, username=user_id, password=password)

        if user is not None:
            is_teacher = hasattr(user, 'teacher')
            is_student = hasattr(user, 'student')
            if user.is_superuser or is_teacher or is_student:
                login(request, user)
                request.session.set_expiry(0)
                if user.is_superuser:
                    return redirect('lesson_list')
                elif is_teacher:
                    return redirect('teacher_dashboard')
                elif is_student:
                    return redirect('student_dashboard')
            else:
                messages.error(request, "Hisobingizga hech qanday rol biriktirilmagan.")
        else:
            messages.error(request, "Bunday foydalanuvchi topilmadi. ID yoki parolni qayta tekshiring.")

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
    except AttributeError:
        messages.error(request, "Siz o'quvchi emassiz")
        return redirect('login')

    week_str = request.GET.get('week')
    if week_str:
        try:
            week_start = dt_date.fromisoformat(week_str)
            week_start = week_start - timedelta(days=week_start.weekday())
        except ValueError:
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
        students=student, is_scheduled=True,
    ).select_related('course__subject', 'teacher', 'room').prefetch_related('schedule')

    grid = {}
    for grp in my_groups:
        week_schedules = [s for s in grp.schedule.all() if week_start <= s.date <= week_end]
        for sched in week_schedules:
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
                grid[key] = {
                    'subject': str(grp.course.subject),
                    'teacher': str(grp.teacher),
                    'teacher_name': f"{grp.teacher.first_name}",
                    'room': str(grp.room) if grp.room else '',
                }

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

    all_attendances = Attendance.objects.filter(
        student=student,
        schedule__group__in=my_groups
    ).select_related('schedule')

    att_data = {}
    for att in all_attendances:
        g_id = att.schedule.group_id
        if g_id not in att_data:
            att_data[g_id] = {'came_count': 0, 'missed_list': []}
        if att.is_present:
            att_data[g_id]['came_count'] += 1
        else:
            att_data[g_id]['missed_list'].append({
                'date': att.schedule.date,
                'lesson_number': att.schedule.lesson_number
            })

    grade_map = {g.course_group_id: g for g in Grade.objects.filter(student=student)}

    groups_data = []
    for grp in my_groups:
        total = grp.schedule.count()
        grp_att = att_data.get(grp.pk, {'came_count': 0, 'missed_list': []})
        came = grp_att['came_count']
        missed_list = sorted(grp_att['missed_list'], key=lambda x: x['date'])
        missed = len(missed_list)
        missed_percent = round(missed / total * 100) if total > 0 else 0
        is_blocked = missed_percent > 25 and not grp.teacher_can_edit

        groups_data.append({
            'group': grp,
            'total': total,
            'came': came,
            'missed': missed,
            'missed_list': missed_list,
            'missed_percent': missed_percent,
            'is_blocked': is_blocked,
            'grade': grade_map.get(grp.pk),
        })

    return render(request, "accounts/student_dashboard.html", {
        "student": student,
        "my_groups": my_groups,
        "table_data": table_data,
        "week_start_str": week_start.strftime("%d.%m.%Y"),
        "week_end_str": week_end.strftime("%d.%m.%Y"),
        "prev_week": prev_week,
        "next_week": next_week,
        "groups_data": groups_data,
    })


@login_required
def teacher_dashboard(request):
    try:
        teacher = request.user.teacher
    except Exception:
        messages.error(request, "Siz o'qituvchi emassiz")
        return redirect('login')

    today = dt_date.today()

    week_str = request.GET.get('week')
    if week_str:
        try:
            week_start = dt_date.fromisoformat(week_str)
            week_start = week_start - timedelta(days=week_start.weekday())
        except Exception:
            week_start = today - timedelta(days=today.weekday())
    else:
        week_start = today - timedelta(days=today.weekday())

    week_end = week_start + timedelta(days=5)

    PARA_TIMES_LIST = [
        ("08:30", "09:50"), ("10:00", "11:20"), ("12:00", "13:20"),
        ("13:30", "14:50"), ("15:00", "16:20"), ("16:30", "17:50"),
    ]
    WEEKDAY_LIST = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba"]

    my_groups = CourseGroup.objects.filter(
        teacher=teacher, is_scheduled=True,
    ).select_related('course__subject', 'room').prefetch_related('schedule', 'students')

    today_schedules = GroupSchedule.objects.filter(
        group__teacher=teacher,
        date=today,
    ).select_related('group__course__subject', 'group__room').prefetch_related('group__students').order_by('start_time')

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
            para_idx = next((i for i, (s, _) in enumerate(PARA_TIMES_LIST) if s == start_str), None)
            if para_idx is None:
                continue
            key = (wd, para_idx)
            if key not in grid:
                students_data = list(grp.students.values('first_name', 'last_name'))
                grid[key] = {
                    'subject': str(grp.course.subject),
                    'room': str(grp.room) if grp.room else '',
                    'sched_id': sched.pk,
                    'group_pk': grp.pk,
                    'students_json': json.dumps(students_data, ensure_ascii=False),
                    'students_count': len(students_data),
                    'group_number': grp.group_number if grp.group_number else 1,
                    'sched_date': sched.date.isoformat(),
                    'is_today': sched.date == today,
                }

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

    return render(request, "accounts/teacher_dashboard.html", {
        "teacher": teacher,
        "my_groups": my_groups,
        "today_schedules": today_schedules,
        "table_data": table_data,
        "week_start_str": week_start.strftime("%d.%m.%Y"),
        "week_end_str": week_end.strftime("%d.%m.%Y"),
        "prev_week": prev_week,
        "next_week": next_week,
        "today": today,
    })


@login_required
def teacher_group_journal(request, group_pk):
    group = get_object_or_404(CourseGroup, pk=group_pk)
    today = dt_date.today()

    is_admin = request.user.is_superuser or request.user.is_staff
    if not is_admin:
        try:
            teacher = request.user.teacher
        except Exception:
            return redirect('login')
        if group.teacher != teacher:
            messages.error(request, "Bu guruh sizniki emas.")
            return redirect('teacher_dashboard')

    students = list(group.students.all().order_by('first_name'))
    schedules = list(group.schedule.all().order_by('date'))
    total_lessons = group.course.total_lessons or 1
    max_ball = round(30 / total_lessons, 2)

    all_att = {
        (a.student_id, a.schedule_id): a.is_present
        for a in Attendance.objects.filter(schedule__group=group, student__in=students)
    }
    all_grades = {
        (g.student_id, g.schedule_id): g.score
        for g in DailyGrade.objects.filter(schedule__group=group, student__in=students)
    }

    rows = []
    for student in students:
        cells = []
        total_score = 0.0
        came = missed = 0
        for sched in schedules:
            att = all_att.get((student.pk, sched.pk))
            score = all_grades.get((student.pk, sched.pk))
            if att is True:
                came += 1
                total_score += score or 0
                cells.append({'att': 'present', 'score': score})
            elif att is False:
                missed += 1
                cells.append({'att': 'absent', 'score': None})
            else:
                cells.append({'att': 'none', 'score': None})

        rows.append({
            'student': student,
            'cells': cells,
            'came': came,
            'missed': missed,
            'total_score': round(total_score, 2),
        })

    return render(request, "accounts/teacher_group_journal.html", {
        'group': group,
        'schedules': schedules,
        'rows': rows,
        'max_ball': max_ball,
        'total_lessons': total_lessons,
        'today': today,
    })


def _student_attendance_info(student, group):
    total = group.schedule.count()
    came = Attendance.objects.filter(student=student, schedule__group=group, is_present=True).count()
    missed = Attendance.objects.filter(student=student, schedule__group=group, is_present=False).count()
    missed_percent = round(missed / total * 100) if total > 0 else 0
    is_blocked = missed_percent > 25 and not group.teacher_can_edit
    return {
        'came': came, 'missed': missed,
        'total': total, 'missed_percent': missed_percent, 'is_blocked': is_blocked,
    }


@login_required
def teacher_group_detail(request, group_pk):
    try:
        teacher = request.user.teacher
    except Exception:
        return redirect('login')

    group = get_object_or_404(CourseGroup, pk=group_pk)
    students = group.students.all().order_by('last_name', 'first_name')
    total_lessons = group.schedule.count()
    today = dt_date.today()

    marked_sched_ids = set(
        Attendance.objects.filter(schedule__group=group)
        .values_list('schedule_id', flat=True).distinct()
    )

    schedules_with_status = []
    for sched in group.schedule.all().order_by('date'):
        is_marked = sched.pk in marked_sched_ids
        is_today = sched.date == today
        is_past = sched.date < today and not is_marked
        if is_marked:
            css = 'btn-success'
        elif is_today:
            css = 'btn-warning'
        elif is_past:
            css = 'btn-danger'
        else:
            css = 'btn-outline-secondary'
        schedules_with_status.append({
            'sched': sched, 'css': css,
            'is_marked': is_marked, 'is_today': is_today, 'is_past': is_past,
        })

    grade_map = {g.student_id: g for g in Grade.objects.filter(course_group=group)}
    att_map = {}
    for a in Attendance.objects.filter(schedule__group=group):
        att_map.setdefault(a.student_id, {'came': 0, 'missed': 0})
        if a.is_present:
            att_map[a.student_id]['came'] += 1
        else:
            att_map[a.student_id]['missed'] += 1

    students_data = []
    for st in students:
        att = att_map.get(st.pk, {'came': 0, 'missed': 0})
        missed_percent = round(att['missed'] / total_lessons * 100) if total_lessons > 0 else 0
        is_blocked = missed_percent > 25 and not group.teacher_can_edit
        students_data.append({
            'student': st, 'came': att['came'], 'missed': att['missed'],
            'missed_percent': missed_percent, 'is_blocked': is_blocked,
            'grade': grade_map.get(st.pk),
        })

    return render(request, "accounts/teacher_group_detail.html", {
        "teacher": teacher, "group": group, "students_data": students_data,
        "schedules": schedules_with_status, "total_lessons": total_lessons,
    })


@login_required
def teacher_attendance(request, sched_pk, group_pk=None):
    try:
        teacher = request.user.teacher
    except Exception:
        return redirect('login')

    schedule = get_object_or_404(GroupSchedule, pk=sched_pk)

    if group_pk is None:
        group = schedule.group
    else:
        group = get_object_or_404(CourseGroup, pk=group_pk)

    students = group.students.all().order_by('last_name', 'first_name')
    today = dt_date.today()
    is_admin = request.user.is_superuser or request.user.is_staff

    if request.method == "POST":
        if not is_admin and schedule.date != today and not group.teacher_can_edit:
            messages.error(
                request,
                f"Faqat bugungi ({today.strftime('%d.%m.%Y')}) dars davomatini o'zgartirish mumkin!"
            )
            return redirect('teacher_attendance_overview', group_pk=group.pk)

        for student in students:
            is_present = request.POST.get(f"present_{student.pk}") == "1"
            Attendance.objects.update_or_create(
                student=student, schedule=schedule,
                defaults={'is_present': is_present}
            )
        messages.success(request, f"{schedule.date} sanasi uchun davomat saqlandi.")
        return redirect('teacher_attendance_overview', group_pk=group.pk)

    existing = {
        a.student_id: a.is_present
        for a in Attendance.objects.filter(schedule=schedule, student__in=students)
    }
    can_edit = is_admin or schedule.date == today or group.teacher_can_edit

    students_list = []
    for st in students:
        att_info = _student_attendance_info(st, group)
        students_list.append({
            'student': st,
            'is_present': existing.get(st.pk, True),
            'already_marked': st.pk in existing,
            'missed_percent': att_info['missed_percent'],
            'is_blocked': att_info['is_blocked'],
        })

    return render(request, "accounts/teacher_attendance.html", {
        "teacher": teacher, "group": group, "schedule": schedule,
        "students_list": students_list, "can_edit": can_edit,
        "is_today": schedule.date == today,
    })


@login_required
def teacher_attendance_overview(request, group_pk):
    try:
        teacher = request.user.teacher
    except Exception:
        return redirect('login')

    group = get_object_or_404(CourseGroup, pk=group_pk)
    students = list(group.students.all().order_by('last_name', 'first_name'))
    raw_schedules = list(group.schedule.all().order_by('date'))
    total_lessons = len(raw_schedules)
    today = dt_date.today()

    all_att = Attendance.objects.filter(schedule__group=group).values(
        'student_id', 'schedule_id', 'is_present'
    )
    att_map = {(a['student_id'], a['schedule_id']): a['is_present'] for a in all_att}

    marked_sched_ids = set(
        Attendance.objects.filter(schedule__group=group)
        .values_list('schedule_id', flat=True).distinct()
    )

    schedules = []
    for sched in raw_schedules:
        is_marked = sched.pk in marked_sched_ids
        is_today = sched.date == today
        is_past = sched.date < today and not is_marked
        if is_marked:
            sched.date_class = 'date-marked'
        elif is_today:
            sched.date_class = 'date-today'
        elif is_past:
            sched.date_class = 'date-missed'
        else:
            sched.date_class = 'date-future'
        sched.is_marked = is_marked
        sched.is_today = is_today
        sched.is_past = is_past
        schedules.append(sched)

    rows = []
    for st in students:
        cells = []
        came = missed = 0
        for sched in schedules:
            val = att_map.get((st.pk, sched.pk))
            if val is True:
                came += 1;
                cells.append('present')
            elif val is False:
                missed += 1;
                cells.append('absent')
            else:
                cells.append('none')
        missed_percent = round(missed / total_lessons * 100) if total_lessons > 0 else 0
        is_blocked = missed_percent > 25 and not group.teacher_can_edit
        rows.append({
            'student': st, 'cells': cells, 'came': came,
            'missed': missed, 'missed_percent': missed_percent,
            'is_blocked': is_blocked, 'total': total_lessons,
        })

    return render(request, "accounts/teacher_attendance_overview.html", {
        "teacher": teacher, "group": group, "students": students,
        "schedules": schedules, "rows": rows, "total_lessons": total_lessons,
    })


# 🌟 YANGLANGAN VA REALONLY QILINGAN JORIY BAHOLI QAYDNOMA VIEWS'I
@login_required
def teacher_grades(request, group_pk):
    try:
        teacher = request.user.teacher
    except Exception:
        return redirect('login')

    group = get_object_or_404(CourseGroup, pk=group_pk)
    students = group.students.all().order_by('last_name', 'first_name')
    total_lessons = group.schedule.count()

    # 🛠️ KUNLIK BAHOLARDAN JORIYNI HISOBLASH VA BAZAGA SINXRONIZATSIYA QILISH ICHKI FUNKSIYASI
    def sync_and_get_current_grade(student_obj):
        # DailyGrade dagi barcha 'score' larni yig'ib chiqamiz
        daily_sum = DailyGrade.objects.filter(
            student=student_obj,
            schedule__group=group
        ).aggregate(total=Sum('score'))['total'] or 0.0

        # Maksimal joriy baho 30 ballik tizimdan oshmasligi sharti
        current_grade = min(float(daily_sum), 30.0)

        # Grade modelida joriy (current) ustunini avtomat yangilaymiz
        Grade.objects.update_or_create(
            student=student_obj, course_group=group,
            defaults={'current': current_grade}
        )
        return current_grade

    if request.method == "POST":
        att_map_blocked = {}
        for st in students:
            missed = Attendance.objects.filter(
                student=st, schedule__group=group, is_present=False
            ).count()
            missed_percent = round(missed / total_lessons * 100) if total_lessons > 0 else 0
            att_map_blocked[st.pk] = missed_percent > 25 and not group.teacher_can_edit

        # 🔐 LIMITS ichidan 'current' olib tashlandi, chunki u endi qo'lda kiritilmaydi!
        LIMITS = {
            'midterm': {'min': 12, 'max': 20, 'name': 'Oraliq'},
            'final': {'min': 28, 'max': 50, 'name': 'Yakuniy'},
        }

        valid_grades_data = []
        has_error = False

        for student in students:
            if att_map_blocked.get(student.pk):
                continue
            student_grades = {}
            for field, bounds in LIMITS.items():
                raw_val = request.POST.get(f"{field}_{student.pk}", "").strip()
                if raw_val == "":
                    student_grades[field] = None
                    continue
                try:
                    val = float(raw_val)
                except (ValueError, TypeError):
                    messages.error(request, f"{student.first_name}ning {bounds['name']} bahosi son bo'lishi kerak!")
                    has_error = True
                    break
                if val < bounds['min'] or val > bounds['max']:
                    messages.error(
                        request,
                        f"{student.first_name}ning {bounds['name']} bahosi "
                        f"{bounds['min']}–{bounds['max']} oralig'ida bo'lishi shart! (Kiritildi: {val})"
                    )
                    has_error = True
                    break
                student_grades[field] = val
            if has_error:
                break

            # Bazadan joriy ballning eng yangi holatini hisoblab biriktirib qo'yamiz
            student_grades['current'] = sync_and_get_current_grade(student)
            valid_grades_data.append((student, student_grades))

        if has_error:
            return redirect('teacher_grades', group_pk=group_pk)

        # To'g'ri kelgan oraliq va yakuniy baholarni bazada saqlash
        for student, grades in valid_grades_data:
            Grade.objects.update_or_create(
                student=student, course_group=group,
                defaults={
                    'midterm': grades['midterm'],
                    'current': grades['current'],  # Avtomatik yig'ilgan joriy baho
                    'final': grades['final'],
                }
            )
        messages.success(request,
                         "Oraliq va Yakuniy baholar saqlandi. Joriy baholar esa darslardan avtomatik hisoblandi.")
        return redirect('teacher_grades', group_pk=group_pk)

    # === GET SO'ROVI (Sahifa yuklanganda) ===
    # Har bir talabaning joriy bahosini oxirgi kunlik darslar bo'yicha yangilab chiqamiz
    for student in students:
        sync_and_get_current_grade(student)

    # Yangilangan barcha baholarni olish
    grade_map = {g.student_id: g for g in Grade.objects.filter(course_group=group)}
    att_counts = {}
    for a in Attendance.objects.filter(schedule__group=group, is_present=False):
        att_counts[a.student_id] = att_counts.get(a.student_id, 0) + 1

    students_grades = []
    for st in students:
        missed = att_counts.get(st.pk, 0)
        missed_percent = round(missed / total_lessons * 100) if total_lessons > 0 else 0
        is_blocked = missed_percent > 25 and not group.teacher_can_edit
        students_grades.append({
            'student': st, 'grade': grade_map.get(st.pk),
            'missed_percent': missed_percent, 'is_blocked': is_blocked,
        })

    return render(request, "accounts/teacher_grades.html", {
        "teacher": teacher, "group": group,
        "students_grades": students_grades,
        "grade_blocked_by_attendance": not group.teacher_can_edit,
    })


@login_required
def teacher_attendance_mark(request, sched_pk):
    sched = get_object_or_404(GroupSchedule, pk=sched_pk)
    group = sched.group
    today = dt_date.today()

    is_admin = request.user.is_superuser or request.user.is_staff
    if not is_admin:
        try:
            teacher = request.user.teacher
        except Exception:
            return redirect('login')

    can_edit = is_admin or sched.date == today or group.teacher_can_edit
    if not can_edit:
        messages.error(request, f"{sched.date} uchun davomat belgilash yopiq. Admin ruxsat berishi kerak.")
        return redirect('teacher_attendance_overview', group_pk=group.pk)

    students = list(group.students.all().order_by('first_name'))
    att_map = {
        a.student_id: a
        for a in Attendance.objects.filter(schedule=sched, student__in=students)
    }
    att_saved = Attendance.objects.filter(schedule=sched).exists()

    if request.method == 'POST':
        with transaction.atomic():
            for student in students:
                is_present = request.POST.get(f'att_{student.pk}') == '1'
                att_obj = att_map.get(student.pk)
                if att_obj:
                    att_obj.is_present = is_present
                    att_obj.save(update_fields=['is_present'])
                else:
                    Attendance.objects.create(
                        student=student, schedule=sched, is_present=is_present
                    )
                if not is_present:
                    DailyGrade.objects.filter(student=student, schedule=sched).delete()

        messages.success(request, f"{sched.date} davomati saqlandi ✅")
        return redirect('teacher_daily_grade', sched_pk=sched_pk)

    students_data = []
    for student in students:
        att = att_map.get(student.pk)
        students_data.append({
            'student': student,
            'is_present': att.is_present if att else None,
        })

    return render(request, 'accounts/teacher_attendance_mark.html', {
        'sched': sched,
        'group': group,
        'students_data': students_data,
        'can_edit': can_edit,
        'is_today': sched.date == today,
        'att_saved': att_saved,
    })


@login_required
def teacher_daily_grade(request, sched_pk):
    sched = get_object_or_404(GroupSchedule, pk=sched_pk)
    group = sched.group
    today = dt_date.today()

    is_admin = request.user.is_superuser or request.user.is_staff
    if not is_admin:
        try:
            teacher = request.user.teacher
        except Exception:
            return redirect('login')

    can_edit = is_admin or sched.date == today or group.teacher_can_edit
    if not can_edit:
        messages.error(request, f"{sched.date} uchun baho qo'yish yopiq.")
        return redirect('teacher_attendance_overview', group_pk=group.pk)

    students = list(group.students.all().order_by('first_name'))
    total_lessons = group.course.total_lessons or 1
    max_ball = round(30 / total_lessons, 2)

    att_map = {
        a.student_id: a.is_present
        for a in Attendance.objects.filter(schedule=sched, student__in=students)
    }
    grade_map = {
        g.student_id: g
        for g in DailyGrade.objects.filter(schedule=sched, student__in=students)
    }
    present_count = sum(1 for v in att_map.values() if v)

    if request.method == 'POST':
        with transaction.atomic():
            for student in students:
                is_present = att_map.get(student.pk, False)
                if not is_present:
                    continue
                score_raw = request.POST.get(f'score_{student.pk}', '').strip()
                if score_raw == '':
                    continue
                try:
                    score = float(score_raw)
                    score = max(0.0, min(score, max_ball))
                except ValueError:
                    score = 0.0
                dg = grade_map.get(student.pk)
                if dg:
                    dg.score = score
                    dg.save(update_fields=['score'])
                else:
                    DailyGrade.objects.create(student=student, schedule=sched, score=score)

        messages.success(request, f"{sched.date} kunlik baholar saqlandi ✅")
        return redirect('teacher_attendance_overview', group_pk=group.pk)

    students_data = []
    for student in students:
        is_present = att_map.get(student.pk, False)
        dg = grade_map.get(student.pk)
        students_data.append({
            'student': student,
            'is_present': is_present,
            'score': dg.score if dg else '',
        })

    return render(request, 'accounts/teacher_daily_grade.html', {
        'sched': sched,
        'group': group,
        'students_data': students_data,
        'max_ball': max_ball,
        'total_lessons': total_lessons,
        'present_count': present_count,
        'can_edit': can_edit,
        'is_today': sched.date == today,
    })


