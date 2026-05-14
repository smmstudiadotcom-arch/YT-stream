"""
YouTube Streams бот — мониторит стримы канала, создаёт заказы в JAP
"""
import requests
import random
import time
import os
import re
from datetime import datetime

# ══════════════════════════════════════
#  JAP
# ══════════════════════════════════════
JAP_API_KEY = "ec2fb6c8f5a4ea7ba6cf532e87a09895"
JAP_API_URL = "https://justanotherpanel.com/api/v2"

# ══════════════════════════════════════
#  YOUTUBE
# ══════════════════════════════════════
YT_CHANNEL_HANDLE  = "ArmeniaTodayTV"
YT_SERVICE         = 1532
YT_QTY_MIN         = 500
YT_QTY_MAX         = 1000
YT_CHECK_INTERVAL  = 60  # каждую минуту

STATE_FILE = "last_yt_stream.txt"

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [YT-Streams] {msg}", flush=True)

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            val = f.read().strip()
            return val if val else None
    return None

def save_state(value):
    with open(STATE_FILE, "w") as f:
        f.write(str(value))

def check_balance():
    try:
        resp = requests.post(JAP_API_URL, data={"key": JAP_API_KEY, "action": "balance"}, timeout=10)
        if resp.text.strip():
            data = resp.json()
            if "balance" in data:
                log(f"💰 Баланс: ${data['balance']} {data.get('currency', '')}")
    except Exception as e:
        log(f"❌ Ошибка баланса: {e}")

def create_jap_order(link):
    quantity = random.randint(YT_QTY_MIN, YT_QTY_MAX)
    payload = {"key": JAP_API_KEY, "action": "add", "service": YT_SERVICE, "link": link, "quantity": quantity}
    try:
        log(f"📤 Заказ: service={YT_SERVICE}, qty={quantity}")
        resp = requests.post(JAP_API_URL, data=payload, timeout=15)
        log(f"📥 JAP: {resp.status_code} | {repr(resp.text[:150])}")
        if not resp.text.strip():
            log("❌ Пустой ответ JAP")
            return
        data = resp.json()
        if "order" in data:
            log(f"✅ Заказ! ID: {data['order']} | Кол-во: {quantity}")
        elif "error" in data:
            log(f"❌ JAP ошибка: {data['error']}")
    except Exception as e:
        log(f"❌ Ошибка заказа: {e}")

def get_channel_id():
    """Получить channel_id из @handle"""
    try:
        url = f"https://www.youtube.com/@{YT_CHANNEL_HANDLE}"
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            log(f"❌ Не могу открыть канал: {resp.status_code}")
            return None
        
        match = re.search(r'"channelId":"(UC[A-Za-z0-9_-]{22})"', resp.text)
        if not match:
            match = re.search(r'/channel/(UC[A-Za-z0-9_-]{22})', resp.text)
        if match:
            channel_id = match.group(1)
            log(f"✅ Channel ID: {channel_id}")
            return channel_id
        log(f"❌ Channel ID не найден в HTML")
        return None
    except Exception as e:
        log(f"❌ Ошибка: {e}")
        return None

def get_streams(channel_id):
    """Получить последние стримы из RSS"""
    try:
        # Пробуем разные playlist ID варианты
        # UULV - все Live Streams
        # UULF - все видео (long form)
        # UU - все видео и стримы
        suffix = channel_id[2:]  # убираем 'UC'
        
        playlist_variants = [
            ("UULV" + suffix, "Live streams"),
            ("UULF" + suffix, "Long form videos"),
            ("UU"   + suffix, "All uploads"),
        ]
        
        for playlist_id, label in playlist_variants:
            url = f"https://www.youtube.com/feeds/videos.xml?playlist_id={playlist_id}"
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, headers=headers, timeout=15)
            log(f"📥 [{label}] {playlist_id}: {resp.status_code} | {len(resp.text)} символов")
            
            if resp.status_code != 200:
                continue
            
            streams = []
            for match in re.finditer(r'<yt:videoId>([A-Za-z0-9_-]{11})</yt:videoId>', resp.text):
                video_id = match.group(1)
                streams.append({
                    "id": video_id,
                    "url": f"https://www.youtube.com/watch?v={video_id}"
                })
            
            if streams:
                log(f"📊 [{label}] Найдено: {len(streams)}")
                return streams
        
        log(f"⚠️  Ни один playlist не вернул видео")
        return []
    except Exception as e:
        log(f"❌ Ошибка: {e}")
        return []

def main():
    log(f"🚀 YouTube Streams бот запущен!")
    log(f"📺 Канал: @{YT_CHANNEL_HANDLE} | Услуга: {YT_SERVICE} | {YT_QTY_MIN}-{YT_QTY_MAX}")
    log(f"⏰ Интервал проверки: {YT_CHECK_INTERVAL} сек")
    check_balance()
    
    # Получаем channel_id один раз
    channel_id = None
    while not channel_id:
        channel_id = get_channel_id()
        if not channel_id:
            log("⏳ Повтор через 60 сек...")
            time.sleep(60)
    
    last_id = load_state()
    
    if not last_id:
        streams = get_streams(channel_id)
        if streams:
            last_id = streams[0]["id"]
            save_state(last_id)
            log(f"📌 Последний стрим: {last_id}. Жду новые...")
        else:
            log("⚠️  Стримов на канале не найдено")
    
    while True:
        time.sleep(YT_CHECK_INTERVAL)
        try:
            streams = get_streams(channel_id)
            if not streams:
                continue
            
            new_streams = []
            for stream in streams:
                if stream["id"] != last_id:
                    new_streams.append(stream)
                else:
                    break
            
            if new_streams:
                log(f"🆕 Новых стримов: {len(new_streams)}")
                latest_id = streams[0]["id"]
                for stream in new_streams:
                    log(f"🆕 {stream['url']}")
                    create_jap_order(stream["url"])
                    time.sleep(2)
                save_state(latest_id)
                last_id = latest_id
            else:
                log(f"🔍 Нет новых стримов (последний: {last_id})")
        except Exception as e:
            log(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    main()
