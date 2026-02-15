document.addEventListener('DOMContentLoaded', () => {
    const showTeachersBtn = document.getElementById('show_teachers');
    const teachersDiv = document.getElementById('teachers_div');
    const showStudentsBtnDiv = document.getElementById('students_button_div');
    const showStudentsBtn = document.getElementById('show_students');
    const studentsDiv = document.getElementById('students_div');
    const teacherSelect = document.getElementById('id_teachers');
    const maxTeachers = 2;

    // O'qituvchi tugmasi bosilganda
    showTeachersBtn?.addEventListener('click', () => {
        teachersDiv.style.display = 'block';
        showStudentsBtnDiv.style.display = 'block';
        showTeachersBtn.style.display = 'none';
    });

    // O'quvchilar tugmasi bosilganda
    showStudentsBtn?.addEventListener('click', () => {
        studentsDiv.style.display = 'block';
        showStudentsBtnDiv.style.display = 'none';
    });

    // O'qituvchilarni 2 ta bilan cheklash
    teacherSelect?.addEventListener('change', () => {
        const selected = [...teacherSelect.options].filter(o => o.selected);
        [...teacherSelect.options].forEach(o => {
            o.disabled = selected.length >= maxTeachers && !o.selected;
        });
    });
});
