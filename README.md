# FedEx Shipment Gateway

Невеликий сервіс на FastAPI для створення відправок у FedEx (звичайна та фрахт), підтримки кількох акаунтів, збереження PDF-етикеток та отримання попередніх тарифів.

## Можливості
- Реєстрація декількох облікових записів FedEx/FedEx Freight.
- Вибір акаунту при запитах на розрахунок тарифу або створення відправлення.
- Генерація PDF-етикеток та збереження їх у `storage/labels`.
- Повернення трек-номеру та оцінки вартості під час створення відправлення.
- Токен-автентифікація через query-параметр `token`.

## Запуск
1. Створіть віртуальне середовище та встановіть залежності:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Додайте файл `.env` або встановіть змінні оточення:
   ```bash
   export SERVICE_TOKEN=super-secret-token
   export DATABASE_URL=sqlite:///$(pwd)/data/app.db
   ```
3. Запустіть сервер:
   ```bash
   uvicorn app.main:app --reload
   ```

## Приклади запитів
- **Створити акаунт**
  ```bash
  curl -X POST "http://localhost:8000/accounts?token=super-secret-token" \
    -H "Content-Type: application/json" \
    -d '{
      "name": "Main standard",
      "account_number": "123456",
      "meter_number": "98765",
      "api_key": "demo-key",
      "api_secret": "demo-secret",
      "is_freight": false
    }'
  ```

- **Запитати тариф**
  ```bash
  curl -X POST "http://localhost:8000/rates?token=super-secret-token" \
    -H "Content-Type: application/json" \
    -d '{
      "account_id": 1,
      "service_type": "fedex_standard",
      "weight_kg": 3.5,
      "destination_country": "USA"
    }'
  ```

- **Створити відправлення**
  ```bash
  curl -X POST "http://localhost:8000/orders?token=super-secret-token" \
    -H "Content-Type: application/json" \
    -d '{
      "order_reference": "ORDER-1",
      "account_id": 1,
      "service_type": "fedex_standard",
      "recipient_name": "John Doe",
      "recipient_address": "1 Market St",
      "recipient_city": "San Francisco",
      "recipient_country": "USA",
      "weight_kg": 3.5
    }'
  ```

- **Завантажити етикетку**
  ```bash
  curl -L "http://localhost:8000/shipments/1/label?token=super-secret-token" -o label.pdf
  ```

## Примітки
- Реалізація FedEx інтеграції емульована: тариф і трек-номер генеруються всередині сервісу. Це дає можливість замінити `FedExClient` реальними API-викликами без зміни API сервісу.
- Дані зберігаються у SQLite, тому резервуйте файл `data/app.db` при продакшн-розгортанні.
