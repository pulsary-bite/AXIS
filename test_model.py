import math,random,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
import model as m,worker as w

def synth(n=3000,seed=42):
    r=random.Random(seed);p=65000;a=[]
    for i in range(n):
        o=p;c=o*(1+math.sin(i/70)*.0015+(r.random()-.5)*.012);h=max(o,c)*(1+r.random()*.003);l=min(o,c)*(1-r.random()*.003);a.append((i*w.HOUR,o,h,l,c));p=c
    return a

class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.a=synth();cls.res=m.train(cls.a)
    def test_feature_causality(self):
        for i in (72,100,800,1500):self.assertEqual(m.features(self.a,i),m.features(self.a[:i+1],i))
    def test_mature_labels(self):
        for end in (1500,2250,3000):
            for i,v,mode,r,j in m.samples(self.a,72,end):self.assertLess(j,end)
    def test_holdout_does_not_train(self):
        a=self.a;modified=a[:2250]+[(t,o*2,h*2,l*2,c*2) for t,o,h,l,c in a[2250:]];r=m.train(modified)
        self.assertEqual(self.res.get('model'),r.get('model'));self.assertEqual(self.res['threshold'],r['threshold'])
    def test_short_history_fails_closed(self):self.assertFalse(m.train(self.a[:300])['active'])
    def test_probability_finite(self):
        model=m.fit(m.samples(self.a,72,1500));self.assertIsNotNone(model);self.assertTrue(0<m.prob(model,m.features(self.a,2000)[0])<1)
    def test_worker_training_prefix(self):
        with tempfile.TemporaryDirectory() as d:
            db=w.connect(Path(d)/'x.db');seen=[]
            def fake(a):seen.append(a[-1][0]);return {'active':False,'reason':'test','train_n':0,'threshold':None}
            with patch('model.train',side_effect=fake):
                w.advance(db,self.a[:800],800*w.HOUR);w.advance(db,self.a[:850],850*w.HOUR)
                self.assertEqual(seen,[799*w.HOUR,823*w.HOUR,847*w.HOUR]);self.assertEqual(w.read(db)['closed'],0)
            db.close()
    def test_rejected_model_no_entry(self):
        with tempfile.TemporaryDirectory() as d:
            db=w.connect(Path(d)/'x.db')
            with patch('model.train',return_value={'active':False,'reason':'test','train_n':0,'threshold':None}),patch('model.candidate',return_value=True):
                w.advance(db,self.a[:800],800*w.HOUR);s=w.advance(db,self.a[:850],850*w.HOUR)
                self.assertEqual(s['equity'],50);self.assertIsNone(s['pos']);self.assertEqual(s['closed'],0)
            db.close()
    def test_no_implicit_migration(self):
        with tempfile.TemporaryDirectory() as d:
            db=w.connect(Path(d)/'x.db');s=w.initial();s['version']='0.5';w.write(db,s)
            with self.assertRaisesRegex(ValueError,'fresh DB'):w.advance(db,self.a[:800],800*w.HOUR)
            self.assertEqual(w.read(db)['version'],'0.5');db.close()
