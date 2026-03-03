# 📅 Raspisaniya — Dars Jadvali Tizimi

Django asosida qurilgan avtomatik dars jadvali boshqaruv tizimi.
Talabalar qarzdor bo'lgan fanlar bo'yicha guruhlar tuziladi, o'qituvchilar tayinlanadi va 15 kunlik jadval avtomatik yaratiladi.

---

## 🚀 Texnologiyalar

- **Python** 3.10
- **Django** 5.2
- **SQLite** (ma'lumotlar bazasi)
- **Bootstrap** 5.3
- **openpyxl** (Excel import/export)
- **django-widget-tweaks**
- **GSAP** (animatsiyalar)
- **Material Design 3** (UI)

---

## 📦 O'rnatish

### 1. Repozitoriyani klonlash
```bash
git clone https://github.com/Sohib70/Raspisaniya.git
cd Raspisaniya
```

### 2. Virtual muhit yaratish va faollashtirish
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / Mac
source .venv/bin/activate
```

### 3. Kutubxonalarni o'rnatish
```bash
pip install -r requirements.txt
```

### 4. Ma'lumotlar bazasini yaratish
```bash
python manage.py migrate
```

### 5. Admin foydalanuvchi yaratish
```bash
python manage.py createsuperuser
```

### 6. Serverni ishga tushirish
```bash
python manage.py runserver
```

Brauzerda oching: **http://127.0.0.1:8000**

---

## 🗂️ Loyiha tuzilmasi
```
Raspisaniya/
├── conf/
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── raspisaniya/
│   ├── models.py
│   ├── views.py
│   ├── forms.py
│   ├── urls.py
│   └── migrations/
├── templates/
│   └── raspisaniya/
│       ├── base.html
│       ├── lesson_create.html
│       ├── lesson_list.html
│       ├── lesson_schedule.html
│       ├── teacher_create.html
│       ├── teacher_list.html
│       ├── teacher_import.html
│       ├── student_create.html
│       ├── student_list.html
│       ├── import_students.html
│       ├── subject_create.html
│       └── subject_list.html
├── static/
├── manage.py
├── requirements.txt
└── README.md
```

---

## 🗄️ Modellar

| Model | Vazifasi |
|-------|----------|
| `Subject` | Fanlar |
| `Group` | Talabalar guruhi (sinf) |
| `Student` | Talaba (qarzdor fanlar bilan) |
| `Teacher` | O'qituvchi (o'qitadigan fanlar bilan) |
| `Lesson` | Dars (fan, sana, vaqt) |
| `LessonGroup` | Dars guruhi (o'qituvchi + talabalar) |
| `LessonSchedule` | 15 ta dars jadvali sanalar |

---

## 🎯 Asosiy funksiyalar

### 📚 Dars yaratish (3 bosqich)
1. **Fan tanlanadi**
2. **Talabalar avtomatik aniqlanadi** — o'sha fandan qarzdor bo'lganlar
3. **Guruhlarga bo'linadi** — maksimal 30 ta, teng taqsimlash
   - 70 talaba → 24 + 23 + 23
   - 31 talaba → 16 + 15
4. **Har guruh uchun o'qituvchi tayinlanadi**
5. **Sana va vaqt kiritiladi** — 80 daqiqa davom etadi

### 📅 Jadval hisoblash (15 dars)
| Boshlanish kuni | Dars kunlari |
|----------------|--------------|
| Dushanba | Dushanba, Chorshanba, Juma |
| Seshanba | Seshanba, Payshanba, Shanba |
| Chorshanba | Chorshanba, Juma, Dushanba |
| Payshanba | Payshanba, Shanba, Seshanba |

### 🔒 Conflict tekshiruvi
- ❌ O'qituvchi bir vaqtda 2 ta darsda bo'la olmaydi
- ❌ Talaba bir vaqtda 2 ta darsda bo'la olmaydi
- ❌ Bir darsda 2 ta guruhga bir xil o'qituvchi tayinlanmaydi
- Xato bo'lsa **qizil rang** bilan ko'rsatiladi

### 📊 Excel imkoniyatlari
- Talabalarni Excel orqali import qilish
- O'qituvchilarni Excel orqali import qilish
- Dars jadvalini Excel formatida yuklab olish

---

## 📊 Excel format

### Talabalar import (`/student/import/`)
| A ustun | B ustun | C ustun |
|---------|---------|---------|
| Ism Familiya Sharif | Guruh | Fanlar (vergul bilan) |
| Karimov Ali Vali | 101-guruh | Matematika,Fizika |

### O'qituvchilar import (`/teacher/import/`)
| A ustun | B ustun |
|---------|---------|
| Ism Familiya Sharif | Fanlar (vergul bilan) |
| Rahimov Vali Soli | Matematika,Fizika |

---

## 📌 URL yo'llari

| URL | Vazifasi |
|-----|----------|
| `/` | Darslar ro'yxati |
| `/lesson/create/` | Yangi dars yaratish |
| `/lesson/<pk>/schedule/` | Dars jadvali ko'rish |
| `/lesson/<pk>/schedule/excel/` | Jadvalni Excel yuklab olish |
| `/lesson/<pk>/delete/` | Darsni o'chirish |
| `/teachers/` | O'qituvchilar ro'yxati |
| `/teacher/create/` | O'qituvchi qo'shish |
| `/teacher/<pk>/update/` | O'qituvchini tahrirlash |
| `/teacher/<pk>/delete/` | O'qituvchini o'chirish |
| `/teacher/import/` | O'qituvchi Excel import |
| `/students/` | Talabalar ro'yxati |
| `/student/create/` | Talaba qo'shish |
| `/student/<pk>/update/` | Talabani tahrirlash |
| `/student/<pk>/delete/` | Talabani o'chirish |
| `/student/import/` | Talaba Excel import |
| `/subjects/` | Fanlar ro'yxati |
| `/subject/create/` | Fan qo'shish |
| `/subject/<pk>/update/` | Fanni tahrirlash |
| `/subject/<pk>/delete/` | Fanni o'chirish |
| `/admin/` | Django admin panel |

---

## 👤 Admin panel
```
http://127.0.0.1:8000/admin/
```

---

## 📸 Interfeys

- Material Design 3 uslubida
- Dark / Light mavzu
- Mobil qurilmalarga moslashgan (responsive)
- Animatsiyalar (GSAP)

---

## 👨‍💻 Muallif

**Sohib70** — [GitHub](https://github.com/Sohib70)