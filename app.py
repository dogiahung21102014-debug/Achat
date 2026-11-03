import os, sqlite3, secrets, functools, re, hmac, hashlib, json, base64, urllib.parse
import requests
from cryptography.fernet import Fernet, InvalidToken
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

app=Flask(__name__)
app.secret_key=os.getenv('SECRET_KEY','dev-only-change-this-secret')
if os.getenv('APP_ENV') == 'production' and (len(app.secret_key)<32 or app.secret_key=='dev-only-change-this-secret'):
    raise RuntimeError('Production requires SECRET_KEY with at least 32 characters')
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.getenv('APP_ENV')=='production', WTF_CSRF_TIME_LIMIT=3600)
app.wsgi_app=ProxyFix(app.wsgi_app,x_for=1,x_proto=1,x_host=1)
csrf=CSRFProtect(app)
@app.after_request
def security_headers(response):
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Cache-Control']='no-store' if request.path.startswith(('/admin','/inbox','/orders','/team','/pages','/products')) else 'private'
    return response
DB=os.getenv('DATABASE_PATH',os.path.join(os.path.dirname(__file__),'achat.sqlite3'))
VN=timezone(timedelta(hours=7))
def now(): return datetime.now(VN)
def conn():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c
def init_db():
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS shops(id INTEGER PRIMARY KEY,name TEXT NOT NULL,plan TEXT NOT NULL DEFAULT 'trial',trial_ends TEXT NOT NULL,max_pages INTEGER NOT NULL DEFAULT 2,max_staff INTEGER NOT NULL DEFAULT 3,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,shop_id INTEGER REFERENCES shops(id),name TEXT NOT NULL,email TEXT NOT NULL UNIQUE,password_hash TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('superadmin','owner','manager','staff')),active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS pages(id INTEGER PRIMARY KEY,shop_id INTEGER NOT NULL REFERENCES shops(id),name TEXT NOT NULL,facebook_page_id TEXT,connected INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY,shop_id INTEGER NOT NULL REFERENCES shops(id),name TEXT NOT NULL,phone TEXT,address TEXT);
        CREATE TABLE IF NOT EXISTS conversations(id INTEGER PRIMARY KEY,shop_id INTEGER NOT NULL REFERENCES shops(id),page_id INTEGER REFERENCES pages(id),customer_id INTEGER NOT NULL REFERENCES customers(id),unread INTEGER NOT NULL DEFAULT 1,assigned_user_id INTEGER REFERENCES users(id),tag TEXT NOT NULL DEFAULT '',updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,shop_id INTEGER NOT NULL REFERENCES shops(id),conversation_id INTEGER NOT NULL REFERENCES conversations(id),sender TEXT NOT NULL,body TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,shop_id INTEGER NOT NULL REFERENCES shops(id),sku TEXT NOT NULL,name TEXT NOT NULL,price INTEGER NOT NULL DEFAULT 0,stock INTEGER NOT NULL DEFAULT 0,UNIQUE(shop_id,sku));
        CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY,shop_id INTEGER NOT NULL REFERENCES shops(id),conversation_id INTEGER REFERENCES conversations(id),customer_id INTEGER REFERENCES customers(id),sku TEXT,qty INTEGER NOT NULL DEFAULT 1,amount INTEGER NOT NULL DEFAULT 0,shipping_fee INTEGER NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT 'Chưa đẩy đơn',source TEXT NOT NULL DEFAULT 'Thủ công',created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,shop_id INTEGER,actor_id INTEGER,action TEXT NOT NULL,details TEXT,created_at TEXT NOT NULL);
        ''')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS system_admins(user_id INTEGER PRIMARY KEY REFERENCES users(id),is_primary INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS facebook_connections(id INTEGER PRIMARY KEY,shop_id INTEGER NOT NULL REFERENCES shops(id),page_id INTEGER NOT NULL REFERENCES pages(id),fb_page_id TEXT NOT NULL UNIQUE,token_encrypted TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS webhook_events(mid TEXT PRIMARY KEY,received_at TEXT NOT NULL);
        ''')
        c.execute('INSERT OR IGNORE INTO system_admins(user_id,is_primary) SELECT id,1 FROM users WHERE role="superadmin" ORDER BY id LIMIT 1')
        if not c.execute('SELECT 1 FROM users WHERE role=?',('superadmin',)).fetchone():
            t=now().isoformat()
            admin_password=os.getenv('ADMIN_PASSWORD','ChangeMe123!')
            admin_email=os.getenv('ADMIN_EMAIL','admin@achat.local')
            if os.getenv('APP_ENV')=='production' and (len(admin_password)<12 or admin_password=='ChangeMe123!' or admin_email.endswith('.local')):
                raise RuntimeError('Set ADMIN_EMAIL and a strong ADMIN_PASSWORD (12+ characters) in production')
            c.execute('INSERT INTO users(shop_id,name,email,password_hash,role,created_at) VALUES(NULL,?,?,?,?,?)',('Quản trị hệ thống',admin_email,generate_password_hash(admin_password),'superadmin',t))
            c.execute('INSERT OR IGNORE INTO system_admins(user_id,is_primary) SELECT id,1 FROM users WHERE role="superadmin" ORDER BY id LIMIT 1')
            if os.getenv('APP_ENV')=='production': return
            c.execute('INSERT INTO shops(name,plan,trial_ends,max_pages,max_staff,created_at) VALUES(?,?,?,?,?,?)',('Shop Đan Đan','trial',(now()+timedelta(days=7)).isoformat(),2,3,t)); sid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            c.execute('INSERT INTO users(shop_id,name,email,password_hash,role,created_at) VALUES(?,?,?,?,?,?)',(sid,'Chủ shop Đan Đan','owner@achat.local',generate_password_hash(os.getenv('DEMO_OWNER_PASSWORD','ChangeMe123!')),'owner',t))
            c.execute('INSERT INTO pages(shop_id,name,created_at) VALUES(?,?,?)',(sid,'Đan Đan Fashion (demo)',t))
            pid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            c.execute('INSERT INTO customers(shop_id,name,phone,address) VALUES(?,?,?,?)',(sid,'Nguyễn Thị Mai','0987654321','Nam Định')); cid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            c.execute('INSERT INTO conversations(shop_id,page_id,customer_id,tag,updated_at) VALUES(?,?,?,?,?)',(sid,pid,cid,'Khách mới',t)); conv=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            for sender,body in [('customer','Chào shop, quần QN01 còn size L không?'),('staff','Dạ còn chị nhé, giá 159.000đ ạ.'),('customer','Cho chị 2 chiếc QN01, số 0987654321, gửi Nam Định nhé')]:c.execute('INSERT INTO messages(shop_id,conversation_id,sender,body,created_at) VALUES(?,?,?,?,?)',(sid,conv,sender,body,t))
            c.execute('INSERT INTO products(shop_id,sku,name,price,stock) VALUES(?,?,?,?,?)',(sid,'QN01','Quần nữ ống rộng',159000,125))
init_db()

def current_user():
    uid=session.get('uid')
    if not uid:return None
    with conn() as c:return c.execute('SELECT * FROM users WHERE id=? AND active=1',(uid,)).fetchone()
def login_required(f):
    @functools.wraps(f)
    def wrapped(*a,**kw):
        if not current_user():return redirect(url_for('login'))
        return f(*a,**kw)
    return wrapped
def roles(*allowed):
    def decorator(f):
        @functools.wraps(f)
        @login_required
        def wrapped(*a,**kw):
            if current_user()['role'] not in allowed:abort(403)
            return f(*a,**kw)
        return wrapped
    return decorator
def shop_access():
    u=current_user()
    if not u or not u['shop_id']:abort(403)
    with conn() as c:s=c.execute('SELECT * FROM shops WHERE id=?',(u['shop_id'],)).fetchone()
    if not s or not s['active']:abort(403)
    if s['plan']=='trial' and datetime.fromisoformat(s['trial_ends'])<now():
        flash('Thời gian dùng thử đã hết. Vui lòng liên hệ quản trị hệ thống.','warning')
        return None
    return s
def audit(c,action,details='',shop_id=None):
    u=current_user(); c.execute('INSERT INTO audit(shop_id,actor_id,action,details,created_at) VALUES(?,?,?,?,?)',(shop_id if shop_id is not None else u['shop_id'],u['id'],action,details,now().isoformat()))
@app.context_processor
def context():return dict(me=current_user(),today=now())
@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        with conn() as c:u=c.execute('SELECT * FROM users WHERE email=?',(request.form.get('email','').strip().lower(),)).fetchone()
        if u and u['active'] and check_password_hash(u['password_hash'],request.form.get('password','')):
            session.clear();session['uid']=u['id'];return redirect(url_for('admin' if u['role']=='superadmin' else 'inbox'))
        flash('Email hoặc mật khẩu không đúng','error')
    return render_template('login.html')
@app.route('/logout',methods=['POST'])
@login_required
def logout():session.clear();return redirect(url_for('login'))
@app.route('/')
@login_required
def index():return redirect(url_for('admin' if current_user()['role']=='superadmin' else 'inbox'))
@app.route('/admin')
@roles('superadmin')
def admin():
    with conn() as c:
        shops=c.execute('''SELECT s.*, (SELECT COUNT(*) FROM pages p WHERE p.shop_id=s.id) page_count,(SELECT COUNT(*) FROM users u WHERE u.shop_id=s.id AND u.role!='owner') staff_count,(SELECT COUNT(*) FROM orders o WHERE o.shop_id=s.id) order_count FROM shops s ORDER BY s.id DESC''').fetchall()
        logs=c.execute('SELECT a.*,u.name actor FROM audit a LEFT JOIN users u ON u.id=a.actor_id ORDER BY a.id DESC LIMIT 12').fetchall()
    return render_template('admin.html',shops=shops,logs=logs)
@app.route('/admin/shops',methods=['POST'])
@roles('superadmin')
def create_shop():
    name=request.form.get('name','').strip();email=request.form.get('email','').strip().lower();password=request.form.get('password','');days=int(request.form.get('days',7));pages=int(request.form.get('pages',2));staff=int(request.form.get('staff',3))
    if not name or not email or len(password)<10 or not 1<=days<=365 or not 0<=pages<=10000 or not 0<=staff<=10000:flash('Thông tin không hợp lệ (mật khẩu tối thiểu 10 ký tự).','error');return redirect(url_for('admin'))
    try:
        with conn() as c:
            c.execute('INSERT INTO shops(name,trial_ends,max_pages,max_staff,created_at) VALUES(?,?,?,?,?)',(name,(now()+timedelta(days=days)).isoformat(),pages,staff,now().isoformat()));sid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            c.execute('INSERT INTO users(shop_id,name,email,password_hash,role,created_at) VALUES(?,?,?,?,?,?)',(sid,'Chủ shop '+name,email,generate_password_hash(password),'owner',now().isoformat()))
            audit(c,'create_shop',name,sid)
        flash('Đã tạo shop và tài khoản chủ shop.','success')
    except sqlite3.IntegrityError:flash('Email đã tồn tại.','error')
    return redirect(url_for('admin'))
@app.route('/admin/shops/<int:sid>/update',methods=['POST'])
@roles('superadmin')
def update_shop(sid):
    with conn() as c:
        s=c.execute('SELECT * FROM shops WHERE id=?',(sid,)).fetchone()
        if not s:abort(404)
        days=int(request.form.get('extend_days',0));pages=max(0,int(request.form.get('max_pages',s['max_pages'])));staff=max(0,int(request.form.get('max_staff',s['max_staff'])));active=1 if request.form.get('active')=='1' else 0
        end=max(now(),datetime.fromisoformat(s['trial_ends']))+timedelta(days=max(0,days))
        c.execute('UPDATE shops SET trial_ends=?,max_pages=?,max_staff=?,active=? WHERE id=?',(end.isoformat(),pages,staff,active,sid));audit(c,'update_shop',f'pages={pages},staff={staff},active={active},extend={days}',sid)
    flash('Đã cập nhật giới hạn shop.','success');return redirect(url_for('admin'))
@app.route('/inbox')
@login_required
def inbox():
    shop=shop_access()
    if not shop:return render_template('expired.html')
    sid=shop['id'];chosen=request.args.get('id',type=int)
    with conn() as c:
        conversations=c.execute('''SELECT v.*,cu.name customer_name,cu.phone,cu.address,p.name page_name,(SELECT body FROM messages m WHERE m.conversation_id=v.id ORDER BY m.id DESC LIMIT 1) preview FROM conversations v JOIN customers cu ON cu.id=v.customer_id LEFT JOIN pages p ON p.id=v.page_id WHERE v.shop_id=? ORDER BY v.updated_at DESC''',(sid,)).fetchall()
        if not chosen and conversations:chosen=conversations[0]['id']
        selected=c.execute('''SELECT v.*,cu.name customer_name,cu.phone,cu.address FROM conversations v JOIN customers cu ON cu.id=v.customer_id WHERE v.id=? AND v.shop_id=?''',(chosen,sid)).fetchone() if chosen else None
        messages=c.execute('SELECT * FROM messages WHERE conversation_id=? AND shop_id=? ORDER BY id',(chosen,sid)).fetchall() if selected else []
        products=c.execute('SELECT * FROM products WHERE shop_id=? ORDER BY name',(sid,)).fetchall()
        orders=c.execute('SELECT * FROM orders WHERE shop_id=? AND conversation_id=? ORDER BY id DESC',(sid,chosen)).fetchall() if selected else []
        pages=c.execute('SELECT * FROM pages WHERE shop_id=?',(sid,)).fetchall()
    return render_template('inbox.html',shop=shop,conversations=conversations,selected=selected,messages=messages,products=products,orders=orders,pages=pages)
@app.route('/inbox/<int:cid>/message',methods=['POST'])
@login_required
def message(cid):
    shop=shop_access()
    if not shop:return redirect(url_for('inbox'))
    body=request.form.get('body','').strip()
    if body:
        with conn() as c:
            if not c.execute('SELECT 1 FROM conversations WHERE id=? AND shop_id=?',(cid,shop['id'])).fetchone():abort(404)
            c.execute('INSERT INTO messages(shop_id,conversation_id,sender,body,created_at) VALUES(?,?,?,?,?)',(shop['id'],cid,'staff',body,now().isoformat()));c.execute('UPDATE conversations SET updated_at=?,unread=0 WHERE id=? AND shop_id=?',(now().isoformat(),cid,shop['id']));audit(c,'demo_message',f'conversation={cid}')
        flash('Đã lưu tin nhắn demo. Chưa gửi tới Facebook.','warning')
    return redirect(url_for('inbox',id=cid))
@app.route('/inbox/<int:cid>/tag',methods=['POST'])
@login_required
def tag(cid):
    shop=shop_access()
    if not shop:return redirect(url_for('inbox'))
    with conn() as c:c.execute('UPDATE conversations SET tag=? WHERE id=? AND shop_id=?',(request.form.get('tag','')[:50],cid,shop['id']));audit(c,'tag',f'conversation={cid}')
    return redirect(url_for('inbox',id=cid))
@app.route('/inbox/<int:cid>/ai-check',methods=['POST'])
@login_required
def ai_check(cid):
    shop=shop_access()
    if not shop:return redirect(url_for('inbox'))
    with conn() as c:
        v=c.execute('SELECT * FROM conversations WHERE id=? AND shop_id=?',(cid,shop['id'])).fetchone()
        if not v:abort(404)
        rows=c.execute('SELECT body FROM messages WHERE conversation_id=? AND shop_id=? AND sender=? ORDER BY id DESC LIMIT 10',(cid,shop['id'],'customer')).fetchall()
        products=c.execute('SELECT * FROM products WHERE shop_id=?',(shop['id'],)).fetchall()
        text=' '.join(r['body'] for r in rows)
        matched=next((p for p in products if re.search(r'(?<!\w)'+re.escape(p['sku'])+r'(?!\w)',text,re.I)),None)
        qtymatch=re.search(r'\b(\d{1,3})\s*(?:chiếc|cái|sp|sản phẩm)\b',text,re.I)
        qty=int(qtymatch.group(1)) if qtymatch else 1
        if not matched:flash('AI Check demo: chưa nhận ra mã SKU trong tin nhắn khách.','warning')
        elif qty>matched['stock']:flash('AI Check demo: tồn kho không đủ.','error')
        elif not re.search(r'(?:0|\+84)\d{9,10}',text):flash('AI Check demo: chưa có số điện thoại.','warning')
        else:
            fee=30000 if qty==1 else 0
            c.execute('INSERT INTO orders(shop_id,conversation_id,customer_id,sku,qty,amount,shipping_fee,source,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(shop['id'],cid,v['customer_id'],matched['sku'],qty,qty*matched['price'],fee,'AI Check (demo)',now().isoformat()))
            c.execute('UPDATE conversations SET tag=? WHERE id=? AND shop_id=?',('AI tạo đơn',cid,shop['id']));audit(c,'ai_demo_order',f'conversation={cid},sku={matched["sku"]},qty={qty}')
            flash('Đã tạo đơn NHÁP bằng quy tắc demo. Cần nhân viên xác nhận trước khi giao.','success')
    return redirect(url_for('inbox',id=cid))
@app.route('/orders')
@login_required
def orders():
    shop=shop_access()
    if not shop:return render_template('expired.html')
    with conn() as c:rows=c.execute('''SELECT o.*,cu.name customer_name,cu.phone FROM orders o LEFT JOIN customers cu ON cu.id=o.customer_id WHERE o.shop_id=? ORDER BY o.id DESC''',(shop['id'],)).fetchall()
    return render_template('orders.html',shop=shop,orders=rows)
@app.route('/products',methods=['GET','POST'])
@login_required
def products():
    shop=shop_access()
    if not shop:return render_template('expired.html')
    if request.method=='POST':
        if current_user()['role'] not in ('owner','manager'):abort(403)
        try:
            with conn() as c:c.execute('INSERT INTO products(shop_id,sku,name,price,stock) VALUES(?,?,?,?,?)',(shop['id'],request.form['sku'].strip(),request.form['name'].strip(),max(0,int(request.form['price'])),max(0,int(request.form['stock']))));audit(c,'create_product',request.form['sku'])
            flash('Đã thêm sản phẩm.','success')
        except sqlite3.IntegrityError:flash('SKU đã tồn tại.','error')
        return redirect(url_for('products'))
    with conn() as c:rows=c.execute('SELECT * FROM products WHERE shop_id=? ORDER BY id DESC',(shop['id'],)).fetchall()
    return render_template('products.html',shop=shop,products=rows)
@app.route('/team',methods=['GET','POST'])
@roles('owner','manager')
def team():
    shop=shop_access()
    if not shop:return render_template('expired.html')
    if request.method=='POST':
        email=request.form.get('email','').strip().lower();password=request.form.get('password','');role=request.form.get('role','staff')
        if role not in ('staff','manager') or len(password)<10:flash('Vai trò hoặc mật khẩu không hợp lệ (ít nhất 10 ký tự).','error')
        else:
            with conn() as c:
                count=c.execute("SELECT COUNT(*) FROM users WHERE shop_id=? AND role IN ('staff','manager') AND active=1",(shop['id'],)).fetchone()[0]
                if count>=shop['max_staff']:flash('Đã đạt giới hạn tài khoản nhân viên của gói.','error')
                else:
                    try:c.execute('INSERT INTO users(shop_id,name,email,password_hash,role,created_at) VALUES(?,?,?,?,?,?)',(shop['id'],request.form['name'].strip(),email,generate_password_hash(password),role,now().isoformat()));audit(c,'create_staff',email);flash('Đã tạo nhân viên.','success')
                    except sqlite3.IntegrityError:flash('Email đã được sử dụng.','error')
        return redirect(url_for('team'))
    with conn() as c:rows=c.execute('SELECT * FROM users WHERE shop_id=? ORDER BY id',(shop['id'],)).fetchall()
    return render_template('team.html',shop=shop,users=rows)
@app.route('/pages',methods=['GET','POST'])
@roles('owner','manager')
def pages():
    shop=shop_access()
    if not shop:return render_template('expired.html')
    if request.method=='POST':
        with conn() as c:
            count=c.execute('SELECT COUNT(*) FROM pages WHERE shop_id=?',(shop['id'],)).fetchone()[0]
            if count>=shop['max_pages']:flash('Đã đạt giới hạn fanpage của gói.','error')
            else:c.execute('INSERT INTO pages(shop_id,name,created_at) VALUES(?,?,?)',(shop['id'],request.form.get('name','Fanpage demo').strip(),now().isoformat()));audit(c,'add_demo_page',request.form.get('name',''));flash('Đã thêm fanpage demo. Chưa kết nối Facebook.','warning')
        return redirect(url_for('pages'))
    with conn() as c:rows=c.execute('SELECT * FROM pages WHERE shop_id=?',(shop['id'],)).fetchall()
    return render_template('pages.html',shop=shop,pages=rows)

# Facebook integration uses official Meta Graph API; requires approved permissions.
META_VERSION=os.getenv('META_API_VERSION','v23.0')
def meta_ready():
    return all(os.getenv(k) for k in ('META_APP_ID','META_APP_SECRET','TOKEN_ENCRYPTION_KEY','META_VERIFY_TOKEN'))
def token_cipher():
    key=os.getenv('TOKEN_ENCRYPTION_KEY')
    if not key:raise RuntimeError('Missing TOKEN_ENCRYPTION_KEY')
    return Fernet(key.encode())
def graph(path,token,method='GET',data=None):
    url=f'https://graph.facebook.com/{META_VERSION}/{path.lstrip("/")}'
    kwargs={'timeout':15,'headers':{'Authorization':f'Bearer {token}'}}
    if method=='GET':kwargs['params']=data or {}
    else:kwargs['json']=data or {}
    r=requests.request(method,url,**kwargs)
    r.raise_for_status()
    return r.json()

@app.route('/admin/system-users',methods=['GET','POST'])
@roles('superadmin')
def system_users():
    with conn() as c:
        primary=c.execute('SELECT is_primary FROM system_admins WHERE user_id=?',(current_user()['id'],)).fetchone()
        if request.method=='POST':
            if not primary or not primary['is_primary']:abort(403)
            email=request.form.get('email','').strip().lower();name=request.form.get('name','').strip();pw=request.form.get('password','')
            if not name or '@' not in email or len(pw)<12:flash('Tên, email hoặc mật khẩu không hợp lệ (tối thiểu 12 ký tự).','error')
            else:
                try:
                    c.execute('INSERT INTO users(shop_id,name,email,password_hash,role,created_at) VALUES(NULL,?,?,?,?,?)',(name,email,generate_password_hash(pw),'superadmin',now().isoformat()))
                    uid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
                    c.execute('INSERT INTO system_admins(user_id,is_primary) VALUES(?,0)',(uid,));audit(c,'create_system_admin',email)
                    flash('Đã tạo quản trị viên hệ thống.','success')
                except sqlite3.IntegrityError:flash('Email đã tồn tại.','error')
            return redirect(url_for('system_users'))
        rows=c.execute('SELECT u.*,sa.is_primary FROM users u JOIN system_admins sa ON sa.user_id=u.id ORDER BY sa.is_primary DESC,u.id').fetchall()
    return render_template('system_users.html',users=rows,primary=bool(primary and primary['is_primary']))

@app.route('/admin/system-users/<int:uid>/toggle',methods=['POST'])
@roles('superadmin')
def toggle_system_user(uid):
    with conn() as c:
        actor=c.execute('SELECT is_primary FROM system_admins WHERE user_id=?',(current_user()['id'],)).fetchone()
        target=c.execute('SELECT u.active,sa.is_primary FROM users u JOIN system_admins sa ON sa.user_id=u.id WHERE u.id=?',(uid,)).fetchone()
        if not actor or not actor['is_primary'] or not target or target['is_primary']:abort(403)
        c.execute('UPDATE users SET active=? WHERE id=?',(0 if target['active'] else 1,uid));audit(c,'toggle_system_admin',str(uid))
    return redirect(url_for('system_users'))

@app.route('/facebook/connect')
@roles('owner','manager')
def facebook_connect():
    shop=shop_access()
    if not shop:return redirect(url_for('pages'))
    if not meta_ready():flash('Chưa cấu hình META_APP_ID, META_APP_SECRET, META_VERIFY_TOKEN và TOKEN_ENCRYPTION_KEY trên máy chủ.','error');return redirect(url_for('pages'))
    nonce=secrets.token_urlsafe(32)
    session['fb_oauth_state']=nonce
    session['fb_oauth_shop']=shop['id']
    params={'client_id':os.environ['META_APP_ID'],'redirect_uri':url_for('facebook_callback',_external=True,_scheme='https' if os.getenv('APP_ENV')=='production' else 'http'),'state':nonce,'scope':'pages_show_list,pages_messaging,pages_manage_metadata','response_type':'code'}
    return redirect('https://www.facebook.com/'+META_VERSION+'/dialog/oauth?'+urllib.parse.urlencode(params))

@app.route('/facebook/callback')
@login_required
def facebook_callback():
    state=request.args.get('state','')
    expected=session.pop('fb_oauth_state',None)
    expected_shop=session.pop('fb_oauth_shop',None)
    if not expected or not hmac.compare_digest(expected,state):abort(400)
    if current_user()['role'] not in ('owner','manager'):abort(403)
    shop=shop_access()
    if not shop:return redirect(url_for('pages'))
    if shop['id']!=expected_shop:abort(403)
    code=request.args.get('code')
    if not code:flash('Facebook không cấp mã xác thực.','error');return redirect(url_for('pages'))
    redirect_uri=url_for('facebook_callback',_external=True,_scheme='https' if os.getenv('APP_ENV')=='production' else 'http')
    try:
        r=requests.get(f'https://graph.facebook.com/{META_VERSION}/oauth/access_token',params={'client_id':os.environ['META_APP_ID'],'client_secret':os.environ['META_APP_SECRET'],'redirect_uri':redirect_uri,'code':code},timeout=15)
        r.raise_for_status();user_token=r.json()['access_token']
        result=graph('me/accounts',user_token,data={'fields':'id,name,access_token','limit':100})
        count=0
        with conn() as c:
            for page in result.get('data',[]):
                fb_id=str(page['id']); page_token=page.get('access_token')
                if not page_token:continue
                owned=c.execute('SELECT shop_id FROM facebook_connections WHERE fb_page_id=?',(fb_id,)).fetchone()
                if owned and owned['shop_id']!=shop['id']:continue
                local=c.execute('SELECT id FROM pages WHERE shop_id=? AND facebook_page_id=?',(shop['id'],fb_id)).fetchone()
                if not local:
                    num=c.execute('SELECT COUNT(*) FROM pages WHERE shop_id=?',(shop['id'],)).fetchone()[0]
                    if num>=shop['max_pages']:continue
                    c.execute('INSERT INTO pages(shop_id,name,facebook_page_id,connected,created_at) VALUES(?,?,?,?,?)',(shop['id'],page['name'],fb_id,1,now().isoformat()))
                    pid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
                else:pid=local['id'];c.execute('UPDATE pages SET connected=1,name=? WHERE id=?',(page['name'],pid))
                encrypted=token_cipher().encrypt(page_token.encode()).decode()
                c.execute('INSERT INTO facebook_connections(shop_id,page_id,fb_page_id,token_encrypted,created_at) VALUES(?,?,?,?,?) ON CONFLICT(fb_page_id) DO UPDATE SET token_encrypted=excluded.token_encrypted',(shop['id'],pid,fb_id,encrypted,now().isoformat()))
                count+=1
            audit(c,'facebook_oauth',f'connected={count}')
        flash(f'Đã lưu {count} fanpage. Cần cấu hình webhook và đăng ký subscribed_apps để nhận tin nhắn.','success')
    except (requests.RequestException,KeyError,ValueError,InvalidToken) as e:
        app.logger.exception('Facebook OAuth error')
        flash('Không thể kết nối Facebook. Kiểm tra quyền Meta và cấu hình OAuth.','error')
    return redirect(url_for('pages'))

@app.route('/facebook/webhook',methods=['GET','POST'])
@csrf.exempt
def facebook_webhook():
    if request.method=='GET':
        if request.args.get('hub.mode')=='subscribe' and os.getenv('META_VERIFY_TOKEN') and hmac.compare_digest(request.args.get('hub.verify_token',''),os.environ['META_VERIFY_TOKEN']):
            return request.args.get('hub.challenge',''),200
        abort(403)
    secret=os.getenv('META_APP_SECRET')
    if not secret:abort(503)
    raw=request.get_data()
    signature=request.headers.get('X-Hub-Signature-256','')
    expected='sha256='+hmac.new(secret.encode(),raw,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature,expected):abort(403)
    payload=request.get_json(silent=True) or {}
    if payload.get('object')!='page':return 'EVENT_RECEIVED',200
    with conn() as c:
        for entry in payload.get('entry',[]):
            page_fb_id=str(entry.get('id',''))
            connection=c.execute('SELECT shop_id,page_id FROM facebook_connections WHERE fb_page_id=?',(page_fb_id,)).fetchone()
            if not connection:continue
            sid=connection['shop_id'];pid=connection['page_id']
            for ev in entry.get('messaging',[]):
                msg=ev.get('message') or {}
                sender=str((ev.get('sender') or {}).get('id',''))
                if not sender or not msg or msg.get('is_echo'):continue
                mid=str(msg.get('mid',''))
                if not mid:continue
                if c.execute('SELECT 1 FROM webhook_events WHERE mid=?',(mid,)).fetchone():continue
                c.execute('INSERT INTO webhook_events(mid,received_at) VALUES(?,?)',(mid,now().isoformat()))
                customer=c.execute('SELECT id FROM customers WHERE shop_id=? AND phone=?',(sid,'fb:'+sender)).fetchone()
                if not customer:
                    c.execute('INSERT INTO customers(shop_id,name,phone) VALUES(?,?,?)',(sid,'Facebook '+sender[-6:],'fb:'+sender))
                    cid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
                else:cid=customer['id']
                conversation=c.execute('SELECT id FROM conversations WHERE shop_id=? AND page_id=? AND customer_id=?',(sid,pid,cid)).fetchone()
                if not conversation:
                    c.execute('INSERT INTO conversations(shop_id,page_id,customer_id,tag,updated_at) VALUES(?,?,?,?,?)',(sid,pid,cid,'Khách mới',now().isoformat()))
                    vid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
                else:vid=conversation['id']
                body=msg.get('text') or '[Tin nhắn có tệp đính kèm]'
                c.execute('INSERT INTO messages(shop_id,conversation_id,sender,body,created_at) VALUES(?,?,?,?,?)',(sid,vid,'customer',body[:10000],now().isoformat()))
                c.execute('UPDATE conversations SET unread=1,updated_at=? WHERE id=? AND shop_id=?',(now().isoformat(),vid,sid))
    return 'EVENT_RECEIVED',200

@app.route('/facebook/conversations/<int:cid>/send',methods=['POST'])
@login_required
def facebook_send(cid):
    shop=shop_access()
    if not shop:return redirect(url_for('inbox'))
    body=request.form.get('body','').strip()
    if not body or len(body)>2000:flash('Tin nhắn phải có từ 1 đến 2000 ký tự.','error');return redirect(url_for('inbox',id=cid))
    with conn() as c:
        row=c.execute("""SELECT v.id,cu.phone,fc.fb_page_id,fc.token_encrypted FROM conversations v JOIN customers cu ON cu.id=v.customer_id JOIN facebook_connections fc ON fc.page_id=v.page_id AND fc.shop_id=v.shop_id WHERE v.id=? AND v.shop_id=?""",(cid,shop['id'])).fetchone()
    if not row or not row['phone'].startswith('fb:'):abort(404)
    try:
        token=token_cipher().decrypt(row['token_encrypted'].encode()).decode()
        graph('me/messages',token,method='POST',data={'recipient':{'id':row['phone'][3:]},'message':{'text':body},'messaging_type':'RESPONSE'})
    except (requests.RequestException,InvalidToken,ValueError):
        app.logger.exception('Facebook send failed')
        flash('Facebook không chấp nhận tin nhắn. Kiểm tra quyền gửi và cửa sổ nhắn tin của Meta.','error')
        return redirect(url_for('inbox',id=cid))
    with conn() as c:
        c.execute('INSERT INTO messages(shop_id,conversation_id,sender,body,created_at) VALUES(?,?,?,?,?)',(shop['id'],cid,'staff',body,now().isoformat()))
        c.execute('UPDATE conversations SET updated_at=?,unread=0 WHERE id=? AND shop_id=?',(now().isoformat(),cid,shop['id']))
        audit(c,'facebook_send',f'conversation={cid}')
    flash('Đã gửi tin nhắn qua Facebook.','success')
    return redirect(url_for('inbox',id=cid))

@app.route('/facebook/pages/<int:pid>/subscribe',methods=['POST'])
@roles('owner','manager')
def facebook_subscribe(pid):
    shop=shop_access()
    if not shop:return redirect(url_for('pages'))
    with conn() as c:connection=c.execute('SELECT * FROM facebook_connections WHERE page_id=? AND shop_id=?',(pid,shop['id'])).fetchone()
    if not connection:abort(404)
    try:
        token=token_cipher().decrypt(connection['token_encrypted'].encode()).decode()
        graph(connection['fb_page_id']+'/subscribed_apps',token,method='POST',data={'subscribed_fields':['messages','messaging_postbacks']})
        flash('Đã yêu cầu đăng ký webhook cho fanpage.','success')
    except (requests.RequestException,InvalidToken,ValueError):flash('Không đăng ký được webhook. Kiểm tra quyền ứng dụng Meta.','error')
    return redirect(url_for('pages'))
@app.route('/health')
def health():return jsonify(status='ok')
if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.getenv('PORT','8080')),debug=False)
