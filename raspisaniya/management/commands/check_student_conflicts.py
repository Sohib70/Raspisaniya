# raspisaniya/management/commands/check_student_conflicts.py
#
# Ishlatish:
#   python manage.py check_student_conflicts
#   python manage.py check_student_conflicts --group-pk 31
#   python manage.py check_student_conflicts --teacher "Muxammadiyeva"

from django.core.management.base import BaseCommand
from raspisaniya.models import CourseGroup, GroupSchedule
from datetime import date, timedelta
from collections import defaultdict


class Command(BaseCommand):
    help = 'O\'quvchilarning band paralarini tekshirish va matematik to\'siqlarni aniqlash'

    def add_arguments(self, parser):
        parser.add_argument('--group-pk', type=int, default=None,
                            help='Faqat shu guruh uchun tekshirish')
        parser.add_argument('--teacher', type=str, default=None,
                            help='Faqat shu o\'qituvchi guruhlarini tekshirish')
        parser.add_argument('--start', type=str, default=None)
        parser.add_argument('--end', type=str, default=None)

    def handle(self, *args, **options):

        # ── Tekshiriladigan guruhlarni tanlash ──────────────────────
        unscheduled = CourseGroup.objects.filter(
            is_scheduled=False
        ).select_related('course__subject', 'teacher', 'course').prefetch_related('students')

        if options['group_pk']:
            unscheduled = unscheduled.filter(pk=options['group_pk'])

        if options['teacher']:
            unscheduled = unscheduled.filter(
                teacher__first_name__icontains=options['teacher']
            )

        if not unscheduled.exists():
            self.stdout.write(self.style.SUCCESS('✅ Tekshiriladigan guruh topilmadi'))
            return

        self.stdout.write(f'\n{"=" * 70}')
        self.stdout.write(f'Jadval tuzilmagan guruhlar: {unscheduled.count()} ta')
        self.stdout.write(f'{"=" * 70}')

        WEEKDAYS = ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba']

        for grp in unscheduled:
            start = options['start'] and date.fromisoformat(options['start']) or grp.course.start_date
            end = options['end'] and date.fromisoformat(options['end']) or grp.course.end_date

            students = list(grp.students.all())
            student_ids = [s.id for s in students]

            self.stdout.write(f'\n{"─" * 70}')
            self.stdout.write(self.style.WARNING(
                f'Guruh: {grp.course.subject} {grp.group_number}-guruh | '
                f'O\'qituvchi: {grp.teacher} | '
                f'{grp.course.total_lessons} para kerak'
            ))
            self.stdout.write(f'Muddat: {start} — {end} | Talabalar: {len(students)} ta')
            self.stdout.write(f'{"─" * 70}')

            # ── Matematik tahlil uchun o'zgaruvchilar ───────────────
            cur = start
            problem_days = 0
            total_free = 0
            total_days = 0

            # Har bir o'quvchi necha marta dars qo'yish imkoniyatini yopganini sanash
            student_block_counts = defaultdict(int)
            # O'qituvchi bo'sh bo'lgan jami paralar (potensial dars o'tish mumkin bo'lgan joylar)
            total_teacher_free_slots = 0

            while cur <= end:
                if cur.weekday() > 4:
                    cur += timedelta(days=1)
                    continue
                total_days += 1

                # O'qituvchi band paralar
                teacher_scheds = GroupSchedule.objects.filter(
                    date=cur,
                    group__teacher=grp.teacher,
                ).select_related('group__course__subject')

                # talabalar band paralar
                student_scheds = GroupSchedule.objects.filter(
                    date=cur,
                    group__students__id__in=student_ids,
                ).select_related(
                    'group__course__subject', 'group__teacher'
                ).prefetch_related('group__students').distinct()

                # Band paralarni aniqlash
                from raspisaniya.views import PARA_TIMES
                teacher_busy = set()
                student_busy = defaultdict(list)  # para_idx -> [talaba ismlari]

                for sc in teacher_scheds:
                    st = sc.start_time or sc.group.start_time
                    if st:
                        for i, (ps, _) in enumerate(PARA_TIMES):
                            if ps == st:
                                teacher_busy.add(i)

                for sc in student_scheds:
                    st = sc.start_time or sc.group.start_time
                    if st:
                        for i, (ps, _) in enumerate(PARA_TIMES):
                            if ps == st:
                                busy_students = [
                                    s.first_name + " " + s.last_name for s in sc.group.students.all()
                                    if s.id in student_ids
                                ]
                                student_busy[i].extend(busy_students)

                                # Matematik hisob: Agar o'qituvchi bo'sh bo'lsa-yu, lekin o'quvchi band bo'lsa,
                                # bu o'quvchi jadval yaratilishiga bevosita to'sqinlik qilmoqda.
                                if i not in teacher_busy:
                                    for b_student in busy_students:
                                        student_block_counts[b_student] += 1

                # O'qituvchi shu kunda bo'sh bo'lgan paralar sonini umumiy fondga qo'shamiz
                total_teacher_free_slots += (len(PARA_TIMES) - len(teacher_busy))

                all_busy = teacher_busy | set(student_busy.keys())
                free_paras = [i for i in range(len(PARA_TIMES)) if i not in all_busy]
                total_free += len(free_paras)

                if len(free_paras) == 0:
                    problem_days += 1
                    self.stdout.write(self.style.ERROR(
                        f'  {cur} {WEEKDAYS[cur.weekday()][:2]} — '
                        f'TO\'LIQ BAND (0 bo\'sh para)'
                    ))
                    # Sabablarini ko'rsatish
                    if teacher_busy:
                        self.stdout.write(
                            f'    👨‍🏫 O\'qituvchi band paralar: '
                            f'{[PARA_TIMES[i][0].strftime("%H:%M") for i in sorted(teacher_busy)]}'
                        )
                    for pi, names in sorted(student_busy.items()):
                        unique_names = list(set(names))
                        self.stdout.write(
                            f'    👨‍🎓 {PARA_TIMES[pi][0].strftime("%H:%M")} parada band: '
                            f'{", ".join(unique_names[:5])}'
                            f'{"..." if len(unique_names) > 5 else ""}'
                        )
                elif len(free_paras) < 2:
                    self.stdout.write(self.style.WARNING(
                        f'  {cur} {WEEKDAYS[cur.weekday()][:2]} — '
                        f'faqat {len(free_paras)} ta bo\'sh para: '
                        f'{[PARA_TIMES[i][0].strftime("%H:%M") for i in free_paras]}'
                    ))

                cur += timedelta(days=1)

            # ── Xulosa va Matematik diagnostika ───────────────────────
            self.stdout.write(f'\n  Xulosa:')
            self.stdout.write(f'    Jami ish kunlari : {total_days}')
            self.stdout.write(f'    To\'liq band kunlar: {problem_days}')
            self.stdout.write(f'    Jami bo\'sh paralar: {total_free}')
            self.stdout.write(f'    Kerak             : {grp.course.total_lessons}')

            if total_free >= grp.course.total_lessons:
                self.stdout.write(self.style.SUCCESS(
                    f'    ✅ Matematik jihatdan MUMKIN '
                    f'(ortiqcha: {total_free - grp.course.total_lessons})'
                ))
            else:
                shortage = grp.course.total_lessons - total_free
                self.stdout.write(self.style.ERROR(
                    f'    ❌ IMKONSIZ — {shortage} ta para yetishmaydi!'
                ))

                # --- Konfliktlarni aniq talabalar kesimida tahlil qilish ---
                self.stdout.write(
                    self.style.WARNING('\n    ⚠️ MATEMATIK TAHLIL (Eng ko\'p to\'sqinlik qilayotgan talabalar):'))

                # Bloklash soni bo'yicha saralaymiz
                sorted_conflicts = sorted(student_block_counts.items(), key=lambda x: x[1], reverse=True)

                for name, count in sorted_conflicts:
                    # O'qituvchi dars o'tishi mumkin bo'lgan jami slotlarning necha foizini shu o'quvchi yopib qo'ygan?
                    impact_percentage = (count / total_teacher_free_slots) * 100 if total_teacher_free_slots > 0 else 0

                    if impact_percentage > 40:  # Agar 40% dan ko'p darsni rad etayotgan bo'lsa (Kritik daraja)
                        self.stdout.write(self.style.ERROR(
                            f'      ❌ {name} — O\'qituvchi bo\'sh bo\'lgan {count} ta parani bloklagan (Konflikt ulushi: {impact_percentage:.1f}%)'
                        ))
                    else:
                        self.stdout.write(
                            f'      🔸 {name} — O\'qituvchi bo\'sh bo\'lgan {count} ta parani bloklagan (Konflikt ulushi: {impact_percentage:.1f}%)'
                        )

                # Tirnoq xatoliklari va bo'lingan satrlar to'liq tuzatildi
                self.stdout.write(self.style.WARNING(
                    "\n    💡 Tavsiya: Yuqoridagi qizil rangli (❌) talabalarni ro'yxatdan vaqtincha chiqarsangiz "
                    "yoki boshqa guruhga o'tkazsangiz, jadval avtomatik tuziladi."
                ))

            self.stdout.write(f'\n{"=" * 70}\n')