from ._shared import *
from .schedule import form_course_groups

def get_lesson_dates(start_date, weekdays, total):
    result = []
    cur = start_date
    while len(result) < total:
        if cur.weekday() in weekdays:
            result.append(cur)
        cur += timedelta(days=1)
    return result


def get_expected_lessons_per_week(total_lessons):
    """
    `find_schedule_for_group` kurs turi (24/16/8 paralik) uchun HAR DOIM
    qat'iy shu haftalik dars (para) sonini qo'llaydi — bu son `total_lessons`
    dan kelib chiqadi, `lessons_per_week` maydonidagi qiymatdan qat'iy nazar:
      - 24 paralik (>=20)  -> 6 para/hafta (3 kun x 2 para)
      - 16 paralik (12-20) -> 4 para/hafta (2 kun x 2 para)
      - 8 paralik  (<12)   -> 2 para/hafta (1 kun x 2 para)

    Kurs yaratish/tahrirlash formalarida admin "Haftada necha marta"
    maydoniga BOSHQA son kiritib qo'ysa, tugash sanasi (`weeks_needed`)
    noto'g'ri hisoblanib, jadval bilan sana bir-biriga mos kelmay qolardi.
    Shu funksiya orqali kiritilgan qiymat tekshiriladi/tuzatiladi.
    """
    if total_lessons >= 20:
        return 6
    elif 12 <= total_lessons <= 20:
        return 4
    else:
        return 2


def apply_lesson_time_change(sched, new_date_val, new_time_val, apply_to_future=False):
    """
    Bitta darsning (sched) sana/vaqtini o'zgartiradi. `apply_to_future=True`
    bo'lsa, xuddi shu guruhning KEYINGI barcha haftalaridagi bir xil hafta
    kuni + bir xil eski vaqtdagi darslari ham AVTOMATIK, HAR BIR HAFTANING
    OʻZIGA XOS yangi hafta kuni + yangi vaqtiga ko'chiriladi — ya'ni agar
    dars Dushanbadan Seshanbaga ko'chirilsa, keyingi barcha haftalarda ham
    o'sha hafta ichidagi Seshanba kuniga o'tkaziladi (shu hafta ichidagi
    boshqa kunga emas).

    Bu — doimiy jadval tuzatishlari uchun (masalan "bu darsni doim
    Seshanba, soat 14:00 ga ko'chiramiz") mo'ljallangan. Agar faqat BITTA
    haftaga tegishli bir martalik istisno kerak bo'lsa (masalan bayram
    sababli), admin apply_to_future'ni yoqmasligi kerak.

    Har bir nishon dars alohida to'qnashuv tekshiruvidan o'tadi — band
    bo'lgan sanalar o'tkazib yuboriladi (o'zgartirilmaydi), qolganlari
    yangilanadi.

    Qaytaradi: (updated_count, skipped_dates_list)
    """
    old_time_val = sched.start_time
    old_weekday = sched.date.weekday()
    new_weekday = new_date_val.weekday()

    if apply_to_future:
        candidates = GroupSchedule.objects.filter(
            group=sched.group,
            date__gte=sched.date,
            start_time=old_time_val,
        )
        targets = [s for s in candidates if s.date.weekday() == old_weekday]
        if sched not in targets:
            targets.append(sched)
    else:
        targets = [sched]

    teacher_id = sched.group.teacher_id
    student_ids = list(sched.group.students.values_list('id', flat=True))

    updated = 0
    skipped_dates = []

    for t in targets:
        if t.pk == sched.pk:
            target_date = new_date_val
        else:
            # Shu darsning o'z haftasi Dushanbasini topib, o'sha hafta
            # ichidagi YANGI hafta-kuniga ko'chiramiz (haftani o'zgartirmaymiz,
            # faqat o'sha hafta ichidagi kunni/vaqtni moslashtiramiz).
            week_monday = t.date - timedelta(days=t.date.weekday())
            target_date = week_monday + timedelta(days=new_weekday)

        if teacher_id and GroupSchedule.objects.filter(
            date=target_date, start_time=new_time_val, group__teacher_id=teacher_id,
        ).exclude(pk=t.pk).exists():
            skipped_dates.append(target_date)
            continue

        if student_ids and GroupSchedule.objects.filter(
            date=target_date, start_time=new_time_val, group__students__id__in=student_ids,
        ).exclude(pk=t.pk).exists():
            skipped_dates.append(target_date)
            continue

        t.date = target_date
        t.start_time = new_time_val
        t.save(update_fields=['date', 'start_time'])
        updated += 1

    return updated, skipped_dates


def get_student_group_conflict(student, target_group, exclude_group=None):
    """
    Talabaning `target_group`ga qo'shilishi, uning boshqa guruhlardagi mavjud
    dars vaqtlari bilan to'qnashib qolmasligini tekshiradi. Agar target_group
    hali jadvallanmagan bo'lsa (is_scheduled=False), tekshirishning hojati
    yo'q — u holda hozircha vaqt yo'q. To'qnashuv topilsa (sana, vaqt) juftini,
    aks holda None qaytaradi.
    """
    if not target_group.is_scheduled:
        return None
    target_times = set(
        GroupSchedule.objects.filter(group=target_group).values_list('date', 'start_time')
    )
    if not target_times:
        return None
    busy_qs = GroupSchedule.objects.filter(group__students=student)
    if exclude_group is not None:
        busy_qs = busy_qs.exclude(group=exclude_group)
    student_busy_times = set(busy_qs.values_list('date', 'start_time'))
    conflict_times = target_times & student_busy_times
    if conflict_times:
        return sorted(conflict_times)[0]
    return None


def get_weekly_schedule_data(week_start=None):
    today = dt_date.today()
    if week_start is None:
        week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=5)

    groups = CourseGroup.objects.filter(
        is_scheduled=True
    ).select_related('course__subject', 'teacher').prefetch_related('schedule')

    grid_lists = defaultdict(list)

    for grp in groups:
        subject_name = str(grp.course.subject)
        # ── teacher None bo'lishi mumkin ──
        if grp.teacher:
            teacher_name = f"{grp.teacher.first_name} {grp.teacher.last_name}"
        else:
            teacher_name = "O'qituvchi biriktirilmagan"

        for sched in grp.schedule.filter(date__gte=week_start, date__lte=week_end):
            weekday = sched.date.weekday()
            if weekday > 5:
                continue
            st = sched.start_time or grp.start_time
            if not st:
                continue
            start_str = st.strftime("%H:%M")
            para_idx = next(
                (i for i, (s, e) in enumerate(PARA_TIMES_WEEKLY) if s == start_str), None
            )
            if para_idx is None:
                continue

            grid_lists[(weekday, para_idx)].append({
                'subject'     : subject_name,
                'teacher'     : teacher_name,
                'room'        : str(grp.room) if grp.room else '',
                'sched_id'    : sched.pk,
                'group_number': grp.group_number,
            })

    max_cols = max((len(v) for v in grid_lists.values()), default=0)

    grid = {}
    for (weekday, para_idx), items in grid_lists.items():
        for col, item in enumerate(items, 1):
            grid[(weekday, para_idx, col)] = item

    return {
        'max_group' : max_cols,
        'grid'      : grid,
        'week_start': week_start,
        'week_end'  : week_end,
    }


# ─────────────────────────────────────────
# LESSON LIST
# ─────────────────────────────────────────
@login_required
def lesson_list(request):
    if is_student(request.user):
        return redirect('student_dashboard')
    if is_teacher(request.user) and not is_admin(request.user):
        return redirect('teacher_dashboard')

    q = request.GET.get('q', '').strip()
    courses = Course.objects.select_related('subject').prefetch_related('groups').all()
    if q:
        courses = courses.filter(subject__name__icontains=q)

    courses_data = []
    for course in courses:
        total = course.groups.count()
        scheduled = course.groups.filter(is_scheduled=True).count()

        # Kurs guruhlari ichida o'qituvchisi biriktirilmagan guruh bormi?
        # Agar kamida 1 ta o'qituvchisiz guruh bo'lsa True, hammasida bo'lsa False qaytaradi
        has_unassigned = course.groups.filter(teacher__isnull=True).exists()

        courses_data.append({
            'course': course,
            'total_groups': total,
            'scheduled_groups': scheduled,
            'has_unassigned_teachers': has_unassigned,  # HTML shablonimiz uchun yangi flag
        })

    return render(request, "raspisaniya/lesson_list.html", {"courses_data": courses_data, "q": q})


@login_required
def lesson_create(request):
    # ── STEP 1 ──
    if request.method == "GET":
        all_subjects = Subject.objects.all()
        subjects_data = []
        for subj in all_subjects:
            count = Student.objects.filter(debts=subj).count()
            if count >= 10:
                subjects_data.append({'subject': subj, 'student_count': count})
        return render(request, "raspisaniya/lesson_create.html", {
            "step": 1,
            "subjects_data": subjects_data,
        })

    # ── STEP 2 ──
    if request.method == "POST" and request.POST.get("step") == "2":
        subject_id = request.POST.get("subject")
        subject = get_object_or_404(Subject, id=subject_id)

        start_date_raw = request.POST.get("start_date")
        total_lessons = request.POST.get("total_lessons")
        lessons_per_week = request.POST.get("lessons_per_week")
        include_saturday = request.POST.get("include_saturday", "0")

        if not all([start_date_raw, total_lessons, lessons_per_week]):
            messages.error(request, "Barcha maydonlarni to'ldiring")
            return redirect("lesson_create")

        total_lessons = int(total_lessons)
        lessons_per_week = int(lessons_per_week)
        start_date = parse_date(start_date_raw)

        # ── YANGI TEKSHIRUV: jadval tuzuvchi algoritm (find_schedule_for_group)
        # kurs turiga (24/16/8 paralik) qarab HAR DOIM qat'iy belgilangan
        # haftalik dars sonini qo'llaydi. Agar admin "Haftada necha marta"ga
        # boshqa son kiritgan bo'lsa, tugash sanasi noto'g'ri hisoblanib
        # qolardi — shuning uchun bu yerda avtomatik to'g'ri qiymatga
        # tuzatib, adminga ogohlantirish beramiz ──
        expected_per_week = get_expected_lessons_per_week(total_lessons)
        if lessons_per_week != expected_per_week:
            messages.warning(
                request,
                f"⚠ Diqqat: {total_lessons} paralik kurs uchun tizim haftada "
                f"faqat {expected_per_week} para joylashtira oladi (siz {lessons_per_week} "
                f"kiritgan edingiz). Tugash sanasi shunga qarab to'g'rilandi."
            )
            lessons_per_week = expected_per_week

        weeks_needed = math.ceil(total_lessons / lessons_per_week)
        end_date = start_date + timedelta(weeks=weeks_needed)
        end_date_raw = end_date.strftime("%Y-%m-%d")

        all_students = list(Student.objects.filter(debts=subject).distinct())
        if not all_students:
            messages.error(request, "Bu fandan yiqilgan o'quvchi yo'q")
            return redirect("lesson_create")

        # ── Tilga qarab ajratamiz ──
        students_by_lang = defaultdict(list)
        for st in all_students:
            students_by_lang[st.language].append(st)

        all_groups = []
        skipped_msgs = []
        group_index = 0

        include_saturday_bool = include_saturday == "1"

        # ── YANGI: talabalar endi RO'YXAT TARTIBIDA emas, balki:
        #   1) ularning boshqa fanlardagi mavjud band vaqtlariga mos ravishda,
        #      umumiy bo'sh vaqt topiladigan tarzda (smart_group_students),
        #   2) kam sonli tillar (masalan rus, agar 10 tadan kam bo'lsa) asosiy
        #      tilga QO'SHIB, lekin albatta BITTA guruhda birga qoldirilgan
        #      holda (form_course_groups),
        #   3) imkon qadar bir xil yo'nalishdagi (masalan "F" bilan
        #      boshlanadigan akademik guruh) talabalar bir joyga yig'ilgan
        #      holda guruhlanadi.
        # Bu — guruh yaratilgan zahoti kamida bitta bo'sh umumiy slot
        # mavjudligini kafolatlaydi va darslar bir vaqtga tushib qolish
        # muammosini ildizidan hal qiladi. ──
        formed_groups = form_course_groups(
            students_by_lang, total_lessons, start_date, include_saturday_bool
        )

        for gdata in formed_groups:
            g = gdata['students']
            lang_name = gdata['lang_name']
            is_small = len(g) < 10
            if is_small:
                skipped_msgs.append(
                    f"{lang_name}: {len(g)} ta o'quvchi "
                    f"(10 tadan kam, guruh baribir shakllantirildi)"
                )
            all_groups.append({
                'index': group_index,
                'lang': gdata['lang'],
                'lang_name': lang_name,
                'students': g,
                'is_small': is_small,
            })
            group_index += 1

        if not all_groups:
            messages.error(request, "Bu fandan o'quvchi yo'q")
            return redirect("lesson_create")

        groups_count = len(all_groups)

        # ── O'qituvchi bu yerda YO'Q ──
        return render(request, "raspisaniya/lesson_create.html", {
            "step": 2,
            "subject": subject,
            "all_groups": all_groups,
            "groups_count": groups_count,
            "start_date": start_date_raw,
            "end_date": end_date_raw,
            "total_lessons": total_lessons,
            "lessons_per_week": lessons_per_week,
            "skipped_langs": skipped_msgs,
            "all_students": all_students,
            "include_saturday": include_saturday,
        })

    # ── STEP 3 ──
    if request.method == "POST" and request.POST.get("step") == "3":
        subject_id = request.POST.get("subject_id")
        subject = get_object_or_404(Subject, id=subject_id)

        start_date_raw = request.POST.get("start_date")
        end_date_raw = request.POST.get("end_date")
        total_lessons = int(request.POST.get("total_lessons"))
        lessons_per_week = int(request.POST.get("lessons_per_week"))
        groups_count = int(request.POST.get("groups_count", 1))
        include_saturday = request.POST.get("include_saturday", "0") == "1"

        # ── Ehtiyot chorasi: STEP 2 da to'g'rilangan bo'lsa ham, formani
        # kimdir qo'lda o'zgartirib yubormasligi uchun bu yerda YANA bir bor
        # tekshiramiz ──
        lessons_per_week = get_expected_lessons_per_week(total_lessons)

        start_date = parse_date(start_date_raw)
        end_date = parse_date(end_date_raw)

        # ── Indekslarni students_ orqali aniqlaymiz
        #    (teacher_ endi yo'q) ──────────────────
        all_indices = []
        for key in request.POST.keys():
            if key.startswith("students_"):
                try:
                    all_indices.append(int(key.split("_", 1)[1]))
                except ValueError:
                    pass
        all_indices = sorted(set(all_indices))

        with transaction.atomic():
            course = Course.objects.create(
                subject=subject,
                start_date=start_date,
                end_date=end_date,
                total_lessons=total_lessons,
                lessons_per_week=lessons_per_week,
                lesson_duration=80,
                include_saturday=include_saturday,
            )

            group_number = 1
            for i in all_indices:
                selected_ids = request.POST.getlist(f"students_{i}")
                if not selected_ids:
                    continue
                selected_students = list(
                    Student.objects.filter(id__in=selected_ids)
                )
                if not selected_students:
                    continue

                lang = request.POST.get(
                    f"lang_{i}", selected_students[0].language
                )

                # ── O'qituvchisiz guruh — keyinroq biriktiriladi ──
                # MUHIM: 10 tadan kam bo'lsa ham guruh HAR DOIM saqlanadi
                # ("Ruxsat berish" talabi olib tashlandi — eski xatti-harakatga qaytarildi)
                cgroup = CourseGroup.objects.create(
                    course=course,
                    teacher=None,
                    group_number=group_number,
                    start_time=None,
                    weekdays=[],
                    language=lang,
                    is_scheduled=False,
                )
                cgroup.students.set(selected_students)
                sync_group_language(cgroup)

                for st in selected_students:
                    st.debts.remove(subject)

                group_number += 1

        messages.success(
            request,
            "Kurs yaratildi! Endi har bir guruhga o'qituvchi "
            "biriktiring, so'ng 'Jadval tuzish' tugmasini bosing."
        )
        return redirect("lesson_list")


# ─────────────────────────────────────────
# LESSON SCHEDULE
# ─────────────────────────────────────────
@login_required
def lesson_schedule(request, pk):
    course = get_object_or_404(Course, pk=pk)
    # Guruhlarni va ularning jadvallarini yuklab olamiz
    groups = course.groups.prefetch_related('students', 'schedule').select_related('teacher')
    duration = timedelta(minutes=80)

    # 1. Shu kursdagi barcha guruhlarda o'qiyotgan talabalar ID lari (takrorlanmaslik uchun)
    all_group_student_ids = set()
    for grp in groups:
        for s in grp.students.all():
            all_group_student_ids.add(s.id)

    # Shu fandan qarzdor va hali hech qaysi guruhga qo'shilmagan talabalar
    addable_students = Student.objects.filter(
        debts=course.subject
    ).exclude(
        id__in=all_group_student_ids
    )

    # 2. Shu fanga ixtisoslashgan barcha o'qituvchilar ro'yxati (Dropdown uchun asos)
    course_teachers = Teacher.objects.filter(subjects=course.subject).order_by('first_name')

    # Hafta kunlari nomlari lug'ati (agar loyihangizda yuqorida bo'lsa o'chirib qo'yishingiz mumkin)
    WEEKDAY_NAMES = {0: 'Dushanba', 1: 'Seshanba', 2: 'Chorshanba', 3: 'Payshanba', 4: 'Juma', 5: 'Shanba'}

    groups_data = []
    for grp in groups:
        # Guruhning dars vaqtlari ro'yxatini shakllantiramiz
        group_schedules = grp.schedule.exclude(start_time__isnull=True).values('date', 'start_time')

        # ── O'QITUVCHILARNING BANDLIGINI TEKSHIRISH (Joriy guruh uchun) ──
        teachers_with_status = []
        for teacher in course_teachers:
            is_busy = False

            # Agar o'qituvchi joriy guruhning o'z o'qituvchisi bo'lsa, uni band deb ko'rsatmaymiz
            if grp.teacher == teacher:
                is_busy = False
            else:
                # O'qituvchining dars vaqtlarini joriy guruhniki bilan solishtiramiz
                for sched in group_schedules:
                    clash_exists = GroupSchedule.objects.filter(
                        date=sched['date'],
                        start_time=sched['start_time'],
                        group__teacher=teacher
                    ).exists()

                    if clash_exists:
                        is_busy = True
                        break  # Bitta to'qnashuv topilsa, ushbu o'qituvchi uchun tekshiruvni to'xtatamiz

            teachers_with_status.append({
                'id': teacher.id,
                'full_name': f"{teacher.first_name} {teacher.last_name}",
                'is_busy': is_busy
            })

        # Jadvallarni formatlash
        schedule_list = []
        for s in grp.schedule.all().order_by('lesson_number'):
            st = s.start_time or grp.start_time
            if st:
                end_t = (datetime.datetime.combine(s.date, st) + duration).time()
                start_str = st.strftime("%H:%M")
                end_str = end_t.strftime("%H:%M")
            else:
                start_str = "—"
                end_str = "—"

            schedule_list.append({
                "sched": s,
                "weekday": WEEKDAY_NAMES.get(s.date.weekday(), "") if st else "",
                "start_time": start_str,
                "end_time": end_str,
            })

        # Har bir guruh uchun unga xos bo'lgan o'qituvchilar ro'yxatini (band/bo'sh statusi bilan) qo'shamiz
        groups_data.append({
            "group": grp,
            "schedule_list": schedule_list,
            "addable_students": addable_students,
            "teachers_list": teachers_with_status,  # <--- Yangi qo'shilgan qism
        })

    return render(request, "raspisaniya/lesson_schedule.html", {
        "course": course,
        "groups_data": groups_data,
        "rooms": Room.objects.all().order_by('name'),
    })


@login_required
def add_student_to_group(request, group_pk):
    group = get_object_or_404(CourseGroup, pk=group_pk)
    if request.method == "POST":
        student_id = request.POST.get("student_id")
        if student_id:
            student = get_object_or_404(Student, pk=student_id)

            # ── YANGI TEKSHIRUV: agar guruh allaqachon jadvallangan bo'lsa,
            # talabaning boshqa guruhlardagi dars vaqtlari bilan to'qnashib
            # qolmasligini tekshiramiz — aks holda talaba bir vaqtda ikki
            # joyga tushib qolishi mumkin edi ──
            conflict = get_student_group_conflict(student, group)
            if conflict:
                conflict_date, conflict_time = conflict
                messages.error(
                    request,
                    f"❌ {student} allaqachon {conflict_date.strftime('%d.%m.%Y')} kuni "
                    f"{conflict_time.strftime('%H:%M')} da boshqa darsga band — guruhga qo'shilmadi."
                )
                return redirect("lesson_schedule", pk=group.course.pk)

            group.students.add(student)
            sync_group_language(group)
            student.debts.remove(group.course.subject)
            messages.success(request, f"{student} guruhga qo'shildi.")
    return redirect("lesson_schedule", pk=group.course.pk)


@login_required
def lesson_schedule_excel(request, pk):
    course = get_object_or_404(Course, pk=pk)
    duration = timedelta(minutes=80)

    wb = Workbook()
    first = True
    for grp in course.groups.prefetch_related('students', 'schedule').select_related('teacher'):
        if first:
            ws = wb.active
            ws.title = f"{grp.group_number}-guruh"
            first = False
        else:
            ws = wb.create_sheet(title=f"{grp.group_number}-guruh")

        ws.append(["#", "Sana", "Hafta kuni", "Boshlanish", "Tugash", "O'qituvchi"])
        for s in grp.schedule.all():
            if grp.start_time:
                end_t = (datetime.datetime.combine(s.date, grp.start_time) + duration).time()
                ws.append([
                    s.lesson_number,
                    s.date.strftime("%d.%m.%Y"),
                    WEEKDAYS.get(s.date.weekday(), ""),
                    grp.start_time.strftime("%H:%M"),
                    end_t.strftime("%H:%M"),
                    str(grp.teacher),
                ])

        ws2 = wb.create_sheet(title=f"{grp.group_number}-guruh talabalar")
        ws2.append(["#", "O'quvchi", "O'qituvchi"])
        for idx, st in enumerate(grp.students.all(), 1):
            ws2.append([idx, str(st), str(grp.teacher)])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="jadval_{course.pk}.xlsx"'
    wb.save(response)
    return response


@login_required
def change_lesson_time(request, sched_pk):
    sched = get_object_or_404(GroupSchedule, pk=sched_pk)
    if request.method == "POST":
        new_time = request.POST.get("start_time")
        new_date = request.POST.get("date")
        # ── YANGI: "apply_to_future" checkbox — agar belgilangan bo'lsa va
        # faqat vaqt o'zgargan bo'lsa (sana o'sha-o'sha), shu haftadagi
        # o'zgarish KEYINGI barcha haftalarga ham qo'llaniladi ──
        apply_to_future = request.POST.get("apply_to_future") in ("1", "true", "on")

        new_date_val = parse_date(new_date) if new_date else sched.date
        if new_time:
            h, m = map(int, new_time.split(":"))
            new_time_val = dtime(h, m)
        else:
            new_time_val = sched.start_time

        updated, skipped_dates = apply_lesson_time_change(
            sched, new_date_val, new_time_val, apply_to_future=apply_to_future
        )

        if updated:
            if apply_to_future and updated > 1:
                messages.success(
                    request,
                    f"✅ {updated} ta hafta uchun dars vaqti {new_time} ga o'zgartirildi "
                    f"(bu va keyingi barcha haftalar)."
                )
            else:
                messages.success(request, f"{new_date_val} dars vaqti o'zgartirildi")
        if skipped_dates:
            dates_str = ", ".join(d.strftime('%d.%m.%Y') for d in skipped_dates[:5])
            extra = len(skipped_dates) - 5
            if extra > 0:
                dates_str += f" va yana {extra} ta"
            messages.warning(
                request,
                f"⚠ Quyidagi sanalarda o'qituvchi yoki talabalar band bo'lgani uchun "
                f"o'zgartirilmadi: {dates_str}"
            )
        if not updated and not skipped_dates:
            messages.error(request, "Dars topilmadi yoki o'zgartirish uchun hech narsa yo'q.")
    return redirect("lesson_schedule", pk=sched.group.course.pk)


@login_required
def change_teacher(request, group_pk):
    group = get_object_or_404(CourseGroup, pk=group_pk)
    if request.method != "POST":
        return redirect("lesson_schedule", pk=group.course.pk)

    teacher_id = request.POST.get("teacher_id", "").strip()
    if not teacher_id:
        messages.error(request, "O'qituvchi tanlanmadi")
        return redirect("lesson_schedule", pk=group.course.pk)

    teacher = get_object_or_404(Teacher, pk=teacher_id)

    # ── Vaqt to'qnashuvi tekshiruvi ──────────────────────────────
    group_schedules = group.schedule.values('date', 'start_time')

    conflicts = []
    for sched in group_schedules:
        if not sched['start_time']:
            continue
        clash = GroupSchedule.objects.filter(
            date=sched['date'],
            start_time=sched['start_time'],
            group__teacher=teacher,
        ).exclude(group=group).select_related(
            'group__course__subject'
        ).first()

        if clash:
            conflicts.append(
                f"{sched['date'].strftime('%d.%m.%Y')} "
                f"{sched['start_time'].strftime('%H:%M')} — "
                f"{clash.group.course.subject} "
                f"({clash.group.group_number}-guruh)"
            )

    if conflicts:
        shown = conflicts[:3]
        extra = len(conflicts) - 3
        msg   = "; ".join(shown)
        if extra > 0:
            msg += f" va yana {extra} ta"
        messages.error(
            request,
            f"❌ {teacher.first_name} o'qituvchisi band: {msg}. "
            f"Boshqa o'qituvchi tanlang."
        )
        return redirect("lesson_schedule", pk=group.course.pk)

    # ── To'qnashuv yo'q — saqlash ────────────────────────────────
    old_teacher = group.teacher
    group.teacher = teacher
    group.save(update_fields=['teacher'])

    messages.success(
        request,
        f"✅ {group.group_number}-guruh o'qituvchisi "
        f"{'↳ ' + old_teacher.first_name + ' → ' if old_teacher else ''}"
        f"{teacher.first_name} ga o'zgartirildi."
    )
    return redirect("lesson_schedule", pk=group.course.pk)


# ─────────────────────────────────────────
# ✅ O'ZGARISH 8: lesson_delete — o'chirilganda talabalar
#    qaytib subject.debts ga qo'shiladi
# ─────────────────────────────────────────
@login_required
def lesson_delete(request, pk):
    lesson = get_object_or_404(Course, pk=pk)
    if request.method == "POST":
        subject = lesson.subject
        # Kursga biriktirilgan barcha guruhlar va ulardagi talabalarni qaytarish
        for group in lesson.groups.prefetch_related('students').all():
            for student in group.students.all():
                student.debts.add(subject)
        lesson.delete()
        messages.success(request, "Dars o'chirildi va talabalar qayta ro'yxatga qaytarildi")
        return redirect("lesson_list")
    return render(request, "raspisaniya/lesson_delete.html", {"lesson": lesson, "course": lesson})


@staff_member_required
def admin_group_grades(request, group_pk):
    """Admin: guruh talabalarining baholari va davomati."""
    from raspisaniya.models import Grade, Attendance
    group = get_object_or_404(CourseGroup, pk=group_pk)
    students = group.students.all().order_by('last_name', 'first_name')
    schedules = list(group.schedule.all().order_by('date'))
    total_lessons = len(schedules)

    grade_map = {g.student_id: g for g in Grade.objects.filter(course_group=group)}
    all_att = Attendance.objects.filter(schedule__group=group).values('student_id', 'schedule_id', 'is_present')
    att_map = {(a['student_id'], a['schedule_id']): a['is_present'] for a in all_att}

    rows = []
    for st in students:
        cells = []
        came = missed = 0
        for sched in schedules:
            val = att_map.get((st.pk, sched.pk))
            if val is True:
                came += 1
                cells.append('present')
            elif val is False:
                missed += 1
                cells.append('absent')
            else:
                cells.append('none')
        missed_percent = round(missed / total_lessons * 100) if total_lessons > 0 else 0
        is_blocked = missed_percent > 25 and not group.teacher_can_edit
        grade = grade_map.get(st.pk)
        total_grade = None
        if grade:
            vals = [v for v in [grade.midterm, grade.current, grade.final] if v is not None]
            total_grade = round(sum(vals), 1) if vals else None
        rows.append({
            'student': st,
            'cells': cells,
            'came': came,
            'missed': missed,
            'missed_percent': missed_percent,
            'is_blocked': is_blocked,
            'grade': grade,
            'total': total_grade,
        })

    return render(request, "raspisaniya/admin_group_grades.html", {
        "group": group,
        "schedules": schedules,
        "rows": rows,
        "total_lessons": total_lessons,
    })


@login_required
def move_one_student(request):
    """Bitta talabani boshqa guruhga ko'chirish."""
    if request.method == "POST":
        student_pk   = request.POST.get('student_pk')
        from_group_pk = request.POST.get('from_group_pk')
        to_group_pk  = request.POST.get('to_group_pk')

        try:
            student    = Student.objects.get(pk=student_pk)
            from_group = CourseGroup.objects.get(pk=from_group_pk)
            to_group   = CourseGroup.objects.get(pk=to_group_pk)

            # ── YANGI TEKSHIRUV: talabaning to_group vaqtlari bilan
            # (from_group'dagi darslardan tashqari) to'qnashuvi bo'lmasin ──
            conflict = get_student_group_conflict(student, to_group, exclude_group=from_group)
            if conflict:
                conflict_date, conflict_time = conflict
                messages.error(
                    request,
                    f"❌ {student.first_name} {conflict_date.strftime('%d.%m.%Y')} kuni "
                    f"{conflict_time.strftime('%H:%M')} da band — {to_group.group_number}-guruhga ko'chirilmadi."
                )
                return redirect('build_schedule')

            from_group.students.remove(student)
            to_group.students.add(student)
            sync_group_language(from_group)
            sync_group_language(to_group)
            messages.success(request, f"{student.first_name} → {to_group.group_number}-guruhga ko'chirildi.")
        except Exception as e:
            messages.error(request, f"Xato: {e}")

    return redirect('build_schedule')


@login_required
@transaction.atomic
def add_group_and_redistribute(request, course_pk, language):
    """
    Yangi bo'sh guruh qo'shish funksiyasi.
    Eski guruhlar, ularning o'qituvchilari, talabalari va
    mavjud jadvallariga umuman ta'sir qilmaydi.
    """
    if request.method != "POST":
        return redirect('lesson_schedule', pk=course_pk)

    course = get_object_or_404(Course, pk=course_pk)

    # Mavjud guruhlar ichida eng katta guruh raqamini topamiz
    existing_groups = CourseGroup.objects.filter(course=course).order_by('-group_number')
    max_num = existing_groups.first().group_number if existing_groups.exists() else 0

    # Yangi bo'sh guruh yaratamiz
    new_group = CourseGroup.objects.create(
        course=course,
        teacher=None,  # O'qituvchi yo'q
        group_number=max_num + 1,  # Keyingi raqam
        language=language,  # Tanlangan til
        is_scheduled=False,  # Jadval hali tuzilmagan
        start_time=None,
        weekdays=[]
    )

    messages.success(
        request,
        f"✅ {max_num + 1}-guruh muvaffaqiyatli qo'shildi. "
        f"Endi talabalarni boshqa guruhlardan o'chirib, bu guruhga qo'shishingiz mumkin."
    )

    return redirect('lesson_schedule', pk=course.pk)


@login_required
def delete_course_group(request, group_pk):
    """Guruhni o'chirish — talabalar debts ga qaytadi."""
    group = get_object_or_404(CourseGroup, pk=group_pk)
    course_pk = group.course.pk
    if request.method == "POST":
        subject = group.course.subject
        for student in group.students.all():
            student.debts.add(subject)
        group.schedule.all().delete()
        group.delete()
        messages.success(request, "Guruh o'chirildi, talabalar qayta ro'yxatga qaytarildi.")
    return redirect("lesson_schedule", pk=course_pk)

@login_required
def remove_student_from_group(request, group_pk, student_pk):
    group = get_object_or_404(CourseGroup, pk=group_pk)
    student = get_object_or_404(Student, pk=student_pk)
    if request.method == "POST":
        group.students.remove(student)
        sync_group_language(group)
        student.debts.add(group.course.subject)
        messages.success(request, f"{student} guruhdan o'chirildi va qayta ro'yxatga qo'shildi")
    return redirect("lesson_schedule", pk=group.course.pk)


# ─────────────────────────────────────────
# TEACHER
# ─────────────────────────────────────────
@login_required
def move_students(request, from_group_pk, to_group_pk):
    from_group = get_object_or_404(CourseGroup, pk=from_group_pk)
    to_group = get_object_or_404(CourseGroup, pk=to_group_pk)

    if request.method == "POST":
        student_ids = request.POST.getlist("student_ids")
        students = list(from_group.students.filter(id__in=student_ids))

        # ── YANGI TEKSHIRUV: har bir talaba uchun to_group vaqtlari bilan
        # to'qnashuvni alohida tekshiramiz — to'qnashgan talabalar
        # ko'chirilmaydi, faqat toza (band bo'lmagan) talabalar ko'chadi ──
        moved_students = []
        skipped_students = []
        for st in students:
            conflict = get_student_group_conflict(st, to_group, exclude_group=from_group)
            if conflict:
                skipped_students.append((st, conflict))
            else:
                from_group.students.remove(st)
                to_group.students.add(st)
                moved_students.append(st)

        sync_group_language(from_group)
        sync_group_language(to_group)

        if moved_students:
            messages.success(request, f"{len(moved_students)} ta talaba ko'chirildi.")
        if skipped_students:
            names = ", ".join(
                f"{st.first_name} ({d.strftime('%d.%m.%Y')} {t.strftime('%H:%M')} da band)"
                for st, (d, t) in skipped_students[:5]
            )
            extra = len(skipped_students) - 5
            if extra > 0:
                names += f" va yana {extra} ta"
            messages.error(request, f"❌ Quyidagi talabalar vaqt to'qnashuvi sababli ko'chirilmadi: {names}")
        return redirect("build_schedule")

    return render(request, "raspisaniya/move_students.html", {
        "from_group": from_group,
        "to_group": to_group,
        "students": from_group.students.all(),
    })


@login_required
def delete_unscheduled_group(request, pk):
    group = get_object_or_404(CourseGroup, pk=pk, is_scheduled=False)
    if request.method == "POST":
        subject = group.course.subject
        for st in group.students.all():
            st.debts.add(subject)
        group.delete()
        messages.success(request, "Guruh o'chirildi, talabalar qayta ro'yxatga qaytdi.")
    return redirect("build_schedule")


@login_required
def course_update(request, pk):
    course = get_object_or_404(Course, pk=pk)
    if request.method == "POST":
        start_date_raw = request.POST.get("start_date")
        end_date_raw = request.POST.get("end_date")
        total_lessons = request.POST.get("total_lessons")
        lessons_per_week = request.POST.get("lessons_per_week")

        if not all([start_date_raw, end_date_raw, total_lessons, lessons_per_week]):
            messages.error(request, "Barcha maydonlarni to'ldiring")
            return redirect("course_update", pk=pk)

        course.start_date = parse_date(start_date_raw)
        course.end_date = parse_date(end_date_raw)
        course.total_lessons = int(total_lessons)
        lessons_per_week = int(lessons_per_week)

        # ── YANGI TEKSHIRUV: jadval tuzuvchi algoritm total_lessons turiga
        # (24/16/8 paralik) qarab HAR DOIM qat'iy haftalik dars sonini
        # qo'llaydi — "Haftada necha marta" maydoniga boshqa son kiritilgan
        # bo'lsa ham, haqiqiy jadval baribir shu qat'iy songa muvofiq
        # tuziladi. Shuning uchun bu yerda mos qiymatga to'g'irlab, adminni
        # ogohlantiramiz — aks holda u "Haftada necha marta"da ko'rgan soni
        # bilan haqiqiy natija mos kelmay, keyin tushunarsiz bo'lib qolardi ──
        expected_per_week = get_expected_lessons_per_week(course.total_lessons)
        if lessons_per_week != expected_per_week:
            messages.warning(
                request,
                f"⚠ Diqqat: {course.total_lessons} paralik kurs uchun tizim haftada "
                f"faqat {expected_per_week} para joylashtira oladi (siz {lessons_per_week} "
                f"kiritgan edingiz). Qiymat avtomatik {expected_per_week} ga to'g'irlandi."
            )
        course.lessons_per_week = expected_per_week
        course.save()

        # MUHIM: sana/dars soni o'zgargani uchun eski jadval endi noto'g'ri —
        # shu bilan birga ustozlar ham eski (endi noto'g'ri) vaqtlarga
        # asosan biriktirilgan edi, shuning uchun ularni ham bo'shatamiz,
        # "Jadval tuzish" dan keyin "O'qituvchilarni taqsimlash" orqali
        # qaytadan to'g'ri biriktiriladi.
        course.groups.update(is_scheduled=False, teacher=None)
        GroupSchedule.objects.filter(group__course=course).delete()

        messages.success(request, "Kurs yangilandi! Qayta jadval tuzing.")
        return redirect("lesson_list")

    return render(request, "raspisaniya/course_update.html", {"course": course})


# ─────────────────────────────────────────
# HAFTALIK JADVAL
# ─────────────────────────────────────────
@login_required
def weekly_schedule_view(request):
    week_str = request.GET.get('week')
    if week_str:
        try:
            week_start = dt_date.fromisoformat(week_str)
            week_start = week_start - timedelta(days=week_start.weekday())
        except Exception:
            week_start = None
    else:
        week_start = None

    data = get_weekly_schedule_data(week_start)
    grid = data['grid']
    week_start = data['week_start']
    week_end = data['week_end']
    max_group = data['max_group']

    prev_week = (week_start - timedelta(weeks=1)).isoformat()
    next_week = (week_start + timedelta(weeks=1)).isoformat()

    # ── Qo'lda qo'shimcha ustun qo'shish/olib tashlash ──
    # extra_cols — admin "+ Ustun qo'shish" tugmasi orqali qo'shgan bo'sh
    # ustunlar soni (haqiqiy jadval ma'lumotidan mustaqil, faqat vizual
    # rejalashtirish uchun). Hafta bo'yicha navigatsiya qilinganda ham
    # saqlanib qolishi uchun URL parametri sifatida uzatiladi.
    try:
        extra_cols = int(request.GET.get('extra_cols', 0))
    except (TypeError, ValueError):
        extra_cols = 0
    extra_cols = max(0, min(extra_cols, 30))

    group_numbers = list(range(1, max_group + extra_cols + 1))

    SUBJECT_COLORS = [
        {'bg': '#dbeafe', 'text': '#1e40af', 'border': '#93c5fd'},
        {'bg': '#d1fae5', 'text': '#065f46', 'border': '#6ee7b7'},
        {'bg': '#fef3c7', 'text': '#92400e', 'border': '#fcd34d'},
        {'bg': '#fce7f3', 'text': '#9d174d', 'border': '#f9a8d4'},
        {'bg': '#ede9fe', 'text': '#5b21b6', 'border': '#c4b5fd'},
        {'bg': '#ffedd5', 'text': '#9a3412', 'border': '#fdba74'},
        {'bg': '#cffafe', 'text': '#155e75', 'border': '#67e8f9'},
        {'bg': '#dcfce7', 'text': '#14532d', 'border': '#86efac'},
        {'bg': '#fee2e2', 'text': '#991b1b', 'border': '#fca5a5'},
        {'bg': '#f0fdf4', 'text': '#166534', 'border': '#bbf7d0'},
        {'bg': '#fdf4ff', 'text': '#6b21a8', 'border': '#e879f9'},
        {'bg': '#fff7ed', 'text': '#9a3412', 'border': '#fed7aa'},
    ]
    subject_color_map = {}
    color_idx = [0]

    def get_subject_color(subject_name):
        if subject_name not in subject_color_map:
            subject_color_map[subject_name] = SUBJECT_COLORS[color_idx[0] % len(SUBJECT_COLORS)]
            color_idx[0] += 1
        return subject_color_map[subject_name]

    table_data = []
    for day_idx, day_name in enumerate(WEEKDAY_LIST):
        for para_idx, (start, end) in enumerate(PARA_TIMES_WEEKLY):
            cells = []
            has_any = False
            for gnum in group_numbers:
                key = (day_idx, para_idx, gnum)
                info = grid.get(key)
                if info:
                    has_any = True
                    color = get_subject_color(info['subject'])
                    cells.append({
                        'filled': True,
                        'sched_id': info['sched_id'],
                        'subject': info['subject'],
                        'teacher': info['teacher'],
                        'room': info.get('room', ''),
                        'group_number': info.get('group_number', ''),
                        'bg': color['bg'],
                        'text': color['text'],
                        'border': color['border'],
                    })
                else:
                    cells.append({'filled': False})
            table_data.append({
                'day': day_name,
                'time': f"{start} - {end}",
                'iso_date': (week_start + timedelta(days=day_idx)).isoformat(),
                'start_time': start,
                'cells': cells,
                'has_any': has_any,
                'show_day': para_idx == 0,
                'para_count': len(PARA_TIMES_WEEKLY),
            })

    return render(request, "raspisaniya/weekly_schedule.html", {
        "group_numbers": group_numbers,
        "table_data": table_data,
        "week_start": week_start,
        "week_end": week_end,
        "week_start_str": week_start.strftime("%d.%m.%Y"),
        "week_end_str": week_end.strftime("%d.%m.%Y"),
        "prev_week": prev_week,
        "next_week": next_week,
        "extra_cols": extra_cols,
        "base_group_count": max_group,
    })


@login_required
def weekly_schedule_excel(request):
    week_str = request.GET.get('week')
    if week_str:
        try:
            week_start = dt_date.fromisoformat(week_str)
            week_start = week_start - timedelta(days=week_start.weekday())
        except Exception:
            week_start = None
    else:
        week_start = None

    data = get_weekly_schedule_data(week_start)
    max_group = data['max_group']
    grid = data['grid']
    group_numbers = list(range(1, max_group + 1))

    wb = Workbook()
    ws = wb.active
    ws.title = "Haftalik jadval"

    thin = Side(style='thin', color='BBBBBB')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal='center', vertical='center', wrap_text=True)
    header_font = Font(name='Arial', bold=True, color='FFFFFF', size=10)
    header_fill = PatternFill('solid', start_color='2E4053')
    time_fill = PatternFill('solid', start_color='5D6D7E')
    time_font = Font(name='Arial', bold=True, color='FFFFFF', size=9)
    day_fill = PatternFill('solid', start_color='1A252F')
    day_font = Font(name='Arial', bold=True, color='FFFFFF', size=10)
    empty_fill = PatternFill('solid', start_color='F5F5F5')

    CELL_COLORS = [
        "D6E4BC", "B8D4E8", "FCE4A8", "E8C8D4",
        "CCE8CC", "FFD8B0", "D8D0E8", "E8E8C8",
        "BCE4E4", "FFC8C8", "D4E4F4", "E4D4BC",
        "C8D8F4", "F4D4C8", "D4F4D4", "F4F4C8",
    ]

    ws.column_dimensions['A'].width = 13
    ws.column_dimensions['B'].width = 14
    for i in range(len(group_numbers)):
        ws.column_dimensions[get_column_letter(i + 3)].width = 22

    ws.row_dimensions[1].height = 30
    for col, val in enumerate(["Kun", "Vaqt"], 1):
        c = ws.cell(1, col, val)
        c.font = header_font
        c.fill = header_fill
        c.alignment = center
        c.border = border

    for i, gnum in enumerate(group_numbers):
        c = ws.cell(1, i + 3, f"{gnum}-guruh")
        c.font = header_font
        c.fill = header_fill
        c.alignment = center
        c.border = border

    subject_color_map = {}
    color_counter = [0]

    def get_subject_color(subj):
        if subj not in subject_color_map:
            subject_color_map[subj] = CELL_COLORS[color_counter[0] % len(CELL_COLORS)]
            color_counter[0] += 1
        return subject_color_map[subj]

    row = 2
    for day_idx, day_name in enumerate(WEEKDAY_LIST):
        day_start_row = row
        for para_idx, (start, end) in enumerate(PARA_TIMES_WEEKLY):
            ws.row_dimensions[row].height = 45

            tc = ws.cell(row, 2, f"{start} - {end}")
            tc.font = time_font
            tc.fill = time_fill
            tc.alignment = center
            tc.border = border

            for i, gnum in enumerate(group_numbers):
                col = i + 3
                key = (day_idx, para_idx, gnum)
                cell = ws.cell(row, col)
                info = grid.get(key)
                if info:
                    room_str = f"\n🏫 {info['room']}" if info.get('room') else ''
                    group_str = f" ({info['group_number']}-guruh)" if info.get('group_number') else ''
                    cell.value = f"{info['subject']}{group_str}\n{info['teacher']}{room_str}"
                    cell.fill = PatternFill('solid', start_color=get_subject_color(info['subject']))
                    cell.font = Font(name='Arial', size=9, bold=True)
                else:
                    cell.value = ""
                    cell.fill = empty_fill
                    cell.font = Font(name='Arial', size=9)
                cell.alignment = center
                cell.border = border

            row += 1

        if row - day_start_row > 1:
            ws.merge_cells(
                start_row=day_start_row, start_column=1,
                end_row=row - 1, end_column=1
            )
        kc = ws.cell(day_start_row, 1)
        kc.value = day_name
        kc.font = day_font
        kc.fill = day_fill
        kc.alignment = center
        kc.border = border

    ws.freeze_panes = 'C2'

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="haftalik_jadval.xlsx"'
    wb.save(response)
    return response

@login_required
def change_lesson_time_ajax(request, sched_pk):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Faqat POST so\'rov'}, status=405)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': 'JSON xato'}, status=400)

    sched = get_object_or_404(GroupSchedule, pk=sched_pk)

    new_date_raw = body.get('new_date', '').strip()
    new_time_raw = body.get('new_time', '').strip()

    if not new_date_raw or not new_time_raw:
        return JsonResponse({'success': False, 'error': 'Sana yoki vaqt yuborilmagan'}, status=400)

    new_date_val = parse_date(new_date_raw)
    if not new_date_val:
        return JsonResponse({'success': False, 'error': 'Noto\'g\'ri sana formati'}, status=400)

    try:
        h, m = map(int, new_time_raw.split(':'))
        new_time_val = dtime(h, m)
    except (ValueError, AttributeError):
        return JsonResponse({'success': False, 'error': 'Noto\'g\'ri vaqt formati'}, status=400)

    if sched.date == new_date_val and sched.start_time == new_time_val:
        return JsonResponse({'success': False, 'error': 'Dars allaqachon shu vaqtda'})

    # Faqat bugungi kun o'zgartiriladi (admin istisno yoki ruxsat berilgan)
    from datetime import date as dt_date_check
    today = dt_date_check.today()
    is_admin = request.user.is_superuser or request.user.is_staff

    if not is_admin:
        if sched.date == today:
            # Bugungi kun — o'zgartirish mumkin, ruxsat shart emas
            pass
        elif sched.group.teacher_can_edit:
            # Admin ruxsat bergan — o'zgartirish mumkin
            pass
        else:
            # Boshqa kun + ruxsat yo'q — bloklash
            return JsonResponse({
                'success': False,
                'error': f'Faqat bugungi ({today.strftime("%d.%m.%Y")}) darsni o\'zgartirish mumkin! Boshqa kunlar uchun admin ruxsat berishi kerak.'
            })
    # ── YANGI: "kelajakdagi barcha haftalarga qo'llash" — faqat ADMIN uchun
    # (o'qituvchi bugungi bitta darsni o'zgartirish huquqiga ega, lekin butun
    # kelajakdagi jadvalni ommaviy o'zgartirish faqat admin qo'lida bo'lishi
    # kerak) ──
    apply_to_future = bool(body.get('apply_to_future')) and is_admin

    updated, skipped_dates = apply_lesson_time_change(
        sched, new_date_val, new_time_val, apply_to_future=apply_to_future
    )

    if updated == 0:
        if skipped_dates:
            return JsonResponse({
                'success': False,
                'error': f'{skipped_dates[0].strftime("%d.%m.%Y")} kuni o\'qituvchi yoki talabalar band!'
            })
        return JsonResponse({'success': False, 'error': 'Dars topilmadi yoki o\'zgartirilmadi'})

    end_time = (datetime.datetime.combine(new_date_val, new_time_val) + timedelta(minutes=80)).time()

    return JsonResponse({
        'success':        True,
        'new_date':       new_date_val.strftime('%d.%m.%Y'),
        'new_date_iso':   new_date_val.isoformat(),
        'new_time':       new_time_val.strftime('%H:%M'),
        'end_time':       end_time.strftime('%H:%M'),
        'weekday':        WEEKDAY_NAMES.get(new_date_val.weekday(), ''),
        'updated_count':  updated,
        'skipped_count':  len(skipped_dates),
    })



@login_required
def sched_info(request, sched_pk):
    """Dars haqida talabalar ro'yxati — modal uchun JSON."""
    sched = get_object_or_404(GroupSchedule, pk=sched_pk)
    students = list(
        sched.group.students.all()
        .order_by('first_name')
        .values_list('first_name', flat=True)
    )
    return JsonResponse({
        'students': students,
        'total': len(students),
        'subject': str(sched.group.course.subject),
        'teacher': str(sched.group.teacher),
        'room': str(sched.group.room) if sched.group.room else '—',
        'group_number': sched.group.group_number,
    })


def sched_info_ajax(request, sched_id):
    try:
        current_sched = get_object_or_404(GroupSchedule, pk=sched_id)
        course_group = current_sched.group

        WEEKDAY_NAMES_LOCAL = {
            0: 'Dushanba', 1: 'Seshanba', 2: 'Chorshanba',
            3: 'Payshanba', 4: 'Juma', 5: 'Shanba', 6: 'Yakshanba'
        }

        # Talabalar ro'yxati
        students_list = []
        if course_group:
            for student in course_group.students.all():
                full_name = f"{student.last_name} {student.first_name}".strip()
                if not full_name:
                    full_name = student.user.get_full_name() if student.user else str(student)

                lang_code = student.language or course_group.language or 'uz'
                student_lang = 'RUS' if lang_code.lower() == 'ru' else 'UZB'

                students_list.append({
                    'name': full_name,
                    'lang': student_lang
                })
        students_list = sorted(students_list, key=lambda x: x['name'])

        # Guruhning dars jadvali shablonini (barcha kunlarini) aniqlash
        other_days_result = []
        if course_group:
            # Guruhning barcha dars kunlarini yig'amiz
            all_schedules = GroupSchedule.objects.filter(group=course_group).order_by('date')
            days_set = {}

            for sched in all_schedules:
                st = sched.start_time or course_group.start_time
                if not st:
                    continue

                wd = sched.date.weekday()
                key = (wd, st.strftime('%H:%M'))

                if key not in days_set:
                    end_min = st.hour * 60 + st.minute + 80
                    end_h, end_m = divmod(end_min, 60)

                    days_set[key] = {
                        'weekday': WEEKDAY_NAMES_LOCAL.get(wd, ''),
                        'time': f"{st.strftime('%H:%M')} – {end_h:02d}:{end_m:02d}",
                    }

            sorted_days = sorted(
                days_set.values(),
                key=lambda d: list(WEEKDAY_NAMES_LOCAL.values()).index(d['weekday']) if d[
                                                                                            'weekday'] in WEEKDAY_NAMES_LOCAL.values() else 9
            )
            other_days_result = [f"{d['weekday']} ({d['time']})" for d in sorted_days]

        return JsonResponse({
            'success': True,
            'students': students_list,
            'other_days': other_days_result
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def student_schedule_info(request, student_pk):
    try:
        # Talabani bazadan qidiramiz
        student = get_object_or_404(Student, pk=student_pk)

        WEEKDAY_NAMES_LOCAL = {
            0: 'Dushanba', 1: 'Seshanba', 2: 'Chorshanba',
            3: 'Payshanba', 4: 'Juma', 5: 'Shanba', 6: 'Yakshanba'
        }

        # Talaba a'zo bo'lgan barcha guruhlarni (CourseGroup) yuklaymiz
        groups = CourseGroup.objects.filter(
            students=student
        ).select_related('course__subject', 'teacher', 'room').prefetch_related('schedule')

        result = []
        for grp in groups:
            days_set = {}
            # Guruhning bazadagi barcha dars sanalarini tekshiramiz
            all_scheds = grp.schedule.all().order_by('date', 'start_time')

            for sched in all_scheds:
                st = sched.start_time or grp.start_time
                if not st:
                    continue

                wd = sched.date.weekday()
                key = (wd, st.strftime('%H:%M'))

                if key not in days_set:
                    end_min = st.hour * 60 + st.minute + 80
                    end_h, end_m = divmod(end_min, 60)
                    days_set[key] = {
                        'weekday': WEEKDAY_NAMES_LOCAL.get(wd, ''),
                        'time': f"{st.strftime('%H:%M')} – {end_h:02d}:{end_m:02d}",
                    }

            # Hafta kunlari tartibida saralash
            days = sorted(
                days_set.values(),
                key=lambda d: list(WEEKDAY_NAMES_LOCAL.values()).index(d['weekday']) if d[
                                                                                            'weekday'] in WEEKDAY_NAMES_LOCAL.values() else 9
            )

            result.append({
                'subject': str(grp.course.subject),
                'teacher': f"{grp.teacher.last_name} {grp.teacher.first_name}".strip() if grp.teacher else "O'qituvchi",
                'room': str(grp.room) if grp.room else '—',
                'days': days,
            })

        return JsonResponse({'success': True, 'groups': result})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ==============================================================================
# 2. HAFTALIK UMUMIY JADVALDA DARS KARTASI BOSILGANDA (sched_id orqali) ISHLAYDIGAN FUNKSIYA
# ==============================================================================