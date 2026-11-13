#!/usr/bin/env python3
"""Small, offline checks for the six-snapshot accounting rules."""
import importlib.util
from decimal import Decimal
from pathlib import Path
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/nopie_memory_delta_reconciliation.py'
spec=importlib.util.spec_from_file_location('reconcile',SCRIPT)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def row(boot,pid,name,exe,total):
    return {'boot':boot,'pid':pid,'name':name,'exe':exe,'Pss_kB':total,
            'SwapPss_kB':0,'measurement_status':'measured','vmas':1,
            'missing_vmas':0,'source':'synthetic'}


class AccountingTests(unittest.TestCase):
    def test_missing_swap_is_not_zero(self):
        lines=['1000-2000 r-xp 00000000 00:00 1 /usr/bin/a\n','Pss: 4 kB\n']
        got=mod.parse_smaps_lines(lines)
        self.assertEqual(got['missing_vmas'],1)

    def test_same_comm_different_exe_and_multiple_instances(self):
        boots={'GCC1':[row('GCC1',1,'svc','/usr/bin/a',2),
                       row('GCC1',2,'svc','/usr/bin/b',3),
                       row('GCC1',3,'svc','/usr/bin/b',4)]}
        ledger=mod.derive_partitions(boots,{('svc','/usr/bin/a')})
        self.assertEqual([r['set'] for r in ledger],['C','R','R'])
        self.assertNotEqual(mod.identity(ledger[0]),mod.identity(ledger[1]))

    def test_absence_vs_unknown_and_single_boot_mean(self):
        ledger=[{**row('noPIE1',11,'x','/usr/bin/x',10),'set':'R','total_kB':10}]
        coverage={b:{'incomplete_pids':[]} for b in ('GCC1','GCC2','LLVM31','LLVM32','noPIE1','noPIE2')}
        got=mod.remaining_contributions(ledger,coverage)[0]
        self.assertEqual(got['new_mean_kB'],5)
        self.assertEqual(got['new2_state'],'absent_in_capture')
        coverage['noPIE2']['incomplete_pids']=[99]
        got=mod.remaining_contributions(ledger,coverage)[0]
        self.assertEqual(got['new2_state'],'unknown_not_measured')
        self.assertIsNone(got['new_mean_kB'])
        self.assertIsNone(got['new2_kB'])
        self.assertEqual(got['observed_new_mean_kB'],5)  # accounting, not an absence claim

    def test_duplicate_pid_rejected(self):
        r=row('GCC1',1,'svc','/usr/bin/a',2)
        with self.assertRaisesRegex(ValueError,'duplicate PID'):
            mod.derive_partitions({'GCC1':[r,r]},set())

    def test_conservation_failure_rejected(self):
        images=[]
        for image,T,C,R in [('GCC',0,0,0),('LLVM3',0,0,0),('noPIE',20,10,5)]:
            images.append({'image':image,'T_mean_kB':Decimal(T),
                           'C_mean_kB':Decimal(C),'R_mean_kB':Decimal(R)})
        with self.assertRaisesRegex(ValueError,'conservation failed'):
            mod.compare_image(images)


if __name__=='__main__':unittest.main()
