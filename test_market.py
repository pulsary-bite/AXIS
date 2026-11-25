import unittest
from urllib.parse import urlparse,parse_qs
from datetime import datetime
from unittest.mock import patch
import market,worker
class MarketTests(unittest.TestCase):
    def fake(self,url):
        q=parse_qs(urlparse(url).query)
        lo=int(datetime.fromisoformat(q['start'][0]).timestamp())
        hi=int(datetime.fromisoformat(q['end'][0]).timestamp())
        return [[t,99,102,100,101,1] for t in reversed(range(lo,hi+3600,3600))]
    def test_pagination_and_order(self):
        now=10000*market.HOUR+12345
        a=market.fetch(now,600,self.fake)
        self.assertEqual(len(a),600)
        self.assertEqual(a[-1][0],9999*market.HOUR)
        self.assertEqual(a[0][1:],(100.,102.,99.,101.))
        worker.validate(a)
    def test_gap_rejected(self):
        with self.assertRaisesRegex(ValueError,'Incomplete'):
            market.fetch(10000*market.HOUR,600,lambda url:self.fake(url)[2:])
    def test_source_switch(self):
        with patch.dict('os.environ',{'AXIS_FEED':'bybit'}):
            self.assertEqual(worker.source(),'Bybit BTCUSDT 1h')
        with patch.dict('os.environ',{'AXIS_FEED':'coinbase'}):
            self.assertEqual(worker.source(),market.SOURCE)
