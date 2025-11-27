# FedEx Shipment Gateway

Невеликий сервіс на FastAPI для створення відправок у FedEx (звичайна та фрахт), підтримки кількох акаунтів, збереження PDF-етикеток та отримання попередніх тарифів. Інтеграція використовує публічні FedEx API (`/oauth/token`, `/rate/v1/rates/quotes`, `/ship/v1/shipments`) та зберігає кожен зовнішній запит і відповідь у БД.

## Можливості
- Реєстрація декількох облікових записів FedEx/FedEx Freight.
- Вибір акаунту при запитах на розрахунок тарифу або створення відправлення.
- Генерація PDF-етикеток та збереження їх у `storage/labels`.
- Повернення трек-номеру та оцінки вартості під час створення відправлення.
- Токен-автентифікація через query-параметр `token`.
- Логування кожного HTTP-звернення до FedEx (запит/відповідь, статус-код) у таблицю `api_logs`.

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
   export FEDEX_BASE_URL=https://apis-sandbox.fedex.com
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
      "service_type": "FIP",
      "weight_kg": 3.5,
      "destination_country": "DE"
    }'
  ```

- **Створити відправлення**
  ```bash
  curl -X POST "http://localhost:8000/orders?token=super-secret-token" \
    -H "Content-Type: application/json" \
    -d '{
      "order_reference": "ORDER-1",
      "account_id": 1,
      "service_type": "FIP",
      "recipient_name": "John Doe",
      "recipient_address": "1 Market St",
      "recipient_city": "Berlin",
      "recipient_country": "DE",
      "weight_kg": 3.5
    }'
  ```

- **Завантажити етикетку**
  ```bash
  curl -L "http://localhost:8000/shipments/1/label?token=super-secret-token" -o label.pdf
  ```

## Примітки
- Запит авторизації виконується на `/oauth/token` (grant_type=client_credentials); отриманий токен автоматично кешується.
- Тарифи беруться з `/rate/v1/rates/quotes`, створення відправки — через `/ship/v1/shipments` із PDF-етикеткою (base64) та збереженням у `storage/labels`.
- Усі дозволені сервіси: FIP, IPE, FIE, RE, PO, FICP, IPF, IEF, REF.
- Дані зберігаються у SQLite, тому резервуйте файл `data/app.db` при продакшн-розгортанні.
