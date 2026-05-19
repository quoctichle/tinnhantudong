import os
import subprocess
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import ElementClickInterceptedException

from config_runtime import get_chrome_profile, get_chrome_user_data_dir, get_env, get_service_account_file

# ==== Cấu hình ===#
SHEET_ID = "1m1lIEcbsjl373-ewW9UdA-WpTYOb2LH0po-J0C8Ovik"
SHEET_NAME = "LIST ĐỔI - SIM 交換"
SERVICE_ACCOUNT_FILE = get_service_account_file()
EMAIL = get_env("FB_EMAIL")
PASSWORD = get_env("FB_PASSWORD")
START_ROW = 8
PAID_VALUE = "ĐÃ TT"
SENT_VALUE = "CHƯA REP"
CHROME_USER_DATA_DIR = get_chrome_user_data_dir()
CHROME_PROFILE = get_chrome_profile()

SEND_BUTTON_XPATHS = [
    "//button[@aria-label='Send']",
    "//div[@aria-label='Send message']",
    "//div[@role='button' and @aria-label='Send message']",
    "//span[text()='Send']",
    "//button[contains(@class,'send')]",
]

# ==== Hàm tiện ích ===#
def connect_to_gsheet(sheet_id, sheet_name):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(sheet_id).worksheet(sheet_name)
    return sheet

def _terminate_profile_processes(user_data_dir):
    normalized_dir = os.path.normcase(os.path.abspath(user_data_dir))
    powershell_command = (
        "$target = [System.IO.Path]::GetFullPath('" + normalized_dir.replace("'", "''") + "'); "
        "Get-CimInstance Win32_Process -Filter \"name = 'chrome.exe'\" | "
        "Where-Object { $_.CommandLine -and $_.CommandLine.ToLower().Contains($target.ToLower()) } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", powershell_command],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        pass

def _remove_profile_locks(user_data_dir):
    lock_files = [
        "SingletonLock",
        "SingletonCookie",
        "SingletonSocket",
        os.path.join(profile := CHROME_PROFILE, "SingletonLock"),
        os.path.join(profile, "SingletonCookie"),
        os.path.join(profile, "SingletonSocket"),
    ]
    for relative_path in lock_files:
        lock_path = os.path.join(user_data_dir, relative_path)
        if os.path.exists(lock_path):
            try:
                os.remove(lock_path)
            except OSError:
                pass

def build_driver(user_data_dir: str, profile: str = "Default") -> webdriver.Chrome:
    os.makedirs(user_data_dir, exist_ok=True)
    last_error = None

    for attempt in range(1, 4):
        _terminate_profile_processes(user_data_dir)
        _remove_profile_locks(user_data_dir)

        options = Options()
        options.add_argument(f"--user-data-dir={user_data_dir}")
        options.add_argument(f"--profile-directory={profile}")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--start-maximized")
        options.add_argument("--remote-debugging-port=0")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        try:
            return webdriver.Chrome(options=options)
        except Exception as exc:
            last_error = exc
            time.sleep(attempt)

    raise RuntimeError(
        "Khong mo duoc Chrome voi profile cua tool sau 3 lan thu. "
        f"Hay dong cac cua so Chrome dang dung profile nay roi chay lai. Chi tiet: {last_error}"
    )

def _has_facebook_session(driver: webdriver.Chrome) -> bool:
    try:
        for cookie in driver.get_cookies():
            if cookie.get("name") == "c_user" and cookie.get("value"):
                return True
    except Exception:
        return False
    return False

def _is_login_or_checkpoint(url: str) -> bool:
    lowered = (url or "").lower()
    return "login" in lowered or "checkpoint" in lowered

def _find_first_visible(driver: webdriver.Chrome, locators):
    for by, value in locators:
        try:
            element = driver.find_element(by, value)
            if element.is_displayed():
                return element
        except Exception:
            pass
    return None

def check_logged_in(driver: webdriver.Chrome, fb_phone: str = "", fb_password: str = "") -> None:
    driver.get("https://www.facebook.com/")
    time.sleep(3)

    if _has_facebook_session(driver) and not _is_login_or_checkpoint(driver.current_url):
        print("[OK] Da xac nhan dang nhap Facebook (session cu).")
        return

    if fb_phone and fb_password:
        print("[INFO] Dang tu dong dang nhap Facebook...")
        try:
            wait = WebDriverWait(driver, 20)
            email_field = wait.until(
                lambda d: _find_first_visible(
                    d,
                    [
                        (By.ID, "email"),
                        (By.NAME, "email"),
                    ],
                )
            )
            email_field.clear()
            email_field.send_keys(fb_phone)

            pass_field = wait.until(
                lambda d: _find_first_visible(
                    d,
                    [
                        (By.ID, "pass"),
                        (By.NAME, "pass"),
                    ],
                )
            )
            pass_field.clear()
            pass_field.send_keys(fb_password)

            login_button = _find_first_visible(
                driver,
                [
                    (By.NAME, "login"),
                    (By.XPATH, "//button[@type='submit']"),
                    (By.XPATH, "//input[@type='submit']"),
                ],
            )
            if login_button:
                login_button.click()
            else:
                pass_field.send_keys(Keys.RETURN)

            WebDriverWait(driver, 40).until(
                lambda d: _has_facebook_session(d)
                or "checkpoint" in d.current_url
                or "login" in d.current_url
            )
            time.sleep(2)

            if "checkpoint" in driver.current_url:
                print("[CANH BAO] Facebook yeu cau xac minh bao mat.")
                print("            Vui long xac minh trong cua so Chrome, tool cho toi da 3 phut...")
                WebDriverWait(driver, 180).until(lambda d: _has_facebook_session(d) and "checkpoint" not in d.current_url)
                time.sleep(2)

            if _has_facebook_session(driver):
                print("[OK] Dang nhap Facebook thanh cong.")
                return
            if "login" in driver.current_url:
                print("[CANH BAO] Da thu auto-login nhung Facebook van o trang login (co the sai mat khau hoac bi chan dang nhap tu dong).")
        except Exception as exc:
            print(f"[CANH BAO] Auto-login khong thanh cong: {type(exc).__name__}: {exc!r}")
        print(f"[INFO] URL sau auto-login: {driver.current_url}")

    print("[YEU CAU] Hay dang nhap Facebook trong cua so Chrome vua mo.")
    print("          Tool se tu tiep tuc sau khi dang nhap xong (toi da 5 phut)...")
    try:
        WebDriverWait(driver, 300).until(
            lambda d: _has_facebook_session(d) and not _is_login_or_checkpoint(d.current_url)
        )
        time.sleep(2)
    except Exception as exc:
        raise RuntimeError("Het thoi gian cho dang nhap. Vui long chay lai tool.") from exc
    print("[OK] Da xac nhan dang nhap Facebook.")

def ensure_business_logged_in(driver, target_url, timeout=30):
    driver.get(target_url)
    wait = WebDriverWait(driver, timeout)

    def _login_state_ready(d):
        current_url = d.current_url
        return (
            "business/loginpage" in current_url
            or "/latest/inbox/" in current_url
            or "redirect_session_id=" in current_url
        )

    wait.until(_login_state_ready)
    if "business/loginpage" not in driver.current_url:
        return
    try:
        continue_button = wait.until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    "//*[(@role='button' or self::a or self::button) and .//*[normalize-space()='Continue with Facebook']]",
                )
            )
        )
        continue_button.click()
        wait.until(lambda d: "business/loginpage" not in d.current_url)
    except Exception:
        print("[YÊU CẦU] Meta Business yêu cầu đăng nhập thêm. Hãy hoàn tất trên Chrome, rồi nhấn Enter để tiếp tục.")
        input()
        driver.get(target_url)

def build_message(condition, customer_id, name, product):
    normalized = condition.upper()
    if "ANH" in normalized or "NINJA" in normalized:
        return f"❌ IMPORTANT NOTICE ❌\n\nCustomer code: {customer_id}  {name} {product}\n\nIn order to provide the best service to customers.\nThe network will cancel the old sim at the end of the month.\nChange to a new sim with better speed; more stable;\n\nNote:   No need to return the old sim.\n            We will pay for any current arising costs\n\n✍️ Please provide information to receive the new product;\n1. Name of recipient:\n2. Address of recipient (please send the address on documents: residence card; electricity bill.... for the most accurate):\n3. Delivery Date :\n4. Delivery Time:\n5. Phone number (if any):\n\n Sincerely apologize to you for this inconvenience!"
    if "MYANMA" in normalized:
        return f"❌ အရေးကြီးသောသတိပေးချက် ❌\n\nဖောက်သည်ကုဒ်- {customer_id}  {name} {product}\n\nဖောက်သည်များကို အကောင်းဆုံးဝန်ဆောင်မှုပေးနိုင်ရန်။\nကွန်ရက်သည် လကုန်တွင် ဆင်းမ်ဟောင်းကို ပယ်ဖျက်ပါမည်။\nပိုမိုကောင်းမွန်သော အမြန်နှုန်း၊ ပိုမိုတည်ငြိမ်သော ဆင်းမ်ကတ်အသစ်သို့ ပြောင်းပါ။\n\nမှတ်ချက်- Sim အဟောင်းကို ပြန်ပေးစရာမလိုပါဘူး။\n                လက်ရှိဖြစ်ပေါ်နေသော ကုန်ကျစရိတ်များအတွက် ကျွန်ုပ်တို့ ပေးဆောင်ပါမည်။\n\n✍️ ထုတ်ကုန်အသစ်ရရှိရန် အချက်အလက်များကို ကျေးဇူးပြု၍ ပေးဆောင်ပါ။\n1. လက်ခံသူအမည်-\n2. လက်ခံသူ၏ နေရပ်လိပ်စာ (အတိကျဆုံးအတွက် စာရွက်စာတမ်းများတွင် နေထိုင်ခွင့်ကတ်၊ လျှပ်စစ်မီတာခ....ကို ပေးပို့ပါ)\n3. လက်ခံရရှိသည့်ရက်စွဲ-\n4. လက်ခံရရှိချိန်-\n5. ဖုန်းနံပါတ် (ရှိပါက)\n\n ယခုလို အဆင်မပြေမှုအတွက် အလေးအနက် တောင်းပန်အပ်ပါသည်။"
    if "VIỆT" in normalized or "CDN" in normalized:
        return f"❌ THÔNG BÁO QUAN TRỌNG ❌\n\nMã khách hàng: {customer_id}  {name} {product}\n\nNhằm đem lại dịch vụ tốt nhất tới khách hàng.\nNhà mạng sẽ hủy sim cũ vào cuối tháng.\nĐổi sim mới với tốc độ tốt hơn; ổn định hơn.\n\nLưu ý: Không cần gửi trả sim cũ.\n           Mọi chi phí phát sinh hiện tại; chúng tôi sẽ chi trả\n\n✍️ Quý khách vui lòng cung cấp thông tin để nhận sản phẩm mới;\n1. Tên nhận hàng:\n2. Địa chỉ nhận hàng (vui lòng gửi địa chỉ trên giấy tờ: thẻ lưu trú; hóa đơn điện nước.... để chính xác nhất)\n3. Giờ nhận hàng :\n4. Ngày nhận hàng :\n5. Số điện thoại (nếu có)\n\n Chân thành xin lỗi quý khách vì sự bất tiện này !"
    return ""

def _find_message_box(driver, timeout=15):
    MSG_BOX_XPATHS = [
        "//div[@aria-label='Message']",
        "//div[@aria-placeholder='Aa']",
        "//div[@role='textbox' and contains(@class,'notranslate')]",
        "//div[@contenteditable='true' and @role='textbox']",
        "//div[@role='textbox']",
    ]
    def _any_box(d):
        for xpath in MSG_BOX_XPATHS:
            try:
                el = d.find_element(By.XPATH, xpath)
                if el.is_displayed() and el.is_enabled():
                    return el
            except Exception:
                pass
        return False
    try:
        return WebDriverWait(driver, timeout, poll_frequency=0.5).until(_any_box)
    except Exception as exc:
        raise RuntimeError("Khong tim thay o nhap tin nhan trong Meta inbox") from exc

def _find_send_button(driver, timeout=3):
    def _any_button(d):
        for xpath in SEND_BUTTON_XPATHS:
            try:
                el = d.find_element(By.XPATH, xpath)
                if el.is_displayed() and el.is_enabled():
                    return el
            except Exception:
                pass
        return False
    try:
        return WebDriverWait(driver, timeout, poll_frequency=0.5).until(_any_button)
    except Exception:
        return None

def _dismiss_blocking_popups(driver, timeout=5):
    popup_button_xpaths = [
        "//div[@role='dialog']//button[normalize-space()='OK']",
        "//div[@role='dialog']//button[normalize-space()='Đóng']",
        "//div[@role='dialog']//*[self::button or @role='button'][@aria-label='Close']",
        "//div[@role='dialog']//*[self::button or @role='button']//*[name()='svg' and @aria-label='Close']/ancestor::*[self::button or @role='button'][1]",
        "//div[@role='dialog']//*[self::button or @role='button'][@aria-label='Đóng']",
    ]
    end_time = time.time() + timeout
    while time.time() < end_time:
        clicked = False
        for xpath in popup_button_xpaths:
            try:
                button = driver.find_element(By.XPATH, xpath)
                if button.is_displayed() and button.is_enabled():
                    driver.execute_script("arguments[0].click();", button)
                    time.sleep(0.25)
                    clicked = True
                    break
            except Exception:
                pass
        if not clicked:
            break

def _wait_for_message_cleared(driver, msg_box, timeout=5.0):
    end_time = time.time() + timeout
    while time.time() < end_time:
        current_text = driver.execute_script(
            "return (arguments[0].textContent || arguments[0].innerText || '').trim();",
            msg_box,
        )
        if not current_text:
            return
        time.sleep(0.15)
    raise RuntimeError("Khong xac nhan duoc tin nhan da gui (o nhap van con noi dung)")

def _normalize_message_text(message):
    return (message or "").replace("\r\n", "\n").replace("\r", "\n")

def _get_msg_box_text(driver, msg_box):
    return driver.execute_script(
        "return (arguments[0].textContent || arguments[0].innerText || '').replace(/\\r\\n/g, '\\n').replace(/\\r/g, '\\n');",
        msg_box,
    ) or ""

def _verify_message_inserted(driver, msg_box, message, timeout=3.0):
    expected = _normalize_message_text(message)
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            inserted = _normalize_message_text(_get_msg_box_text(driver, msg_box))
            if inserted == expected:
                return True
        except Exception:
            pass
        time.sleep(0.15)
    return False

def _insert_message_via_js(driver, msg_box, message):
    driver.execute_script(
        """
        const box = arguments[0];
        const text = arguments[1];
        box.focus();
        box.textContent = '';
        const lines = text.split('\\n');
        lines.forEach((line, idx) => {
          if (idx > 0) {
            const br = document.createElement('br');
            box.appendChild(br);
          }
          box.appendChild(document.createTextNode(line));
        });
        box.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: text}));
        """,
        msg_box,
        _normalize_message_text(message),
    )

def _paste_full_message(msg_box, message):
    try:
        import pyperclip

        pyperclip.copy(_normalize_message_text(message))
        msg_box.send_keys(Keys.CONTROL, "v")
        return True
    except Exception:
        return False

def _type_message(driver, msg_box, message):
    try:
        msg_box.click()
    except ElementClickInterceptedException:
        _dismiss_blocking_popups(driver, timeout=3)
        driver.execute_script("arguments[0].click();", msg_box)
    time.sleep(0.1)
    driver.execute_script("arguments[0].focus();", msg_box)
    time.sleep(0.05)

    pasted = _paste_full_message(msg_box, message)
    if not pasted or not _verify_message_inserted(driver, msg_box, message, timeout=2.5):
        _insert_message_via_js(driver, msg_box, message)
        if not _verify_message_inserted(driver, msg_box, message, timeout=2.5):
            raise RuntimeError("Khong chen duoc day du noi dung tin nhan truoc khi gui")

    send_button = _find_send_button(driver, timeout=1)
    if send_button:
        try:
            send_button.click()
        except ElementClickInterceptedException:
            _dismiss_blocking_popups(driver, timeout=3)
            driver.execute_script("arguments[0].click();", send_button)
    else:
        ActionChains(driver).send_keys(Keys.RETURN).perform()

    _wait_for_message_cleared(driver, msg_box, timeout=5.0)

def send_message(driver, meta_link, message):
    ensure_business_logged_in(driver, meta_link.strip())
    _dismiss_blocking_popups(driver, timeout=4)
    msg_box = _find_message_box(driver, timeout=15)
    _type_message(driver, msg_box, message)

def save_debug_artifacts(driver, row_number):
    base_dir = os.path.join(os.path.dirname(__file__), "debug-artifacts")
    os.makedirs(base_dir, exist_ok=True)
    screenshot_path = os.path.join(base_dir, f"row-{row_number}.png")
    html_path = os.path.join(base_dir, f"row-{row_number}.html")
    driver.save_screenshot(screenshot_path)
    with open(html_path, "w", encoding="utf-8") as output_file:
        output_file.write(driver.page_source)
    return screenshot_path, html_path

def main():
    sheet = connect_to_gsheet(SHEET_ID, SHEET_NAME)
    data = sheet.get_all_values()
    driver = build_driver(CHROME_USER_DATA_DIR, CHROME_PROFILE)
    check_logged_in(driver, EMAIL, PASSWORD)
    try:
        for i, row in enumerate(data[START_ROW - 1:], start=START_ROW):
            padded = row + [""] * 37
            link = padded[7].strip()  # H
            condition_s = padded[18].strip()  # S
            status_aj = padded[35].strip()  # AJ
            status_ak = padded[36].strip()  # AK
            customer_id = padded[4].strip()  # E
            name = padded[11].strip()  # L
            product = padded[12].strip()  # M
            # Chỉ gửi nếu AJ == 'ĐÃ TT' và AK là rỗng (sau strip)
            if status_aj.upper() == PAID_VALUE and not status_ak.strip():
                message = build_message(condition_s, customer_id, name, product)
                if not link or not message:
                    continue
                print(f"Gửi dòng {i}: {customer_id} | {link}")
                try:
                    send_message(driver, link, message)
                    sheet.update_cell(i, 37, SENT_VALUE)
                    print(f"  OK -> cập nhật AK={SENT_VALUE}")
                except Exception as exc:
                    screenshot_path, html_path = save_debug_artifacts(driver, i)
                    print(f"  Lỗi gửi dòng {i}: {type(exc).__name__}: {exc!r}")
                    print(f"  URL hiện tại: {driver.current_url}")
                    print(f"  Screenshot: {screenshot_path}")
                    print(f"  HTML: {html_path}")
            else:
                continue
    finally:
        driver.quit()

if __name__ == "__main__":
    main()