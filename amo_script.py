import csv
import requests
import time
import json
from typing import List, Dict, Optional

class AmoCRMClient:
    def __init__(self, csv_path):
        try:
            with open('credentials.json', 'r') as file:
                creds = json.load(file)
        except FileNotFoundError:
            raise Exception("Файл credentials.json не найден")
        self.client_id = creds.get('client_id')
        self.client_secret = creds.get('client_secret')
        self.redirect_uri = creds.get('redirect_uri')
        self.subdomain = creds.get('subdomain')
        self.access_token = creds.get('access_token')
        self.refresh_token = creds.get('refresh_token')
        required_fields = ['subdomain', 'access_token']
        for field in required_fields:
            if not getattr(self, field):
                raise ValueError(f"Отсутствует обязательное поле в конфиге: {field}")
        self.csv_path = csv_path
        self.custom_fields = {
            "desired_position": None,
            "city": None,
            "age": None,
            "salary": None,
            "comment": None,
            "probability": None
        }
        self.deal_status_id = self.get_new_deal_status_id()
        self.load_custom_field_ids()

    def _check_token(self):
        return True

    def _make_request(self, method: str, url: str, **kwargs) -> requests.Response:
        max_retries = 3
        retry_delay = 5
        for attempt in range(max_retries):
            try:
                response = requests.request(method, url, **kwargs)
                if response.status_code == 401:
                    if self._check_token():
                        kwargs['headers']['Authorization'] = f"Bearer {self.access_token}"
                        continue
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', retry_delay))
                    print(f"Достигнут лимит запросов. Ожидание {retry_after} сек...")
                    time.sleep(retry_after)
                    continue
                return response
            except requests.exceptions.RequestException as e:
                print(f"Ошибка сети (попытка {attempt+1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
        raise Exception("Не удалось выполнить запрос после нескольких попыток")

    def load_custom_field_ids(self):
        if not self._check_token():
            raise Exception("Токен недействителен")
        url = f"https://{self.subdomain}.amocrm.ru/api/v4/contacts/custom_fields"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            response = self._make_request("GET", url, headers=headers)
            if response.status_code == 200:
                try:
                    data = response.json()
                    fields = data.get('_embedded', {}).get('custom_fields', [])
                    print("\nНайденные кастомные поля:")
                    for field in fields:
                        field_name = field['name'].lower()
                        field_id = field['id']
                        print(f"- {field['name']} (ID: {field_id})")
                        if field_name == 'желаемая должность':
                            self.custom_fields["desired_position"] = field_id
                        elif field_name == 'город':
                            self.custom_fields["city"] = field_id
                        elif field_name == 'возраст':
                            self.custom_fields["age"] = field_id
                        elif field_name == 'зарплата':
                            self.custom_fields["salary"] = field_id
                        elif field_name == 'комментарий':
                            self.custom_fields["comment"] = field_id
                        elif field_name == 'вероятность класса 1':
                            self.custom_fields["probability"] = field_id
                    missing_fields = [k for k, v in self.custom_fields.items() if v is None]
                    if missing_fields:
                        print("\nВНИМАНИЕ: Не найдены следующие кастомные поля:")
                        print(", ".join(missing_fields))
                        print("Рекомендуется создать их в amoCRM → Настройки → Контакты → Поля")
                except (KeyError, json.JSONDecodeError) as e:
                    print(f"Ошибка разбора ответа: {e}")
            else:
                print(f"Ошибка получения кастомных полей: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"Ошибка при загрузке кастомных полей: {e}")

    def get_new_deal_status_id(self) -> Optional[int]:
        if not self._check_token():
            return None
        url = f"https://{self.subdomain}.amocrm.ru/api/v4/leads/pipelines"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            response = self._make_request("GET", url, headers=headers)
            if response.status_code == 200:
                try:
                    pipelines = response.json().get('_embedded', {}).get('pipelines', [])
                    for pipeline in pipelines:
                        statuses = pipeline.get('_embedded', {}).get('statuses', [])
                        for status in statuses:
                            if status['name'].lower() == 'первичный контакт':
                                print(f"\nНайден статус 'Первичный контакт' с ID: {status['id']}")
                                return status['id']
                    print("Статус 'Первичный контакт' не найден в воронках")
                    return None
                except (KeyError, json.JSONDecodeError) as e:
                    print(f"Ошибка структуры ответа: {e}")
                    return None
            else:
                print(f"Ошибка получения статуса: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"Ошибка при получении статусов: {e}")
            return None

    def create_contact(self, name: str, phone: str, data: Dict) -> Optional[int]:
        if not self._check_token():
            return None
        url = f"https://{self.subdomain}.amocrm.ru/api/v4/contacts"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        custom_fields_values = []
        if phone:
            custom_fields_values.append({
                "field_code": "PHONE",
                "values": [{"value": phone, "enum_code": "WORK"}]
            })
        else:
            print(f"⚠️ Пропущен контакт '{name}': отсутствует телефон")
            return None
        if self.custom_fields["desired_position"] and data.get("desired_position"):
            custom_fields_values.append({
                "field_id": self.custom_fields["desired_position"],
                "values": [{"value": data["desired_position"]}]
            })
        if self.custom_fields["city"] and data.get("city"):
            custom_fields_values.append({
                "field_id": self.custom_fields["city"],
                "values": [{"value": data["city"]}]
            })
        if self.custom_fields["age"] and data.get("age"):
            try:
                age_str = data["age"].strip() if data["age"] else ""
                if age_str and age_str != "-":
                    age = int(age_str.replace(" ", "").replace(",", "").replace(".", ""))
                    custom_fields_values.append({
                        "field_id": self.custom_fields["age"],
                        "values": [{"value": age}]
                    })
            except ValueError:
                print(f"⚠️ Некорректный возраст для контакта '{name}': {data['age']}")
        if self.custom_fields["salary"] and data.get("salary"):
            salary_str = data["salary"].strip() if data["salary"] else ""
            if salary_str and salary_str != "-":
                custom_fields_values.append({
                    "field_id": self.custom_fields["salary"],
                    "values": [{"value": salary_str}]
                })
            else:
                print(f"⚠️ Пропущено значение зарплаты для '{name}'")
        if self.custom_fields["comment"] and data.get("comment"):
            custom_fields_values.append({
                "field_id": self.custom_fields["comment"],
                "values": [{"value": data["comment"]}]
            })
        if self.custom_fields["probability"] and data.get("probability"):
            try:
                prob_str = data["probability"].strip() if data["probability"] else ""
                if prob_str and prob_str != "-":
                    prob = float(prob_str.replace(" ", "").replace(",", "."))
                    custom_fields_values.append({
                        "field_id": self.custom_fields["probability"],
                        "values": [{"value": prob}]
                    })
            except ValueError:
                print(f"⚠️ Некорректная вероятность для контакта '{name}': {data['probability']}")
        payload = [{
            "name": name,
            "custom_fields_values": custom_fields_values
        }]
        try:
            print(f"\nСоздание контакта: {name}")
            print(f"Отправляемые данные: {json.dumps(payload, ensure_ascii=False, indent=2)}")
            response = self._make_request("POST", url, json=payload, headers=headers)
            if response.status_code == 200:
                try:
                    contact_id = response.json()['_embedded']['contacts'][0]['id']
                    print(f"✅ Контакт '{name}' успешно создан с ID: {contact_id}")
                    return contact_id
                except (KeyError, json.JSONDecodeError) as e:
                    print(f"Ошибка разбора ответа: {e}")
                    print(f"Полный ответ: {response.text}")
                    return None
            else:
                print(f"❌ Ошибка создания контакта '{name}': {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"Ошибка запроса: {e}")
            return None

    def create_deal(self, contact_id: int, name: str):
        if not self.deal_status_id:
            print("❌ Статус сделки не найден")
            return
        url = f"https://{self.subdomain}.amocrm.ru/api/v4/leads"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        payload = [{
            "name": f"Сделка с {name}",
            "price": 0,
            "status_id": self.deal_status_id,
            "_embedded": {"contacts": [{"id": contact_id}]}
        }]
        try:
            print(f"\nСоздание сделки для {name}")
            response = self._make_request("POST", url, json=payload, headers=headers)
            if response.status_code == 200:
                print(f"✅ Сделка '{payload[0]['name']}' успешно создана")
            else:
                print(f"❌ Ошибка создания сделки '{payload[0]['name']}': {response.status_code} - {response.text}")
        except Exception as e:
            print(f"Ошибка запроса: {e}")

    def process_csv(self):
        try:
            with open(self.csv_path, newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                required_headers = ['Файл', 'Телефон']
                missing_headers = [h for h in required_headers if h not in reader.fieldnames]
                if missing_headers:
                    raise ValueError(f"Отсутствуют обязательные колонки в CSV: {', '.join(missing_headers)}")
                print(f"\nНайдены колонки в CSV: {', '.join(reader.fieldnames)}")
                for row in reader:
                    name = row['Файл'].strip() if row.get('Файл') else ''
                    phone = row['Телефон'].strip() if row.get('Телефон') else ''
                    if not name or not phone:
                        print(f"⚠️ Пропущен контакт: отсутствует имя или телефон ({name}, {phone})")
                        continue
                    data = {
                        "desired_position": row.get('Желаемая должность', '').strip(),
                        "city": row.get('Город', '').strip(),
                        "age": row.get('Возраст', '').strip(),
                        "salary": row.get('Зарплата', '').strip(),
                        "comment": row.get('Комментарий', '').strip(),
                        "probability": row.get('Вероятность класса 1', '').strip()
                    }
                    print(f"\n{'='*50}\nОбработка контакта: {name}")
                    contact_id = self.create_contact(name=name, phone=phone, data=data)
                    if contact_id:
                        self.create_deal(contact_id=contact_id, name=name)
                    time.sleep(6)
        except FileNotFoundError:
            print(f"❌ Файл {self.csv_path} не найден")
        except csv.Error as e:
            print(f"❌ Ошибка чтения CSV: {e}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Использование: python amo_script.py <csv_path>")
        sys.exit(1)
    try:
        client = AmoCRMClient(sys.argv[1])
        client.process_csv()
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")