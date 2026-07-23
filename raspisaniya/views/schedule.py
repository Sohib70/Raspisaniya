from ._shared import *
from ..scheduling.busy_index import BusyIndex

def split_into_groups(students, max_size=15, min_size=10):
    total = len(students)
    if total == 0:
        return []
    num_groups = (total + max_size - 1) // max_size
    base_size = total // num_groups
    remainder = total % num_groups
    groups = []
    start = 0
    for i in range(num_groups):
        size = base_size + (1 if i < remainder else 0)
        groups.append(students[start:start + size])
        start += size
    return groups

def _slot_candidates_for_course(total_lessons, include_saturday):
    """
    Kurs turiga (24/16/8 paralik) qarab, talabalarni guruhlashda sinab
    ko'riladigan (hafta_kunlari, para_blok) kombinatsiyalari ro'yxatini beradi.
    """
    max_wd = 5 if include_saturday else 4
    if total_lessons >= 20:
        weekday_sets = [(0, 2, 4)]          # Dush-Chor-Jum
    elif 12 <= total_lessons <= 20:
        weekday_sets = [(1, 3)]             # Sesh-Pay
    else:
        weekday_sets = [(wd,) for wd in range(0, max_wd + 1)]  # istalgan 1 kun

    return [(wds, block) for wds in weekday_sets for block in VALID_PARA_PAIRS]


def _slot_occurrence_dates(start_date, weekday_set, total_lessons):
    """
    Berilgan hafta-kunlari to'plami bo'yicha, kurs davomida HAQIQATDA qaysi
    sanalarda dars bo'lishini hisoblab chiqaradi (kuniga 2 paradan,
    total_lessons soniga yetguncha, keyingi haftalarga davom etib).
    """
    dates = []
    cur_monday = start_date - timedelta(days=start_date.weekday())
    lessons_left = total_lessons
    safety = 0
    while lessons_left > 0 and safety < 60:
        for wd in weekday_set:
            if lessons_left <= 0:
                break
            d = cur_monday + timedelta(days=wd)
            if d < start_date:
                continue
            dates.append(d)
            lessons_left -= min(2, lessons_left)
        cur_monday += timedelta(weeks=1)
        safety += 1
    return dates


LANG_MERGE_THRESHOLD = 8  # bundan kam bo'lsa, til alohida guruh bo'la olmaydi


def _student_direction(student):
    """
    Talabaning fakultet/yo'nalish belgisini qaytaradi (`Student.group` — bu
    akademik guruh/yo'nalish, `CourseGroup` bilan aralashtirmaslik kerak).
    Faqat guruhlarni yo'nalish bo'yicha "imkon qadar" birlashtirish uchun,
    ikkinchi darajali (soft) mezon sifatida ishlatiladi.
    """
    if student.group_id:
        return student.group.name
    return ''


def _sort_by_direction(ids, by_id):
    """
    Bir xil yo'nalishdagi (masalan nomi 'F' bilan boshlanadigan guruhlar)
    talabalarni imkon qadar bitta CourseGroup ichida yig'ish uchun — eng ko'p
    uchraydigan yo'nalishdagi talabalarni ro'yxat boshiga chiqaradi, shunda
    max_size bo'yicha kesib tashlashda ular birga qolish ehtimoli oshadi.
    """
    from collections import Counter
    dirs = {sid: _student_direction(by_id[sid]) for sid in ids}
    counts = Counter(dirs.values())
    return sorted(ids, key=lambda sid: (-counts[dirs[sid]], dirs[sid] or '\uffff'))


def smart_group_students(students, total_lessons, start_date, include_saturday,
                          max_size=15, min_size=10, mandatory_blocks=None):
    """
    Talabalarni RO'YXAT TARTIBIDA emas, balki ularning ALLAQACHON band bo'lgan
    (boshqa fanlardagi) dars vaqtlariga qarab guruhlaydi.

    Mantiq: har bir mumkin bo'lgan (hafta_kunlari, para_bloki) kombinatsiyasi
    uchun — o'sha slotga to'liq mos keladigan (hech qanday band kuni/vaqti
    to'qnashmaydigan) talabalar sonini hisoblaymiz. Eng ko'p talabani "qamrab
    oladigan" slotni tanlab, o'sha talabalardan guruh tuzamiz, so'ng qolganlar
    bilan xuddi shu jarayonni davom ettiramiz.

    `mandatory_blocks` — bir-biridan AJRATIB BO'LMAYDIGAN talabalar to'plami
    ro'yxati (masalan kam sonli til guruhi): har bir blokning barcha a'zolari
    albatta BITTA CourseGroup ichida, birga qoladi (masalan kam sonli rus
    talabalari, o'zbek talabalar bilan birlashtirilganda ham, hech qachon
    2 xil guruhga bo'linib ketmaydi — chunki 2 tilda birdek dars bera oladigan
    o'qituvchilar yetishmasligi mumkin).

    Guruh hajmi qat'iy `min_size`–`max_size` oralig'ida ushlanishga harakat
    qilinadi (standart: 10–15) — juda kichik yoki juda katta guruh avtomatik
    hosil bo'lmaydi, faqat admin qo'lda o'zgartirsa o'zgaradi.

    Natija: har bir guruh, hali `find_schedule_for_group` chaqirilmasdan
    OLDIN, kamida bitta haqiqiy bo'sh umumiy vaqtga ega bo'lishi KAFOLATLANADI
    — shuning uchun keyinchalik "joy topilmadi" holati keskin kamayadi va
    talabalar darslari bir-biriga tushib qolish xavfi yo'qoladi.
    """
    mandatory_blocks = [b for b in (mandatory_blocks or []) if b]
    all_involved = list(students) + [s for block in mandatory_blocks for s in block]
    if not all_involved:
        return []

    # Har bir talabaning haqiqiy band (sana, vaqt) juftliklari
    student_busy = {}
    for st in all_involved:
        student_busy[st.id] = set(
            GroupSchedule.objects.filter(
                group__students=st, group__is_scheduled=True
            ).values_list('date', 'start_time')
        )

    candidates = _slot_candidates_for_course(total_lessons, include_saturday)
    dates_cache = {
        (wds, block): _slot_occurrence_dates(start_date, wds, total_lessons)
        for wds, block in candidates
    }

    def fits(sid, wds, block):
        busy = student_busy[sid]
        p1_time = PARA_TIMES[block[0]][0]
        p2_time = PARA_TIMES[block[1]][0]
        for d in dates_cache[(wds, block)]:
            if (d, p1_time) in busy or (d, p2_time) in busy:
                return False
        return True

    by_id = {st.id: st for st in all_involved}
    remaining = {st.id for st in students}
    groups = []  # {'students': [...], 'slot': (wds, block) | None}

    # ── 1-BOSQICH: majburiy bloklarni (masalan oz sonli til) avval joylashtiramiz.
    # Har biriga eng ko'p qo'shimcha talabani ham qamrab oladigan slot tanlanadi,
    # shunda guruh imkon qadar to'liq (max_size ga yaqin) bo'ladi ──
    for block_students in mandatory_blocks:
        block_ids = [s.id for s in block_students]
        best_key, best_extra = None, []
        for wds, blk in candidates:
            if not all(fits(sid, wds, blk) for sid in block_ids):
                continue
            capacity = max_size - len(block_ids)
            extra = [sid for sid in remaining if fits(sid, wds, blk)] if capacity > 0 else []
            if best_key is None or len(extra) > len(best_extra):
                best_key, best_extra = (wds, blk), extra

        group_students = list(block_students)
        if best_key is not None:
            capacity = max(0, max_size - len(block_students))
            take_extra = _sort_by_direction(best_extra, by_id)[:capacity]
            group_students += [by_id[sid] for sid in take_extra]
            remaining -= set(take_extra)
        groups.append({'students': group_students, 'slot': best_key})

    # ── 2-BOSQICH: qolgan talabalarni, avvalgidek, eng ko'p mos keladigan
    # slot bo'yicha, yo'nalishni imkon qadar hisobga olib guruhlaymiz ──
    while remaining:
        best_key = None
        best_ids = []
        for wds, block in candidates:
            fit_ids = [sid for sid in remaining if fits(sid, wds, block)]
            if len(fit_ids) > len(best_ids):
                best_ids = fit_ids
                best_key = (wds, block)

        if not best_ids:
            # Hech qanday slotga to'liq mos kelmadigan qolgan talabalar —
            # baribir guruh sifatida saqlaymiz (build_schedule bosqichidagi
            # avario-tuzatish algoritmlari ular uchun ishlaydi).
            groups.append({'students': [by_id[sid] for sid in remaining], 'slot': None})
            remaining = set()
            break

        take_ids = _sort_by_direction(best_ids, by_id)[:max_size]
        groups.append({'students': [by_id[sid] for sid in take_ids], 'slot': best_key})
        remaining -= set(take_ids)

    # ── 3-BOSQICH: min_size dan kichik chiqqan guruhlarni, agar mos slotli
    # boshqa guruh topilsa (va max_size dan oshib ketmasa), o'sha guruhga
    # qo'shib yuboramiz — shunda tasodifiy juda kichik guruhlar kamayadi ──
    groups.sort(key=lambda g: len(g['students']))
    merged = []
    for g in groups:
        placed = False
        if len(g['students']) < min_size and g['slot'] is not None:
            for host in merged:
                if host['slot'] is None:
                    continue
                if len(host['students']) + len(g['students']) > max_size:
                    continue
                if all(fits(s.id, host['slot'][0], host['slot'][1]) for s in g['students']):
                    host['students'] += g['students']
                    placed = True
                    break
        if not placed:
            merged.append(g)

    return [g['students'] for g in merged]


def form_course_groups(students_by_lang, total_lessons, start_date, include_saturday,
                        max_size=15, min_size=10, lang_merge_threshold=LANG_MERGE_THRESHOLD):
    """
    Tillar kesimida guruh shakllantirish qoidasi:
      - Agar biror til (masalan rus) talabalari soni `lang_merge_threshold`
        dan kam bo'lsa — ular ALOHIDA guruh bo'la olmaydi, ENG KO'P talaba
        gapiradigan tilga (odatda o'zbek) qo'shib yuboriladi.
      - Lekin shu kam sonli til talabalarining HAMMASI albatta BITTA
        CourseGroup ichida, ajralmagan holda qoladi (`mandatory_blocks`
        orqali) — chunki 2 tilda dars bera oladigan o'qituvchi kam.
      - Yetarlicha katta (>= lang_merge_threshold) til guruhlari odatdagidek
        o'z holicha (aralashtirmasdan) guruhlanadi.

    Qaytaradi: [{'lang': kod, 'lang_name': nom, 'students': [...]}, ...]
    """
    lang_display = dict(LANGUAGE_CHOICES)
    non_empty = {lang: sts for lang, sts in students_by_lang.items() if sts}
    if not non_empty:
        return []

    dominant_lang = max(non_empty, key=lambda l: len(non_empty[l]))
    dominant_students = list(non_empty[dominant_lang])

    result = []

    standalone_langs = {
        lang: sts for lang, sts in non_empty.items()
        if lang != dominant_lang and len(sts) >= lang_merge_threshold
    }
    merge_blocks = [
        sts for lang, sts in non_empty.items()
        if lang != dominant_lang and len(sts) < lang_merge_threshold
    ]

    for lang, sts in standalone_langs.items():
        groups = smart_group_students(sts, total_lessons, start_date, include_saturday,
                                        max_size, min_size)
        for g in groups:
            result.append({'lang': lang, 'lang_name': lang_display.get(lang, lang), 'students': g})

    dominant_groups = smart_group_students(
        dominant_students, total_lessons, start_date, include_saturday,
        max_size, min_size, mandatory_blocks=merge_blocks
    )
    for g in dominant_groups:
        langs_present = sorted({s.language for s in g if s.language})
        if len(langs_present) > 1:
            code = '-'.join(langs_present)
            name = " + ".join(lang_display.get(l, l) for l in langs_present) + " (aralash)"
        else:
            code = dominant_lang
            name = lang_display.get(dominant_lang, dominant_lang)
        result.append({'lang': code, 'lang_name': name, 'students': g})

    return result


def parse_group_langs(lang_value):
    """
    Guruhning `language` maydonidagi tillarni to'plam qilib ajratib beradi.
    Masalan: 'uz' -> {'uz'}; 'ru' -> {'ru'}; 'uz-ru' -> {'uz', 'ru'}.
    Guruhlarni til bo'yicha solishtirishda (masalan parallel-swap uchun nomzod
    qidirishda) aniq matn tengligi ('uz' == 'uz-ru' -> False) o'rniga shu
    to'plamlar KESISHMASINI tekshirish kerak — shunda sof 'uz' guruh bilan
    aralash 'uz-ru' guruh ham bir-biriga mos nomzod sifatida ko'riladi.
    """
    if not lang_value:
        return set()
    return {part for part in lang_value.split('-') if part}


def get_teacher_group_conflict(teacher, target_group, exclude_group=None):
    """
    O'qituvchining `target_group`ga biriktirilishi (yoki target_group
    vaqtlarining o'zgarishi) o'qituvchining boshqa guruhlardagi mavjud
    dars vaqtlari bilan to'qnashib qolmasligini tekshiradi. To'qnashuv
    topilsa (sana, vaqt) juftini, aks holda None qaytaradi.
    """
    if not teacher or not target_group.is_scheduled:
        return None
    target_times = set(
        GroupSchedule.objects.filter(group=target_group).values_list('date', 'start_time')
    )
    if not target_times:
        return None
    busy_qs = GroupSchedule.objects.filter(group__teacher=teacher)
    if exclude_group is not None:
        busy_qs = busy_qs.exclude(group=exclude_group)
    teacher_busy_times = set(busy_qs.values_list('date', 'start_time'))
    conflict_times = target_times & teacher_busy_times
    if conflict_times:
        return sorted(conflict_times)[0]
    return None


def find_schedule_for_group(
        start_date, end_date, total_lessons, lessons_per_week,
        teacher=None, students=None, group_number=1,
        include_saturday=False,
        same_subject_busy=None,
        busy_index=None,   # ← YANGI, ixtiyoriy. Berilmasa — eski xatti-harakat saqlanadi.
):
    from collections import defaultdict
    from datetime import timedelta

    if students is None:
        students = []
    if same_subject_busy is None:
        same_subject_busy = set()

    student_ids = [s.id for s in students]
    student_id_set = set(student_ids)
    teacher_id = teacher.id if teacher else None
    max_wd = 5 if include_saturday else 4
    available_wds = list(range(0, max_wd + 1))

    import itertools

    if total_lessons >= 20:
        # 24 para: Faqat Dush, Chor, Jum
        preferred = [(0, 2, 4)]
        days_needed = 3
    elif 12 <= total_lessons <= 20:
        # 16 para: Faqat Sesh, Pay
        preferred = [(1, 3)]
        days_needed = 2
    else:
        # 8 para: FAQAT bitta kun/hafta, 2 para/hafta (haftada 1 kun 2 para).
        # MUHIM: avvalgi versiya barcha bo'sh kunlarni BITTA pattern'ga yig'ib
        # olardi — bu bitta guruhning bitta haftasiga bir nechta kun (masalan
        # Sesh+Pay) sig'dirib, "haftada 1 kun 2 para" qoidasini buzardi va
        # darslarni kerakidan tezroq (kamroq haftaga) joylashtirib yuborardi.
        # Endi FAQAT bitta kun tanlanadi (days_needed=1). Lekin barcha
        # guruhlar bir xil kunga (odatda Dushanbaga) to'planib qolmasligi
        # uchun boshlang'ich kun guruh raqamiga (group_number) qarab
        # aylantiriladi — 1-guruh Dushanbadan, 2-guruh Seshanbadan va h.k.
        # boshlab qidiradi, shunda guruhlar tabiiy ravishda haftaning turli
        # kunlariga tarqaladi.
        start_offset = (group_number - 1) % len(available_wds)
        rotated_wds = available_wds[start_offset:] + available_wds[:start_offset]
        preferred = [(wd,) for wd in rotated_wds]
        days_needed = 1

    # 2. Qat'iy rejim: Faqat mavjud bo'lgan (start va end date oralig'iga tushadigan)
    # kunlarni filtrlash
    candidate_wd_sets = [c for c in preferred if all(wd in available_wds for wd in c)]

    week_monday = start_date - timedelta(days=start_date.weekday())

    def get_hard_busy(date):
        # YANGI YO'L: busy_index oldindan (build_schedule darajasida, BITTA
        # query bilan) tayyorlangan bo'lsa — SQL umuman yubormaymiz.
        if busy_index is not None:
            busy = set()
            if teacher_id:
                for i in range(len(PARA_TIMES)):
                    if not busy_index.teacher_free(teacher_id, date, i):
                        busy.add(i)
            for sid in student_ids:
                for i in range(len(PARA_TIMES)):
                    if not busy_index.student_free(sid, date, i):
                        busy.add(i)
            return busy

        # ESKI YO'L: busy_index berilmagan bo'lsa (masalan eski chaqiruv
        # joylari hali yangilanmagan bo'lsa), avvalgidek SQL bilan ishlaydi —
        # hech narsa buzilmaydi.
        busy = set()
        if teacher_id:
            for sc in GroupSchedule.objects.filter(
                    date=date, group__teacher_id=teacher_id
            ).select_related('group'):
                st = sc.start_time or sc.group.start_time
                if st:
                    for i, (ps, _) in enumerate(PARA_TIMES):
                        if ps == st:
                            busy.add(i)
                else:
                    busy.update(range(len(PARA_TIMES)))

        if student_ids:
            for sc in GroupSchedule.objects.filter(
                    date=date, group__students__id__in=student_ids
            ).select_related('group').distinct():
                st = sc.start_time or sc.group.start_time
                if st:
                    for i, (ps, _) in enumerate(PARA_TIMES):
                        if ps == st:
                            busy.add(i)
                else:
                    busy.update(range(len(PARA_TIMES)))
        return busy

    def get_subject_busy_paras(date):
        # MUHIM: bu yerda ENDI binary (band/bo'sh) emas, balki HAR BIR parada
        # bitta fanning nechta guruhi allaqachon joylashganini SANAYMIZ.
        # Shu sonlar orqali eng "bo'sh" (kam guruh joylashgan) parani tanlab,
        # guruhlarni bir-biriga teng taqsimlashga erishamiz.
        counts = defaultdict(int)
        for (bd, bt) in same_subject_busy:
            if bd == date:
                for i, (ps, _) in enumerate(PARA_TIMES):
                    if ps == bt:
                        counts[i] += 1
        return counts

    # ── TUZATILGAN: Birinchi haftadan pattern qidirish mantiqi ──
    MAX_GROUPS_PER_SLOT_NO_TEACHER = 4  # o'qituvchisiz bosqichda bitta parada eng ko'pi bilan shuncha guruh joylasha oladi

    def find_best_pair(date):
        hard_busy = get_hard_busy(date)
        subject_busy_counts = get_subject_busy_paras(date)
        strict_candidates = []    # subj_conflicts == 0 (hech kim band qilmagan)
        fallback_candidates = []  # 0 < mavjud guruhlar soni < MAX_GROUPS_PER_SLOT_NO_TEACHER

        for p1, p2 in VALID_PARA_PAIRS:
            # MUHIM: Ustoz yoki TALABA haqiqiy to'qnashuvi endi "ball" emas,
            # balki QAT'IY TAQIQ. Agar shu para juftlikda ustoz yoki talaba
            # boshqa darsga band bo'lsa, bu juftlik UMUMAN ko'rib chiqilmaydi —
            # aks holda bitta talaba bir vaqtda bir necha guruhga tushib qolardi.
            student_conflicts = sum(1 for p in (p1, p2) if p in hard_busy)
            if student_conflicts > 0:
                continue

            subj_conflicts = subject_busy_counts[p1] + subject_busy_counts[p2]
            # Har bir mavjud guruh shu blokka p1 VA p2 ga bittadan yozuv qo'shadi,
            # shuning uchun mavjud guruhlar soni = subj_conflicts / 2
            existing_groups_here = subj_conflicts // 2

            if teacher_id is None:
                # ── Guruhga HALI O'QITUVCHI BIRIKTIRILMAGAN bo'lsa (ish tartibi:
                # guruhlar -> jadval -> keyin o'qituvchi): birinchi navbatda
                # bitta fanning boshqa guruhi band qilmagan (subj_conflicts == 0)
                # parani QAT'IY AFZAL ko'ramiz — shunda odatiy holatda barcha
                # guruhlar bir-biridan HAQIQIY ajratilgan vaqtlarga tushadi va
                # keyinchalik istalgan o'qituvchini istalgan guruhga muammosiz
                # biriktirish mumkin bo'ladi.
                #
                # LEKIN: agar shu kunda BUTUNLAY bo'sh para umuman topilmasa
                # (masalan 16-paralik fan uchun 6 tadan ortiq parallel guruh
                # bo'lib, barcha 6 ta joy allaqachon band bo'lib qolgan bo'lsa)
                # — guruhni "joy yo'q" deb butunlay rad etib qo'ymaymiz. Buning
                # o'rniga, agar shu parada ALLAQACHON MAX_GROUPS_PER_SLOT_NO_TEACHER
                # dan kam guruh tursa (hozircha 4 tagacha) — shu parani ZAXIRA
                # sifatida ishlatishga ruxsat beramiz, ya'ni bitta parada ENG
                # KO'PI BILAN 4 TA guruh birga turishi mumkin. 4 TADAN ORTIQ
                # guruh esa HECH QACHON bitta paraga to'planib qolmaydi — shu
                # holatda para butunlay chetlab o'tiladi va guruh haqiqatan
                # "joy yo'q" deb xabar beradi (keyin avtomatik almashtirish/
                # tarqatish algoritmlari ishga tushadi). Bir parada bir nechta
                # guruh birga qolgan holatda ularga keyinchalik turli
                # o'qituvchilar biriktiriladi (yoki vaqt/talaba almashtirish
                # orqali yechim topiladi).
                if existing_groups_here >= MAX_GROUPS_PER_SLOT_NO_TEACHER:
                    continue
                if subj_conflicts > 0:
                    fallback_candidates.append((subj_conflicts, p1, p2))
                    continue

            # Faqat to'qnashuvsiz (va, agar teacher yo'q bo'lsa, hali 2 taga
            # to'lmagan) paralar orasida — kamroq band bo'lgan parasini
            # tanlaymiz (guruhlarni teng taqsimlash uchun)
            strict_candidates.append((subj_conflicts, p1, p2))

        # ── Avval BUTUNLAY bo'sh joylarni ishlatamiz; ular umuman bo'lmasagina
        # (va faqat shundagina) 4 tagacha guruh turgan "zaxira" joylarga o'tamiz ──
        candidates = strict_candidates if strict_candidates else fallback_candidates

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0])
        best = candidates[0]
        return (best[1], best[2], best[0])

    def get_busy_detailed(date):
        busy = defaultdict(list)
        if teacher_id:
            for sc in GroupSchedule.objects.filter(
                    date=date, group__teacher_id=teacher_id
            ).select_related('group__course__subject', 'group__teacher'):
                st = sc.start_time or sc.group.start_time
                idxs = list(range(len(PARA_TIMES))) if not st else [
                    i for i, (ps, _) in enumerate(PARA_TIMES) if ps == st
                ]
                for i in idxs:
                    busy[i].append({
                        'type': 'teacher', 'group': sc.group,
                        'subject': sc.group.course.subject,
                        'busy_students': []
                    })
        if student_ids:
            for sc in GroupSchedule.objects.filter(
                    date=date, group__students__id__in=student_ids
            ).select_related('group__course__subject', 'group__teacher') \
                    .prefetch_related('group__students').distinct():
                st = sc.start_time or sc.group.start_time
                idxs = list(range(len(PARA_TIMES))) if not st else [
                    i for i, (ps, _) in enumerate(PARA_TIMES) if ps == st
                ]
                busy_sts = [s for s in sc.group.students.all()
                            if s.id in student_id_set]
                for i in idxs:
                    busy[i].append({
                        'type': 'student', 'group': sc.group,
                        'subject': sc.group.course.subject,
                        'busy_students': busy_sts
                    })
        return busy

    # ── FAQAT start_date haftasida pattern qidirish — BARCHA kombinatsiyalar ──
    pattern = []

    for wd_set in candidate_wd_sets:
        trial_pattern = []
        for wd in wd_set:
            d = week_monday + timedelta(days=wd)
            if d < start_date or d > end_date:
                continue
            pair = find_best_pair(d)
            if pair is not None:
                trial_pattern.append((wd, pair[0], pair[1]))

        if len(trial_pattern) >= days_needed:
            pattern = trial_pattern
            break
        # Bu kombinatsiya ishlamadi — keyingisini sinaymiz (natijani tashlab yubormaymiz,
        # faqat eng oxirida hech biri ishlamasa, xabar uchun saqlab qo'yamiz)

    # ── C variant: HECH QANDAY kombinatsiya ishlamadi → xato ───────
    if len(pattern) < days_needed:
        conflict_info = []
        for wd in available_wds:
            d = week_monday + timedelta(days=wd)
            if d < start_date or d > end_date:
                continue
            bd = get_busy_detailed(d)
            for pi, occs in bd.items():
                for occ in occs:
                    conflict_info.append({
                        'date': d,
                        'para_index': pi,
                        'para_time': PARA_TIMES[pi],
                        'type': occ['type'],
                        'group': occ['group'],
                        'subject': occ['subject'],
                        'busy_students': occ['busy_students'],
                    })
        find_schedule_for_group._last_conflict_info = conflict_info
        find_schedule_for_group._last_missing = total_lessons
        find_schedule_for_group._last_no_slot_in_week = True
        return []
    find_schedule_for_group._last_no_slot_in_week = False
    result = []
    cur_monday = week_monday
    while len(result) < total_lessons:
        if cur_monday > end_date + timedelta(weeks=24):
            break

        for (wd, p1, p2) in pattern:
            if len(result) >= total_lessons:
                break

            d = cur_monday + timedelta(days=wd)

            # Sanani tekshiramiz
            if d < start_date or d > end_date:
                continue

            # ✅ YANGI TEKSHIRUV: Agar o'sha kunda ustoz yoki talaba band bo'lsa,
            # darsni o'sha haftada emas, keyingi haftada davom ettirish kerakmi?
            # Yo'q, biz "qat'iy rejim"damiz, shuning uchun darsni yozamiz
            # (chunki biz allaqachon to'qnashuvsiz kunni topganmiz).

            remaining = total_lessons - len(result)

            # Juft para (p1 va p2) mantiqi
            if remaining >= 2:
                result.append((d, PARA_TIMES[p1][0], PARA_TIMES[p1][1]))
                result.append((d, PARA_TIMES[p2][0], PARA_TIMES[p2][1]))
            else:
                # Agar 1 ta dars qolgan bo'lsa
                result.append((d, PARA_TIMES[p1][0], PARA_TIMES[p1][1]))

        cur_monday += timedelta(weeks=1)

    result.sort(key=lambda x: (x[0], x[1]))

    missing = max(0, total_lessons - len(result))
    conflict_info = []

    if missing > 0:
        chk = week_monday
        for _ in range(10):
            if chk > end_date + timedelta(weeks=12):
                break
            for (wd, p1, p2) in pattern:
                d = chk + timedelta(days=wd)
                if d < start_date:
                    continue
                bd = get_busy_detailed(d)
                for pi in (p1, p2):
                    if pi in bd:
                        for occ in bd[pi]:
                            conflict_info.append({
                                'date': d,
                                'para_index': pi,
                                'para_time': PARA_TIMES[pi],
                                'type': occ['type'],
                                'group': occ['group'],
                                'subject': occ['subject'],
                                'busy_students': occ['busy_students'],
                            })
            chk += timedelta(weeks=1)
            if len(conflict_info) >= 30:
                break

    find_schedule_for_group._last_conflict_info = conflict_info
    find_schedule_for_group._last_missing = missing
    return result


def _auto_resolve_via_cross_subject_swap(grp_a, conflicts, group_last_positions=None):
    """
    grp_a joylasha olmayapti — boshqa fanning joylashgan guruhi
    bilan VAQT almashish orqali joy ochadi.

    group_last_positions: dict ko'rinishida guruhlarning oxirgi band qilgan vaqti saqlanadi.
    Shunda guruh faqat o'zining eski vaqtiga qayta olmaydi (Ping-pong bo'lmaydi),
    lekin boshqa istalgan yangi paraga ko'chaveradi.
    """
    if not conflicts:
        return None

    if group_last_positions is None:
        group_last_positions = {}  # {group_id: (date, start_time_string)}

    course = grp_a.course
    start = course.start_date
    week_monday = start - timedelta(days=start.weekday())

    # Kurs darslar soniga qarab kunlarni aniqlash
    if course.total_lessons >= 20:
        needed_wds = [0, 2, 4]  # Dush, Chor, Jum
    elif course.total_lessons >= 12 and course.total_lessons <= 20:
        needed_wds = [1, 3]  # Sesh, Pay
    else:
        needed_wds = list(range(5))

    # conflicts dan qaysi kun/paralar band ekanini aniqlaymiz
    blocked = defaultdict(set)
    for c in conflicts:
        c_date = c.get('date')
        c_pi = c.get('para_index')
        if c_date and c_pi is not None:
            blocked[c_date].add(c_pi)

    for wd in needed_wds:
        d = week_monday + timedelta(days=wd)
        if d < start or d > course.end_date:
            continue
        if d not in blocked:
            continue

        blocked_paras = blocked[d]

        for pi in list(blocked_paras):
            # Shu kunda, shu parada turgan boshqa guruhlarni topamiz
            blocking_scheds = GroupSchedule.objects.filter(
                date=d,
                start_time=PARA_TIMES[pi][0],
                group__is_scheduled=True,
            ).exclude(
                group=grp_a
            ).select_related(
                'group__course__subject', 'group__teacher'
            ).prefetch_related('group__students')

            for b_sched in blocking_scheds:
                b_grp = b_sched.group
                b_teacher_id = b_grp.teacher_id
                b_student_ids = list(b_grp.students.values_list('id', flat=True))

                # b_grp ning juft dars parasini topamiz
                partner_pi = None
                for pp1, pp2 in VALID_PARA_PAIRS:
                    if pp1 == pi:
                        partner_pi = pp2
                        break
                    if pp2 == pi:
                        partner_pi = pp1
                        break

                # b_grp ni ko'chirish mumkin bo'lgan yangi juft parani qidiramiz
                for new_p1, new_p2 in VALID_PARA_PAIRS:
                    # Eski para bilan ustma-ust kelib qolmasin
                    if new_p1 == pi or new_p2 == pi:
                        continue
                    if partner_pi is not None and (new_p1 == partner_pi or new_p2 == partner_pi):
                        continue

                    # ── PING-PONG OLDINI OLISH: Faqat o'zining eski o'rniga qaytishni taqiqlaymiz ──
                    target_time_1 = PARA_TIMES[new_p1][0]
                    last_pos = group_last_positions.get(b_grp.id)
                    if last_pos and last_pos == (d, target_time_1):
                        # Agar guruh xuddi shu kunda, shu paraga qaytayotgan bo'lsa - rad etamiz
                        continue

                    # 1. Yangi parada o'qituvchi band emasmi?
                    if b_teacher_id:
                        t_busy = GroupSchedule.objects.filter(
                            date=d,
                            start_time__in=[PARA_TIMES[new_p1][0], PARA_TIMES[new_p2][0]],
                            group__teacher_id=b_teacher_id,
                        ).exclude(group=b_grp).exists()
                        if t_busy:
                            continue

                    # 2. Yangi parada talabalar band emasmi?
                    if b_student_ids:
                        s_busy = GroupSchedule.objects.filter(
                            date=d,
                            start_time__in=[PARA_TIMES[new_p1][0], PARA_TIMES[new_p2][0]],
                            group__students__id__in=b_student_ids,
                        ).exclude(group=b_grp).exists()
                        if s_busy:
                            continue

                    # ✅ Yangi vaqt topildi -> Ko'chiramiz
                    with transaction.atomic():
                        moved = False

                        # Eski joylashuvni xotiraga yozamiz (Qaytmasligi uchun qulflash)
                        current_time = PARA_TIMES[pi][0]
                        group_last_positions[b_grp.id] = (d, current_time)

                        # 1-parani ko'chirish
                        s1 = GroupSchedule.objects.filter(
                            date=d, group=b_grp,
                            start_time=current_time
                        ).first()
                        if s1:
                            s1.start_time = target_time_1
                            s1.save(update_fields=['start_time'])
                            moved = True

                        # 2-parani ko'chirish
                        if partner_pi is not None:
                            s2 = GroupSchedule.objects.filter(
                                date=d, group=b_grp,
                                start_time=PARA_TIMES[partner_pi][0]
                            ).first()
                            if s2:
                                s2.start_time = PARA_TIMES[new_p2][0]
                                s2.save(update_fields=['start_time'])

                    if moved:
                        # ✅ Tuzatildi: O'qituvchi ismi obyektning o'zini stringga o'girish orqali xavfsiz olindi
                        b_teacher_name = str(b_grp.teacher) if b_grp.teacher else "O'qituvchi biriktirilmagan"
                        return (
                            f"⚡ Fano'g'ri almashtirish (Cross-Subject): '{b_grp.course.subject}' fani "
                            f"'{b_grp.group_number}-guruh' ({b_teacher_name}) {d.strftime('%d.%m.%Y')} kunidagi "
                            f"{pi + 1}-paradan {new_p1 + 1}-paraga muvaffaqiyatli ko'chirildi."
                        )
    return None

def _brute_force_find_slot(grp_a):
    """
    grp_a uchun joy qidiradi. Barcha `is_scheduled=True` guruhlarni
    birin-ketin ko'rib chiqadi va ularni boshqa bo'sh joyga surishga harakat qiladi.
    """
    course = grp_a.course
    start = course.start_date
    end = course.end_date
    week_monday = start - timedelta(days=start.weekday())
    include_saturday = getattr(course, 'include_saturday', False)
    max_wd = 5 if include_saturday else 4

    if course.total_lessons >= 20:
        needed_wds = [wd for wd in (0, 2, 4) if wd <= max_wd]
    elif course.total_lessons >= 12:
        needed_wds = [wd for wd in (1, 3) if wd <= max_wd]
    else:
        needed_wds = list(range(max_wd + 1))

    grp_a_teacher_id = grp_a.teacher_id
    grp_a_student_ids = list(grp_a.students.values_list('id', flat=True))

    needed_slots = []  # [(date, para_idx), ...]
    for wd in needed_wds:
        d = week_monday + timedelta(days=wd)
        if d < start or d > end:
            continue
        for pi in range(len(PARA_TIMES)):
            blocked_by_teacher = False
            blocked_by_student = False

            if grp_a_teacher_id:
                blocked_by_teacher = GroupSchedule.objects.filter(
                    date=d,
                    start_time=PARA_TIMES[pi][0],
                    group__teacher_id=grp_a_teacher_id,
                ).exclude(group=grp_a).exists()

            if grp_a_student_ids and not blocked_by_teacher:
                blocked_by_student = GroupSchedule.objects.filter(
                    date=d,
                    start_time=PARA_TIMES[pi][0],
                    group__students__id__in=grp_a_student_ids,
                ).exclude(group=grp_a).exists()

            if blocked_by_teacher or blocked_by_student:
                needed_slots.append((d, pi))

    if not needed_slots:
        return None

    all_scheduled = list(
        CourseGroup.objects.filter(
            is_scheduled=True,
        ).exclude(
            pk=grp_a.pk,
        ).select_related(
            'course__subject', 'teacher'
        ).prefetch_related('students')
        .order_by('pk')
    )

    if not all_scheduled:
        return None

    visited = set()
    queue = list(all_scheduled)

    while queue:
        blocker = queue.pop(0)

        if blocker.pk in visited:
            continue
        visited.add(blocker.pk)

        b_teacher_id = blocker.teacher_id
        b_student_ids = list(blocker.students.values_list('id', flat=True))

        blocker_slots = []
        for wd in needed_wds:
            d = week_monday + timedelta(days=wd)
            if d < start or d > end:
                continue
            for sc in GroupSchedule.objects.filter(date=d, group=blocker):
                st = sc.start_time or blocker.start_time
                if not st:
                    continue
                for i, (ps, _) in enumerate(PARA_TIMES):
                    if ps == st:
                        is_problem = (d, i) in needed_slots
                        if is_problem:
                            blocker_slots.append((d, i, sc))

        if not blocker_slots:
            continue

        blocker_current_paras = defaultdict(set)
        for sc2 in GroupSchedule.objects.filter(
                date__gte=start, date__lte=end, group=blocker
        ):
            st2 = sc2.start_time or blocker.start_time
            if st2:
                for i, (ps, _) in enumerate(PARA_TIMES):
                    if ps == st2:
                        blocker_current_paras[sc2.date].add(i)

        for (prob_date, prob_pi, prob_sc) in blocker_slots:
            blk_own_paras = blocker_current_paras.get(prob_date, set())

            partner_pis = []
            for pp1, pp2 in VALID_PARA_PAIRS:
                if pp1 == prob_pi:
                    partner_pis.append(pp2)
                elif pp2 == prob_pi:
                    partner_pis.append(pp1)
            partner_pi = partner_pis[0] if partner_pis else None

            blk_others_busy = set()
            if b_teacher_id:
                for sc3 in GroupSchedule.objects.filter(
                        date=prob_date, group__teacher_id=b_teacher_id
                ).exclude(group=blocker):
                    st3 = sc3.start_time or sc3.group.start_time
                    if st3:
                        for i, (ps, _) in enumerate(PARA_TIMES):
                            if ps == st3:
                                blk_others_busy.add(i)
            if b_student_ids:
                for sc3 in GroupSchedule.objects.filter(
                        date=prob_date,
                        group__students__id__in=b_student_ids,
                ).exclude(group=blocker).distinct():
                    st3 = sc3.start_time or sc3.group.start_time
                    if st3:
                        for i, (ps, _) in enumerate(PARA_TIMES):
                            if ps == st3:
                                blk_others_busy.add(i)

            grp_a_busy_today = set()
            if grp_a_teacher_id:
                for sc3 in GroupSchedule.objects.filter(
                        date=prob_date, group__teacher_id=grp_a_teacher_id
                ).exclude(group=grp_a):
                    st3 = sc3.start_time or sc3.group.start_time
                    if st3:
                        for i, (ps, _) in enumerate(PARA_TIMES):
                            if ps == st3:
                                grp_a_busy_today.add(i)
            if grp_a_student_ids:
                for sc3 in GroupSchedule.objects.filter(
                        date=prob_date,
                        group__students__id__in=grp_a_student_ids,
                ).exclude(group=grp_a).distinct():
                    st3 = sc3.start_time or sc3.group.start_time
                    if st3:
                        for i, (ps, _) in enumerate(PARA_TIMES):
                            if ps == st3:
                                grp_a_busy_today.add(i)

            for new_p1, new_p2 in VALID_PARA_PAIRS:
                if new_p1 in blk_own_paras or new_p2 in blk_own_paras:
                    continue
                if new_p1 in blk_others_busy or new_p2 in blk_others_busy:
                    continue
                if new_p1 in grp_a_busy_today or new_p2 in grp_a_busy_today:
                    continue
                needed_pis_today = {pi for (d, pi) in needed_slots if d == prob_date}
                if new_p1 in needed_pis_today or new_p2 in needed_pis_today:
                    continue

                try:
                    with transaction.atomic():
                        moved_count = 0

                        s1 = GroupSchedule.objects.filter(
                            date=prob_date,
                            group=blocker,
                            start_time=PARA_TIMES[prob_pi][0],
                        ).first()
                        if s1:
                            s1.start_time = PARA_TIMES[new_p1][0]
                            s1.save(update_fields=['start_time'])
                            moved_count += 1

                        if partner_pi is not None:
                            s2 = GroupSchedule.objects.filter(
                                date=prob_date,
                                group=blocker,
                                start_time=PARA_TIMES[partner_pi][0],
                            ).first()
                            if s2:
                                s2.start_time = PARA_TIMES[new_p2][0]
                                s2.save(update_fields=['start_time'])
                                moved_count += 1
                            else:
                                raise ValueError("Juft para topilmadi")

                        if moved_count == 0:
                            raise ValueError("Ko'chiriladigan dars yo'q")

                except (ValueError, Exception):
                    continue

                # ✅ TUZATILDI: Muvaffaqiyatli xabar matni to'liq shakllantirildi
                old_t = PARA_TIMES[prob_pi][0].strftime('%H:%M')
                new_t = PARA_TIMES[new_p1][0].strftime('%H:%M')
                b_teacher_name = str(blocker.teacher) if blocker.teacher else "O'qituvchi biriktirilmagan"
                return (
                    f"⚡ Brute-force muvaffaqiyatli: '{blocker.course.subject}' fani "
                    f"'{blocker.group_number}-guruh' ({b_teacher_name}) {prob_date.strftime('%d.%m.%Y')} kunidagi "
                    f"soat {old_t} dars vaqti {new_t} ga surildi va '{grp_a.course.subject}' uchun joy ochildi."
                )

    return None

# ... avvalgi yordamchi funksiyalar (subject_swap, parallel_swap, cross_subject_swap, brute_force) ...


# ── 1. SHU YERGA YANGI MAJBURIY CHIQARISH FUNKSIYASINI JOYLASHTIRING ──
def _auto_resolve_by_force_student_eviction(grp_a, conflicts, same_course_groups):
    """
    Agar grp_a guruhiga dars qo'yishga ziddiyat keltirib chiqarayotgan talabalar soni
    juda kam bo'lsa (1 tadan 3 tagacha), ularni ushbu guruhdan majburlab chiqaradi va
    boshqa ziddiyatsiz parallel guruhlarga tarqatadi.
    Guruh hajmi chegaralari: MIN_GROUP_SIZE / MAX_GROUP_SIZE (yuqorida belgilangan).
    """
    if not conflicts:
        return None

    eviction_candidates = set()
    for c in conflicts:
        if c.get('type') == 'student':
            for st in c.get('busy_students', []):
                if grp_a.students.filter(pk=st.pk).exists():
                    eviction_candidates.add(st)

    if not eviction_candidates or len(eviction_candidates) > 3:
        return None

    other_groups = [g for g in same_course_groups if g.pk != grp_a.pk]
    if not other_groups:
        return None

    migrations = []
    temp_counts = {g.pk: g.students.count() for g in other_groups}

    for st in eviction_candidates:
        moved = False
        for target_grp in other_groups:
            if temp_counts[target_grp.pk] + 1 > MAX_GROUP_SIZE:
                continue

            if target_grp.is_scheduled:
                target_times = set(
                    GroupSchedule.objects.filter(group=target_grp).values_list('date', 'start_time')
                )
                student_busy = set(
                    GroupSchedule.objects.filter(group__students=st)
                    .exclude(group=grp_a)
                    .values_list('date', 'start_time')
                )
                if student_busy & target_times:
                    continue

            migrations.append((st, target_grp))
            temp_counts[target_grp.pk] += 1
            moved = True
            break

        if not moved:
            return None

    # Guruhda kamida MIN_GROUP_SIZE ta o'quvchi qolishi shart!
    if (grp_a.students.count() - len(eviction_candidates)) < MIN_GROUP_SIZE:
        return None

    with transaction.atomic():
        evicted_names = []
        affected_groups = {grp_a}
        for st, target_grp in migrations:
            grp_a.students.remove(st)
            target_grp.students.add(st)
            affected_groups.add(target_grp)
            evicted_names.append(f"{st.first_name} (-> {target_grp.group_number}-guruh)")

        for g in affected_groups:
            sync_group_language(g)

        evicted_str = ", ".join(evicted_names)
        return (
            f"🔄 Majburiy ko'chirish: '{grp_a}' guruhiga dars qo'yilishiga xalaqit berayotgan "
            f"kam sonli talabalar {evicted_str} boshqa guruhlarga surildi (guruh tarkibi 8 tadan kam bo'lib qolmadi)."
        )


def _try_dissolve_and_distribute_group(grp, same_course_groups):
    """
    Muammoli grp guruhini o'chirib, uning talabalarini boshqa guruhlarga tarqatadi.
    Faqat barcha talabalar muvaffaqiyatli joylashsa (sig'im <= MAX_GROUP_SIZE va
    dars vaqti to'qnashuvlarisiz), o'zgarishni bazada saqlaydi. Aks holda rad etadi (Rollback).
    """
    students_to_distribute = list(grp.students.all())
    other_groups = [g for g in same_course_groups if g.pk != grp.pk]

    if not other_groups:
        return False, "Tarqatish uchun boshqa parallel guruhlar yo'q."

    # Guruhlar sig'imi va talabalar ro'yxatini xotirada vaqtincha simulyatsiya qilamiz
    temp_assignments = {g.pk: list(g.students.all()) for g in other_groups}

    for student in students_to_distribute:
        distributed = False
        for target_grp in other_groups:
            current_students_in_target = temp_assignments[target_grp.pk]

            # 1. Yangi sig'im tekshiruvi
            if len(current_students_in_target) >= MAX_GROUP_SIZE:
                continue

            # 2. Agar maqsadli guruh allaqachon dars jadvaliga ega bo'lsa, talabaning vaqti mos keladimi?
            if target_grp.is_scheduled:
                target_times = set(
                    GroupSchedule.objects.filter(group=target_grp).values_list('date', 'start_time')
                )
                student_busy = set(
                    GroupSchedule.objects.filter(group__students=student)
                    .exclude(group=grp)  # joriy o'chirilayotgan guruh darslarini hisobga olmaymiz
                    .values_list('date', 'start_time')
                )
                # Agar talaba maqsadli guruh dars vaqtida band bo'lsa, bu guruhga qo'sha olmaymiz
                if student_busy & target_times:
                    continue

            # Shartlar bajarilsa, talabani vaqtincha shu guruhga yozamiz
            current_students_in_target.append(student)
            distributed = True
            break

        if not distributed:
            # Bitta talaba bo'lsa ham joylasha olmay qolsa, tarqatishni butunlay bekor qilamiz
            return False, f"Ba'zi talabalar guruh sig'imi (max {MAX_GROUP_SIZE}) yoki dars vaqti to'qnashuvi sababli boshqa guruhlarga sig'madi."

    # Hamma muvaffaqiyatli tarqaldi -> o'zgarishlarni bazada atomar saqlaymiz
    with transaction.atomic():
        for target_grp in other_groups:
            target_grp.students.set(temp_assignments[target_grp.pk])
            sync_group_language(target_grp)

        # Eski muammoli guruhni butunlay o'chirib tashlaymiz
        GroupSchedule.objects.filter(group=grp).delete()
        grp.delete()

    return True, f"'{grp}' guruhi dars jadvalida bo'sh joy topilmagani sababli tarqatib yuborildi. Talabalar qolgan guruhlarga muvaffaqiyatli qo'shildi."


def _try_deep_cascade_relocate(grp, course, teacher, max_depth=12, max_nodes=400):
    """
    ENG SO'NGGI, ENG CHUQUR CHORA — foydalanuvchi so'roviga ko'ra:
    "yo'q qil, joy topish yo'li qanday bo'lsa ham hammasini ko'rib chiq,
    10-11 bosqich bo'lsa ham qil".

    `_try_relocate_blocking_groups`dan farqi: o'sha funksiya faqat BITTA
    bosqichli ko'chirishga urinadi (to'siq guruhni ko'chirish uchun uning
    o'zi albatta bo'sh joy topishi kerak). Bu funksiya esa REKURSIV
    zanjir quradi: agar to'siq guruhning o'zi ham band bo'lsa, UNI
    bloklayotgan guruh(lar)ni ham ko'chirishga urinadi, va h.k. —
    `max_depth` (standart 12) bosqichgacha.

    Butun zanjir XOTIRADA (`virtual` lug'at orqali) simulyatsiya
    qilinadi — hech narsa bazaga yozilmaydi, toki BUTUN zanjir охиригача
    muvaffaqiyatli bo'lmaguncha. Faqat to'liq ishlagan yechim topilsa,
    barcha ishtirokchi guruhlar bitta atomik tranzaksiyada saqlanadi.

    Xavfsizlik: `max_nodes` — umumiy rekursiv chaqiruvlar soni chegarasi
    (juda katta/zich ma'lumotlarda cheksiz qidiruvning oldini olish uchun).
    """
    node_counter = {'count': 0}

    def get_weekday_options(total_lessons, include_saturday):
        max_wd = 5 if include_saturday else 4
        if total_lessons >= 20:
            return [(0, 2, 4)]
        elif 12 <= total_lessons <= 20:
            return [(1, 3)]
        else:
            return [(wd,) for wd in range(0, max_wd + 1)]

    def real_slots(group_id):
        return set(GroupSchedule.objects.filter(group_id=group_id).values_list('date', 'start_time'))

    def effective_slots(group_id, virtual):
        if group_id in virtual:
            wds, p1, p2, dates = virtual[group_id]
            return (set((d, PARA_TIMES[p1][0]) for d in dates)
                     | set((d, PARA_TIMES[p2][0]) for d in dates))
        return real_slots(group_id)

    def find_blockers(students, dates, times, virtual, exclude_group_id):
        student_ids = set(s.id for s in students)
        target_set = {(d, t) for d in dates for t in times}
        relevant = set(
            GroupSchedule.objects.filter(
                group__students__id__in=student_ids
            ).values_list('group_id', flat=True).distinct()
        ) | set(virtual.keys())
        relevant.discard(exclude_group_id)

        blockers = set()
        for gid in relevant:
            g_student_ids = set(
                CourseGroup.objects.get(pk=gid).students.values_list('id', flat=True)
            )
            if not (g_student_ids & student_ids):
                continue
            if effective_slots(gid, virtual) & target_set:
                blockers.add(gid)
        return blockers

    def try_place(g, g_course, g_teacher, virtual, locked, depth):
        node_counter['count'] += 1
        if node_counter['count'] > max_nodes or depth > max_depth:
            return False

        students = list(g.students.all())
        if len(students) < MIN_GROUP_SIZE:
            return False
        teacher_id = g_teacher.id if g_teacher else None
        total_lessons = g_course.total_lessons
        include_saturday = getattr(g_course, 'include_saturday', False)
        wd_options = get_weekday_options(total_lessons, include_saturday)

        candidates = []
        for wds in wd_options:
            dates = _slot_occurrence_dates(g_course.start_date, wds, total_lessons)
            if not dates:
                continue
            for (p1, p2) in VALID_PARA_PAIRS:
                if g.is_scheduled and tuple(g.weekdays or []) == wds and PARA_TIMES[p1][0] == g.start_time:
                    continue  # bu o'zining hozirgi joyi
                times = [PARA_TIMES[p1][0], PARA_TIMES[p2][0]]
                if teacher_id and GroupSchedule.objects.filter(
                    date__in=dates, start_time__in=times, group__teacher_id=teacher_id
                ).exclude(group=g).exists():
                    continue
                blockers = find_blockers(students, dates, times, virtual, g.pk)
                candidates.append((len(blockers), wds, p1, p2, dates, blockers))

        candidates.sort(key=lambda c: c[0])

        for _, wds, p1, p2, dates, blockers in candidates:
            if not blockers:
                virtual[g.pk] = (wds, p1, p2, dates)
                return True

            if g.pk in locked:
                continue

            new_locked = locked | {g.pk}
            saved_keys = set(virtual.keys())
            all_resolved = True
            for bgid in blockers:
                if bgid in new_locked:
                    all_resolved = False
                    break
                bg = CourseGroup.objects.select_related('course__subject', 'teacher').get(pk=bgid)
                if not bg.course:
                    all_resolved = False
                    break
                if not try_place(bg, bg.course, bg.teacher, virtual, new_locked, depth + 1):
                    all_resolved = False
                    break

            if all_resolved:
                virtual[g.pk] = (wds, p1, p2, dates)
                return True
            else:
                for k in list(virtual.keys()):
                    if k not in saved_keys:
                        del virtual[k]

        return False

    virtual = {}
    ok = try_place(grp, course, teacher, virtual, set(), 0)
    if not ok or not virtual:
        return False, None

    # ── Barcha zanjir a'zolarini bitta atomik tranzaksiyada saqlaymiz ──
    moved_names = []
    with transaction.atomic():
        for gid, (wds, p1, p2, dates) in virtual.items():
            g2 = CourseGroup.objects.get(pk=gid)
            t1, t2 = PARA_TIMES[p1][0], PARA_TIMES[p2][0]
            g2.weekdays = list(wds)
            g2.start_time = t1
            g2.is_scheduled = True
            g2.save()
            sync_group_language(g2)
            GroupSchedule.objects.filter(group=g2).delete()
            GroupSchedule.objects.bulk_create([
                GroupSchedule(group=g2, date=d, start_time=t1, lesson_number=2 * i + 1)
                for i, d in enumerate(dates)
            ] + [
                GroupSchedule(group=g2, date=d, start_time=t2, lesson_number=2 * i + 2)
                for i, d in enumerate(dates)
            ])
            if gid != grp.pk:
                moved_names.append(str(g2))

    if moved_names:
        msg = (
            f"'{grp}' guruhi CHUQUR ZANJIRLI qidiruv orqali joylashtirildi — "
            f"buning uchun {len(moved_names)} ta guruh zanjir bo'ylab boshqa vaqtga "
            f"ko'chirildi: {', '.join(moved_names)}."
        )
    else:
        msg = f"'{grp}' guruhi to'liq bo'sh vaqtga joylashtirildi."
    return True, msg


def _try_relocate_blocking_groups(grp, course, teacher):
    """
    YANGI, ENG KUCHLI ZANJIRLI CHORA — foydalanuvchi so'rovi bo'yicha:
    "eng kam xato ko'rsatgan vaqtni aniqlab, shu vaqtga to'sqinlik
    qilayotgan talabalarni boshqa guruhga o'tkazing yoki almashtiring;
    bo'lmasa — o'sha boshqa guruhning O'ZINI boshqa joyga ko'chiring".

    Farqi `_try_minimal_disruption_swap`dan: o'sha funksiya to'siq
    talabani xuddi SHU FANNING boshqa GURUHIGA almashtirar edi (agar
    parallel guruh bo'lsa). Bu funksiya esa — agar parallel guruh
    UMUMAN BO'LMASA (masalan yolg'iz 18 kishilik guruh) — to'siq
    qiluvchi talabani band qilib turgan BOSHQA FANNING guruhini
    TOPIB, O'SHA guruhning o'zini (agar imkoni bo'lsa) BOSHQA vaqtga
    ko'chiradi — shu orqali to'siq talaba ozod bo'ladi.

    Xavfsizlik: ko'chiriladigan "to'siq guruh" boshqa joyga ko'chganda,
    UNING o'z a'zolari uchun YANGI to'qnashuv yaratmasligi kifoya
    tekshiriladi. Faqat BARCHA to'siq guruhlar muvaffaqiyatli
    ko'chirilsa (yoki umuman to'siq bo'lmasa) — natija saqlanadi.
    """
    students = list(grp.students.all())
    # ── MUHIM BUG TUZATISH: MIN_GROUP_SIZE tekshiruvi yo'q edi! Bu funksiya
    # guruh a'zoligini o'zgartirmaydi (faqat BOSHQA guruhlarni ko'chiradi),
    # shuning uchun agar `grp`ning o'zi allaqachon MIN_GROUP_SIZE dan kam
    # bo'lsa (masalan qayta guruhlashdan qolgan 4 kishilik "qoldiq"), bu
    # funksiya uni baribir "muvaffaqiyatli" deb belgilab qo'yishi mumkin
    # edi — bu sizning 8-18 qoidangizni ochiqchasiga buzardi.
    if len(students) < MIN_GROUP_SIZE:
        return False, None

    student_ids = set(s.id for s in students)
    teacher_id = teacher.id if teacher else None
    total_lessons = course.total_lessons
    start_date = course.start_date
    include_saturday = getattr(course, 'include_saturday', False)
    max_wd = 5 if include_saturday else 4

    if total_lessons >= 20:
        weekday_options = [(0, 2, 4)]
    elif 12 <= total_lessons <= 20:
        weekday_options = [(1, 3)]
    else:
        weekday_options = [(wd,) for wd in range(0, max_wd + 1)]

    # ── 1-BOSQICH: eng kam to'siqli vaqtni topish (blocker GURUHLAR bilan) ──
    candidates = []
    for wds in weekday_options:
        dates = _slot_occurrence_dates(start_date, wds, total_lessons)
        if not dates:
            continue
        for (p1, p2) in VALID_PARA_PAIRS:
            times = [PARA_TIMES[p1][0], PARA_TIMES[p2][0]]
            if teacher_id and GroupSchedule.objects.filter(
                date__in=dates, start_time__in=times, group__teacher_id=teacher_id,
            ).exclude(group=grp).exists():
                continue
            # ── MUHIM TUZATISH: bu yerda ham "bitta fandan bir parada
            # MAX_GROUPS_PER_SLOT_NO_TEACHER (4) tadan ortiq guruh
            # bo'lmasin" chegarasi yo'q edi — grp shu funksiya orqali
            # allaqachon 4 ta guruh bilan to'lgan slotga ham joylashib
            # qolishi mumkin edi (agar u yerda haqiqiy talaba to'qnashuvi
            # bo'lmasa). Endi bunday to'lgan slotlar chetlab o'tiladi.
            if teacher_id is None:
                existing_same_subject = GroupSchedule.objects.filter(
                    date__in=dates, start_time__in=times,
                    group__course__subject=course.subject,
                    group__is_scheduled=True,
                ).exclude(group=grp).values_list('group_id', flat=True).distinct().count()
                if existing_same_subject >= 4:  # MAX_GROUPS_PER_SLOT_NO_TEACHER
                    continue
            blocking_group_ids = set(GroupSchedule.objects.filter(
                date__in=dates, start_time__in=times, group__students__id__in=student_ids,
            ).exclude(group=grp).values_list('group_id', flat=True))
            candidates.append((len(blocking_group_ids), wds, p1, p2, dates, blocking_group_ids))

    if not candidates:
        return False, None

    candidates.sort(key=lambda c: c[0])
    _, wds, p1, p2, dates, blocking_group_ids = candidates[0]
    times = [PARA_TIMES[p1][0], PARA_TIMES[p2][0]]

    if not blocking_group_ids:
        return False, None  # (bu holat allaqachon boshqa funksiyalar tomonidan qamrab olingan)

    # ── 2-BOSQICH: har bir to'siq guruh uchun muqobil vaqt qidirish ──
    relocations = []  # [(blocking_grp, new_wds, new_p1, new_p2, new_dates), ...]
    for bgid in blocking_group_ids:
        bg = CourseGroup.objects.select_related('course', 'course__subject').get(pk=bgid)
        if not bg.course:
            return False, None
        bg_students = list(bg.students.all())
        bg_teacher_id = bg.teacher_id
        bg_total = bg.course.total_lessons
        bg_include_sat = getattr(bg.course, 'include_saturday', False)
        bg_max_wd = 5 if bg_include_sat else 4

        if bg_total >= 20:
            bg_wd_opts = [(0, 2, 4)]
        elif 12 <= bg_total <= 20:
            bg_wd_opts = [(1, 3)]
        else:
            bg_wd_opts = [(wd,) for wd in range(0, bg_max_wd + 1)]

        found_alt = None
        for bwds in bg_wd_opts:
            bdates = _slot_occurrence_dates(bg.course.start_date, bwds, bg_total)
            if not bdates:
                continue
            for (bp1, bp2) in VALID_PARA_PAIRS:
                if bwds == tuple(bg.weekdays or []) and PARA_TIMES[bp1][0] == bg.start_time:
                    continue  # bu — uning HOZIRGI vaqti, o'tkazib yuboramiz
                btimes = [PARA_TIMES[bp1][0], PARA_TIMES[bp2][0]]
                if bg_teacher_id and GroupSchedule.objects.filter(
                    date__in=bdates, start_time__in=btimes, group__teacher_id=bg_teacher_id,
                ).exclude(group=bg).exists():
                    continue
                conflict = GroupSchedule.objects.filter(
                    date__in=bdates, start_time__in=btimes, group__students__in=bg_students,
                ).exclude(group=bg).exists()
                if conflict:
                    continue
                found_alt = (bwds, bp1, bp2, bdates)
                break
            if found_alt:
                break

        if not found_alt:
            return False, None  # Bu to'siq guruhni ko'chirib bo'lmadi -> butun urinish bekor

        relocations.append((bg, *found_alt))

    # ── 3-BOSQICH: barcha ko'chirishlar + grp'ni saqlash ──
    with transaction.atomic():
        for bg, bwds, bp1, bp2, bdates in relocations:
            bg.start_time = PARA_TIMES[bp1][0]
            bg.weekdays = list(bwds)
            bg.save()
            sync_group_language(bg)
            GroupSchedule.objects.filter(group=bg).delete()
            GroupSchedule.objects.bulk_create([
                GroupSchedule(group=bg, date=d, start_time=PARA_TIMES[bp1][0], lesson_number=2 * i + 1)
                for i, d in enumerate(bdates)
            ] + [
                GroupSchedule(group=bg, date=d, start_time=PARA_TIMES[bp2][0], lesson_number=2 * i + 2)
                for i, d in enumerate(bdates)
            ])

        grp.start_time = times[0]
        grp.weekdays = list(wds)
        grp.is_scheduled = True
        grp.save()
        sync_group_language(grp)
        GroupSchedule.objects.filter(group=grp).delete()
        GroupSchedule.objects.bulk_create([
            GroupSchedule(group=grp, date=d, start_time=times[0], lesson_number=2 * i + 1)
            for i, d in enumerate(dates)
        ] + [
            GroupSchedule(group=grp, date=d, start_time=times[1], lesson_number=2 * i + 2)
            for i, d in enumerate(dates)
        ])

    names = ", ".join(str(bg) for bg, *_ in relocations)
    return True, (
        f"'{grp}' guruhi joylashtirildi — buning uchun {len(relocations)} ta to'siq guruh "
        f"boshqa vaqtga ko'chirildi: {names}."
    )


def _try_absorb_from_sibling_to_reach_minimum(grp, course, teacher, same_course_groups):
    """
    YANGI: kichik "qoldiq" guruh (MIN_GROUP_SIZE dan kam, masalan 6 kishi)
    uchun — uning O'Z A'ZOLARI to'liq bo'sh bo'ladigan vaqtni topib, o'sha
    aniq vaqtga MOS KELUVCHI qo'shimcha talabalarni to'liq (yoki yarim
    to'liq) aka-uka guruhlardan TORTIB OLADI — shu orqali guruh hajmini
    MIN_GROUP_SIZE (8) ga yetkazadi.

    MUHIM QOIDALAR (hech biri buzilmaydi):
    - Manba (aka-uka) guruh MIN_GROUP_SIZE dan kam bo'lib qolmaydi.
    - Maqsad guruh (grp) MAX_GROUP_SIZE dan oshmaydi.
    - Faqat grp allaqachon MIN_GROUP_SIZE dan kam bo'lsa ishlaydi (aks
      holda oddiy `_try_minimal_disruption_swap` yetarli).

    Bu — `_try_partial_distribute_and_reschedule`ning TESKARI varianti:
    u talabalarni muammoli guruhdan tashqariga chiqarardi, bu esa
    ICHKARIGA tortib oladi.
    """
    students = list(grp.students.all())
    if len(students) >= MIN_GROUP_SIZE:
        return False, None  # Bu funksiya faqat kichik qoldiqlar uchun

    other_groups = [g for g in same_course_groups if g.pk != grp.pk and g.is_scheduled]
    if not other_groups:
        return False, None

    teacher_id = teacher.id if teacher else None
    total_lessons = course.total_lessons
    start_date = course.start_date
    include_saturday = getattr(course, 'include_saturday', False)
    max_wd = 5 if include_saturday else 4

    if total_lessons >= 20:
        weekday_options = [(0, 2, 4)]
    elif 12 <= total_lessons <= 20:
        weekday_options = [(1, 3)]
    else:
        weekday_options = [(wd,) for wd in range(0, max_wd + 1)]

    needed = MIN_GROUP_SIZE - len(students)  # kamida shuncha qo'shimcha talaba kerak

    for wds in weekday_options:
        dates = _slot_occurrence_dates(start_date, wds, total_lessons)
        if not dates:
            continue
        for (p1, p2) in VALID_PARA_PAIRS:
            times = [PARA_TIMES[p1][0], PARA_TIMES[p2][0]]
            if teacher_id and GroupSchedule.objects.filter(
                date__in=dates, start_time__in=times, group__teacher_id=teacher_id,
            ).exclude(group=grp).exists():
                continue

            # ── MUHIM TUZATISH: "bitta fandan bir parada MAX_GROUPS_PER_SLOT_
            # NO_TEACHER (4) tadan ortiq guruh bo'lmasin" chegarasi bu yerda
            # yo'q edi. Endi tekshiriladi.
            if teacher_id is None:
                existing_same_subject = GroupSchedule.objects.filter(
                    date__in=dates, start_time__in=times,
                    group__course__subject=course.subject,
                    group__is_scheduled=True,
                ).exclude(group=grp).values_list('group_id', flat=True).distinct().count()
                if existing_same_subject >= 4:  # MAX_GROUPS_PER_SLOT_NO_TEACHER
                    continue

            # 1) grp'ning O'Z a'zolari shu vaqtda TO'LIQ bo'sh bo'lishi shart
            own_conflict = GroupSchedule.objects.filter(
                date__in=dates, start_time__in=times, group__students__in=students,
            ).exclude(group=grp).exists()
            if own_conflict:
                continue

            # 2) Aka-uka guruh(lar)dan shu vaqtga MOS keluvchi talabalarni yig'amiz
            absorbed = []
            source_map = {}  # student_id -> manba guruh
            for og in other_groups:
                og_students = list(og.students.all())
                # Manba guruh MIN_GROUP_SIZE dan kam bo'lib qolmasligi uchun,
                # undan olib qo'yish mumkin bo'lgan MAKSIMAL son:
                max_takeable = len(og_students) - MIN_GROUP_SIZE
                if max_takeable <= 0:
                    continue
                taken_from_this = 0
                for s in og_students:
                    if len(absorbed) >= needed:
                        break
                    if taken_from_this >= max_takeable:
                        break
                    conflict = GroupSchedule.objects.filter(
                        date__in=dates, start_time__in=times, group__students=s,
                    ).exclude(group=og).exists()
                    if conflict:
                        continue
                    absorbed.append(s)
                    source_map[s.id] = og
                    taken_from_this += 1
                if len(absorbed) >= needed:
                    break

            new_total = len(students) + len(absorbed)
            if len(absorbed) < needed or new_total > MAX_GROUP_SIZE:
                continue  # bu vaqt uchun yetarli nomzod topilmadi -> keyingi vaqtni sinaymiz

            # ── Topildi — saqlaymiz ──
            with transaction.atomic():
                # Manba guruhlardan olib, maqsad guruhga qo'shamiz
                by_source = {}
                for s in absorbed:
                    by_source.setdefault(source_map[s.id].pk, []).append(s)
                for og_pk, taken_students in by_source.items():
                    og = next(g2 for g2 in other_groups if g2.pk == og_pk)
                    remaining_og = [s for s in og.students.all() if s.id not in {t.id for t in taken_students}]
                    og.students.set(remaining_og)
                    sync_group_language(og)

                final_students = students + absorbed
                grp.students.set(final_students)
                grp.start_time = times[0]
                grp.weekdays = list(wds)
                grp.is_scheduled = True
                grp.save()
                sync_group_language(grp)
                GroupSchedule.objects.filter(group=grp).delete()
                GroupSchedule.objects.bulk_create([
                    GroupSchedule(group=grp, date=d, start_time=times[0], lesson_number=2 * i + 1)
                    for i, d in enumerate(dates)
                ] + [
                    GroupSchedule(group=grp, date=d, start_time=times[1], lesson_number=2 * i + 2)
                    for i, d in enumerate(dates)
                ])

            names = ", ".join(str(s) for s in absorbed)
            return True, (
                f"'{grp}' guruhi ({len(students)} kishi) kichik bo'lgani uchun, "
                f"aka-uka guruh(lar)dan {len(absorbed)} ta mos talaba tortib olindi "
                f"({names}) — yakuniy hajm: {new_total} kishi."
            )

    return False, None


def _try_last_resort_expand_weekdays(grp, course, teacher):
    """
    YANGI, ENG OXIRGI CHORA — faqat 16-paralik (12-20 dars) kurslar uchun.

    Hozirgi qat'iy qoida: 16-paralik kurslar FAQAT Seshanba/Payshanba
    juftligida joylashadi. Agar bu ishlamasa (va boshqa BARCHA algoritmlar
    — almashtirish, bo'lish, qayta guruhlash, tarqatish — ham yordam
    bermagan bo'lsa), bu funksiya SO'NGGI imkoniyat sifatida Dushanba/
    Chorshanba/Juma kunlarini ham (alohida yoki Seshanba/Payshanba bilan
    aralash juftlik sifatida) sinab ko'radi.

    XAVFSIZLIK SHARTI (24-paraliklarni himoya qilish uchun): agar hozirgi
    paytda BOSHQA biror 24-paralik (yoki undan uzunroq) kurs hali
    tuzilmagan bo'lsa — bu funksiya ISHLAMAYDI (False qaytaradi). Sabab:
    24-paralik kurslar Dush/Chor/Juma kunlarining BARCHA 3 kunini talab
    qiladi (deyarli hech qanday zaxirasiz), shuning uchun ular har doim
    USTUVOR bo'lishi kerak — 16-paralik kurs ularning joyini "o'g'irlab"
    qo'ymasligi kerak.
    """
    if not (12 <= course.total_lessons <= 20):
        return False, None  # Faqat 16-paralik oralig'idagi kurslar uchun

    # ── MUHIM BUG TUZATISH: bu funksiyada MIN_GROUP_SIZE tekshiruvi
    # umuman yo'q edi! Agar `grp` allaqachon MIN_GROUP_SIZE dan kam
    # bo'lsa (masalan qayta guruhlashdan qolgan kichik "qoldiq"), bu
    # funksiya uni baribir muvaffaqiyatli deb belgilab, 8-18 qoidasini
    # buzib qo'yishi mumkin edi.
    if grp.students.count() < MIN_GROUP_SIZE:
        return False, None

    # ── Xavfsizlik: 24-paralik kurslar ustuvorligini himoya qilish ──
    # MUHIM: shunchaki "MIN_GROUP_SIZE dan kam emas" tekshiruvi YETARLI
    # EMAS EKAN — masalan aynan 8 kishilik guruh (chegaraga teng) ham
    # HAQIQATDA 0 dars topa olmasligi, ya'ni ABADIY "qoldiq" bo'lishi
    # mumkin. Shuning uchun endi HAR BIR nomzod uchun haqiqatan
    # (find_schedule_for_group bilan) tekshiramiz — agar u 0 dars topsa,
    # demak u ham 16-paralikni bloklashga haqli emas.
    other_24_groups = list(
        CourseGroup.objects.filter(
            is_scheduled=False, course__total_lessons__gte=20,
        ).exclude(pk=grp.pk).select_related('course').prefetch_related('students')
    )
    other_24_unresolved = False
    for og in other_24_groups:
        if og.students.count() < MIN_GROUP_SIZE:
            continue  # abadiy qoldiq — hisobga olinmaydi
        og_course = og.course
        og_sched = find_schedule_for_group(
            og_course.start_date, og_course.end_date, og_course.total_lessons,
            og_course.lessons_per_week, og.teacher, list(og.students.all()),
            group_number=og.group_number,
            include_saturday=getattr(og_course, 'include_saturday', False),
        )
        if len(og_sched) >= og_course.total_lessons:
            other_24_unresolved = True  # HALI real umidga ega -> ustuvorlik saqlanadi
            break
    if other_24_unresolved:
        return False, None  # 24-paraliklar hali navbatda — ularga yo'l bermaymiz

    import itertools
    students = list(grp.students.all())
    teacher_id = teacher.id if teacher else None
    start_date = course.start_date
    include_saturday = getattr(course, 'include_saturday', False)
    max_wd = 5 if include_saturday else 4

    # BARCHA 2 kunlik kombinatsiyalarni sinaymiz (Sesh/Pay bilan
    # cheklanmasdan) — masalan Dush/Chor, Dush/Juma, Chor/Juma va h.k.
    all_weekday_pairs = list(itertools.combinations(range(0, max_wd + 1), 2))
    # Sesh/Pay (kanonik) ni birinchi sinaymiz (afzal ko'riladi), qolganlarini keyin
    canonical = (1, 3)
    ordered_pairs = [canonical] + [p for p in all_weekday_pairs if p != canonical]

    for wds in ordered_pairs:
        dates = _slot_occurrence_dates(start_date, wds, course.total_lessons)
        if not dates:
            continue
        for (p1, p2) in VALID_PARA_PAIRS:
            times = [PARA_TIMES[p1][0], PARA_TIMES[p2][0]]
            if teacher_id and GroupSchedule.objects.filter(
                date__in=dates, start_time__in=times, group__teacher_id=teacher_id,
            ).exists():
                continue
            conflict = GroupSchedule.objects.filter(
                date__in=dates, start_time__in=times, group__students__in=students,
            ).exists()
            if conflict:
                continue

            # ── MUHIM TUZATISH: bu funksiya ilgari faqat QATTIQ (o'qituvchi/
            # talaba) to'qnashuvlarni tekshirar, lekin "bitta fandan bir
            # parada MAX_GROUPS_PER_SLOT_NO_TEACHER (4) tadan ortiq guruh
            # bo'lmasin" chegarasini UMUMAN hisobga olmasdi. Natijada bu
            # "eng so'nggi chora" orqali cheksiz ko'p guruh (masalan 6 ta)
            # bitta parada to'planib qolishi mumkin edi — garchi asosiy
            # find_schedule_for_group bu chegarani to'g'ri qo'llasa ham.
            # Endi shu yerda ham xuddi shu chegara tekshiriladi.
            if teacher_id is None:
                existing_same_subject = GroupSchedule.objects.filter(
                    date__in=dates, start_time__in=times,
                    group__course__subject=course.subject,
                    group__is_scheduled=True,
                ).exclude(group=grp).values_list('group_id', flat=True).distinct().count()
                if existing_same_subject >= 4:  # MAX_GROUPS_PER_SLOT_NO_TEACHER bilan bir xil qiymat
                    continue

            # Topildi — saqlaymiz
            with transaction.atomic():
                grp.start_time = times[0]
                grp.weekdays = list(wds)
                grp.is_scheduled = True
                grp.save()
                sync_group_language(grp)
                GroupSchedule.objects.filter(group=grp).delete()
                GroupSchedule.objects.bulk_create([
                    GroupSchedule(group=grp, date=d, start_time=times[0], lesson_number=2 * i + 1)
                    for i, d in enumerate(dates)
                ] + [
                    GroupSchedule(group=grp, date=d, start_time=times[1], lesson_number=2 * i + 2)
                    for i, d in enumerate(dates)
                ])
            wd_names = [WEEKDAY_NAMES.get(wd, str(wd)) for wd in wds]
            return True, (
                f"'{grp}' guruhi ENG OXIRGI CHORA sifatida, odatiy Seshanba/Payshanba "
                f"o'rniga {wd_names} kunlariga joylashtirildi (barcha boshqa imkoniyat tugagani uchun)."
            )

    return False, None


def _try_regroup_same_subject(course, teacher, unresolved_groups):
    """
    YANGI: Bitta fanning BIR NECHTA tuzilmagan guruhi bo'lsa (masalan
    "Organik kimyo 3-semestr — 2,3,4-guruh", uchalasi ham tuzilmagan, va
    ular orasida hech qanday TUZILGAN parallel guruh yo'q — shuning uchun
    oddiy almashtirish/taqsimlash ISHLAMAYDI), bu funksiya original guruh
    chegaralarini butunlay unutib, BARCHA talabalarni birlashtirib, ularni
    bo'sh vaqtlariga qarab ENG YAXSHI tarzda QAYTADAN guruhlaydi.

    MUHIM QOIDA: yangi yaratiladigan HAR BIR guruh MIN_GROUP_SIZE (8) dan
    kam va MAX_GROUP_SIZE (18) dan ko'p bo'la olmaydi — bu chegara hech
    qachon buzilmaydi.

    Algoritm (ochko'z klasterlash):
    1. Barcha talabalarni bitta ro'yxatga yig'amiz (takrorlarsiz).
    2. Har bir mumkin (hafta_kuni, para_blok) kombinatsiyasi uchun, hozircha
       joylashtirilmagan talabalardan aynan KIMLAR to'liq mos kelishini
       hisoblaymiz.
    3. Eng KO'P talabaga mos keladigan kombinatsiyani tanlaymiz, undan
       (MAX_GROUP_SIZE tagacha) yangi guruh yaratamiz.
    4. Talabalar tugagunча yoki mos kombinatsiya qolmaguncha takrorlaymiz.
    5. Oxirida MIN_GROUP_SIZE dan kam qolgan "guruh" hosil bo'lsa — uni
       yaratmaymiz, o'sha talabalar tuzilmagan holicha qoladi.
    """
    all_students = []
    seen_ids = set()
    for g in unresolved_groups:
        for s in g.students.all():
            if s.id not in seen_ids:
                seen_ids.add(s.id)
                all_students.append(s)

    if len(all_students) < MIN_GROUP_SIZE:
        return False, None

    total_lessons = course.total_lessons
    start_date = course.start_date
    include_saturday = getattr(course, 'include_saturday', False)
    max_wd = 5 if include_saturday else 4
    teacher_id = teacher.id if teacher else None

    if total_lessons >= 20:
        weekday_options = [(0, 2, 4)]
    elif 12 <= total_lessons <= 20:
        weekday_options = [(1, 3)]
    else:
        weekday_options = [(wd,) for wd in range(0, max_wd + 1)]

    all_candidates = []
    for wds in weekday_options:
        dates = _slot_occurrence_dates(start_date, wds, total_lessons)
        if not dates:
            continue
        for (p1, p2) in VALID_PARA_PAIRS:
            times = [PARA_TIMES[p1][0], PARA_TIMES[p2][0]]
            if teacher_id and GroupSchedule.objects.filter(
                date__in=dates, start_time__in=times, group__teacher_id=teacher_id,
            ).exists():
                continue  # o'qituvchi shu vaqtda band -> bu kombinatsiya umuman ishlatilmaydi
            all_candidates.append((wds, p1, p2, dates, times))

    remaining = list(all_students)
    new_groups = []  # [(students, wds, p1, p2, dates), ...]

    # ── MUHIM TUZATISH: bu "ochko'z klasterlash" tsikli ilgari HAR BIR
    # iteratsiyada eng ko'p talabaga mos keladigan (hafta_kuni, para)
    # kombinatsiyasini tanlar, lekin shu kombinatsiya ALLAQACHON NECHTA
    # YANGI GURUHGA ishlatilganini hisobga OLMAS edi. Natijada — agar
    # talabalarning aksariyati faqat BITTA vaqtda bo'sh bo'lsa (masalan
    # 08:30) — barcha yangi guruhlar (6 tagacha yoki undan ham ko'p)
    # xuddi shu bitta vaqtga cheksiz ravishda to'planib qolardi, chunki
    # o'qituvchi biriktirilmagan bosqichda bu combo hech qachon "band"
    # deb belgilanmasdi. Endi har bir combo uchun nechta guruh
    # yaratilganini sanaymiz va MAX_GROUPS_PER_SLOT_NO_TEACHER (4) ga
    # yetgach, o'sha combo keyingi tanlovlardan CHIQARIB TASHLANADI —
    # shunda qolgan talabalar haqiqatan ham BOSHQA vaqtga taqsimlanadi.
    MAX_GROUPS_PER_SLOT_NO_TEACHER = 4
    combo_usage_count = defaultdict(int)

    # ── TUZATILGAN: endi bu tsikl "eng ko'p talabaga mos keladigan"
    # combo'ni EMAS, balki "ENG KAM ISHLATILGAN (iloji bo'lsa hali
    # umuman ishlatilmagan) combo'ni AFZAL ko'radi — mos keladigan
    # talaba soni faqat TENGLIK bo'lganda hal qiluvchi omil bo'ladi.
    # Shunday qilib guruhlar avval BOSHQA-BOSHQA bo'sh vaqtlarga
    # tarqaladi (masalan 2-2-2), va faqat haqiqatan boshqa imkoniyat
    # qolmaganda bitta vaqtga 4 tagacha to'planadi. Bu — kamroq
    # o'qituvchi bilan ko'proq guruhni qamrab olish imkonini beradi
    # (turli vaqtdagi guruhlarni bitta o'qituvchi ketma-ket o'qitishi
    # mumkin bo'ladi).
    while len(remaining) >= MIN_GROUP_SIZE and all_candidates:
        best = None  # (score, wds, p1, p2, dates, matched_students)
        for wds, p1, p2, dates, times in all_candidates:
            usage = 0
            if teacher_id is None:
                combo_key = (wds, p1, p2)
                usage = combo_usage_count[combo_key]
                if usage >= MAX_GROUPS_PER_SLOT_NO_TEACHER:
                    continue  # bu vaqt allaqachon 4 ta guruh bilan to'lgan — o'tkazib yuboramiz
            matched = [
                s for s in remaining
                if not GroupSchedule.objects.filter(
                    date__in=dates, start_time__in=times, group__students=s,
                ).exists()
            ]
            if len(matched) >= MIN_GROUP_SIZE:
                # Ustuvorlik: 1) kamroq ishlatilgan combo, 2) ko'proq mos kelgan talaba
                score = (usage, -len(matched))
                if best is None or score < best[0]:
                    best = (score, wds, p1, p2, dates, matched)

        if best is None:
            break

        _, wds, p1, p2, dates, matched = best
        group_students = matched[:MAX_GROUP_SIZE]  # MAX_GROUP_SIZE — hech qachon buzilmaydi
        new_groups.append([group_students, wds, p1, p2, dates])
        combo_usage_count[(wds, p1, p2)] += 1
        matched_ids = {s.id for s in group_students}
        remaining = [s for s in remaining if s.id not in matched_ids]

    # ── YANGI: "TO'LDIRISH" BOSQICHI ──
    # Asosiy klasterlash tugagach, ba'zi YANGI guruhlarda hali bo'sh joy
    # qolgan bo'lishi mumkin (masalan 13/18), va `remaining`da qolgan
    # talabalardan ba'zilari aynan o'sha guruhning vaqtiga mos kelishi
    # mumkin (garchi ular "eng katta" klasterga tushmagan bo'lsa ham).
    # Bunday talabalarni MAX_GROUP_SIZE chegarasini buzmasdan qo'shib
    # chiqamiz — bu "qoldiq" sonini kamaytiradi.
    if remaining and new_groups:
        still_remaining = []
        for s in remaining:
            placed_in_topup = False
            for group_ref in new_groups:
                group_students, wds, p1, p2, dates = group_ref
                if len(group_students) >= MAX_GROUP_SIZE:
                    continue
                times = [PARA_TIMES[p1][0], PARA_TIMES[p2][0]]
                conflict = GroupSchedule.objects.filter(
                    date__in=dates, start_time__in=times, group__students=s,
                ).exists()
                if conflict:
                    continue
                group_students.append(s)
                placed_in_topup = True
                break
            if not placed_in_topup:
                still_remaining.append(s)
        remaining = still_remaining

    placed_count = sum(len(gs) for gs, *_ in new_groups)
    if placed_count == 0:
        return False, None

    with transaction.atomic():
        for g in unresolved_groups:
            GroupSchedule.objects.filter(group=g).delete()
            g.delete()

        existing_numbers = list(
            CourseGroup.objects.filter(course=course).values_list('group_number', flat=True)
        )
        next_number = (max(existing_numbers) + 1) if existing_numbers else 1

        for group_students, wds, p1, p2, dates in new_groups:
            new_grp = CourseGroup.objects.create(
                course=course, teacher=teacher, group_number=next_number, is_scheduled=True,
            )
            next_number += 1
            new_grp.students.set(group_students)
            new_grp.start_time = PARA_TIMES[p1][0]
            new_grp.weekdays = list(wds)
            new_grp.save()
            sync_group_language(new_grp)
            GroupSchedule.objects.bulk_create([
                GroupSchedule(group=new_grp, date=d, start_time=PARA_TIMES[p1][0], lesson_number=2 * i + 1)
                for i, d in enumerate(dates)
            ] + [
                GroupSchedule(group=new_grp, date=d, start_time=PARA_TIMES[p2][0], lesson_number=2 * i + 2)
                for i, d in enumerate(dates)
            ])

        if remaining:
            leftover_grp = CourseGroup.objects.create(
                course=course, teacher=teacher, group_number=next_number, is_scheduled=False,
            )
            leftover_grp.students.set(remaining)
            sync_group_language(leftover_grp)

    msg = (
        f"'{course.subject}' fani uchun {len(unresolved_groups)} ta eski guruh birlashtirilib, "
        f"bo'sh vaqtga qarab {len(new_groups)} ta YANGI guruhga qayta taqsimlandi "
        f"({placed_count}/{len(all_students)} talaba joylashdi, har biri {MIN_GROUP_SIZE}-{MAX_GROUP_SIZE} oralig'ida)."
    )
    if remaining:
        msg += f" {len(remaining)} ta talaba hali ham hech qanday vaqtga sig'madi."
    return True, msg


def _try_partial_distribute_and_reschedule(grp, course, teacher, same_course_groups):
    """
    YANGI: `_try_dissolve_and_distribute_group`dan farqli o'laroq, bu
    funksiya "hammasi yoki hech narsa" tamoyilida ISHLAMAYDI.

    Sabab: masalan 18 kishilik guruh bor, parallel guruhda faqat 9 ta
    bo'sh joy bor. Eski funksiya BUTUN 18 kishi sig'masa, hech narsa
    qilmay rad etardi. Bu YANGI funksiya esa: bo'sh joyga SIG'GAN
    talabalarni (masalan 9 tasini) ko'chiradi, QOLGAN talabalar
    (masalan 9 tasi) bilan esa asosiy guruh — endi ANCHA KICHIKROQ
    bo'lgani uchun — o'zi mustaqil, alohida vaqt izlaydi (kamroq talaba
    bilan bo'sh vaqt topish ehtimoli sezilarli yuqori).

    Faqat: (a) kamida 1 talaba ko'chgan, VA (b) qolgan talabalar
    (bo'lsa) MIN_GROUP_SIZE dan kam bo'lib qolmagan, VA (c) qolgan
    talabalar uchun TO'LIQ jadval topilgan bo'lsagina — natija saqlanadi.
    """
    students = list(grp.students.all())
    other_groups = [g for g in same_course_groups if g.pk != grp.pk and g.is_scheduled]
    if not other_groups:
        return False, None

    temp_assignments = {g.pk: list(g.students.all()) for g in other_groups}

    # ── YANGI, MUHIM TUZATISH ──
    # ESKI mantiq: har bir talabani sig'sa ko'chirar edi, va agar oxirida
    # asosiy guruhda MIN_GROUP_SIZE dan kam qolib qolsa — BUTUN amal (hatto
    # muvaffaqiyatli qismi ham) bekor qilinardi.
    #
    # YANGI mantiq: asosiy guruhda KAMIDA MIN_GROUP_SIZE (8) talaba QOLISHI
    # kafolatlanadi — ko'chirish shu chegaraga yetguncha davom etadi, undan
    # keyin TO'XTAYDI (hech qachon 8 dan pastga tushmaydi), lekin bekor
    # qilinmaydi — chegaragacha ko'chirilgan qism baribir SAQLANADI.
    # Istisno: agar HAMMASI ko'chsa (qoldiq 0), bu — to'liq tarqatish,
    # alohida ruxsat etiladi (pastda ko'rib chiqiladi).
    max_movable = max(0, len(students) - MIN_GROUP_SIZE)

    remaining_students = []
    moved_students = []

    for student in students:
        if len(moved_students) >= max_movable:
            # Chegaraga yetdik — qolganlarni endi ko'chirishga urinmaymiz,
            # ular "remaining"da, asosiy guruhda qoladi.
            remaining_students.append(student)
            continue

        placed = False
        for target_grp in other_groups:
            current = temp_assignments[target_grp.pk]
            if len(current) >= MAX_GROUP_SIZE:
                continue
            target_times = set(
                GroupSchedule.objects.filter(group=target_grp).values_list('date', 'start_time')
            )
            student_busy = set(
                GroupSchedule.objects.filter(group__students=student)
                .exclude(group=grp).values_list('date', 'start_time')
            )
            if student_busy & target_times:
                continue
            current.append(student)
            placed = True
            break
        if placed:
            moved_students.append(student)
        else:
            remaining_students.append(student)

    # Agar chegara tufayli TO'XTAGAN bo'lsak-u, lekin aslida BARCHA qolgan
    # talabalar ham (agar chegara bo'lmaganida) ko'chib ketishi mumkin
    # bo'lsa — bu holda TO'LIQ tarqatishga (remaining=0) ruxsat beramiz,
    # chunki bu holatda MIN_GROUP_SIZE qoidasi umuman qo'llanmaydi (guruh
    # butunlay yo'q bo'ladi, "8 dan kam qoladigan guruh" degani emas).
    if remaining_students and len(moved_students) == max_movable:
        still_could_move = []
        cant_move = []
        for student in remaining_students:
            placed = False
            for target_grp in other_groups:
                current = temp_assignments[target_grp.pk]
                if len(current) >= MAX_GROUP_SIZE:
                    continue
                target_times = set(
                    GroupSchedule.objects.filter(group=target_grp).values_list('date', 'start_time')
                )
                student_busy = set(
                    GroupSchedule.objects.filter(group__students=student)
                    .exclude(group=grp).values_list('date', 'start_time')
                )
                if student_busy & target_times:
                    continue
                placed = True
                break
            (still_could_move if placed else cant_move).append(student)
        if not cant_move:
            # Hammasi ko'cha oladi -> to'liq tarqatishga o'tamiz
            for student in still_could_move:
                for target_grp in other_groups:
                    current = temp_assignments[target_grp.pk]
                    if len(current) >= MAX_GROUP_SIZE:
                        continue
                    target_times = set(
                        GroupSchedule.objects.filter(group=target_grp).values_list('date', 'start_time')
                    )
                    student_busy = set(
                        GroupSchedule.objects.filter(group__students=student)
                        .exclude(group=grp).values_list('date', 'start_time')
                    )
                    if student_busy & target_times:
                        continue
                    current.append(student)
                    moved_students.append(student)
                    break
            remaining_students = []

    moved_count = len(moved_students)
    if moved_count == 0:
        return False, None  # Hech kim ko'chmadi — bu funksiya foyda bermadi

    if remaining_students and len(remaining_students) < MIN_GROUP_SIZE:
        # Bu holatda talabalar juda kam qolib, MIN_GROUP_SIZE buzilardi.
        # Lekin ko'chirishning o'zi (og'ga) hali ham FOYDALI bo'lishi mumkin —
        # shuning uchun butunlay rad etmasdan, ularni ko'chirmasdan, faqat
        # ULARSIZ davom etamiz (ya'ni bu talabalar "remaining"da qoladi va
        # asl guruhda, kattaroq holicha qoladi). Xavfsizlik uchun hozircha
        # oddiy True qaytarib, hech kimni ko'chirmasdan chiqamiz.
        return False, None

    # YANGI, MUHIM TUZATISH: qolgan talabalar uchun jadval qidiramiz, LEKIN
    # agar ular TO'LIQ joylasha olmasa ham — bu MUVAFFAQIYATLI ko'chirilgan
    # qismni (masalan 9 kishi) BEKOR QILISH UCHUN SABAB EMAS. Foydalanuvchi
    # talabiga ko'ra: "maksimal darajada talabalarni darsga qo'yish" —
    # shuning uchun aniq bo'lgan yutuqni (9 kishi joylashdi) har doim
    # saqlaymiz, qolganlari esa (agar hozircha joylasha olmasa) oddiy
    # UNSCHEDULED guruh sifatida qolib, KEYINGI bosqichlarda (split,
    # dissolve, keyingi iteratsiya) yana urinib ko'riladi.
    new_schedule = None
    remaining_scheduled = False
    if remaining_students:
        new_schedule = find_schedule_for_group(
            course.start_date, course.end_date, course.total_lessons,
            course.lessons_per_week, teacher, remaining_students,
            group_number=grp.group_number,
            include_saturday=getattr(course, 'include_saturday', False),
        )
        remaining_scheduled = len(new_schedule) >= course.total_lessons

    with transaction.atomic():
        for target_grp in other_groups:
            target_grp.students.set(temp_assignments[target_grp.pk])
            sync_group_language(target_grp)

        if remaining_students:
            grp.students.set(remaining_students)
            if remaining_scheduled:
                from collections import Counter
                para_counter = Counter(p_start for _, p_start, _ in new_schedule)
                most_common_para = para_counter.most_common(1)[0][0]
                grp.start_time = most_common_para
                grp.weekdays = list({d.weekday() for d, _, _ in new_schedule})
                grp.is_scheduled = True
                grp.save()
                sync_group_language(grp)
                GroupSchedule.objects.filter(group=grp).delete()
                GroupSchedule.objects.bulk_create([
                    GroupSchedule(group=grp, date=d, start_time=p1, lesson_number=i + 1)
                    for i, (d, p1, p2) in enumerate(new_schedule)
                ])
            else:
                # Qolganlar hozircha joylasha olmadi — lekin ko'chirilgan
                # qism baribir SAQLANADI. `grp` shunchaki kichikroq (faqat
                # `remaining_students`) TUZILMAGAN guruh bo'lib qoladi,
                # keyingi bosqichlar/iteratsiyalar uchun.
                grp.is_scheduled = False
                grp.save()
                sync_group_language(grp)
                GroupSchedule.objects.filter(group=grp).delete()
        else:
            GroupSchedule.objects.filter(group=grp).delete()
            grp.delete()

    msg = f"'{grp}' guruhidan {moved_count} ta talaba bo'sh joyi bor parallel guruh(lar)ga ko'chirildi."
    if remaining_students:
        if remaining_scheduled:
            msg += f" Qolgan {len(remaining_students)} ta talaba uchun alohida, mustaqil vaqt topildi."
        else:
            msg += (
                f" Qolgan {len(remaining_students)} ta talaba uchun hozircha vaqt topilmadi "
                f"— ular kichikroq, alohida guruh sifatida qoldi (keyingi bosqichlarda qayta sinaladi)."
            )
    else:
        msg += " Barcha talaba ko'chirilgani uchun asl guruh o'chirildi."
    return True, msg


def _diagnose_true_blockers(grp, course, teacher):
    """
    YANGI: DIAGNOSTIKA funksiyasi (hech narsani o'zgartirmaydi, faqat
    TEKSHIRADI) — foydalanuvchi so'roviga ko'ra: "aynan qaysini
    o'zgartirsa muammo hal bo'ladi" degan savolga aniq javob beradi.

    `_try_minimal_disruption_swap` bilan bir xil mantiqda ENG KAM
    to'siqli vaqtni topadi, so'ngra HAR BIR to'siq talaba uchun
    almashtirish nomzodi bor-yo'qligini tekshiradi va natijani qaytaradi:

        {
            'target_time': ..., 'target_weekdays': ...,
            'blockers': [
                {'student': <Student>, 'has_candidate': True/False,
                 'candidate': <Student yoki None>,
                 'candidate_group': <CourseGroup yoki None>},
                ...
            ],
            'truly_stuck': [<faqat has_candidate=False bo'lgan talabalar>],
        }

    Bu natija UI'da ko'rsatish uchun mo'ljallangan — admin aynan qaysi
    talaba(lar) "haqiqiy" to'siq ekanini, va qolganlari uchun qanday
    almashtirish mavjudligini ko'radi.
    """
    students = list(grp.students.all())
    student_ids = set(s.id for s in students)
    teacher_id = teacher.id if teacher else None
    total_lessons = course.total_lessons
    start_date = course.start_date
    include_saturday = getattr(course, 'include_saturday', False)
    max_wd = 5 if include_saturday else 4

    if total_lessons >= 20:
        weekday_options = [(0, 2, 4)]
    elif 12 <= total_lessons <= 20:
        weekday_options = [(1, 3)]
    else:
        weekday_options = [(wd,) for wd in range(0, max_wd + 1)]

    candidates = []
    for wds in weekday_options:
        dates = _slot_occurrence_dates(start_date, wds, total_lessons)
        if not dates:
            continue
        for (p1, p2) in VALID_PARA_PAIRS:
            times = [PARA_TIMES[p1][0], PARA_TIMES[p2][0]]
            if teacher_id and GroupSchedule.objects.filter(
                date__in=dates, start_time__in=times, group__teacher_id=teacher_id,
            ).exclude(group=grp).exists():
                continue
            blocker_ids = set(GroupSchedule.objects.filter(
                date__in=dates, start_time__in=times, group__students__id__in=student_ids,
            ).exclude(group=grp).values_list('group__students__id', flat=True))
            candidates.append((len(blocker_ids), wds, p1, p2, dates, blocker_ids))

    if not candidates:
        return None

    candidates.sort(key=lambda c: c[0])
    _, wds, p1, p2, dates, blocker_ids = candidates[0]
    times = [PARA_TIMES[p1][0], PARA_TIMES[p2][0]]

    same_subject_groups = list(course.groups.exclude(pk=grp.pk).filter(is_scheduled=True))
    used_candidates = set()
    blockers_info = []

    for bid in sorted(blocker_ids):
        blocker = next((s for s in students if s.id == bid), None)
        if blocker is None:
            continue
        swap_found = None
        for og in same_subject_groups:
            og_dates_times = set(GroupSchedule.objects.filter(group=og).values_list('date', 'start_time'))
            for cand in og.students.order_by('id'):
                if cand.id in used_candidates:
                    continue
                cand_conflict = GroupSchedule.objects.filter(
                    date__in=dates, start_time__in=times, group__students=cand,
                ).exclude(group=og).exists()
                if cand_conflict:
                    continue
                blocker_conflict = any(
                    GroupSchedule.objects.filter(date=d, start_time=t, group__students=blocker)
                    .exclude(group=grp).exists()
                    for d, t in og_dates_times
                )
                if blocker_conflict:
                    continue
                swap_found = (og, cand)
                break
            if swap_found:
                break
        if swap_found:
            og, cand = swap_found
            used_candidates.add(cand.id)
            blockers_info.append({
                'student': blocker, 'has_candidate': True,
                'candidate': cand, 'candidate_group': og,
            })
        else:
            blockers_info.append({
                'student': blocker, 'has_candidate': False,
                'candidate': None, 'candidate_group': None,
            })

    return {
        'target_weekdays': [WEEKDAY_NAMES.get(w, str(w)) for w in wds],
        'target_time': times[0],
        'blockers': blockers_info,
        'truly_stuck': [b['student'] for b in blockers_info if not b['has_candidate']],
    }


def _try_minimal_disruption_swap(grp, course, teacher):
    """
    YANGI, ENG KUCHLI resolver — foydalanuvchi talabiga ko'ra:
    "100% avtomatlashtirilishi kerak, qolganlari buzilsa ham sinab ko'raversin,
    eng kam muammolisini topsin".

    Ishlash tartibi:
    1. Guruh uchun BARCHA mumkin (hafta_kuni, para_blok) kombinatsiyalarini
       sanaydi va HAR BIRIDA nechta talaba to'siq ekanini hisoblaydi.
    2. ENG KAM to'siqli variantni tanlaydi (masalan 08:30da 2ta, 12:00da 5ta
       bo'lsa — 08:30 tanlanadi).
    3. Har bir to'siq talaba uchun, xuddi shu fanning BOSHQA (hatto
       muvaffaqiyatli tuzilgan) guruhlaridan mos NOMZOD qidiradi — ya'ni
       "meni band qilgan talaba" bilan "u band bo'lgan boshqa guruhdagi,
       lekin MENING vaqtimda bo'sh bo'lgan talaba"ni ALMASHTIRADI. Bu —
       ikkala tomon ham o'z jadvaliga mos kelishini talab qiladigan haqiqiy
       (ikki tomonlama) almashtirish, shuning uchun boshqa muvaffaqiyatli
       guruh HAM davom etadi (faqat bitta talabasi almashadi).
    4. Agar biror to'siq talaba uchun HECH QANDAY nomzod topilmasa (masalan
       uning butun haftasi allaqachon boshqa fanlar bilan to'lgan) — faqat
       O'SHA talaba(lar) asosiy guruhdan chiqarilib, alohida (tuzilmagan)
       kichik guruhga o'tkaziladi — BUTUN guruh emas, faqat haqiqatan iloji
       yo'q individual talaba(lar) "hal qilinmagan" deb qoladi.

    Natija: MIN_GROUP_SIZE (8) qoidasi doim saqlanadi — agar juda ko'p
    talaba chiqib ketishi kerak bo'lib, qolgan qism 8 dan kam bo'lib
    qolsa, bu urinish butunlay bekor qilinadi (False qaytadi).
    """
    students = list(grp.students.all())
    student_ids = set(s.id for s in students)
    teacher_id = teacher.id if teacher else None
    total_lessons = course.total_lessons
    start_date = course.start_date
    include_saturday = getattr(course, 'include_saturday', False)
    max_wd = 5 if include_saturday else 4

    # ── MUHIM: agar guruh BOSHIDANOQ MIN_GROUP_SIZE dan kam bo'lsa
    # (masalan 6-7 kishilik "qoldiq"), bu funksiya uni MUSTAQIL guruh
    # sifatida TUZMAYDI — hatto to'qnashuvsiz vaqt topilsa ham. Sabab:
    # foydalanuvchi qoidasi — "hech qaysi guruh 8 dan kam bo'lmasin" —
    # bu funksiyaning o'zi hajmni o'zgartirmasa ham amal qiladi. Bunday
    # kichik qoldiqlar boshqa (parallel) guruhga QO'SHILISHI kerak, mustaqil
    # guruh sifatida emas — buni `_try_partial_distribute_and_reschedule`
    # yoki `_try_dissolve_and_distribute_group` bajaradi.
    if len(students) < MIN_GROUP_SIZE:
        return False, None, []

    if total_lessons >= 20:
        weekday_options = [(0, 2, 4)]
    elif 12 <= total_lessons <= 20:
        weekday_options = [(1, 3)]
    else:
        weekday_options = [(wd,) for wd in range(0, max_wd + 1)]

    # ── 1-2 BOSQICH: eng kam to'siqli (hafta_kuni, blok) ni topish ──
    candidates = []
    for wds in weekday_options:
        dates = _slot_occurrence_dates(start_date, wds, total_lessons)
        if not dates:
            continue
        for (p1, p2) in VALID_PARA_PAIRS:
            times = [PARA_TIMES[p1][0], PARA_TIMES[p2][0]]
            if teacher_id and GroupSchedule.objects.filter(
                date__in=dates, start_time__in=times, group__teacher_id=teacher_id,
            ).exclude(group=grp).exists():
                continue  # o'qituvchi band -> bu slot umuman ishlamaydi
            # ── MUHIM TUZATISH: bu yerda ham "bitta fandan bir parada
            # MAX_GROUPS_PER_SLOT_NO_TEACHER (4) tadan ortiq guruh
            # bo'lmasin" chegarasi hisobga olinmagan edi — natijada bu
            # funksiya (talaba almashtirish orqali) allaqachon 4 ta guruh
            # bilan TO'LGAN slotga yana bir guruhni "siqib kirita" olardi.
            # Endi bunday to'lgan slotlar butunlay nomzodlikdan chiqariladi.
            if teacher_id is None:
                existing_same_subject = GroupSchedule.objects.filter(
                    date__in=dates, start_time__in=times,
                    group__course__subject=course.subject,
                    group__is_scheduled=True,
                ).exclude(group=grp).values_list('group_id', flat=True).distinct().count()
                if existing_same_subject >= 4:  # MAX_GROUPS_PER_SLOT_NO_TEACHER
                    continue
            blocker_ids = set(GroupSchedule.objects.filter(
                date__in=dates, start_time__in=times, group__students__id__in=student_ids,
            ).exclude(group=grp).values_list('group__students__id', flat=True))
            candidates.append((len(blocker_ids), wds, p1, p2, dates, blocker_ids))

    if not candidates:
        return False, None, []

    candidates.sort(key=lambda c: c[0])
    _, wds, p1, p2, dates, blocker_ids = candidates[0]
    times = [PARA_TIMES[p1][0], PARA_TIMES[p2][0]]

    # ── 3-BOSQICH: har bir to'siq talaba uchun almashtirish nomzodi qidirish ──
    same_subject_groups = list(course.groups.exclude(pk=grp.pk).filter(is_scheduled=True).order_by('pk'))
    swaps = []
    unresolved = []
    used_candidates = set()

    for bid in sorted(blocker_ids):
        blocker = next(s for s in students if s.id == bid)
        swap_found = None
        for og in same_subject_groups:
            og_dates_times = set(GroupSchedule.objects.filter(group=og).values_list('date', 'start_time'))
            for cand in og.students.order_by('id'):
                if cand.id in used_candidates:
                    continue
                cand_conflict = GroupSchedule.objects.filter(
                    date__in=dates, start_time__in=times, group__students=cand,
                ).exclude(group=og).exists()
                if cand_conflict:
                    continue
                blocker_conflict = any(
                    GroupSchedule.objects.filter(date=d, start_time=t, group__students=blocker)
                    .exclude(group=grp).exists()
                    for d, t in og_dates_times
                )
                if blocker_conflict:
                    continue
                swap_found = (og, cand)
                break
            if swap_found:
                break
        if swap_found:
            og, cand = swap_found
            swaps.append((blocker, cand, og))
            used_candidates.add(cand.id)
        else:
            unresolved.append(blocker)

    # ── MUHIM BUG TUZATISH: agar boshidanoq HECH QANDAY to'siq bo'lmasa
    # (blocker_ids bo'sh) — bu ALLAQACHON to'liq bo'sh, mukammal slot
    # topilgani, hech qanday almashtirish kerak emasligini bildiradi.
    # Eski kod buni "swaps bo'sh -> muvaffaqiyatsiz" deb XATO talqin
    # qilardi — aslida bu ENG YAXSHI holat (0 talaba chiqarish/almashtirish
    # kerak emas). Endi bu holatni alohida, to'g'ri tekshiramiz.
    if not blocker_ids:
        pass  # swaps=[] bilan davom etamiz — pastdagi saqlash bloki buni to'g'ri bajaradi
    elif not swaps:
        return False, None, []

    # YANGI (foydalanuvchi talabiga ko'ra): endi FAQAT hamma to'siq talaba
    # uchun almashtirish topilgan bo'lsagina davom etamiz. Agar birortasiga
    # ham nomzod topilmasa — BUTUN urinish bekor qilinadi, hech kim
    # guruhdan chiqarilmaydi va hech qanday kichik "qoldiq" guruh
    # yaratilmaydi (guruh shunchaki "hal qilinmagan" bo'lib qoladi, keyingi
    # resolverga yoki qo'lda ko'rib chiqishga o'tadi).
    if unresolved:
        return False, None, []

    # Eslatma: bu yerda MIN_GROUP_SIZE tekshiruvi KERAK EMAS — chunki bu
    # funksiya `grp` hajmini HECH QACHON o'zgartirmaydi (har bir chiqqan
    # talabaga aynan bittadan kiruvchi to'g'ri keladi, sof almashtirish).
    # Agar `grp` boshidanoq MIN_GROUP_SIZE dan kam bo'lgan "qoldiq" guruh
    # bo'lsa ham (masalan 6 kishi) — bu funksiya uning hajmini
    # o'zgartirmagani uchun bu holat qoidani buzmaydi.
    # ── 4-BOSQICH: saqlash (swap + yakuniy guruh tarkibi) ──
    with transaction.atomic():
        for blocker, cand, og in swaps:
            og_students = [s for s in og.students.all() if s.id != cand.id]
            og_students.append(blocker)
            og.students.set(og_students)
            sync_group_language(og)

        swapped_out_ids = {b.id for b, _, _ in swaps}
        final_students = [s for s in students if s.id not in swapped_out_ids]
        final_students += [c for _, c, _ in swaps]

        grp.students.set(final_students)
        grp.start_time = times[0]
        grp.weekdays = list(wds)
        grp.is_scheduled = True
        grp.save()
        sync_group_language(grp)

        GroupSchedule.objects.filter(group=grp).delete()
        GroupSchedule.objects.bulk_create([
            GroupSchedule(group=grp, date=d, start_time=times[0], lesson_number=2 * i + 1)
            for i, d in enumerate(dates)
        ] + [
            GroupSchedule(group=grp, date=d, start_time=times[1], lesson_number=2 * i + 2)
            for i, d in enumerate(dates)
        ])
        # YANGI: endi bu funksiya faqat TO'LIQ muvaffaqiyatli bo'lgandagina
        # shu yergacha yetib keladi (barcha to'siqlar almashtirilgan), shuning
        # uchun "qoldiq guruh" yaratish shart emas — hech kim ortiqcha
        # chiqarilmaydi, MIN_GROUP_SIZE hech qachon buzilmaydi.

    names_swapped = ", ".join(f"{b} <-> {c}" for b, c, _ in swaps)
    if swaps:
        msg = (
            f"'{grp}' guruhi eng kam to'siqli vaqtga ({wds}, {times[0]}) joylashtirildi. "
            f"{len(swaps)} ta talaba boshqa guruh bilan almashtirildi: {names_swapped}."
        )
    else:
        msg = f"'{grp}' guruhi hech qanday to'siqsiz, to'liq bo'sh vaqtga ({wds}, {times[0]}) joylashtirildi."
    return True, msg, []


def _try_split_group_and_schedule(grp, course, teacher, num_parts=2):
    """
    YANGI: Guruhni N ta (standart 2) kichik qismga bo'lib, HAR BIRINI
    ALOHIDA (mustaqil) vaqtga joylashtirishga urinadi.

    Sabab: 18 kishilik guruhning BARCHASI bir vaqtda bo'sh bo'lishi kam
    ehtimol, lekin uni 2 ta 9 kishilik qismga bo'lsak, har bir kichik
    qismning o'z ichida bo'sh vaqt topish ehtimoli SEZILARLI oshadi —
    va ikkala qism ham bir xil vaqtga tushishi shart emas (ikkalasi
    turli kunlarga/bloklarga tushishi mumkin).

    Faqat BARCHA qismlar to'liq (course.total_lessons ga teng) joylasha
    olsagina o'zgarish saqlanadi — aks holda hech narsa o'zgarmaydi
    (rollback), False qaytadi.
    """
    students = list(grp.students.all())
    # ── MUHIM: MIN_GROUP_SIZE qoidasini hech qachon buzmaymiz. ──
    # Har bir qism KAMIDA MIN_GROUP_SIZE (hozir 8) talabaga ega bo'lishi
    # shart — aks holda bo'lish ma'nosiz (yangi, qoidabuzar kichik
    # guruhlar yaratib qo'yamiz).
    if len(students) < num_parts * MIN_GROUP_SIZE:
        return False, None

    parts = [[] for _ in range(num_parts)]
    for i, s in enumerate(students):
        parts[i % num_parts].append(s)

    results = []
    for part_students in parts:
        sched = find_schedule_for_group(
            course.start_date, course.end_date, course.total_lessons,
            course.lessons_per_week, teacher, part_students,
            group_number=grp.group_number,
        )
        if len(sched) < course.total_lessons:
            return False, (
                f"'{grp}' guruhini {num_parts} qismga bo'lish ham yordam bermadi "
                f"({len(part_students)} kishilik qism ham to'liq joylasha olmadi)."
            )
        results.append((part_students, sched))

    # Barcha qismlar muvaffaqiyatli -> saqlaymiz
    from collections import Counter
    existing_numbers = set(
        CourseGroup.objects.filter(course=course).values_list('group_number', flat=True)
    )
    next_number = (max(existing_numbers) + 1) if existing_numbers else 1

    with transaction.atomic():
        new_groups = []
        for idx, (part_students, sched) in enumerate(results):
            if idx == 0:
                target_grp = grp
                target_grp.students.set(part_students)
            else:
                target_grp = CourseGroup.objects.create(
                    course=course, teacher=teacher,
                    group_number=next_number,
                )
                next_number += 1
                target_grp.students.set(part_students)

            para_counter = Counter(p_start for _, p_start, _ in sched)
            most_common_para = para_counter.most_common(1)[0][0]
            target_grp.start_time = most_common_para
            target_grp.weekdays = list({d.weekday() for d, _, _ in sched})
            target_grp.is_scheduled = True
            target_grp.save()
            sync_group_language(target_grp)

            GroupSchedule.objects.filter(group=target_grp).delete()
            GroupSchedule.objects.bulk_create([
                GroupSchedule(group=target_grp, date=d, start_time=p_start, lesson_number=i + 1)
                for i, (d, p_start, p_end) in enumerate(sched)
            ])
            new_groups.append(target_grp)

    names = ", ".join(str(g) for g in new_groups)
    return True, (
        f"'{course.subject if course else '?'}' guruhi {num_parts} qismga bo'lindi "
        f"va har biri alohida vaqtga muvaffaqiyatli joylashtirildi: {names}"
    )


def _auto_resolve_conflicts_by_subject_swap(grp_a, conflicts, already_moved_student_ids=None):
    """
    Parallel guruhlar orasida o'quvchilarni almashtiradi.
    Til (language) cheklovi mutlaqo olib tashlandi - o'zbek va rus guruh o'quvchilari o'rin almasha oladi!
    Guruh hajmi chegaralari: MIN_GROUP_SIZE / MAX_GROUP_SIZE (yuqorida belgilangan) —
    manba guruh (og) MIN_GROUP_SIZE dan kamayib qolmasligi, maqsadli guruh (cand) esa
    MAX_GROUP_SIZE dan oshib ketmasligi qat'iy tekshiriladi.
    """
    messages_out = []
    if not conflicts:
        return messages_out

    if already_moved_student_ids is None:
        already_moved_student_ids = set()

    grp_a_student_ids = set(grp_a.students.values_list('id', flat=True))

    conflict_map = defaultdict(set)
    for c in conflicts:
        if c.get('type') != 'student':
            continue
        for st in c.get('busy_students', []):
            if st.pk in already_moved_student_ids:
                continue
            conflict_map[(st, c['group'])].add((c['date'], c['para_time'][0]))

    if not conflict_map:
        return messages_out

    for (st, og), conflict_times in conflict_map.items():
        if st.pk in already_moved_student_ids:
            continue

        if not og.students.filter(pk=st.pk).exists():
            continue

        oc = og.course
        og_student_count = og.students.count()
        # MUHIM: `og`ning O'ZINING to'liq jadvali kerak — ret_st (qaytaruvchi
        # talaba) shu guruhga qo'shilganda haqiqiy to'qnashuv chiqmasligini
        # tekshirish uchun (avval bu o'rniga grp_a.teacher jadvali solishtirilardi —
        # bu NOTO'G'RI edi, chunki ret_st OG ga qo'shiladi, grp_a ga emas).
        og_times = set(
            GroupSchedule.objects.filter(group=og).values_list('date', 'start_time')
        )

        # MUHIM: `st` (ko'chiriladigan talaba)ning TO'LIQ band jadvali —
        # faqat grp_a bilan bog'liq to'qnashuvlar (conflict_times) emas.
        # Aks holda st boshqa, mutlaqo aloqasi bo'lmagan biror fanga
        # yangi guruhda (cand) tasodifan to'qnashib qolishi mumkin edi.
        st_full_busy = set(
            GroupSchedule.objects.filter(group__students=st)
            .exclude(group__in=[og, grp_a])
            .values_list('date', 'start_time')
        )

        # MUHIM: `course=oc` (aynan bitta Course yozuvi) o'rniga endi
        # `course__subject=oc.subject` — chunki bir xil fan turli Course
        # sifatida (masalan turli oqim/fakultet uchun) yaratilgan bo'lishi
        # mumkin. Avvalgi qidiruv bunday hollarda parallel guruhni umuman
        # topa olmasdi.
        candidates = CourseGroup.objects.filter(
            course__subject=oc.subject, is_scheduled=True
        ).exclude(pk=og.pk).select_related('teacher').prefetch_related(
            'students',
            Prefetch('schedule', to_attr='cached_schedules')
        )

        if not candidates.exists():
            continue

        # Hamma nomzod talabalarni yig'ish (Tilidan qat'iy nazar)
        all_candidate_student_ids = set()
        for cand in candidates:
            for ret_st in cand.students.all():
                if ret_st.id != st.pk:
                    all_candidate_student_ids.add(ret_st.id)

        student_busy_map = defaultdict(set)
        if all_candidate_student_ids:
            ret_busy_schedules = GroupSchedule.objects.filter(
                group__students__in=all_candidate_student_ids
            ).values('group__students__id', 'date', 'start_time')

            for sch in ret_busy_schedules:
                student_busy_map[sch['group__students__id']].add((sch['date'], sch['start_time']))

        for cand in candidates:
            cand_times = {(sch.date, sch.start_time) for sch in cand.cached_schedules}
            if conflict_times & cand_times:
                continue
            # YANGI TEKSHIRUV: st ning TO'LIQ jadvali cand bilan to'qnashmasin
            if st_full_busy & cand_times:
                continue

            cand_student_count = cand.students.count()

            # Nomzod talabalar ro'yxati (Til cheklovisiz)
            cand_students = [
                ret_st for ret_st in cand.students.all()
                if ret_st.id != st.pk
            ]

            safe_return = None
            if cand_students:
                for ret_st in cand_students:
                    ret_busy_times = student_busy_map[ret_st.id]
                    # TUZATILGAN: ret_st OG ga qo'shiladi — demak uning band
                    # vaqtlari OG ning O'ZINING jadvali bilan solishtirilishi kerak
                    conflict_for_ret = bool(ret_busy_times & og_times)

                    if not conflict_for_ret:
                        safe_return = ret_st
                        break

            # ── QAT'IY SHART 1: Agar safe_return (o'rniga keladigan) topilmasa
            # va original guruhda o'quvchi soni MIN_GROUP_SIZE dan kamayib qolsa,
            # ko'chirishga mutlaqo yo'l qo'ymaymiz ──
            if not safe_return and (og_student_count - 1) < MIN_GROUP_SIZE:
                continue

            # ── QAT'IY SHART 2 (YANGI): Agar safe_return topilmasa (bir tomonlama
            # ko'chirish bo'ladi), cand guruh MAX_GROUP_SIZE dan oshib ketmasligi
            # kerak. safe_return bo'lsa, cand hajmi o'zgarmaydi (bittasi chiqib,
            # bittasi kiradi) — shuning uchun bu holatda tekshirish shart emas.
            if not safe_return and cand_student_count + 1 > MAX_GROUP_SIZE:
                continue

            with transaction.atomic():
                og.students.remove(st)
                cand.students.add(st)

                log_msg = f"O'quvchi {st} '{og}' guruhidan '{cand}' guruhiga ko'chirildi."

                if safe_return:
                    cand.students.remove(safe_return)
                    og.students.add(safe_return)
                    log_msg += f" O'rniga '{safe_return}' qaytarildi (Swap)."
                else:
                    log_msg += f" Bir tomonlama ko'chirish bajarildi (Guruhda {og_student_count - 1} o'quvchi qoldi)."

                sync_group_language(og)
                sync_group_language(cand)

                messages_out.append(log_msg)

            already_moved_student_ids.add(st.pk)
            break

    return messages_out


def _auto_resolve_via_parallel_swap(grp_a):
    """
    Guruhdagi eng ziddiyatli talabani topib, uni parallel guruhga o'tkazadi.
    O'qituvchi yo'q bo'lsa, o'qituvchi tekshiruvini chetlab o'tib ishlayveradi.
    """
    start = grp_a.course.start_date
    end = grp_a.course.end_date

    teacher_free_slots = set()
    has_teacher = bool(grp_a.teacher_id)

    cur = start
    while cur <= end:
        if cur.weekday() <= 4:  # Dushanba - Juma
            if has_teacher:
                teacher_busy = set()
                for sc in GroupSchedule.objects.filter(date=cur, group__teacher=grp_a.teacher):
                    st = sc.start_time or sc.group.start_time
                    if st:
                        for i, (ps, _) in enumerate(PARA_TIMES):
                            if ps == st:
                                teacher_busy.add(i)
                for i in range(len(PARA_TIMES)):
                    if i not in teacher_busy:
                        teacher_free_slots.add((cur, i))
            else:
                # O'qituvchi bo'lmasa, barcha vaqtlar ochiq deb hisoblanadi
                for i in range(len(PARA_TIMES)):
                    teacher_free_slots.add((cur, i))
        cur += timedelta(days=1)

    if not teacher_free_slots:
        return None

    students_a = list(grp_a.students.all())
    student_a_ids = set(s.id for s in students_a)
    block_counts = defaultdict(int)

    for sc in GroupSchedule.objects.filter(
            date__range=(start, end),
            group__students__id__in=student_a_ids,
    ).prefetch_related('group__students'):
        st = sc.start_time or sc.group.start_time
        if st:
            for i, (ps, _) in enumerate(PARA_TIMES):
                if ps == st and (sc.date, i) in teacher_free_slots:
                    for s in sc.group.students.all():
                        if s.id in student_a_ids:
                            block_counts[s.id] += 1

    if not block_counts:
        return None

    # Eng ko'p ziddiyatga uchrayotgan talabani aniqlaymiz
    bad_id = max(block_counts, key=block_counts.get)
    bad_student = Student.objects.get(id=bad_id)

    # MUHIM: aniq matn tengligi (`language=grp_a.language`) o'rniga endi
    # TIL KESISHMASI tekshiriladi. Chunki guruh tili endi talabalar tarkibiga
    # qarab avtomatik hisoblanadi (`sync_group_language`) va aralash bo'lishi
    # mumkin (masalan 'uz-ru'). Aniq tenglik bo'lganda sof 'uz' guruh bilan
    # aralash 'uz-ru' guruh bir-biriga umuman mos kelmay qolardi — bu esa
    # asossiz ravishda ko'plab haqiqiy nomzodlarni chetlab o'tishga olib kelardi.
    grp_a_langs = parse_group_langs(grp_a.language)
    all_subject_groups = list(
        CourseGroup.objects.filter(
            course__subject=grp_a.course.subject,
        ).exclude(pk=grp_a.pk).prefetch_related('students')
    )
    lang_matched_groups = [
        g for g in all_subject_groups
        if parse_group_langs(g.language) & grp_a_langs
    ]

    # MUHIM: bad_student ning O'ZI ham yangi guruhga (p_grp) mos kelishi kerak —
    # avval faqat "candidate" (qaytaruvchi talaba) tekshirilar edi, bad_student
    # ning o'zi p_grp bilan to'qnashib qolishi mumkinligi HECH tekshirilmagan edi!
    bad_student_full_busy = set(
        GroupSchedule.objects.filter(group__students=bad_student)
        .exclude(group=grp_a)
        .values_list('date', 'start_time')
    )

    def _find_safe_swap(search_groups):
        """Berilgan guruhlar ro'yxatidan xavfsiz swap (safe_candidate + grp_b) qidiradi."""
        for p_grp in search_groups:
            p_grp_times = set(
                GroupSchedule.objects.filter(group=p_grp).values_list('date', 'start_time')
            )
            if bad_student_full_busy & p_grp_times:
                # bad_student ning o'zi shu guruhga to'g'ri kelmaydi — keyingisiga o'tamiz
                continue

            for candidate in p_grp.students.all():
                if candidate.id in student_a_ids:
                    continue

                cand_busy = set()
                for sc in GroupSchedule.objects.filter(
                        group__students=candidate,
                        date__range=(start, end)
                ):
                    st = sc.start_time or sc.group.start_time
                    if st:
                        for i, (ps, _) in enumerate(PARA_TIMES):
                            if ps == st:
                                cand_busy.add((sc.date, i))

                if not (teacher_free_slots & cand_busy):
                    return candidate, p_grp
        return None, None

    def _find_one_way(search_groups):
        """Berilgan guruhlar ro'yxatidan bir tomonlama ko'chirish uchun bo'sh
        VA hajmi MAX_GROUP_SIZE dan oshib ketmaydigan guruh qidiradi."""
        bad_busy_times = set(
            GroupSchedule.objects.filter(group__students=bad_student)
            .exclude(group=grp_a)
            .values_list('date', 'start_time')
        )
        for p_grp in search_groups:
            # YANGI TEKSHIRUV: bir tomonlama ko'chirish guruhni MAX_GROUP_SIZE
            # dan oshirib yubormasligi kerak (avval bu tekshirilmagan edi)
            if p_grp.students.count() + 1 > MAX_GROUP_SIZE:
                continue
            p_grp_times = set(
                GroupSchedule.objects.filter(group=p_grp)
                .values_list('date', 'start_time')
            )
            if not (bad_busy_times & p_grp_times):
                return p_grp
        return None

    # 1-URINISH: til mos keladigan guruhlar orasidan qidiramiz (afzal variant)
    safe_candidate, grp_b = _find_safe_swap(lang_matched_groups)
    used_cross_language = False

    # 2-OXIRGI IMKON: til mos kelmasa ham, HECH bo'lmaganda joy topilishi uchun
    # BARCHA fan guruhlaridan (tildan qat'iy nazar) qidiramiz. Bu faqat til mos
    # guruhlar orasida yechim topilmagandagina ishga tushadi.
    if not safe_candidate and len(lang_matched_groups) < len(all_subject_groups):
        cross_lang_groups = [g for g in all_subject_groups if g not in lang_matched_groups]
        safe_candidate, grp_b = _find_safe_swap(cross_lang_groups)
        if safe_candidate:
            used_cross_language = True

    # Agar o'rniga qaytadigan (safe_candidate) topilmasa, bir tomonlama ko'chirishga harakat qilamiz
    if not safe_candidate:
        fallback_grp_b = None
        # O'quvchilar MIN_GROUP_SIZE dan kam bo'lib qolmasligi uchun
        if (grp_a.students.count() - 1) >= MIN_GROUP_SIZE:
            # 1-URINISH: til mos keladigan guruhlar orasidan
            fallback_grp_b = _find_one_way(lang_matched_groups)
            # 2-OXIRGI IMKON: hech biri topilmasa, tildan qat'iy nazar barcha guruhlardan
            if not fallback_grp_b and len(lang_matched_groups) < len(all_subject_groups):
                cross_lang_groups = [g for g in all_subject_groups if g not in lang_matched_groups]
                fallback_grp_b = _find_one_way(cross_lang_groups)
                if fallback_grp_b:
                    used_cross_language = True

        if fallback_grp_b:
            with transaction.atomic():
                grp_a.students.remove(bad_student)
                fallback_grp_b.students.add(bad_student)
                sync_group_language(grp_a)
                sync_group_language(fallback_grp_b)

            teacher_status = "" if has_teacher else " (O'qituvchi belgilanmagan)"
            lang_note = " ⚠️ (til mos guruh topilmagani uchun boshqa tildagi guruhga ko'chirildi)" if used_cross_language else ""
            return (
                f"✅ Avtomatik ko'chirish{teacher_status}: '{grp_a.course.subject}' "
                f"{bad_student.first_name} → {fallback_grp_b.group_number}-guruhga ko'chirildi "
                f"(guruh tarkibi 9 tadan kam bo'lib qolmadi).{lang_note}"
            )
        return None

    # Muvaffaqiyatli almashtirish (Swap)
    with transaction.atomic():
        grp_a.students.remove(bad_student)
        grp_b.students.add(bad_student)
        grp_b.students.remove(safe_candidate)
        grp_a.students.add(safe_candidate)
        sync_group_language(grp_a)
        sync_group_language(grp_b)

    teacher_status = "" if has_teacher else " (O'qituvchi belgilanmagan)"
    lang_note = " ⚠️ (til mos guruh topilmagani uchun boshqa tildagi guruh bilan almashtirildi)" if used_cross_language else ""
    return (
        f"✅ Avtomatik almashtirish{teacher_status}: '{grp_a.course.subject}' "
        f"{bad_student.first_name} → {grp_b.group_number}-guruhga, "
        f"{safe_candidate.first_name} → {grp_a.group_number}-guruhga almashtirildi.{lang_note}"
    )


@login_required
def build_schedule(request):
    """
    To'liq, avtomatlashtirilgan dars jadvalini tuzish funksiyasi.
    while tsikli yordamida zanjirli optimallashtirish (bitta bosishda maksimal natija).
    """
    auto_resolve_messages = []
    group_last_positions = {}
    already_moved_students = set()
    total_success_count = 0

    def sort_key(g):
        total_lessons = g.course.total_lessons if g.course else 0
        student_count = len(g.students.all())
        return (-total_lessons, -student_count)

    def _count_feasible_slots(grp, course, teacher, busy_index):
        """
        MRV evristikasi uchun: shu guruh nechta (hafta_kunlari, para_blok)
        kombinatsiyasiga TO'LIQ (butun kurs davomida, hech qanday
        to'qnashuvsiz) sig'ishini hisoblaydi. Natija qancha kichik bo'lsa,
        guruh shuncha "qiyin" — shuning uchun birinchi ishlanishi kerak
        (aks holda "oson" guruhlar eng yaxshi joylarni oldindan band
        qilib qo'yadi).
        """
        if not course:
            return 999
        student_ids = [s.id for s in grp.students.all()]
        teacher_id = teacher.id if teacher else None
        total_lessons = course.total_lessons
        include_saturday = getattr(course, 'include_saturday', False)
        max_wd = 5 if include_saturday else 4

        if total_lessons >= 20:
            weekday_sets = [(0, 2, 4)]
        elif 12 <= total_lessons <= 20:
            weekday_sets = [(1, 3)]
        else:
            weekday_sets = [(wd,) for wd in range(0, max_wd + 1)]

        count = 0
        for wds in weekday_sets:
            dates = _slot_occurrence_dates(course.start_date, wds, total_lessons)
            for p1, p2 in VALID_PARA_PAIRS:
                ok = True
                for d in dates:
                    for pi in (p1, p2):
                        if teacher_id and not busy_index.teacher_free(teacher_id, d, pi):
                            ok = False
                            break
                        if not busy_index.group_free(student_ids, d, pi):
                            ok = False
                            break
                    if not ok:
                        break
                if ok:
                    count += 1
        return count

    def _rebuild_schedule(grp, course, teacher, busy_index=None):
        same_subject_busy = list(
            GroupSchedule.objects.filter(
                group__course__subject=course.subject,
                group__is_scheduled=True,
            ).exclude(group=grp).values_list('date', 'start_time')
        )

        sched = find_schedule_for_group(
            course.start_date, course.end_date,
            course.total_lessons, course.lessons_per_week,
            teacher, list(grp.students.all()),
            group_number=grp.group_number,
            include_saturday=getattr(course, 'include_saturday', False),
            same_subject_busy=same_subject_busy,
            busy_index=busy_index,   # ← berilsa, get_hard_busy SQL yubormaydi
        )
        fc = len(sched)
        cf = getattr(find_schedule_for_group, '_last_conflict_info', [])
        return sched, fc, cf

    def _run_scheduling_pass():
        # ── 🔄 MULTI-PASS OPTIMIZATION (WHILE TSIKLI) ──
        iteration = 0
        max_iterations = 40

        while iteration < max_iterations:
            iteration += 1

            unscheduled_groups = list(
                CourseGroup.objects.filter(
                    is_scheduled=False
                ).select_related('course', 'course__subject', 'teacher')
                .prefetch_related('students')
            )

            if not unscheduled_groups:
                break

            from collections import defaultdict as _dd
            by_course = _dd(list)
            for g in unscheduled_groups:
                if g.course_id:
                    by_course[g.course_id].append(g)

            regrouped_any = False
            for course_id, groups_here in by_course.items():
                if len(groups_here) < 2:
                    continue
                course_obj = groups_here[0].course
                has_scheduled_sibling = CourseGroup.objects.filter(
                    course_id=course_id, is_scheduled=True
                ).exists()
                if has_scheduled_sibling:
                    continue
                teacher_here = groups_here[0].teacher if groups_here[0].teacher_id else None
                ok, msg = _try_regroup_same_subject(course_obj, teacher_here, groups_here)
                if ok:
                    auto_resolve_messages.append(msg)
                    regrouped_any = True

            if regrouped_any:
                iteration_success_count = 1
                continue

            unscheduled_list = sorted(unscheduled_groups, key=sort_key)
            iteration_success_count = 0

            date_from = min((g.course.start_date for g in unscheduled_list if g.course), default=None)
            date_to = max((g.course.end_date for g in unscheduled_list if g.course), default=None)
            busy_index = None
            if date_from and date_to:
                busy_index = BusyIndex.build(
                    date_from - timedelta(weeks=4), date_to + timedelta(weeks=24),
                    GroupSchedule=GroupSchedule,
                )

                def _mrv_key(g):
                    feasible = _count_feasible_slots(g, g.course, g.teacher, busy_index)
                    fallback = sort_key(g)
                    return (feasible,) + fallback

                unscheduled_list = sorted(unscheduled_list, key=_mrv_key)

            for grp in unscheduled_list:
                if not CourseGroup.objects.filter(pk=grp.pk).exists():
                    if grp.course_id and CourseGroup.objects.filter(course_id=grp.course_id, students__isnull=False).exists():
                        pass
                    continue

                course = grp.course
                teacher = grp.teacher if grp.teacher_id else None

                schedule = []
                found_count = 0
                conflicts = []

                # ── 1-BOSQICH: To'g'ridan-to'g'ri joylashtirish ──
                find_schedule_for_group._last_conflict_info = []
                find_schedule_for_group._last_missing = 0
                find_schedule_for_group._last_no_slot_in_week = False

                schedule, found_count, conflicts = _rebuild_schedule(grp, course, teacher, busy_index=busy_index)

                # ── 2-BOSQICH: Joy topilmasa — 3 ta asosiy aqlli algoritmni ishga tushirish ──
                if found_count < course.total_lessons:
                    MAX_ROUNDS = 80
                    for _ in range(MAX_ROUNDS):
                        if found_count >= course.total_lessons:
                            break
                        changed = False

                        # 1. ALGORITM: Talaba almashtirish (Subject swap)
                        sid = transaction.savepoint()
                        resolved = _auto_resolve_conflicts_by_subject_swap(
                            grp, conflicts, already_moved_student_ids=already_moved_students
                        )
                        if resolved:
                            test_schedule, test_fc, test_cf = _rebuild_schedule(grp, course, teacher)
                            if test_fc <= found_count:
                                transaction.savepoint_rollback(sid)
                            else:
                                transaction.savepoint_commit(sid)
                                auto_resolve_messages.extend(resolved)
                                schedule, found_count, conflicts = test_schedule, test_fc, test_cf
                                changed = True
                                # ── YANGI, MUHIM TUZATISH: bu algoritm boshqa
                                # guruhlarning talaba tarkibini o'zgartiradi
                                # (almashtirish orqali) — busy_index bu haqda
                                # bilmaydi, shuning uchun uni bekor qilamiz,
                                # shu iteratsiyaning qolgan guruhlari xavfsiz
                                # (har doim yangi SQL bilan) yo'lga o'tsin.
                                busy_index = None
                                if found_count >= course.total_lessons:
                                    break

                        # 2. ALGORITM: Parallel swap
                        sid = transaction.savepoint()
                        swap_msg = _auto_resolve_via_parallel_swap(grp)
                        if swap_msg:
                            test_schedule, test_fc, test_cf = _rebuild_schedule(grp, course, teacher)
                            if test_fc <= found_count:
                                transaction.savepoint_rollback(sid)
                            else:
                                transaction.savepoint_commit(sid)
                                auto_resolve_messages.append(swap_msg)
                                schedule, found_count, conflicts = test_schedule, test_fc, test_cf
                                changed = True
                                # ── YANGI: xuddi shu sabab bilan busy_index bekor qilinadi ──
                                busy_index = None
                                if found_count >= course.total_lessons:
                                    break

                        # 3. ALGORITM: Boshqa fan guruhi bilan vaqt almashish
                        sid = transaction.savepoint()
                        cross_msg = _auto_resolve_via_cross_subject_swap(
                            grp, conflicts, group_last_positions=group_last_positions
                        )
                        if cross_msg:
                            test_schedule, test_fc, test_cf = _rebuild_schedule(grp, course, teacher)
                            if test_fc <= found_count:
                                transaction.savepoint_rollback(sid)
                            else:
                                transaction.savepoint_commit(sid)
                                auto_resolve_messages.append(cross_msg)
                                schedule, found_count, conflicts = test_schedule, test_fc, test_cf
                                changed = True
                                # ── YANGI: bu algoritm boshqa (b_grp) guruhning
                                # BITTA kunlik vaqtini o'zgartiradi — busy_index
                                # bundan bexabar qolmasligi uchun bekor qilamiz ──
                                busy_index = None
                                if found_count >= course.total_lessons:
                                    break

                        if not changed:
                            break

                    # ── 3-BOSQICH: Brute Force chorasi ──
                    if found_count < course.total_lessons:
                        MAX_BRUTE_ROUNDS = 80
                        brute_used = 0

                        while found_count < course.total_lessons and brute_used < MAX_BRUTE_ROUNDS:
                            sid = transaction.savepoint()
                            brute_msg = _brute_force_find_slot(grp)

                            if brute_msg is None:
                                break

                            test_schedule, test_fc, test_cf = _rebuild_schedule(grp, course, teacher)
                            if test_fc <= found_count:
                                transaction.savepoint_rollback(sid)
                                break
                            else:
                                transaction.savepoint_commit(sid)
                                auto_resolve_messages.append(brute_msg)
                                schedule, found_count, conflicts = test_schedule, test_fc, test_cf
                                brute_used += 1
                                # ── YANGI: brute force ham boshqa guruhni ko'chiradi ──
                                busy_index = None

                # ── 💡 4-BOSQICH: MUAMMOLI TALABANI MAJBURIY SURISH ──
                if found_count < course.total_lessons:
                    same_course_groups = list(course.groups.all())
                    sid = transaction.savepoint()

                    eviction_msg = _auto_resolve_by_force_student_eviction(grp, conflicts, same_course_groups)
                    if eviction_msg:
                        test_schedule, test_fc, test_cf = _rebuild_schedule(grp, course, teacher)
                        if test_fc >= course.total_lessons:
                            transaction.savepoint_commit(sid)
                            auto_resolve_messages.append(eviction_msg)
                            schedule, found_count, conflicts = test_schedule, test_fc, test_cf
                            # ── YANGI: talabalar boshqa guruhlarga ko'chirilgani
                            # uchun busy_index eskirgan — bekor qilamiz ──
                            busy_index = None
                        else:
                            transaction.savepoint_rollback(sid)

                # ── 5-BOSQICH: ENG KAM TO'SIQLI VAQTNI TOPIB, TO'LIQ ALMASHTIRISH ──
                if found_count < course.total_lessons:
                    mds_ok, mds_msg, mds_unresolved = _try_minimal_disruption_swap(grp, course, teacher)
                    if mds_ok:
                        auto_resolve_messages.append(mds_msg)
                        # ── YANGI, MUHIM TUZATISH: bu funksiya grp'ni TO'G'RIDAN-
                        # TO'G'RI (o'zining ichida, busy_index'dan tashqarida)
                        # GroupSchedule.bulk_create bilan saqlaydi. build_schedule
                        # buni bilmagani uchun busy_index eskirib qoladi — aynan
                        # shu yerda "Biofizika vs Tarix" kabi kesishmalar paydo
                        # bo'lgan edi. Endi busy_index'ni bekor qilamiz, shunda
                        # shu iteratsiyaning qolgan guruhlari xavfsiz SQL yo'liga
                        # o'tadi va bu guruhning YANGI band vaqtlarini albatta ko'radi.
                        busy_index = None
                        iteration_success_count += 1
                        continue

                # ── 5.5-BOSQICH: KICHIK "QOLDIQ" GURUHNI AKA-UKA GURUHDAN
                # QO'SHIMCHA TALABA TORTIB, MIN_GROUP_SIZE GA YETKAZISH ──
                if found_count < course.total_lessons:
                    same_course_groups_absorb = list(course.groups.all())
                    absorb_ok, absorb_msg = _try_absorb_from_sibling_to_reach_minimum(
                        grp, course, teacher, same_course_groups_absorb
                    )
                    if absorb_ok:
                        auto_resolve_messages.append(absorb_msg)
                        busy_index = None  # ── YANGI ──
                        iteration_success_count += 1
                        continue

                # ── 6-BOSQICH: GURUHNI IKKIGA BO'LIB, HAR BIRINI ALOHIDA JOYLASHTIRISHGA URINISH ──
                if found_count < course.total_lessons:
                    split_ok, split_msg = _try_split_group_and_schedule(grp, course, teacher)
                    if split_ok:
                        auto_resolve_messages.append(split_msg)
                        busy_index = None  # ── YANGI ──
                        iteration_success_count += 1
                        continue

                # ── 7-BOSQICH: QISMAN TAQSIMLASH ──
                if found_count < course.total_lessons:
                    same_course_groups = list(course.groups.all())
                    partial_ok, partial_msg = _try_partial_distribute_and_reschedule(
                        grp, course, teacher, same_course_groups
                    )
                    if partial_ok:
                        auto_resolve_messages.append(partial_msg)
                        busy_index = None  # ── YANGI ──
                        iteration_success_count += 1
                        continue

                # ── 8-BOSQICH: JADVAL SHAKLLANMASA GURUHNI DINAMIK TARQATAMIZ (DISSOLUTION) ──
                if found_count < course.total_lessons:
                    same_course_groups = list(course.groups.all())
                    dissolved, dissolve_msg = _try_dissolve_and_distribute_group(grp, same_course_groups)
                    if dissolved:
                        auto_resolve_messages.append(dissolve_msg)
                        busy_index = None  # ── YANGI ──
                        iteration_success_count += 1
                        continue

                # ── 9-BOSQICH (ENG OXIRGI CHORA): 16-paralik kurslar uchun
                # Dush/Chor/Juma kunlarini ham sinash ──
                if found_count < course.total_lessons:
                    lr_ok, lr_msg = _try_last_resort_expand_weekdays(grp, course, teacher)
                    if lr_ok:
                        auto_resolve_messages.append(lr_msg)
                        busy_index = None  # ── YANGI ──
                        iteration_success_count += 1
                        continue

                # ── 10-BOSQICH (ENG SO'NGGI, ENG KUCHLI CHORA): to'siq
                # qiluvchi BOSHQA GURUHNI o'zini boshqa vaqtga ko'chirish ──
                if found_count < course.total_lessons:
                    reloc_ok, reloc_msg = _try_relocate_blocking_groups(grp, course, teacher)
                    if reloc_ok:
                        auto_resolve_messages.append(reloc_msg)
                        busy_index = None  # ── YANGI ──
                        iteration_success_count += 1
                        continue

                # ── 11-BOSQICH (ENG CHUQUR, ENG OXIRGI CHORA): 10-bosqich
                # faqat BITTA bosqichli ko'chirishga urinadi. Agar bu ham
                # yordam bermasa — endi REKURSIV, ko'p bosqichli (12
                # bosqichgacha) zanjirli qidiruvni sinaymiz: to'siq
                # guruhni ko'chirish uchun UNI bloklovchi guruh(lar)ni ham,
                # kerak bo'lsa ularni ham bloklovchilarni ham ko'chiramiz. ──
                if found_count < course.total_lessons:
                    deep_ok, deep_msg = _try_deep_cascade_relocate(grp, course, teacher)
                    if deep_ok:
                        auto_resolve_messages.append(deep_msg)
                        busy_index = None
                        iteration_success_count += 1
                        continue

                # ── 5.7-BOSQICH: agar jadval TOPILGAN bo'lsa-yu, lekin hajmi
                # MIN_GROUP_SIZE dan kam bo'lgani uchun saqlanmasa — ABSORB
                # funksiyasini sinaymiz ──
                if found_count >= course.total_lessons and grp.students.count() < MIN_GROUP_SIZE:
                    same_course_groups_absorb2 = list(course.groups.all())
                    absorb_ok2, absorb_msg2 = _try_absorb_from_sibling_to_reach_minimum(
                        grp, course, teacher, same_course_groups_absorb2
                    )
                    if absorb_ok2:
                        auto_resolve_messages.append(absorb_msg2)
                        busy_index = None  # ── YANGI ──
                        iteration_success_count += 1
                        continue

                # ── JADVALNI SAQLASH BLOKI ──
                group_size_ok = grp.students.count() >= MIN_GROUP_SIZE
                if found_count >= course.total_lessons and group_size_ok:
                    from collections import Counter
                    para_counter = Counter(p_start for _, p_start, _ in schedule)
                    most_common_para = para_counter.most_common(1)[0][0]
                    grp.start_time = most_common_para
                    grp.weekdays = list({d.weekday() for d, _, _ in schedule})
                    grp.is_scheduled = True

                    for attempt in range(5):
                        try:
                            with transaction.atomic():
                                grp.save()
                                GroupSchedule.objects.filter(group=grp).delete()
                                GroupSchedule.objects.bulk_create([
                                    GroupSchedule(
                                        group=grp, date=ld,
                                        lesson_number=idx, start_time=p_start
                                    )
                                    for idx, (ld, p_start, p_end) in enumerate(schedule, 1)
                                ])
                            break
                        except Exception:
                            time.sleep(0.5)
                            continue

                    # Bu yo'l busy_index'ni TO'G'RI, xotirada yangilaydi —
                    # qo'shimcha SQL yo'q, shuning uchun busy_index = None qilish
                    # SHART EMAS (aksincha, buni bekor qilish samaradorlikni
                    # yo'qotardi). Faqat resolverlar orqali (yuqoridagi 2/4/5-10
                    # bosqichlar) o'zgargan hollarda busy_index None qilinadi.
                    if busy_index is not None:
                        para_index_by_time = {ps: i for i, (ps, _) in enumerate(PARA_TIMES)}
                        dates_and_paras = [
                            (ld, para_index_by_time[p_start])
                            for (ld, p_start, p_end) in schedule
                            if p_start in para_index_by_time
                        ]
                        busy_index.record_scheduled(
                            group=grp,
                            teacher_id=teacher.id if teacher else None,
                            subject_id=course.subject_id,
                            student_ids=[s.id for s in grp.students.all()],
                            dates_and_paras=dates_and_paras,
                        )

                    last_lesson_date = schedule[-1][0] if schedule else None
                    if last_lesson_date and last_lesson_date > course.end_date:
                        overrun_days = (last_lesson_date - course.end_date).days
                        messages.warning(
                            request,
                            f"⏰ '{course.subject}' {grp.group_number}-guruh: band kunlar ko'pligi "
                            f"sababli oxirgi dars belgilangan tugash sanasidan "
                            f"({course.end_date.strftime('%d.%m.%Y')}) {overrun_days} kun keyin — "
                            f"{last_lesson_date.strftime('%d.%m.%Y')} da joylashdi. Kurs muddatini "
                            f"yoki band kunlarni ko'rib chiqishni tavsiya etamiz."
                        )

                    iteration_success_count += 1

            if iteration_success_count == 0:
                break

        # ── YANGI, YAKUNIY TOZALASH BOSQICHI ──
        small_leftover_groups = list(
            CourseGroup.objects.filter(is_scheduled=False)
            .select_related('course').prefetch_related('students')
        )
        for leftover in small_leftover_groups:
            if not leftover.course_id:
                continue
            current_count = leftover.students.count()
            if current_count == 0 or current_count >= MIN_GROUP_SIZE:
                continue

            needed = MIN_GROUP_SIZE - current_count
            siblings = list(
                CourseGroup.objects.filter(course_id=leftover.course_id)
                .exclude(pk=leftover.pk).prefetch_related('students')
            )
            taken_students = []
            for sib in siblings:
                if len(taken_students) >= needed:
                    break
                sib_students = list(sib.students.all())
                max_takeable = len(sib_students) - MIN_GROUP_SIZE
                if max_takeable <= 0:
                    continue
                take_n = min(max_takeable, needed - len(taken_students))
                to_take = sib_students[:take_n]
                remaining_sib = sib_students[take_n:]
                sib.students.set(remaining_sib)
                sync_group_language(sib)
                taken_students.extend(to_take)

            if taken_students:
                final_leftover_students = list(leftover.students.all()) + taken_students
                leftover.students.set(final_leftover_students)
                sync_group_language(leftover)

        # ── YANGI: GURUH HAJMLARINI TENGLASHTIRISH ──
        from collections import defaultdict as _dd2
        scheduled_by_course = _dd2(list)
        for g in CourseGroup.objects.filter(is_scheduled=True).select_related('course').prefetch_related('students'):
            if g.course_id:
                scheduled_by_course[g.course_id].append(g)

        for course_id, course_groups in scheduled_by_course.items():
            if len(course_groups) < 2:
                continue
            for _ in range(50):
                course_groups.sort(key=lambda g: g.students.count())
                smallest = course_groups[0]
                largest = course_groups[-1]
                diff = largest.students.count() - smallest.students.count()
                if diff <= 1:
                    break

                smallest_times = set(
                    GroupSchedule.objects.filter(group=smallest).values_list('date', 'start_time')
                )
                moved_one = False
                for s in list(largest.students.all()):
                    if largest.students.count() - 1 < MIN_GROUP_SIZE:
                        break
                    if smallest.students.count() + 1 > MAX_GROUP_SIZE:
                        break
                    s_busy = set(
                        GroupSchedule.objects.filter(group__students=s)
                        .exclude(group=largest).values_list('date', 'start_time')
                    )
                    if s_busy & smallest_times:
                        continue
                    new_largest = [x for x in largest.students.all() if x.id != s.id]
                    largest.students.set(new_largest)
                    sync_group_language(largest)
                    new_smallest = list(smallest.students.all()) + [s]
                    smallest.students.set(new_smallest)
                    sync_group_language(smallest)
                    moved_one = True
                    break
                if not moved_one:
                    break

        # ── TENGLASHTIRISHDAN KEYIN QOLGAN TUZILMAGAN GURUHLARNI YANA BIR
        # MARTA _try_minimal_disruption_swap BILAN SINAB KO'RISH ──
        still_unscheduled_for_mds = list(
            CourseGroup.objects.filter(is_scheduled=False)
            .select_related('course', 'teacher').prefetch_related('students')
        )
        for grp in still_unscheduled_for_mds:
            course = grp.course
            if not course:
                continue
            teacher = grp.teacher if grp.teacher_id else None
            mds_ok, mds_msg, _ = _try_minimal_disruption_swap(grp, course, teacher)
            if mds_ok:
                auto_resolve_messages.append(mds_msg)

        # ── YANGI: HAFTALAR IZCHILLIGINI MAJBURIY TA'MINLASH ──
        for grp in CourseGroup.objects.filter(is_scheduled=True).select_related('course').prefetch_related('students'):
            course = grp.course
            if not course or not grp.weekdays or not grp.start_time:
                continue
            wds = tuple(sorted(grp.weekdays))
            target_pair = None
            for (pp1, pp2) in VALID_PARA_PAIRS:
                if PARA_TIMES[pp1][0] == grp.start_time:
                    target_pair = (pp1, pp2)
                    break
            if target_pair is None:
                continue
            p1, p2 = target_pair
            canonical_dates = _slot_occurrence_dates(course.start_date, wds, course.total_lessons)
            if not canonical_dates:
                continue

            existing = list(GroupSchedule.objects.filter(group=grp).order_by('date', 'start_time'))
            expected_times_by_date = {}
            for d in canonical_dates:
                expected_times_by_date.setdefault(d, set()).update({PARA_TIMES[p1][0], PARA_TIMES[p2][0]})

            is_consistent = (
                len(existing) == 2 * len(canonical_dates)
                and all(
                    sc.date in expected_times_by_date and sc.start_time in expected_times_by_date[sc.date]
                    for sc in existing
                )
            )
            if is_consistent:
                continue

            # ── 🛡️ MUHIM TUZATISH: bu blok ilgari HECH QANDAY TEKSHIRUVSIZ
            # guruhning butun jadvalini "kanonik" sana/vaqtlarga qayta yozib
            # qo'yardi — bu boshqa guruhlar bilan (talaba/o'qituvchi/xona
            # bo'yicha) haqiqiy to'qnashuv keltirib chiqarishi mumkin edi,
            # chunki bu yerda busy_index yoki boshqa hech qanday konflikt
            # tekshiruvi ishlatilmagan. Endi qayta yozishdan OLDIN, yangi
            # (kanonik) sana/vaqtlar boshqa allaqachon joylashtirilgan
            # guruhlar bilan to'qnashmasligini tekshiramiz. Agar to'qnashuv
            # aniqlansa — qayta yozish O'TKAZIB YUBORILADI (joriy, nomukammal
            # bo'lsa-da xavfsiz jadval saqlanib qoladi) va admin ogohlantiriladi.
            candidate_slots = [(d, PARA_TIMES[p1][0]) for d in canonical_dates] + \
                              [(d, PARA_TIMES[p2][0]) for d in canonical_dates]
            candidate_dates = {d for d, _ in candidate_slots}
            candidate_set = set(candidate_slots)

            conflict_reason = None

            student_ids = list(grp.students.values_list('id', flat=True))
            if student_ids:
                clash = GroupSchedule.objects.filter(
                    group__is_scheduled=True,
                    group__students__id__in=student_ids,
                    date__in=candidate_dates,
                ).exclude(group=grp).values_list('date', 'start_time').distinct()
                if any((d, t) in candidate_set for d, t in clash):
                    conflict_reason = "talaba(lar) boshqa guruhda shu vaqtda band"

            if conflict_reason is None and grp.teacher_id:
                clash = GroupSchedule.objects.filter(
                    group__is_scheduled=True,
                    group__teacher_id=grp.teacher_id,
                    date__in=candidate_dates,
                ).exclude(group=grp).values_list('date', 'start_time').distinct()
                if any((d, t) in candidate_set for d, t in clash):
                    conflict_reason = "o'qituvchi boshqa guruhda shu vaqtda band"

            if conflict_reason is None and grp.room_id:
                clash = GroupSchedule.objects.filter(
                    group__is_scheduled=True,
                    group__room_id=grp.room_id,
                    date__in=candidate_dates,
                ).exclude(group=grp).values_list('date', 'start_time').distinct()
                if any((d, t) in candidate_set for d, t in clash):
                    conflict_reason = "xona boshqa guruhda shu vaqtda band"

            if conflict_reason is not None:
                messages.warning(
                    request,
                    f"⚠️ '{grp}' guruhining hafta izchilligi tuzatilmadi, chunki "
                    f"bu {conflict_reason} — to'qnashuv oldini olish uchun "
                    f"joriy jadval o'zgartirilmay qoldirildi."
                )
                continue

            GroupSchedule.objects.filter(group=grp).delete()
            GroupSchedule.objects.bulk_create([
                GroupSchedule(group=grp, date=d, start_time=PARA_TIMES[p1][0], lesson_number=2 * i + 1)
                for i, d in enumerate(canonical_dates)
            ] + [
                GroupSchedule(group=grp, date=d, start_time=PARA_TIMES[p2][0], lesson_number=2 * i + 2)
                for i, d in enumerate(canonical_dates)
            ])

        # ── 🚨🚨 YANGI: OXIRGI HIMOYA QATLAMI — SUBYEKTLARARO HAQIQIY
        # TALABA TO'QNASHUVLARINI ANIQLASH VA HAL QILISH ──
        # Sabab: busy_index yuqoridagi tuzatishlar bilan endi to'g'ri
        # yangilanadi, lekin bu — himoya, kafolat emas (masalan boshqa
        # kod yo'li, qo'lda o'zgartirish yoki kelajakdagi resolver buni
        # yana buzishi mumkin). Shuning uchun build_schedule HAR DOIM
        # oxirida, BARCHA fanlar bo'yicha, har bir talabaning HAQIQIY
        # (sana, vaqt) juftliklarini tekshirib, ikki xil guruhga bir
        # vaqtda tushib qolgan hollarni topadi va ADMINGA ko'rsatadi.
        conflict_rows = defaultdict(list)  # (student_id, date, start_time) -> [group, ...]
        gs_qs = (
            GroupSchedule.objects
            .filter(group__is_scheduled=True)
            .select_related('group__course__subject')
            .prefetch_related('group__students')
        )
        for sc in gs_qs:
            for st in sc.group.students.all():
                conflict_rows[(st.id, sc.date, sc.start_time)].append(sc.group)

        evicted_count = 0
        real_conflicts = {
            key: grps for key, grps in conflict_rows.items()
            if len({g.pk for g in grps}) > 1
        }

        if real_conflicts:
            # Har bir talaba uchun, qaysi guruhlar to'qnashayotganini yig'amiz
            by_student = defaultdict(set)
            for (sid, d, t), grps in real_conflicts.items():
                for g in grps:
                    by_student[sid].add((d, t, g.pk, str(g)))

            conflict_lines = []
            for sid, items in by_student.items():
                try:
                    st_obj = Student.objects.get(pk=sid)
                    st_name = str(st_obj)
                except Student.DoesNotExist:
                    st_name = f"ID={sid}"
                groups_str = ", ".join(sorted({f"{g}" for (_, _, _, g) in items}))
                conflict_lines.append(f"{st_name}: {groups_str}")

            messages.error(
                request,
                f"🚨 DIQQAT: {len(by_student)} ta talaba ikki (yoki undan ko'p) "
                f"guruhga BIR XIL kun/vaqtda yozilgan — bu haqiqiy jadval "
                f"to'qnashuvi edi, TIZIM UNI AVTOMATIK BARTARAF ETMOQDA: "
                + " | ".join(conflict_lines[:15])
                + (f" ... va yana {len(conflict_lines) - 15} ta" if len(conflict_lines) > 15 else "")
            )

            # ── 🔁 AVTOMATIK BARTARAF ETISH: faqat aniqlab qo'ymay, haqiqatan
            # ham tuzatamiz. Har bir to'qnashuv klasterida (bir xil sana/vaqtda
            # bir xil talabaga ega guruhlar to'plamida) talabalar soni ENG KAM
            # bo'lgan guruh(lar)ni "bo'shatamiz" (is_scheduled=False qilib,
            # jadvalini o'chiramiz) — bunday guruh odatda boshqa vaqtga
            # ko'chirish uchun ENG QULAY hisoblanadi. Bo'shatilgan guruh
            # keyingi "Jadval tuzish" bosilganda avtomatik qayta joylashtiriladi,
            # shu tariqa to'qnashuv doimiy holatda QOLIB KETMAYDI.
            groups_to_unschedule = {}
            for key, grps in real_conflicts.items():
                unique_groups = list({g.pk: g for g in grps}.values())
                unique_groups.sort(key=lambda g: g.students.count(), reverse=True)
                for loser in unique_groups[1:]:
                    groups_to_unschedule[loser.pk] = loser

            if groups_to_unschedule:
                evicted_count = len(groups_to_unschedule)
                unresolved_names = [str(g) for g in groups_to_unschedule.values()]
                GroupSchedule.objects.filter(group_id__in=groups_to_unschedule.keys()).delete()
                CourseGroup.objects.filter(pk__in=groups_to_unschedule.keys()).update(is_scheduled=False)
                messages.warning(
                    request,
                    f"🔁 To'qnashuvni bartaraf etish uchun {len(groups_to_unschedule)} ta "
                    f"guruh vaqtincha bo'shatildi (qayta joylashtirish navbatiga qo'yildi): "
                    + ", ".join(sorted(unresolved_names)[:15])
                    + (f" ... va yana {len(unresolved_names) - 15} ta" if len(unresolved_names) > 15 else "")
                    + ". Tizim ularni shu so'rov ichida avtomatik qayta joylashtirishga urinmoqda..."
                )

        return evicted_count


    MAX_AUTO_RESOLVE_ATTEMPTS = 8
    for _outer_attempt in range(MAX_AUTO_RESOLVE_ATTEMPTS):
        _evicted_this_pass = _run_scheduling_pass()
        if _evicted_this_pass == 0:
            break

    # ── 🚨 XATOLIKLARNI YIG'ISH (FAQAT OXIRGI NUQTADA SIG'MAY QOLGANLAR UCHUN) ──
    final_unscheduled_groups = list(
        CourseGroup.objects.filter(is_scheduled=False)
        .select_related('course', 'course__subject', 'teacher')
        .prefetch_related('students')
    )

    if final_unscheduled_groups:
        error_details = []
        for grp in final_unscheduled_groups:
            course = grp.course
            teacher = grp.teacher if grp.teacher_id else None

            schedule, found_count, conflicts = _rebuild_schedule(grp, course, teacher)
            no_slot = getattr(find_schedule_for_group, '_last_no_slot_in_week', False)

            other_groups = CourseGroup.objects.filter(
                course=course, is_scheduled=True,
            ).exclude(pk=grp.pk).prefetch_related('students')

            teacher_conflicts_display = []
            seen_teacher_groups = set()
            for c in sorted(conflicts, key=lambda c: (c['date'], c['para_time'][0])):
                if c['type'] != 'teacher':
                    continue
                if c['group'].pk in seen_teacher_groups:
                    continue
                seen_teacher_groups.add(c['group'].pk)
                teacher_conflicts_display.append({
                    'date': c['date'],
                    'start_time': c['para_time'][0],
                    'subject': c['subject'],
                    'group': c['group'],
                })
                if len(teacher_conflicts_display) >= 10:
                    break

            student_groups = defaultdict(list)
            for c in conflicts:
                if c['type'] != 'student':
                    continue
                key = (c['date'], c['para_time'][0], c['group'].pk)
                student_groups[key].append(c)

            student_conflicts_display = []
            sorted_keys = sorted(student_groups.items(), key=lambda kv: (kv[0][0], kv[0][1]))
            for key, items in sorted_keys[:10]:
                first = items[0]
                all_students = []
                for it in items:
                    for st in it['busy_students']:
                        if st not in all_students:
                            all_students.append(st)
                student_conflicts_display.append({
                    'date': first['date'],
                    'start_time': first['para_time'][0],
                    'subject': first['subject'],
                    'group': first['group'],
                    'busy_students': all_students,
                })

            teacher_suggestion = None
            student_move_suggestions = []
            swap_suggestions = []

            blocker_diagnosis = _diagnose_true_blockers(grp, course, teacher)

            error_details.append({
                'group': grp,
                'course': course,
                'other_groups': other_groups,
                'found_count': found_count,
                'missing_count': course.total_lessons - found_count,
                'teacher_conflicts_display': teacher_conflicts_display,
                'student_conflicts_display': student_conflicts_display,
                'teacher_suggestion': teacher_suggestion,
                'student_move_suggestions': student_move_suggestions,
                'swap_suggestions': swap_suggestions,
                'no_teacher': not grp.teacher_id,
                'no_slot': no_slot,
                'blocker_diagnosis': blocker_diagnosis,
            })

        if auto_resolve_messages:
            for msg in auto_resolve_messages:
                messages.info(request, msg)

        real_scheduled_count = CourseGroup.objects.filter(is_scheduled=True).count()
        return render(request, "raspisaniya/build_schedule_errors.html", {
            "error_details": error_details,
            "success_count": real_scheduled_count,
        })

    if auto_resolve_messages:
        for msg in auto_resolve_messages:
            messages.info(request, msg)

    real_scheduled_count = CourseGroup.objects.filter(is_scheduled=True).count()
    messages.success(request, f"Jadval muvaffaqiyatli tuzildi! Jami {real_scheduled_count} ta guruh tuzilgan.")
    return redirect("lesson_list")


@login_required
def apply_expand_weekdays_suggestion(request, group_pk):
    """
    YANGI: Admin uchun QO'LDA tugma — 16-paralik (12-20 dars) guruh uchun
    odatiy Seshanba/Payshanba o'rniga Dushanba/Chorshanba/Juma kunlarini
    ham (yoki ular bilan aralash) sinab ko'rishni MAJBURAN ishga tushiradi.

    Bu — `_try_last_resort_expand_weekdays` funksiyasining aynan o'zi,
    build_schedule jarayonida AVTOMATIK oxirgi chora sifatida ham
    ishlatiladi. Bu tugma esa — admin buni ANIQ, bitta tanlangan guruh
    uchun, ko'rib turib, qo'lda ishga tushirishga imkon beradi (masalan
    avtomatik jarayon hali yetib bormagan yoki eski kod bilan ishlagan
    holatlarda).
    """
    if request.method != "POST":
        return redirect('build_schedule')

    grp = get_object_or_404(CourseGroup, pk=group_pk)
    course = grp.course
    teacher = grp.teacher if grp.teacher_id else None

    if not course or not (12 <= course.total_lessons <= 20):
        messages.error(
            request,
            f"'{grp}' — bu funksiya faqat 16-paralik (12-20 dars) kurslar uchun ishlaydi."
        )
        return redirect('build_schedule')

    ok, msg = _try_last_resort_expand_weekdays(grp, course, teacher)
    if ok:
        messages.success(request, f"✅ {msg}")
    else:
        messages.error(
            request,
            f"❌ '{grp}' uchun Dush/Chor/Juma kunlarida ham hech qanday bo'sh vaqt topilmadi "
            f"(yoki hali navbatda kutayotgan 24-paralik kurslar bor)."
        )
    return redirect('build_schedule')


def apply_teacher_suggestion(request, group_pk, teacher_pk):
    """Taklif: guruhga boshqa o'qituvchini biriktirish."""
    if request.method == "POST":
        grp = get_object_or_404(CourseGroup, pk=group_pk)
        teacher = get_object_or_404(Teacher, pk=teacher_pk)

        # ── YANGI TEKSHIRUV: agar guruh allaqachon jadvallangan bo'lsa
        # (masalan mavjud guruhga o'qituvchi almashtirilayotgan bo'lsa),
        # yangi o'qituvchining boshqa guruhlardagi vaqtlari bilan
        # to'qnashmasligini tekshiramiz ──
        conflict = get_teacher_group_conflict(teacher, grp)
        if conflict:
            conflict_date, conflict_time = conflict
            messages.error(
                request,
                f"❌ {teacher} {conflict_date.strftime('%d.%m.%Y')} kuni "
                f"{conflict_time.strftime('%H:%M')} da band — biriktirilmadi."
            )
            return redirect('build_schedule')

        grp.teacher = teacher
        grp.save()
        messages.success(
            request,
            f"'{grp.course.subject}' {grp.group_number}-guruh uchun o'qituvchi "
            f"{teacher} ga almashtirildi. Jadval qayta tuzilmoqda..."
        )
    return redirect('build_schedule')


@login_required
def apply_swap_suggestion(request):
    """Taklif: boshqa guruhning bir kunlik darsini boshqa vaqtga ko'chirish."""
    if request.method == "POST":
        group_pk = request.POST.get("group_pk")
        date_str = request.POST.get("date")
        old_time_str = request.POST.get("old_time")
        new_time_str = request.POST.get("new_time")

        grp = get_object_or_404(CourseGroup, pk=group_pk)
        d = parse_date(date_str)
        oh, om = map(int, old_time_str.split(":"))
        nh, nm = map(int, new_time_str.split(":"))
        old_t = dtime(oh, om)
        new_t = dtime(nh, nm)

        sched = GroupSchedule.objects.filter(group=grp, date=d, start_time=old_t).first()
        if sched:
            # ── YANGI TEKSHIRUV: yangi vaqtda (d, new_t) o'qituvchi yoki
            # talabalar boshqa darsga band emasligini tekshiramiz ──
            teacher_id = grp.teacher_id
            student_ids = list(grp.students.values_list('id', flat=True))

            if teacher_id and GroupSchedule.objects.filter(
                date=d, start_time=new_t, group__teacher_id=teacher_id,
            ).exclude(pk=sched.pk).exists():
                messages.error(
                    request,
                    f"❌ O'qituvchi {grp.teacher} {d.strftime('%d.%m.%Y')} kuni {new_time_str} da band — ko'chirilmadi."
                )
                return redirect('build_schedule')

            if student_ids and GroupSchedule.objects.filter(
                date=d, start_time=new_t, group__students__id__in=student_ids,
            ).exclude(pk=sched.pk).exists():
                messages.error(
                    request,
                    f"❌ Ba'zi talabalar {d.strftime('%d.%m.%Y')} kuni {new_time_str} da band — ko'chirilmadi."
                )
                return redirect('build_schedule')

            sched.start_time = new_t
            sched.save(update_fields=['start_time'])
            messages.success(
                request,
                f"'{grp.course.subject}' {grp.group_number}-guruhning {d.strftime('%d.%m.%Y')} "
                f"kungi darsi {old_time_str} dan {new_time_str} ga ko'chirildi. "
                f"Jadval qayta tuzilmoqda..."
            )
        else:
            messages.error(request, "Dars topilmadi — balki allaqachon o'zgargan. Qayta urinib ko'ring.")
    return redirect('build_schedule')


@login_required
def apply_student_swap_suggestion(request, group_pk):
    """
    Guruh jadvalini to'sib qo'ygan muammoli talabani aniqlash va
    parallel guruhdan zararsiz talabaga AVTOMATIK almashtirish.
    Tasdiqlash sahifasi yo'q — darhol bajariladi.
    """
    grp_a = get_object_or_404(CourseGroup, pk=group_pk)
    start = grp_a.course.start_date
    end   = grp_a.course.end_date

    # 1. O'qituvchining bo'sh slotlari
    teacher_free_slots = set()
    cur = start
    while cur <= end:
        if cur.weekday() <= 4:
            teacher_busy = set()
            for sc in GroupSchedule.objects.filter(date=cur, group__teacher=grp_a.teacher):
                st = sc.start_time or sc.group.start_time
                if st:
                    for i, (ps, _) in enumerate(PARA_TIMES):
                        if ps == st:
                            teacher_busy.add(i)
            for i in range(len(PARA_TIMES)):
                if i not in teacher_busy:
                    teacher_free_slots.add((cur, i))
        cur += timedelta(days=1)

    if not teacher_free_slots:
        messages.error(request,
            f"O'qituvchi {grp_a.teacher} da umuman bo'sh vaqt yo'q!")
        return redirect('build_schedule')

    # 2. Har bir talabaning nechta slotni to'sayotganini hisoblash
    students_a    = list(grp_a.students.all())
    student_a_ids = set(s.id for s in students_a)
    block_counts  = defaultdict(int)

    for sc in GroupSchedule.objects.filter(
        date__range=(start, end),
        group__students__id__in=student_a_ids,
    ).prefetch_related('group__students'):
        st = sc.start_time or sc.group.start_time
        if st:
            for i, (ps, _) in enumerate(PARA_TIMES):
                if ps == st and (sc.date, i) in teacher_free_slots:
                    for s in sc.group.students.all():
                        if s.id in student_a_ids:
                            block_counts[s.id] += 1

    if not block_counts:
        messages.warning(request,
            "Bu guruh talabalarida konflikt aniqlanmadi.")
        return redirect('build_schedule')

    # Eng ko'p to'sayotgan talaba
    bad_id      = max(block_counts, key=block_counts.get)
    bad_student = Student.objects.get(id=bad_id)

    # 3. Parallel guruhlardan zararsiz talaba qidirish
    parallel_groups = CourseGroup.objects.filter(
        course__subject=grp_a.course.subject
    ).exclude(pk=grp_a.pk).prefetch_related('students')

    safe_candidate = None
    grp_b          = None

    # MUHIM: bad_student ning O'ZI ham yangi guruhga (p_grp) mos kelishi kerak
    bad_student_full_busy = set(
        GroupSchedule.objects.filter(group__students=bad_student)
        .exclude(group=grp_a)
        .values_list('date', 'start_time')
    )

    for p_grp in parallel_groups:
        p_grp_times = set(
            GroupSchedule.objects.filter(group=p_grp).values_list('date', 'start_time')
        )
        if bad_student_full_busy & p_grp_times:
            continue

        for candidate in p_grp.students.all():
            if candidate.id in student_a_ids:
                continue

            # Nomzodning band slotlari
            cand_busy = set()
            for sc in GroupSchedule.objects.filter(
                group__students=candidate,
                date__range=(start, end)
            ):
                st = sc.start_time or sc.group.start_time
                if st:
                    for i, (ps, _) in enumerate(PARA_TIMES):
                        if ps == st:
                            cand_busy.add((sc.date, i))

            # O'qituvchi bo'sh slotlarining HECH BIRIDA band bo'lmasligi kerak
            if not (teacher_free_slots & cand_busy):
                safe_candidate = candidate
                grp_b          = p_grp
                break
        if safe_candidate:
            break

    # 4. Avtomatik almashtirish — tasdiqlashsiz
    if safe_candidate and grp_b:
        with transaction.atomic():
            grp_a.students.remove(bad_student)
            grp_b.students.add(bad_student)
            grp_b.students.remove(safe_candidate)
            grp_a.students.add(safe_candidate)
            sync_group_language(grp_a)
            sync_group_language(grp_b)

        messages.success(request,
            f"✅ Avtomatik almashtirish bajarildi: "
            f"{bad_student.first_name} → {grp_b.group_number}-guruhga, "
            f"{safe_candidate.first_name} → {grp_a.group_number}-guruhga ko'chirildi. "
            f"Jadval qayta tuzilmoqda..."
        )
    else:
        messages.error(request,
            f"Parallel guruhlarda o'qituvchi {grp_a.teacher} vaqtiga "
            f"mos keladigan zararsiz talaba topilmadi. "
            f"Muddatni uzaytirishni yoki boshqa o'qituvchi tanlashni tavsiya etamiz."
        )

    return redirect('build_schedule')



@login_required
def assign_teachers_auto(request):
    """
    TIZIMDAGI BARCHA kurslarning o'qituvchisi yo'q guruhlariga konfliktlarsiz avtomatik o'qituvchi taqsimlash.
    """
    if request.method != "POST":
        return redirect('lesson_list')

    courses = Course.objects.filter(groups__teacher__isnull=True).distinct().select_related('subject')

    if not courses.exists():
        messages.info(request, "Tizimda o'qituvchi biriktirilmagan guruhlar topilmadi.")
        return redirect('lesson_list')

    total_assigned_count = 0
    all_failed_details = []

    for course in courses:
        groups = list(
            course.groups.filter(teacher__isnull=True)
            .prefetch_related('students', 'schedule')
        )
        candidates = list(Teacher.objects.filter(subjects=course.subject).order_by('pk'))

        if not candidates:
            for grp in groups:
                all_failed_details.append(f"{course.subject.name} ({grp.group_number}-guruh): O'qituvchi umuman yo'q")
            continue

        start = course.start_date
        end = course.end_date

        def get_teacher_free_slots_count(teacher):
            busy_count = GroupSchedule.objects.filter(
                group__teacher=teacher,
                date__gte=start,
                date__lte=end,
            ).count()
            work_days = sum(
                1 for i in range((end - start).days + 1)
                if (start + timedelta(days=i)).weekday() <= 4
            )
            return work_days * 6 - busy_count

        # Har bir guruh uchun o'qituvchi saralash
        for grp in groups:
            # MUHIM: Guruh allaqachon "Jadval tuzish" bosqichida aniq (sana, vaqt)
            # larga joylashtirilgan bo'ladi. Endi haftaning taxminiy kunlarini
            # (check_wds) TAXMIN QILISH o'rniga, guruhning HAQIQIY jadvalidan
            # foydalanamiz — bu ustozlarni bekorga rad etib, "bitta guruhdan keyin
            # to'xtab qolish" muammosini bartaraf etadi.
            grp_slots = list(grp.schedule.values_list('date', 'start_time'))

            if not grp_slots:
                all_failed_details.append(
                    f"{course.subject.name} ({grp.group_number}-guruh): "
                    f"guruh hali jadvallanmagan (avval 'Jadval tuzish'ni bajaring)"
                )
                continue

            best_teacher = None
            max_free = -1

            for teacher in candidates:
                free = get_teacher_free_slots_count(teacher)

                # 1. Yuklama yetarliligini tekshirish
                if free < course.total_lessons:
                    continue

                # 2. ANIQ TO'QNASHUV TEKSHIRUVI: ustoz aynan shu guruhning
                #    HAQIQIY (sana, vaqt) laridan birortasida allaqachon BOSHQA
                #    guruhga band bo'lsa — bu ustozni rad etamiz. Guruhning o'zi
                #    boshqa vaqt/kunda bo'lsa, ustoz erkin hisoblanadi.
                teacher_busy_slots = set(
                    GroupSchedule.objects.filter(
                        group__teacher=teacher,
                        date__gte=start,
                        date__lte=end,
                    ).exclude(group=grp).values_list('date', 'start_time')
                )
                conflict = any(slot in teacher_busy_slots for slot in grp_slots)
                if conflict:
                    continue

                # Agar barcha tekshiruvlardan o'tsa va eng optimali bo'lsa tanlaymiz
                if free > max_free:
                    max_free = free
                    best_teacher = teacher

            # O'qituvchini saqlash
            if best_teacher:
                grp.teacher = best_teacher
                grp.save(update_fields=['teacher'])
                total_assigned_count += 1
            else:
                all_failed_details.append(
                    f"{course.subject.name} ({grp.group_number}-guruh): Mos keladigan konfliktlarsiz o'qituvchi topilmadi")

    if total_assigned_count > 0:
        messages.success(request,
                         f"✅ Jami {total_assigned_count} ta guruhga o'qituvchilar konfliktlarsiz muvaffaqiyatli biriktirildi!")

    if all_failed_details:
        for fail_msg in all_failed_details:
            messages.error(request, f"❌ Joy ajratilmadi: {fail_msg}")
        messages.warning(request,
                         "💡 Ayrim guruhlarga vaqt to'g'ri kelmagani (conflict bergani) sababli o'qituvchi biriktirilmadi. Ularni qo'lda ko'rib chiqishingiz mumkin.")

    return redirect('lesson_list')


@login_required
def teacher_capacity_check(request):
    """
    O'qituvchilar uchun matematik imkoniyat tekshiruvi.
    Har bir o'qituvchi uchun: mavjud bo'sh paralar vs kerak bo'lgan paralar.
    """
    from django.db.models import Count, Sum

    # Jadval tuzilmagan guruhlar
    unscheduled = CourseGroup.objects.filter(
        is_scheduled=False
    ).select_related('course__subject', 'teacher', 'course').prefetch_related('students')

    # O'qituvchi bo'yicha guruhlash
    teacher_data = defaultdict(lambda: {
        'teacher': None,
        'groups': [],
        'total_needed': 0,
    })

    for grp in unscheduled:
        tid = grp.teacher_id
        teacher_data[tid]['teacher'] = grp.teacher
        teacher_data[tid]['groups'].append(grp)
        teacher_data[tid]['total_needed'] += grp.course.total_lessons

    results = []

    for tid, tdata in teacher_data.items():
        teacher = tdata['teacher']
        groups  = tdata['groups']

        # Muddatni aniqlash (eng keng muddat)
        start = min(g.course.start_date for g in groups)
        end   = max(g.course.end_date   for g in groups)

        # Ish kunlari soni
        work_days = sum(
            1 for i in range((end - start).days + 1)
            if (start + timedelta(days=i)).weekday() <= 4  # Du-Ju
        )

        # Mavjud jadvaldagi band paralar (shu muddat ichida)
        already_scheduled = GroupSchedule.objects.filter(
            group__teacher=teacher,
            date__gte=start,
            date__lte=end,
        ).count()

        # Jami mavjud joy
        total_slots = work_days * 6  # kuniga max 6 para

        # Bo'sh joy
        free_slots = total_slots - already_scheduled

        # Kerak
        needed = tdata['total_needed']

        # Imkoniyat
        possible   = free_slots >= needed
        shortage   = max(0, needed - free_slots)
        extra_days = math.ceil(shortage / 6) if shortage > 0 else 0

        # Kunlik o'rtacha yuklanma (yangi guruhlar bilan)
        avg_per_day = round((already_scheduled + needed) / max(work_days, 1), 1)

        results.append({
            'teacher':            teacher,
            'groups':             groups,
            'start':              start,
            'end':                end,
            'work_days':          work_days,
            'total_slots':        total_slots,
            'already_scheduled':  already_scheduled,
            'free_slots':         free_slots,
            'needed':             needed,
            'possible':           possible,
            'shortage':           shortage,
            'extra_days':         extra_days,
            'avg_per_day':        avg_per_day,
        })

    # Imkonsizlarni avval ko'rsatish
    results.sort(key=lambda x: (x['possible'], -x['shortage']))

    return render(request, 'raspisaniya/teacher_capacity_check.html', {
        'results': results,
        'total_impossible': sum(1 for r in results if not r['possible']),
        'total_possible':   sum(1 for r in results if r['possible']),
    })


@login_required
def group_schedule_debug(request, group_pk):
    grp = get_object_or_404(CourseGroup, pk=group_pk)
    course = grp.course

    import itertools
    start_date = course.start_date
    end_date = course.end_date
    total_lessons = course.total_lessons

    max_wd = 4
    available_wds = list(range(0, max_wd + 1))

    # ── MANTIQLARNI BU YERDA TO'LIQ ANIQHLAYMIZ ──
    if total_lessons >= 20:
        needed_wds = [0, 2, 4]
        candidate_wd_sets = [tuple(needed_wds)]
        days_needed = 3  # <--- Buni belgilash shart
    elif 12 <= total_lessons < 20:
        needed_wds = [1, 3]
        # YANGI: faqat kanonik Seshanba/Payshanba emas, BARCHA 2 kunlik
        # kombinatsiyalarni ham ko'rsatamiz (kanonik birinchi, keyin
        # qolganlari) — bu asosiy scheduler'dagi "eng oxirgi chora"
        # (`_try_last_resort_expand_weekdays`) mantig'iga mos keladi.
        canonical = tuple(needed_wds)
        all_pairs = list(itertools.combinations(available_wds, 2))
        candidate_wd_sets = [canonical] + [p for p in all_pairs if p != canonical]
        days_needed = 2  # <--- Buni belgilash shart
    else:
        # 8 para: FAQAT bitta kun/hafta (asosiy find_schedule_for_group bilan bir
        # xil mantiq) — guruh raqamiga qarab boshlang'ich kun aylantiriladi,
        # shunda barcha guruhlar bir xil kunga to'planib qolmaydi.
        start_offset = (grp.group_number - 1) % len(available_wds)
        rotated_wds = available_wds[start_offset:] + available_wds[:start_offset]
        candidate_wd_sets = [(wd,) for wd in rotated_wds]
        days_needed = 1  # <--- Buni belgilash shart
    # ─────────────────────────────────────────────

    week_monday = start_date - timedelta(days=start_date.weekday())

    teacher_id = grp.teacher_id
    student_ids = list(grp.students.values_list('id', flat=True))
    student_id_set = set(student_ids)

    # ── Grid (Diagnostika) qismi avvalgidek qoladi ──
    grid = []
    for wd in available_wds:
        d = week_monday + timedelta(days=wd)
        in_range = start_date <= d <= end_date
        blocks = []
        for (p1, p2) in VALID_PARA_PAIRS:
            reasons = []
            if in_range:
                for pi in (p1, p2):
                    if teacher_id:
                        for sc in GroupSchedule.objects.filter(
                                date=d, start_time=PARA_TIMES[pi][0], group__teacher_id=teacher_id,
                        ).exclude(group=grp).select_related('group__course__subject'):
                            reasons.append(
                                f"👨‍🏫 Ustoz band — {sc.group.course.subject} ({sc.group.group_number}-guruh), {PARA_TIMES[pi][0].strftime('%H:%M')}"
                            )
                    if student_ids:
                        for sc in GroupSchedule.objects.filter(
                                date=d, start_time=PARA_TIMES[pi][0],
                                group__students__id__in=student_ids,
                        ).exclude(group=grp).select_related('group__course__subject') \
                                .prefetch_related('group__students').distinct():
                            busy_names = [str(s) for s in sc.group.students.all() if s.id in student_id_set]
                            if busy_names:
                                reasons.append(
                                    f"🎓 Talaba(lar) band: {', '.join(busy_names)} — "
                                    f"{sc.group.course.subject} ({sc.group.group_number}-guruh), "
                                    f"{PARA_TIMES[pi][0].strftime('%H:%M')}"
                                )
            else:
                reasons.append("Kurs muddatidan tashqarida")

            blocks.append({
                'label': f"{PARA_TIMES[p1][0].strftime('%H:%M')}–{PARA_TIMES[p2][1].strftime('%H:%M')}",
                'free': in_range and not reasons,
                'reasons': reasons,
            })
        grid.append({
            'wd': wd, 'wd_name': WEEKDAY_NAMES[wd], 'date': d,
            'in_range': in_range, 'blocks': blocks,
        })

    # ── Qaysi kunlar kombinatsiyasi ishlaydi/ishlamaydi ──
    combo_results = []
    winning_combo = None
    for combo in candidate_wd_sets:
        detail = []
        ok_days = 0
        for wd in combo:
            row = grid[wd]
            # row['blocks'] ichidagi 'free' ni tekshiramiz
            any_free = row['in_range'] and any(b['free'] for b in row['blocks'])
            if any_free:
                ok_days += 1
            detail.append({'wd': wd, 'wd_name': WEEKDAY_NAMES[wd], 'ok': any_free})

        success = ok_days >= days_needed
        combo_results.append({
            'combo_names': [WEEKDAY_NAMES[w] for w in combo],
            'success': success,
            'detail': detail,
        })
        if success and winning_combo is None:
            winning_combo = combo_results[-1]['combo_names']

    context = {
        'grp': grp, 'course': course, 'days_needed': days_needed,
        'week_monday': week_monday, 'grid': grid,
        'combo_results': combo_results, 'winning_combo': winning_combo,
    }
    return render(request, 'raspisaniya/group_schedule_debug.html', context)


@login_required
def teacher_assignment_status(request, course_pk):
    """
    Kurs uchun o'qituvchi taqsimlash holati — JSON.
    Har bir guruh uchun: o'qituvchi biriktirilganmi, kim biriktirilgan.
    """
    course  = get_object_or_404(Course, pk=course_pk)
    groups  = course.groups.select_related('teacher').prefetch_related('students')
    result  = []

    for grp in groups:
        result.append({
            'group_number': grp.group_number,
            'student_count': grp.students.count(),
            'teacher': grp.teacher.first_name if grp.teacher else None,
            'is_scheduled': grp.is_scheduled,
        })

    # Qancha o'qituvchi kerak
    candidates = Teacher.objects.filter(subjects=course.subject).count()
    unassigned = sum(1 for r in result if not r['teacher'])

    return JsonResponse({
        'groups':             result,
        'total_groups':       len(result),
        'unassigned_count':   unassigned,
        'available_teachers': candidates,
        'needs_more':         max(0, unassigned - candidates),
    })



HEADER_FONT = Font(name="Arial", size=10, bold=True, color="FFFFFF")
HEADER_FILL = PatternFill(start_color="1A237E", end_color="1A237E", fill_type="solid")
CENTER_ALIGN = Alignment(horizontal="center", vertical="center")
LEFT_ALIGN = Alignment(horizontal="left", vertical="center")

@login_required
def apply_minimal_disruption_swap(request, group_pk):
    """
    Diagnostika ('_diagnose_true_blockers') ko'rsatgan almashtirishlarni
    HAQIQATDA bajaradigan tugma — '_try_minimal_disruption_swap' orqali.
    """
    if request.method != "POST":
        return redirect('build_schedule')

    grp = get_object_or_404(CourseGroup, pk=group_pk)
    course = grp.course
    teacher = grp.teacher if grp.teacher_id else None

    if not course:
        messages.error(request, f"'{grp}' uchun kurs topilmadi.")
        return redirect('build_schedule')

    ok, msg, _ = _try_minimal_disruption_swap(grp, course, teacher)
    if ok:
        messages.success(request, f"✅ {msg}")
    else:
        messages.error(
            request,
            f"❌ '{grp}' uchun avtomatik almashtirish endi ishlamadi "
            f"(holat o'zgargan bo'lishi mumkin — sahifani yangilab qayta urinib ko'ring)."
        )
    return redirect('build_schedule')