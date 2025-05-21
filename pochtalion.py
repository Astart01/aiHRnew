import imaplib
import email
from email.header import decode_header
import os
from dotenv import load_dotenv

def download_pdfs():
    """
    Загружает PDF-файлы с почты и сохраняет их в папку resume.
    
    Returns:
        list: Список путей к загруженным файлам
    """
    # Указываем путь к файлу с переменными окружения
    # Если файл находится в другом месте, измените путь
    env_path = "pochtalion.env"
    if os.path.exists(env_path):
        load_dotenv(dotenv_path=env_path, override=True)
    else:
        load_dotenv(override=True)  # Пробуем загрузить из .env по умолчанию

    # Получаем данные для подключения из переменных окружения
    EMAIL = os.getenv("EMAIL")
    PASSWORD = os.getenv("EMAIL_PASSWORD")
    IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.yandex.com")
    
    # Проверяем, что переменные с логином и паролем загружены
    if not EMAIL or not PASSWORD:
        raise ValueError("EMAIL или PASSWORD не указаны в переменных окружения")
    
    # Указываем папку, куда будем сохранять все вложения .pdf
    SAVE_DIR = "resume"
    
    # Создаём директорию для сохранения PDF-файлов, если её ещё нет
    os.makedirs(SAVE_DIR, exist_ok=True)
    
    # Список путей к загруженным файлам
    downloaded_files = []
    
    try:
        # Подключаемся к почтовому серверу через защищенное соединение
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        
        # Входим в почтовый ящик
        mail.login(EMAIL, PASSWORD)
        
        # Выбираем папку "Входящие"
        mail.select("inbox")
        
        # Ищем все непрочитанные письма
        status, messages = mail.search(None, '(UNSEEN)')
        
        # Получаем список ID писем (байты), разбиваем в список
        email_ids = messages[0].split()
        
        # Обрабатываем каждое письмо из найденных
        for email_id in email_ids:
            # Получаем сырое содержимое письма по ID
            res, msg_data = mail.fetch(email_id, "(RFC822)")
            raw_email = msg_data[0][1]
            
            # Преобразуем байты в email-объект
            message = email.message_from_bytes(raw_email)
            
            # Проходимся по частям письма (тело, вложения и т.д.)
            for part in message.walk():
                # Пропускаем контейнерные части (многочастные письма)
                if part.get_content_maintype() == 'multipart':
                    continue
                # Пропускаем части, у которых нет заголовка Content-Disposition (чаще всего это тело письма)
                if part.get('Content-Disposition') is None:
                    continue
                
                # Получаем имя вложенного файла
                filename = part.get_filename()
                
                if filename:
                    # Декодируем имя файла (может быть в base64 или других кодировках)
                    decoded_filename, encoding = decode_header(filename)[0]
                    if isinstance(decoded_filename, bytes):
                        decoded_filename = decoded_filename.decode(encoding or "utf-8")
                    
                    # Проверяем, что файл действительно PDF
                    if decoded_filename.lower().endswith(".pdf"):
                        # Формируем путь, по которому сохраним файл
                        filepath = os.path.join(SAVE_DIR, decoded_filename)
                        
                        # Сохраняем файл в указанную папку
                        with open(filepath, "wb") as f:
                            f.write(part.get_payload(decode=True))
                        
                        # Добавляем путь к файлу в список загруженных
                        downloaded_files.append(filepath)
                        
                        print(f"Сохранен файл: {filepath}")
        
        # Завершаем сессию и выходим из почтового ящика
        mail.logout()
        
    except Exception as e:
        print(f"Ошибка при загрузке резюме с почты: {e}")
    
    return downloaded_files

if __name__ == "__main__":
    # Если файл запущен напрямую, вызываем функцию
    downloaded_files = download_pdfs()
    print(f"Загружено {len(downloaded_files)} файлов")