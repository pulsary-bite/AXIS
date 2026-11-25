import tempfile,unittest,sqlite3,math
from pathlib import Path
from unittest.mock import patch
import worker as w
def candles(n):
    a=[]
    for i in range(n):
        o=65000*math.exp(i*.002);c=o*1.002
        a.append((i*w.HOUR,o,c*1.0001,o*.9999,c))
    return a
class TestWorker(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'s.db';self.db=w.connect(self.path);self.a=candles(150)
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def run_at(self,n):return w.advance(self.db,self.a[:n],n*w.HOUR)
    def test_forward_only(self):
        s=self.run_at(90);self.assertEqual(s['cash'],50);self.assertEqual(s['closed'],0);self.assertEqual(s['last'],89*w.HOUR)
    def test_replay_is_idempotent(self):
        self.run_at(90);s=self.run_at(120);n=self.db.execute('SELECT count(*) FROM events').fetchone()[0];q=self.run_at(120);self.assertEqual(s['equity'],q['equity']);self.assertEqual(n,self.db.execute('SELECT count(*) FROM events').fetchone()[0])
    def test_restart(self):
        self.run_at(90);s=self.run_at(120);self.db.close();self.db=w.connect(self.path);self.assertEqual(w.read(self.db)['last'],s['last']);self.run_at(150)
    def test_missing_data(self):
        self.run_at(90);before=w.read(self.db);with_gap=self.a[:100]+self.a[101:120]
        with self.assertRaises(ValueError):w.advance(self.db,with_gap,120*w.HOUR)
        self.assertEqual(w.read(self.db),before)
    def test_stale_data(self):
        with self.assertRaises(ValueError):w.advance(self.db,self.a[:90],99*w.HOUR)
    def test_unclosed(self):
        with self.assertRaises(ValueError):w.advance(self.db,self.a[:90],89*w.HOUR)
    def test_cash_reconciliation(self):
        self.run_at(90)
        with patch('worker.ml_signal',return_value=True):s=self.run_at(150)
        import json
        pnl=sum(json.loads(x[0])['pnl'] for x in self.db.execute("SELECT payload FROM events WHERE kind='PAPER_EXIT'"))
        self.assertAlmostEqual(s['cash']+(s['pos']['cost'] if s['pos'] else 0),50+pnl,places=8);self.assertGreaterEqual(s['cash'],0)
    def test_rollback(self):
        self.run_at(90);before=w.read(self.db)
        with patch('worker.write',side_effect=RuntimeError('test')):
            with self.assertRaises(RuntimeError):self.run_at(91)
        self.assertEqual(w.read(self.db),before)
    def test_failed_feed_no_new_trades(self):
        self.run_at(90);before=w.read(self.db)
        with patch('worker.fetch',side_effect=RuntimeError('network')):
            with self.assertRaises(RuntimeError):w.tick(self.db)
        s=w.read(self.db);self.assertEqual(s['last'],before['last']);self.assertEqual(s['equity'],before['equity']);self.assertEqual(s['last_error'],'network')
