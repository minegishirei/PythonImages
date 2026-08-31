import json
import os
import threading
import time
import base64
import re
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey
from cryptography.hazmat.backends import default_backend
from flask import Flask, jsonify, render_template_string, request
from pywebpush import WebPushException, webpush
from py_vapid import Vapid

app = Flask(__name__)

# VAPID鍵ファイル
private_key_file = "private_key.pem"

# 鍵が無ければ生成して保存する（再起動で上書きしない）
if not os.path.exists(private_key_file):
    v = Vapid()
    v.generate_keys()
    v.save_key(private_key_file)

# ファイルから Vapid オブジェクトをロード
v = Vapid.from_file(private_key_file)

# 秘密鍵から確実にEC未圧縮公開鍵を導出してブラウザ用のURL-safe base64に変換
def derive_public_key_urlsafe_from_private(pem_path):
    with open(pem_path, 'rb') as f:
        pem = f.read()

    priv = serialization.load_pem_private_key(pem, password=None, backend=default_backend())
    pub = priv.public_key()
    nums = pub.public_numbers()
    x = nums.x
    y = nums.y
    key_bytes = b'\x04' + x.to_bytes(32, 'big') + y.to_bytes(32, 'big')
    return base64.urlsafe_b64encode(key_bytes).rstrip(b'=').decode('utf-8')


VAPID_PUBLIC_KEY = derive_public_key_urlsafe_from_private(private_key_file)


@app.route('/vapid_public')
def vapid_public():
    return jsonify({'public_key': VAPID_PUBLIC_KEY})

# pywebpush accepts a path to the PEM file; pass the file path instead of raw PEM text
VAPID_PRIVATE_KEY = private_key_file

# VAPID claims
VAPID_CLAIMS = {"sub": "mailto:test@example.com"}

# 購読情報を保持する簡易リスト
subscriptions = []

# 1. メイン画面（HTMLをPython内で直接描画）
INDEX_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>Flask Web Push (Python Only)</title>
</head>
<body>
    <h1>Flask Web Push 通知テスト</h1>
    <button id="subscribeBtn">通知を有効にする</button>
    <br><br>
    <input type="text" id="msgInput" value="Pythonからこんにちは！">
    <button id="sendBtn">プッシュ通知を送る</button>

    <script>
        const publicKeyValue = "{{ public_key }}";
        console.log('VAPID public key (server):', publicKeyValue);

        function urlBase64ToUint8Array(base64String) {
            const padding = '='.repeat((4 - base64String.length % 4) % 4);
            const base64 = (base64String + padding).replace(/\\-/g, '+').replace(/_/g, '/');
            const rawData = window.atob(base64);
            const outputArray = new Uint8Array(rawData.length);
            for (let i = 0; i < rawData.length; ++i) {
                outputArray[i] = rawData.charCodeAt(i);
            }
            return outputArray;
        }

        document.getElementById('subscribeBtn').addEventListener('click', async () => {
            if (!('serviceWorker' in navigator)) return;

            // 外部のsw.jsの代わりに /sw.js エンドポイントを登録する
            console.log('Registering service worker...');
                const registration = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
                console.log('Service worker registration:', registration);
            
                const permission = await Notification.requestPermission();
            if (permission !== 'granted') {
                alert('通知権限が拒否されました');
                return;
            }
                console.log('Notification.permission=', Notification.permission);

                const subscription = await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: urlBase64ToUint8Array(publicKeyValue)
            });

                console.log('Push subscription after subscribe:', subscription);

            console.log('subscription object:', subscription);

            await fetch('/subscribe', {
                method: 'POST',
                body: JSON.stringify(subscription),
                headers: { 'Content-Type': 'application/json' }
            });

            alert('プッシュ通知の登録が完了しました！');
        });

        document.getElementById('sendBtn').addEventListener('click', async () => {
            const msg = document.getElementById('msgInput').value;
            await fetch('/send-notification', {
                method: 'POST',
                body: JSON.stringify({ message: msg }),
                headers: { 'Content-Type': 'application/json' }
            });
            alert('通知送信リクエストを送信しました');
        });
    </script>
</body>
</html>
"""

# 2. Service Workerのコード（PythonからJavaScriptの文字列として動的配信）
SERVICE_WORKER_JS = """
self.addEventListener('install', function(e) {
    console.log('[SW] install');
    self.skipWaiting();
});

self.addEventListener('activate', function(e) {
    console.log('[SW] activate');
    return self.clients.claim();
});

self.addEventListener('push', function(event) {
    console.log('[SW] push event', event);
    
    // ペイロードデータの取得（JSONまたはフォールバック）
    const data = event.data ? event.data.json() : { title: '通知', body: '本文がありません', url: '/' };
    console.log('[SW] push data', data);

    // 1. 開いているページ（クライアント）へメッセージを送信（必要に応じて画面を更新するため）
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(clientList) {
        if (clientList && clientList.length > 0) {
            clientList.forEach(function(client) {
                try {
                    client.postMessage({ type: 'push', payload: data });
                } catch (e) {
                    console.error('[SW] postMessage failed', e);
                }
            });
        }
    });

    // 2. OSの通知機能を使ったシステム通知のオプション設定
    const options = {
        body: data.body,
        icon: data.icon || '/icon.png', // デフォルトアイコンのパスを指定すると安全です
        badge: data.badge || '/badge.png',
        data: { url: data.url || '/' }, // 通知クリック時に開くURL
        requireInteraction: data.requireInteraction || false,
        vibrate: data.vibrate || [200, 100, 200],
        tag: data.tag || 'default-tag',
        actions: data.actions || [],
    };

    // 3. OS通知を表示（event.waitUntilで処理の完了を保証）
    event.waitUntil(
        self.registration.showNotification(data.title, options)
    );
});

// 4. 【追加】通知をクリックしたときの動作を定義
self.addEventListener('notificationclick', function(event) {
    console.log('[SW] notificationclick event', event);
    
    event.notification.close(); // 通知を閉じる

    const targetUrl = event.notification.data.url || '/';

    event.waitUntil(
        self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(clientList) {
            // すでに開いているタブがあれば、そこにフォーカスする
            for (let i = 0; i < clientList.length; i++) {
                const client = clientList[i];
                if (client.url === targetUrl && 'focus' in client) {
                    return client.focus();
                }
            }
            // 開いていない場合は新しくウィンドウ/タブを開く
            if (self.clients.openWindow) {
                return self.clients.openWindow(targetUrl);
            }
        })
    );
});

self.addEventListener('notificationclick', function(event) {
    console.log('[SW] notificationclick', event.notification);
    event.notification.close();
    const url = (event.notification.data && event.notification.data.url) || '/';
    event.waitUntil(clients.openWindow(url));
});
"""


@app.route("/")
def index():
  return render_template_string(INDEX_HTML, public_key=VAPID_PUBLIC_KEY)


# Service WorkerをPython側から直接JavaScriptとしてルーティング配信
@app.route("/sw.js")
def service_worker():
  return SERVICE_WORKER_JS, 200, {"Content-Type": "application/javascript"}


@app.route("/subscribe", methods=["POST"])
def subscribe():
  subscription_info = request.get_json()
  if subscription_info not in subscriptions:
    subscriptions.append(subscription_info)
  print(subscription_info)
  return jsonify({"status": "success"})


# 10秒後に通知を送るための関数
def delayed_notification(message):
        print(message)
        print("subscriptions", subscriptions)

        time.sleep(3)  # 10秒待機

        results = []
        for sub in subscriptions:
                try:
                    payload = {
                        "title": "Flaskからのお知らせ",
                        "body": message,
                        "icon": "https://via.placeholder.com/128.png?text=通知",
                        "badge": "https://via.placeholder.com/64.png?text=B",
                        "url": "/",
                        "requireInteraction": True,
                        "vibrate": [100, 50, 100],
                        "tag": "flask-push",
                        "timestamp": int(time.time() * 1000),
                        "actions": [
                            {"action": "open", "title": "開く"},
                            {"action": "dismiss", "title": "閉じる"}
                        ]
                    }

                    res = webpush(
                        subscription_info=sub,
                        data=json.dumps(payload),
                        vapid_private_key=VAPID_PRIVATE_KEY,
                        vapid_claims=VAPID_CLAIMS,
                    )
                    results.append(getattr(res, "status_code", None))
                except WebPushException as ex:
                    print("WebPushException sending to subscription:", ex)
                    results.append(None)

        print(f"Delayed notification sent. Results: {results}")


@app.route("/send-notification", methods=["POST"])
def send_notification():
  message = request.json.get("message", "プッシュ通知テストです")

  # 別スレッドで10秒待機＆通知処理を実行する（リクエストをブロックしないため）
  thread = threading.Thread(target=delayed_notification, args=(message,))
  thread.start()

  return jsonify({"status": "accepted", "message": "10秒後に通知を送信します"})

if __name__ == "__main__":
  app.run(host="0.0.0.0", port=80, debug=True)