from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

@app.route("/")
def index():
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <title>Flask WebSocket Chat</title>
        <style>
            body { font-family: sans-serif; margin: 30px; }
            #chat-box { 
                width: 100%; max-width: 500px; height: 250px; 
                border: 1px solid #ccc; padding: 10px; overflow-y: scroll; 
                background: #f9f9f9; margin-bottom: 10px; 
            }
            .message { margin-bottom: 8px; border-bottom: 1px solid #eee; padding-bottom: 4px; }
            input { padding: 8px; width: 350px; }
            button { padding: 8px 15px; }
        </style>
    </head>
    <body>
        <h2>💬 リアルタイムチャット (WebSocket)</h2>
        <div id="chat-box"></div>
        
        <input type="text" id="message-input" placeholder="メッセージを入力..." onkeypress="if(event.key === 'Enter') sendMsg();">
        <button onclick="sendMsg()">送信</button>

        <!-- Socket.IOのクライアントライブラリ -->
        <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
        <script>
            const socket = io();

            // サーバーからメッセージを受信したとき
            socket.on('server_to_client', function(data) {
                const chatBox = document.getElementById('chat-box');
                const div = document.createElement('div');
                div.className = 'message';
                div.innerText = data.msg;
                chatBox.appendChild(div);
                // 自動で一番下までスクロール
                chatBox.scrollTop = chatBox.scrollHeight;
            });

            function sendMsg() {
                const input = document.getElementById('message-input');
                const text = input.value.trim();
                if (text !== '') {
                    // サーバーへメッセージを送信
                    socket.emit('client_to_server', { msg: text });
                    input.value = '';
                }
            }
        </script>
    </body>
    </html>
    """)

# クライアントからメッセージを受け取ったときの処理
@socketio.on('client_to_server')
def handle_custom_event(data):
    print(f"受信したメッセージ: {data['msg']}")
    # 接続している【すべての人（自分含む）】に向けてメッセージをブロードキャスト送信
    emit('server_to_client', {'msg': data['msg']}, broadcast=True)

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=80, debug=True)