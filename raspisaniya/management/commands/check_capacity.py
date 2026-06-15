# Bu faylni quyidagi joyga saqlang:
# raspisaniya/management/commands/check_capacity.py
#
# Ishlatish:
#   python manage.py check_capacity

from django.core.management.base import BaseCommand
from raspisaniya.models import CourseGroup, GroupSchedule
from datetime import timedelta
from collections import defaultdict
import math


class Command(BaseCommand):
    help = 'O\'qituvchilar uchun matematik imkoniyat tekshiruvi'

    def handle(self, *args, **kwargs):
        unscheduled = CourseGroup.objects.filter(
            is_scheduled=False
        ).select_related('course__subject', 'teacher', 'course').prefetch_related('students')

        if not unscheduled.exists():
            self.stdout.write(self.style.SUCCESS('✅ Barcha guruhlar jadvalda!'))
            return

        teacher_data = defaultdict(lambda: {'teacher': None, 'groups': [], 'total_needed': 0})

        for grp in unscheduled:
            tid = grp.teacher_id
            teacher_data[tid]['teacher'] = grp.teacher
            teacher_data[tid]['groups'].append(grp)
            teacher_data[tid]['total_needed'] += grp.course.total_lessons

        impossible = []
        possible   = []

        for tid, tdata in teacher_data.items():
            teacher = tdata['teacher']
            groups  = tdata['groups']

            start = min(g.course.start_date for g in groups)
            end   = max(g.course.end_date   for g in groups)

            work_days = sum(
                1 for i in range((end - start).days + 1)
                if (start + timedelta(days=i)).weekday() <= 4
            )

            already_scheduled = GroupSchedule.objects.filter(
                group__teacher=teacher,
                date__gte=start,
                date__lte=end,
            ).count()

            total_slots = work_days * 6
            free_slots  = total_slots - already_scheduled
            needed      = tdata['total_needed']
            shortage    = max(0, needed - free_slots)
            extra_days  = math.ceil(shortage / 6) if shortage > 0 else 0

            info = {
                'teacher':           teacher,
                'groups':            groups,
                'start':             start,
                'end':               end,
                'work_days':         work_days,
                'total_slots':       total_slots,
                'already_scheduled': already_scheduled,
                'free_slots':        free_slots,
                'needed':            needed,
                'shortage':          shortage,
                'extra_days':        extra_days,
            }

            if shortage > 0:
                impossible.append(info)
            else:
                possible.append(info)

        # ── Natijalar ──────────────────────────────────────────────
        self.stdout.write('\n' + '='*70)
        self.stdout.write(f'Jami tekshirildi: {len(teacher_data)} o\'qituvchi')
        self.stdout.write(
            self.style.ERROR(f'❌ Imkonsiz: {len(impossible)} ta') +
            '  |  ' +
            self.style.SUCCESS(f'✅ Mumkin: {len(possible)} ta')
        )
        self.stdout.write('='*70)

        if impossible:
            self.stdout.write(self.style.ERROR('\n--- IMKONSIZ O\'QITUVCHILAR ---'))
            for r in sorted(impossible, key=lambda x: -x['shortage']):
                self.stdout.write('')
                self.stdout.write(self.style.ERROR(
                    f"❌ {r['teacher']}"
                ))
                self.stdout.write(
                    f"   Muddat     : {r['start']} — {r['end']}"
                )
                self.stdout.write(
                    f"   Ish kunlari: {r['work_days']} kun × 6 para = {r['total_slots']} joy"
                )
                self.stdout.write(
                    f"   Band       : {r['already_scheduled']} para"
                )
                self.stdout.write(
                    f"   Bo'sh joy  : {r['free_slots']} para"
                )
                self.stdout.write(self.style.WARNING(
                    f"   Kerak      : {r['needed']} para"
                ))
                self.stdout.write(self.style.ERROR(
                    f"   Yetishmaydi: {r['shortage']} para "
                    f"(+{r['extra_days']} kun kerak)"
                ))
                self.stdout.write('   Guruhlar:')
                for grp in r['groups']:
                    self.stdout.write(
                        f"     - {grp.course.subject} "
                        f"{grp.group_number}-guruh "
                        f"({grp.course.total_lessons} para, "
                        f"{grp.students.count()} talaba)"
                    )
                self.stdout.write(self.style.WARNING(
                    f"   Yechim: muddatni +{r['extra_days']} kun uzaytiring "
                    f"YOKI boshqa o'qituvchiga o'tkazing"
                ))

        if possible:
            self.stdout.write(self.style.SUCCESS('\n--- MUMKIN O\'QITUVCHILAR ---'))
            for r in possible:
                self.stdout.write(self.style.SUCCESS(
                    f"✅ {r['teacher']} — "
                    f"bo'sh: {r['free_slots']}, kerak: {r['needed']}, "
                    f"ortiqcha: {r['free_slots'] - r['needed']}"
                ))

        self.stdout.write('\n' + '='*70 + '\n')