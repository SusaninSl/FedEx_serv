# FedEx Shipment Gateway

Невеликий сервіс на FastAPI для створення відправок у FedEx (звичайна та фрахт), підтримки кількох акаунтів, збереження PDF-етикеток та отримання попередніх тарифів. Інтеграція використовує публічні FedEx API (`/oauth/token`, `/rate/v1/rates/quotes`, `/ship/v1/shipments`) та зберігає кожен зовнішній запит і відповідь у БД та окремі JSON-файли.

## Можливості
- Реєстрація декількох облікових записів FedEx/FedEx Freight.
- Вибір акаунту при запитах на розрахунок тарифу або створення відправлення.
- Генерація PDF-етикеток та збереження їх у `storage/labels`.
- Повернення трек-номеру та оцінки вартості під час створення відправлення.
- Токен-автентифікація через query-параметр `token`.
- Логування кожного HTTP-звернення до FedEx (запит/відповідь, статус-код) у таблицю `api_logs` та у файли `storage/logs/*.json`.
- Збережені брокери (Broker Select Option), відправки з Third Party Consignee (TPC) та Global Returns.
- Підтримка Electronic Trade Documents (ETD) з аплоадом документів та Email Notification (ShipAlert).
- Трекінг та запит SPOD (підтвердження доставки як PDF), а також тарифи/відправлення для великогабаритних сервісів IPF/IEF/REF.

## Запуск
1. Створіть віртуальне середовище та встановіть залежності:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Додайте файл `.env` або встановіть змінні оточення (тут зберігаються всі ключі й налаштування):
   ```bash
   # токен, що використовується в кожному запиті як `?token=...`
   export SERVICE_TOKEN=super-secret-token

   # шлях до бази даних (можна залишити SQLite або вказати Postgres)
   export DATABASE_URL=sqlite:///$(pwd)/data/app.db

   # базовий URL FedEx (для sandbox: https://apis-sandbox.fedex.com, для продакшену замініть на https://apis.fedex.com)
   export FEDEX_BASE_URL=https://apis-sandbox.fedex.com
   ```
3. Переконайтеся, що існують робочі директорії:
   ```bash
   mkdir -p data storage/labels storage/logs storage/spod
   ```
4. Запустіть сервер:
   ```bash
   uvicorn app.main:app --reload
   ```

## Як усе влаштовано
- `app/main.py` — FastAPI-ендпоїнти (акаунти, склади-відправники, тарифи, створення відправлення, видача етикеток) та middleware для токен-автентифікації.
- `app/services/fedex_client.py` — робота з FedEx API: OAuth (`/oauth/token`), тарифи (`/rate/v1/rates/quotes`), створення відправлень (`/ship/v1/shipments`), збереження PDF.
- `app/models.py` / `app/database.py` — SQLAlchemy-моделі та сесія (записи акаунтів, замовлень, логів зовнішніх запитів, збережені шляхи до етикеток).
- `app/schemas.py` — Pydantic-схеми та перелік дозволених сервіс-кодів, що відповідає наданому списку.
- `app/config.py` — зчитування змінних оточення, які ви виставляєте у `.env` або у своєму хостингу.
- `storage/labels/` — папка з PDF-етикетками, що повернулися з FedEx (base64 -> PDF).
- `storage/logs/` — JSON-журнали кожного запиту та відповіді FedEx із вхідними/вихідними даними.
- `storage/spod/` — PDF-підтвердження доставки (SPOD) за трек-номером.
- `data/` — папка з SQLite БД (якщо використовуєте SQLite).

## Де зберігати ключі доступу FedEx
- Ключі клієнта FedEx (API Key/API Secret) не кладуться у `.env`, а зберігаються в БД для кожного акаунту.
- Додавати їх потрібно через ендпоїнт створення акаунта (`POST /accounts`):
  ```json
  {
    "name": "Main standard",
    "account_number": "123456",
    "meter_number": "98765",
    "api_key": "<your-fedex-api-key>",
    "api_secret": "<your-fedex-api-secret>",
    "is_freight": false
  }
  ```
  Сервіс сам викличе `/oauth/token` з цими ключами, кешує access_token і використовує його для тарифів та відправлень. Для декількох акаунтів просто реєструйте їх окремо.

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

- **Додати відправника (склад)**
  ```bash
  curl -X POST "http://localhost:8000/shippers?token=super-secret-token" \
    -H "Content-Type: application/json" \
    -d '{
      "name": "Kyiv warehouse",
      "company": "My Store LLC",
      "person_name": "Olha Manager",
      "phone_number": "+380441112233",
      "email": "warehouse@example.com",
      "street_lines": "Vulytsia Vasylkivska 1",
      "city": "Kyiv",
      "state_code": "KY",
      "postal_code": "01001",
      "country_code": "UA"
    }'
  ```

- **Додати брокера (для International Broker Select Option)**
  ```bash
  curl -X POST "http://localhost:8000/brokers?token=super-secret-token" \
    -H "Content-Type: application/json" \
    -d '{
      "name": "Customs broker",
      "person_name": "Hans Broker",
      "phone_number": "+49-30-555555",
      "street_lines": "Broker Str. 1",
      "city": "Berlin",
      "state_code": "BE",
      "postal_code": "10115",
      "country_code": "DE"
    }'
  ```

- **Запитати тариф**
  - Якщо вказати `service_type`, повертається ціна конкретного сервісу:
    ```bash
    curl -X POST "http://localhost:8000/rates?token=super-secret-token" \
      -H "Content-Type: application/json" \
      -d '{
        "account_id": 1,
        "shipper_id": 1,
        "service_type": "FIP",
        "weight_kg": 3.5,
        "destination_postal_code": "10117",
        "destination_country": "DE"
      }'
    ```

  - Якщо **не вказувати** `service_type`, відповідь міститиме список тарифів для всіх доступних сервісів:
    ```bash
    curl -X POST "http://localhost:8000/rates?token=super-secret-token" \
      -H "Content-Type: application/json" \
      -d '{
        "account_id": 1,
        "shipper_id": 1,
        "weight_kg": 3.5,
        "destination_postal_code": "10117",
        "destination_country": "DE"
      }'
    ```
  - Для розрахунку тарифу FedEx використовуються лише індекс та код країни відправника/одержувача, валюта відповіді — EUR.

- **Створити відправлення**
  > Ендпоїнт створення відправлення **не робить запит тарифу**; спочатку за потреби викличте `/rates` і самостійно зафіксуйте ціну.
  ```bash
  curl -X POST "http://localhost:8000/orders?token=super-secret-token" \
    -H "Content-Type: application/json" \
    -d '{
      "order_reference": "ORDER-1",
      "account_id": 1,
      "shipper_id": 1,
      "service_type": "FIP",
      "recipient_name": "John Doe",
      "recipient_company": "Doe GmbH",
      "recipient_phone": "+49-30-123456",
      "recipient_email": "john@example.com",
      "recipient_address": "1 Market St",
      "recipient_city": "Berlin",
      "recipient_state_code": "BE",
      "recipient_postal_code": "10115",
      "recipient_country": "DE",
      "weight_kg": 3.5,
      "customs_required": 1,
      "customs_items": [
        {
          "description": "Laptop", "quantity": 1, "price": 1200, "weight_kg": 2.5
        },
        {
          "description": "Power cable"  
        }
      ],
      "broker_id": 1,
      "broker_select_option": true,
      "third_party_consignee": false,
      "ship_alert_emails": ["notify@example.com"],
      "etd_documents": [
        {
          "name": "invoice.pdf",
          "content_base64": "<base64>",
          "doc_type": "COMMERCIAL_INVOICE"
        }
      ]
    }'
  ```
  - Щоб надіслати відправку з **International Broker Select Option**, передайте `broker_id` та `broker_select_option: true` або скористайтеся ендпоїнтом `/orders/bso`.
  - Для **FedEx Third Party Consignee (TPC)** використовуйте поле `third_party_consignee: true` або ендпоїнт `/orders/tpc`.
  - `ship_alert_emails` вмикає Email Notification (ShipAlert), масив email-адрес.
  - `etd_documents` — Electronic Trade Documents (FedEx завантажує переданий PDF/документ).

- **Технічний тест на кілька сервісів** — створює серію відправлень із однаковими відправником/одержувачем, але різними сервісами
  (`FIP`, `IPE`, `FIE`, `RE`, `PO`, `FICP`). До `order_reference_prefix` автоматично додається код сервісу.
  ```bash
  curl -X POST "http://localhost:8000/test/shipments?token=super-secret-token" \
    -H "Content-Type: application/json" \
    -d '{
      "account_id": 1,
      "shipper_id": 1,
      "order_reference_prefix": "TEST-BATCH",
      "recipient_name": "John Doe",
      "recipient_phone": "+49-30-123456",
      "recipient_address": "1 Market St",
      "recipient_city": "Berlin",
      "recipient_state_code": "BE",
      "recipient_postal_code": "10115",
      "recipient_country": "DE",
      "weight_kg": 3.5,
      "customs_required": 1,
      "customs_items": [
        { "description": "Test goods", "quantity": 1, "price": 10 }
      ],
      "ship_alert_emails": ["qa@example.com"]
    }'
  ```
  У відповіді повертається масив результатів по кожному сервісу зі статусом та, за успіху, повним записом відправлення.

- **Глобальний ретерн (FedEx Global Returns, RETURNS)** — клієнт виступає відправником, а склад приймає повернення:
  ```bash
  curl -X POST "http://localhost:8000/returns?token=super-secret-token" \
    -H "Content-Type: application/json" \
    -d '{
      "order_reference": "RETURN-100",
      "account_id": 1,
      "warehouse_shipper_id": 1,
      "service_type": "RETURNS",
      "customer_name": "Jane Customer",
      "customer_phone": "+49-30-222222",
      "customer_address": "Customer Str. 5",
      "customer_city": "Berlin",
      "customer_state_code": "BE",
      "customer_postal_code": "10115",
      "customer_country": "DE",
      "weight_kg": 2.0,
      "return_reference": "ORDER-99"
    }'
  ```
  `warehouse_shipper_id` — склад, куди повертається товар; `customer_*` — звідки FedEx забирає повернення. У відповідь приходить трек і PDF-лейбл.

- **Трекінг і SPOD**
  ```bash
  curl -X POST "http://localhost:8000/tracking?token=super-secret-token" \
    -H "Content-Type: application/json" \
    -d '{"account_id":1,"tracking_number":"1234567890"}'

  curl -X POST "http://localhost:8000/tracking/spod?token=super-secret-token" \
    -H "Content-Type: application/json" \
    -d '{"account_id":1,"tracking_number":"1234567890"}'
  ```
  Перший запит повертає сирі дані FedEx трекінгу, другий — шлях до збереженого PDF підтвердження доставки (`storage/spod/spod_<tracking>.pdf`).

- **Завантажити етикетку**
  ```bash
  curl -L "http://localhost:8000/shipments/1/label?token=super-secret-token" -o label.pdf
  ```

## Примітки
- Запит авторизації виконується на `/oauth/token` (grant_type=client_credentials); отриманий токен автоматично кешується.
- Тарифи беруться з `/rate/v1/rates/quotes`, створення відправки — через `/ship/v1/shipments` із PDF-етикеткою (base64) та збереженням у `storage/labels`.
- Усі дозволені сервіси: FIP, IPE, FIE, RE, PO, FICP, IPF, IEF, REF, RETURNS.
- Поле `price_quote` у відправленнях може бути відсутнім (None), якщо тариф не запитували через `/rates`.
- У FedEx-запитах для створення відправлення тепер передаються обов'язкові поля: поштовий індекс та штат/область одержувача, телефон, `mergeLabelDocOption=LABELS_ONLY`, `labelSpecification.imageType=PDF`; відправники (shipper) зберігаються окремо і підставляються в кожен запит.
- До `requestedShipment.customsClearanceDetail` автоматично додається комерційний інвойс, який формує FedEx, та перелік товарів з описом (quantity/price/weight за бажанням). Якщо не передати `customs_items`, у запит піде базова позиція "General Goods" з вагою відправлення. Для відправлень без митного оформлення передайте `customs_required: 0`, тоді `customsClearanceDetail` не включатиметься в запит.
- Для International Broker Select Option використовуйте `broker_id` + `broker_select_option`; для Third Party Consignee — `third_party_consignee`; для повернень — ендпоїнт `/returns` (код сервісу `RETURNS`).
- Freight-сервіси IPF/IEF/REF підтримуються стандартними запитами `/orders` і `/rates`; у FedEx-запиті автоматично додається `totalWeight`.
- Дані зберігаються у SQLite, тому резервуйте файл `data/app.db` при продакшн-розгортанні.

## Швидкий старт на Windows 11 у Visual Studio Code
1. **Встановіть Python та Git**. Додайте їх у PATH (установник Python має опцію *Add python.exe to PATH*).
2. **Клонуйте репозиторій і відкрийте у VS Code**:
   - Відкрийте Git Bash або PowerShell і виконайте `git clone <repo-url>`.
   - У VS Code оберіть *File → Open Folder* і відкрийте скопійований каталог.
3. **Створіть та активуйте віртуальне середовище** у вбудованому терміналі VS Code (PowerShell):
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate
   pip install -r requirements.txt
   ```
4. **Створіть `.env` (або задайте перемінні в PowerShell)**:
   ```powershell
   echo SERVICE_TOKEN=super-secret-token >> .env
   echo DATABASE_URL=sqlite:///${PWD}/data/app.db >> .env
   echo FEDEX_BASE_URL=https://apis-sandbox.fedex.com >> .env
   mkdir data
   mkdir -Force storage\labels
   mkdir -Force storage\logs
   mkdir -Force storage\spod
   ```
5. **Запустіть сервер у VS Code**:
   - Відкрийте термінал (*Terminal → New Terminal*), переконайтеся, що активоване `.venv` (у підказці має бути `(.venv)`), і виконайте:
     ```powershell
     uvicorn app.main:app --reload
     ```
   - VS Code підсвітить URL у консолі; переходьте за ним у браузері або використовуйте `curl` з `?token=...`.
6. **Налаштуйте форматування/літери переносу** (опційно): у `settings.json` VS Code можна додати `"files.eol": "\n"`, щоб уникнути CRLF у Git.
