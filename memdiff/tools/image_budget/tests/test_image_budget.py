import importlib.util
import collections
import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import budget
import collect
import compare


def parser_module():
    spec = importlib.util.spec_from_file_location('parse_pages_test', ROOT/'engine/parse_pages.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def raw(pid, inode):
    return (f'__MAPS_BEGIN__\n1000-2000 r-xp 00000000 00:01 {inode} /usr/lib/a.so\n__MAPS_END__\n'
            f'__SMAPS_BEGIN__\n1000-2000 r-xp 00000000 00:01 {inode} /usr/lib/a.so\n'
            'Rss: 4 kB\nPss: 4 kB\nPrivate_Dirty: 0 kB\n__SMAPS_END__\n'
            '__PAGE_BEGIN__\t1000-2000\tr-xp\t00000000\t/usr/lib/a.so\t1\n'
            '8000000000000000\n__PAGE_END__\t0\n__DONE__\n')


class ImageBudgetTests(unittest.TestCase):
    def test_process_exits_during_collection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'process.stdout'
            path.write_text('__EXITED__\n')
            records, issues = parser_module().parse_process(path, 12, 4096)
            self.assertEqual(records, [])
            self.assertTrue(any('missing DONE' in x for x in issues))

    def test_elf_pull_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp)/'libmissing.so'
            self.assertEqual(collect.pull_status(1, missing), 'pull_failed')
            self.assertEqual(collect.pull_status(0, missing), 'pull_failed')

    def test_remote_rc_is_not_host_rc(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'raw').mkdir()
            output=root/'raw/test.stdout';output.write_bytes(b'failure\n__IMAGE_BUDGET_RC__17\n')
            records=[]
            original=collect.HERE
            collect.HERE=root
            try:
                with mock.patch.object(collect,'run',return_value=(0,'failure\n__IMAGE_BUDGET_RC__17\n')):
                    # The mocked run does not append a record, so seed the expected command entry.
                    records.append({'stdout':'raw/test.stdout'})
                    rc, text=collect.shell('127.0.0.1','test','false',records,required=False)
                self.assertEqual(rc,17)
                self.assertEqual(text,'failure')
                self.assertEqual(records[-1]['remote_rc'],17)
            finally:
                collect.HERE=original

    def test_stable_window_cpu_at_threshold(self):
        samples=[{'uptime_s':600+i*30,'available_kB':90000+i,'swap_used_kB':1000+i,
                  'cpu_busy_percent':21} for i in range(10)]
        self.assertTrue(collect.steady_window(samples,100000))
        samples[-1]['cpu_busy_percent']=22
        self.assertFalse(collect.steady_window(samples,100000))

    def test_same_path_multiple_inodes_is_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'raw').mkdir()
            processes = []
            for pid, inode in ((11,100),(12,101)):
                name = f'raw/process_{pid}.stdout'
                (root/name).write_text(raw(pid,inode))
                processes.append({'pid':pid,'status':'complete','raw':name})
            (root/'collection.json').write_text(json.dumps({'status':'DONE','root_restored':True,
                 'page_size':4096,'processes':processes}))
            parser = parser_module(); parser.HERE = root; parser.main()
            result=(root/'files_from_pages.tsv').read_text()
            self.assertIn('multiple_dev_inode',result)

    def test_cross_section_page_allocation(self):
        sections=[{'name':'.dynsym','kind':'DYNSYM','offset':0,'size':1024},
                  {'name':'.text','kind':'PROGBITS','offset':1024,'size':3072},
                  {'name':'.bss','kind':'NOBITS','offset':4090,'size':200}]
        allocated=budget.allocate_page(0,4096,sections)
        self.assertEqual(allocated['.dynsym'],1)
        self.assertEqual(allocated['.text'],3)
        self.assertNotIn('.bss',allocated)

    def test_compare_strict_process_pairing(self):
        baseline=[{('a','/bin/a'):collections.Counter({'Pss_total_kB':5}),
                   ('b','/bin/b'):collections.Counter({'Pss_total_kB':3})}]
        new=[{('a','/bin/a'):collections.Counter({'Pss_total_kB':4}),
              ('c','/bin/c'):collections.Counter({'Pss_total_kB':2})}]
        matched,bonly,nonly=compare.key_status(baseline,new)
        self.assertEqual(matched,{('a','/bin/a')})
        self.assertEqual(bonly,{('b','/bin/b')})
        self.assertEqual(nonly,{('c','/bin/c')})

    def test_compare_noise_rule(self):
        self.assertEqual(compare.verdict(5,6,4,2,2),'无显著差异')
        self.assertEqual(compare.verdict(7,6,4,2,2),'超出两边开机波动')
        self.assertIn('无波动数据',compare.verdict(7,0,0,1,1))


if __name__ == '__main__': unittest.main()
