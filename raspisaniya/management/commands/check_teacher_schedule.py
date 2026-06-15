# raspisaniya/management/commands/check_teacher_schedule.py
#
# Ishlatish:
#   python manage.py check_teacher_schedule "Muxammadiyeva"
#   python manage.py check_teacher_schedule "Muxammadiyeva" --start 2026-05-25 --end 2026-06-22

from django.core.management.base import BaseCommand
from raspisaniya.models import Teacher, CourseGroup, GroupSchedule, PARA_TIMES
from datetime import date, timedelta
from collections import defaultdict


class Command(BaseCommand):
    help = 'O\'qituvchining kun bo\'yicha band paralarini ko\'rsatish'

    def add_arguments(self, parser):
        parser.add_argument('teacher_name', type=str)
        parser.add_argument('--start', type=str, default=None)
        parser.add_argument('--end',   type=str, default=None)

    def handle(self, *args, **options):
        name = options['teacher_name']

        teachers = Teacher.objects.filter(first_name__icontains=name)
        if not teachers.exists():
            self.stdout.write(self.style.ERROR(f'"{name}" topilmadi'))
            return
        if teachers.count() > 1:
            self.stdout.write(self.style.WARNING('Bir nechta topildi:'))
            for t in teachers:
                self.stdout.write(f'  - {t.pk}: {t.first_name}')
            return

        teacher = teachers.first()

        # Muddat
        if options['start']:
            start = date.fromisoformat(options['start'])
        else:
            # Jadval tuzilmagan guruhlarning boshlanish sanasi
            groups = CourseGroup.objects.filter(teacher=teacher, is_scheduled=False)
            if groups.exists():
                start = min(g.course.start_date for g in groups)
            else:
                start = date.today()

        if options['end']:
            end = date.fromisoformat(options['end'])
        else:
            groups = CourseGroup.objects.filter(teacher=teacher, is_scheduled=False)
            if groups.exists():
                end = max(g.course.end_date for g in groups)
            else:
                end = start + timedelta(weeks=4)

        self.stdout.write(f'\n{"="*60}')
        self.stdout.write(f'O\'qituvchi: {teacher}')
        self.stdout.write(f'Muddat    : {start} — {end}')
        self.stdout.write(f'{"="*60}')

        # Jadvalga tuzilgan darslar
        scheds = GroupSchedule.objects.filter(
            group__teacher=teacher,
            date__gte=start,
            date__lte=end,
        ).select_related('group__course__subject').order_by('date', 'start_time')

        # Kun bo'yicha guruhlash
        day_map = defaultdict(list)
        for s in scheds:
            day_map[s.date].append(s)

        # Jadval tuzilmagan guruhlar
        unscheduled = CourseGroup.objects.filter(
            teacher=teacher, is_scheduled=False
        ).select_related('course__subject', 'course')

        self.stdout.write(f'\nJadval tuzilmagan guruhlar:')
        for grp in unscheduled:
            self.stdout.write(self.style.WARNING(
                f'  ❌ {grp.course.subject} {grp.group_number}-guruh '
                f'({grp.course.total_lessons} para kerak, '
                f'{grp.course.start_date}—{grp.course.end_date})'
            ))

        self.stdout.write(f'\nKun bo\'yicha band paralar ({start} — {end}):')
        self.stdout.write(f'{"Sana":<14} {"Kun":<12} {"Band":<6} {"Paralar"}')
        self.stdout.write('-'*60)

        WEEKDAYS = ['Du', 'Se', 'Ch', 'Pa', 'Ju', 'Sh', 'Ya']
        total_band = 0
        full_days  = 0  # 6 ta band bo'lgan kunlar

        cur = start
        while cur <= end:
            if cur.weekday() > 4:
                cur += timedelta(days=1)
                continue

            day_scheds = day_map.get(cur, [])
            band = len(day_scheds)
            total_band += band
            free = 6 - band

            if band == 6:
                full_days += 1
                status = self.style.ERROR('TO\'LIQ BAND')
            elif band >= 4:
                status = self.style.WARNING(f'{free} bo\'sh')
            elif band == 0:
                status = self.style.SUCCESS('bo\'sh')
            else:
                status = f'{free} bo\'sh'

            subjects = ', '.join(
                f'{s.start_time.strftime("%H:%M") if s.start_time else "?"} {s.group.course.subject}'
                for s in day_scheds
            )

            self.stdout.write(
                f'{str(cur):<14} {WEEKDAYS[cur.weekday()]:<12} {band:<6} {status}'
            )
            if subjects:
                self.stdout.write(f'{"":14} {"":12} {"":6} {subjects}')

            cur += timedelta(days=1)

        work_days = sum(
            1 for i in range((end - start).days + 1)
            if (start + timedelta(days=i)).weekday() <= 4
        )
        self.stdout.write(f'\n{"="*60}')
        self.stdout.write(f'Jami ish kunlari : {work_days}')
        self.stdout.write(f'Jami band paralar: {total_band}')
        self.stdout.write(f'Jami bo\'sh paralar: {work_days * 6 - total_band}')
        self.stdout.write(self.style.ERROR(f'To\'liq band kunlar: {full_days}'))
        self.stdout.write(f'{"="*60}\n')