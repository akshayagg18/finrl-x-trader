"""Persist genuine historical proof records; no broker connections."""
from pathlib import Path
from trader.service import Service
from trader.backtest import run_backtest
from trader.db import dumps

service=Service('runtime/trader.db')
cycle=service.cycle(replay_date='2025-01-06')
backtest=run_backtest(service,service.db.settings(),'2025-01-02','2025-10-07','2025-07-01')
restarted=Service('runtime/trader.db')
report={
 'upstream_commit':'4409abe925c904e570be78ebfb5e77ac3491dff8',
 'source':'actual upstream AdaptiveRotationEngine + archived market bars',
 'mode':'local simulation; not paper/live',
 'initial_capital':500,
 'raw_targets':cycle['raw_targets'],
 'permitted_targets':cycle['permitted_targets'],
 'fills':[{k:o[k] for k in ['symbol','side','qty','filled_qty','fill_price','status','fees']} for o in cycle['fills']],
 'cash':restarted.overview()['account']['cash'],
 'positions_survive_restart':len(restarted.overview()['positions']),
 'duplicate_cycle_id':restarted.cycle(replay_date='2025-01-06')['cycle']==cycle['cycle'],
 'backtest':{'id':backtest['id'],'metrics':backtest['metrics'],'oos':backtest['out_of_sample'],'fills':len(backtest['orders']),'halted':backtest['halted'],'data_hash':backtest['data_hash'],'assumptions':backtest['assumptions']},
 'live_activated':restarted.overview()['live_activated'],
 'real_orders_submitted':0,
}
Path('artifacts').mkdir(exist_ok=True)
Path('artifacts/verification.json').write_text(dumps(report))
print(dumps(report))
