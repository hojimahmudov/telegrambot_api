// mini_app/script.js (yoki index.html ichidagi <script> tegi)

document.addEventListener('DOMContentLoaded', function() {
    let tg = window.Telegram.WebApp;
    tg.ready();

    const categoriesListDiv = document.getElementById('categories-list');
    const productsListDiv = document.getElementById('products-list'); // Yangi div
    const loadingDiv = document.getElementById('loading');
    const errorDiv = document.getElementById('error');

    const API_BASE_URL = 'http://127.0.0.1:8000/api/v1/';
    const userLanguage = tg.initDataUnsafe?.user?.language_code || 'uz';

    // --- Kategoriyalarni olish uchun funksiya (avvalgidek) ---
    async function fetchCategories() {
        loadingDiv.style.display = 'block';
        errorDiv.style.display = 'none';
        categoriesListDiv.innerHTML = ''; // Kategoriyalar listini tozalaymiz
        productsListDiv.innerHTML = '<p>Iltimos, yuqoridan kategoriya tanlang.</p>'; // Mahsulotlar bo'limini tiklaymiz

        try {
            const response = await fetch(API_BASE_URL + 'categories/', {
                method: 'GET',
                headers: { 'Accept': 'application/json', 'Accept-Language': userLanguage }
            });
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const paginatedResponse = await response.json();
            if (paginatedResponse && paginatedResponse.results) {
                 displayCategories(paginatedResponse.results);
            } else {
                 console.error("API javobi kutilgan formatda emas:", paginatedResponse);
                 displayCategories([]);
            }
        } catch (error) {
            console.error('Kategoriyalarni olishda xatolik:', error);
            errorDiv.textContent = `Kategoriyalarni yuklashda xatolik: ${error.message}`;
            errorDiv.style.display = 'block';
        } finally {
             if(loadingDiv) loadingDiv.style.display = 'none';
        }
    }

    // --- Kategoriyalarni ko'rsatish funksiyasi (onclick o'zgargan) ---
    function displayCategories(categories) {
        categoriesListDiv.innerHTML = ''; // Tozalash
        if (!categories || categories.length === 0) {
            categoriesListDiv.innerHTML = '<p>Kategoriyalar topilmadi.</p>';
            return;
        }
        categories.forEach(category => {
            const categoryDiv = document.createElement('div');
            categoryDiv.className = 'category';
            categoryDiv.textContent = category.name || 'Nomsiz kategoriya';
            // --- O'ZGARISH: onclick endi mahsulotlarni yuklaydi ---
            categoryDiv.onclick = () => {
                // alert('Tanlangan kategoriya IDsi: ' + category.id); // Eski alert
                fetchAndDisplayProducts(category.id); // Yangi funksiyani chaqiramiz
            };
            // -----------------------------------------------
            if (category.image_url) { /* ... (rasm kodi avvalgidek) ... */ }
            categoriesListDiv.appendChild(categoryDiv);
        });
    }

    // --- YANGI: Mahsulotlarni olish va ko'rsatish funksiyasi ---
    async function fetchAndDisplayProducts(categoryId) {
        productsListDiv.innerHTML = '<p>Mahsulotlar yuklanmoqda...</p>'; // Yuklanish xabari
        errorDiv.style.display = 'none'; // Eski xatoni yashirish

        try {
            const response = await fetch(`${API_BASE_URL}products/?category_id=${categoryId}`, { // Kategoriya ID si bilan so'rov
                method: 'GET',
                headers: { 'Accept': 'application/json', 'Accept-Language': userLanguage }
                // Agar mahsulotlarni ko'rish uchun ham login kerak bo'lsa, 'Authorization' qo'shiladi
            });
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const paginatedResponse = await response.json();
            if (paginatedResponse && paginatedResponse.results) {
                displayProducts(paginatedResponse.results);
            } else {
                console.error("Mahsulotlar API javobi kutilgan formatda emas:", paginatedResponse);
                displayProducts([]);
            }
        } catch (error) {
            console.error(`Kategoriya ${categoryId} uchun mahsulotlarni olishda xatolik:`, error);
            productsListDiv.innerHTML = `<p style="color: red;">Mahsulotlarni yuklashda xatolik: ${error.message}</p>`;
        }
    }

    // --- YANGI: Mahsulotlarni HTML'ga chiqarish funksiyasi ---
    function displayProducts(products) {
        productsListDiv.innerHTML = ''; // Tozalash
        if (!products || products.length === 0) {
            productsListDiv.innerHTML = '<p>Bu kategoriyada mahsulotlar topilmadi.</p>';
            return;
        }

        products.forEach(product => {
            const productDiv = document.createElement('div');
            productDiv.className = 'product'; // Stil berish uchun klass qo'shish mumkin

            let content = '';
            if (product.image_url) {
                content += `<img src="${product.image_url}" alt="${product.name}" style="max-width: 60px; vertical-align: middle; margin-right: 10px;" onerror="this.style.display='none'">`;
            }
            content += `<strong>${product.name || 'Nomsiz'}</strong>`;
            if (product.description) {
                content += `<br><small>${product.description}</small>`;
            }
            content += `<br>Narxi: ${product.price} so'm`;
            // Savatga qo'shish tugmasi
            content += ` <button onclick="addToCart(${product.id})">Savatga</button>`;

            productDiv.innerHTML = content;
            productsListDiv.appendChild(productDiv);
        });
    }

    // --- YANGI: Savatga qo'shish funksiyasi (Hozircha Placeholder) ---
    function addToCart(productId) {
        // !!! MUHIM: Bu funksiya ishlashi uchun foydalanuvchi autentifikatsiyadan
        // o'tgan bo'lishi va API so'roviga JWT token qo'shilishi kerak.
        // Hozircha bizda bu logika yo'q.
        alert(`Mahsulot ID ${productId} savatga qo'shishga harakat qilindi. (Autentifikatsiya talab qilinadi)`);

        // Kelajakda bu funksiya quyidagicha bo'ladi:
        // 1. Saqlangan access_token'ni olish.
        // 2. Agar token bo'lmasa, login/register'ga yo'naltirish.
        // 3. API'ga POST /api/v1/cart/ so'rovini Authorization sarlavhasi
        //    va { "product_id": productId, "quantity": 1 } body bilan yuborish.
        // 4. Natijani foydalanuvchiga ko'rsatish.
    }


    // Sahifa yuklanganda kategoriyalarni olib kelamiz
    fetchCategories();

}); // DOMContentLoaded tugadi