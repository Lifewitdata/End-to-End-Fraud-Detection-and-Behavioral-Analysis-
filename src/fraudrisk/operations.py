"""Transaction reporting and label-blind retrospective review-budget comparisons."""
import numpy as np
import pandas as pd
from .evaluation import metrics


def bounded_queue(frame,scores,threshold,fraction,capacity):
    """End-of-hour batch ranking, not a real-time authorisation decision.

    Ties use ingestion row_id. No labels or amount enter selection. A floor
    prevents small batches from exceeding the percentage budget.
    """
    if not 0<=fraction<=1 or capacity<0:
        raise ValueError('Invalid review budget')
    work=pd.DataFrame({'step':frame.step.to_numpy(),'score':scores,
                       'row_id':frame.row_id.to_numpy(),'position':np.arange(len(frame))})
    limits=work.groupby('step').size().mul(fraction).apply(np.floor).clip(upper=capacity)
    eligible=work[work.score>=threshold].sort_values(['step','score','row_id'],ascending=[True,False,True])
    rank=eligible.groupby('step').cumcount()
    selected=eligible.loc[rank<eligible.step.map(limits),'position'].to_numpy()
    result=np.zeros(len(frame),dtype=bool);result[selected]=True
    return result


def write_operations(out,history,validation,val_scores,test,test_scores,threshold,cfg):
    rows=[]
    for period,frame,scores in [('validation',validation,val_scores),('test',test,test_scores)]:
        for budget in [.01,.05,.10]:
            flags=bounded_queue(frame,scores,threshold,budget,cfg['review_capacity_per_step'])
            rows.append(dict(period=period,budget_fraction=budget,**metrics(frame,flags,cfg)))
    pd.DataFrame(rows).to_csv(out/'review_budget_comparison.csv',index=False)
    # Predeclared illustrative budget; never choose a winner using test labels.
    flags=bounded_queue(test,test_scores,threshold,.05,cfg['review_capacity_per_step'])
    test.loc[flags,['row_id','step','type','amount','score']].to_csv(out/'bounded_review_queue.csv',index=False)
    hourly=history.groupby('step').agg(transactions=('row_id','size'),transaction_value=('amount','sum'),
        average_transaction_value=('amount','mean'),active_senders=('nameOrig','nunique'),active_recipients=('nameDest','nunique')).reset_index()
    mix=history.groupby('type').agg(transactions=('row_id','size'),transaction_value=('amount','sum'),average_transaction_value=('amount','mean')).reset_index()
    mix['transaction_share']=mix.transactions/len(history)
    segment=np.select([history.sender_count_24h.eq(0),history.sender_count_24h.le(3)],
        ['No prior activity in 24h','1-3 prior transactions'],default='4+ prior transactions')
    segments=history.groupby(segment).agg(transactions=('row_id','size'),transaction_value=('amount','sum'),
        fraud_cases=('isFraud','sum'),fraud_rate=('isFraud','mean')).rename_axis('activity_segment').reset_index()
    checks={
        'hourly_rows':int(hourly.transactions.sum())==len(history),
        'type_rows':int(mix.transactions.sum())==len(history),
        'segment_rows':int(segments.transactions.sum())==len(history),
        'hourly_amount':bool(np.isclose(hourly.transaction_value.sum(),history.amount.sum(),rtol=1e-12,atol=.01)),
        'type_amount':bool(np.isclose(mix.transaction_value.sum(),history.amount.sum(),rtol=1e-12,atol=.01)),
        'segment_amount':bool(np.isclose(segments.transaction_value.sum(),history.amount.sum(),rtol=1e-12,atol=.01)),
    }
    if not all(checks.values()): raise ValueError('Transaction reporting reconciliation failed')
    hourly.to_csv(out/'transaction_metrics.csv',index=False)
    mix.to_csv(out/'transaction_mix.csv',index=False)
    segments.to_csv(out/'activity_segments.csv',index=False)
    pd.DataFrame([{'check':k,'passed':v} for k,v in checks.items()]).to_csv(out/'transaction_reconciliation.csv',index=False)
    report=out/'dashboard.html'
    if report.exists():
        extra='<section><h2>Transaction performance (full input)</h2>'+mix.to_html(index=False,escape=True)+'</section>'
        extra+='<section><h2>Review-budget trade-offs</h2><p>Predeclared end-of-hour batch policies. No test-based winner selection; smaller queues may miss valuable cases.</p>'
        extra+=pd.DataFrame(rows)[['period','budget_fraction','alerts','precision','recall','missed_fraud_value','peak_alerts_per_step']].to_html(index=False,escape=True)+'</section>'
        report.write_text(report.read_text().replace('</main>',extra+'</main>'))
    with (out/'stakeholder_brief.md').open('a') as brief:
        brief.write('\n## Operational alternatives\nSee review_budget_comparison.csv for predeclared 1%, 5%, and 10% end-of-hour batch budgets. The 5% queue is illustrative, not an optimum or real-time authorisation policy. These alternatives do not replace the original evaluation. Selection is label-blind; evaluation requires mature outcomes.\n')
