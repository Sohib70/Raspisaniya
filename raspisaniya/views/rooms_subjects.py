from ._shared import *

@login_required
def room_list(request):
    q = request.GET.get('q', '').strip()
    rooms = Room.objects.prefetch_related(
        'coursegroup_set__course__subject',
        'coursegroup_set__teacher',
    ).all().order_by('name')
    if q:
        rooms = rooms.filter(name__icontains=q)
    return render(request, 'raspisaniya/room_list.html', {'rooms': rooms, 'q': q})


@login_required
def room_create(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        capacity = request.POST.get("capacity", 30)
        if not name:
            messages.error(request, "Xona nomi kiritilmagan")
        elif Room.objects.filter(name=name).exists():
            messages.error(request, f"'{name}' xonasi allaqachon mavjud")
        else:
            Room.objects.create(name=name, capacity=int(capacity))
            messages.success(request, f"'{name}' xonasi qo'shildi")
            return redirect("room_list")
    return render(request, 'raspisaniya/room_create.html')


@login_required
def room_delete(request, pk):
    room = get_object_or_404(Room, pk=pk)
    if request.method == "POST":
        room.delete()
        messages.success(request, "Xona o'chirildi")
    return redirect("room_list")


@login_required
def assign_room(request, group_pk):
    group = get_object_or_404(CourseGroup, pk=group_pk)
    if request.method == "POST":
        room_id = request.POST.get("room_id")
        if not room_id:
            group.room = None
            group.save()
            messages.success(request, "Xona biriktirilmadi (bo'shatildi)")
            return redirect("lesson_schedule", pk=group.course.pk)

        room = get_object_or_404(Room, pk=room_id)

        for sched in group.schedule.all():
            st = sched.start_time or group.start_time
            if not st:
                continue
            conflict = GroupSchedule.objects.filter(
                date=sched.date,
                start_time=st,
                group__room=room,
            ).exclude(group=group)
            if conflict.exists():
                conflict_grp = conflict.first().group
                messages.error(
                    request,
                    f"'{room.name}' xonasi {sched.date} kuni {st.strftime('%H:%M')} da "
                    f"'{conflict_grp.course.subject}' ({conflict_grp.group_number}-guruh) uchun band!"
                )
                return redirect("lesson_schedule", pk=group.course.pk)

        group.room = room
        group.save()
        messages.success(request, f"'{room.name}' xonasi biriktirildi")
    return redirect("lesson_schedule", pk=group.course.pk)


# ─────────────────────────────────────────
# SUBJECT
# ─────────────────────────────────────────
@login_required
def subject_list(request):
    q = request.GET.get('q', '').strip()

    # Saralash parametrlari (default holatda Fan nomi bo'yicha ASC)
    sort_by = request.GET.get('sort_by', 'subject')  # subject yoki debt
    direction = request.GET.get('direction', 'asc')  # asc yoki desc

    # Fanlarni va ularga tegishli qarzdorlarni bazadan yuklash
    subjects_queryset = Subject.objects.prefetch_related('debt_students').all()

    if q:
        subjects_queryset = subjects_queryset.filter(name__icontains=q)

    # Saralash mantiqi aniq ishlashi uchun ma'lumotlar ro'yxatini yig'amiz
    subjects_data = []
    for subj in subjects_queryset:
        subjects_data.append({
            'subject': subj,
            'debt_count': subj.debt_students.count()  # Qarzdorlar soni
        })

    # Python orqali mukammal saralash
    is_reverse = (direction == 'desc')

    if sort_by == 'subject':
        # Fan nomi bo'yicha saralash
        subjects_data.sort(key=lambda x: (x['subject'].name or '').lower(), reverse=is_reverse)

    elif sort_by == 'debt':
        # Qarzdor talabalar soni bo'yicha saralash
        subjects_data.sort(key=lambda x: x['debt_count'], reverse=is_reverse)

    return render(request, 'raspisaniya/subject_list.html', {
        'subjects_data': subjects_data,
        'q': q,
        'sort_by': sort_by,
        'direction': direction,
    })


@login_required
def subject_create(request):
    if request.method == 'POST':
        form = SubjectForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Fan qo'shildi")
            return redirect('subject_list')
    else:
        form = SubjectForm()
    return render(request, 'raspisaniya/subject_create.html', {'form': form})


@login_required
def subject_update(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    if request.method == 'POST':
        form = SubjectForm(request.POST, instance=subject)
        if form.is_valid():
            form.save()
            messages.success(request, "Fan yangilandi")
            return redirect('subject_list')
    else:
        form = SubjectForm(instance=subject)
    return render(request, 'raspisaniya/subject_create.html', {'form': form})


@login_required
def subject_delete(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    if request.method == 'POST':
        subject.delete()
        messages.success(request, "Fan o'chirildi")
        return redirect('subject_list')
    return render(request, 'raspisaniya/subject_delete.html', {'subject': subject})


@login_required
def subject_students(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    students = Student.objects.filter(debts=subject).order_by('last_name')
    return render(request, 'raspisaniya/subject_students.html', {
        'subject': subject, 'students': students,
    })


@login_required
def subject_students_excel(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    students = Student.objects.filter(debts=subject).order_by('last_name')

    wb = Workbook()
    ws = wb.active
    ws.title = subject.name
    ws.append(["#", "Familiya", "Ism Sharif", "Guruh"])
    for i, student in enumerate(students, 1):
        ws.append([i, student.last_name, student.first_name,
                   str(student.group) if student.group else "—"])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{subject.name}_qarzdorlar.xlsx"'
    wb.save(response)
    return response


