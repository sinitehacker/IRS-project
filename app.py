"""ShopperStop Promotional Pricing Engine (standard-library HTTP service)."""
from __future__ import annotations
import json, logging, re, uuid
from copy import deepcopy
from datetime import datetime, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

TIERS = {
    'regular': {'id': 'regular', 'name': 'Regular', 'slabs': [[5000, 0], [10000, 10], [None, 20]]},
    'premium': {'id': 'premium', 'name': 'Premium', 'slabs': [[5000, 10], [10000, 20], [None, 30]]},
}
PROMOTIONS, AUDIT = {}, []

def error(message, status=400, field=None):
    body={'error': {'code': 'VALIDATION_ERROR' if status == 400 else 'NOT_FOUND', 'message': message}}
    if field: body['error']['field'] = field
    return body, status

def number(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(field + ' must be a non-negative number')
    return float(value)

def money(v): return round(v + 1e-9, 2)

def slab_discount(amount, tier):
    start = 0.0; discount = 0.0; details=[]
    for ceiling, rate in tier['slabs']:
        upper = amount if ceiling is None else min(amount, ceiling)
        portion = max(0, upper-start)
        if portion:
            saved = portion * rate / 100
            details.append({'from': start, 'to': upper, 'ratePercent': rate, 'discount': money(saved)})
            discount += saved
        start = upper
        if start >= amount: break
    return discount, details

def active_promotions(context, provided=None):
    values = provided if provided is not None else PROMOTIONS.values()
    now = context.get('time') or datetime.now().strftime('%H:%M')
    store = context.get('storeId')
    result=[]
    for p in values:
        if not p.get('active', False) or p.get('deleted'): continue
        if p.get('storeIds') and store not in p['storeIds']: continue
        window=p.get('timeWindow')
        if window and not (window['start'] <= now <= window['end']): continue
        result.append(p)
    return sorted(result, key=lambda p: p.get('priority', 100))

def calculate(payload, promos=None):
    customer=payload.get('customer', {}); tier_id=customer.get('tier', 'regular').lower()
    if tier_id not in TIERS: raise ValueError('customer.tier must be regular or premium')
    items=payload.get('items')
    if not isinstance(items, list) or not items: raise ValueError('items must be a non-empty array')
    normalized=[]
    for i, item in enumerate(items):
        if not isinstance(item, dict) or not item.get('name'): raise ValueError('items[%d].name is required' % i)
        qty=number(item.get('quantity', 1), 'items[%d].quantity' % i); price=number(item.get('unitPrice'), 'items[%d].unitPrice' % i)
        if qty <= 0: raise ValueError('items[%d].quantity must be greater than zero' % i)
        normalized.append({**item, 'quantity':qty, 'unitPrice':price, 'lineTotal':money(qty*price)})
    subtotal=sum(x['lineTotal'] for x in normalized); tier=TIERS[tier_id]
    slab, slabs=slab_discount(subtotal, tier); running=subtotal-slab
    applied=[{'type':'SLAB', 'name':tier['name']+' tier discount', 'discount':money(slab), 'breakdown':slabs}]
    for p in active_promotions(payload.get('context', {}), promos):
        kind=p.get('type'); value=number(p.get('value', 0), 'promotion.value'); discount=0.0
        if kind == 'FLAT' and running >= number(p.get('minimumOrder', 0), 'promotion.minimumOrder'): discount=value
        elif kind in ('PERCENTAGE', 'TIME'):
            discount=running*value/100
        elif kind == 'CATEGORY':
            eligible=sum(x['lineTotal'] for x in normalized if x.get('category') == p.get('category'))
            discount=eligible*value/100
        elif kind == 'BUY_X_GET_Y':
            for item in normalized:
                if not p.get('category') or item.get('category') == p['category']:
                    discount += (item['quantity'] // (int(p.get('buy', 1))+int(p.get('get', 1)))) * int(p.get('get', 1)) * item['unitPrice']
        else: continue
        cap=p.get('maxDiscount')
        if cap is not None: discount=min(discount, number(cap, 'promotion.maxDiscount'))
        discount=min(discount, running)
        if discount: running-=discount; applied.append({'promotionId':p.get('id'), 'type':kind, 'name':p.get('name'), 'discount':money(discount)})
    total_discount=money(subtotal-running)
    return {'currency':payload.get('currency','INR'),'customerTier':tier_id,'subtotal':money(subtotal),'discountTotal':total_discount,'finalTotal':money(running),'discountPercent':money(total_discount/subtotal*100),'appliedDiscounts':applied,'items':normalized}

def create_promotion(data, existing=None):
    required=['name','type']; allowed={'FLAT','PERCENTAGE','CATEGORY','BUY_X_GET_Y','TIME'}
    if not all(data.get(k) for k in required): raise ValueError('promotion name and type are required')
    if data['type'] not in allowed: raise ValueError('unsupported promotion type')
    p=deepcopy(existing or {}); p.update(data); p.setdefault('id',str(uuid.uuid4())); p.setdefault('active',False); p.setdefault('priority',100); p.setdefault('version',1); p.setdefault('createdAt',datetime.utcnow().isoformat()+'Z'); p['updatedAt']=datetime.utcnow().isoformat()+'Z'
    return p

class Handler(BaseHTTPRequestHandler):
    server_version='ShopperStopPPE/1.0'
    def log_message(self, fmt, *args): logging.info('%s - %s', self.headers.get('X-Correlation-ID','-'), fmt % args)
    def send(self, body, status=200):
        data=json.dumps(body, default=str).encode(); self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(data))); self.send_header('X-Correlation-ID',self.headers.get('X-Correlation-ID',str(uuid.uuid4()))); self.end_headers(); self.wfile.write(data)
    def page(self):
        html=r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ShopperStop Pricing Engine</title><style>*{box-sizing:border-box}body{margin:0;background:#f5f6f8;color:#252b35;font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}header{background:#fff;border-bottom:1px solid #dce1e7;padding:20px max(20px,calc((100% - 1160px)/2))}h1{font-size:21px;margin:0}h1 span{font-weight:400;color:#6b7280}.sub{margin:3px 0 0;color:#687080}.layout{max-width:1160px;margin:24px auto;padding:0 20px;display:grid;grid-template-columns:minmax(0,1fr) 285px;gap:20px}.panel{background:#fff;border:1px solid #dce1e7;border-radius:6px;padding:20px;box-shadow:0 1px 2px #00000008}h2{font-size:16px;margin:0 0 15px}.section{border-top:1px solid #e5e7eb;margin-top:20px;padding-top:20px}.section:first-child{border:0;margin-top:0;padding-top:0}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.field{display:flex;flex-direction:column;gap:5px}.label,label{font-size:13px;font-weight:600;color:#4e5866}input,textarea{border:1px solid #bbc4ce;border-radius:4px;padding:9px 10px;font:inherit;color:#202633;background:#fff}textarea{width:100%;min-height:185px;resize:vertical;font:13px/1.45 ui-monospace,monospace}input:focus,textarea:focus{outline:2px solid #bed2e8;border-color:#4478a8}.radios{display:flex;gap:18px}.radios label,.check{font-weight:400;display:flex;align-items:center;gap:6px}.hint{font-size:12px;color:#687080}button{background:#8a1738;border:1px solid #8a1738;color:white;border-radius:4px;padding:10px 16px;font-weight:600;cursor:pointer}button:disabled{opacity:.65}.actions{display:flex;gap:12px;align-items:center;margin-top:16px}.message{display:none;margin-top:13px;padding:10px;background:#fff3f3;color:#942033;border:1px solid #e6bbc0;border-radius:4px}.summary{display:none}.metrics{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid #dce1e7;border-radius:5px;overflow:hidden}.metric{padding:12px;border-right:1px solid #dce1e7}.metric:last-child{border:0}.metric small{display:block;color:#687080}.metric strong{font-size:17px}.final{background:#f1f7f2}.final strong,.amount{color:#17633a}.discounts{list-style:none;padding:0;margin:0}.discounts li{border:1px solid #e1e5ea;border-radius:4px;margin-top:8px;padding:10px}.discount-head{display:flex;justify-content:space-between;gap:10px}.tag{font-size:11px;background:#eef1f4;color:#596575;border-radius:3px;padding:2px 6px;margin-left:6px}.amount{font-weight:700;white-space:nowrap}details{margin-top:8px;color:#566171}details ul{margin:6px 0 0;padding-left:18px}pre{background:#202633;color:#eaf0f8;padding:12px;border-radius:4px;overflow:auto;font-size:12px}.promotion{padding:12px 0;border-bottom:1px solid #e5e7eb}.promotion:last-child{border:0}.promotion strong{display:block}.promotion p{margin:3px 0 0;color:#687080;font-size:12px}.status{border-left:3px solid #2e7d4f;padding-left:8px;color:#53606d;font-size:12px}.bad{border-color:#c23d3d}.footer{max-width:1160px;margin:auto;padding:0 20px 24px;color:#687080;font-size:12px}a{color:#416d99}.empty{color:#687080}@media(max-width:800px){.layout{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(2,1fr)}.metric:nth-child(2){border-right:0}.metric:nth-child(-n+2){border-bottom:1px solid #dce1e7}}@media(max-width:430px){.layout{margin:16px auto;padding:0 12px}.grid,.metrics{grid-template-columns:1fr}.metric{border-right:0;border-bottom:1px solid #dce1e7}.metric:last-child{border:0}}</style></head><body><header><h1>ShopperStop <span>/ Promotional Pricing Engine</span></h1><p class="sub">Bill calculation preview</p></header><main class="layout"><section class="panel"><div class="section"><h2>Customer and calculation</h2><div class="field"><span class="label">Customer tier</span><div class="radios"><label><input type="radio" name="tier" value="regular" checked>Regular</label><label><input type="radio" name="tier" value="premium">Premium</label></div></div><div class="grid" style="margin-top:15px"><div class="field"><label for="store">Store ID <span class="hint">(optional)</span></label><input id="store" placeholder="e.g. BLR-014"></div><div class="field"><label for="coupon">Coupon code <span class="hint">(optional)</span></label><input id="coupon" placeholder="e.g. WEEKEND10"></div><div class="field"><label for="timestamp">Calculation timestamp</label><input id="timestamp" type="datetime-local"></div><label class="check" style="align-self:end;padding-bottom:10px"><input id="preview" type="checkbox" checked>Preview mode (no changes saved)</label></div></div><div class="section"><h2>Cart items</h2><p class="hint">Enter a JSON array. Each item needs <code>name</code>, <code>quantity</code>, and <code>unitPrice</code>.</p><textarea id="cart" aria-label="Cart JSON"></textarea><div id="message" class="message" role="alert"></div><div class="actions"><button id="calculate" type="button">Calculate bill</button><span class="hint">Calculations are idempotent.</span></div></div><section id="summary" class="summary section"><h2>Bill summary</h2><div class="metrics"><div class="metric"><small>Subtotal</small><strong id="subtotal">—</strong></div><div class="metric"><small>Total discount</small><strong id="discount">—</strong></div><div class="metric final"><small>Final total</small><strong id="final">—</strong></div><div class="metric"><small>Savings</small><strong id="percent">—</strong></div></div><div style="margin-top:20px"><h2>Applied discounts</h2><ul id="discounts" class="discounts"></ul></div><details style="margin-top:20px"><summary>API Response (JSON)</summary><pre id="raw"></pre></details></section></section><aside class="panel"><h2>Active promotions</h2><div id="promotions"><p class="empty">Loading promotions…</p></div><div class="section"><h2>Backend status</h2><p id="health" class="status">Checking API health…</p><p class="hint">Endpoint<br><code>POST /api/v1/bills/calculate</code></p><p class="hint">Version 1.0.0 · <a href="/openapi.json">OpenAPI / Swagger</a></p></div></aside></main><footer class="footer">ShopperStop internal pricing tools · API version 1.0.0</footer><script>const $=id=>document.getElementById(id),money=n=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:2}).format(n||0),samples=[{name:'Happy Hour',type:'TIME',value:5,detail:'5% off from 5 PM to 8 PM'},{name:'Electronics event',type:'CATEGORY',value:10,detail:'10% off eligible electronics'}];$('cart').value=JSON.stringify([{name:'Television',category:'Electronics',quantity:1,unitPrice:15000},{name:'Cotton shirt',category:'Apparel',quantity:2,unitPrice:1200}],null,2);let d=new Date();d.setMinutes(d.getMinutes()-d.getTimezoneOffset());$('timestamp').value=d.toISOString().slice(0,16);function err(m){$('message').textContent=m;$('message').style.display='block'}function valid(items){if(!Array.isArray(items)||!items.length)throw Error('Add at least one cart item.');items.forEach((x,i)=>{if(!String(x.name||'').trim())throw Error(`Item ${i+1}: name is required.`);if(typeof x.unitPrice!=='number'||x.unitPrice<0)throw Error(`Item ${i+1}: unitPrice must be a non-negative number.`);if(typeof x.quantity!=='number'||x.quantity<=0)throw Error(`Item ${i+1}: quantity must be greater than zero.`)})}function esc(v){return String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}function render(r){$('summary').style.display='block';$('subtotal').textContent=money(r.subtotal);$('discount').textContent='−'+money(r.discountTotal);$('final').textContent=money(r.finalTotal);$('percent').textContent=(r.discountPercent||0)+'%';$('raw').textContent=JSON.stringify(r,null,2);$('discounts').innerHTML=(r.appliedDiscounts||[]).map(x=>{let b=(x.breakdown||[]).filter(y=>y.ratePercent||y.discount).map(y=>`<li>${money(y.from)} – ${money(y.to)} at ${y.ratePercent}%: <b>−${money(y.discount)}</b></li>`).join('');return `<li><div class="discount-head"><div><strong>${esc(x.name||'Promotion')}</strong><span class="tag">${esc(x.type||'DISCOUNT')}</span></div><span class="amount">−${money(x.discount)}</span></div>${b?`<details><summary>Slab breakdown</summary><ul>${b}</ul></details>`:''}</li>`}).join('')||'<li class="empty">No discounts applied.</li>';$('summary').scrollIntoView({behavior:'smooth',block:'nearest'})}async function calculate(){let items;$('message').style.display='none';try{items=JSON.parse($('cart').value);valid(items)}catch(e){err(e.message.startsWith('Unexpected')?'Cart JSON is invalid. Check commas, quotes, and brackets.':e.message);return}let context={},dt=$('timestamp').value;if($('store').value.trim())context.storeId=$('store').value.trim();if(dt)context.time=dt.slice(11,16);let body={customer:{tier:document.querySelector('input[name=tier]:checked').value},items,context,preview:$('preview').checked};if($('coupon').value.trim())body.couponCode=$('coupon').value.trim();let btn=$('calculate');btn.disabled=true;btn.textContent='Calculating…';try{let res=await fetch('/api/v1/bills/calculate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),data=await res.json();if(!res.ok)throw Error(data.error?.message||'Calculation could not be completed.');render(data)}catch(e){err(e.message)}finally{btn.disabled=false;btn.textContent='Calculate bill'}}$('calculate').onclick=calculate;function promo(x){return `<div class="promotion"><strong>${esc(x.name||'Untitled promotion')}</strong><span class="tag">${esc(x.type||'PROMOTION')}</span> <span class="hint">${x.value?(x.type==='FLAT'?money(x.value):x.value+'% off'):''}</span><p>${esc(x.detail||x.category||'Active promotion')}</p></div>`}async function boot(){try{let r=await fetch('/health'),x=await r.json();if(!r.ok)throw Error();$('health').textContent='● Online · '+(x.service||'API available')}catch(e){$('health').classList.add('bad');$('health').textContent='● Unavailable · Check local API'}try{let r=await fetch('/api/v1/promotions?active=true'),x=await r.json(),rows=x.data||[];$('promotions').innerHTML=(rows.length?rows:samples).map(promo).join('')}catch(e){$('promotions').innerHTML=samples.map(promo).join('')}}boot();</script></body></html>'''.encode()
        self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(html))); self.end_headers(); self.wfile.write(html)
    def read(self):
        try: return json.loads(self.rfile.read(int(self.headers.get('Content-Length','0')) or 0) or '{}')
        except json.JSONDecodeError: raise ValueError('request body must be valid JSON')
    def route(self):
        path=urlparse(self.path).path; method=self.command; parts=path.strip('/').split('/')
        if method=='GET' and path=='/': self.page(); return None, None
        if method=='GET' and path=='/health': return {'status':'ok','service':'promotional-pricing-engine'},200
        if method=='GET' and path=='/openapi.json': return OPENAPI,200
        if path=='/api/v1/bills/calculate' and method=='POST': return calculate(self.read()),200
        if path=='/api/v1/promotions/simulate' and method=='POST':
            body=self.read(); promotion=create_promotion(body.get('promotion',{})); promotion['active']=True
            return calculate(body.get('bill',{}), list(PROMOTIONS.values())+[promotion]),200
        if path=='/api/v1/customer-tiers':
            if method=='GET': return {'data':list(TIERS.values())},200
            if method=='POST':
                data=self.read(); ident=data.get('id','').lower()
                if not ident or not isinstance(data.get('slabs'),list): raise ValueError('id and slabs are required')
                TIERS[ident]={'id':ident,'name':data.get('name',ident.title()),'slabs':data['slabs']}; return TIERS[ident],201
        if path=='/api/v1/promotions' and method=='GET':
            q=parse_qs(urlparse(self.path).query); rows=[p for p in PROMOTIONS.values() if not p.get('deleted')]
            if 'active' in q: rows=[p for p in rows if p['active']==(q['active'][0].lower()=='true')]
            return {'data':rows,'count':len(rows)},200
        if path=='/api/v1/promotions' and method=='POST':
            p=create_promotion(self.read()); PROMOTIONS[p['id']]=p; AUDIT.append({'action':'CREATE','promotionId':p['id'],'at':p['updatedAt']}); return p,201
        match=re.fullmatch(r'/api/v1/promotions/([^/]+)(?:/(activate|deactivate))?',path)
        if match:
            ident, action=match.groups(); p=PROMOTIONS.get(ident)
            if not p or p.get('deleted'): return error('promotion not found',404)
            if action and method=='POST': p['active']=action=='activate'; p['updatedAt']=datetime.utcnow().isoformat()+'Z'; AUDIT.append({'action':action.upper(),'promotionId':ident,'at':p['updatedAt']}); return p,200
            if method=='GET': return p,200
            if method=='PUT': p=create_promotion(self.read(),p); p['version']+=1; PROMOTIONS[ident]=p; AUDIT.append({'action':'UPDATE','promotionId':ident,'at':p['updatedAt']}); return p,200
            if method=='DELETE': p['deleted']=True; AUDIT.append({'action':'DELETE','promotionId':ident,'at':datetime.utcnow().isoformat()+'Z'}); return {},204
        return error('route not found',404)
    def do_any(self):
        try:
            body,status=self.route()
            if status is not None: self.send(body,status)
        except ValueError as exc: self.send(*error(str(exc)))
        except Exception: logging.exception('Unhandled error'); self.send({'error':{'code':'INTERNAL_ERROR','message':'internal server error'}},500)
    do_GET=do_POST=do_PUT=do_DELETE=do_any

OPENAPI={'openapi':'3.0.3','info':{'title':'ShopperStop Promotional Pricing API','version':'1.0.0'},'paths':{p:{m:{'responses':{'200':{'description':'Success'}}} for m in methods} for p,methods in {'/health':['get'],'/api/v1/bills/calculate':['post'],'/api/v1/promotions':['get','post'],'/api/v1/promotions/{id}':['get','put','delete'],'/api/v1/promotions/{id}/activate':['post'],'/api/v1/promotions/{id}/deactivate':['post'],'/api/v1/promotions/simulate':['post'],'/api/v1/customer-tiers':['get','post']}.items()}}
def run(port=8000): ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
if __name__=='__main__': run()
