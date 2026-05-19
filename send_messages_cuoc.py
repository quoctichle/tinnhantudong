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
SHEET_ID = "1Blkt-CDZMOTYljomHNNY4fO7ol6m2QHJD4jm8Qb9eLU"
SHEET_NAME = None
SERVICE_ACCOUNT_FILE = get_service_account_file()
EMAIL = get_env("FB_EMAIL")
PASSWORD = get_env("FB_PASSWORD")
START_ROW = 4
IMAGE_PATH = os.path.join(os.path.dirname(__file__), "cuoc.jpg")
IMAGE_PASTE_SETTLE_SECONDS = 0.08
IMAGE_PREVIEW_WAIT_SECONDS = 0.6
IMAGE_PREVIEW_FALLBACK_SECONDS = 0.05
CHROME_USER_DATA_DIR = get_chrome_user_data_dir()
CHROME_PROFILE = get_chrome_profile()

SEND_BUTTON_XPATHS = [
    "//button[@aria-label='Send']",
    "//div[@aria-label='Send message']",
    "//div[@role='button' and @aria-label='Send message']",
    "//button[normalize-space()='Gửi']",
    "//div[@role='button' and normalize-space()='Gửi']",
    "//*[self::button or @role='button'][.//span[normalize-space()='Gửi']]",
    "//button[contains(@aria-label,'Gửi')]",
    "//div[contains(@aria-label,'Gửi') and @role='button']",
    "//button[contains(@title,'Send') or contains(@title,'Gửi')]",
    "//*[@role='button' and (contains(@aria-label,'Send') or contains(@aria-label,'Gửi'))]",
    "//span[text()='Send']",
    "//button[contains(@class,'send')]",
]

# ==== Hàm tiện ích ===#
def connect_to_gsheet(sheet_id, sheet_name):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(sheet_id)
    if sheet_name:
        return spreadsheet.worksheet(sheet_name)

    # Auto-pick the worksheet that has the most sendable rows for this bot.
    best_sheet = None
    best_score = -1
    for ws in spreadsheet.worksheets():
        try:
            values = ws.get_all_values()
        except Exception:
            continue

        score = 0
        for row in values[max(START_ROW - 1, 0):]:
            padded = row + [""] * 22
            name = padded[3].strip()  # D
            link = padded[5].strip()  # F
            if name and link:
                score += 1

        if score > best_score:
            best_score = score
            best_sheet = ws

    if best_sheet is None:
        return spreadsheet.get_worksheet(0)

    print(f"[INFO] Da chon sheet: {best_sheet.title} (so dong hop le: {best_score})")
    return best_sheet

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

def build_message(customer_id, name, product, phone_number, amount_due, payment_code):
    next_month = (time.localtime().tm_mon % 12) + 1
    return (
        f"Xin chào {name} . Cước tháng {next_month} của quý khách là :\n"
        f"{customer_id} {name} {product} {phone_number} {amount_due}\n"
        f"Mã đóng cước: {payment_code}\n\n"
        "⏰⏰ Hạn đóng cước hàng tháng là ngày 23.\n"
        "📸 Xin vui lòng chụp ảnh hoá đơn kèm ID sau đó gửi chúng tôi để xác nhận thanh toán.\n"
        "⏰⏰Cắt mạng tạm thời: Ngày 24.\n"
        "📌 Sẽ cắt mạng tự động nếu quý khách chưa thanh toán cước.\n"
        "⏳Thời gian mở lại: 1-7 ngày sau khi đóng cước. Đối với các gói data không giới hạn, 300GB mở mạng sẽ mất từ 1 đến 2 tuần.\n"
        "☘️Chúng tôi chỉ có một tài khoản ngân hàng duy nhất là: \" PHAM DINH THUONG\", tất cả các tài khoản khác là giả mạo, vui lòng không thanh toán và thông báo lại cho chúng tôi.\n"
        "Hướng dẫn thanh toán:\n"
        "https://www.youtube.com/watch?v=Qxt6XWh99Pg&t=32s"
    )

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

def _click_send_near_msg_box(driver, msg_box):
    script = """
    const box = arguments[0];
    const root = box.closest('[role="main"]') || document;
    const boxRect = box.getBoundingClientRect();
    const candidates = root.querySelectorAll(
      'button,[role="button"],div[role="button"],span[role="button"]'
    );
    const keys = ['send', 'send message', 'gui', 'g\u1eedi'];
    let best = null;
    let bestScore = Number.POSITIVE_INFINITY;
    for (const el of candidates) {
      const label = ((el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('title') || '') + ' ' + (el.textContent || '')).toLowerCase();
      if (!keys.some(k => label.includes(k))) continue;
      const rect = el.getBoundingClientRect();
      if (rect.width < 8 || rect.height < 8) continue;
      // Prefer send control nearest bottom-right side of composer
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const dx = Math.abs(cx - (boxRect.right + 16));
      const dy = Math.abs(cy - (boxRect.bottom - 8));
      const score = dx + dy * 2;
      if (score < bestScore) {
        bestScore = score;
        best = el;
      }
    }
    if (best) {
      best.click();
      return true;
    }
    return false;
    """
    try:
        return bool(driver.execute_script(script, msg_box))
    except Exception:
        return False

def _composer_has_pending_content(driver, msg_box):
    script = """
    const box = arguments[0];
    const container = box.closest('form') || box.parentElement || box;
    const text = ((box.textContent || box.innerText || '').trim());
    const hasPreview = !!container.querySelector(
      "img[src^='blob:'], [aria-label*='Remove'], [aria-label*='Xóa'], [data-testid*='attachment'], [data-testid*='composer_attachment']"
    );
    return text.length > 0 || hasPreview;
    """
    try:
        return bool(driver.execute_script(script, msg_box))
    except Exception:
        # If cannot inspect composer, assume still pending to avoid false OK
        return True

def _send_with_retries(driver, msg_box):
    attempts = []

    def _attempt_send(click_fn):
        try:
            click_fn()
        except Exception:
            return False
        # Very short settle and quick polling to avoid long waits on each attempt
        end_time = time.time() + 0.45
        while time.time() < end_time:
            if not _composer_has_pending_content(driver, msg_box):
                return True
            time.sleep(0.06)
        return False

    # 1) Try standard send button locators (normal click then JS click)
    btn = _find_send_button(driver, timeout=1.5)
    if btn:
        attempts.append(lambda: btn.click())
        attempts.append(lambda: driver.execute_script("arguments[0].click();", btn))

    # 2) Try JS click around composer region
    attempts.append(lambda: (_click_send_near_msg_box(driver, msg_box) or (_ for _ in ()).throw(RuntimeError("send-near-failed"))))

    # 3) Last attempt: find exact text button near composer and click via JS
    try:
        exact_send = driver.find_elements(
            By.XPATH,
            "//button[normalize-space()='Gửi'] | //div[@role='button' and normalize-space()='Gửi'] | //*[self::button or @role='button'][.//span[normalize-space()='Gửi']]",
        )
        for element in exact_send:
            if element.is_displayed() and element.is_enabled():
                attempts.append(lambda el=element: el.click())
                attempts.append(lambda el=element: driver.execute_script("arguments[0].click();", el))
    except Exception:
        pass

    for click_fn in attempts:
        if _attempt_send(click_fn):
            return True

    return False

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
        if not _composer_has_pending_content(driver, msg_box):
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
    # Khong phu thuoc pyperclip; de fallback JS chen noi dung cho on dinh
    return False

def _paste_image_to_message(driver, msg_box, image_path, timeout=IMAGE_PREVIEW_WAIT_SECONDS):
    """Copy image to clipboard and paste into message box, wait briefly for preview."""
    if not os.path.exists(image_path):
        return False
    
    try:
        absolute_path = os.path.abspath(image_path)
        ps_command = f"""
        [System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms') | Out-Null
        [System.Reflection.Assembly]::LoadWithPartialName('System.Drawing') | Out-Null
        $img = [System.Drawing.Image]::FromFile('{absolute_path}')
        [System.Windows.Forms.Clipboard]::SetImage($img)
        """
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_command],
            check=False,
            capture_output=True,
            timeout=10,
        )
        time.sleep(0.05)
        
        try:
            msg_box.click()
            driver.execute_script("arguments[0].focus();", msg_box)
        except Exception:
            pass

        # Paste image using Ctrl+V directly on composer
        msg_box.send_keys(Keys.CONTROL, "v")
        time.sleep(IMAGE_PASTE_SETTLE_SECONDS)
        
        # Wait for image to be added (check for image elements in the composer area)
        def _image_loaded(d):
            try:
                # Look for image elements or img tag in the message composer
                images = d.find_elements(By.XPATH, "//img[@role='presentation'] | //img[contains(@alt, 'Photo')] | //div[contains(@class, 'attachment')]//img")
                return len(images) > 0
            except Exception:
                return False
        
        try:
            WebDriverWait(driver, timeout, poll_frequency=0.1).until(_image_loaded)
            print("  Anh da load")
        except Exception:
            # Fallback wait ngan de tranh tre qua lau
            time.sleep(IMAGE_PREVIEW_FALLBACK_SECONDS)
            print("  Tiep tuc gui nhanh")
        
        return True
    except Exception as exc:
        print(f"[CANH BAO] Loi paste anh: {type(exc).__name__}: {exc!r}")
        return False

def _type_message(driver, msg_box, message, image_path=None):
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

    # Paste image BEFORE sending if provided
    if image_path:
        _paste_image_to_message(driver, msg_box, image_path)

    print("  Dang gui tin nhan...")
    send_clicked = _send_with_retries(driver, msg_box)
    if not send_clicked:
        raise RuntimeError("Khong the click nut Gui. Da bo fallback Enter de tranh mo link khi bi boi xanh")

    try:
        _wait_for_message_cleared(driver, msg_box, timeout=8.0)
    except Exception as exc:
        raise RuntimeError("Da thu gui nhung o nhap van chua clear. Co the tin nhan chua duoc gui.") from exc

def send_message(driver, meta_link, message, image_path=None):
    ensure_business_logged_in(driver, meta_link.strip())
    _dismiss_blocking_popups(driver, timeout=4)
    msg_box = _find_message_box(driver, timeout=15)
    _type_message(driver, msg_box, message, image_path=image_path)

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
            padded = row + [""] * 22
            link = padded[5].strip()  # F
            customer_id = padded[2].strip()  # C
            name = padded[3].strip()  # D
            product = padded[9].strip()  # J
            phone_number = padded[10].strip()  # K
            amount_due = padded[19].strip()  # T
            payment_code = padded[21].strip()  # V

            message = build_message(customer_id, name, product, phone_number, amount_due, payment_code)
            if not link or not name:
                continue

            print(f"Gửi dòng {i}: {customer_id} | {link}")
            try:
                send_message(driver, link, message, image_path=IMAGE_PATH)
                print("  OK")
            except Exception as exc:
                screenshot_path, html_path = save_debug_artifacts(driver, i)
                print(f"  Lỗi gửi dòng {i}: {type(exc).__name__}: {exc!r}")
                print(f"  URL hiện tại: {driver.current_url}")
                print(f"  Screenshot: {screenshot_path}")
                print(f"  HTML: {html_path}")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
