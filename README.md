"""
Ourbit Self-Bot
===============

مانیتور لحظه‌ای یک کانال تلگرام برای پیام‌های **Ourbit New Listing**
(اسپات و فیوچرز) و انتشار نسخه فارسی‌شده در کانال مقصد، با اکانت شخصی شما.

این برنامه یک **user client** است (Telethon روی اکانت خودتان)، نه Bot API.


1. دریافت API ID و API Hash
---------------------------

1. وارد [https://my.telegram.org](https://my.telegram.org) شوید.
2. با شماره تلفن اکانت تلگرام خود login کنید.
3. بخش **API development tools** را باز کنید.
4. یک اپلیکیشن بسازید و این دو مقدار را بردارید:
   - `API_ID` (عدد)
   - `API_HASH` (رشته)


2 و 3. ساخت فایل `.env`
-----------------------

```bash
copy .env.example .env
```

روی لینوکس/مک:

```bash
cp .env.example .env
```

سپس `.env` را پر کنید:

```env
API_ID=123456
API_HASH=your_api_hash
PHONE_NUMBER=+98912xxxxxxx
SOURCE_CHANNEL=@source_channel
DESTINATION_CHANNEL=@destination_channel
```

`SOURCE_CHANNEL` و `DESTINATION_CHANNEL` می‌توانند یکی از این‌ها باشند:

- یوزرنیم کانال مثل `@ourbit_announcements`
- آیدی عددی مثل `-1001234567890`

اکانت شما باید عضو هر دو کانال باشد و برای کانال مقصد دسترسی ارسال پیام داشته باشد.


4. نصب Dependencies
-------------------

پایتون 3.10 یا بالاتر لازم است.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

لینوکس/مک:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```


5. اجرای اولیه
--------------

از ریشه پروژه:

```bash
python -m ourbit_selfbot
```

یا:

```bash
python run.py
```


6 و 7. Login و ساخت Session
---------------------------

در اولین اجرا Telethon کد ورود تلگرام را می‌پرسد.

1. کد را از تلگرام وارد کنید.
2. اگر Two-Factor Authentication فعال است، رمز را وارد کنید
   (یا `TELEGRAM_2FA_PASSWORD` را در `.env` بگذارید).
3. فایل Session ساخته می‌شود؛ پیش‌فرض:

```text
ourbit_session.session
```

اجراهای بعدی از همین Session استفاده می‌کنند و دوباره login نمی‌خواهند.


8. کانال مبدأ (Source)
----------------------

فقط کانالی که در `SOURCE_CHANNEL` آمده مانیتور می‌شود.

Event Listener خود Telethon استفاده می‌شود؛ polling دستی وجود ندارد.

فقط پیام‌هایی که ساختار **Ourbit New Listing** دارند پردازش می‌شوند
(اسپات یا Perpetual Futures). پیام‌های معمولی، خبری، یا فقط دارای `$SYMBOL`
نادیده گرفته می‌شوند.


9. کانال مقصد (Destination)
---------------------------

خروجی فارسی با قالب ثابت اسپات/فیوچرز به `DESTINATION_CHANNEL` ارسال می‌شود.

- اگر پیام مبدأ عکس داشته باشد، **همان عکس** با Caption جدید فرستاده می‌شود.
- اگر عکس نداشته باشد، فقط متن ارسال می‌شود.
- لینک مقاله Ourbit از خود پیام مبدأ استخراج می‌شود و hardcode نیست.


10. اجرای دائمی
---------------

ربات باید روشن بماند تا پیام‌های جدید را لحظه‌ای بگیرد.

ویندوز (PowerShell):

```powershell
python -m ourbit_selfbot
```

برای اجرای پس‌زمینه می‌توانید از Task Scheduler، nssm، یا یک terminal جدا استفاده کنید.

اگر اتصال قطع شود، برنامه با فاصلهٔ افزایشی دوباره وصل می‌شود.


11. امنیت Session و `.env`
--------------------------

فایل‌های زیر **دسترسی کامل به اکانت تلگرام شما** می‌دهند و نباید اشتراک
گذاشته شوند یا وارد Git شوند:

- `.env`
- `*.session`
- `*.session-journal`

`.gitignore` همین موارد را (به‌علاوه `bot.db`) نادیده می‌گیرد.

اگر Session لو رفت، فوراً از تلگرام تمام Sessionهای فعال را Terminate کنید
و Session را از نو بسازید.


ترجمه Description
-----------------

فقط توضیح Spot ترجمه می‌شود. فیوچرز ترجمه متنی ندارد.

پیش‌فرض **Groq** است (AI رایگان، بدون هزینه):

1. یک حساب در [https://console.groq.com](https://console.groq.com) بسازید (کارت بانکی نمی‌خواهد).
2. API Key بگیرید و در `.env` بگذارید:

```env
GROQ_API_KEY=gsk_...
```

اگر Groq در دسترس نباشد، Google Translate و بعد MyMemory به‌عنوان پشتیبان استفاده می‌شوند.
اگر آن‌ها هم شکست بخورند، متن انگلیسی می‌ماند و برنامه crash نمی‌کند.

نام توکن، `$SYMBOL`، `USDT`، `Ourbit` و برندهایی مثل `OpenRouter` ترجمه نمی‌شوند.

برای خاموش کردن ترجمه:

```env
TRANSLATOR=off
```


تست‌ها
------

```bash
python -m pytest -q
```

پوشش می‌دهد: اسپات FLORK/ORBIO، فیوچرز AIINU، پیام غیرلیستینگ،
تبدیل UTC→تهران→جلالی، اعداد فارسی، duplicate، و رفتار عکس/متن.


نکته معماری
-----------

خروجی با **HTML parse mode** تلگرام ساخته می‌شود، نه Markdown.
دلیل: لینک‌های رسمی (اینستاگرام و X) شامل `_` و query string هستند و
Markdown تلگرام را خراب می‌کنند. ظاهر نهایی (bold، blockquote، لینک، هشتگ)
همان قالب درخواستی است.

اگر پیام مبدأ بعداً edit شود و قبلاً به مقصد ارسال شده باشد، پیام مقصد هم
به‌روزرسانی می‌شود (`source_message_id` و `destination_message_id` در SQLite).
"""
"# ourbitlistingtranslate" 
