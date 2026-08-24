from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
# allow_unsafe_werkzeug=True は開発環境(debug=True)での警告回避用です
socketio = SocketIO(app, cors_allowed_origins="*")

@app.route("/")
def index():
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <title>WebRTC P2P Chat via Flask Signaling</title>
        <style>
            body { font-family: sans-serif; margin: 30px; }
            #chat-box { 
                width: 100%; max-width: 500px; height: 250px; 
                border: 1px solid #ccc; padding: 10px; overflow-y: scroll; 
                background: #f9f9f9; margin-bottom: 10px; 
            }
            .message { margin-bottom: 8px; border-bottom: 1px solid #eee; padding-bottom: 4px; }
            input { padding: 8px; width: 350px; }
            button { padding: 8px 15px; margin-bottom: 15px; }
            .box { border: 1px solid #ddd; padding: 15px; margin-bottom: 15px; border-radius: 5px; }
        </style>
    </head>
    <body>
        <h2>🔌 WebRTC P2P リアルタイムチャット</h2>
        
        <div class="box">
            <h3>1. 接続</h3>
            <button onclick="startConnection()">接続を開始する（両方のタブ/端末で押してください）</button>
            <p id="status">ステータス: 未接続</p>
        </div>

        <div class="box">
            <h3>2. メッセージ送信</h3>
            <div id="chat-box"></div>
            <input type="text" id="message-input" placeholder="メッセージを入力..." onkeypress="if(event.key === 'Enter') sendMsg();">
            <button onclick="sendMsg()">送信</button>
        </div>

        <!-- Socket.IOのクライアントライブラリ（シグナリング用） -->
        <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
        <script>
            const socket = io();
            let pc, dataChannel;
            const configuration = { iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] };

            // --- シグナリング（WebSocket経由でWebRTCの接続情報をやり取り） ---
            socket.on('signal', async (data) => {
                if (data.type === 'offer') {
                    if (!pc) createPeerConnection(false);
                    await pc.setRemoteDescription(new RTCSessionDescription(data.offer));
                    const answer = await pc.createAnswer();
                    await pc.setLocalDescription(answer);
                    socket.emit('signal', { type: 'answer', answer: pc.localDescription.toJSON() });
                } 
                else if (data.type === 'answer') {
                    await pc.setRemoteDescription(new RTCSessionDescription(data.answer));
                } 
                else if (data.type === 'candidate' && pc) {
                    try {
                        await pc.addIceCandidate(new RTCIceCandidate(data.candidate));
                    } catch (e) {
                        console.error('ICE候補の追加に失敗', e);
                    }
                }
            });

            function createPeerConnection(isInitiator) {
                pc = new RTCPeerConnection(configuration);

                // ネットワーク経路が見つかったら相手に通知
                pc.onicecandidate = (event) => {
                    if (event.candidate) {
                        socket.emit('signal', { type: 'candidate', candidate: event.candidate.toJSON() });
                    }
                };

                if (isInitiator) {
                    // 発信者側：DataChannelを作成してOfferを作る
                    dataChannel = pc.createDataChannel("chat");
                    setupDataChannel();

                    pc.createOffer()
                      .then(offer => pc.setLocalDescription(offer))
                      .then(() => {
                          socket.emit('signal', { type: 'offer', offer: pc.localDescription.toJSON() });
                      });
                } else {
                    // 受信者側：相手からDataChannelが届くのを待つ
                    pc.ondatachannel = (event) => {
                        dataChannel = event.channel;
                        setupDataChannel();
                    };
                }
            }

            function startConnection() {
                if (pc) {
                    appendLog("すでに接続処理が走っています");
                    return;
                }
                document.getElementById('status').innerText = "ステータス: 接続中...";
                createPeerConnection(true); // ボタンを押した方をイニシエーター（発信者）にする
            }

            // --- WebRTC DataChannel の設定（ここからP2P直接通信） ---
            function setupDataChannel() {
                dataChannel.onopen = () => {
                    document.getElementById('status').innerText = "ステータス: P2P接続完了！";
                    appendLog("system: P2Pデータチャンネルがオープンしました");
                };
                dataChannel.onmessage = (e) => {
                    appendLog("相手: " + e.data);
                };
                dataChannel.onclose = () => {
                    document.getElementById('status').innerText = "ステータス: 切断されました";
                    appendLog("system: チャンネルが閉じました");
                };
            }

            function sendMsg() {
                const input = document.getElementById('message-input');
                const text = input.value.trim();
                
                if (text !== '') {
                    if (dataChannel && dataChannel.readyState === 'open') {
                        // P2Pで直接相手に送信
                        dataChannel.send(text);
                        appendLog("自分: " + text);
                        input.value = '';
                    } else {
                        alert("P2Pチャネルがまだ接続されていません。");
                    }
                }
            }

            function appendLog(msg) {
                const chatBox = document.getElementById('chat-box');
                const div = document.createElement('div');
                div.className = 'message';
                div.innerText = msg;
                chatBox.appendChild(div);
                chatBox.scrollTop = chatBox.scrollHeight;
            }
        </script>
    </body>
    </html>
    """)

# シグナリングデータを転送するイベント（自分以外へブロードキャスト）
@socketio.on('signal')
def handle_signal(data):
    emit('signal', data, broadcast=True, include_self=False)

if __name__ == "__main__":
    # ポート80で起動（管理者権限が必要な場合があります。必要に応じて 5000 などに変更してください）
    socketio.run(app, host="0.0.0.0", port=80, debug=True, allow_unsafe_werkzeug=True)