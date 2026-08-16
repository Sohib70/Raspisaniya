from ._shared import *

@login_required
def teacher_list(request):
    q = request.GET.get('q', '').strip()
    sort = request.GET.get('sort', 'name_asc')

    # 'groups' o'rniga modelingizga mos bo'lgan 'coursegroup_set' ni yuklaymiz
    teachers = Teacher.objects.prefetch_related('subjects', 'coursegroup_set').all()

    if q:
        teachers = teachers.filter(first_name__icontains=q) | \
                   teachers.filter(last_name__icontains=q) | \
                   teachers.filter(teacher_id__icontains=q) | \
                   teachers.filter(subjects__name__icontains=q)

    teachers = teachers.distinct()

    # ID bo'yicha saralashda T- dan keyingi raqamni olib raqam sifatida tartiblash
    if sort in ('id_asc', 'id_desc'):
        def extract_num(t):
            m = re.search(r'\d+', t.teacher_id or '')
            return int(m.group()) if m else 0
        reverse = (sort == 'id_desc')
        teachers = sorted(teachers, key=extract_num, reverse=reverse)
    elif sort == 'name_asc':
        teachers = teachers.order_by('first_name')
    elif sort == 'name_desc':
        teachers = teachers.order_by('-first_name')
    elif sort == 'subj_asc':
        teachers = teachers.order_by('subjects__name', 'first_name')
    elif sort == 'subj_desc':
        teachers = teachers.order_by('-subjects__name', 'first_name')
    else:
        teachers = teachers.order_by('first_name')

    # HTML shablonda oson ishlatishimiz uchun har bir o'qituvchining dars yuklamasini yig'ib chiqamiz
    teachers_data = []
    for teacher in teachers:
        # Keshdagi ma'lumotdan foydalanish uchun .count() o'rniga len(...all()) ishlatamiz.
        # Bu bazaga qayta-qayta SQL so'rov yuborilishining oldini oladi (N+1 muammosi yechimi).
        group_count = len(teacher.coursegroup_set.all())

        teachers_data.append({
            'teacher': teacher,
            'group_count': group_count,
            'has_groups': group_count > 0
        })

    subjects = Subject.objects.all().order_by('name')

    return render(request, 'raspisaniya/teacher_list.html', {
        'teachers_data': teachers_data,
        'q': q,
        'subjects': subjects,
        'selected_subject': request.GET.get('subject', ''),
        'sort': sort,
    })


@login_required
def check_teacher_id_available(request):
    """
    Yengil AJAX endpoint — berilgan Teacher ID band yoki bo'shligini
    darhol (foydalanuvchi yozayotganida) tekshiradi. `exclude_pk`
    berilsa (tahrirlash sahifasida), o'sha o'qituvchining o'ziga
    tegishli ID hisobga olinmaydi.
    """
    tid = request.GET.get('id', '').strip()
    exclude_pk = request.GET.get('exclude_pk', '').strip()

    if not tid:
        return JsonResponse({'available': True})

    qs = User.objects.filter(username=tid)
    if exclude_pk:
        qs = qs.exclude(teacher__pk=exclude_pk)

    taken = qs.exists()
    return JsonResponse({'available': not taken})


def _next_available_teacher_id():
    """
    Band bo'lmagan ENG KICHIK 'T-N' raqamini topadi (bo'shliqlarni ham
    hisobga olib) — masalan T-1, T-3 band bo'lsa, T-2 taklif qilinadi.
    """
    used_numbers = set()
    for tid in Teacher.objects.exclude(teacher_id__isnull=True).exclude(teacher_id='').values_list('teacher_id', flat=True):
        m = re.match(r'^T-(\d+)$', tid.strip())
        if m:
            used_numbers.add(int(m.group(1)))
    n = 1
    while n in used_numbers:
        n += 1
    return f"T-{n}"


@login_required
def teacher_create(request):
    if request.method == 'POST':
        form = TeacherForm(request.POST)
        submitted_teacher_id = request.POST.get("teacher_id", "").strip()
        submitted_subject_ids = [int(sid) for sid in request.POST.getlist('subjects') if sid.isdigit()]

        if form.is_valid():
            teacher_id = submitted_teacher_id or _next_available_teacher_id()
            password = request.POST.get("password", "").strip()

            if User.objects.filter(username=teacher_id).exists():
                messages.error(request, f"❌ Bu ID ({teacher_id}) allaqachon mavjud — boshqa ID tanlang.")
                return render(request, 'raspisaniya/teacher_create.html', {
                    'form': form, 'subjects': Subject.objects.all(),
                    'selected_subjects': submitted_subject_ids,
                    'suggested_teacher_id': teacher_id,
                })

            with transaction.atomic():
                teacher = form.save(commit=False)
                teacher.teacher_id = teacher_id
                teacher.save()
                form.save_m2m()
                user = User.objects.create_user(
                    username=teacher_id,
                    password=password if password else teacher_id,
                    first_name=teacher.first_name,
                    last_name=teacher.last_name,
                )
                teacher.user = user
                teacher.save()

            messages.success(request, f"✅ O'qituvchi qo'shildi. ID: {teacher_id}")
            return redirect('teacher_list')
        else:
            # ── MUHIM: forma yaroqsiz bo'lsa (masalan siz o'zgartirgan Teacher
            # ID allaqachon band bo'lsa — bu holat Teacher modelidagi
            # unique=True cheklovi orqali aniqlanadi), sababini ANIQ
            # ko'rsatamiz va siz kiritgan qiymatlarni (ID, tanlangan
            # fanlar) YO'QOTMAY qayta ko'rsatamiz — shunda ID'ni
            # o'zgartirish haqiqatan ishlaydi, faqat "sababsiz" qayta
            # yuklanib qolmaydi.
            for field, errs in form.errors.items():
                for err in errs:
                    messages.error(request, f"❌ {err}")
            return render(request, 'raspisaniya/teacher_create.html', {
                'form': form, 'subjects': Subject.objects.all(),
                'selected_subjects': submitted_subject_ids,
                'suggested_teacher_id': submitted_teacher_id or _next_available_teacher_id(),
            })
    else:
        form = TeacherForm()
    return render(request, 'raspisaniya/teacher_create.html', {
        'form': form, 'subjects': Subject.objects.all(), 'selected_subjects': [],
        'suggested_teacher_id': _next_available_teacher_id(),
    })


@login_required
def teacher_update(request, pk):
    teacher = get_object_or_404(Teacher, pk=pk)

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        new_id = request.POST.get('teacher_id', '').strip()
        new_password = request.POST.get('new_password', '').strip()
        subject_ids = request.POST.getlist('subjects')

        # 1. Ismni tekshirish va yangilash
        if first_name:
            teacher.first_name = first_name
            if teacher.user:
                teacher.user.first_name = first_name
                teacher.user.save()

        # 2. XAVFSIZLIK TEKSHIRUVI: Yangi ID unikal ekanligini tekshirish
        if new_id and new_id != teacher.teacher_id:
            # Bazada aynan shu username mavjudligini tekshiramiz (o'zidan tashqari)
            if User.objects.filter(username=new_id).exists():
                messages.error(request,
                               f"Xatolik: Tizimda '{new_id}' ID ga ega foydalanuvchi allaqachon mavjud! Iltimos, boshqa ID kiriting.")

                # Xatolik bo'lgani uchun formani qayta yuklaymiz, foydalanuvchi kiritgan ma'lumotlar yo'qolmaydi
                return render(request, 'raspisaniya/teacher_update.html', {
                    'teacher': teacher,
                    'subjects': Subject.objects.all().order_by('name'),
                    'selected_subjects': [int(sid) for sid in subject_ids],  # Tanlangan fanlar o'chib ketmasligi uchun
                })

            # Agar muammo bo'lmasa, ID ni yangilaymiz
            teacher.teacher_id = new_id
            if teacher.user:
                teacher.user.username = new_id
                teacher.user.save()

        # 3. Parolni yangilash
        if new_password and teacher.user:
            if len(new_password) < 4:
                messages.error(request, "Xatolik: Yangi parol kamida 4 ta belgidan iborat bo'lishi kerak.")
                return render(request, 'raspisaniya/teacher_update.html', {
                    'teacher': teacher,
                    'subjects': Subject.objects.all().order_by('name'),
                    'selected_subjects': [int(sid) for sid in subject_ids],
                })
            teacher.user.set_password(new_password)
            teacher.user.save()

        # O'qituvchi modelini saqlash va fanlarni bog'lash
        teacher.save()
        teacher.subjects.set(subject_ids)

        messages.success(request, "O'qituvchi ma'lumotlari muvaffaqiyatli yangilandi.")
        return redirect('teacher_list')

    return render(request, 'raspisaniya/teacher_update.html', {
        'teacher': teacher,
        'subjects': Subject.objects.all().order_by('name'),
        'selected_subjects': list(teacher.subjects.values_list('id', flat=True)),
    })


@login_required
def teacher_delete(request, pk):
    teacher = get_object_or_404(Teacher, pk=pk)
    if request.method == 'POST':
        teacher.delete()
        messages.success(request, "O'qituvchi o'chirildi")
        return redirect('teacher_list')
    return render(request, 'raspisaniya/teacher_delete.html', {'teacher': teacher})


@login_required
def teacher_import(request):
    if request.method == "POST":
        form = TeacherImportForm(request.POST, request.FILES)
        if form.is_valid():
            file = request.FILES["file"]
            try:
                wb = load_workbook(file)
                ws = wb.active

                # 1. Barcha mavjud ma'lumotlarni bir marta xotiraga yuklaymiz
                # Fanlarni nomi bo'yicha lug'atga olamiz: {'Matematika': <Subject object>, ...}
                existing_subjects = {s.name: s for s in Subject.objects.all()}

                # Userlarning username'larini tezkor tekshirish uchun 'set'ga olamiz
                existing_usernames = set(User.objects.values_list('username', flat=True))

                with transaction.atomic():
                    for row in ws.iter_rows(min_row=2, values_only=True):
                        # Bo'sh qatorlarni tashlab ketish
                        if not row or not row[0] or not row[1]:
                            continue

                        tid = f"T-{str(row[0]).strip()}"
                        full_name = str(row[1]).strip()
                        if not full_name:
                            continue

                        first_name = full_name   # To'liq nom — qanday tursa shunday
                        last_name = ""

                        # 2. User yaratish yoki olish (Xotiradan tekshiramiz)
                        if tid not in existing_usernames:
                            u = User.objects.create_user(username=tid, password=tid)
                            existing_usernames.add(tid)
                        else:
                            u = User.objects.get(username=tid)

                        # 3. Teacher yaratish yoki yangilash
                        teacher, created = Teacher.objects.update_or_create(
                            user=u,
                            defaults={
                                'first_name': first_name,
                                'last_name': last_name,
                                'teacher_id': tid
                            }
                        )

                        # 4. Fanlarni bog'lash (Xotira orqali)
                        if len(row) > 2 and row[2]:
                            subject_names = [s.strip() for s in str(row[2]).split(",") if s.strip()]
                            for sname in subject_names:
                                # Agar fan lug'atda bo'lmasa, bazada yaratib lug'atga qo'shamiz
                                if sname not in existing_subjects:
                                    subj = Subject.objects.create(name=sname)
                                    existing_subjects[sname] = subj

                                # Fanlarni bog'laymiz
                                teacher.subjects.add(existing_subjects[sname])

                        teacher.save()

                messages.success(request, "O'qituvchilar muvaffaqiyatli import qilindi ✅")
                return redirect("teacher_list")
            except Exception as e:
                # Xatoni terminalda ham ko'rish uchun:
                print(f"Import Error: {e}")
                messages.error(request, f"Xatolik: {e}")
    else:
        form = TeacherImportForm()
    return render(request, "raspisaniya/teacher_import.html", {"form": form})


# ─────────────────────────────────────────
# STUDENT
# ─────────────────────────────────────────
@login_required
def admin_change_teacher_password(request, pk):
    """Admin: o'qituvchi parolini o'zgartirish."""
    teacher = get_object_or_404(Teacher, pk=pk)
    if request.method == "POST":
        new_password = request.POST.get("new_password", "").strip()
        if not new_password:
            messages.error(request, "Parol bo'sh bo'lmasin")
        elif not teacher.user:
            messages.error(request, "Bu o'qituvchining tizim akkaunti yo'q")
        else:
            teacher.user.set_password(new_password)
            teacher.user.save()
            messages.success(request, f"{teacher.first_name} ning paroli o'zgartirildi")
    return redirect("teacher_list")


@login_required
def toggle_teacher_edit_permission(request, group_pk):
    """Admin: guruh uchun o'qituvchiga dars vaqtini o'zgartirish ruxsatini berish/olish."""
    if not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({'success': False, 'error': 'Ruxsat yo\'q'}, status=403)
    group = get_object_or_404(CourseGroup, pk=group_pk)
    if request.method == 'POST':
        group.teacher_can_edit = not group.teacher_can_edit
        group.save(update_fields=['teacher_can_edit'])
        return JsonResponse({
            'success': True,
            'permitted': group.teacher_can_edit,
            'label': 'Ruxsat berildi ✅' if group.teacher_can_edit else 'Ruxsat berilmagan',
        })
    return JsonResponse({'success': False}, status=405)

@login_required
def toggle_all_teacher_edit_permission(request):
    """Admin: barcha guruhlarga bir vaqtda ruxsat berish/olish."""
    if not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({'success': False, 'error': 'Ruxsat yo\'q'}, status=403)
    if request.method == 'POST':
        import json as _json
        body = _json.loads(request.body)
        permitted = body.get('permitted', True)
        CourseGroup.objects.filter(is_scheduled=True).update(teacher_can_edit=permitted)
        count = CourseGroup.objects.filter(is_scheduled=True).count()
        return JsonResponse({
            'success': True,
            'permitted': permitted,
            'count': count,
            'label': f'Hammaga ruxsat berildi ✅ ({count} guruh)' if permitted else f'Hammadan ruxsat olindi ({count} guruh)',
        })
    return JsonResponse({'success': False}, status=405)