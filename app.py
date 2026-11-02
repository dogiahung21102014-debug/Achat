
import os,sqlite3,json,re
from flask import Flask,request,session,redirect,render_template_string,flash
from werkzeug.security import generate_password_hash,check_password_hash
app=Flask(__name__);app.secret_key=os.getenv('SECRET_KEY','CHANGE_ME_BEFORE_HOSTING')
DB=os.getenv('DATABASE_PATH','achat.db')
def db():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;return c
def init():
 with db() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS shops(id INTEGER PRIMARY KEY,name TEXT);
  CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT UNIQUE,passhash TEXT,role TEXT,shop INTEGER);
  CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,shop INTEGER,sku TEXT,name TEXT,price INTEGER,stock INTEGER);
  CREATE TABLE IF NOT EXISTS chats(id INTEGER PRIMARY KEY,shop INTEGER,customer TEXT,messages TEXT,tags TEXT);
  CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY,shop INTEGER,chat INTEGER,sku TEXT,qty INTEGER,price INTEGER,status TEXT,source TEXT);
  CREATE TABLE IF NOT EXISTS tags(id INTEGER PRIMARY KEY,shop INTEGER,name TEXT,color TEXT);''')
  if c.execute('SELECT count(*) FROM users').fetchone()[0]:return
  c.executemany('INSERT INTO shops VALUES(?,?)',[(1,'Tổng kho Đan Đan'),(2,'Shop Thời Trang')])
  for i,(name,role,shop) in enumerate([('admin','owner',None),('dan','shop_owner',1),('nhanvien','staff',1),('thoitrang','shop_owner',2)],1):
   c.execute('INSERT INTO users VALUES(?,?,?,?,?)',(i,name,generate_password_hash('Achat@123'),role,shop))
  c.executemany('INSERT INTO products(shop,sku,name,price,stock) VALUES(?,?,?,?,?)',[(1,'QN01','Quần ống rộng nữ',179000,100),(1,'DP02','Dép siêu nhẹ',99000,80),(2,'AO01','Áo thun',129000,60)])
  c.executemany('INSERT INTO chats(shop,customer,messages,tags) VALUES(?,?,?,?)',[(1,'Nguyễn Thị Lan',json.dumps(['Khách: Chị lấy 2 quần mã QN01, SĐT 0987654321, địa chỉ 123 Nguyễn Văn Cừ Nam Định.','Shop: Dạ em chào chị.'],ensure_ascii=False),json.dumps(['Chưa chốt'],ensure_ascii=False)),(1,'Trần Văn Minh',json.dumps(['Khách: Dép DP02 còn không?'],ensure_ascii=False),json.dumps(['Chưa ai tương tác'],ensure_ascii=False)),(2,'Lê Thị Mai',json.dumps(['Khách: Áo AO01 còn không?'],ensure_ascii=False),'[]')])
  for shop in (1,2):
   for name,color in [('Chưa ai tương tác','#64748b'),('Đang tư vấn','#eab308'),('Chưa chốt','#2563eb'),('Đã chốt','#16a34a'),('Đã lên đơn','#22c55e'),('Chưa đẩy đơn','#f97316'),('Đã đẩy đơn','#0ea5e9'),('Cần kiểm tra','#a855f7'),('AI Check','#8b5cf6'),('FB Agent','#0d9488'),('AI tạo đơn','#15803d'),('Nhân viên tạo đơn','#64748b'),('Đã huỷ','#ef4444')]:
    c.execute('INSERT INTO tags(shop,name,color) VALUES(?,?,?)',(shop,name,color))
def user():
 if 'uid' not in session:return None
 with db() as c:return c.execute('SELECT * FROM users WHERE id=?',(session['uid'],)).fetchone()
def shop():
 u=user();return int(session.get('shop',1)) if u['role']=='owner' else u['shop']
def badge(name,colors):
 from markupsafe import escape
 return '<span class="badge"><i style="background:'+colors.get(name,'#64748b')+'"></i>'+str(escape(name))+'</span>'
HTML='''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Achat</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f1f5fb;color:#18324c;font:14px Arial}.shell{display:flex;min-height:100vh}.nav{width:205px;background:#142b46;color:white;padding:18px;flex-shrink:0}.nav a{display:block;color:white;text-decoration:none;padding:12px;border-radius:9px}.nav a:hover{background:#2563eb}.main{flex:1;min-width:0}.top{background:white;padding:19px 25px;display:flex;justify-content:space-between}.content{padding:18px}.card{background:white;border:1px solid #e1e7f0;border-radius:13px;padding:17px;margin-bottom:12px}.chat{display:grid;grid-template-columns:250px minmax(290px,1fr) 315px;gap:12px}.badge{display:inline-flex;align-items:center;background:#f1f5f9;border-radius:15px;padding:5px 9px;margin:3px}.badge i{width:9px;height:9px;border-radius:50%;margin-right:6px}.btn{background:#1769ef;color:white;border:0;border-radius:8px;padding:10px 12px;cursor:pointer}.green{background:#16a34a}.orange{background:#ea8a15}input,select{padding:9px;border:1px solid #cbd5e1;border-radius:7px;max-width:100%}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:10px;border-bottom:1px solid #e5eaf2}th{background:#f7f9fd}.bubble{background:#e8eef5;padding:13px;border-radius:12px;margin:12px 0}.bubble.shop{background:#1769ef;color:white;margin-left:25%}.person{display:block;padding:14px;border-bottom:1px solid #e8eef5;text-decoration:none;color:#18324c}.person:hover{background:#eaf1ff}.note{padding:11px;background:#fff4dd;border-radius:8px;margin:10px 0}.muted{color:#64748b}.field{display:block;margin:8px 0}.field input,.field select{width:100%}@media(max-width:1000px){.chat{display:block}}@media(max-width:650px){.nav{width:110px;padding:8px}.nav a{font-size:11px}.content{padding:7px}}</style>
<div class="shell"><nav class="nav"><h1>◈ Achat</h1><a href="/">Tổng quan</a><a href="/chat">Hội thoại Facebook</a><a href="/orders">Đơn hàng</a><a href="/products">Sản phẩm</a><a href="/tags">Hashtag</a><a href="/users">Nhân viên</a><a href="/shops">Cửa hàng</a><a href="/logout">Đăng xuất</a></nav><main class="main"><header class="top"><b>{{title}}</b><span>{{who}} · {{shopname}}</span></header><div class="content">{% for m in get_flashed_messages() %}<div class="note">{{m}}</div>{% endfor %}{{body|safe}}</div></main></div></html>'''
def page(title,body):
 u=user();s=shop()
 with db() as c:row=c.execute('SELECT name FROM shops WHERE id=?',(s,)).fetchone()
 return render_template_string(HTML,title=title,body=body,who=u['username'],shopname=row['name'] if row else '')
@app.before_request
def guard():
 if request.endpoint not in ('login','health','static') and not user():return redirect('/login')
@app.route('/login',methods=['GET','POST'])
def login():
 if request.method=='POST':
  with db() as c:u=c.execute('SELECT * FROM users WHERE username=?',(request.form.get('username'),)).fetchone()
  if u and check_password_hash(u['passhash'],request.form.get('password','')):
   session.clear();session['uid']=u['id'];return redirect('/')
  flash('Sai tài khoản hoặc mật khẩu')
 return render_template_string('<meta charset="utf-8"><div style="font:16px Arial;max-width:360px;margin:12vh auto;padding:30px;box-shadow:0 2px 20px #ddd"><h1>◈ Achat</h1><p>Đăng nhập bản dùng thử</p>{% for m in get_flashed_messages() %}<p>{{m}}</p>{% endfor %}<form method="post"><p><input name="username" placeholder="Tài khoản" required></p><p><input name="password" type="password" placeholder="Mật khẩu" required></p><button>Đăng nhập</button></form></div>')
@app.route('/logout')
def logout():session.clear();return redirect('/login')
@app.route('/health')
def health():return {'status':'ok'}
@app.route('/')
def home():
 s=shop()
 with db() as c:
  counts=[c.execute('SELECT count(*) FROM '+t+' WHERE shop=?',(s,)).fetchone()[0] for t in ('chats','orders','products')]
  waiting=c.execute("SELECT count(*) FROM orders WHERE shop=? AND status='Đã lên đơn'",(s,)).fetchone()[0]
 body='<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px">'+''.join('<div class="card"><h3>'+label+'</h3><h1>'+str(n)+'</h1></div>' for label,n in zip(['Hội thoại','Đơn hàng','Sản phẩm','Chờ đẩy vận chuyển'],counts+[waiting]))+'</div><div class="card"><h2>Achat — Quản lý bán hàng</h2><p>Giao diện thuần Việt · 3 cột hội thoại · hashtag chấm màu · chốt đơn trước, đẩy đơn sau.</p><div class="note">BẢN DEMO: Tin nhắn, AI Check và đẩy vận chuyển chỉ mô phỏng. Chưa kết nối Facebook, FB Agent hay hãng vận chuyển thật.</div></div>'
 return page('Tổng quan',body)
@app.route('/chat')
def chats():
 from markupsafe import escape as e
 s=shop()
 with db() as c:
  rows=c.execute('SELECT * FROM chats WHERE shop=?',(s,)).fetchall()
  colors={x['name']:x['color'] for x in c.execute('SELECT * FROM tags WHERE shop=?',(s,))}
  products=c.execute('SELECT * FROM products WHERE shop=?',(s,)).fetchall()
  cid=int(request.args.get('id',rows[0]['id'] if rows else 0));v=next((x for x in rows if x['id']==cid),None)
 body='<div class="chat"><div class="card"><h3>Hội thoại</h3>'+''.join('<a class="person" href="/chat?id='+str(x['id'])+'"><b>'+str(e(x['customer']))+'</b><br>'+''.join(badge(t,colors) for t in json.loads(x['tags']))+'</a>' for x in rows)+'</div><div class="card"><h3>'+str(e(v['customer'])) if v else '<div class="chat"><div class="card">Chưa có hội thoại</div>'
 if not v:return page('Hội thoại Facebook',body+'</div>')
 body+='<p class="muted">Messenger · Dữ liệu mẫu</p>'
 for msg in json.loads(v['messages']):
  body+='<div class="bubble '+('shop' if msg.startswith('Shop:') else '')+'">'+str(e(msg))+'</div>'
 body+='<form method="post" action="/message/'+str(cid)+'"><input name="text" placeholder="Tin nhắn thử..." required style="width:75%"><button class="btn">Gửi thử</button></form><div class="note">AI Check: thử nhận dạng mã SKU, số lượng, điện thoại và địa chỉ. FB Agent chưa kết nối thật.</div><form method="post" action="/aicheck/'+str(cid)+'"><button class="btn green">AI Check thử</button></form></div>'
 body+='<div class="card"><h3>Khách hàng và đơn hàng</h3><b>'+str(e(v['customer']))+'</b><h4>Hashtag</h4>'+''.join(badge(t,colors) for t in json.loads(v['tags']))
 body+='<form method="post" action="/tagchat/'+str(cid)+'"><select name="tag">'+''.join('<option>'+str(e(n))+'</option>' for n in colors)+'</select><button class="btn">Gắn hashtag</button></form>'
 body+='<h3>Chốt đơn</h3><form method="post" action="/createorder"><input type="hidden" name="chat" value="'+str(cid)+'"><label class="field">Mã sản phẩm<select name="product">'+''.join('<option value="'+str(x['id'])+'">'+str(e(x['sku']))+' — '+str(e(x['name']))+'</option>' for x in products)+'</select></label><label class="field">Số lượng<input type="number" name="qty" min="1" value="1" required></label><button class="btn green">Chốt và lưu đơn</button></form><p class="muted">Đơn được lưu để đẩy sau tại mục Đơn hàng.</p></div></div>'
 return page('Hội thoại Facebook',body)
def addtag(c,v,t):
 a=json.loads(v['tags'])
 if t not in a:a.append(t)
 c.execute('UPDATE chats SET tags=? WHERE id=?',(json.dumps(a,ensure_ascii=False),v['id']))
@app.route('/tagchat/<int:cid>',methods=['POST'])
def tagchat(cid):
 with db() as c:
  v=c.execute('SELECT * FROM chats WHERE id=? AND shop=?',(cid,shop())).fetchone()
  t=c.execute('SELECT * FROM tags WHERE shop=? AND name=?',(shop(),request.form.get('tag'))).fetchone()
  if v and t:addtag(c,v,t['name'])
 return redirect('/chat?id='+str(cid))
@app.route('/message/<int:cid>',methods=['POST'])
def message(cid):
 with db() as c:
  v=c.execute('SELECT * FROM chats WHERE id=? AND shop=?',(cid,shop())).fetchone()
  if v:
   a=json.loads(v['messages']);a.append('Shop: '+request.form.get('text','')[:1000]);c.execute('UPDATE chats SET messages=? WHERE id=?',(json.dumps(a,ensure_ascii=False),cid))
 flash('Đã thêm tin nhắn MÔ PHỎNG, không gửi Facebook.')
 return redirect('/chat?id='+str(cid))
def create(c,v,p,qty,source):
 if qty<1 or qty>p['stock']:raise ValueError('Không đủ hàng hoặc số lượng không hợp lệ')
 c.execute('INSERT INTO orders(shop,chat,sku,qty,price,status,source) VALUES(?,?,?,?,?,?,?)',(shop(),v['id'],p['sku'],qty,p['price'],'Đã lên đơn',source))
 c.execute('UPDATE products SET stock=stock-? WHERE id=?',(qty,p['id']))
 a=[t for t in json.loads(v['tags']) if t not in ('Chưa chốt','Chưa ai tương tác','Cần kiểm tra')]
 a+=['Đã chốt','Đã lên đơn','Chưa đẩy đơn',source]
 c.execute('UPDATE chats SET tags=? WHERE id=?',(json.dumps(list(dict.fromkeys(a)),ensure_ascii=False),v['id']))
@app.route('/createorder',methods=['POST'])
def createorder():
 with db() as c:
  v=c.execute('SELECT * FROM chats WHERE id=? AND shop=?',(request.form.get('chat'),shop())).fetchone()
  p=c.execute('SELECT * FROM products WHERE id=? AND shop=?',(request.form.get('product'),shop())).fetchone()
  if v and p:
   try:create(c,v,p,int(request.form.get('qty',0)),'Nhân viên tạo đơn');flash('Đã chốt và lưu đơn, chưa đẩy vận chuyển.')
   except ValueError as ex:flash(str(ex))
 return redirect('/chat?id='+request.form.get('chat',''))
@app.route('/aicheck/<int:cid>',methods=['POST'])
def aicheck():
 with db() as c:
  v=c.execute('SELECT * FROM chats WHERE id=? AND shop=?',(cid,shop())).fetchone()
  if not v:return redirect('/chat')
  text=' '.join(json.loads(v['messages']))
  prods=c.execute('SELECT * FROM products WHERE shop=?',(shop(),)).fetchall()
  matches=[p for p in prods if re.search(r'(?<!\\w)'+re.escape(p['sku'])+r'(?!\\w)',text,re.I)]
  qty=re.search(r'\\b(\\d+)\\s*(quần|áo|đôi|chiếc|cái)',text,re.I)
  phone=re.search(r'(?<!\\d)0\\d{9}(?!\\d)',text)
  addr=re.search(r'địa chỉ\\s+[^.]+',text,re.I)
  if len(matches)==1 and qty and phone and addr:
   try:create(c,v,matches[0],int(qty.group(1)),'AI tạo đơn');flash('AI Check thử: đã tạo đơn theo mã SKU. Không phải AI thật.')
   except ValueError as ex:addtag(c,v,'Cần kiểm tra');flash(str(ex))
  else:addtag(c,v,'Cần kiểm tra');flash('AI Check thử: thiếu thông tin hoặc không nhận dạng chắc chắn. Đã gắn Cần kiểm tra.')
 return redirect('/chat?id='+str(cid))
@app.route('/orders')
def orders():
 s=shop();status=request.args.get('status','')
 with db() as c:rows=c.execute('SELECT * FROM orders WHERE shop=? '+('AND status=?' if status else '')+' ORDER BY id DESC',(s,status) if status else (s,)).fetchall()
 body='<div class="card"><p>'+''.join('<a class="btn" style="margin:4px" href="/orders?status='+x+'">'+(x or 'Tất cả')+'</a>' for x in ('','Đã lên đơn','Đã đẩy đơn'))+'</p><form method="post" action="/dispatch"><button class="btn orange">Đẩy đơn đã chọn (MÔ PHỎNG)</button><table><tr><th>Chọn</th><th>Mã đơn</th><th>Khách</th><th>SKU</th><th>Số lượng</th><th>Tổng tiền</th><th>Trạng thái</th><th>Nguồn</th></tr>'
 with db() as c:
  for o in rows:
   customer=c.execute('SELECT customer FROM chats WHERE id=?',(o['chat'],)).fetchone()
   body+='<tr><td><input type="checkbox" name="id" value="'+str(o['id'])+'"></td><td>#'+str(o['id'])+'</td><td>'+customer['customer']+'</td><td>'+o['sku']+'</td><td>'+str(o['qty'])+'</td><td>'+format(o['qty']*o['price'],',')+'đ</td><td>'+o['status']+'</td><td>'+o['source']+'</td></tr>'
 return page('Đơn hàng',body+'</table></form></div>')
@app.route('/dispatch',methods=['POST'])
def dispatch():
 n=0
 with db() as c:
  for val in request.form.getlist('id'):
   if not val.isdigit():continue
   o=c.execute("SELECT * FROM orders WHERE id=? AND shop=? AND status='Đã lên đơn'",(int(val),shop())).fetchone()
   if not o:continue
   c.execute("UPDATE orders SET status='Đã đẩy đơn' WHERE id=?",(o['id'],));n+=1
   v=c.execute('SELECT * FROM chats WHERE id=? AND shop=?',(o['chat'],shop())).fetchone()
   if v:
    a=[x for x in json.loads(v['tags']) if x!='Chưa đẩy đơn'];a.append('Đã đẩy đơn')
    c.execute('UPDATE chats SET tags=? WHERE id=?',(json.dumps(list(dict.fromkeys(a)),ensure_ascii=False),v['id']))
 flash('Đã đổi trạng thái '+str(n)+' đơn (MÔ PHỎNG, không gọi hãng vận chuyển).')
 return redirect('/orders')
@app.route('/products',methods=['GET','POST'])
def products():
 from markupsafe import escape as e
 if request.method=='POST' and user()['role']!='staff':
  with db() as c:
   try:c.execute('INSERT INTO products(shop,sku,name,price,stock) VALUES(?,?,?,?,?)',(shop(),request.form['sku'].upper(),request.form['name'],int(request.form['price']),int(request.form['stock'])));flash('Đã thêm sản phẩm')
   except ValueError:flash('Dữ liệu không hợp lệ')
  return redirect('/products')
 with db() as c:rows=c.execute('SELECT * FROM products WHERE shop=?',(shop(),)).fetchall()
 body='<div class="card"><table><tr><th>Mã SKU</th><th>Sản phẩm</th><th>Giá</th><th>Tồn</th></tr>'+''.join('<tr><td>'+str(e(x['sku']))+'</td><td>'+str(e(x['name']))+'</td><td>'+str(x['price'])+'</td><td>'+str(x['stock'])+'</td></tr>' for x in rows)+'</table></div>'
 if user()['role']!='staff':body+='<div class="card"><h3>Thêm sản phẩm</h3><form method="post"><input name="sku" placeholder="Mã SKU" required><input name="name" placeholder="Tên sản phẩm" required><input name="price" type="number" min="0" placeholder="Giá" required><input name="stock" type="number" min="0" placeholder="Tồn" required><button class="btn">Thêm</button></form></div>'
 return page('Sản phẩm',body)
@app.route('/tags',methods=['GET','POST'])
def tags():
 if request.method=='POST' and user()['role']!='staff':
  name=request.form.get('name','').strip();color=request.form.get('color','#2563eb')
  if name and re.fullmatch('#[0-9a-fA-F]{6}',color):
   with db() as c:c.execute('INSERT INTO tags(shop,name,color) VALUES(?,?,?)',(shop(),name,color))
  return redirect('/tags')
 with db() as c:rows=c.execute('SELECT * FROM tags WHERE shop=?',(shop(),)).fetchall()
 body='<div class="card"><h3>Hashtag của cửa hàng</h3>'+''.join(badge(x['name'],{x['name']:x['color']}) for x in rows)+'</div>'
 if user()['role']!='staff':body+='<div class="card"><h3>Tạo hashtag</h3><form method="post"><input name="name" required placeholder="Tên hashtag"><input name="color" type="color" value="#2563eb"><button class="btn">Tạo</button></form></div>'
 return page('Hashtag',body)
@app.route('/users',methods=['GET','POST'])
def users():
 u=user()
 if request.method=='POST' and u['role']!='staff':
  role=request.form.get('role','staff')
  if u['role']!='owner':role='staff'
  sid=int(request.form.get('shop',shop())) if u['role']=='owner' else shop()
  with db() as c:
   try:c.execute('INSERT INTO users(username,passhash,role,shop) VALUES(?,?,?,?)',(request.form['username'],generate_password_hash(request.form['password']),role,None if role=='owner' else sid));flash('Đã tạo tài khoản')
   except sqlite3.IntegrityError:flash('Tài khoản đã tồn tại')
  return redirect('/users')
 with db() as c:
  rows=([u] if u['role']=='staff' else c.execute('SELECT * FROM users '+('' if u['role']=='owner' else 'WHERE shop=?'),() if u['role']=='owner' else (shop(),)).fetchall())
  shops=c.execute('SELECT * FROM shops').fetchall()
 body='<div class="card"><table><tr><th>Tài khoản</th><th>Vai trò</th><th>Shop</th></tr>'+''.join('<tr><td>'+x['username']+'</td><td>'+x['role']+'</td><td>'+str(x['shop'] or 'Toàn hệ thống')+'</td></tr>' for x in rows)+'</table></div>'
 if u['role']!='staff':
  body+='<div class="card"><h3>Thêm tài khoản</h3><form method="post"><input name="username" required placeholder="Tên đăng nhập"><input name="password" type="password" minlength="8" required placeholder="Mật khẩu"><select name="role"><option value="staff">Nhân viên</option>'
  if u['role']=='owner':body+='<option value="shop_owner">Chủ shop</option><option value="owner">Chủ hệ thống</option>'
  body+='</select>'
  if u['role']=='owner':body+='<select name="shop">'+''.join('<option value="'+str(x['id'])+'">'+x['name']+'</option>' for x in shops)+'</select>'
  body+='<button class="btn">Tạo</button></form></div>'
 return page('Nhân viên và phân quyền',body)
@app.route('/shops',methods=['GET','POST'])
def shops():
 u=user()
 if request.method=='POST' and u['role']=='owner':
  with db() as c:c.execute('INSERT INTO shops(name) VALUES(?)',(request.form['name'],))
  return redirect('/shops')
 with db() as c:rows=c.execute('SELECT * FROM shops '+('' if u['role']=='owner' else 'WHERE id=?'),() if u['role']=='owner' else (shop(),)).fetchall()
 body='<div class="card"><h3>Cửa hàng được phép xem</h3>'+''.join('<p>'+x['name']+'</p>' for x in rows)+'</div>'
 if u['role']=='owner':body+='<div class="card"><form method="post"><input name="name" placeholder="Tên shop mới" required><button class="btn">Thêm shop</button></form><form method="post" action="/switch"><select name="shop">'+''.join('<option value="'+str(x['id'])+'">'+x['name']+'</option>' for x in rows)+'</select><button class="btn">Chuyển shop</button></form></div>'
 return page('Cửa hàng',body)
@app.route('/switch',methods=['POST'])
def switch():
 if user()['role']=='owner':
  with db() as c:
   x=c.execute('SELECT id FROM shops WHERE id=?',(request.form.get('shop'),)).fetchone()
   if x:session['shop']=x['id']
 return redirect('/')
init()
if __name__=='__main__':app.run(port=5000)
