import os,tempfile,unittest
from fastapi.testclient import TestClient
import main
class SimulationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();main.DB=self.tmp.name+'/test.db';self.client=TestClient(main.app);self.client.__enter__();self.a=self.make('Alpha');self.b=self.make('Beta')
 def tearDown(self):self.client.__exit__(None,None,None);self.tmp.cleanup()
 def make(self,name):
  r=self.client.post('/api/companies',json={'name':name,'count':100,'eps':20,'active_pct':100,'exception_pct':0});self.assertEqual(r.status_code,200,r.text);return r.json()['id']
 def path(self,cid,tail):return f'/api/companies/{cid}/{tail}'
 def test_isolation(self):
  e=self.client.get(self.path(self.a,'employees')).json()['items'][0];self.assertEqual(self.client.get(self.path(self.b,f"employees/{e['id']}")).status_code,404);self.assertEqual(self.client.get(self.path(self.a,'summary')).json()['employees'],100)
 def test_engine_reset(self):
  self.client.post(self.path(self.a,'simulation/start'));main.tick();events=self.client.get(self.path(self.a,'events')).json()['items'];self.assertGreater(len(events),1);self.assertTrue(all(x['company']==self.a for x in events));self.client.post(self.path(self.a,'simulation/reset'));self.assertEqual(self.client.get(self.path(self.a,'events')).json()['total'],0);self.assertEqual(self.client.get(self.path(self.a,'summary')).json()['employees'],100)
 def test_offboarding(self):
  e=self.client.get(self.path(self.a,'employees')).json()['items'][0]['id'];self.client.post(self.path(self.a,f'employees/{e}/operation'),json={'action':'terminate'});p=self.client.get(self.path(self.a,f'employees/{e}')).json();self.assertEqual(p['employee']['status'],'terminated');self.assertTrue(all(a['status']=='disabled' for a in p['accounts']));self.assertEqual(p['grants'],[])
 def test_export(self):
  r=self.client.get(self.path(self.a,'export/json'));self.assertEqual(r.status_code,200);self.assertEqual(r.json()[0]['action'],'company.create')
if __name__=='__main__':unittest.main()
