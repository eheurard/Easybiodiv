document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('test-btn');
    btn.addEventListener('click', () => {
        btn.classList.toggle('active');
    });
});
