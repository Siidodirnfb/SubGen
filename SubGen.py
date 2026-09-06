import asyncio
import random
import string
import time
import json
import requests
import telebot
from playwright.async_api import async_playwright
from openai import OpenAI

BOT_TOKEN = "8837057013:AAHRuegBTBR71mTspn3h58rV9ETz25TUjQ4"
MAIL_TM_API = "https://api.mail.tm"
GROQ_API_KEY = "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"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
COOLDOWN = 60
last_run = 0

bot = telebot.TeleBot(BOT_TOKEN)
client = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)

def get_domains():
    r = requests.get(f"{MAIL_TM_API}/domains")
    return [d["domain"] for d in r.json().get("hydra:member", [])] if r.ok else []

def create_email(domain):
    pwd = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    addr = f"tmp_{random.randint(1000,9999)}@{domain}"
    r = requests.post(f"{MAIL_TM_API}/accounts", json={"address": addr, "password": pwd})
    if r.status_code != 201:
        return None, None, None
    t = requests.post(f"{MAIL_TM_API}/token", json={"address": addr, "password": pwd})
    return addr, pwd, t.json().get("token") if t.ok else None

def random_name():
    return f"{random.choice(['Иван','Петр','Сергей','Алексей','Дмитрий'])} {random.choice(['Иванов','Петров','Сидоров'])}"

@bot.message_handler(commands=['create'])
def handle_create(msg):
    global last_run
    now = time.time()
    if now - last_run < COOLDOWN:
        bot.reply_to(msg, f"Подождите {int(COOLDOWN - (now - last_run))} сек.")
        return
    bot.reply_to(msg, "Запускаю процесс...")
    domains = get_domains()
    if not domains:
        bot.reply_to(msg, "Ошибка получения доменов")
        return
    email, pwd, token = create_email(domains[0])
    if not email:
        bot.reply_to(msg, "Ошибка создания почты")
        return
    bot.send_message(msg.chat.id, f"Создана почта: {email}")
    try:
        result = asyncio.run(run_flow(msg.chat.id, email))
        bot.send_message(msg.chat.id, f"Результат: {result}")
        last_run = time.time()
    except Exception as e:
        bot.send_message(msg.chat.id, f"Ошибка: {str(e)}")

async def run_flow(chat_id, email):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--incognito", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        await page.goto("https://power-vps.pro/free-trial/")
        await page.wait_for_load_state("networkidle")

        btn = await page.query_selector("a[data-trial-email-modal]")
        if not btn:
            btn = await page.query_selector("div[data-role='form.button.1']")
        if not btn:
            raise Exception("Кнопка не найдена")
        await btn.click()
        await page.wait_for_timeout(3000)

        # Проверяем iframe
        iframe = await page.query_selector("iframe")
        if iframe:
            frame = await iframe.content_frame()
            if frame:
                page = frame

        # Принудительно показываем все скрытые поля
        await page.evaluate("""() => {
            document.querySelectorAll('input').forEach(el => el.style.display = 'block');
            document.querySelectorAll('input').forEach(el => el.style.visibility = 'visible');
            document.querySelectorAll('input').forEach(el => el.style.opacity = '1');
        }""")

        # Ждём появления полей
        try:
            await page.wait_for_selector("input", state="visible", timeout=15000)
        except:
            pass

        # Ищем поля
        name_input = await page.query_selector("input[name='name']")
        if not name_input:
            name_input = await page.query_selector("input[placeholder*='имя']")
        if not name_input:
            name_input = await page.query_selector("input[placeholder*='Name']")
        if not name_input:
            name_input = await page.query_selector("input[type='text']")

        email_input = await page.query_selector("input[name='email']")
        if not email_input:
            email_input = await page.query_selector("input[type='email']")
        if not email_input:
            email_input = await page.query_selector("input[placeholder*='email']")

        # Если не нашли — берём все инпуты и назначаем по порядку
        if not name_input or not email_input:
            inputs = await page.query_selector_all("input")
            visible_inputs = []
            for inp in inputs:
                is_visible = await inp.is_visible()
                if is_visible:
                    visible_inputs.append(inp)
            if len(visible_inputs) >= 2:
                name_input = visible_inputs[0]
                email_input = visible_inputs[1]

        if not name_input or not email_input:
            raise Exception("Поля не найдены")

        await name_input.fill(random_name())
        await email_input.fill(email)

        submit = await page.query_selector("button[type='submit']")
        if not submit:
            submit = await page.query_selector("button:has-text('Получить VPN доступ')")
        if submit:
            await submit.click()
        else:
            await page.keyboard.press("Enter")

        await page.wait_for_timeout(5000)
        current_url = page.url
        if "power-vps.pro" in current_url:
            for _ in range(10):
                await page.wait_for_timeout(1000)
                new_url = page.url
                if new_url != current_url:
                    current_url = new_url
                    break
        await browser.close()
        return current_url

if __name__ == "__main__":
    print("Бот запущен")
    bot.infinity_polling()
