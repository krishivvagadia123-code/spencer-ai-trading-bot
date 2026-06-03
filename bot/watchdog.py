import time,traceback
from datetime import date
from bot.logger_config import get_logger
from bot.db import load_state,save_state
log=get_logger("kite-bot.watchdog")
MAX_DAILY_LOSS_PCT=3.0; MAX_RESTART_ATTEMPTS=10; RESTART_BACKOFF_SEC=[5,10,30,60,120]
class CircuitBreaker:
    def __init__(self,threshold=5): self.threshold=threshold; self.fail_count=0; self.open=False
    def record_success(self): self.fail_count=0; self.open=False
    def record_failure(self,reason=""):
        self.fail_count+=1; log.warning(f"CB failure {self.fail_count}/{self.threshold}: {reason}")
        if self.fail_count>=self.threshold: self.open=True; log.error("CIRCUIT BREAKER OPEN")
    def check(self): return not self.open
def check_daily_loss_limit(start_bal,cur_bal):
    ds=load_state(f"balance_start_{date.today()}",default=start_bal)
    if cur_bal<ds:
        pct=(ds-cur_bal)/ds*100
        if pct>=MAX_DAILY_LOSS_PCT: log.warning(f"KILL SWITCH: loss {pct:.2f}%"); return False
    return True
def record_day_start_balance(bal):
    k=f"balance_start_{date.today()}"
    if load_state(k) is None: save_state(k,bal); log.info(f"Day start: Rs.{bal:,.2f}")
def run_with_watchdog(fn,*args,**kwargs):
    attempt=0
    while attempt<MAX_RESTART_ATTEMPTS:
        try: log.info(f"Starting attempt {attempt+1}"); fn(*args,**kwargs); log.info("Clean exit."); break
        except KeyboardInterrupt: log.info("Stopped by user."); break
        except Exception as e:
            attempt+=1; wait=RESTART_BACKOFF_SEC[min(attempt-1,len(RESTART_BACKOFF_SEC)-1)]
            log.error(f"CRASH {attempt}: {e}\n{traceback.format_exc()}")
            if attempt>=MAX_RESTART_ATTEMPTS: log.critical("MAX RESTARTS. Shutting down."); break
            log.info(f"Restarting in {wait}s..."); time.sleep(wait)
