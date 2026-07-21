from ._shared import *

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
        page_text = f"Sahifa {self._pageNumber} / {page_count}"
        self.drawRightString(A4[0] - 30, 20, page_text)


@login_required
def download_vedomost(request, group_id):
    # SIKLIK IMPORT (Circular Import) xatoligini oldini olish uchun importni funksiya ichida bajaramiz
    from ..models import CourseGroup, Attendance, Grade
    import io
    import datetime
    from django.http import HttpResponse
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors

    # Guruh ma'lumotlarini bazadan olish
    group = get_object_or_404(CourseGroup, pk=group_id)
    students = group.students.all().order_by('last_name', 'first_name')

    # 1. AVTOMATIK VEDOMOST RAQAMINI SHAKLLANTIRISH
    start_year = group.course.start_date.year if group.course.start_date else datetime.date.today().year
    end_year = start_year + 1
    oq_yil = f"{start_year}/{end_year}"

    qayta_oqish_status = "1"
    vedomost_no = f"{oq_yil}/{qayta_oqish_status}-{group.pk}"

    # Qaydnoma to'ldirilgan sana
    qayd_sana = datetime.date.today().strftime("%d.%m.%Y")

    # PDF sahifasi o'lchamlari (A4)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()

    # Matn va sarlavhalar stillari
    title_style = ParagraphStyle(
        'VTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=12, leading=16, alignment=1, spaceAfter=4
    )
    subtitle_style = ParagraphStyle(
        'VSub', parent=styles['Normal'], fontName='Helvetica', fontSize=9, leading=14, alignment=0, spaceAfter=4
    )

    # Oddiy matnlar stili (F.I.Sh va Haqiqiy guruh uchun - chapga tekislangan)
    table_text_style = ParagraphStyle(
        'VText', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10
    )

    # Raqamlar va baholar stili (No, JN, ON, YN, Jami, Baho uchun - o'rtaga tekislangan)
    table_center_text = ParagraphStyle(
        'VCenterText', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10, alignment=1
    )

    # Jadval sarlavhasi (Header) stili
    table_header_style = ParagraphStyle(
        'VHeader', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=10, alignment=1,
        textColor=colors.whitesmoke
    )

    elements = []

    # Sarlavha qismini shakllantirish
    elements.append(Paragraph("TOSHKENT FARMATSEVTIKA INSTITUTI", title_style))
    elements.append(Paragraph(f"BAHOLASH QAYDNOMASI № {vedomost_no}", title_style))
    elements.append(Spacer(1, 10))

    # Hujjat haqida avtomatik ma'lumotlar
    elements.append(Paragraph(f"<b>Fan nomi:</b> {group.course.subject.name}", subtitle_style))
    elements.append(
        Paragraph(f"<b>Fan o'qituvchisi:</b> {group.teacher.last_name} {group.teacher.first_name}", subtitle_style))
    elements.append(Paragraph(f"<b>Qaydnoma to'ldirilgan sana:</b> {qayd_sana}", subtitle_style))
    elements.append(Spacer(1, 12))

    # Jadval ustunlari sarlavhasi
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

    # Talabalarni aylantirib jadval qatorlarini to'ldirish
    for idx, student in enumerate(students, 1):
        full_name = f"{student.last_name} {student.first_name}"
        haqiqiy_guruh = student.group.name if student.group else "Mavjud emas"

        # Baholarni Grade modelidan olish
        grade_obj = Grade.objects.filter(student=student, course_group=group).first()

        # Davomat foizini aniqlash (25% lik blok sharti uchun)
        total_lessons = group.schedule.count()
        missed_count = Attendance.objects.filter(student=student, schedule__in=group.schedule.all(),
                                                 is_present=False).count()
        missed_percent = (missed_count / total_lessons * 100) if total_lessons > 0 else 0

        # 🌟 O'ZGARISH SHU YERDA: Bloklangan yoki yiqilgan talabaga 2 qo'yilmaydi
        if missed_percent > 25:
            jn = "0"
            on = "0"
            yn = "0"
            umumiy = "0"
            baho = "-"  # "2 (Blok)" o'rniga faqat chiziqcha qoldiramiz
        else:
            jn_val = grade_obj.current if (grade_obj and grade_obj.current is not None) else 0
            on_val = grade_obj.midterm if (grade_obj and grade_obj.midterm is not None) else 0
            yn_val = grade_obj.final if (grade_obj and grade_obj.final is not None) else 0

            total_val = jn_val + on_val + yn_val

            jn = str(jn_val)
            on = str(on_val)
            yn = str(yn_val)
            umumiy = str(total_val)

            # Reyting shkalasi konvertatsiyasi
            if total_val >= 86:
                baho = "5"
            elif total_val >= 71:
                baho = "4"
            elif total_val >= 56:
                baho = "3"
            else:
                baho = "-"  # 56 dan kam bo'lsa ham "2" qo'yilmaydi, bo'sh (chiziqcha) qoladi

        # Qator ma'lumotlarini o'z stillari bilan jadvalga qo'shish
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

    # Ustunlar kengligi
    col_widths = [28, 155, 72, 35, 35, 35, 50, 60, 65]

    vedomost_table = Table(table_data, colWidths=col_widths, repeatRows=1)

    # Jadvalning vizual stillari
    vedomost_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1a237e")),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),

        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),

        ('ALIGN', (1, 1), (1, -1), 'LEFT'),
        ('ALIGN', (2, 1), (2, -1), 'LEFT'),
    ]))

    elements.append(vedomost_table)
    elements.append(Spacer(1, 15))

    # Jami talabalar soni qismi
    elements.append(Paragraph(f"<b>Jami talabalar soni:</b> {len(students)} ta", subtitle_style))
    elements.append(Spacer(1, 20))

    # Imzolar qismi
    signature_data = [
        [Paragraph("<b>Fakultet dekani:</b> ___________________________", subtitle_style),
         Paragraph("<b>Kafedra mudiri:</b> ___________________________", subtitle_style)],
        [Spacer(1, 15), Spacer(1, 15)],
    ]
    signature_table = Table(signature_data, colWidths=[265, 265])
    elements.append(signature_table)

    # PDF faylni qurish — NumberedCanvas shu faylning o'zida (yuqorida)
    # aniqlangan, shuning uchun uni alohida import qilish shart emas.
    # ESKI: `from .utils import NumberedCanvas` — mavjud bo'lmagan modulga
    # ishora qilar edi, shu sababli try/except doim "except" tomonga
    # tushib, sahifa raqamlash hech qachon ishlamas edi.
    try:
        doc.build(elements, canvasmaker=NumberedCanvas)
    except Exception:
        doc.build(elements)  # Agar muammo bo'lsa oddiy build qiladi

    buffer.seek(0)

    # Brauzerga yuklash uchun javob yuborish
    response = HttpResponse(buffer, content_type='application/pdf')
    response[
        'Content-Disposition'] = f'attachment; filename="Qaydnoma_{group.course.subject.name}_{group.group_number}-guruh.pdf"'
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