"""Small conservation and classification checks for the offline hotspot pass."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nopie_memory_hotspots as h


class HotspotTests(unittest.TestCase):
    def test_unique_classification(self):
        expected = {
            ('/usr/lib/a.so', 'r-xp'): 'file_exec',
            ('/usr/lib/a.so', 'r--p'): 'file_readonly',
            ('/usr/lib/a.so', 'rw-p'): 'file_writable',
            ('[stack]', 'rw-p'): 'stack',
            ('[anon:worker]', 'rw-p'): 'anonymous',
            ('[anon]', 'rw-p'): 'anonymous',
            ('', 'rw-p'): 'anonymous',
            ('/dev/dri/card0', 'rw-s'): 'special',
            ('memfd:foo', 'rw-s'): 'special',
        }
        for (path, perm), cat in expected.items():
            self.assertEqual(h.classify(path, perm), cat)

    def test_multimap_file_and_swap(self):
        def row(pid, key, path, p, s):
            return dict(boot='B1', pid=pid, identity_key=key, path=path,
                        device='08:01', inode='11' if path.endswith('x.so') else '12',
                        category='file_exec', Pss=p, SwapPss=s,
                        Pss_plus_SwapPss_kB=p+s,
                        Private_Dirty=0, Shared_Clean=p, Rss=p)
        files = h.aggregate_files([row(1,'a','/lib/x.so',10,3),
                                   row(2,'b','/lib/x.so',20,7),
                                   row(3,'c','/lib/y.so',5,0)])
        self.assertEqual(len(files), 2)
        x = next(f for f in files if f['path']=='/lib/x.so')
        self.assertEqual((x['users_C'],x['Pss_kB'],x['SwapPss_kB'],x['total_kB']),
                         (2,30,10,40))

    def test_same_path_different_inode_rejected(self):
        base=dict(boot='GCC1',path='/lib/x.so',category='file_exec',Pss=4,
                  SwapPss=0,Pss_plus_SwapPss_kB=4,Private_Dirty=0,
                  Shared_Clean=4,Rss=4,device='08:01')
        with self.assertRaisesRegex(ValueError,'multiple device/inode'):
            h.aggregate_files([dict(base,identity_key='a',inode='11'),
                               dict(base,identity_key='b',inode='12')])

    def test_missing_is_not_unmapped(self):
        rows=[dict(boot=b,path='/lib/x.so',total_kB=v,Pss_kB=v,SwapPss_kB=0,
                   file_exec_total_kB=v,file_readonly_total_kB=0,
                   file_writable_total_kB=0,file_other_total_kB=0,users_C=1,
                   largest_C_user='a') for b,v in [('B1',2),('B2',4)]]
        # A genuinely absent mapping has zero contribution; a missing C identity fails.
        self.assertEqual(h.compare(rows,'path',['Pss_kB'])[0]['base1_present'],0)
        with self.assertRaises(ValueError):
            h.compare([dict(boot='noPIE1',identity_key='x',total_kB=1,Pss_kB=1)],
                      'identity_key',['Pss_kB'])

    def test_missing_metrics_rejected(self):
        lines=['1000-2000 r--p 00000000 00:00 0 /lib/x.so\n', 'Pss: 4 kB\n']
        rows,missing=h.parse_selected(lines,'B1',1,'x','sample')
        self.assertEqual((rows,missing),([],1))

    def test_same_name_different_exe_not_merged(self):
        records=[]
        for boot in ('GCC1','GCC2','LLVM31','LLVM32','noPIE1','noPIE2'):
            for exe in ('/bin/a','/bin/b'):
                records.append(dict(boot=boot,identity_key='same | '+exe,
                                    total_kB=1,Pss_kB=1,SwapPss_kB=0))
        compared=h.compare(records,'identity_key',['Pss_kB'])
        self.assertEqual({r['identity_key'] for r in compared if r['comparison']=='noPIE_minus_GCC'},
                         {'same | /bin/a','same | /bin/b'})

    def test_conservation_failure_detected(self):
        maps=[dict(boot='GCC1',pid=1,category='anonymous',Pss=2,SwapPss=1)]
        ledger={('GCC1',1):dict(Pss_kB='1',SwapPss_kB='1',name='x',exe='/bin/x',identity_key='x | /bin/x')}
        with self.assertRaisesRegex(ValueError,'process conservation'):
            h.aggregate_process(maps,ledger)


if __name__=='__main__': unittest.main()
