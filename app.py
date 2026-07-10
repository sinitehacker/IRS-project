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
    def read(self):
        try: return json.loads(self.rfile.read(int(self.headers.get('Content-Length','0')) or 0) or '{}')
        except json.JSONDecodeError: raise ValueError('request body must be valid JSON')
    def route(self):
        path=urlparse(self.path).path; method=self.command; parts=path.strip('/').split('/')
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
            body,status=self.route(); self.send(body,status)
        except ValueError as exc: self.send(*error(str(exc)))
        except Exception: logging.exception('Unhandled error'); self.send({'error':{'code':'INTERNAL_ERROR','message':'internal server error'}},500)
    do_GET=do_POST=do_PUT=do_DELETE=do_any

OPENAPI={'openapi':'3.0.3','info':{'title':'ShopperStop Promotional Pricing API','version':'1.0.0'},'paths':{p:{m:{'responses':{'200':{'description':'Success'}}} for m in methods} for p,methods in {'/health':['get'],'/api/v1/bills/calculate':['post'],'/api/v1/promotions':['get','post'],'/api/v1/promotions/{id}':['get','put','delete'],'/api/v1/promotions/{id}/activate':['post'],'/api/v1/promotions/{id}/deactivate':['post'],'/api/v1/promotions/simulate':['post'],'/api/v1/customer-tiers':['get','post']}.items()}}
def run(port=8000): ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
if __name__=='__main__': run()
