# 📅 Raspisaniya — Akademik Qarzdorlik Dars Jadvali Tizimi

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-4.x-green?logo=django&logoColor=white)
![SQLite](https://img.shields.io/badge/Database-SQLite-lightgrey?logo=sqlite)
![License](https://img.shields.io/badge/License-MIT-yellow)
![Status](https://img.shields.io/badge/Status-Active-brightgreen)

**Django asosida qurilgan to'liq funksional dars jadvali boshqaruv tizimi.**
Akademik qarzdor talabalar uchun guruhlarni avtomatik shakllantirish,
o'qituvchi va xona biriktirib, jadval tuzadi.

[🚀 O'rnatish](#️-ornatish) · [📖 Foydalanish](#-foydalanish) · [🔌 API](#-api-endpointlar) · [🤝 Hissa qo'shish](#-hissa-qoshish)

</div>

---

## 📸 Ekran tasvirlari

> **Eslatma:** Quyidagi bo'limlar ilova ishga tushirilgandan so'ng to'ldiriladi.

| Sahifa | Tasvir |
|--------|--------|
| 🏠 Bosh sahifa — Darslar ro'yxati | `[ screenshot: lesson_list ]` |
| 📆 Haftalik jadval | `[ screenshot: weekly_schedule ]` |
| ➕ Dars yaratish (3 bosqich) | `[ screenshot: lesson_create_step2 ]` |
| 👨‍🎓 Talaba paneli | `[ screenshot: student_dashboard ]` |
| 👨‍🏫 O'qituvchi paneli | `[ screenshot: teacher_dashboard ]` |
| 🏫 Xonalar ro'yxati | `[ screenshot: room_list ]` |

---

## 📋 Mundarija

- [Loyiha haqida](#-loyiha-haqida)
- [Imkoniyatlar](#-imkoniyatlar)
- [Texnologiyalar](#️-texnologiyalar)
- [Loyiha tuzilmasi](#-loyiha-tuzilmasi)
- [O'rnatish](#️-ornatish)
- [Konfiguratsiya](#️-konfiguratsiya-settingspy)
- [Foydalanish](#-foydalanish)
- [Foydalanuvchi rollari](#-foydalanuvchi-rollari)
- [Dars yaratish jarayoni](#-dars-yaratish-jarayoni)
- [Ma'lumotlar modeli](#-malumotlar-modeli)
- [API endpointlar](#-api-endpointlar)
- [Import funksiyasi](#-import-funksiyasi)
- [Zaxira nusxa](#-zaxira-nusxa-backup--restore)
- [Muammolar va yechimlar](#-muammolar-va-yechimlar-troubleshooting)
- [Hissa qo'shish](#-hissa-qoshish)

---

## 🎯 Loyiha haqida

**Raspisaniya** — oliy ta'lim muassasalarida **qayta o'qish (akademik qarzdorlik)** darslarini boshqarish uchun mo'ljallangan veb-tizim.

### Muammo

Ko'pgina universitetlarda akademik qarzdor talabalar uchun dars jadvali qo'lda tuziladi. Bu jarayon:
- Ko'p vaqt oladi
- O'qituvchi va xona to'qnashuvlariga olib keladi
- Talabalar bir vaqtda ikki darsga tushib qolishi mumkin

### Yechim

Raspisaniya bu jarayonni **to'liq avtomatlashtiradi**: talabalarni guruhlarga ajratib, bo'sh vaqt topib, jadval tuzadi — hammasini bir tugma bilan.

---

## ✨ Imkoniyatlar

### 👥 Guruh boshqaruvi
- Talabalarni **ta'lim tili** bo'yicha avtomatik guruhlarga ajratish (o'zbek, rus, qoraqalpoq, ingliz)
- Guruh hajmini nazorat qilish: minimal **8**, maksimal **15** talaba
- Guruhlarga o'qituvchi va xona biriktirish
- Talabani guruhdan olib chiqish / boshqa guruhga ko'chirish

### 📆 Jadval tuzish
- O'qituvchi va talabalar **bandligini** avtomatik hisobga olish
- To'qnashuvlarni oldini olish (bir vaqtda ikki dars yo'q)
- Shanba kunini jadvalga kiritish/chiqarish imkoniyati
- Dars vaqtini keyin **drag & drop** orqali o'zgartirish (AJAX)

### 🖥️ Foydalanuvchi panellari
- **Admin**: barcha boshqaruv funksiyalari
- **O'qituvchi**: o'z haftalik jadvalini ko'rish
- **Talaba**: o'z haftalik jadvalini ko'rish
- Hafta bo'yicha navigatsiya (oldingi/keyingi hafta)

### 📊 Hisobotlar
- Haftalik jadvalni **Excel (.xlsx)** formatda eksport
- Guruh talabalar ro'yxatini Excel formatda eksport
- Qarzdor talabalar ro'yxatini fan bo'yicha eksport
- Statistika API (darslar, o'qituvchilar, talabalar, xonalar soni)

### 🔒 Xavfsizlik
- Rol asosidagi kirish nazorati
- Har bir foydalanuvchi faqat o'z ma'lumotlarini ko'radi
- Parolni o'zgartirish imkoniyati

---

## 🛠️ Texnologiyalar

| Texnologiya | Maqsad | Versiya |
|-------------|--------|---------|
| **Python** | Backend til | 3.10+ |
| **Django** | Veb freymvork | 4.x |
| **SQLite** | Ma'lumotlar bazasi (default) | — |
| **openpyxl** | Excel fayllar bilan ishlash | 3.x |
| **Bootstrap** | UI/UX dizayni | 5.x |
| **JavaScript (Fetch API)** | AJAX drag & drop | ES6+ |

---

## 📁 Loyiha tuzilmasi

```
Raspisaniya/
│
├── conf/                          # Django asosiy sozlamalari
│   ├── __init__.py
│   ├── settings.py                # Loyiha konfiguratsiyasi
│   ├── urls.py                    # Asosiy URL marshrutlari
│   ├── asgi.py
│   └── wsgi.py
│
├── accounts/                      # Autentifikatsiya ilovasi
│   ├── migrations/
│   ├── views.py                   # Login, logout, student/teacher dashboard
│   ├── urls.py                    # accounts/ URL marshrutlari
│   └── templates/
│       └── accounts/
│           ├── login.html
│           ├── change_password.html
│           ├── student_dashboard.html
│           └── teacher_dashboard.html
│
├── raspisaniya/                   # Asosiy ilova
│   ├── migrations/                # Ma'lumotlar bazasi migratsiyalari
│   ├── management/                # Maxsus management buyruqlari
│   ├── __init__.py
│   ├── models.py                  # 8 ta ma'lumotlar modeli
│   ├── views.py                   # Barcha ko'rinishlar (700+ qator)
│   ├── forms.py                   # Django formalar
│   ├── urls.py                    # raspisaniya/ URL marshrutlari
│   ├── admin.py
│   └── templates/
│       └── raspisaniya/
│           ├── base.html
│           ├── weekly_schedule.html
│           ├── lesson_list.html
│           ├── lesson_create.html
│           ├── lesson_schedule.html
│           ├── build_schedule_errors.html
│           ├── course_update.html
│           ├── import_students.html
│           ├── move_students.html
│           ├── reset_database.html
│           ├── restore_database.html
│           ├── room_create.html
│           ├── room_list.html
│           ├── student_create.html
│           ├── student_list.html
│           ├── student_update.html
│           ├── subject_list.html
│           ├── subject_students.html
│           ├── teacher_create.html
│           ├── teacher_list.html
│           └── ... (20+ shablon)
│
├── static/                        # CSS, JS, rasm fayllari
├── templates/                     # Umumiy shablonlar
├── manage.py
├── requirements.txt
├── db.sqlite3
├── .gitignore
└── README.md
```

---

## ⚙️ O'rnatish

### Talablar

- Python **3.10** yoki yuqori
- pip
- Git

### 1-qadam: Repozitoriyani klonlash

```bash
git clone https://github.com/username/raspisaniya.git
cd raspisaniya
```

### 2-qadam: Virtual muhit yaratish

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate
```

### 3-qadam: Kutubxonalarni o'rnatish

```bash
pip install -r requirements.txt
```

`requirements.txt` tarkibi:
```
Django>=4.0
openpyxl>=3.0
```

### 4-qadam: Ma'lumotlar bazasini sozlash

```bash
python manage.py migrate
```

### 5-qadam: Superuser (admin) yaratish

```bash
python manage.py createsuperuser
```

```
Username: admin
Email address: admin@example.com
Password: ********
```

### 6-qadam: Serverni ishga tushirish

```bash
python manage.py runserver
```

Brauzerda oching: [http://127.0.0.1:8000](http://127.0.0.1:8000)

---

## 🔧 Konfiguratsiya (`settings.py`)

### Maxfiy kalit

```python
# ⚠️ Production muhitida albatta o'zgartiring!
SECRET_KEY = 'django-insecure-your-secret-key-here'
```

Yangi kalit generatsiya qilish:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### Debug rejimi

```python
# Development uchun
DEBUG = True

# Production uchun — albatta False qiling!
DEBUG = False
ALLOWED_HOSTS = ['yourdomain.com', 'www.yourdomain.com']
```

### Ma'lumotlar bazasi

Default SQLite (kichik loyihalar uchun yetarli):
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
```

PostgreSQL ga o'tish (tavsiya etiladi):
```python
# pip install psycopg2-binary
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'raspisaniya_db',
        'USER': 'db_user',
        'PASSWORD': 'db_password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

### Til va vaqt zonasi

```python
LANGUAGE_CODE = 'uz-uz'
TIME_ZONE = 'Asia/Tashkent'
USE_TZ = True
```

### Statik fayllar (Production)

```bash
python manage.py collectstatic
```

---

## 📖 Foydalanish

### Asosiy ish oqimi

```
1. Fanlar qo'shish         →  /subjects/
        ↓
2. O'qituvchilar qo'shish  →  /teachers/
        ↓
3. Xonalar qo'shish        →  /rooms/
        ↓
4. Talabalar import qilish →  /student/import/
        ↓
5. Dars yaratish           →  /lesson/create/
        ↓
6. Jadval tuzish           →  /build-schedule/
        ↓
7. Haftalik jadval         →  /weekly-schedule/
```

---

## 👤 Foydalanuvchi rollari

### Admin (Superuser)

| Funksiya | URL |
|----------|-----|
| Darslar ro'yxati | `/` |
| Yangi dars yaratish | `/lesson/create/` |
| Jadval tuzish | `/build-schedule/` |
| Haftalik jadval | `/weekly-schedule/` |
| O'qituvchilar | `/teachers/` |
| Talabalar | `/students/` |
| Fanlar | `/subjects/` |
| Xonalar | `/rooms/` |
| Bazani tiklash | `/reset-database/` |
| Backup | `/export-database/` |

### O'qituvchi

Login: `teacher_id` (masalan: `T-101`) / parol

- ✅ O'z haftalik jadvalini ko'rish (`/teacher/`)
- ✅ Parolni o'zgartirish (`/change-password/`)
- ❌ Boshqa sahifalarga kirish yo'q

### Talaba

Login: `student_id` (masalan: `S-101`) / parol

- ✅ O'z haftalik jadvalini ko'rish (`/student/`)
- ✅ Parolni o'zgartirish (`/change-password/`)
- ❌ Boshqa sahifalarga kirish yo'q

> **Default parol:** Yangi foydalanuvchi uchun ID o'zi parol bo'lib tayinlanadi.
> Masalan, ID = `S-42` bo'lsa, parol ham `S-42`.

---

## 🔄 Dars yaratish jarayoni

### 1-bosqich — Asosiy ma'lumotlar

```
Fan tanlash
Boshlanish sanasi
Jami darslar soni        (masalan: 16)
Haftada nechta dars      (masalan: 4)
Shanba kuni kiritilsinmi? (Ha / Yo'q)
```

### 2-bosqich — Guruhlar va o'qituvchilar

Tizim avtomatik ravishda:
- Tanlangan fandan qarzdor talabalarni topadi
- Ularni **ta'lim tili bo'yicha** ajratadi
- Har 8–15 talabadan bir guruh tuzadi
- Har guruhga o'qituvchi tayinlash imkoniyatini beradi

> ⚠️ 8 talabadan kam guruhlar avtomatik chiqarib tashlanadi.

### 3-bosqich — Tasdiqlash va saqlash

- Ma'lumotlarni ko'rib chiqish
- "Saqlash" → kurs yaratiladi
- Keyin **"Jadval tuzish"** → jadval avtomatik tuziladi

### Jadval tuzish algoritmi

```
Har bir guruh uchun:
  1. Haftaning qaysi kunlari bo'sh ekanligini tekshir
  2. O'qituvchining band vaqtlarini chiqar
  3. Talabalarning band vaqtlarini chiqar
  4. Ikki ketma-ket bo'sh para topish
  5. Agar topilmasa — keyingi haftaga o'tish
  6. Barcha darslar joylashtirilguncha takrorlash
```

### Para vaqtlari

| Para | Boshlanish | Tugash |
|------|-----------|--------|
| 1-para | 08:30 | 09:50 |
| 2-para | 10:00 | 11:20 |
| 3-para | 12:00 | 13:20 |
| 4-para | 13:30 | 14:50 |
| 5-para | 15:00 | 16:20 |
| 6-para | 16:30 | 17:50 |

---

## 🗄️ Ma'lumotlar modeli

```
Subject (Fan)
    ↑ ManyToMany (debts)
Student (Talaba) ←──────────────────────┐
    │                                   │
    └──→ Group (Guruh)                  │ ManyToMany
                                        │
Course (Kurs)                           │
    │                                   │
    └──→ CourseGroup (Dars guruhi) ─────┘
              │
              ├──→ Teacher (O'qituvchi)
              ├──→ Room (Xona)
              └──→ GroupSchedule (Jadval)
                        date
                        start_time
                        lesson_number
```

| Model | Asosiy maydonlar |
|-------|-----------------|
| `Subject` | `name` |
| `Group` | `name` |
| `Student` | `student_id`, `first_name`, `last_name`, `language`, `debts` |
| `Teacher` | `teacher_id`, `first_name`, `last_name`, `subjects` |
| `Course` | `subject`, `start_date`, `end_date`, `total_lessons`, `lessons_per_week` |
| `Room` | `name`, `capacity` |
| `CourseGroup` | `course`, `teacher`, `students`, `room`, `is_scheduled`, `language` |
| `GroupSchedule` | `group`, `date`, `lesson_number`, `start_time` |

---

## 🔌 API Endpointlar

### Statistika

**`GET /api/stats/`** — Login talab etilmaydi

```json
{
    "lessons": 24,
    "teachers": 15,
    "students": 312,
    "rooms": 8
}
```

---

### Dars vaqtini AJAX orqali o'zgartirish

**`POST /change-lesson-time-ajax/<sched_pk>/`**

Drag & drop bilan ishlaydi. CSRF cookie kerak.

**So'rov:**
```json
{
    "new_date": "2026-04-15",
    "new_time": "10:00"
}
```

**Muvaffaqiyatli javob:**
```json
{
    "success": true,
    "new_date": "15.04.2026",
    "new_date_iso": "2026-04-15",
    "new_time": "10:00",
    "end_time": "11:20",
    "weekday": "Seshanba"
}
```

**Xatolik javoblari:**

| Sabab | `error` |
|-------|---------|
| Guruh band | `"2026-04-15 kuni 10:00 da 2-guruhda boshqa dars bor!"` |
| O'qituvchi band | `"O'qituvchi Aliyev 2026-04-15 kuni 10:00 da band!"` |
| Talabalar band | `"Ba'zi talabalar 2026-04-15 kuni 10:00 da band!"` |
| Noto'g'ri format | `"Noto'g'ri sana formati"` |

```json
{
    "success": false,
    "error": "O'qituvchi Aliyev 2026-04-15 kuni 10:00 da band!"
}
```

---

### Boshqa endpointlar (forma orqali)

| Method | URL | Tavsif |
|--------|-----|--------|
| `POST` | `/schedule/<pk>/change-time/` | Dars vaqtini forma bilan o'zgartirish |
| `POST` | `/group/<pk>/add-student/` | Guruhga talaba qo'shish |
| `POST` | `/group/<gpk>/remove-student/<spk>/` | Talabani guruhdan chiqarish |
| `POST` | `/group/<pk>/assign-room/` | Guruhga xona biriktirish |
| `POST` | `/group/<pk>/change-teacher/` | Guruh o'qituvchisini almashtirish |
| `GET`  | `/weekly-schedule/excel/` | Haftalik jadvalni Excel'da yuklab olish |
| `GET`  | `/lesson/<pk>/schedule/excel/` | Guruh jadvalini Excel'da yuklab olish |
| `GET`  | `/subject/<pk>/students/excel/` | Qarzdor talabalar Excel'da |

---

## 📥 Import funksiyasi

### Talabalar importi (`/student/import/`)

Excel `.xlsx` formatida. 1-qator sarlavha, 2-qatordan ma'lumot.

| Ustun | № | Mazmun | Misol |
|-------|---|--------|-------|
| A | 1 | Tartib raqami | `101` → `S-101` |
| B | 2 | F.I.Sh | `Aliyev Sardor Bekovich` |
| E | 5 | Guruh nomi | `2-A` |
| F | 6 | Ta'lim tili | `O'zbek` / `Рус` / `Қарақалпақ` |
| I | 9 | Qarzdor fanlar (`;` bilan) | `Kimyo;Fizika (retake)` |

**Ta'lim tili qiymatlari:**

| Excel'da | Tizimda |
|----------|---------|
| O'zbek, uz | `uz` |
| Рус, Rus | `ru` |
| Қарақалпақ, Qoraqalpoq | `qq` |
| Ingliz, Eng | `en` |

**Namuna:**
```
| 1 | Aliyev Sardor   | | | 2-A | O'zbek | | | Kimyo;Fizika       |
| 2 | Karimova Malika | | | 3-B | Рус    | | | Organik kimyo      |
```

---

### O'qituvchilar importi (`/teacher/import/`)

| Ustun | № | Mazmun | Misol |
|-------|---|--------|-------|
| A | 1 | Tartib raqami | `15` → `T-15` |
| B | 2 | F.I.Sh | `Karimov Bobur` |
| C | 3 | Fanlar (vergul bilan) | `Kimyo, Fizika` |

---

## 💾 Zaxira nusxa (Backup & Restore)

### Eksport

```
GET /export-database/
```

Barcha ma'lumotlarni `timetable_backup.json` sifatida yuklab oladi.

```bash
# Buyruq qatori orqali ham:
python manage.py dumpdata --indent 2 > backup.json
```

### Restore

```
POST /restore-database/
```

`.json` faylni forma orqali yuklang.

```bash
# Buyruq qatori orqali:
python manage.py loaddata backup.json
```

> ⚠️ Restore qilishdan oldin mavjud ma'lumotlarni tozalang, aks holda ID to'qnashuvi bo'lishi mumkin.

### Ma'lumotlar bazasini tozalash (`/reset-database/`)

O'chirish tartibi (muhim — foreign key bog'liqligi):

```
1. GroupSchedule  →  2. CourseGroup  →  3. Student
4. Course         →  5. Subject      →  6. Teacher  →  7. Room
```

---

## 🔍 Muammolar va Yechimlar (Troubleshooting)

### ❌ `ModuleNotFoundError: No module named 'openpyxl'`

```bash
pip install openpyxl
```

---

### ❌ `OperationalError: no such table`

```bash
python manage.py makemigrations
python manage.py migrate
```

---

### ❌ Login: "ID yoki parol noto'g'ri"

```bash
python manage.py shell
>>> from django.contrib.auth.models import User
>>> User.objects.filter(username='S-101').exists()
# False bo'lsa — foydalanuvchi yo'q

# Parolni tiklash:
python manage.py changepassword S-101
```

---

### ❌ Jadval tuzishda guruh "jadvalsiz" qoldi

**Sabab:** O'qituvchi yoki talabalar barcha paraga band.

**Yechim:**
1. `build_schedule_errors.html` da xatolik sababini o'qing
2. O'qituvchini almashtirib qayta jadval tuzing
3. Yoki guruhni o'chirib, talabalarni boshqa guruhga ko'chiring: `/move-students/<from>/<to>/`

---

### ❌ Excel import'da "Xatolik" xabari

- Fayl `.xlsx` formatida ekanligini tekshiring (`.xls` emas)
- 1-qator sarlavha bo'lishi kerak — import 2-qatordan boshlanadi
- F.I.Sh ustunida kamida 2 so'z bo'lishi kerak (ism + familiya)

---

### ❌ CSS/Static fayllar ko'rinmayapti

```python
# settings.py da tekshiring:
DEBUG = True   # development uchun
```

Production uchun:
```bash
python manage.py collectstatic
# nginx/apache static fayllarni serve qilishini sozlang
```

---

### ❌ `CSRF verification failed`

Formada `{% csrf_token %}` borligini tekshiring:
```html
<form method="post">
    {% csrf_token %}
    ...
</form>
```

---

### ❌ `IntegrityError: UNIQUE constraint failed`

Import faylda takroriy ID yoki ism bor. Excel faylda dublikatlarni o'chiring.

---

### ❌ Xona biriktirish: "Xona band" xabari

O'sha vaqtda boshqa guruh o'sha xonada dars o'tayapti. Boshqa xona tanlang yoki dars vaqtini o'zgartiring.

---

## 🤝 Hissa qo'shish

### Qadamlar

```bash
# 1. Fork va clone
git clone https://github.com/YOUR_USERNAME/raspisaniya.git
cd raspisaniya

# 2. Branch yaratish
git checkout -b feature/yangi-funksiya   # Yangi funksiya
git checkout -b fix/xatolik-nomi         # Bug fix

# 3. O'zgarishlar va commit
git add .
git commit -m "feat: yangi funksiya — qisqacha tavsif"

# 4. Push va Pull Request
git push origin feature/yangi-funksiya
```

### Commit xabar formati

```
feat: yangi funksiya qo'shildi
fix:  xatolik tuzatildi
docs: hujjat yangilandi
refactor: kod qayta tashkil etildi
style: formatlash o'zgartirildi
```

### Bug xabar berish

[Issues](https://github.com/username/raspisaniya/issues) bo'limida quyidagilarni ko'rsating:
- Muammo tavsifi
- Qayta takrorlash qadamlari
- Kutilgan vs haqiqiy natija
- Python va Django versiyasi

---

## 📄 Litsenziya

MIT License — [`LICENSE`](LICENSE) faylini ko'ring.

---

<div align="center">

**Raspisaniya** — O'zbekiston universitetlari uchun 🇺🇿

[GitHub Issues](https://github.com/username/raspisaniya/issues) orqali murojaat qiling

</div>
