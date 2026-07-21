"""
Allocator — muammo #2 (Greedy algoritm) uchun yechim, loyihadagi ENG
KATTA muammo sifatida belgilangan.

ESKI ALGORITM:
    1-guruh -> eng yaxshi joyni oladi -> 2-guruh -> eng yaxshi joyni
    oladi -> ... -> oxirgi guruhlar uchun joy qolmaydi.

    Bu klassik "greedy ochko'zlik" muammosi: guruhlar RO'YXATDAGI TARTIBDA
    (odatda yaratilish tartibida) qayta ishlanadi, va birinchi guruh eng
    qulay slotni "tortib olib qo'yadi", garchi u boshqa slotlarda ham
    yaxshi joylasha olsa-da. Kamroq muqobili bo'lgan (masalan faqat 1-2 ta
    bo'sh kuni qolgan kichik til guruhi) oxirida qoladi va hech qanday joy
    topolmay qoladi — shundan "104 -> 90" holati kelib chiqadi (104 ta
    guruhdan atigi 90 tasi muvaffaqiyatli joylashtiriladi).

YANGI ALGORITM — MRV (Minimum Remaining Values), CSP nazariyasidan:
    Guruhlar YARATILISH TARTIBIDA emas, balki ENG KAM MUQOBIL VARIANTGA EGA
    bo'lgan guruhdan boshlab qayta ishlanadi. Sabab: agar guruh A uchun 8 ta
    mumkin bo'lgan slot bor-u, guruh B uchun faqat 1 ta bor bo'lsa —
    avval B ni joylashtirish kerak, chunki A istalgan boshqa vaqtga ham
    ulgurishi mumkin, B esa yo'q. Bu klassik constraint-satisfaction
    evristikasi bo'lib, "eng qiyin talabgorni birinchi hal qilish"
    tamoyiliga asoslanadi va greedy-ochko'zlikdan sezilarli farq qiladi:
    endi birinchi bo'lib yaratilgan guruh emas, ENG NOZIK guruh ustuvorlik
    oladi.

    Bundan tashqari, bir xil miqdordagi variant bo'lsa, "least constraining
    value" evristikasi qo'llaniladi: shu slotni tanlash boshqa hali
    joylashtirilmagan guruhlarning imkoniyatlarini eng kam qisqartiradigan
    variant tanlanadi (subject_load orqali taxminiy baholanadi).

NATIJA: hamma guruh muvaffaqiyatsizlikka bir xil tarzda emas, balki eng
"qiyin" guruhlar birinchi hal qilingani uchun, umumiy joylashtirilgan
guruhlar SONI ko'proq bo'ladi (104/104ga yaqinlashadi, 104/90 emas).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class Candidate:
    """Bitta guruh uchun bitta imkoniyat: qaysi (hafta_kunlari, para_blok)."""
    slot_key: tuple           # (weekday_set, para_block) — identifikatsiya uchun
    score: float              # past = yaxshiroq (masalan subject_load)


@dataclass
class GroupTask:
    """Joylashtirilishi kerak bo'lgan bitta guruh (yoki guruh-nomzod)."""
    group_id: object
    candidates: list = field(default_factory=list)  # list[Candidate]
    assigned: Optional[tuple] = None

    @property
    def remaining_values(self) -> int:
        return len(self.candidates)


class MRVAllocator:
    """
    Bir nechta guruhni, bir-birining imkoniyatlariga ta'sir qiladigan
    umumiy resurs (para slotlari) uchun MRV evristikasi bilan taqsimlaydi.

    `candidate_provider(task, already_assigned) -> list[Candidate]` —
    chaqiruvchi tomon (Scheduler) beradi: har bir guruh uchun, HOZIRGI
    holatda (boshqa guruhlar allaqachon nima olganini hisobga olib) qanday
    variantlar qolganini qaytaradi. Bu allocatorni domendan (Django
    modellaridan) mustaqil qiladi — u faqat abstrakt "necha variant qoldi"
    bilan ishlaydi.
    """

    def __init__(self, candidate_provider: Callable[[GroupTask, dict], list]):
        self._provider = candidate_provider

    def allocate(self, group_ids: list) -> tuple[dict, list]:
        """
        Qaytaradi: (assigned: {group_id: slot_key}, unresolved: [group_id]).

        `unresolved` — muammo #2 dagi "oxirgi guruhlar uchun joy qolmaydi"
        holatiga tushib qolgan guruhlar. ESKI koddan farqli o'laroq bu
        ro'yxat ANIQ va oldindan ma'lum bo'ladi (shovqinsiz yo'qolib
        ketmaydi) — Scheduler shu ro'yxatni keyingi bosqichga (masalan
        conflict-resolution / swap algoritmlariga) uzatadi.
        """
        pending = {gid: GroupTask(group_id=gid) for gid in group_ids}
        assigned: dict = {}
        unresolved: list = []

        while pending:
            # Har bir kutayotgan guruh uchun HOZIRGI holatga mos variantlarni
            # qayta hisoblaymiz (chunki oldingi tur assigned to'plamini
            # o'zgartirgan bo'lishi mumkin — subject_load, band vaqtlar va h.k.)
            for task in pending.values():
                task.candidates = self._provider(task, assigned)

            # MRV: eng kam variantli guruhni tanlaymiz.
            next_gid = min(pending, key=lambda gid: pending[gid].remaining_values)
            task = pending.pop(next_gid)

            if not task.candidates:
                unresolved.append(next_gid)
                continue

            # Least-constraining-value: eng past score (masalan eng kam
            # band bo'lgan / eng "bo'sh" slot) tanlanadi.
            best = min(task.candidates, key=lambda c: c.score)
            assigned[next_gid] = best.slot_key

        return assigned, unresolved
