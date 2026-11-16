from ._shared import *
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
import io
from django.shortcuts import get_object_or_404
import openpyxl
from openpyxl.styles import Font, Alignment
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from ..models import Student

class NumberedCanvas(canvas.Canvas):
    """PDF sahifalarining ostiga 'Sahifa X / Y' dinamik raqamini qo'yish uchun"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count):
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#555555"))
        page_text = ""
        self.drawRightString(A4[0] - 30, 20, page_text)


@login_required
def download_vedomost(request, group_id):
    from ..models import CourseGroup, Attendance, Grade
    import io
    import datetime
    from django.http import HttpResponse
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors

    group = get_object_or_404(CourseGroup, pk=group_id)

    start_year = group.course.start_date.year if group.course.start_date else datetime.date.today().year
    end_year = start_year + 1
    oq_yil = f"{start_year}/{end_year}"

    qayta_oqish_status = "1"
    vedomost_no = f"{oq_yil}/{qayta_oqish_status}-{group.pk}"
    qayd_sana = datetime.date.today().strftime("%d.%m.%Y")

    buffer = io.BytesIO()

    # 1. TEPADAN VA PASTDAN KATTA BO'SHLIQLAR (MARGIN) QISQARTIRILDI
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20,
        leftMargin=20,
        topMargin=20,  # 30 dan 20 ga qisqardi
        bottomMargin=20  # 40 dan 20 ga qisqardi
    )

    styles = getSampleStyleSheet()

    # 2. SHRIFTLAR VA QATOR ORALIQLARI (LEADING) BIROZ IXCHAMLASHTIRILDI
    title_style = ParagraphStyle(
        'VTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, leading=14, alignment=1, spaceAfter=2
    )
    subtitle_style = ParagraphStyle(
        'VSub', parent=styles['Normal'], fontName='Helvetica', fontSize=8.5, leading=12, alignment=0, spaceAfter=2
    )
    table_text_style = ParagraphStyle(
        'VText', parent=styles['Normal'], fontName='Helvetica', fontSize=7.5, leading=9
    )
    table_center_text = ParagraphStyle(
        'VCenterText', parent=styles['Normal'], fontName='Helvetica', fontSize=7.5, leading=9, alignment=1
    )
    table_header_style = ParagraphStyle(
        'VHeader', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7.5, leading=9, alignment=1,
        textColor=colors.whitesmoke
    )

    elements = []

    elements.append(Paragraph("TOSHKENT FARMATSEVTIKA INSTITUTI", title_style))
    elements.append(Paragraph(f"BAHOLASH QAYDNOMASI № {vedomost_no}", title_style))
    elements.append(Spacer(1, 5))  # Spacer (ochiq joylar) qisqartirildi

    teacher_str = (
        f"{group.teacher.last_name} {group.teacher.first_name}".strip()
        if group.teacher else "O'qituvchi biriktirilmagan"
    )
    elements.append(Paragraph(f"<b>Fan nomi:</b> {group.course.subject.name}", subtitle_style))
    elements.append(Paragraph(f"<b>Fan o'qituvchisi:</b> {teacher_str}", subtitle_style))
    elements.append(Paragraph(f"<b>Qaydnoma to'ldirilgan sana:</b> {qayd_sana}", subtitle_style))
    elements.append(Spacer(1, 5))

    headers = [
        Paragraph("<b>No</b>", table_header_style),
        Paragraph("<b>Talabaning familiyasi, ismi, sharifi</b>", table_header_style),
        Paragraph("<b>Guruhi</b>", table_header_style),
        Paragraph("<b>JN</b><br/><font size=6>max 30</font>", table_header_style),
        Paragraph("<b>ON</b><br/><font size=6>max 20</font>", table_header_style),
        Paragraph("<b>YN</b><br/><font size=6>max 50</font>", table_header_style),
        Paragraph("<b>Umumiy ball</b><br/><font size=6>max 100</font>", table_header_style),
        Paragraph("<b>Baho</b>", table_header_style),
        Paragraph("<b>O'qituvchi imzosi</b>", table_header_style),
    ]

    table_data = [headers]

    students = list(group.students.select_related('group').order_by('last_name', 'first_name'))
    total_lessons = group.schedule.count()

    grade_map = {
        g.student_id: g
        for g in Grade.objects.filter(course_group=group)
    }
    from django.db.models import Count as _Count
    missed_map = dict(
        Attendance.objects.filter(schedule__group=group, is_present=False)
        .values_list('student_id')
        .annotate(cnt=_Count('id'))
    )

    for idx, student in enumerate(students, 1):
        full_name = f"{student.last_name} {student.first_name}"
        haqiqiy_guruh = student.group.name if student.group else "Mavjud emas"

        grade_obj = grade_map.get(student.id)
        missed_count = missed_map.get(student.id, 0)
        missed_percent = (missed_count / total_lessons * 100) if total_lessons > 0 else 0

        if missed_percent > 25:
            jn = "0";
            on = "0";
            yn = "0";
            umumiy = "0";
            baho = "-"
        else:
            jn_val = grade_obj.current if (grade_obj and grade_obj.current is not None) else 0
            on_val = grade_obj.midterm if (grade_obj and grade_obj.midterm is not None) else 0
            yn_val = grade_obj.final if (grade_obj and grade_obj.final is not None) else 0

            total_val = jn_val + on_val + yn_val
            jn = str(jn_val);
            on = str(on_val);
            yn = str(yn_val);
            umumiy = str(total_val)

            if total_val >= 86:
                baho = "5"
            elif total_val >= 71:
                baho = "4"
            elif total_val >= 56:
                baho = "3"
            else:
                baho = "-"

        table_data.append([
            Paragraph(str(idx), table_center_text),
            Paragraph(f"<b>{full_name}</b>", table_text_style),
            Paragraph(haqiqiy_guruh, table_text_style),
            Paragraph(jn, table_center_text),
            Paragraph(on, table_center_text),
            Paragraph(yn, table_center_text),
            Paragraph(f"<b>{umumiy}</b>", table_center_text),
            Paragraph(baho, table_center_text),
            Paragraph("", table_text_style),
        ])

    # Kengliklar ASL HOLIDA (siz xohlagan holatda) qoldirildi
    col_widths = [28, 155, 72, 35, 35, 35, 50, 60, 65]

    vedomost_table = Table(table_data, colWidths=col_widths, repeatRows=1)

    # 3. ENG MUHIMI: JADVAL QATORLARINING BALANDLIGI QISQARTIRILDI (7 dan 3 ga tushdi)
    vedomost_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1a237e")),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),

        ('TOPPADDING', (0, 0), (-1, -1), 3),  # <--- Shu qisqardi
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),  # <--- Shu qisqardi

        ('ALIGN', (1, 1), (1, -1), 'LEFT'),
        ('ALIGN', (2, 1), (2, -1), 'LEFT'),
    ]))

    elements.append(vedomost_table)
    elements.append(Spacer(1, 8))

    elements.append(Paragraph(f"<b>Jami talabalar soni:</b> {len(students)} ta", subtitle_style))
    elements.append(Spacer(1, 10))

    signature_data = [
        [Paragraph("<b>Fakultet dekani:</b> ___________________________", subtitle_style),
         Paragraph("<b>Kafedra mudiri:</b> ___________________________", subtitle_style)],
    ]
    signature_table = Table(signature_data, colWidths=[265, 265])
    elements.append(signature_table)

    try:
        doc.build(elements, canvasmaker=NumberedCanvas)
    except Exception:
        doc.build(elements)

    buffer.seek(0)
    group_num = getattr(group, 'group_number', group.pk)
    response = HttpResponse(buffer, content_type='application/pdf')
    response[
        'Content-Disposition'] = f'attachment; filename="Qaydnoma_{group.course.subject.name}_{group_num}-guruh.pdf"'
    return response


def format_excel_sheet(ws):
    """Excel jadvalini chiroyli formatlash uchun yordamchi funksiya"""
    ws.row_dimensions[1].height = 28
    for cell in ws[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER_ALIGN

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)   # ✅ to'g'irlandi
        ws.column_dimensions[col_letter].width = max(max_len + 3, 10)
        for cell in col:
            if cell.row > 1:
                cell.alignment = LEFT_ALIGN if cell.column == 1 else CENTER_ALIGN


@login_required
def export_attendance_only_excel(request, group_pk):
    """FAQAT DAVOMATNI EXCELGA YUKLASH"""
    group = get_object_or_404(CourseGroup, pk=group_pk)
    schedules = group.schedule.all().order_by('date', 'lesson_number')
    students = group.students.all().order_by('first_name')
    total_lessons = schedules.count()

    # Barcha davomat yozuvlarini bir martada olib, tez qidirish uchun lug'atga solamiz
    attendance_qs = Attendance.objects.filter(
        schedule__group=group
    ).values('student_id', 'schedule_id', 'is_present')
    att_map = {(a['student_id'], a['schedule_id']): a['is_present'] for a in attendance_qs}

    rows = []
    for student in students:
        cells = []
        came = missed = 0
        for sched in schedules:
            val = att_map.get((student.id, sched.id))
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

        rows.append({
            'student': student,
            'cells': cells,
            'came': came,
            'missed': missed,
            'missed_percent': missed_percent,
            'is_blocked': is_blocked,
        })

    wb = Workbook()
    ws = wb.active
    ws.title = "Davomat"

    headers = ["# Talaba"]
    for sched in schedules:
        headers.append(f"{sched.date.strftime('%d.%m')} / {sched.lesson_number}-dars")
    headers.extend(["Keldi", "Kelmadi", "%"])
    ws.append(headers)

    for idx, row in enumerate(rows, start=1):
        name = f"{idx}. {row['student'].first_name}"
        if row['is_blocked']:
            name += " (bloklangan)"
        row_data = [name]
        for cell in row['cells']:
            if cell == 'present':
                row_data.append("✓")
            elif cell == 'absent':
                row_data.append("✗")
            else:
                row_data.append("—")
        row_data.extend([row['came'], row['missed'], f"{row['missed_percent']}%"])
        ws.append(row_data)

    format_excel_sheet(ws)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename=davomat_{group.group_number}.xlsx'
    wb.save(response)
    return response


@login_required
def export_grades_only_excel(request, group_pk):
    """FAQAT KUNLIK BAHOLARNI EXCELGA YUKLASH"""
    group = get_object_or_404(CourseGroup, pk=group_pk)
    schedules = group.schedule.all().order_by('date', 'lesson_number')
    students = group.students.all().order_by('first_name')
    total_lessons = schedules.count()

    # Har bir darsning JN (30) ichidagi ulushi
    per_lesson_max = (30 / total_lessons) if total_lessons > 0 else 0

    attendance_qs = Attendance.objects.filter(
        schedule__group=group
    ).values('student_id', 'schedule_id', 'is_present')
    att_map = {(a['student_id'], a['schedule_id']): a['is_present'] for a in attendance_qs}

    grade_qs = DailyGrade.objects.filter(
        schedule__group=group
    ).values('student_id', 'schedule_id', 'score')
    grade_map = {(g['student_id'], g['schedule_id']): g['score'] for g in grade_qs}

    rows = []
    for student in students:
        cells = []
        missed = 0
        total_score = 0.0
        for sched in schedules:
            is_present = att_map.get((student.id, sched.id))
            score = grade_map.get((student.id, sched.id))

            if is_present is False:
                missed += 1
                cells.append({'att': 'absent', 'score': None})
            elif score is not None:
                # ✅ TUZATILDI: xom ball emas, 30 balllik tizimga normallashtirilgan qiymat qo'shiladi
                normalized = (score / 100) * per_lesson_max
                total_score += normalized
                cells.append({'att': None, 'score': score})  # jadvalda xom ball ko'rsatiladi
            else:
                cells.append({'att': None, 'score': None})

        missed_percent = round(missed / total_lessons * 100) if total_lessons > 0 else 0
        is_blocked = missed_percent > 25 and not group.teacher_can_edit

        rows.append({
            'student': student,
            'cells': cells,
            'total_score': round(total_score, 2),   # ✅ 2 xonagacha yaxlitlash (masalan 3.38)
            'is_blocked': is_blocked,
        })

    wb = Workbook()
    ws = wb.active
    ws.title = "Kunlik baho"

    headers = ["# Talaba"]
    for sched in schedules:
        headers.append(f"{sched.date.strftime('%d.%m')} / {sched.lesson_number}-dars")
    headers.append("JN (30)")
    ws.append(headers)

    for idx, row in enumerate(rows, start=1):
        name = f"{idx}. {row['student'].first_name}"
        if row['is_blocked']:
            name += " (bloklangan)"
        row_data = [name]
        for cell in row['cells']:
            if cell['att'] == 'absent':
                row_data.append("X")
            elif cell['score'] is not None:
                row_data.append(int(cell['score']))
            else:
                row_data.append("—")
        row_data.append(row['total_score'])
        ws.append(row_data)

    format_excel_sheet(ws)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename=baholar_{group.group_number}.xlsx'
    wb.save(response)
    return response


@login_required
def export_teachers_excel(request):
    """Barcha o'qituvchilar ro'yxati, login va parollarini Excelga yuklash"""
    from ..models import Teacher

    teachers = Teacher.objects.prefetch_related('subjects').all().order_by('first_name')

    wb = Workbook()
    ws = wb.active
    ws.title = "O'qituvchilar loginlari"

    headers = ["#", "F.I.Sh.", "Login (ID)", "Parol", "Fanlari"]
    ws.append(headers)

    for idx, teacher in enumerate(teachers, 1):
        full_name = f"{teacher.last_name} {teacher.first_name}".strip()
        login = teacher.teacher_id or "—"
        # Agar admin ataylab o'zgartirmagan bo'lsa, parol login bilan bir xil bo'ladi
        password = teacher.teacher_id or "—"
        subjects = ", ".join([s.name for s in teacher.subjects.all()])

        ws.append([idx, full_name, login, password, subjects])

    # exports.py dagi format_excel_sheet yordamchi funksiyasidan foydalanamiz
    format_excel_sheet(ws)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="oqituvchilar_login_parollari.xlsx"'
    wb.save(response)
    return response


@login_required
def export_students_excel(request):
    """Barcha talabalar, ularning fanlari va login/parollarini Excelda yuklab olish"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Talabalar"

    # 1. Sarlavhalarga "Fanlar" qo'shildi
    headers = ["T/r", "F.I.Sh.", "Guruhi", "O'zlashtirilmagan fanlar", "Login", "Parol"]
    ws.append(headers)

    for col_num, cell in enumerate(ws[1], 1):
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center")

    # Ustun kengliklari
    ws.column_dimensions['A'].width = 8
    ws.column_dimensions['B'].width = 35
    ws.column_dimensions['C'].width = 15
    ws.column_dimensions['D'].width = 35  # Fanlar uchun kattaroq joy ajratildi
    ws.column_dimensions['E'].width = 20
    ws.column_dimensions['F'].width = 20

    # 2. Bazadan olish: Fanlarni (debts) ham tezkor yuklash uchun prefetch_related qo'shildi
    students = Student.objects.select_related('group', 'user').prefetch_related('debts').all().order_by('group__name',
                                                                                                        'first_name')

    for idx, student in enumerate(students, 1):
        # F.I.Sh.
        full_name = getattr(student, 'first_name', '')
        if hasattr(student, 'last_name') and student.last_name:
            full_name = f"{student.last_name} {full_name}".strip()

        # Guruh nomi
        group_name = student.group.name if student.group else "Guruhsiz"

        # 3. Fanlarni yig'ish (HTML kodingizdagi debts asosida)
        subjects_list = [debt.name for debt in student.debts.all()]
        subjects_str = ", ".join(subjects_list) if subjects_list else "—"

        # 4. Login va Parolni BIR XIL qilish
        username = student.user.username if hasattr(student, 'user') and student.user else "Login yo'q"
        password = username  # <--- Parol aynan Login nima bo'lsa, o'shani oladi

        ws.append([idx, full_name, group_name, subjects_str, username, password])

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="Talabalar_Royxati.xlsx"'
    wb.save(response)

    return response


class NumberedCanvasLandscape(canvas.Canvas):
    """PDF sahifalarining ostiga 'Sahifa X / Y' dinamik raqamini (Landscape - albom shaklida) qo'yish uchun"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count):
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#555555"))
        page_text = ""
        self.drawRightString(841.89 - 15, 10, page_text)


@login_required
def download_journal_pdf(request, group_id):
    """O'qituvchi uchun tayyor kunlik jurnali PDF ko'rinishida yuklab olish"""
    from ..models import CourseGroup, Attendance, DailyGrade

    group = get_object_or_404(CourseGroup, pk=group_id)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=15, leftMargin=15, topMargin=15, bottomMargin=15
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'VTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, leading=12, alignment=1, spaceAfter=6
    )
    subtitle_style = ParagraphStyle(
        'VSub', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, leading=11, alignment=0
    )
    subtitle_right = ParagraphStyle(
        'VSubR', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, leading=11, alignment=2
    )
    text_style = ParagraphStyle(
        'VText', parent=styles['Normal'], fontName='Helvetica', fontSize=7.5, leading=9
    )
    center_text = ParagraphStyle(
        'VCenter', parent=styles['Normal'], fontName='Helvetica', fontSize=7.5, leading=9, alignment=1
    )
    header_style = ParagraphStyle(
        'VHeader', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7.5, leading=9, alignment=1,
        textColor=colors.whitesmoke
    )

    # Lavozim va Ism-familiyalar xuddi rasmga mos chapga (alignment=0) tekislangan
    footer_title_style = ParagraphStyle(
        'VFooterTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=10, alignment=0
    )
    footer_name_style = ParagraphStyle(
        'VFooterName', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10, alignment=0
    )

    elements = []

    elements.append(Paragraph(
        "Toshkent farmatsevtika instituti __________________________________________________________________ qayta o'qish uchun professor-o‘qituvchi jurnali",
        title_style))

    info_table_data = [
        [
            Paragraph(f"<b>Guruh raqami:</b> {group.group_number}", subtitle_style),
            Paragraph(f"<b>Modul nomi:</b> {group.course.subject.name}", subtitle_right)
        ]
    ]
    info_table = Table(info_table_data, colWidths=[405, 405])
    info_table.setStyle(TableStyle([('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
    elements.append(info_table)

    schedules = list(group.schedule.all().order_by('date', 'lesson_number'))
    students = list(group.students.all().order_by('last_name', 'first_name'))

    attendance_qs = Attendance.objects.filter(schedule__group=group).values('student_id', 'schedule_id', 'is_present')
    att_map = {(a['student_id'], a['schedule_id']): a['is_present'] for a in attendance_qs}

    grade_qs = DailyGrade.objects.filter(schedule__group=group).values('student_id', 'schedule_id', 'score')
    grade_map = {(g['student_id'], g['schedule_id']): g['score'] for g in grade_qs}

    headers = [Paragraph("<b>T/r</b>", header_style), Paragraph("<b>F.I.Sh.</b>", header_style)]
    for sched in schedules:
        headers.append(Paragraph(f"<b>{sched.date.strftime('%d.%m')}</b>", header_style))
    table_data = [headers]

    for idx, student in enumerate(students, 1):
        full_name = f"{student.last_name} {student.first_name}".strip()
        row = [Paragraph(str(idx), center_text), Paragraph(full_name, text_style)]
        for sched in schedules:
            is_present = att_map.get((student.id, sched.id))
            score = grade_map.get((student.id, sched.id))

            cell_val = ""
            if is_present is False:
                cell_val = "<b>X</b>"
            elif score is not None:
                cell_val = str(int(score)) if float(score).is_integer() else str(score)
            elif is_present is True:
                cell_val = "✓"

            row.append(Paragraph(cell_val, center_text))
        table_data.append(row)

    teacher_name = f"{group.teacher.last_name} {group.teacher.first_name}".strip() if group.teacher else "________________________"
    footer_row = [
        Paragraph("", text_style),
        Paragraph(f"<b>O'qituvchi F.I.Sh:</b> {teacher_name}<br/><b></b> ", text_style)
    ]
    for _ in schedules:
        footer_row.append(Paragraph("<font color='#555555' size='6'><i></i></font>", center_text))
    table_data.append(footer_row)

    avail_width = 841.89 - 30
    col1_w = 22
    col2_w = 160
    rem_width = avail_width - col1_w - col2_w
    num_lessons = len(schedules)
    lesson_w = (rem_width / num_lessons) if num_lessons > 0 else 40
    col_widths = [col1_w, col2_w] + [lesson_w] * num_lessons

    main_table = Table(table_data, colWidths=col_widths, repeatRows=1)

    main_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#bbbbbb")),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 1), (1, -2), 'LEFT'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1a237e")),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),

        ('VALIGN', (1, -1), (1, -1), 'MIDDLE'),
        ('ALIGN', (1, -1), (1, -1), 'LEFT'),
        ('TOPPADDING', (0, -1), (-1, -1), 4),
        ('BOTTOMPADDING', (0, -1), (-1, -1), 4),
    ]))
    elements.append(main_table)

    # --- MAS'ULLAR RO'YXATI ---
    # --- MAS'ULLAR RO'YXATI ---
    elements.append(Spacer(1, 10))

    # E'tibor bering, har bir qatorda endi 7 ta ustun bor (O'rtadagi "" jadvalni 2 ga bo'lib beradi)
    officials_data = [
        [
            Paragraph("O'quv ishlari bo'yicha prorektor", footer_title_style),
            "",
            Paragraph("Z.U.Mamatqulov", footer_name_style),
            "",  # <--- O'RTADAGI AJRATUVCHI BO'SHLIQ
            Paragraph("Farmatsiya fakulteti dekani", footer_title_style),
            "",
            Paragraph("U.M.Jalilov", footer_name_style)
        ],
        [
            Paragraph("Ta'lim sifatini nazorat qilish bo'limi boshlig'i", footer_title_style),
            "",
            Paragraph("D.K.Xudoyqulova", footer_name_style),
            "",  # <--- O'RTADAGI AJRATUVCHI BO'SHLIQ
            Paragraph("Sanoat farmatsiyasi fakulteti dekani", footer_title_style),
            "",
            Paragraph("E.D.Raxmonov", footer_name_style)
        ],
        [
            Paragraph("O'quv-uslubiy boshqarma boshlig'i", footer_title_style),
            "",
            Paragraph("V.R.Xaydarov", footer_name_style),
            "",  # <--- O'RTADAGI AJRATUVCHI BO'SHLIQ
            Paragraph("Xalqaro va tibbiyot fakulteti dekani", footer_title_style),
            "",
            Paragraph("D.Sh.Sabirov", footer_name_style)
        ],
        [
            Paragraph("Registrator ofis boshlig'i", footer_title_style),
            "",
            Paragraph("Sh.B.Murotov", footer_name_style),
            "",  # <--- O'RTADAGI AJRATUVCHI BO'SHLIQ
            Paragraph("Kafedra mudiri", footer_title_style),
            "",
            Paragraph("_________________", footer_name_style)
        ]
    ]

    col_title1 = 200  # Chap lavozim
    col_sig1 = 15  # Chap imzo uchun ixcham joy (Ism lavozimga yopishadi!)
    col_name1 = 100  # Chap ism

    col_center = 180  # <--- O'RTADAGI KATTA BO'SHLIQ (Jadvalni 2 ga itarib turadi)

    col_title2 = 200  # O'ng lavozim
    col_sig2 = 15  # O'ng imzo uchun ixcham joy
    col_name2 = 100  # O'ng ism

    officials_table = Table(officials_data,
                            colWidths=[col_title1, col_sig1, col_name1, col_center, col_title2, col_sig2, col_name2],
                            hAlign='CENTER')
    officials_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
    ]))

    elements.append(officials_table)

    try:
        doc.build(elements, canvasmaker=NumberedCanvasLandscape)
    except Exception:
        doc.build(elements)

    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response[
        'Content-Disposition'] = f'attachment; filename="Jurnal_{group.course.subject.name}_{group.group_number}-guruh.pdf"'
    return response