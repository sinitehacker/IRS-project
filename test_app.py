import unittest
from app import calculate, create_promotion, active_promotions

def bill(amount, tier='regular'):
    return {'customer':{'tier':tier},'items':[{'name':'Cart','quantity':1,'unitPrice':amount}]}

class PricingTests(unittest.TestCase):
    def test_regular_slabs(self): self.assertEqual(calculate(bill(15000))['finalTotal'],13500)
    def test_premium_slabs(self): self.assertEqual(calculate(bill(15000,'premium'))['finalTotal'],12000)
    def test_boundary(self): self.assertEqual(calculate(bill(5000))['discountTotal'],0)
    def test_flat_promotion(self):
        p=create_promotion({'name':'500 off','type':'FLAT','value':500,'minimumOrder':3000}); p['active']=True
        self.assertEqual(calculate(bill(6000),[p])['finalTotal'],5400)
    def test_category_promotion(self):
        p=create_promotion({'name':'Electronic sale','type':'CATEGORY','value':25,'category':'Electronics'}); p['active']=True
        data={'customer':{'tier':'regular'},'items':[{'name':'TV','category':'Electronics','quantity':1,'unitPrice':10000}]}
        self.assertEqual(calculate(data,[p])['finalTotal'],7000)
    def test_time_filter(self):
        p=create_promotion({'name':'Happy Hour','type':'TIME','value':5,'timeWindow':{'start':'17:00','end':'20:00'}});p['active']=True
        self.assertEqual(len(active_promotions({'time':'18:00'},[p])),1); self.assertEqual(len(active_promotions({'time':'12:00'},[p])),0)
    def test_invalid_amount(self):
        with self.assertRaises(ValueError): calculate(bill(-1))
if __name__=='__main__': unittest.main()
