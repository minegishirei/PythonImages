import logging
import os
import random
import sqlite3
import time
from flask import Flask, redirect, render_template_string, request, session, url_for
from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import StatusCode

def configure_telemetry():
    resource = Resource.create(
        {
            "service.name": os.getenv("OTEL_SERVICE_NAME", "flask-shop-demo"),
            "service.version": "2.3.0",
        }
    )
    
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318").rstrip('/')
    headers = {}
    if token := os.getenv("SIGNOZ_ACCESS_TOKEN"):
        headers["signoz-access-token"] = token

    tracer_provider = TracerProvider(resource=resource)
    if os.getenv("OTEL_TRACE_CONSOLE", "false").lower() == "true":
        tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    if os.getenv("OTEL_TRACE_MODE", "otlp").lower() != "console":
        trace_exporter = OTLPSpanExporter(
            endpoint=f"{otlp_endpoint}/v1/traces",
            headers=headers,
        )
        tracer_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
    trace.set_tracer_provider(tracer_provider)

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{otlp_endpoint}/v1/metrics", headers=headers)
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    logger_provider = LoggerProvider(resource=resource)
    log_exporter = OTLPLogExporter(endpoint=f"{otlp_endpoint}/v1/logs", headers=headers)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
    set_logger_provider(logger_provider)

    handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)

    return (
        trace.get_tracer("flask_shop.demo"),
        metrics.get_meter("flask_shop.demo"),
        logging.getLogger("flask_shop.app")
    )

app = Flask(__name__)
app.secret_key = "super-secret-shopping-key"
FlaskInstrumentor().instrument_app(app)

tracer, meter, app_logger = configure_telemetry()

checkout_counter = meter.create_counter("shop.checkout.count", unit="1")
error_counter = meter.create_counter("shop.error.count", unit="1")

DB_PATH = "shop.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            total_amount INTEGER,
            item_count INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

PRODUCTS = [
    {"id": 1, "name": "超高速SSD 2TB", "price": 18000, "emoji": "⚡"},
    {"id": 2, "name": "メカニカルキーボード", "price": 12800, "emoji": "⌨️"},
    {"id": 3, "name": "エルゴノミクスマウス", "price": 7500, "emoji": "🖱️"},
    {"id": 4, "name": "4K ゲーミングモニター", "price": 45000, "emoji": "🖥️"},
]

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>OpenTelemetry ギアショップ（SQLite対応）</title>
    
    <style>
        body { font-family: sans-serif; background: #f4f6f8; margin: 0; padding: 20px; color: #333; }
        .container { max-width: 800px; margin: auto; background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
        h1 { color: #2c3e50; border-bottom: 2px solid #eee; padding-bottom: 10px; }
        .grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; margin-top: 20px; }
        .card { border: 1px solid #e1e4e8; padding: 20px; border-radius: 8px; text-align: center; background: #fafbfc; }
        .btn { background: #3498db; color: white; border: none; padding: 10px 15px; border-radius: 5px; cursor: pointer; text-decoration: none; display: inline-block; margin-top: 10px; }
        .btn:hover { background: #2980b9; }
        .btn-success { background: #2ecc71; }
        .btn-error { background: #e74c3c; }
        .btn-secondary { background: #95a5a6; }
        .cart-box { margin-top: 30px; background: #e8f8f5; padding: 15px; border-radius: 8px; }
        .db-box { margin-top: 20px; background: #ebf5fb; padding: 15px; border-radius: 8px; border: 1px solid #85c1e9; }
        .error-box { margin-top: 20px; background: #fdebd0; padding: 15px; border-radius: 8px; border: 1px solid #f39c12; }
    </style>
    
<!-- Performance: resolve DNS + open the TLS connection early for the CDN and
     your OpenObserve endpoint, so neither is on the SDK's critical path. -->
<link rel="preconnect" href="https://browsersdk.openobserve.ai" crossorigin />
<link rel="dns-prefetch" href="https://browsersdk.openobserve.ai" />
<link rel="preconnect" href="http://localhost:5080" crossorigin />
<link rel="dns-prefetch" href="http://localhost:5080" />

<!-- Async loaders: both bundles download in parallel without blocking
     rendering. init calls queued via onReady() run as each bundle arrives. -->
<script>
  (function (h, o, u, n, d) {
    h = h[d] = h[d] || { q: [], onReady: function (c) { h.q.push(c); } };
    d = o.createElement(u); d.async = 1; d.src = n;
    n = o.getElementsByTagName(u)[0]; n.parentNode.insertBefore(d, n);
  })(window, document, 'script', 'https://browsersdk.openobserve.ai/0.3.4/openobserve-rum.js', 'OO_RUM');
  (function (h, o, u, n, d) {
    h = h[d] = h[d] || { q: [], onReady: function (c) { h.q.push(c); } };
    d = o.createElement(u); d.async = 1; d.src = n;
    n = o.getElementsByTagName(u)[0]; n.parentNode.insertBefore(d, n);
  })(window, document, 'script', 'https://browsersdk.openobserve.ai/0.3.4/openobserve-logs.js', 'OO_LOGS');
</script>

</head>
<body>
<div class="container">
    <h1>🛒 OpenTelemetry ギアショップ</h1>
    <p>SQLite、エラーテスト、メトリクス・ログ・バックエンドトレースがすべて収集されます。</p>
    
    <div class="grid">
        {% for p in products %}
        <div class="card">
            <div style="font-size: 40px;">{{ p.emoji }}</div>
            <h3>{{ p.name }}</h3>
            <p>¥{{ "{:,}".format(p.price) }}</p>
            <form action="/add/{{ p.id }}" method="post">
                <button type="submit" class="btn">カートに入れる</button>
            </form>
        </div>
        {% endfor %}
    </div>

    <div class="cart-box">
        <h3>🛍️ 現在のカート</h3>
        {% if cart %}
            <ul>
            {% for item in cart %}
                <li>{{ item.name }} - ¥{{ "{:,}".format(item.price) }}</li>
            {% endfor %}
            </ul>
            <form action="/checkout" method="post" style="display:inline;">
                <button type="submit" class="btn btn-success">レジに進む（SQLite保存）</button>
            </form>
        {% else %}
            <p>カートは空です。</p>
        {% endif %}
    </div>

    <div class="db-box">
        <h3>📦 データベース操作</h3>
        <a href="/orders" class="btn btn-secondary">SQLiteの購入履歴一覧を見る</a>
        <a href="/admin/heavy-query" class="btn btn-secondary" style="margin-left: 10px;">⚡ 重いSQLiteクエリを実行する</a>
    </div>

    <div class="error-box">
        <h3>💥 障害シミュレーション</h3>
        <form action="/trigger-error" method="post">
            <button type="submit" class="btn btn-error">意図的サーバーエラー（500）を起こす</button>
        </form>
    </div>
</div>
</body>
<script>
  var options = {
    clientToken: 'rump3Vt6s4QkuUcqass',
    applicationId: 'web-application-id', // any string identifying your application
    site: 'localhost:5080',
    organizationIdentifier: 'default',
    service: 'my-web-application',
    env: 'production',
    version: '0.0.1',
    insecureHTTP: true,
    apiVersion: 'v1',
  };

  OO_RUM.onReady(function () {
    OO_RUM.init({
      applicationId: options.applicationId,
      clientToken: options.clientToken,
      site: options.site,
      organizationIdentifier: options.organizationIdentifier,
      service: options.service,
      env: options.env,
      version: options.version,
      trackResources: true,
      trackLongTasks: true,
      trackUserInteractions: true,
      apiVersion: options.apiVersion,
      insecureHTTP: options.insecureHTTP,
      defaultPrivacyLevel: 'allow', // 'allow' | 'mask-user-input' | 'mask'
      // End-to-end trace correlation: inject tracing headers into matched requests.
      allowedTracingUrls: [
        {
          match: 'https://your-api-domain.com/api', // string, RegExp or (url) => boolean
          propagatorTypes: ['openobserve', 'tracecontext'],
        },
      ],
      sessionSampleRate: 100, // track 100% of sessions
      sessionReplaySampleRate: 50, // record 50% of sessions,
    });
    OO_RUM.startSessionReplayRecording();
  });

  OO_LOGS.onReady(function () {
    OO_LOGS.init({
      clientToken: options.clientToken,
      site: options.site,
      organizationIdentifier: options.organizationIdentifier,
      service: options.service,
      env: options.env,
      version: options.version,
      forwardErrorsToLogs: true,
      insecureHTTP: options.insecureHTTP,
      apiVersion: options.apiVersion,
    });
  });
</script>

</html>

"""


@app.route("/")
def index():
    app_logger.info("Home page requested.")
    with tracer.start_as_current_span("shop.home") as span:
        span.set_attribute("shop.page", "home")
        cart = session.get("cart", [])
        return render_template_string(HTML_TEMPLATE, products=PRODUCTS, cart=cart)

@app.route("/add/<int:product_id>", methods=["POST"])
def add_to_cart(product_id):
    product = next((p for p in PRODUCTS if p["id"] == product_id), None)
    if product:
        app_logger.info(f"Product added: {product['name']}")
    
    with tracer.start_as_current_span("shop.add_to_cart") as span:
        if product:
            span.set_attribute("product.id", product["id"])
            span.set_attribute("product.name", product["name"])
            span.set_attribute("product.price", product["price"])
            
            cart = session.get("cart", [])
            cart.append(product)
            session["cart"] = cart
        return redirect(url_for("index"))

@app.route("/checkout", methods=["POST"])
def checkout():
    app_logger.info("Checkout initiated.")
    with tracer.start_as_current_span("shop.checkout") as span:
        cart = session.get("cart", [])
        total = sum(item["price"] for item in cart)
        
        span.set_attribute("order.item_count", len(cart))
        span.set_attribute("order.total_amount", total)
        
        with tracer.start_as_current_span("sqlite.save_order") as db_span:
            db_span.set_attribute("db.system", "sqlite")
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO orders (total_amount, item_count) VALUES (?, ?)", (total, len(cart)))
            conn.commit()
            conn.close()

        with tracer.start_as_current_span("shop.payment_gateway") as payment_span:
            payment_span.set_attribute("payment.gateway", "stripe_mock")
            time.sleep(random.uniform(0.1, 0.3))
            
        checkout_counter.add(1, {"status": "success"})
        session.pop("cart", None)
        app_logger.info(f"Checkout completed. Total: {total}")
        
        return f"""
        <div style="text-align:center; margin-top:50px; font-family:sans-serif;">
            <h1 style="color: #27ae60;">🎉 ご注文ありがとうございます！</h1>
            <p>合計金額: ¥{total:,} がSQLiteに保存されました。</p>
            <a href="/orders" style="color: #3498db; text-decoration: none; font-weight: bold; margin-right: 20px;">📦 購入履歴を確認</a>
            <a href="/" style="color: #3498db; text-decoration: none; font-weight: bold;">← ショップに戻る</a>
        </div>
        """

@app.route("/orders")
def view_orders():
    app_logger.info("Fetching orders from SQLite.")
    with tracer.start_as_current_span("sqlite.get_orders") as span:
        span.set_attribute("db.system", "sqlite")
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, total_amount, item_count, created_at FROM orders ORDER BY id DESC")
        orders = cursor.fetchall()
        conn.close()
        span.set_attribute("db.rows_returned", len(orders))

    orders_html = "".join([
        f"<li>注文ID: {o[0]} | 商品数: {o[2]}個 | 合計金額: ¥{o[1]:,} | 日時: {o[3]}</li>"
        for o in orders
    ]) if orders else "<li>まだ購入履歴はありません。</li>"

    return f"""
    <div style="max-width: 600px; margin: 50px auto; font-family: sans-serif;">
        <h1>📦 SQLite 購入履歴一覧</h1>
        <ul>{orders_html}</ul>
        <br>
        <a href="/" style="color: #3498db; text-decoration: none; font-weight: bold;">← ショップに戻る</a>
    </div>
    """

@app.route("/admin/heavy-query", methods=["GET"])
def heavy_sqlite_query():
    app_logger.info("Executing heavy SQLite performance test query.")
    with tracer.start_as_current_span("sqlite.heavy_performance_test") as span:
        span.set_attribute("db.system", "sqlite")
        start_time = time.time()
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        with tracer.start_as_current_span("sqlite.execute_sql") as sql_span:
            sql_span.set_attribute("db.statement", "SELECT COUNT(*), SUM, AVG FROM orders")
            time.sleep(random.uniform(0.05, 0.2))
            cursor.execute("SELECT COUNT(*), COALESCE(SUM(total_amount), 0), COALESCE(AVG(total_amount), 0) FROM orders")
            result = cursor.fetchone()
        conn.close()
        
        duration_ms = (time.time() - start_time) * 1000
        span.set_attribute("db.duration_ms", duration_ms)
        app_logger.info(f"SQLite heavy query executed in {duration_ms:.2f} ms.")

    return f"""
    <div style="max-width: 600px; margin: 50px auto; font-family: sans-serif; text-align: center;">
        <h1>⚡ SQLite パフォーマンス計測結果</h1>
        <p>クエリ実行時間: <b>{duration_ms:.2f} ms</b></p>
        <p>総注文数: <b>{result[0]}件</b></p>
        <br>
        <a href="/" style="color: #3498db; text-encryption: none; font-weight: bold;">← ショップに戻る</a>
    </div>
    """

@app.route("/trigger-error", methods=["POST"])
def trigger_error():
    app_logger.error("Critical error triggered manually!")
    with tracer.start_as_current_span("shop.fail_operation") as span:
        span.set_attribute("error.type", "ManualTriggerError")
        span.set_status(StatusCode.ERROR, "Intentional exception")
        error_counter.add(1, {"error.type": "InternalServerError"})
        raise ZeroDivisionError("意図的なゼロ除算エラー！")

@app.errorhandler(Exception)
def handle_exception(e):
    app_logger.exception(f"Unhandled exception: {str(e)}")
    return f"""
    <div style="text-align:center; margin-top:50px; font-family:sans-serif;">
        <h1 style="color: #e74c3c;">💥 500 Internal Server Error</h1>
        <p>エラー: <b>{str(e)}</b></p>
        <a href="/" style="color: #3498db; text-decoration: none; font-weight: bold;">← ショップに戻る</a>
    </div>
    """, 500

@app.route("/health")
def health():
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")), debug=True)



  