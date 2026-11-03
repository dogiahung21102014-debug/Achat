import os, sqlite3, secrets, functools, re
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app=Flask(__name__)
app.secret_key=os.getenv('SECRET_KEY','dev-only-change-this-secret')
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
        if not c.execute('SELECT 1 FROM users WHERE role=?',('superadmin',)).fetchone():
            t=now().isoformat(); c.execute('INSERT INTO users(shop_id,name,email,password_hash,role,created_at) VALUES(NULL,?,?,?,?,?)',('Quản trị hệ thống','admin@achat.local',generate_password_hash(os.getenv('ADMIN_PASSWORD','ChangeMe123!')),'superadmin',t))
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
@app.route('/health')
def health():return jsonify(status='ok')
if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.getenv('PORT','8080')),debug=False)
