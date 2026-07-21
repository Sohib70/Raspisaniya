"""
ConflictChecker — muammo #1 (find_schedule_for_group juda ko'p vazifani
bajarishi) va #11 (teacher/student conflict tekshiruvi 4 xil joyda
qayta-qayta yozilgani) uchun yechim.

ESKI: "teacher conflict" tekshiruvi kamida quyidagi funksiyalarda,
har birida sal boshqacharoq yozilgan holda takrorlangan edi:
    - find_schedule_for_group() ichidagi get_hard_busy()
    - get_teacher_group_conflict()
    - _auto_resolve_via_cross_subject_swap()
    - _auto_resolve_via_parallel_swap()
    - _brute_force_find_slot()

YANGI: bitta ConflictChecker klassi, BusyIndex ustiga qurilgan. Barcha
yuqoridagi joylar endi shu klassning metodlarini chaqiradi. Natijada:
  - Bitta joyda tuzatilgan xato — hammasida tuzalgan bo'ladi.
  - Test yozish oson: ConflictChecker ni alohida sinab ko'rish mumkin.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from .busy_index import BusyIndex


@dataclass(frozen=True)
class ConflictReport:
    ok: bool
    teacher_conflict: bool = False
    student_conflicts: tuple = ()   # band bo'lgan (student_id, group) juftliklari
    room_conflict: bool = False
    subject_load: int = 0           # shu parada bitta fanning nechta guruhi bor


class ConflictChecker:
    """Guruh/o'qituvchi/xona uchun (sana, para) slotini baholaydi."""

    def __init__(self, busy_index: BusyIndex):
        self.busy = busy_index

    def check(
        self,
        *,
        date,
        para_idx: int,
        teacher_id: Optional[int] = None,
        student_ids: Iterable[int] = (),
        subject_id: Optional[int] = None,
        room_busy_lookup=None,  # callable(room_id, date, para_idx) -> bool, ixtiyoriy
        room_id: Optional[int] = None,
    ) -> ConflictReport:
        teacher_conflict = not self.busy.teacher_free(teacher_id, date, para_idx)
        busy_students = tuple(self.busy.busy_students_in(student_ids, date, para_idx))
        room_conflict = False
        if room_id is not None and room_busy_lookup is not None:
            room_conflict = bool(room_busy_lookup(room_id, date, para_idx))

        subject_load = (
            self.busy.subject_occupancy(subject_id, date, para_idx)
            if subject_id is not None else 0
        )

        ok = not teacher_conflict and not busy_students and not room_conflict
        return ConflictReport(
            ok=ok,
            teacher_conflict=teacher_conflict,
            student_conflicts=busy_students,
            room_conflict=room_conflict,
            subject_load=subject_load,
        )

    def pair_ok(self, *, date, para1, para2, **kwargs) -> bool:
        """Ikkita ketma-ket para (masalan 1-2 blok) uchun ikkalasi ham bo'sh bo'lishi kerak."""
        return (
            self.check(date=date, para_idx=para1, **kwargs).ok
            and self.check(date=date, para_idx=para2, **kwargs).ok
        )
