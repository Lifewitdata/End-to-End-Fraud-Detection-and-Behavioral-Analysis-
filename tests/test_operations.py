import json
import numpy as np
import pandas as pd
import pytest
from fraudrisk.data import make_demo,validate,DataValidationError
from fraudrisk.pipeline import run
from fraudrisk.operations import bounded_queue


def test_budget_ties_no_label_dependency():
    f=pd.DataFrame({'step':[1]*20+[2]*20,'row_id':range(40),'isFraud':[0]*40})
    flags=bounded_queue(f,np.ones(40),.5,.1,1)
    assert list(np.flatnonzero(flags))==[0,20]
    f['isFraud']=1
    assert np.array_equal(flags,bounded_queue(f,np.ones(40),.5,.1,1))
    assert not bounded_queue(f,np.ones(40),2,.1,1).any()
    assert not bounded_queue(f,np.ones(40),.5,0,1).any()
    assert not bounded_queue(f.head(1),np.ones(1),.5,.05,100).any()


def test_failed_run_preserves_output_and_safe_evidence(tmp_path):
    out=tmp_path/'published';out.mkdir()
    (out/'manifest.json').write_text('{"old":true}')
    source=tmp_path/'bad.csv';d=make_demo(source,rows=100)
    d['amount']=d.amount.astype(object);d.loc[0,'amount']='PRIVATE_INVALID_VALUE'
    d.to_csv(source,index=False)
    with pytest.raises(DataValidationError): run(input_path=source,output_dir=out)
    assert json.loads((out/'manifest.json').read_text())=={'old':True}
    failure=next((tmp_path/'published_failures').glob('*.json')).read_text()
    assert 'PRIVATE_INVALID_VALUE' not in failure
    report=json.loads(failure)
    assert report['row_positions']['amount']==[0]
    assert len(report['input_sha256'])==64
    assert not report['published_outputs_changed']


def test_negative_positions_and_empty_input(tmp_path):
    d=make_demo(tmp_path/'in.csv',rows=20);d.loc[4,'amount']=-1
    with pytest.raises(DataValidationError) as exc: validate(d)
    assert exc.value.positions['negative_amounts']==[4]
    with pytest.raises(DataValidationError): validate(d.iloc[:0])
