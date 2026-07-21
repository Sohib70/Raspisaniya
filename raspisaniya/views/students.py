from ._shared import *

@login_required
def student_list(request):
    q = request.GET.get('q', '').strip()

    # Saralash parametrlari
    sort_by = request.GET.get('sort_by', 'fio')  # fio, lang, subject
    direction = request.GET.get('direction', 'asc')  # asc yoki desc

    students = Student.objects.prefetch_related(
        'debts',
        'coursegroup_set__course__subject',
    ).select_related('group').all()

    # 1. Qidiruv filtri
    if q:
        students = students.filter(
            first_name__icontains=q
        ) | students.filter(
            last_name__icontains=q
        ) | students.filter(
            student_id__icontains=q
        ) | students.filter(
            group__name__icontains=q
        )
        students = students.distinct()

    # 2. Ma'lumotlarni yig'ish (Sizning eski tsiklingiz)
    students_data = []
    for student in students:
        completed = list({grp.course.subject for grp in student.coursegroup_set.all()})

        # Saralash oson bo'lishi uchun fanlar nomini bitta matnga birlashtiramiz (masalan: "Matematika, Fizika")
        subjects_text = ", ".join(sorted([subj.name for subj in completed]))

        students_data.append({
            'student': student,
            'completed': completed,
            'subjects_text': subjects_text  # Saralash uchun kerak
        })

    # 3. Python orqali mukammal saralash (Gibrid mantiq)
    is_reverse = (direction == 'desc')

    if sort_by == 'fio':
        # Familiya va Ism bo'yicha saralash
        students_data.sort(key=lambda x: (x['student'].last_name.lower(), x['student'].first_name.lower()),
                           reverse=is_reverse)

    elif sort_by == 'lang':
        # Ta'lim tili bo'yicha saralash (uz, ru, en...)
        students_data.sort(key=lambda x: (x['student'].language or '').lower(), reverse=is_reverse)

    elif sort_by == 'subject':
        # Biriktirilgan fanlar matni bo'yicha saralash
        students_data.sort(key=lambda x: x['subjects_text'].lower(), reverse=is_reverse)

    return render(request, 'raspisaniya/student_list.html', {
        'students_data': students_data,
        'q': q,
        'sort_by': sort_by,
        'direction': direction,
    })


@login_required
def student_create(request):
    if request.method == 'POST':
        form = StudentForm(request.POST)
        if form.is_valid():
            student_id = request.POST.get("student_id", "").strip()
            password = request.POST.get("password", "").strip()

            if not student_id:
                messages.error(request, "Student ID kiritilmagan")
                return render(request, 'raspisaniya/student_create.html', {
                    'form': form, 'subjects': Subject.objects.all(),
                    'groups': Group.objects.all(), 'selected_debts': [],
                })

            if User.objects.filter(username=student_id).exists():
                messages.error(request, f"Bu ID ({student_id}) allaqachon mavjud")
                return render(request, 'raspisaniya/student_create.html', {
                    'form': form, 'subjects': Subject.objects.all(),
                    'groups': Group.objects.all(), 'selected_debts': [],
                })

            with transaction.atomic():
                student = form.save(commit=False)
                student.student_id = student_id
                student.save()
                form.save_m2m()
                user = User.objects.create_user(
                    username=student_id,
                    password=password if password else student_id,
                    first_name=student.first_name,
                    last_name=student.last_name,
                )
                student.user = user
                student.save()

            messages.success(request, f"O'quvchi qo'shildi. ID: {student_id}")
            return redirect('student_list')
    else:
        form = StudentForm()
    return render(request, 'raspisaniya/student_create.html', {
        'form': form, 'subjects': Subject.objects.all(),
        'groups': Group.objects.all(), 'selected_debts': [],
    })


@login_required
def student_update(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        full_name = request.POST.get('first_name', '').strip()
        if full_name:
            student.first_name = full_name
            student.last_name = ''

        group_id = request.POST.get('group', '').strip()
        if group_id:
            try:
                student.group = Group.objects.get(pk=group_id)
            except Group.DoesNotExist:
                pass
        else:
            student.group = None

        language = request.POST.get('language', '').strip()
        if language:
            student.language = language

        student.save()

        debt_ids = request.POST.getlist('debts')
        student.debts.set(debt_ids)

        new_password = request.POST.get('new_password', '').strip()
        if new_password and student.user:
            student.user.set_password(new_password)
            student.user.save()
            messages.success(request, "O'quvchi va parol yangilandi")
        else:
            messages.success(request, "O'quvchi yangilandi")
        return redirect('student_list')

    form = StudentForm(instance=student)
    return render(request, 'raspisaniya/student_update.html', {
        'form': form,
        'student': student,
        'subjects': Subject.objects.all(),
        'groups': Group.objects.all(),
        'selected_debts': list(student.debts.values_list('id', flat=True)),
    })


@login_required
def admin_change_student_password(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == "POST":
        new_password = request.POST.get("new_password", "").strip()
        if not new_password:
            messages.error(request, "Parol bo'sh bo'lmasin")
        elif not student.user:
            messages.error(request, "Bu talabaning tizim akkaunti yo'q")
        else:
            student.user.set_password(new_password)
            student.user.save()
            messages.success(request, f"{student} ning paroli o'zgartirildi")
    return redirect("student_list")


@login_required
def student_delete(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        student.delete()
        messages.success(request, "O'quvchi o'chirildi")
        return redirect('student_list')
    return render(request, 'raspisaniya/student_delete.html', {'student': student})


WORD_SUBJECTS_LOWER = [
    "noorganik kimyo",
    "organik kimyo",
    "fizik va kolloid kimyo",
    "analitik kimyo",
    "farmakognoziya",
    "farmatsevtik kimyo",
    "farmatsevtik texnologiya",
    "dorixonada ish yuritish",
    "sanoat texnologiyasi",
    "toksikologik kimyo",
    "sanoat farmatsiyasi",
    "farmatsevtik iqtisodiyoti",
]


def process_subject(raw_item):
    raw_item = raw_item.strip()
    if '(' in raw_item:
        name_only = raw_item[:raw_item.index('(')].strip()
    else:
        name_only = raw_item.strip()
    if name_only.lower() in WORD_SUBJECTS_LOWER:
        return raw_item
    else:
        return name_only


@login_required
@transaction.atomic
def import_students(request):
    if request.method == "POST":
        form = StudentImportForm(request.POST, request.FILES)
        if form.is_valid():
            file = request.FILES["file"]
            try:
                wb = load_workbook(file, read_only=True, data_only=True)
                ws = wb.active

                existing_users = {u.username: u for u in User.objects.filter(username__startswith='S-')}
                existing_groups = {g.name: g for g in Group.objects.all()}
                existing_subjects = {s.name: s for s in Subject.objects.all()}
                existing_students = {s.student_id: s for s in Student.objects.all()}

                new_users_to_create = []
                students_to_create = []
                students_to_update = []
                student_debts_collector = {}

                # Til mapping — Excel da qanday yozilsa shunga mos
                LANG_MAP = {
                    'o\'zbek': 'uz', 'uzbek': 'uz', 'uz': 'uz', "o'zbek": 'uz',
                    'рус': 'ru', 'rus': 'ru', 'ru': 'ru', 'russian': 'ru',
                    'қорақалпоқ': 'qq', 'karakalpak': 'qq', 'qq': 'qq',
                    'ingliz': 'en', 'english': 'en', 'en': 'en',
                }

                for row in ws.iter_rows(min_row=2, values_only=True):
                    if not row or not row[0] or not row[1]:
                        continue

                    sid = f"S-{str(row[0]).strip()}"
                    full_name = str(row[1]).strip()
                    if not full_name:
                        continue
                    first_name = full_name
                    last_name = ""

                    # Ta'lim tili — F ustuni (row[5])
                    lang_raw = str(row[5]).strip().lower() if len(row) > 5 and row[5] else 'uz'
                    language = LANG_MAP.get(lang_raw, 'uz')

                    # Guruh — E ustuni (row[4])
                    group_obj = None
                    if len(row) > 4 and row[4]:
                        g_name = str(row[4]).strip()
                        if g_name not in existing_groups:
                            group_obj = Group.objects.create(name=g_name)
                            existing_groups[g_name] = group_obj
                        else:
                            group_obj = existing_groups[g_name]

                    if sid not in existing_users:
                        user_obj = User(username=sid)
                        user_obj.set_password(sid)
                        new_users_to_create.append(user_obj)
                        existing_users[sid] = user_obj
                    else:
                        user_obj = existing_users[sid]

                    if sid not in existing_students:
                        st_obj = Student(
                            user=user_obj, student_id=sid,
                            first_name=first_name, last_name=last_name,
                            group=group_obj, language=language
                        )
                        students_to_create.append(st_obj)
                        existing_students[sid] = st_obj
                    else:
                        st_obj = existing_students[sid]
                        st_obj.first_name = first_name
                        st_obj.last_name = last_name
                        st_obj.group = group_obj
                        st_obj.language = language
                        if st_obj not in students_to_update:
                            students_to_update.append(st_obj)

                    # Fanlar — I ustuni (row[8])
                    if len(row) > 8 and row[8]:
                        raw_subjects = [s.strip() for s in str(row[8]).split(";") if s.strip()]
                        if sid not in student_debts_collector:
                            student_debts_collector[sid] = set()
                        for s_name in raw_subjects:
                            if s_name not in existing_subjects:
                                subj = Subject.objects.create(name=s_name)
                                existing_subjects[s_name] = subj
                            else:
                                subj = existing_subjects[s_name]
                            student_debts_collector[sid].add(subj)

                # Bulk create users
                if new_users_to_create:
                    User.objects.bulk_create(new_users_to_create, ignore_conflicts=True)
                    created_users = {u.username: u for u in
                                     User.objects.filter(username__in=[u.username for u in new_users_to_create])}
                    for s in students_to_create:
                        s.user = created_users.get(s.student_id)

                if students_to_create:
                    Student.objects.bulk_create(students_to_create)

                if students_to_update:
                    Student.objects.bulk_update(students_to_update, ['first_name', 'last_name', 'group', 'language'])

                if student_debts_collector:
                    db_students = {s.student_id: s for s in
                                   Student.objects.filter(student_id__in=student_debts_collector.keys())}
                    StudentDebtModel = Student.debts.through
                    debt_relations = []
                    for sid, subjects in student_debts_collector.items():
                        st_obj = db_students.get(sid)
                        if st_obj:
                            for subj_obj in subjects:
                                debt_relations.append(
                                    StudentDebtModel(student_id=st_obj.pk, subject_id=subj_obj.pk)
                                )
                    StudentDebtModel.objects.bulk_create(debt_relations, ignore_conflicts=True)

                messages.success(request, f"Import yakunlandi! {len(students_to_create)} yangi talaba qo'shildi.")
                return redirect("student_list")

            except Exception as e:
                print(f"IMPORT ERROR: {e}")
                messages.error(request, f"Xatolik yuz berdi: {str(e)}")
    else:
        form = StudentImportForm()

    return render(request, "raspisaniya/import_students.html", {"form": form})


# ─────────────────────────────────────────
# ROOM (XONA)
# ─────────────────────────────────────────
def split_subjects(raw):
    results = []
    current = ""
    depth = 0
    for char in str(raw):
        if char == '(':
            depth += 1
            current += char
        elif char == ')':
            depth -= 1
            current += char
        elif char == ';' and depth == 0:
            if current.strip():
                results.append(current.strip())
            current = ""
        else:
            current += char
    if current.strip():
        results.append(current.strip())
    return results


