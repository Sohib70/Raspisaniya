from ._shared import *

def get_backups_dir():
    backup_dir = os.path.join(settings.MEDIA_ROOT, 'backups')
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir


@staff_member_required
def reset_database_view(request):
    if request.method == 'POST' and request.POST.get('confirm') == 'TASDIQLASH':
        selected_models = request.POST.getlist('models_to_delete')

        if not selected_models:
            return render(request, 'raspisaniya/reset_database.html', {
                'error': "Hech bo'lmaganda bitta bo'limni tanlang!",
                'done': False
            })

        try:
            with transaction.atomic():
                # ── 1. Avval user ID larini yig'ib ol (o'chirishdan oldin) ──
                student_user_ids = []
                teacher_user_ids = []

                if 'student' in selected_models:
                    student_user_ids = list(
                        Student.objects.filter(user__isnull=False)
                        .values_list('user_id', flat=True)
                    )
                if 'teacher' in selected_models:
                    teacher_user_ids = list(
                        Teacher.objects.filter(user__isnull=False)
                        .values_list('user_id', flat=True)
                    )

                # ── 2. To'g'ri tartibda o'chirish (CASCADE yo'q — faqat Django ORM) ──
                # Tartib muhim: avval bog'liq jadvallar, keyin asosiylar

                if 'schedule' in selected_models:
                    GroupSchedule.objects.all().delete()

                if 'group' in selected_models:
                    CourseGroup.objects.all().delete()

                if 'course' in selected_models:
                    # GroupSchedule va CourseGroup avval o'chadi (yuqorida yoki cascade orqali)
                    Course.objects.all().delete()

                if 'student' in selected_models:
                    Student.objects.all().delete()

                if 'teacher' in selected_models:
                    Teacher.objects.all().delete()

                if 'subject' in selected_models:
                    Subject.objects.all().delete()

                if 'room' in selected_models:
                    Room.objects.all().delete()

                # ── 3. Tegishli oddiy foydalanuvchilarni o'chir ──
                all_user_ids = list(set(student_user_ids + teacher_user_ids))
                if all_user_ids:
                    User.objects.filter(
                        id__in=all_user_ids,
                        is_staff=False,
                        is_superuser=False,
                    ).delete()

            return render(request, 'raspisaniya/reset_database.html', {'done': True})

        except Exception as e:
            print(f"Baza tozalashda xato: {e}")
            return render(request, 'raspisaniya/reset_database.html', {
                'error': f"Xatolik yuz berdi: {str(e)}",
                'done': False
            })

    return render(request, 'raspisaniya/reset_database.html', {'done': False})


def export_database_view(request):
    """Backup yaratish — serverda saqlaydi va yuklab olish imkonini beradi."""
    from datetime import datetime as dt

    output = StringIO()
    management.call_command(
        'dumpdata',
        'raspisaniya', 'accounts', 'auth.user',
        indent=2,
        stdout=output,
        natural_foreign=True,
        natural_primary=True,
    )
    data = output.getvalue()

    # Nom: foydalanuvchi bergan nom yoki avtomatik sana
    custom_name = request.GET.get('name', '').strip()
    now = dt.now().strftime('%Y-%m-%d_%H-%M')
    if custom_name:
        safe_name = ''.join(c for c in custom_name if c.isalnum() or c in '-_ ')
        safe_name = safe_name.strip().replace(' ', '_')
        filename = f"{now}_{safe_name}.json"
    else:
        filename = f"{now}_backup.json"

    # Serverda saqlash
    backup_dir = get_backups_dir()
    filepath = os.path.join(backup_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(data)

    # Yuklab olish
    response = HttpResponse(data, content_type='application/json')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def restore_database_view(request):
    backup_dir = get_backups_dir()

    def do_restore(filepath):
        """Bazani tiklash — avval eski ma'lumotlarni tozalab, keyin yuklaymiz."""
        from django.contrib.auth.models import User
        from raspisaniya.models import (
            Student, Teacher, Subject, CourseGroup, Group,
            GroupSchedule, Room, Course, Attendance, Grade
        )
        try:
            # Ketma-ketlikda tozalaymiz (foreign key tartibida)
            Attendance.objects.all().delete()
            Grade.objects.all().delete()
            GroupSchedule.objects.all().delete()
            CourseGroup.objects.all().delete()
            Course.objects.all().delete()
            Student.objects.all().delete()
            Teacher.objects.all().delete()
            Room.objects.all().delete()
            Subject.objects.all().delete()
            # MUHIM: `Group` (talaba guruhi, masalan "21-KI-01") oldin o'chirilmagan edi —
            # shu sabab eski nomlar bazada qolib, tiklashda `UNIQUE constraint failed:
            # raspisaniya_group.name` xatosini berardi.
            Group.objects.all().delete()
            # Auth userlarni ham tozalaymiz (superuser qolsin)
            User.objects.filter(is_superuser=False).delete()
        except Exception as e:
            return f"Tozalashda xato: {e}"

        try:
            management.call_command('loaddata', filepath, ignorenonexistent=True)
            return None  # Xato yo'q
        except Exception as e:
            return str(e)

    if request.method == 'POST':
        action = request.POST.get('action')

        # 1. Fayl yuklash orqali tiklash
        if action == 'upload' and request.FILES.get('backup_file'):
            backup_file = request.FILES['backup_file']
            custom_name = request.POST.get('backup_name', '').strip()
            from datetime import datetime as dt
            now = dt.now().strftime('%Y-%m-%d_%H-%M')

            if custom_name:
                safe_name = ''.join(c for c in custom_name if c.isalnum() or c in '-_ ')
                filename = f"{now}_{safe_name.replace(' ', '_')}.json"
            else:
                filename = f"{now}_{backup_file.name}"

            save_path = os.path.join(backup_dir, filename)
            with open(save_path, 'wb+') as dest:
                for chunk in backup_file.chunks():
                    dest.write(chunk)

            err = do_restore(save_path)
            if err:
                messages.error(request, f"Xatolik: {err}")
            else:
                messages.success(request, f"✅ '{filename}' yuklandi va baza tiklandi!")
            return redirect('restore_database')

        # 2. Serverda saqlangan backup dan tiklash
        if action == 'restore_saved':
            filename = request.POST.get('filename', '')
            filepath = os.path.join(backup_dir, filename)
            if os.path.exists(filepath):
                err = do_restore(filepath)
                if err:
                    messages.error(request, f"Xatolik: {err}")
                else:
                    messages.success(request, f"✅ '{filename}' dan baza muvaffaqiyatli tiklandi!")
            else:
                messages.error(request, "Fayl topilmadi!")
            return redirect('restore_database')

        # 3. Backup o'chirish
        if action == 'delete_backup':
            filename = request.POST.get('filename', '')
            filepath = os.path.join(backup_dir, filename)
            if os.path.exists(filepath) and filename.endswith('.json'):
                os.remove(filepath)
                messages.success(request, f"'{filename}' o'chirildi.")
            return redirect('restore_database')

    # Saqlangan backuplar ro'yxati
    backups = []
    if os.path.exists(backup_dir):
        for fname in sorted(os.listdir(backup_dir), reverse=True):
            if fname.endswith('.json'):
                fpath = os.path.join(backup_dir, fname)
                stat = os.stat(fpath)
                backups.append({
                    'name': fname,
                    'size': round(stat.st_size / 1024, 1),
                    'date': stat.st_mtime,
                })

    return render(request, 'raspisaniya/restore_database.html', {
        'backups': backups,
    })


def admin_password_reset_request(request):
    """ Admin parolini tiklash: Kod har doim loyiha rahbarining pochtasiga boradi """
    if request.method == "POST":
        # Formadan kelayotgan emailni tekshirib o'tirmaymiz,
        # chunki kod baribir settings.py dagi sizning emailingizga ketadi.

        # Tizimdagi asosiy superuser (admin)ni topamiz
        admin_user = User.objects.filter(is_superuser=True).first()

        if admin_user:
            # 5 xonali tasodifiy kod yaratish
            code = str(random.randint(10000, 99999))

            # Kod va admin ID sini sessionga saqlaymiz
            request.session['reset_code'] = code
            request.session['reset_admin_id'] = admin_user.pk

            # Email sozlamalari
            subject = "Dars jadvali - Admin parolini va loginini tiklash kodi"
            message = f"Tizim admin paneli uchun parolni tiklash kodi: {code}\n\nUshbu kodni parolni yangilash sahifasiga kiriting."

            # Kod yuboriladigan manzil - qat'iy ravishda settings.py dagi sizning pochtangiz
            target_email = settings.ADMIN_RESET_TARGET_EMAIL
            from_email = settings.DEFAULT_FROM_EMAIL

            try:
                send_mail(subject, message, from_email, [target_email], fail_silently=False)
                messages.success(request, f"Tasdiqlash kodi tizim rahbarining pochtasiga yuborildi.")
                return render(request, "accounts/admin_password_verify.html")
            except Exception as e:
                messages.error(request, f"Email yuborishda xatolik: {str(e)}")
                return redirect('login')
        else:
            messages.error(request, "Tizimda hech qanday admin foydalanuvchi topilmadi!")
            return redirect('login')

    return redirect('login')


def admin_password_verify_and_change(request):
    """ Kodni tekshirish, login (username) va parolni yangilash """
    if request.method == "POST":
        input_code = request.POST.get("verification_code", "").strip()
        new_username = request.POST.get("new_username", "").strip()
        new_password = request.POST.get("new_password", "").strip()
        confirm_password = request.POST.get("confirm_password", "").strip()

        session_code = request.session.get('reset_code')
        admin_id = request.session.get('reset_admin_id')

        if not session_code or not admin_id:
            messages.error(request, "Sessiya muddati tugagan yoki noto'g'ri so'rov.")
            return redirect('login')

        if input_code != session_code:
            messages.error(request, "Kiritilgan tasdiqlash kodi noto'g'ri!")
            return render(request, "accounts/admin_password_verify.html")

        # 🌟 YANGI LOGIN TEKSHIRUVI: Bu username bazada band emasligini tekshiramiz
        # Lekin aynan shu o'zgartirayotgan adminning o'z eski ID si bo'lsa, unga ruxsat berish kerak
        username_exists = User.objects.filter(username=new_username).exclude(pk=admin_id).exists()
        if username_exists:
            messages.error(request, f"'{new_username}' ID raqami tizimda band! Boshqa ID kiriting.")
            return render(request, "accounts/admin_password_verify.html")

        if new_password != confirm_password:
            messages.error(request, "Yangi parollar bir-biriga mos kelmadi.")
            return render(request, "accounts/admin_password_verify.html")

        if len(new_password) < 4:
            messages.error(request, "Parol kamida 4 ta belgi bo'lishi kerak.")
            return render(request, "accounts/admin_password_verify.html")

        # Admin modelini olib, ham username, ham parolni yangilaymiz
        admin_user = User.objects.get(pk=admin_id)
        admin_user.username = new_username
        admin_user.set_password(new_password)
        admin_user.save()

        # Sessiyadagi ma'lumotlarni tozalaymiz
        del request.session['reset_code']
        del request.session['reset_admin_id']

        messages.success(request,
                         f"Admin hisob ma'lumotlari muvaffaqiyatli yangilandi! Yangi ID ({new_username}) va yangi parol bilan kiring.")
        return redirect('login')

    return redirect('login')


# raspisaniya/views.py ga qo'shing

