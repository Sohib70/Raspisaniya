from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from raspisaniya.models import Student, Teacher


class Command(BaseCommand):
    help = 'Mavjud student va teacherlar uchun User yaratish'

    def handle(self, *args, **kwargs):
        # O'quvchilar
        students = Student.objects.filter(user__isnull=True)
        for student in students:
            if not student.student_id:
                student.student_id = f"S-{student.pk}"
                student.save()

            if User.objects.filter(username=student.student_id).exists():
                self.stdout.write(f"  SKIP (mavjud): {student.student_id}")
                continue

            user = User.objects.create_user(
                username=student.student_id,
                password=student.student_id,  # parol = ID
                first_name=student.first_name,
                last_name=student.last_name,
            )
            student.user = user
            student.save()
            self.stdout.write(self.style.SUCCESS(f"  ✅ O'quvchi: {student} → ID: {student.student_id}"))

        # O'qituvchilar
        teachers = Teacher.objects.filter(user__isnull=True)
        for teacher in teachers:
            if not teacher.teacher_id:
                teacher.teacher_id = f"T-{teacher.pk}"
                teacher.save()

            if User.objects.filter(username=teacher.teacher_id).exists():
                self.stdout.write(f"  SKIP (mavjud): {teacher.teacher_id}")
                continue

            user = User.objects.create_user(
                username=teacher.teacher_id,
                password=teacher.teacher_id,  # parol = ID
                first_name=teacher.first_name,
                last_name=teacher.last_name,
            )
            teacher.user = user
            teacher.save()
            self.stdout.write(self.style.SUCCESS(f"  ✅ O'qituvchi: {teacher} → ID: {teacher.teacher_id}"))

        self.stdout.write(self.style.SUCCESS("\nHammasi tayyor!"))