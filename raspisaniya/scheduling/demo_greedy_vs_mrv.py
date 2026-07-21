"""
"104 -> 90" muammosining kichraytirilgan, aniq isboti.

Ssenariy: 5 ta guruh, 5 ta slot.
  - 4 ta guruh "keng imkoniyatli" (masalan katta o'zbek-tilli guruhlar) —
    istalgan slotga sig'adi.
  - 1 ta guruh (id=4, masalan kam sonli rus-tilli guruh) FAQAT bitta
    slotga (0-slot) sig'adi — lekin YARATILISH RO'YXATIDA OXIRIDA turibdi.

ESKI (greedy, yaratilish tartibida): guruh 0,1,2,3 navbat bilan "birinchi
bo'sh" slotni oladi -> 0,1,2,3 slotlarini egallab qo'yadi. Guruh 4 keladi,
unga kerakli yagona slot (0) allaqachon band -> RAD ETILADI.
Natija: 4/5 guruh joylashadi, 1 tasi "joy yo'q" bo'lib qoladi.

YANGI (MRV allocator): avval ENG KAM variantli guruh (id=4, atigi 1 ta
variant) joylashtiriladi -> slot 0 ni oladi. Keyin qolgan 4 ta keng
imkoniyatli guruh, hali BO'SH bo'lgan 1,2,3,4-slotlarga muammosiz
joylashadi.
Natija: 5/5 guruh joylashadi.

Ishga tushirish: `python3 demo_greedy_vs_mrv.py`
"""
from allocator import MRVAllocator, Candidate

groups = {
    0: [0, 1, 2, 3, 4],
    1: [0, 1, 2, 3, 4],
    2: [0, 1, 2, 3, 4],
    3: [0, 1, 2, 3, 4],
    4: [0],  # eng "qiyin" guruh, lekin ro'yxatda OXIRIDA
}


def run_greedy(order):
    taken, assigned, unresolved = set(), {}, []
    for gid in order:
        choice = next((s for s in groups[gid] if s not in taken), None)
        if choice is None:
            unresolved.append(gid)
        else:
            taken.add(choice)
            assigned[gid] = choice
    return assigned, unresolved


def run_mrv():
    def provider(task, already_assigned):
        taken = set(already_assigned.values())
        return [Candidate(slot_key=s, score=0) for s in groups[task.group_id] if s not in taken]
    return MRVAllocator(provider).allocate(list(groups.keys()))


if __name__ == "__main__":
    order = [0, 1, 2, 3, 4]  # yaratilish tartibi
    ga, gu = run_greedy(order)
    ma, mu = run_mrv()

    print("ESKI greedy (yaratilish tartibida):", f"{len(ga)}/5 joylashdi.")
    print("  Natija:", ga, " Joy topilmadi:", gu)
    print()
    print("YANGI MRV allocator:              ", f"{len(ma)}/5 joylashdi.")
    print("  Natija:", ma, " Joy topilmadi:", mu)
