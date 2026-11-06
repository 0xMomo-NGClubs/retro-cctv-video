"""Offline regression tests. No service credentials or network requests are used."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from rh_workflow import compile_project,submit,poll,SECTIONS
from rh_client import APIError,SubmissionUnknown,Client
from osd import Renderer
from common import digest

class MockClient:
    key='offline-test-only';base='https://www.runninghub.ai'
    def __init__(self,outcome=None):self.calls=0;self.outcome=outcome
    def upload(self,p):return 'uploaded-image.png'
    def create(self,*a):
        self.calls+=1
        if self.outcome:raise self.outcome
        return '123'

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.graph={
          '1':{'class_type':'LoadImage','inputs':{'image':'old.png'}},
          '2':{'class_type':'Text','inputs':{'text':'old'}},
          '3':{'class_type':'Float','inputs':{'value':8}},
          '4':{'class_type':'Noise','inputs':{'seed':1}},
          '5':{'class_type':'MiniMaxH3AudioConditioningT8','inputs':{'prompt':['2',0],'duration':['3',0],'ref_images.ref_image_0':['9',0],'ref_videos.ref_video_0':['10',0]}},
          '6':{'class_type':'Sampler','inputs':{'conditioning':['5',0],'noise':['4',0]}},
          '7':{'class_type':'VHS_VideoCombine','inputs':{'images':['6',0]}},
          '8':{'class_type':'ExpensiveUpscaler','inputs':{'images':['7',0]}},
          '9':{'class_type':'LoadImage','inputs':{'image':'stale.png'}},
          '10':{'class_type':'VHS_LoadVideo','inputs':{'video':'stale.mp4'}}}
        self.cfg={'workflow_file':'graph.json','workflow_id':'999','bindings':{'prompt':{'node':'2','field':'text','class_type':'Text'},'duration':{'node':'3','field':'value'},'seed':{'node':'4','field':'seed'}},'conditioning_nodes':['5'],'image_bindings':[{'node':'1','field':'image'}],'output_nodes':['7'],'result_node':'7','shots':[{'id':'S001','prompt_file':'prompt.txt','duration_seconds':8,'seed':42,'images':['image.png']}]}
        (self.root/'graph.json').write_text(json.dumps(self.graph));(self.root/'image.png').write_bytes(b'offline image fixture')
        (self.root/'prompt.txt').write_text('\n'.join(SECTIONS)+' <Picture 1>')
        self.path=self.root/'project.json';self.save();self.state=self.root/'state.json'
    def save(self):self.path.write_text(json.dumps(self.cfg))
    def tearDown(self):self.temp.cleanup()
    def test_prunes_paid_branch_and_stale_media(self):
        _,_,g,_,fp=compile_project(self.path,'S001')
        self.assertEqual(set(g),set('1234567'));self.assertEqual(g['5']['inputs']['ref_images.ref_image_0'],['1',0]);self.assertNotIn('ref_videos.ref_video_0',g['5']['inputs'])
        *_,remote_fp=compile_project(self.path,'S001',['remote.png']);self.assertEqual(fp,remote_fp)
    def test_two_overrides_on_same_node(self):
        self.graph['6']['inputs'].update(steps=4,guidance=1)
        (self.root/'graph.json').write_text(json.dumps(self.graph))
        self.cfg['overrides']=[{'node':'6','field':'steps','value':5},{'node':'6','field':'guidance','value':2}];self.save()
        _,_,g,_,_=compile_project(self.path,'S001');self.assertEqual(g['6']['inputs']['guidance'],2)
    def test_invalid_picture_and_class(self):
        (self.root/'prompt.txt').write_text('\n'.join(SECTIONS)+' <Picture 2>')
        with self.assertRaisesRegex(ValueError,'no uploaded'):compile_project(self.path,'S001')
        (self.root/'prompt.txt').write_text('\n'.join(SECTIONS));self.cfg['bindings']['prompt']['class_type']='Wrong';self.save()
        with self.assertRaisesRegex(ValueError,'Class mismatch'):compile_project(self.path,'S001')
    def test_connected_stale_media_rejected(self):
        self.graph['6']['inputs']['extra']=['10',0];(self.root/'graph.json').write_text(json.dumps(self.graph))
        with self.assertRaisesRegex(ValueError,'Unbound media'):compile_project(self.path,'S001')
    def test_unknown_never_resubmitted(self):
        c=MockClient(SubmissionUnknown('simulated timeout'))
        with self.assertRaises(SubmissionUnknown):submit(self.path,'S001',self.state,c)
        self.assertEqual(json.loads(self.state.read_text())['status'],'SUBMISSION_UNKNOWN')
        with self.assertRaisesRegex(ValueError,'Will not resubmit'):submit(self.path,'S001',self.state,c)
        self.assertEqual(c.calls,1)
    def test_reuses_known_id_and_blocks_changed_inputs(self):
        c=MockClient();self.assertEqual(submit(self.path,'S001',self.state,c)['task_id'],'123')
        submit(self.path,'S001',self.state,c);self.assertEqual(c.calls,1)
        self.cfg['shots'][0]['seed']=43;self.save()
        with self.assertRaisesRegex(ValueError,'changed'):submit(self.path,'S001',self.state,c)
    def test_crash_after_submit_stays_unknown(self):
        c=MockClient(RuntimeError('simulated unexpected response'))
        with self.assertRaises(RuntimeError):submit(self.path,'S001',self.state,c)
        self.assertEqual(json.loads(self.state.read_text())['status'],'SUBMISSION_UNKNOWN')
    def test_input_changes_during_upload_do_not_submit(self):
        c=MockClient()
        def upload(p):
            self.cfg['shots'][0]['seed']=45;self.save();return 'remote.png'
        c.upload=upload
        with self.assertRaisesRegex(ValueError,'changed during upload'):submit(self.path,'S001',self.state,c)
        self.assertEqual(c.calls,0)
    def test_client_redirect_is_unknown_for_create(self):
        class Response:status_code=302
        class Transport:
            def post(self,*args,**kwargs):
                assert kwargs['allow_redirects'] is False
                return Response()
        c=Client(key='offline-test',transport=Transport())
        with self.assertRaises(SubmissionUnknown):c.create('999',{})

class OSDTests(unittest.TestCase):
    """Fonts supplied explicitly by caller; absent fonts skip only these tests."""
    @classmethod
    def setUpClass(cls):
        import os
        cls.fonts=os.environ.get('CCTV_TEST_FONT_DIR')
        if not cls.fonts:raise unittest.SkipTest('Set CCTV_TEST_FONT_DIR to a verified project font cache')
    def renderer(self,**kwargs):return Renderer({'font_dir':self.fonts,'start_time':'09:59:59',**kwargs},Path.cwd(),(1280,720))
    def test_clock_hour_and_date_rollover(self):
        r=self.renderer();self.assertEqual(r.text_at(1),'10:00:00')
        r=self.renderer(start_time='23:59:59',date='2026-12-31');self.assertEqual(r.text_at(1),'2027年01月01日00:00:00')
    def test_digits_fixed_cells_and_soft_transparency(self):
        r=self.renderer(camera='CAM1',place='庭院');self.assertEqual({r.glyph(x)[1] for x in '0123456789'},{16})
        a=r.render(0).getchannel('A');self.assertEqual(a.getpixel((640,360)),0);self.assertTrue(any(0<n<255 for n in a.getdata()))
    def test_fractional_tail_gets_extra_osd(self):
        r=self.renderer()
        with tempfile.TemporaryDirectory() as t:
            meta=r.write(1.125,t);self.assertEqual(meta['osd_frames'],3);self.assertTrue((Path(t)/'osd-000002.png').exists())
    def test_missing_glyph_fails(self):
        with self.assertRaisesRegex(ValueError,'explicit glyph'):self.renderer().glyph('\U0001f600')

if __name__=='__main__':unittest.main()
